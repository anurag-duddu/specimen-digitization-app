"""Retrospective geography and G37/G38 derivations over pinned, open data.

The broker owns network execution and its durable receipts. This adapter only
reads verified reference objects and computes: historian candidates never settle
a value by themselves, GEOLocate validates modern interpretations, and a
qualified footprint supplies the uncertainty (never the model or GEOLocate).
The worker supplies persisted settled inputs, not free-form model assertions.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.georef_boundaries import Unit, extent, holding_circle, read_units
from specimen_digitization.application.georef_curated import curated_place, settles
from specimen_digitization.application.georef_datasets import (
    MANIFEST, Dataset, boundary_files, dataset, geonames_dump, verified,
)
from specimen_digitization.application.georef_elevation import (
    ElevationCoverageError, circle_bounds, pinned_elevation_range, read_pinned_tile,
)
from specimen_digitization.application.georef_geonames import find, read_dump
from specimen_digitization.application.georef_geometry import inside
from specimen_digitization.application.georef_history import interval, modern_successors, use_on
from specimen_digitization.application.georef_locality import comparison_key, read_locality
from specimen_digitization.application.georef_places import Place
from specimen_digitization.application.georef_radius import Errors, feature_only

from .contracts import (
    EvidenceItem, FieldKey, SourceCoverageReceipt, SourceCoverageState, SourceQuery,
    SourceResult, SpecialistRequest, SpecialistRole, digest,
)

VERSION = "retrospective-georeferencing-v1"
HISTORY_SOURCE = "georeference_history"
SPATIAL_SOURCE = "georeference_spatial"
ELEVATION_FIELDS = frozenset({FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M,
                             FieldKey.ELEVATION_FROM_FT, FieldKey.ELEVATION_TO_FT})
# These files describe provinces/departments and municipalities. Neither country
# has a reviewed county mapping here. Do not copy a municipality into two fields.
FIELD_LEVELS = {
    "PH": {FieldKey.PROVINCE_STATE: 2, FieldKey.CITY: 3},
    "GT": {FieldKey.PROVINCE_STATE: 1, FieldKey.CITY: 2},
}


@dataclass(frozen=True, slots=True)
class SettledLocationInput:
    """A current persisted value supplied by the worker, with its provenance."""

    field_key: FieldKey
    value: str
    evidence_ids: tuple[str, ...]
    revision: int
    authority_id: str

    def __post_init__(self):
        if (self.field_key not in {FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.COUNTY,
                                  FieldKey.CITY, FieldKey.PRECISE_LOCATION}
                or not self.value.strip() or not self.evidence_ids or not all(self.evidence_ids)
                or not self.authority_id or type(self.revision) is not int or self.revision < 0):
            raise ValueError("Derivation requires a settled value, evidence, authority and revision")


@dataclass(frozen=True, slots=True)
class Georeference:
    latitude: float
    longitude: float
    uncertainty_m: float
    footprint_dataset: str
    footprint_id: str
    authority_ids: tuple[str, ...]
    input_fields: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    tool_call_id: str
    simplification_margin_m: float = 0.0
    method: str = "administrative footprint enclosing circle widened by its simplification margin"
    geodetic_datum: str = "EPSG:4326"
    version: str = VERSION


@dataclass(frozen=True, slots=True)
class DerivationProposal:
    field_key: FieldKey
    value: str
    input_fields: tuple[str, ...]
    input_revisions: tuple[tuple[str, int], ...]
    evidence_ids: tuple[str, ...]
    authority_id: str
    dataset_ids: tuple[str, ...]
    tool_call_id: str
    value_layer: str = "derived"
    rule_version: str = VERSION


@dataclass(frozen=True, slots=True)
class DerivationResult:
    status: LookupStatus
    reason: str
    georeference: Georeference | None = None
    proposals: tuple[DerivationProposal, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    unresolved: tuple[tuple[str, str], ...] = ()
    unresolved_statuses: tuple[tuple[str, LookupStatus], ...] = ()


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _dataset_evidence(entry: Dataset) -> EvidenceItem:
    return EvidenceItem(id="dataset:" + entry.sha256, kind="qualified_dataset",
                        source_id=entry.id.split("/")[0], locator=entry.source_url,
                        response_digest=entry.sha256, source_version=entry.id,
                        publisher_assertion_id=entry.id, retrieved_at=entry.retrieved,
                        excerpt=entry.credit, role="supports")


def _result(field_key: FieldKey, status: LookupStatus, reason: str, *, candidates=(), evidence=(),
            query=None, failed=False) -> SourceResult:
    return SourceResult(status=status, evidence=tuple(evidence),
                        candidate_json=tuple(_json(candidate) for candidate in candidates),
                        coverage=SourceCoverageReceipt(
                            source_id=HISTORY_SOURCE, field_key=field_key,
                            state=(SourceCoverageState.NOT_ATTEMPTED if status == LookupStatus.POLICY
                                   else SourceCoverageState.FAILED if failed else SourceCoverageState.SEARCHED),
                            source_version=VERSION, qualification_digest=digest(VERSION),
                            query_digest=digest(query) if query is not None else None,
                            receipt_ids=tuple(item.id for item in evidence), candidate_count=len(candidates),
                            coverage_limit="Pinned country gazetteer only; a candidate needs modern validation",
                            reason=reason))


class GeoreferencingAdapter:
    """Load by manifest object name; callers provide their normal object reader.

    Missing objects and digest mismatches are operational evidence, never an empty
    gazetteer. There is no network fallback, unpinned file, or implicit download.
    """

    def __init__(self, read_dataset: Callable[[Dataset], bytes], *,
                 field_levels: Mapping[str, Mapping[FieldKey, int]] | None = None):
        self.read_dataset = read_dataset
        self.field_levels = {country: dict(levels) for country, levels in
                             (FIELD_LEVELS if field_levels is None else field_levels).items()}
        self._dumps = {}
        self._units = {}

    def _read(self, entry: Dataset) -> bytes:
        return verified(entry, self.read_dataset(entry))

    def _dump(self, country: str):
        entry = geonames_dump(country)
        if entry is None:
            raise FileNotFoundError("No pinned country gazetteer")
        if entry.id not in self._dumps:
            status, parsed = read_dump(country, self._read(entry))
            if status != LookupStatus.SUCCESS or parsed is None:
                raise ValueError("Pinned gazetteer is malformed")
            self._dumps[entry.id] = parsed
        return entry, self._dumps[entry.id]

    def _boundaries(self, country: str) -> tuple[Unit, ...]:
        entries = boundary_files(country)
        if not entries:
            raise FileNotFoundError("No pinned administrative boundaries")
        for entry in entries:
            if entry.id not in self._units:
                self._units[entry.id] = read_units(entry, self._read(entry))
        return tuple(unit for entry in entries for unit in self._units[entry.id])

    def history_query(self, request: SpecialistRequest, query: SourceQuery) -> SourceResult:
        """Broker entry: JSON country ISO2, name, optional collected_on (ISO date).

        This local search may read the collection date without disclosing it to a
        geocoder. The broker records this result through its normal effect path.
        """
        if request.scope.sensitive or request.role != SpecialistRole.GEOGRAPHY:
            raise ValueError("Historical search requires non-sensitive geography scope")
        if query.source_id != HISTORY_SOURCE or query.field_key not in request.field_keys:
            raise ValueError("Historical search exceeds source or field scope")
        try:
            arguments = json.loads(query.query_text)
            if not isinstance(arguments, dict) or set(arguments) - {"country", "name", "collected_on"}:
                raise ValueError("History query keys are country, name, collected_on")
            country, name = arguments["country"], arguments["name"]
            if (country not in {"PH", "GT"} or type(name) is not str or not name.strip()
                    or len(name) > 200):
                raise ValueError("History needs a pinned ISO country and a place name")
            collected_on = arguments.get("collected_on")
            if collected_on is not None:
                interval(collected_on)
        except (KeyError, TypeError, ValueError, OverflowError):
            return _result(query.field_key, LookupStatus.POLICY,
                           "History needs JSON country (PH/GT), name and optional ISO collected_on", query=query)
        curated = curated_place(country, name)
        if curated is not None:
            pin = digest(asdict(curated))
            evidence = EvidenceItem(id="curated-hypothesis:" + pin, kind="curated_hypothesis",
                                    source_id="curated_places", locator=curated.id, response_digest=pin,
                                    source_version=VERSION, publisher_assertion_id=curated.id,
                                    excerpt="; ".join(curated.sources))
            confirmed = settles(curated)
            return _result(query.field_key, LookupStatus.SUCCESS if confirmed else LookupStatus.AMBIGUOUS,
                           "Curator-confirmed historical crosswalk; modern proposal requires GEOLocate validation"
                           if confirmed else "G36: unconfirmed historical place requires curator review", query=query,
                           evidence=(evidence,),
                           candidates=({"hypothesis": curated.proposed, "curated_entry_id": curated.id,
                                        "sources": list(curated.sources), "confirmed": confirmed,
                                        "proposed_ids": curated.proposed_ids,
                                        "confirmation": asdict(curated.confirmation) if confirmed else None,
                                        "validation_required": "geolocate",
                                        "settlement_allowed": False},))
        try:
            entry, gazetteer = self._dump(country)
            matches = find(gazetteer, name)
        except (OSError, ValueError, KeyError):
            return _result(query.field_key, LookupStatus.PROVIDER,
                           "Pinned gazetteer absent, malformed or digest mismatch", query=query, failed=True)
        places = matches.exact or matches.near
        candidates = []
        for place in places[:10]:
            candidate = asdict(place)
            candidate.update(authority_id=f"{place.source}:{place.record_id}",
                             match_type="exact" if matches.exact else "near_spelling",
                             settlement_allowed=False, validation_required="geolocate",
                             temporal_status=use_on(place, collected_on).state if collected_on else "undated",
                             dataset_id=entry.id, source_digest=entry.sha256)
            candidates.append(candidate)
        status = LookupStatus.SUCCESS if len(places) == 1 else (
            LookupStatus.AMBIGUOUS if places else LookupStatus.NO_MATCH)
        return _result(query.field_key, status,
                       "Historical candidates require historian context and GEOLocate validation; no date inferred",
                       candidates=candidates, evidence=(_dataset_evidence(entry),), query=query)

    def derive_rest(self, *, country: str, validation: SourceResult,
                    settled_inputs: Sequence[SettledLocationInput], requested_fields: Sequence[FieldKey],
                    verbatim_locality: str, label_has_elevation: bool | None,
                    tool_call_id: str) -> DerivationResult:
        """Create editable proposals; never approve or overwrite a field.

        `validation` must be the broker's trusted GEOLocate result for this
        specimen. `settled_inputs` must be current stored final/reviewer values.
        The caller checks their scope/revisions and carries these pins into the
        proposal. No requested point or radius is accepted from a model.
        """
        if not tool_call_id or not settled_inputs:
            raise ValueError("Derivation requires its tool call and settled inputs")
        keys = [item.field_key for item in settled_inputs]
        if len(keys) != len(set(keys)):
            raise ValueError("Settled inputs must have one current revision per field")
        if validation.coverage.source_id != "geolocate":
            return DerivationResult(LookupStatus.POLICY, "Modern validation must come from GEOLocate")
        if validation.status != LookupStatus.SUCCESS:
            return DerivationResult(validation.status, "Modern place has not passed GEOLocate validation: "
                                    + validation.coverage.reason)
        if len(validation.candidate_json) != 1 or not validation.evidence:
            return DerivationResult(LookupStatus.MALFORMED, "GEOLocate result has no unique evidenced candidate")
        country_names = {"PH": "Philippines", "GT": "Guatemala"}
        for item in settled_inputs:
            if item.field_key == FieldKey.COUNTRY and comparison_key(item.value) not in {
                    comparison_key(country), comparison_key(country_names.get(country, ""))}:
                return DerivationResult(LookupStatus.AMBIGUOUS, "Settled country conflicts with reference dataset country")
        parsed_locality = read_locality(verbatim_locality)
        for part in parsed_locality.parts:
            curated = curated_place(country, part.name)
            if curated is not None and not settles(curated):
                return DerivationResult(LookupStatus.AMBIGUOUS, "G36: curator confirmation is still missing")
        candidate = json.loads(validation.candidate_json[0])
        try:
            point = (float(candidate["decimal_latitude"]), float(candidate["decimal_longitude"]))
            if (not all(math.isfinite(value) for value in point) or not -90 <= point[0] <= 90
                    or not -180 <= point[1] <= 180 or not isinstance(candidate.get("authority_id"), str)
                    or not candidate["authority_id"].startswith("geolocate:")
                    or not isinstance(candidate.get("value"), str)
                    or not isinstance(candidate.get("match_name"), str)):
                raise ValueError("Invalid validator point")
            gazetteer_entry, gazetteer = self._dump(country)
            matches = find(gazetteer, candidate["match_name"])
            # The validator confirms the named interpretation. Geographic
            # filtering below uses the qualified polygon, not a guessed radius.
            places = matches.exact
            units = self._boundaries(country)
        except (OSError, ValueError, TypeError, KeyError):
            return DerivationResult(LookupStatus.PROVIDER, "Qualified place data unavailable or invalid")
        levels = self.field_levels.get(country, {})
        options = []
        for item in settled_inputs:
            level = levels.get(item.field_key)
            if level is None:
                continue
            matching_units = []
            for unit in units:
                if (unit.level == level and comparison_key(unit.name) == comparison_key(item.value)
                        and inside(unit.shape, point)):
                    matching_units.append(unit)
            if len(matching_units) != 1:
                return DerivationResult(LookupStatus.AMBIGUOUS,
                                        "Settled administrative input conflicts with, or lacks, a unique qualified footprint")
            options.append((level, matching_units[0], item))
        if not options:
            return DerivationResult(LookupStatus.NO_MATCH,
                                    "No qualified extent for a settled named unit; point alone supplies no uncertainty")
        best_level = max(level for level, _, _ in options)
        best = [(unit, item) for level, unit, item in options if level == best_level]
        if len(best) != 1:
            return DerivationResult(LookupStatus.AMBIGUOUS, "Multiple administrative footprints fit settled inputs")
        footprint, anchor = best[0]
        if (candidate.get("field_key") != str(anchor.field_key)
                or validation.coverage.field_key != anchor.field_key
                or comparison_key(candidate.get("value", "")) != comparison_key(anchor.value)):
            return DerivationResult(LookupStatus.AMBIGUOUS,
                                    "GEOLocate result does not validate the settled footprint anchor field and value")
        open_places = [place for place in places if place.point is not None and inside(footprint.shape, place.point)]
        if not open_places:
            return DerivationResult(LookupStatus.NO_MATCH,
                                    "Modern validator lacks a matching open gazetteer point in the settled footprint")
        circle = extent(footprint)
        # Extent already includes simplification error. The enclosing-circle
        # center is computed from the licensed polygon; no GEOLocate coordinate
        # is promoted to a derived coordinate.
        radius = feature_only(Errors(radial_m=circle.radial_m))
        footprint_entry = dataset(footprint.dataset)
        evidence = (*validation.evidence, _dataset_evidence(gazetteer_entry), _dataset_evidence(footprint_entry))
        source_ids = tuple(dict.fromkeys([*(eid for item in settled_inputs for eid in item.evidence_ids),
                                        *(item.id for item in evidence)]))
        fields = tuple(str(item.field_key) for item in settled_inputs)
        revisions = tuple((str(item.field_key), item.revision) for item in settled_inputs)
        georeference = Georeference(
            latitude=circle.center[0], longitude=circle.center[1], uncertainty_m=radius,
            footprint_dataset=footprint.dataset, footprint_id=footprint.code,
            authority_ids=(candidate["authority_id"], *(f"geonames:{place.record_id}" for place in open_places)),
            input_fields=fields, evidence_ids=source_ids, tool_call_id=tool_call_id,
            simplification_margin_m=footprint.margin_m)
        proposals, unresolved, unresolved_statuses = [], [], []
        available = holding_circle(units, circle.center, radius)
        requested = tuple(dict.fromkeys(FieldKey(key) for key in requested_fields if key not in keys))
        for field_key in requested:
            if field_key in ELEVATION_FIELDS:
                continue
            level = levels.get(field_key)
            unit = available.get(level) if level else None
            if unit is None:
                unresolved.append((str(field_key), "No unique qualified unit contains the whole uncertainty circle"))
                continue
            entry = dataset(unit.dataset)
            item = _dataset_evidence(entry)
            if item not in evidence:
                evidence = (*evidence, item)
            proposals.append(DerivationProposal(
                field_key, unit.name, fields, revisions, tuple(dict.fromkeys((*source_ids, item.id))),
                f"{unit.dataset}:{unit.code}", (footprint.dataset, unit.dataset), tool_call_id))
        elevation_keys = [key for key in requested if key in ELEVATION_FIELDS]
        if elevation_keys:
            if label_has_elevation is not False or parsed_locality.elevations:
                unresolved.extend((str(key), "Label elevation present or absence not established; DEM cannot replace it")
                                  for key in elevation_keys)
            else:
                dem_proposals, dem_evidence, reason, status = self._elevations(georeference, elevation_keys, revisions)
                proposals.extend(dem_proposals)
                evidence = (*evidence, *dem_evidence)
                if reason:
                    unresolved.extend((str(key), reason) for key in elevation_keys)
                    unresolved_statuses.extend((str(key), status) for key in elevation_keys)
        return DerivationResult(LookupStatus.SUCCESS, "Computed conservative uncertainty and editable derived proposals",
                                georeference, tuple(proposals), tuple(evidence), tuple(unresolved), tuple(unresolved_statuses))

    def _elevations(self, georef, fields, revisions):
        if georef.uncertainty_m > 200_000:
            return (), (), "DEM circle exceeds bounded supported extent", LookupStatus.NO_MATCH
        entries, tiles = [], []
        try:
            south_bound, west_bound, north_bound, east_bound = circle_bounds(
                (georef.latitude, georef.longitude), georef.uncertainty_m)
            for entry in MANIFEST:
                if not entry.id.startswith("copernicus-glo30/"):
                    continue
                cell = entry.id.split("/")[1]
                south = int(cell[1:3]) * (-1 if cell[0] == "S" else 1)
                west = int(cell[8:11]) * (-1 if cell[7] == "W" else 1)
                if (south <= north_bound and south + 1 >= south_bound
                        and west <= east_bound and west + 1 >= west_bound):
                    entries.append(entry)
                    tiles.append(read_pinned_tile(entry.id, self._read(entry)))
            heights = pinned_elevation_range(tiles, (georef.latitude, georef.longitude), georef.uncertainty_m)
        except ElevationCoverageError:
            return (), tuple(_dataset_evidence(entry) for entry in entries), (
                "Qualified DEM coverage is incomplete or has no-data inside the uncertainty circle"), LookupStatus.NO_MATCH
        except (OSError, ValueError, KeyError, IndexError):
            return (), (), "Pinned DEM object absent, invalid or digest mismatch", LookupStatus.PROVIDER
        if heights is None:
            return (), (), "Pinned DEM does not cover the complete uncertainty circle", LookupStatus.NO_MATCH
        evidence = tuple(_dataset_evidence(entry) for entry in entries)
        lower, upper = heights
        values = {FieldKey.ELEVATION_FROM_M: Decimal(str(lower)), FieldKey.ELEVATION_TO_M: Decimal(str(upper)),
                  FieldKey.ELEVATION_FROM_FT: Decimal(str(lower)) / Decimal("0.3048"),
                  FieldKey.ELEVATION_TO_FT: Decimal(str(upper)) / Decimal("0.3048")}
        ids = tuple(dict.fromkeys((*georef.evidence_ids, *(item.id for item in evidence))))
        proposals = tuple(DerivationProposal(key, str(values[key]), georef.input_fields, revisions, ids,
                                             "copernicus-glo30:circle-extrema", tuple(entry.id for entry in entries),
                                             georef.tool_call_id) for key in fields)
        return proposals, evidence, None, LookupStatus.SUCCESS


def derivation_source_result(result: DerivationResult, field_key: FieldKey) -> SourceResult:
    """Represent one computed proposal in the existing broker tool envelope.

    The broker still has to retain its durable receipt. A computed georeference
    remains candidate/trace metadata; this function creates no record coordinate
    fields and grants no publication authority.
    """
    proposals = [proposal for proposal in result.proposals if proposal.field_key == field_key]
    reason = dict(result.unresolved).get(str(field_key), result.reason)
    status = result.status
    if not proposals and status == LookupStatus.SUCCESS:
        status = dict(result.unresolved_statuses).get(str(field_key), LookupStatus.NO_MATCH)
    candidates = tuple(_json({**asdict(proposal), "field_key": str(field_key),
                               "georeference": asdict(result.georeference) if result.georeference else None})
                       for proposal in proposals)
    if not candidates and result.georeference is not None:
        candidates = (_json({"field_key": str(field_key), "settlement_allowed": False,
                             "unresolved_reason": reason, "georeference": asdict(result.georeference)}),)
    if status == LookupStatus.POLICY:
        state = SourceCoverageState.NOT_ATTEMPTED
    elif status in {LookupStatus.AUTHENTICATION, LookupStatus.AUTHORIZATION}:
        state = SourceCoverageState.INACCESSIBLE
    elif status in {LookupStatus.PROVIDER, LookupStatus.MALFORMED, LookupStatus.TIMEOUT,
                    LookupStatus.RATE_LIMITED, LookupStatus.EMPTY}:
        state = SourceCoverageState.FAILED
    else:
        state = SourceCoverageState.SEARCHED if result.georeference else SourceCoverageState.NOT_ATTEMPTED
    return SourceResult(status=status, evidence=result.evidence, candidate_json=candidates,
                        coverage=SourceCoverageReceipt(
                            source_id=SPATIAL_SOURCE, field_key=field_key, source_version=VERSION,
                            state=state,
                            qualification_digest=digest(VERSION), receipt_ids=tuple(item.id for item in result.evidence),
                            candidate_count=len(proposals),
                            coverage_limit="Whole-circle qualified containment or complete pinned DEM coverage",
                            reason=reason))


def historical_candidates(places: Sequence[Place], *, collected_on: str) -> tuple[dict, ...]:
    """Shared temporal annotation for TGN/Wikidata/NGA records read by the broker.

    Successors must be actual source references. An undated alias is never
    promoted into a claim that the name was in use on the collecting date.
    """
    interval(collected_on)
    return tuple({**asdict(place), "temporal_status": use_on(place, collected_on).state,
                  "modern_successors": [asdict(ref) for ref in modern_successors(
                      place, {item.record_id: item for item in places if item.source == place.source})],
                  "settlement_allowed": False, "validation_required": "geolocate"} for place in places)
