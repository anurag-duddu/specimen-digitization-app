"""Host-only geography context over accepted checkpoints and captured sources.

These helpers do not fetch, settle fields, or claim that a historical name is
modern. A hierarchy supplies a bounded next GEOLocate query; the ordinary
source broker, evidence validator, and writer still own its acceptance.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from specimen_digitization.application.domain import LookupStatus, ValueState
from specimen_digitization.application.georef_history import interval, use_on
from specimen_digitization.application.georef_places import Place, Ref

from .accepted_output import AcceptedCheckpointProofV1
from .contracts import (
    DependencyPin, EventKind, FieldKey, ResearchScope, SourceQuery, SourceResult,
    SpecialistRequest, SpecialistRole, WorkState, digest,
)
from .sources import result_envelope

CONTEXT_FIELDS = frozenset({FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO, FieldKey.COLLECTORS})
HISTORICAL_SOURCES = frozenset({"tgn", "wikidata", "nga"})
# Same reviewed country code labels used by retrospective-georeferencing-v1.
# An unknown source code is retained as context; it cannot become a guessed name.
COUNTRY_LABELS = {"PH": "Philippines", "GT": "Guatemala"}
VERSION = "captured-geography-context/v1"


@dataclass(frozen=True, slots=True)
class AcceptedCollectingValue:
    field_key: FieldKey
    value: str
    event_id: str
    pin: DependencyPin
    evidence_ids: tuple[str, ...]
    accepted_proof_digest: str


@dataclass(frozen=True, slots=True)
class CollectingContext:
    scope: ResearchScope
    values: tuple[AcceptedCollectingValue, ...] = ()
    proofs: tuple[AcceptedCheckpointProofV1, ...] = ()

    @property
    def collected_on(self) -> str | None:
        """A single accepted date, preserving its written precision.

        A date range is retained in ``values`` but is not collapsed to one day
        for a historical-parent decision.
        """
        dates = {item.value for item in self.values if item.field_key in {
            FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO}}
        return next(iter(dates)) if len(dates) == 1 else None


def accepted_collecting_context(
    request: SpecialistRequest, proofs: Sequence[AcceptedCheckpointProofV1],
) -> CollectingContext:
    """Expose only host-read accepted collecting values pinned by this request.

    The worker must obtain proofs from ``read_accepted_checkpoint_proof`` and
    pin the current checkpoint revisions in ``request.dependencies``. This
    function replays their acceptance validation; it is not a model tool taking
    a dictionary labelled "accepted". Unpinned proofs and stale pins fail closed.
    """
    if request.role != SpecialistRole.GEOGRAPHY:
        raise ValueError("geography_context_wrong_role")
    pins = {pin.field_key: pin for pin in request.dependencies if pin.field_key in CONTEXT_FIELDS}
    if len(pins) != sum(pin.field_key in CONTEXT_FIELDS for pin in request.dependencies):
        raise ValueError("geography_context_duplicate_dependency")
    values: dict[FieldKey, AcceptedCollectingValue] = {}
    for supplied in proofs:
        if not isinstance(supplied, AcceptedCheckpointProofV1):
            raise ValueError("geography_context_acceptance_proof_required")
        # model_copy/model_construct bypass validation, so replay from JSON.
        proof = AcceptedCheckpointProofV1.model_validate(supplied.model_dump(mode="json"))
        original = proof.acceptance.original_request
        if original.scope != request.scope:
            raise ValueError("geography_context_scope_changed")
        for checkpoint in proof.checkpoints:
            key, resolution = checkpoint.field_key, checkpoint.resolution
            if key not in CONTEXT_FIELDS:
                continue
            pin = pins.get(key)
            if pin is None or pin.revision != checkpoint.revision or pin.digest != digest(resolution):
                raise ValueError("geography_context_dependency_changed_or_unpinned")
            if (resolution.work_state != WorkState.RESOLVED
                    or resolution.value.state != ValueState.SUPPORTED):
                raise ValueError("geography_context_dependency_not_resolved")
            events = [item for item in original.events if item.id == resolution.event_id
                and item.kind == EventKind.COLLECTING and item.status == "accepted"]
            if len(events) != 1:
                raise ValueError("geography_context_collecting_event_unproved")
            text = resolution.value.parsed or resolution.value.normalized or resolution.value.literal
            if not text:
                raise ValueError("geography_context_value_missing")
            if key != FieldKey.COLLECTORS:
                interval(text)
            value = AcceptedCollectingValue(key, text, events[0].id, pin,
                resolution.evidence_ids, proof.proof_digest)
            if key in values and values[key] != value:
                raise ValueError("geography_context_competing_checkpoints")
            values[key] = value
    if set(values) != set(pins):
        raise ValueError("geography_context_pinned_proof_missing")
    if len({item.event_id for item in values.values()}) > 1:
        raise ValueError("geography_context_competing_collecting_events")
    return CollectingContext(request.scope, tuple(values[key] for key in sorted(values)), tuple(proofs))


@dataclass(frozen=True, slots=True)
class HierarchyProposal:
    field_key: FieldKey
    value: str
    authority_id: str
    receipt_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    relation: str
    settlement_allowed: bool = False
    validation_required: str = "geolocate"


@dataclass(frozen=True, slots=True)
class GeographyHierarchyResearch:
    scope: ResearchScope
    proposals: tuple[HierarchyProposal, ...]
    next_queries: tuple[SourceQuery, ...]
    unresolved: tuple[tuple[FieldKey, str], ...]
    source_effect_ids: tuple[str, ...]
    dependency_pins: tuple[DependencyPin, ...] = ()
    version: str = VERSION
    place_authority_ids: tuple[str, ...] = ()


def _captured(request: SpecialistRequest, supplied: SourceResult) -> SourceResult:
    result = SourceResult.model_validate(supplied.model_dump(mode="json"))
    receipt, coverage = result.receipt, result.coverage
    ids = tuple(item.id for item in result.evidence)
    if (receipt is None or receipt.scope != request.scope
            or coverage.source_id not in HISTORICAL_SOURCES
            or coverage.field_key not in request.field_keys
            or receipt.source_id != coverage.source_id
            or receipt.field_keys != (coverage.field_key,)
            or receipt.effect_status != "completed" or receipt.outcome != result.status
            or not receipt.capture_locator or not receipt.response_digest
            or not coverage.qualification_digest or not coverage.query_digest
            or receipt.result_json != result_envelope(result)
            or receipt.result_digest != hashlib.sha256(result_envelope(result).encode()).hexdigest()
            or not ids or len(set(ids)) != len(ids)
            or receipt.evidence_ids != ids or coverage.receipt_ids != ids
            or any(item.source_id != coverage.source_id for item in result.evidence)
            or coverage.candidate_count != len(result.candidate_json)):
        raise ValueError("geography_hierarchy_exact_captured_result_required")
    return result


def _reference(data: object) -> Ref:
    if not isinstance(data, dict) or set(data) - {"id", "name", "start", "end"}:
        raise ValueError("geography_hierarchy_invalid_reference")
    if (not isinstance(data.get("id"), str) or not data["id"]
            or any(value is not None and (not isinstance(value, str) or not value)
                for value in (data.get("name"), data.get("start"), data.get("end")))):
        raise ValueError("geography_hierarchy_invalid_reference")
    for endpoint in (data.get("start"), data.get("end")):
        if endpoint is not None:
            interval(endpoint)
    return Ref(**data)


def _place(result: SourceResult, raw: str) -> tuple[Place, str]:
    data = json.loads(raw)
    if (not isinstance(data, dict) or data.get("source") != result.coverage.source_id
            or data.get("field_key") != str(result.coverage.field_key)
            or data.get("authority_role") != "historical_candidate"
            or data.get("settlement_allowed") is not False
            or data.get("validation_required") != "geolocate"
            or not all(isinstance(data.get(key), str) and data[key].strip() == data[key]
                and data[key] for key in ("record_id", "name", "input_literal"))
            or data.get("authority_id") != f"{data['source']}:{data['record_id']}"):
        raise ValueError("geography_hierarchy_historical_candidate_required")
    names = data.get("names", [])
    if not isinstance(names, list) or not all(isinstance(name, str) and name for name in names):
        raise ValueError("geography_hierarchy_invalid_names")
    country = _reference(data["country"]) if data.get("country") is not None else None
    parents = tuple(_reference(item) for item in data.get("parents", []))
    kinds = tuple(_reference(item) for item in data.get("kinds", []))
    place = Place(source=data["source"], record_id=data["record_id"], name=data["name"],
        names=tuple(names), country=country, parents=parents, kinds=kinds,
        valid_from=data.get("valid_from"), valid_to=data.get("valid_to"))
    for endpoint in (place.valid_from, place.valid_to):
        if endpoint is not None:
            interval(endpoint)
    return place, data["input_literal"]


def _link_applies(ref: Ref, context: CollectingContext | None) -> bool:
    if ref.start is None and ref.end is None:
        return True
    written = context.collected_on if context else None
    if written is None:
        return False
    first, last = interval(written)
    return (ref.start is None or interval(ref.start)[1] <= first) and (
        ref.end is None or interval(ref.end)[0] >= last)


def hierarchy_research(
    request: SpecialistRequest, captured_results: Sequence[SourceResult], *,
    context: CollectingContext | None = None,
) -> GeographyHierarchyResearch:
    """Suggest missing country/admin validation from a captured hierarchy.

    Parents do not imply a geographic level: only NGA's explicit first-order
    unit code contract presently qualifies province/state. TGN/Wikidata links
    remain useful context pending captured parent types and a reviewed mapping.
    County and precise-location inference are deliberately absent here.
    Distinct same-name features may supply unanimous country/admin links; their
    identities remain unresolved and every contributing capture is retained.

    This is pure replay over retained results. Interrupted/held calls are never
    retried here; replaying a completed effect performs no external operation.
    """
    if request.role != SpecialistRole.GEOGRAPHY:
        raise ValueError("geography_hierarchy_wrong_role")
    if context is not None:
        if context.scope != request.scope:
            raise ValueError("geography_context_scope_changed")
        if accepted_collecting_context(request, context.proofs) != context:
            raise ValueError("geography_context_accepted_values_changed")
    results = tuple(_captured(request, item) for item in captured_results)
    # Repeated delivery of the same effect is safe; changed effect contents are not.
    unique: dict[str, SourceResult] = {}
    for result in results:
        effect = result.receipt.effect_id
        if effect in unique and unique[effect] != result:
            raise ValueError("geography_hierarchy_effect_changed")
        unique[effect] = result
    results = tuple(unique.values())
    requested = tuple(key for key in request.field_keys if key in {
        FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.COUNTY})
    reason = "no_captured_hierarchy"
    candidates = []
    for result in results:
        if result.status != LookupStatus.SUCCESS:
            reason = f"source_{result.status}"
            continue
        candidates.extend((result, *_place(result, item)) for item in result.candidate_json)
    identities = {(place.source, place.record_id) for _, place, _ in candidates}
    if not identities:
        return GeographyHierarchyResearch(request.scope, (), (),
            tuple((key, reason) for key in requested), tuple(unique))
    result, place, written = candidates[0]
    records: dict[tuple[str, str], Place] = {}
    for _, candidate, _ in candidates:
        identity = (candidate.source, candidate.record_id)
        if identity in records and records[identity] != candidate:
            raise ValueError("geography_hierarchy_conflicting_authority_records")
        records[identity] = candidate
    if len(identities) > 1 and len({(candidate.source, candidate.name.casefold(),
            candidate.country, candidate.parents) for candidate in records.values()}) != 1:
        return GeographyHierarchyResearch(request.scope, (), (),
            tuple((key, "ambiguous_authority_places") for key in requested), tuple(unique))
    ids = tuple(dict.fromkeys(item.id for source, _, _ in candidates for item in source.evidence))
    receipts = tuple(dict.fromkeys(source.receipt.id for source, _, _ in candidates))
    pins = tuple(item.pin for item in context.values) if context else ()
    if any(candidate.valid_from is not None or candidate.valid_to is not None for candidate in records.values()):
        date = context.collected_on if context else None
        if date is None or any(use_on(candidate, date).state not in {"in_use", "undated"}
                for candidate in records.values()):
            return GeographyHierarchyResearch(request.scope, (), (),
                tuple((key, "historical_date_context_unqualified") for key in requested), tuple(unique), pins)
    country = place.country if place.country and _link_applies(place.country, context) else None
    country_name = country.name or COUNTRY_LABELS.get(country.id) if country else None
    # NGA returns country identifiers and adm1 codes. Generic parent names from
    # other sources cannot be promoted to province, state, or county.
    parents = [parent for parent in place.parents if place.source == "nga"
        and re.fullmatch(r"[A-Z]{2}-[A-Z0-9]{1,3}", parent.id) and not parent.id.endswith("-000")
        and country is not None and parent.id.startswith(country.id + "-") and parent.name
        and _link_applies(parent, context)]
    province = parents[0] if len(parents) == 1 else None
    relation = "canonical_name" if written.casefold() == place.name.casefold() else (
        "captured_alternate_name" if written.casefold() in {name.casefold() for name in place.names}
        else "spelling_or_name_hypothesis")
    proposals, queries, unresolved = [], [], []
    for key in requested:
        ref, value = (country, country_name) if key == FieldKey.COUNTRY else (
            (province, province.name if province else None) if key == FieldKey.PROVINCE_STATE else (None, None))
        if ref is None or value is None or not country_name:
            unresolved.append((key, "county_mapping_unqualified" if key == FieldKey.COUNTY
                else "country_name_unqualified" if not country_name else "parent_level_unqualified"))
            continue
        proposals.append(HierarchyProposal(key, value, f"{place.source}:{ref.id}", receipts, ids, relation))
        payload = {"country": country_name, "locality": place.name, "place": place.name, "value": value}
        if province:
            payload["state"] = province.name
        queries.append(SourceQuery(source_id="geolocate", field_key=key,
            query_text=json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)))
    return GeographyHierarchyResearch(request.scope, tuple(proposals), tuple(queries),
        tuple(unresolved), tuple(unique), pins,
        place_authority_ids=tuple(sorted(f"{source}:{identifier}" for source, identifier in identities)))
