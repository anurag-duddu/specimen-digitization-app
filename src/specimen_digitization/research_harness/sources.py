"""Owner-selected source registry and typed, read-only, effect-scoped adapters.

Source selection is independent of endpoint qualification. Inaccessible/schema-only
sources cannot be relabelled exhausted; Museum occurrence reads have only the
2026-09-29 exact-metadata purpose, never legacy D4 point corroboration.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Protocol
from urllib.parse import urlencode, urlsplit

import httpx
from pydantic import Field

from specimen_digitization.application.domain import LookupStatus, now
from specimen_digitization.application.lookup import (
    CLAUSES, COL_XR, MONTHS, _shape_ok, cleared_synonym, row_one, scientific_name,
)

from .contracts import (
    ROLE_FIELDS, Digest, EvidenceItem, FieldKey, FrozenRecord, SourceCoverageReceipt,
    SourceCoverageState, SourceQuery, SourceResult, SpecialistRequest,
    SpecialistRole, ToolReceipt, digest,
)

MUSEUM_DATASET = "7931dcab-94f1-46ce-8092-56e4335423de"
PUBLIC_METADATA_POLICY = "owner-2026-09-29-exact-museum-metadata-v1"
_METADATA_FIELDS = (
    FieldKey.FMNH_INS_NUMBER, FieldKey.COLLECTION_CODE, FieldKey.COLLECTORS,
    FieldKey.DATE_IDENTIFIED, FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO,
    FieldKey.TAXON, FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.PRECISE_LOCATION,
)
_DWC = {
    FieldKey.FMNH_INS_NUMBER: "catalogNumber", FieldKey.COLLECTION_CODE: "collectionCode",
    FieldKey.COLLECTORS: "recordedBy", FieldKey.DATE_IDENTIFIED: "dateIdentified",
    FieldKey.DATE_VISITED_FROM: "eventDate", FieldKey.DATE_VISITED_TO: "eventDate",
    FieldKey.TAXON: "scientificName", FieldKey.COUNTRY: "country",
    FieldKey.PROVINCE_STATE: "stateProvince", FieldKey.PRECISE_LOCATION: "locality",
}


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


SETTLEMENT_UTILITY_VERSION = "deterministic-settlement-v1"


class UtilityInputError(ValueError):
    """A model supplied an argument outside the immutable utility inputs."""


def _utility_field_key(value):
    try:
        return FieldKey(value)
    except (ValueError, TypeError):
        raise UtilityInputError("Utility field is outside the reviewed roster") from None


def local_settlement_result(request: SpecialistRequest, tool_id: str, arguments: dict) -> SourceResult:
    """Return the validator's exact event/assembly settlement, with no model authority.

    The same pure adapter is replayed at publication. It accepts only immutable
    identifiers already in this role's request and never raw model-supplied text,
    source authority, evidence relation or revision.
    """
    from .evidence import settle_elevation, temporal_resolutions

    if tool_id == "settle_collection":
        from .collection import COLLECTION_FIELDS, collection_resolution
        if request.role != SpecialistRole.COLLECTION or set(arguments) != {"field_key"}:
            raise UtilityInputError("Collection settlement requires only its owned field key")
        field_key = _utility_field_key(arguments["field_key"])
        if field_key not in request.field_keys or field_key not in COLLECTION_FIELDS:
            raise UtilityInputError("Collection settlement exceeds scoped request or defined fields")
        resolutions = (collection_resolution(request, field_key),)
    elif tool_id == "settle_temporal":
        if request.role != SpecialistRole.TEMPORAL or set(arguments) != {"field_key", "event_id"}:
            raise UtilityInputError("Temporal settlement requires its exact owned event")
        field_key = _utility_field_key(arguments["field_key"])
        event_id = arguments["event_id"]
        if field_key not in request.field_keys or not isinstance(event_id, str):
            raise UtilityInputError("Temporal settlement exceeds scoped request")
        source_pin = next((pin for pin in request.dependencies
                           if pin.field_key == FieldKey.DATE_VISITED_FROM), None)
        source_revision = (source_pin.revision if source_pin is not None
                           else request.field_revisions.get(FieldKey.DATE_VISITED_FROM, 0))
        resolutions = temporal_resolutions(request, event_id=event_id, source_revision=source_revision)
        selected = next((item for item in resolutions if item.field_key == field_key), None)
        if selected is None:
            raise UtilityInputError("Temporal event does not establish the requested field")
        if (field_key == FieldKey.DATE_VISITED_TO and selected.value_layer == "derived"
                and FieldKey.DATE_VISITED_FROM not in request.field_keys and source_pin is None):
            raise UtilityInputError("Temporal To repair requires exact native From dependency")
        assembly_ids = tuple(item.id for item in request.assemblies if item.event_id == event_id)
        context_fields = set(request.field_keys)
        if field_key == FieldKey.DATE_VISITED_TO:
            context_fields.add(FieldKey.DATE_VISITED_FROM)
        if not assembly_ids or any(item.field_key not in context_fields
                                   for item in request.assemblies if item.event_id == event_id):
            raise UtilityInputError("Temporal event has no complete scoped assembly")
    elif tool_id == "settle_elevation":
        if request.role != SpecialistRole.MEASUREMENT or set(arguments) != {
            "field_key", "event_id", "assembly_ids"}:
            raise UtilityInputError("Elevation settlement requires exact owned assemblies")
        field_key = _utility_field_key(arguments["field_key"])
        event_id, ids = arguments["event_id"], arguments["assembly_ids"]
        if (field_key not in request.field_keys or not isinstance(event_id, str)
            or not isinstance(ids, list) or not ids or any(not isinstance(item, str) for item in ids)):
            raise UtilityInputError("Elevation settlement exceeds scoped request")
        # Evidence from an omitted native source remains available for a
        # derived-only retry; output scope and native checkpoint availability
        # are separate checks. Include every elevation assertion of the event.
        assemblies = tuple(item for item in request.assemblies
            if item.event_id == event_id and str(item.field_key).startswith("elevation_"))
        requested = tuple(item for item in assemblies if item.field_key in request.field_keys)
        if (not assemblies or tuple(ids) != tuple(item.id for item in assemblies)
            or requested and requested[0].field_key != field_key):
            raise UtilityInputError("Elevation settlement needs every assembly in immutable request order")
        # G41 always derives from a written From quantity of the matching unit,
        # even when the organiser's original proposal named a To slot.
        from .evidence import parse_measurement
        first = parse_measurement(assemblies[0].interpreted_text)
        source_key = FieldKey(f"elevation_from_{first.from_unit}")
        source_revision = request.field_revisions.get(source_key, 0)
        settled = settle_elevation(request, assembly_ids=ids, source_revision=source_revision)
        from .measurement import pinned_elevation_resolutions
        resolutions = pinned_elevation_resolutions(request, settled)
    elif tool_id == "settle_collectors":
        if request.role != SpecialistRole.PARTIES or set(arguments) != {"field_key", "event_id"}:
            raise UtilityInputError("Collector settlement requires its exact owned event")
        field_key = _utility_field_key(arguments["field_key"])
        event_id = arguments["event_id"]
        if field_key != FieldKey.COLLECTORS or field_key not in request.field_keys or not isinstance(event_id, str):
            raise UtilityInputError("Collector settlement exceeds scoped request")
        assemblies = [item for item in request.assemblies if item.event_id == event_id
            and item.field_key == FieldKey.COLLECTORS]
        if not assemblies:
            raise UtilityInputError("Collector event has no available assembly")
        from .people import collector_resolution
        resolutions = (collector_resolution(request, assembly_id=assemblies[0].id),)
    else:
        raise ValueError("Unknown settlement utility")
    return SourceResult(status=LookupStatus.SUCCESS,
        coverage=SourceCoverageReceipt(source_id=tool_id, field_key=field_key,
            state=SourceCoverageState.SEARCHED, source_version=SETTLEMENT_UTILITY_VERSION,
            coverage_limit="Exact deterministic assembly settlement; no external source authority",
            reason="exact_settlement"),
        candidate_json=(canonical_json({"resolutions": [item.model_dump(mode="json") for item in resolutions]}),))


def _source_json(raw: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Source JSON duplicate key")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("Source JSON nonfinite number")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


class SourcePolicy(FrozenRecord):
    id: str
    version: str
    roles: tuple[SpecialistRole, ...]
    fields: tuple[FieldKey, ...]
    allowed_hosts: tuple[str, ...]
    allowed_path_patterns: tuple[str, ...]
    source_type: str
    license: str
    terms_locator: str
    retention: str
    publisher_id: str
    authority_role: str
    qualification_state: SourceCoverageState = SourceCoverageState.UNQUALIFIED
    qualification_receipt: str | None = None
    schema_digest: Digest | None = None
    source_release: str | None = None
    credentials_required: bool = False
    paid: bool = False
    max_response_bytes: int = Field(default=150_000, gt=0, le=2_000_000)
    timeout_seconds: float = Field(default=15, gt=0, le=30)
    result_limit: int = Field(default=3, strict=True, ge=1, le=5)
    purpose_policy: str = "insects-research-v1"

    @property
    def ready(self) -> bool:
        return (self.qualification_state == SourceCoverageState.SEARCHED
                and self.qualification_receipt is not None and self.schema_digest is not None
                and self.source_release is not None and not self.paid and not self.credentials_required)


class SourceRegistry:
    def __init__(self, policies: Sequence[SourcePolicy]):
        if len({item.id for item in policies}) != len(policies):
            raise ValueError("Duplicate source registry identity")
        self._policies = tuple(policies)
        self.digest = digest([item.model_dump(mode="json") for item in policies])

    @property
    def policies(self) -> tuple[SourcePolicy, ...]:
        return self._policies

    def get(self, source_id: str) -> SourcePolicy:
        for policy in self._policies:
            if policy.id == source_id:
                return policy
        raise ValueError("Source is outside owner allowlist")

    def allowed(self, request: SpecialistRequest, *, qualified_only: bool = True) -> tuple[SourcePolicy, ...]:
        return tuple(policy for policy in self._policies if request.role in policy.roles
                     and set(request.field_keys) & set(policy.fields)
                     and policy.source_type not in {"computed_local", "local_dataset"}
                     and (not qualified_only or policy.ready))


def insects_registry(*, qualification_overrides: Mapping[str, dict] | None = None) -> SourceRegistry:
    """Owner-selected sources, including worker-only computed adapters."""
    taxonomy = (SpecialistRole.TAXONOMY,)
    geography = (SpecialistRole.GEOGRAPHY,)
    geo_fields = (FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.COUNTY,
                  FieldKey.CITY, FieldKey.PRECISE_LOCATION)
    museum_roles = tuple(SpecialistRole)
    specs = (
        ("global_names_verifier", taxonomy, (FieldKey.TAXON,), ("verifier.globalnames.org",),
         (r"/api/v1/verifications/[^/]+",), "public_api", "underlying-source-specific", "https://verifier.globalnames.org/api", "retain licensed typed name evidence", "gnv-underlying-sources", "supports"),
        ("catalogue_of_life", taxonomy, (FieldKey.TAXON,), ("api.checklistbank.org",),
         (r"/dataset/[0-9A-Z]+/nameusage/search",), "public_api", "CC BY 4.0 release-specific", "https://www.catalogueoflife.org/tools/api", "retain cited release evidence", "catalogue-of-life", "supports"),
        ("gbif", taxonomy, (FieldKey.TAXON,), ("api.gbif.org",),
         (r"/v2/species/match", r"/v2/species/match/metadata"), "public_api", "CC BY 4.0 COL XR", "https://www.gbif.org/citation-guidelines", "retain exact typed name evidence and response digest", "gbif-col-xr", "decides"),
        ("bugguide", taxonomy, (FieldKey.TAXON,), ("www.bugguide.net", "bugguide.net"),
         (r"/node/view/[0-9]+",), "browser", "individual-content-specific", "https://www.bugguide.net/node/view/6/bgimage", "terms/access pending; no image reuse", "bugguide-community", "supports"),
        ("mapcarta", geography, geo_fields, ("mapcarta.com",),
         (r"/(?:[0-9]+|[A-Z][A-Za-z0-9_]*)",), "browser", "CC BY-SA/ODbL with exceptions", "https://mapcarta.com/About_Mapcarta", "upstream attribution; no map/photo screenshot storage", "mapcarta-upstream", "supports"),
        ("geolocate", geography, geo_fields, ("geo-locate.org", "www.geo-locate.org"),
         (r"/webservices/geolocatesvcv2/glcwrap\.aspx",), "public_api", "keyless public web service; no published terms", "https://geo-locate.org/developers/default.html", "full response retained as evidence (coordinator engineering call 2026-10-03 under the owner standing technical approval; revisit if GEOLocate publishes terms)", "geolocate", "candidate"),
        ("georeference_history", geography, geo_fields, (), (), "local_dataset",
         "pinned dataset-specific attribution", "docs/execution/golive/GEOREFERENCE_ADAPTER.md",
         "retain exact manifest digest, source record and computed search result", "pinned-historical-gazetteer", "candidate"),
        ("georeference_spatial", (SpecialistRole.GEOGRAPHY, SpecialistRole.MEASUREMENT),
         geo_fields + (FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M,
                       FieldKey.ELEVATION_FROM_FT, FieldKey.ELEVATION_TO_FT), (), (), "computed_local",
         "derived from pinned open datasets", "docs/execution/golive/GEOREFERENCE_ADAPTER.md",
         "retain dataset IDs, revisions, calculation and tool receipt", "retrospective-georeferencing", "derived_candidate"),
        ("tgn", geography, geo_fields, ("services.getty.edu", "vocab.getty.edu"),
         (r"/vocab/reconcile/", r"/sparql\.json"), "public_api", "ODC-By 1.0",
         "https://www.getty.edu/research/tools/vocabularies/obtain/", "retain all three source exchanges with attribution",
         "getty-tgn", "candidate"),
        ("wikidata", geography, geo_fields, ("www.wikidata.org",),
         (r"/w/api\.php",), "public_api", "CC0",
         "https://www.wikidata.org/wiki/Wikidata:Copyright", "retain all returned entity exchanges",
         "wikidata", "candidate"),
        ("nga", geography, geo_fields, ("geonames.nga.mil",),
         (r"/geon-ags/rest/services/RESEARCH/GIS_OUTPUT/MapServer/[01]/query",), "public_api",
         "NGA GNS public general use; credit NGA; third-party coordinates separately sourced", "https://geonames.nga.mil/gns/html/gns_services.html",
         "retain all returned feature and unit exchanges", "nga-gns", "candidate"),
        ("field_museum_ipt", museum_roles, _METADATA_FIELDS, ("fmipt.fieldmuseum.org", "api.gbif.org"),
         (r"/ipt/eml.do", r"/ipt/resource.do", r"/v1/occurrence/search", r"/v1/occurrence/[0-9]+/verbatim"), "public_publisher_metadata", "CC0 dataset; images excluded", "https://fmipt.fieldmuseum.org/ipt/eml.do?r=fmnh_insects&v=12.64", "bounded exact publisher metadata; no archive/media", "field-museum-insects", "publisher_assertion"),
        ("field_museum_emudata", museum_roles, _METADATA_FIELDS + (FieldKey.IDENTIFIED_BY_IRN,), ("emudata.fieldmuseum.org",),
         (r"/",), "browser_pending", "unqualified", "https://emudata.fieldmuseum.org/", "access/schema pending; no guessed REST/private credentials", "field-museum-emu", "unknown"),
    )
    overrides = qualification_overrides or {}
    if set(overrides) - {item[0] for item in specs}:
        raise ValueError("Qualification cannot introduce a new source")
    policies = []
    for source_id, roles, fields, hosts, paths, kind, license, terms, retention, publisher, authority in specs:
        policy = SourcePolicy(id=source_id, version="registry-v1-2026-09-29", roles=roles,
                              fields=fields, allowed_hosts=hosts, allowed_path_patterns=paths,
                              source_type=kind, license=license, terms_locator=terms,
                              retention=retention, publisher_id=publisher, authority_role=authority,
                              max_response_bytes=2_000_000 if source_id in {"tgn", "wikidata", "nga"} else 150_000,
                              purpose_policy=PUBLIC_METADATA_POLICY if source_id == "field_museum_ipt" else "insects-research-v1")
        if source_id in overrides:
            # Qualification changes readiness/version only; never grants host/role/field.
            admitted = {"qualification_state", "qualification_receipt", "schema_digest", "source_release"}
            if set(overrides[source_id]) - admitted:
                raise ValueError("Qualification cannot expand capabilities or price policy")
            policy = SourcePolicy.model_validate({**policy.model_dump(), **overrides[source_id]})
        policies.append(policy)
    return SourceRegistry(policies)


# GEOLocate validates the geography historian's interpretation (owner G-geo-1..3,
# 2026-10-03). The glcwrap wrapper answers JSON; outside the USA it ignores State and
# reports no uncertainty, and the uncertainty radius is computed in-house (D13).
GEOLOCATE_ENDPOINT = "https://geo-locate.org/webservices/geolocatesvcv2/glcwrap.aspx"
GEOLOCATE_RELEASE = "geolocatesvcv2-glcwrap-json"
GEOLOCATE_SCHEMA = (
    "engineVersion:string", "numResults:integer", "resultSet.type:FeatureCollection",
    "resultSet.crs:EPSG:4326", "features[].geometry:Point[longitude,latitude]",
    "features[].properties.parsePattern:string", "features[].properties.precision:string",
    "features[].properties.score:integer", "features[].properties.debug:string(:Adm=)",
)
GEOLOCATE_QUALIFICATION = {
    "qualification_state": SourceCoverageState.SEARCHED.value,
    "qualification_receipt": "owner G-geo-1..3 2026-10-03; glcwrap.aspx fmt=json probed 2026-10-03",
    "schema_digest": digest(GEOLOCATE_SCHEMA),
    "source_release": GEOLOCATE_RELEASE,
}
GEOLOCATE_AGREEMENT_KM = 10.0
SOURCE_REQUEST_INTERVAL_SECONDS = {"geolocate": 3.0}
_GEOLOCATE_TEXT = ("country", "state", "county", "locality", "place", "value")
_GEOLOCATE_REQUIRED = ("country", "locality", "place", "value")
_GEOLOCATE_BOUNDS = {"latitude": (-90.0, 90.0), "longitude": (-180.0, 180.0), "radius_km": (1.0, 50.0)}
_USA = {("usa",), ("us",), ("united", "states"), ("united", "states", "of", "america")}


@dataclass(frozen=True, slots=True)
class GeolocateInterpretation:
    """Place text, with an optional placement reserved for the trusted derivation worker.

    GEOLocate receives only the text. A placement is a local match filter, so
    accepting model-created coordinates would conceal otherwise valid namesakes.
    """

    country: str
    state: str
    county: str
    locality: str
    place: str
    value: str
    latitude: float | None
    longitude: float | None
    radius_km: float | None


@dataclass(frozen=True, slots=True)
class _GeolocateMatch:
    latitude: float
    longitude: float
    name: str
    admin: str
    precision: str
    score: int
    distance_km: float | None


def geolocate_interpretation(query_text: str, field_key: FieldKey | None = None) -> GeolocateInterpretation:
    """Parse the query_text JSON; the ValueError message tells the agent what to correct.

    Model queries omit placement. The trusted derivation worker may supply all
    three placement numbers after proving its captured seed and boundary footprint.
    Parsing numbers does not authorize their use; the broker checks that boundary
    before opening an effect.

    With a field key, also refuse a value GEOLocate cannot confirm for that field: country and
    city must be the queried country and place, and a county exists only inside the USA, where
    the gazetteer's admin unit is the county (outside it, the first-level unit).
    """
    try:
        value = _source_json(query_text.encode())
    except ValueError:
        value = None
    if not isinstance(value, dict):
        raise ValueError("GEOLocate query_text must be one JSON object")
    unknown = sorted(set(value) - set(_GEOLOCATE_TEXT) - set(_GEOLOCATE_BOUNDS))
    missing = [key for key in _GEOLOCATE_REQUIRED if key not in value]
    if unknown or missing:
        shown = [key if re.fullmatch(r"[A-Za-z_]{1,32}", key) else "?" for key in unknown]
        raise ValueError("GEOLocate query_text keys: " + "; ".join(
            part for part in ("unknown " + ", ".join(shown) if unknown else "",
                              "missing " + ", ".join(missing) if missing else "") if part))
    for key in _GEOLOCATE_TEXT:
        item = value.get(key, "")
        if (type(item) is not str or item != item.strip() or len(item) > 200
                or any(ord(character) < 32 for character in item) or (key in _GEOLOCATE_REQUIRED and not item)):
            raise ValueError(f"GEOLocate {key} must be trimmed text of at most 200 characters")
    placement_keys = set(value) & set(_GEOLOCATE_BOUNDS)
    if placement_keys and placement_keys != set(_GEOLOCATE_BOUNDS):
        raise ValueError("GEOLocate placement requires latitude, longitude and radius_km together")
    for key, (low, high) in _GEOLOCATE_BOUNDS.items():
        if key not in value:
            continue
        item = value[key]
        if not _finite_number(item) or not low <= item <= high:
            raise ValueError(f"GEOLocate {key} must be a number from {low:g} to {high:g}")
    place = GeolocateInterpretation(
        country=value["country"], state=value.get("state", ""), county=value.get("county", ""),
        locality=value["locality"], place=value["place"], value=value["value"],
        latitude=float(value["latitude"]) if placement_keys else None,
        longitude=float(value["longitude"]) if placement_keys else None,
        radius_km=float(value["radius_km"]) if placement_keys else None)
    claimed = _fold_words(place.value)
    usa = _fold_words(place.country) in _USA
    if field_key == FieldKey.COUNTRY and claimed != _fold_words(place.country):
        raise ValueError("GEOLocate country value must be the queried country")
    if field_key == FieldKey.CITY and claimed != _fold_words(place.place):
        raise ValueError("GEOLocate city value must be the queried place")
    if field_key == FieldKey.COUNTY and not usa:
        raise ValueError("GEOLocate confirms a county only inside the USA")
    if field_key == FieldKey.PROVINCE_STATE and usa and claimed != _fold_words(place.state):
        raise ValueError("GEOLocate state value inside the USA must be the queried state")
    return place


def _finite_number(item) -> bool:
    # A JSON integer of any length compares exactly; converting a huge one to float overflows.
    return type(item) is int or (type(item) is float and math.isfinite(item))


def geolocate_place_text_defect(request: SpecialistRequest, place: GeolocateInterpretation) -> str | None:
    """PLAN 4.8: only place text leaves the harness, so the request names what GEOLocate may see.

    The locality is built from the historian's own place and unit names, or is the exact text of
    an accepted precise_location assembly; no request has a reusable per-field place filter, and a
    reading line can hold a collector or a date beside the locality. Every sent value is refused
    when it holds a digit, a month word, a party marker, or a word of any label clause that holds
    a marker.
    """
    markers = {word for clause in CLAUSES for word in _fold_words(clause)}
    marked = {word for item in request.assemblies if item.field_key == FieldKey.COLLECTORS
              for word in _fold_words(item.interpreted_text)}
    for fragment in request.fragments:
        for clause in re.split(r"[,;]", fragment.literal):
            words = set(_fold_words(clause))
            if words & markers:
                marked |= words
    for key in ("country", "state", "county", "locality", "place"):
        words = set(_fold_words(getattr(place, key)))
        if any(character.isdigit() for word in words for character in word):
            return f"GEOLocate {key} must be place text: no digits, dates or elevations"
        if words & MONTHS:
            return f"GEOLocate {key} must be place text: no month words"
        if words & (markers | marked):
            return f"GEOLocate {key} must be place text: no collector or determiner text"
    named = set(_fold_words(" ".join((place.place, place.county, place.state, place.country))))
    assembled = {item.interpreted_text for item in request.assemblies if item.field_key == FieldKey.PRECISE_LOCATION}
    if not set(_fold_words(place.locality)) <= named and place.locality not in assembled:
        return ("GEOLocate locality must use only the words of place and the named units, "
                "or the exact text of an accepted precise_location assembly")
    return None


def _captured_geography_results(request: SpecialistRequest,
                               trusted_results: Sequence[SourceResult]) -> tuple[SourceResult, ...]:
    """Same-scope semantic closures only; model-provided candidate text is not context."""
    retained = []
    for supplied in trusted_results:
        try:
            result = SourceResult.model_validate(supplied.model_dump(mode="json"))
            receipt, coverage = result.receipt, result.coverage
            ids = tuple(item.id for item in result.evidence)
            raw = result_envelope(result)
            if (receipt is None or receipt.scope != request.scope
                or coverage.source_id not in {"geolocate", "tgn", "wikidata", "nga"}
                or coverage.field_key not in ROLE_FIELDS[SpecialistRole.GEOGRAPHY]
                or receipt.source_id != coverage.source_id or receipt.field_keys != (coverage.field_key,)
                or receipt.effect_status != "completed" or receipt.outcome != result.status
                or not receipt.capture_locator or not receipt.response_digest
                or not coverage.qualification_digest or not coverage.query_digest
                or receipt.result_json != raw or receipt.result_digest != hashlib.sha256(raw.encode()).hexdigest()
                or not ids or len(set(ids)) != len(ids) or receipt.evidence_ids != ids
                or coverage.receipt_ids != ids
                or any(item.source_id != coverage.source_id for item in result.evidence)):
                continue
            retained.append(result)
        except (ValueError, TypeError, AttributeError):
            continue
    return tuple(retained)


def geolocate_grounding_defect(request: SpecialistRequest, query: SourceQuery,
        place: GeolocateInterpretation, trusted_results: Sequence[SourceResult], *,
        collecting_context=None) -> str | None:
    """Bind proposed names to immutable readings or verified captured hierarchy.

    A historical place's name/aliases authorize a place-name hypothesis, not an
    invented geographic level. Missing country/admin names need the exact next
    query computed by the reviewed hierarchy helper. Previously validated
    same-field GEOLocate values can then serve as context for sibling fields.
    """
    geo_fields = {FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.COUNTY,
                  FieldKey.CITY, FieldKey.PRECISE_LOCATION}
    texts = [item.literal for item in request.fragments if item.scope == request.scope and not item.unreadable]
    texts.extend(item.interpreted_text for item in request.assemblies
                 if item.scope == request.scope and item.field_key in geo_fields)

    def printed(name):
        words = _fold_words(name)
        return bool(words) and any(any(tuple(line[index:index + len(words)]) == words
            for index in range(len(line) - len(words) + 1)) for line in map(_fold_words, texts))

    retained = _captured_geography_results(request, trusted_results)
    captured_names, validated = set(), {key: set() for key in geo_fields}
    for result in retained:
        if result.status not in {LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS}:
            continue
        for raw in result.candidate_json:
            candidate = json.loads(raw)
            for key in ("name", "match_name"):
                if isinstance(candidate.get(key), str):
                    captured_names.add(_fold_words(candidate[key]))
            for alias in candidate.get("names", ()):
                if isinstance(alias, str):
                    captured_names.add(_fold_words(alias))
            if (result.coverage.source_id == "geolocate" and result.status == LookupStatus.SUCCESS
                and candidate.get("field_key") == str(result.coverage.field_key)
                and isinstance(candidate.get("value"), str)):
                validated[result.coverage.field_key].add(_fold_words(candidate["value"]))
    missing = []
    for key, field in (("country", FieldKey.COUNTRY), ("state", FieldKey.PROVINCE_STATE),
                       ("county", FieldKey.COUNTY)):
        value = getattr(place, key)
        if value and not printed(value) and _fold_words(value) not in validated[field]:
            missing.append(key)
    if not printed(place.place) and _fold_words(place.place) not in captured_names:
        missing.append("place")
    if (query.field_key not in {FieldKey.CITY, FieldKey.COUNTRY}
        and not printed(place.value) and _fold_words(place.value) not in validated[query.field_key]):
        missing.append("value")
    if not missing:
        return None
    # Import only at invocation: geography_context itself uses source envelopes.
    from .geography_context import hierarchy_research

    history = tuple(result for result in retained if result.coverage.source_id in {"tgn", "wikidata", "nga"})
    try:
        research = hierarchy_research(request, history, context=collecting_context)
        if any(item.field_key == query.field_key
               and geolocate_interpretation(item.query_text, item.field_key) == place
               for item in research.next_queries):
            return None
    except (ValueError, TypeError, KeyError):
        pass
    return ("GEOLocate " + ", ".join(missing)
            + " absent from immutable place reading or verified captured hierarchy; research the printed place first")


def historical_place_name_defect(request: SpecialistRequest, name: str,
                                 trusted_results: Sequence[SourceResult] = ()) -> str | None:
    """Admit one place name from reading or retained source, never a label clause.

    The same conservative marker and date exclusions used for GEOLocate apply
    before a tier-one GET. Modernized names may enter only from a result this
    broker already captured in the current request scope.
    """
    if type(name) is not str or name != name.strip() or not name or len(name) > 200:
        return "Historical query needs one trimmed place name"
    words = set(_fold_words(name))
    markers = {word for clause in CLAUSES for word in _fold_words(clause)}
    marked = {word for item in request.assemblies if item.field_key == FieldKey.COLLECTORS
              for word in _fold_words(item.interpreted_text)}
    safe_texts = []
    for item in request.assemblies:
        if item.field_key in {FieldKey.COUNTRY, FieldKey.PROVINCE_STATE, FieldKey.COUNTY,
                              FieldKey.CITY, FieldKey.PRECISE_LOCATION}:
            safe_texts.append(item.interpreted_text)
    for fragment in request.fragments:
        for clause in re.split(r"[,;]", fragment.literal):
            clause_words = set(_fold_words(clause))
            if clause_words & markers or clause_words & MONTHS or any(
                character.isdigit() for word in clause_words for character in word):
                marked |= clause_words
            else:
                safe_texts.append(clause)
    for result in trusted_results:
        if result.receipt is None or result.receipt.scope != request.scope:
            continue
        for item in result.candidate_json:
            candidate = json.loads(item)
            for key in ("name", "value", "match_name"):
                if type(candidate.get(key)) is str:
                    safe_texts.append(candidate[key])
            for alias in candidate.get("names", ()):
                if type(alias) is str:
                    safe_texts.append(alias)
    if (not words or any(character.isdigit() for word in words for character in word)
        or words & MONTHS or words & (markers | marked)):
        return "Historical name must contain place text only"
    if not any(words <= set(_fold_words(text)) for text in safe_texts):
        return "Historical name is absent from trusted place reading or prior captured result"
    return None


def _fold_words(text: str) -> tuple[str, ...]:
    plain = "".join(character for character in unicodedata.normalize("NFKD", text)
                    if not unicodedata.combining(character)).casefold()
    return tuple("mount" if word == "mt" else word for word in re.sub(r"[\W_]+", " ", plain).split())


def _distance_km(latitude: float, longitude: float, other_latitude: float, other_longitude: float) -> float:
    phi, other_phi = math.radians(latitude), math.radians(other_latitude)
    half_chord = (math.sin((other_phi - phi) / 2) ** 2 + math.cos(phi) * math.cos(other_phi)
                  * math.sin(math.radians(other_longitude - longitude) / 2) ** 2)
    return 2 * 6371.0088 * math.asin(min(1.0, math.sqrt(half_chord)))


def _geolocate_matches(payload, place: GeolocateInterpretation) -> tuple[str, int, list[_GeolocateMatch]]:
    result_set = payload.get("resultSet") if isinstance(payload, dict) else None
    features = result_set.get("features") if isinstance(result_set, dict) else None
    count = payload.get("numResults") if isinstance(payload, dict) else None
    engine = payload.get("engineVersion") if isinstance(payload, dict) else None
    if (type(count) is not int or count < 0 or not isinstance(features, list) or len(features) != count
            or result_set.get("type") != "FeatureCollection" or type(engine) is not str or not engine
            or (features and result_set.get("crs") != {"type": "EPSG", "properties": {"code": 4326}})):
        raise ValueError("GEOLocate glcwrap schema mismatch")
    matches = []
    for feature in features:
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        properties = feature.get("properties") if isinstance(feature, dict) else None
        point = geometry.get("coordinates") if isinstance(geometry, dict) else None
        if (not isinstance(properties, dict) or not isinstance(geometry, dict) or geometry.get("type") != "Point"
                or not isinstance(point, list) or len(point) != 2
                or any(not _finite_number(item) for item in point)
                or type(properties.get("parsePattern")) is not str or type(properties.get("precision")) is not str
                or type(properties.get("score")) is not int or type(properties.get("debug")) is not str):
            raise ValueError("GEOLocate feature schema mismatch")
        if not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
            raise ValueError("GEOLocate coordinates out of range")
        longitude, latitude = (float(item) for item in point)
        admin = re.search(r"(?:^|\|):Adm=([^|]*)", properties["debug"])
        matches.append(_GeolocateMatch(
            latitude=latitude, longitude=longitude, name=properties["parsePattern"],
            admin=admin.group(1) if admin else "", precision=properties["precision"],
            score=properties["score"],
            distance_km=(_distance_km(place.latitude, place.longitude, latitude, longitude)
                         if place.latitude is not None else None)))
    return engine, count, matches


def _geolocate_agrees(field_key: FieldKey, place: GeolocateInterpretation, match: _GeolocateMatch) -> bool:
    """The match must be the named place and agree with the declared place context."""
    if (_fold_words(match.name) != _fold_words(place.place)
        or (place.radius_km is not None and match.distance_km > place.radius_km)):
        return False
    # The admin unit is the county inside the USA and the first-level unit outside it; inside
    # the USA GEOLocate confines the search to the queried State instead.
    usa = _fold_words(place.country) in _USA
    if field_key == FieldKey.COUNTY or (field_key == FieldKey.PROVINCE_STATE and not usa):
        return bool(match.admin) and _fold_words(match.admin) == _fold_words(place.value)
    # Outside the USA State is ignored by the provider. Without a proven
    # placement, enforce any named first-level context on its returned admin
    # unit ourselves rather than selecting a namesake in another province.
    if place.latitude is None:
        unit = place.county if usa else place.state
        if unit:
            return bool(match.admin) and _fold_words(match.admin) == _fold_words(unit)
    return True


GEOLOCATE_ID_SCHEME = "geolocate-match-v1"


def geolocate_authority_id(match: _GeolocateMatch) -> str:
    """The identifier of one GEOLocate match: ``geolocate:`` and 16 hex digits, no coordinates.

    A candidate's authority_id is stored on field_candidate rows and shown in the public record
    on country, state, county and city alike. The matched point is candidate metadata in the tool
    result and the trace, not a record field (G39), so the identifier is a digest of the match
    instead of the point itself; the point stays in the candidate's decimal_latitude and
    decimal_longitude and in the captured response.

    The digest input is the match's own identity: the scheme, the place name and admin unit
    GEOLocate returned, and the point rounded to 6 decimals (about 0.1 m, the precision the
    earlier identifier kept). The same match always gives the same identifier, a different point,
    name or unit gives a different one, and score, precision, distance and engine version are
    left out, so a re-ranking never renames a place. The digest is a name, not a cipher:
    whoever holds the same GEOLocate response can recompute it, but the string does not hold
    the coordinates.
    """
    identity = digest({"scheme": GEOLOCATE_ID_SCHEME, "name": match.name, "admin": match.admin,
                       "latitude": f"{match.latitude:.6f}", "longitude": f"{match.longitude:.6f}"})
    return "geolocate:" + identity[:16]


def geolocate_verdict(policy: SourcePolicy, query: SourceQuery, payload, *,
                      trusted_placement: bool = False) -> tuple[LookupStatus, list[dict], int, str]:
    """Verify every GEOLocate match against the interpretation; only agreeing points become candidates."""
    place = geolocate_interpretation(query.query_text, query.field_key)
    if place.latitude is not None and not trusted_placement:
        raise ValueError("GEOLocate placement requires the trusted derivation worker; omit latitude, longitude and radius_km")
    engine, count, matches = _geolocate_matches(payload, place)
    agreeing = sorted((item for item in matches if _geolocate_agrees(query.field_key, place, item)),
                      key=lambda item: (-item.score, item.distance_km or 0.0))
    if not agreeing:
        named = sorted({item.admin or "no unit" for item in matches
                        if (place.radius_km is None or item.distance_km <= place.radius_km)
                        and _fold_words(item.name) == _fold_words(place.place)})
        if named:
            claimed_unit = (place.value if query.field_key in {FieldKey.COUNTY, FieldKey.PROVINCE_STATE}
                            else place.county if _fold_words(place.country) in _USA else place.state)
            return (LookupStatus.NO_MATCH, [], count,
                    f"GEOLocate places {place.place!r} in {', '.join(named)}, not {claimed_unit!r}")
        if place.radius_km is None:
            return (LookupStatus.NO_MATCH, [], count,
                    f"GEOLocate returned {count} match(es); none is {place.place!r} in the queried place context")
        return (LookupStatus.NO_MATCH, [], count,
                f"GEOLocate returned {count} match(es); none is {place.place!r} "
                f"within {place.radius_km:g} km of the interpreted placement")
    best = agreeing[0]
    spread = max(_distance_km(best.latitude, best.longitude, item.latitude, item.longitude) for item in agreeing)
    chosen = [best] if spread <= GEOLOCATE_AGREEMENT_KM else agreeing[:policy.result_limit]
    candidates = [{
        "field_key": str(query.field_key), "value": place.value,
        "authority_id": geolocate_authority_id(item),
        "authority_role": policy.authority_role, "input_literal": place.locality, "rank": rank,
        "decimal_latitude": item.latitude, "decimal_longitude": item.longitude, "geodetic_datum": "EPSG:4326",
        "match_name": item.name, "match_admin": item.admin, "match_precision": item.precision,
        "match_score": item.score, "engine_version": engine,
        **({"distance_km": round(item.distance_km, 1)} if item.distance_km is not None else {}),
    } for rank, item in enumerate(chosen, 1)]
    if len(chosen) == 1:
        return (LookupStatus.SUCCESS, candidates, count,
                f"GEOLocate confirms {place.value!r}: {len(agreeing)} of {count} match(es) agree within "
                f"{GEOLOCATE_AGREEMENT_KM:g} km of each other")
    return (LookupStatus.AMBIGUOUS, candidates, count,
            f"GEOLocate is ambiguous for {place.value!r}: agreeing matches lie up to {spread:.0f} km apart")


class RequestPacer:
    """Process-wide minimum spacing between request starts to one source; it never raises."""

    def __init__(self, intervals: Mapping[str, float], *, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[object]] = asyncio.sleep):
        self._intervals = dict(intervals)
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_start: dict[str, float] = {}

    async def wait(self, source_id: str, *, limit: float | None = None) -> bool:
        """Wait for this request's turn to start; True. With `limit`, a turn
        more than `limit` seconds off is not taken: False at once, and the
        requests after it are not spaced behind a request that is not sent."""
        interval = self._intervals.get(source_id)
        if not interval:
            return True
        with self._lock:
            current = self._clock()
            start = max(current, self._next_start.get(source_id, current))
            if limit is not None and start - current > limit:
                return False
            self._next_start[source_id] = start + interval
        if start > current:
            await self._sleep(start - current)
        return True


SOURCE_PACER = RequestPacer(SOURCE_REQUEST_INTERVAL_SECONDS)


class SourceTransport(Protocol):
    async def get(self, url: str, *, policy: SourcePolicy) -> tuple[int, bytes]: ...


@dataclass(frozen=True, slots=True)
class FixtureSourceTransport:
    """Explicit injected offline fixtures. This adapter performs no HTTP itself."""

    read: Callable[[str, SourcePolicy], Awaitable[tuple[int, bytes]]]

    async def get(self, url: str, *, policy: SourcePolicy) -> tuple[int, bytes]:
        validate_destination(policy, url)
        code, body = await self.read(url, policy)
        if type(code) is not int or not isinstance(body, bytes) or len(body) > policy.max_response_bytes:
            raise ValueError("Offline fixture violates bounded source response contract")
        return code, body


class BoundedHTTPTransport:
    """TLS-verified streamed GET with redirects/encoding/response size refused."""

    def __init__(self, client: httpx.AsyncClient | None = None, *, pacer: RequestPacer | None = None):
        self.client = client
        self.pacer = pacer or SOURCE_PACER

    async def get(self, url: str, *, policy: SourcePolicy) -> tuple[int, bytes]:
        validate_destination(policy, url)
        await self.pacer.wait(policy.id)
        if self.client is None:
            async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as client:
                return await self._read(client, url, policy)
        return await self._read(self.client, url, policy)

    async def _read(self, client, url, policy):
        async with client.stream("GET", url, follow_redirects=False, timeout=policy.timeout_seconds,
                                 headers={"Accept": "application/json", "Accept-Encoding": "identity",
                                          "User-Agent": "FieldMuseumSpecimenResearch/1.0 (https://github.com/anurag-duddu/specimen-digitization-app)"}) as response:
            if 300 <= response.status_code < 400:
                raise ValueError("Source redirects require separately qualified destination")
            if response.headers.get("content-encoding", "identity") not in {"", "identity"}:
                raise ValueError("Compressed source payload is not qualified")
            body = bytearray()
            async for chunk in response.aiter_raw():
                body.extend(chunk)
                if len(body) > policy.max_response_bytes:
                    raise ValueError("Source response exceeds bounded capture")
            return response.status_code, bytes(body)


def validate_destination(policy: SourcePolicy, url: str) -> None:
    from urllib.parse import unquote
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.fragment
        or parsed.port not in {None, 443} or parsed.hostname not in policy.allowed_hosts
        or re.search(r"%(?:2f|5c|2e|00)", parsed.path, re.IGNORECASE)
        or ".." in unquote(parsed.path) or "\\" in unquote(parsed.path)
        or any(ord(character) < 32 for character in unquote(parsed.path))
        or not any(re.fullmatch(pattern, parsed.path) for pattern in policy.allowed_path_patterns)):
        raise ValueError("Destination exceeds qualified source capability")
    if policy.id == "mapcarta" and parsed.path.casefold().startswith(("/s/", "/dynamic/", "/library/", "/challenge")):
        raise ValueError("Mapcarta excluded path")


def _status(code: int) -> LookupStatus:
    return {200: LookupStatus.SUCCESS, 401: LookupStatus.AUTHENTICATION,
            403: LookupStatus.AUTHORIZATION, 429: LookupStatus.RATE_LIMITED}.get(code, LookupStatus.PROVIDER)


def result_envelope(result: SourceResult) -> str:
    """The exact semantic receipt body checked again at deterministic finalization."""
    return canonical_json({"candidate_json": result.candidate_json,
                           "evidence": [item.model_dump(mode="json") for item in result.evidence],
                           "coverage": result.coverage.model_dump(mode="json"), "status": str(result.status)})


EffectDispatch = Callable[[SpecialistRequest, str, dict, Callable[[], Awaitable[str]]], Awaitable[ToolReceipt]]


class SourceBroker:
    """Capabilities enforced in code. Every actual source call needs effect dispatch."""

    def __init__(self, registry: SourceRegistry, *, transport: SourceTransport | None = None,
                 effect_dispatch: EffectDispatch | None = None, georeferencing_adapter=None,
                 collecting_context=None):
        self.registry = registry
        self.transport = transport or BoundedHTTPTransport()
        self.effect_dispatch = effect_dispatch
        self.georeferencing_adapter = georeferencing_adapter
        self.collecting_context = collecting_context
        if type(self.transport) is BoundedHTTPTransport and effect_dispatch is not None and type(effect_dispatch) is not DurableSourceEffects:
            raise ValueError("Actual HTTP source calls require the durable live effect adapter")
        if effect_dispatch is not None and hasattr(effect_dispatch, "validate_transport"):
            effect_dispatch.validate_transport(self.transport)
        self.trusted_results: list[SourceResult] = []

    def available_sources(self, request: SpecialistRequest) -> tuple[str, ...]:
        return tuple(item.id for item in self.registry.allowed(request))

    async def query_source(self, request: SpecialistRequest, query: SourceQuery, *,
                           trusted_anchor: bool = False) -> SourceResult:
        return await self.query(request, query, trusted_anchor=trusted_anchor)

    async def dispatch(self, request: SpecialistRequest, tool_id: str, arguments: dict) -> SourceResult:
        if tool_id != "source_lookup":
            raise ValueError("Tool is outside source capability")
        return await self.query(request, SourceQuery.model_validate(arguments))

    async def query(self, request: SpecialistRequest, query: SourceQuery, *,
                    trusted_anchor: bool = False) -> SourceResult:
        if type(self.transport) is BoundedHTTPTransport and self.effect_dispatch is not None and type(self.effect_dispatch) is not DurableSourceEffects:
            raise ValueError("Actual HTTP source calls require the durable live effect adapter")
        if self.effect_dispatch is not None and hasattr(self.effect_dispatch, "validate_transport"):
            self.effect_dispatch.validate_transport(self.transport)
        policy = self.registry.get(query.source_id)
        if query.field_key not in request.field_keys or request.role not in policy.roles or query.field_key not in policy.fields:
            raise ValueError("Source lookup escaped specialist field scope")
        if request.prompt.source_registry_digest != self.registry.digest:
            raise ValueError("Source registry differs from durable prompt/job pin")
        if policy.source_type == "local_dataset" and not trusted_anchor:
            return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED,
                "Pinned historical dataset is reserved for the trusted derivation worker")
        if query.source_id == "bugguide" and not query.north_american:
            return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED, "BugGuide applicability requires established US/Canada evidence")
        if not policy.ready:
            return self._unavailable(policy, query, policy.qualification_state, "Source endpoint/schema/terms/version qualification incomplete")
        if policy.source_type not in {"public_api", "public_publisher_metadata", "local_dataset"}:
            return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED, "Approved managed browser or licensed credentialed adapter prerequisite")
        if request.scope.sensitive:
            return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED, "No sensitive source disclosure authorization")
        if self.effect_dispatch is None:
            return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED, "Durable effect dispatcher required before source execution")
        if query.source_id in {"tgn", "wikidata", "nga", "georeference_history"}:
            try:
                name = (json.loads(query.query_text)["name"] if query.source_id == "georeference_history"
                        else query.query_text)
            except (TypeError, ValueError, KeyError):
                return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED,
                    "Historical source needs a typed place-only query")
            if not trusted_anchor or query.source_id != "georeference_history":
                defect = historical_place_name_defect(request, name, self.trusted_results)
                if defect:
                    return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED, defect)
        if policy.source_type == "local_dataset":
            if (query.source_id != "georeference_history" or self.georeferencing_adapter is None
                or not hasattr(self.effect_dispatch, "local_lookup")):
                return self._unavailable(policy, query, SourceCoverageState.FAILED,
                    "Pinned historical dataset reader or durable capture is unavailable")

            async def local_invoke() -> str:
                return result_envelope(self.georeferencing_adapter.history_query(request, query))

            receipt = await self.effect_dispatch.local_lookup(request, query, local_invoke)
            if (receipt.scope != request.scope or receipt.source_id != query.source_id
                or receipt.field_keys != (query.field_key,) or receipt.result_json is None):
                raise ValueError("Pinned historical receipt escaped scoped query")
            result = SourceResult.model_validate({**json.loads(receipt.result_json), "receipt": receipt})
            if result.coverage.source_id != policy.id or result.coverage.field_key != query.field_key:
                raise ValueError("Pinned historical result escaped scoped query")
            self.trusted_results.append(result)
            return result
        if query.source_id == "gbif":
            # The adapter needs a genus before it can build a request. Refuse
            # locally before reserving an effect that cannot retain a response.
            parsed = scientific_name(query.query_text)
            if parsed is None or not parsed.genus:
                return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED,
                    "GBIF requires an actual genus or full scientific name from specimen evidence; "
                    "do not invent a genus. If none is evidenced, abstain with waiting_policy and an unresolved value "
                    "under the declared missing-policy rule.")
        if query.source_id == "geolocate":
            # Checked before effect dispatch: a request that cannot be sent must never hold an effect.
            try:
                place = geolocate_interpretation(query.query_text, query.field_key)
                defect = geolocate_place_text_defect(request, place)
                if not defect and place.latitude is not None and not trusted_anchor:
                    defect = ("GEOLocate placement requires the trusted derivation worker; "
                              "omit latitude, longitude and radius_km")
                if not defect and not trusted_anchor:
                    defect = geolocate_grounding_defect(request, query, place, self.trusted_results,
                        collecting_context=self.collecting_context)
            except ValueError as error:
                defect = str(error)
            if defect:
                return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED, defect)

        async def invoke() -> str:
            if hasattr(self.effect_dispatch, "validate_transport"):
                self.effect_dispatch.validate_transport(self.transport)
            return result_envelope(await self._execute(policy, request, query, trusted_anchor=trusted_anchor))

        receipt = await self.effect_dispatch(request, "source_lookup", query.model_dump(mode="json"), invoke)
        if receipt.scope != request.scope or receipt.source_id != query.source_id or receipt.field_keys != (query.field_key,):
            raise ValueError("Effect receipt escaped source request scope")
        if receipt.effect_status != "completed" or receipt.result_json is None:
            return self._unavailable(policy, query, SourceCoverageState.FAILED, "Source effect outcome held unknown or incomplete")
        payload = json.loads(receipt.result_json)
        result = SourceResult.model_validate({**payload, "receipt": receipt})
        if result.coverage.source_id != policy.id or result.coverage.field_key != query.field_key:
            raise ValueError("Replayed source payload differs from effect query")
        self.trusted_results.append(result)
        return result

    def _unavailable(self, policy, query, state, reason):
        return SourceResult(status=LookupStatus.POLICY, coverage=SourceCoverageReceipt(
            source_id=policy.id, field_key=query.field_key, state=state,
            source_version=policy.version, coverage_limit="No qualified exact scientific search completed", reason=reason))

    def derive_spatial_from_trusted_inputs(self, request: SpecialistRequest, *, field_key: FieldKey,
            country: str, validation: SourceResult, settled_inputs: tuple,
            requested_fields: tuple[FieldKey, ...], verbatim_locality: str,
            label_has_elevation: bool | None, tool_call_id: str) -> SourceResult:
        """Compute one proposal from a captured GEOLocate answer and current inputs.

        The captured broker verifies the command, current field revisions and
        effect before it calls this adapter. This pure method still refuses an
        unreceipted or cross-specimen validator result. It is intentionally not
        exposed through the specialist's model tool roster.
        """
        from .georeferencing import derivation_source_result

        if (self.georeferencing_adapter is None or field_key not in request.field_keys
            or field_key not in requested_fields or len(requested_fields) != len(set(requested_fields))
            or request.scope.sensitive or validation.receipt is None
            or validation.receipt.scope != request.scope
            or validation.receipt.source_id != "geolocate"
            or validation.receipt.source_id != validation.coverage.source_id
            or validation.coverage.field_key not in {item.field_key for item in settled_inputs}
            or validation.receipt.field_keys != (validation.coverage.field_key,)
            or validation.receipt.effect_status != "completed"
            or validation.receipt.result_json != result_envelope(validation.model_copy(update={"receipt": None}))
            or tool_call_id != validation.receipt.id):
            raise ValueError("Spatial derivation requires a current captured validator and target field")
        result = self.georeferencing_adapter.derive_rest(
            country=country, validation=validation, settled_inputs=settled_inputs,
            requested_fields=requested_fields, verbatim_locality=verbatim_locality,
            label_has_elevation=label_has_elevation, tool_call_id=tool_call_id)
        return derivation_source_result(result, field_key)

    async def _historical_gazetteer(self, policy: SourcePolicy, query: SourceQuery) -> SourceResult:
        """Run the bounded tier-one chain through the admitted capture transport.

        Every follow-up identifier comes from the preceding parsed response in
        `historical_gazetteers`; every GET is captured before its bytes reach
        that parser. A candidate is historian context, never a settled field.
        """
        from .historical_gazetteers import lookup

        async def fetch(url: str, params: dict[str, str]) -> tuple[int, bytes]:
            final_url = url + "?" + urlencode(params)
            validate_destination(policy, final_url)
            return await self.transport.get(final_url, policy=policy)

        outcome = await lookup(query.source_id, query.query_text, fetch)
        evidence = []
        for ordinal, exchange in enumerate(outcome.exchanges, 1):
            if exchange.response_body is None or exchange.response_digest is None:
                continue
            final_url = exchange.url + "?" + urlencode(exchange.params)
            evidence.append(EvidenceItem(
                id="source-exchange:" + digest({"source_id": query.source_id,
                    "query": query.model_dump(mode="json"), "ordinal": ordinal,
                    "sha256": exchange.response_digest}),
                kind="historical_gazetteer_exchange", source_id=query.source_id,
                locator=final_url, response_digest=exchange.response_digest,
                source_version=policy.source_release or policy.version,
                publisher_assertion_id=f"{policy.publisher_id}:{ordinal}",
                retrieved_at=now(), role="supports"))
        status = outcome.status
        reason = outcome.reason or str(status)
        # A search returned at its cap cannot prove that no other namesakes
        # exist. The source may still offer all retained candidates to compare.
        if query.source_id == "tgn" and len(outcome.places) >= 10:
            status, reason = LookupStatus.AMBIGUOUS, "reconciliation hit ten-result cap"
        if query.source_id == "wikidata" and len(outcome.places) >= 7:
            status, reason = LookupStatus.AMBIGUOUS, "search hit seven-result cap"
        candidates = tuple(canonical_json({**asdict(place),
            "field_key": str(query.field_key), "value": place.name,
            "authority_id": f"{query.source_id}:{place.record_id}",
            "authority_role": "historical_candidate", "input_literal": query.query_text,
            "match_details": {"names": place.names, "kinds": [asdict(item) for item in place.kinds],
                              "country": asdict(place.country) if place.country else None,
                              "parents": [asdict(item) for item in place.parents],
                              "valid_from": place.valid_from, "valid_to": place.valid_to},
            "settlement_allowed": False, "validation_required": "geolocate"})
            for place in outcome.places)
        if status in {LookupStatus.AUTHENTICATION, LookupStatus.AUTHORIZATION}:
            state = SourceCoverageState.INACCESSIBLE
        elif status in {LookupStatus.PROVIDER, LookupStatus.MALFORMED,
                        LookupStatus.TIMEOUT, LookupStatus.RATE_LIMITED, LookupStatus.EMPTY}:
            state = SourceCoverageState.FAILED
        elif status == LookupStatus.POLICY:
            state = SourceCoverageState.UNQUALIFIED
        else:
            state = SourceCoverageState.SEARCHED
        return SourceResult(status=status, evidence=tuple(evidence), candidate_json=candidates,
            coverage=SourceCoverageReceipt(source_id=query.source_id, field_key=query.field_key,
                state=state, source_version=policy.source_release or policy.version,
                qualification_digest=digest(policy), query_digest=digest(query),
                receipt_ids=tuple(item.id for item in evidence), candidate_count=len(candidates),
                coverage_limit="At most three captured responses and bounded returned candidates; names require modern validation",
                reason=f"{status}: {reason}"))

    async def _execute(self, policy, request, query, *, trusted_anchor=False):
        if query.source_id == "field_museum_ipt":
            return await self._museum(policy, query)
        if query.source_id in {"tgn", "wikidata", "nga"}:
            return await self._historical_gazetteer(policy, query)
        try:
            if query.source_id == "gbif":
                from .taxonomy import gbif_query_params
                parsed = scientific_name(query.query_text)
                params = gbif_query_params(request, query)
                url = "https://api.gbif.org/v2/species/match?" + urlencode(params)
            elif query.source_id == "global_names_verifier":
                from urllib.parse import quote
                url = "https://verifier.globalnames.org/api/v1/verifications/" + quote(query.query_text, safe="")
            elif query.source_id == "catalogue_of_life":
                if not re.fullmatch(r"[1-9][0-9]*", policy.source_release or ""):
                    raise ValueError("COL immutable integer release key must be pinned; aliases are mutable")
                url = f"https://api.checklistbank.org/dataset/{policy.source_release}/nameusage/search?" + urlencode({"q": query.query_text, "limit": policy.result_limit})
            elif query.source_id == "geolocate":
                place = geolocate_interpretation(query.query_text, query.field_key)
                url = GEOLOCATE_ENDPOINT + "?" + urlencode({
                    "Country": place.country, "State": place.state, "County": place.county,
                    "Locality": place.locality, "hwyX": "false", "enableH2O": "false", "doUncert": "true",
                    "doPoly": "false", "displacePoly": "false", "languageKey": "0", "fmt": "json"})
            else:
                return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED, "Typed hosted-method adapter/schema/terms prerequisite")
            code, raw = await self.transport.get(url, policy=policy)
            if code != 200:
                return self._failure(policy, query, _status(code), raw)
            payload = _source_json(raw)
            if query.source_id == "geolocate":
                status, candidates, count, reason = geolocate_verdict(
                    policy, query, payload, trusted_placement=trusted_anchor)
                # The reason leads with the typed outcome, as every other source's reason is the status.
                return self._result(policy, query, status, raw, url, candidates, count=count,
                                    reason=f"{status}: {reason}")
            candidates = []
            status = LookupStatus.AMBIGUOUS
            if query.source_id == "gbif":
                if not isinstance(payload, dict) or not _shape_ok(payload):
                    raise ValueError("GBIF typed schema mismatch")
                diagnostics = payload["diagnostics"]
                usage, accepted = payload.get("usage"), payload.get("acceptedUsage")
                classification, alternatives = payload.get("classification") or [], diagnostics.get("alternatives") or []
                synonym = diagnostics.get("matchType") == "EXACT" and cleared_synonym(parsed, usage, accepted, classification, alternatives)
                if diagnostics.get("matchType") == "NONE":
                    status = LookupStatus.NO_MATCH
                elif synonym or (diagnostics.get("matchType") == "EXACT" and row_one(parsed, usage, classification, alternatives)):
                    status = LookupStatus.SUCCESS
                chosen = accepted if synonym else usage
                if status != LookupStatus.NO_MATCH and isinstance(chosen, dict):
                    candidates.append({"field_key": str(query.field_key), "value": chosen.get("name"),
                                       "authority_id": f"{COL_XR}:{chosen.get('key')}", "rank": chosen.get("rank"),
                                       "authority_role": policy.authority_role, "input_literal": query.query_text,
                                       "checklist_key": COL_XR, "match_type": diagnostics.get("matchType")})
            elif query.source_id == "global_names_verifier":
                if not isinstance(payload, dict) or not isinstance(payload.get("names"), list):
                    raise ValueError("GNV verification schema mismatch")
                names = payload["names"]
                if len(names) != 1 or names[0].get("name") != query.query_text:
                    raise ValueError("GNV response changed requested name identity")
                best = names[0].get("bestResult")
                if best is None:
                    status = LookupStatus.NO_MATCH
                elif (not isinstance(best, dict) or type(best.get("dataSourceId")) is not int
                      or not isinstance(best.get("currentName") or best.get("matchedName"), str)):
                    raise ValueError("GNV match/source attribution schema mismatch")
                else:
                    candidates.append({"field_key": str(query.field_key), "input_literal": query.query_text,
                        "value": best.get("currentName") or best.get("matchedName"),
                        "authority_id": f"gnv:{best['dataSourceId']}:{best.get('currentRecordId') or best.get('recordId')}",
                        "authority_role": "supports", "underlying_source_id": best["dataSourceId"],
                        "underlying_source_title": best.get("dataSourceTitleShort"),
                        "underlying_entry_date": best.get("entryDate"), "match_type": best.get("matchType"),
                        "classification_ranks": best.get("classificationRanks"), "is_synonym": best.get("isSynonym")})
                    status = LookupStatus.SUCCESS
            elif query.source_id == "catalogue_of_life":
                if not isinstance(payload, dict) or not isinstance(payload.get("result"), list) or type(payload.get("total")) is not int:
                    raise ValueError("COL nameusage schema mismatch")
                status = LookupStatus.NO_MATCH if payload["total"] == 0 else LookupStatus.AMBIGUOUS
                for row in payload["result"][:policy.result_limit]:
                    usage = row.get("usage") if isinstance(row, dict) else None
                    name = usage.get("name") if isinstance(usage, dict) else None
                    if (not isinstance(name, dict) or not isinstance(name.get("scientificName"), str)
                        or str(usage.get("datasetKey")) != policy.source_release):
                        raise ValueError("COL nameusage differs from pinned release")
                    candidates.append({"field_key": str(query.field_key), "input_literal": query.query_text,
                        "value": usage.get("label") or name["scientificName"],
                        "authority_id": f"col:{policy.source_release}:{usage.get('id')}",
                        "authority_role": "supports", "rank": name.get("rank"), "status": usage.get("status"),
                        "scientific_name": name["scientificName"], "dataset_key": policy.source_release})
                if payload["total"] == 1 and candidates:
                    status = LookupStatus.SUCCESS
            return self._result(policy, query, status, raw, url, candidates)
        except httpx.TimeoutException:
            return self._failure(policy, query, LookupStatus.TIMEOUT)
        except httpx.HTTPError:
            return self._failure(policy, query, LookupStatus.PROVIDER)
        except (ValueError, KeyError, TypeError, ArithmeticError):
            return self._failure(policy, query, LookupStatus.MALFORMED)

    async def _museum(self, policy, query):
        if query.join is None or query.join.dataset_id != MUSEUM_DATASET:
            raise ValueError("Public Museum metadata requires fixed dataset exact specimen join")
        join = query.join
        params = {"datasetKey": MUSEUM_DATASET, "limit": policy.result_limit, "offset": 0}
        if join.occurrence_id:
            params["occurrenceId"] = join.occurrence_id
        else:
            params.update({"institutionCode": join.institution_code, "collectionCode": join.collection_code,
                           "catalogNumber": join.catalog_number})
        url = "https://api.gbif.org/v1/occurrence/search?" + urlencode(params)
        try:
            code, raw = await self.transport.get(url, policy=policy)
            if code != 200:
                return self._failure(policy, query, _status(code), raw)
            payload = _source_json(raw)
            if (not isinstance(payload, dict) or not isinstance(payload.get("results"), list)
                or type(payload.get("count")) is not int):
                raise ValueError("Museum bounded search schema mismatch")
            rows = payload["results"]
            count = payload["count"]
            if count == 0 and not rows:
                return self._result(policy, query, LookupStatus.NO_MATCH, raw, url, [], exact_attempt=True, count=0)
            if count != 1 or len(rows) != 1:
                return self._result(policy, query, LookupStatus.AMBIGUOUS, raw, url, [], exact_attempt=True, count=count)
            indexed = rows[0]
            if indexed.get("datasetKey") != MUSEUM_DATASET or type(indexed.get("key")) is not int:
                raise ValueError("Matched row has wrong dataset/key")
            verbatim_url = f"https://api.gbif.org/v1/occurrence/{indexed['key']}/verbatim"
            code, publisher_raw = await self.transport.get(verbatim_url, policy=policy)
            if code != 200:
                return self._failure(policy, query, _status(code), publisher_raw)
            publisher = _source_json(publisher_raw)
            fields = publisher.get("fields") if isinstance(publisher, dict) else None
            if not isinstance(fields, dict) or publisher.get("key") != indexed["key"]:
                raise ValueError("Publisher verbatim identity/schema mismatch")
            # GBIF keys may use full Darwin Core URIs; normalize only term namespace.
            values = {key.rsplit("/", 1)[-1]: value for key, value in fields.items()}
            exact = (values.get("occurrenceID") == join.occurrence_id if join.occurrence_id else
                     all(values.get(key) == target for key, target in (
                         ("institutionCode", join.institution_code), ("collectionCode", join.collection_code),
                         ("catalogNumber", join.catalog_number))))
            if not exact or values.get("individualCount") not in {None, "1", 1} or values.get("parentOccurrenceID"):
                return self._result(policy, query, LookupStatus.AMBIGUOUS, publisher_raw, verbatim_url, [], exact_attempt=True, count=1)
            term = _DWC[query.field_key]
            written = values.get(term)
            if not isinstance(written, str) or not written.strip():
                return self._result(policy, query, LookupStatus.NO_MATCH, publisher_raw, verbatim_url, [], exact_attempt=True, exact_proven=True, count=1)
            event_kind = "determination" if query.field_key == FieldKey.DATE_IDENTIFIED else "collecting"
            candidate = {"field_key": str(query.field_key), "value": written,
                         "authority_id": f"occurrence:{values.get('occurrenceID', indexed['key'])}",
                         "authority_role": "publisher_assertion", "event_kind": event_kind,
                         "publisher_id": policy.publisher_id, "dataset_id": MUSEUM_DATASET,
                         "occurrence_id": values.get("occurrenceID"), "publisher_term": term,
                         "last_crawled": indexed.get("lastCrawled"), "publication_version": policy.source_release}
            candidate["event_id"] = f"published:{values.get('occurrenceID', indexed['key'])}:{event_kind}"
            if str(query.field_key).startswith("date_"):
                if not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", written):
                    return self._result(policy, query, LookupStatus.AMBIGUOUS, publisher_raw, verbatim_url, [], exact_attempt=True, exact_proven=True, count=1)
                candidate["precision"] = {4: "year", 7: "month", 10: "day"}[len(written)]
                from .evidence import parse_temporal, EvidenceError
                try:
                    parse_temporal(written)
                except EvidenceError:
                    return self._result(policy, query, LookupStatus.AMBIGUOUS, publisher_raw, verbatim_url, [], exact_attempt=True, exact_proven=True, count=1)
            return self._result(policy, query, LookupStatus.SUCCESS, publisher_raw, verbatim_url, [candidate], exact_attempt=True, exact_proven=True, count=1)
        except httpx.TimeoutException:
            return self._failure(policy, query, LookupStatus.TIMEOUT)
        except httpx.HTTPError:
            return self._failure(policy, query, LookupStatus.PROVIDER)
        except (ValueError, KeyError, TypeError):
            return self._failure(policy, query, LookupStatus.MALFORMED)

    def _failure(self, policy, query, status, raw=b""):
        return SourceResult(status=status, coverage=SourceCoverageReceipt(
            source_id=policy.id, field_key=query.field_key,
            state=SourceCoverageState.INACCESSIBLE if status in {LookupStatus.AUTHENTICATION, LookupStatus.AUTHORIZATION} else SourceCoverageState.FAILED,
            source_version=policy.source_release or policy.version,
            qualification_digest=digest(policy), query_digest=digest(query),
            coverage_limit="Transport/schema failure is not scientific absence", reason=str(status)))

    def _result(self, policy, query, status, raw, locator, candidates, *, exact_attempt=False, exact_proven=False, count=None, reason=None):
        response_digest = hashlib.sha256(raw).hexdigest()
        evidence_id = "source:" + digest((policy.id, query.model_dump(mode="json"), response_digest))
        publisher_id = f"{policy.publisher_id}:{policy.source_release}:{query.join.occurrence_id or query.join.catalog_number}" if query.join else f"{policy.publisher_id}:{policy.source_release}:{query.query_text}"
        evidence = EvidenceItem(id=evidence_id, kind="qualified_source", source_id=policy.id,
                                locator=locator, response_digest=response_digest,
                                source_version=policy.source_release, publisher_assertion_id=publisher_id,
                                retrieved_at=now(), role="decides" if policy.authority_role == "decides" else "supports")
        # A no-match at an exact scoped source is exhausted only for that source/field.
        # A flat publisher row's missing date never establishes full determination history.
        state = SourceCoverageState.SEARCHED
        limit = "Bounded source assertion; other available strategies remain explicit"
        if status == LookupStatus.NO_MATCH and exact_attempt:
            state = SourceCoverageState.EXHAUSTED
            limit = "Only this pinned publisher occurrence search/term; not full EMu history"
        coverage = SourceCoverageReceipt(
            source_id=policy.id, field_key=query.field_key, state=state,
            source_version=policy.source_release, qualification_digest=digest(policy),
            exact_join_attempted=exact_attempt, exact_join_proven=exact_proven,
            query_digest=digest(query), receipt_ids=(evidence_id,), candidate_count=count,
            coverage_limit=limit, reason=reason or str(status))
        return SourceResult(status=status, coverage=coverage, evidence=(evidence,),
                            candidate_json=tuple(canonical_json(item) for item in candidates))

    async def invoke_utility(self, request: SpecialistRequest, tool_id: str, arguments: dict) -> SourceResult:
        from .evidence import catalog_literal, parse_measurement
        if tool_id in {"settle_temporal", "settle_elevation", "settle_collectors", "settle_collection"}:
            return local_settlement_result(request, tool_id, arguments)
        allowed = {"parse_measurement": SpecialistRole.MEASUREMENT,
                   "parse_temporal": SpecialistRole.TEMPORAL,
                   "catalog_number": SpecialistRole.COLLECTION}
        if tool_id not in allowed or request.role != allowed[tool_id]:
            raise UtilityInputError("Utility is outside reviewed role/tool roster")
        if set(arguments) != {"text", "field_key"}:
            raise UtilityInputError("Utility accepts only typed measurement text/field")
        field_key = _utility_field_key(arguments["field_key"])
        if field_key not in request.field_keys:
            raise UtilityInputError("Utility field exceeds scoped request")
        if tool_id == "catalog_number" and field_key != FieldKey.FMNH_INS_NUMBER:
            raise UtilityInputError("Catalogue utility cannot supply collection code or another field")
        matching = [assembly for assembly in request.assemblies
            if (tool_id != "catalog_number" or assembly.field_key == field_key)
            and arguments["text"] == assembly.interpreted_text]
        if not matching:
            raise UtilityInputError("Utility text must come from an available evidenced assembly")
        from .evidence import validate_assembly
        if tool_id == "catalog_number":
            for assembly in matching:
                validate_assembly(request, assembly)
        if tool_id == "catalog_number":
            parsed = {"field_key": str(field_key), "value": catalog_literal(arguments["text"]),
                      "rule_version": "catalog-number-v1"}
        else:
            from .temporal_context import parse_temporal_text
            parsed = (parse_measurement(arguments["text"]) if tool_id == "parse_measurement"
                      else parse_temporal_text(request, arguments["text"], field_key)).model_dump(mode="json")
        return SourceResult(status=LookupStatus.SUCCESS,
                            coverage=SourceCoverageReceipt(source_id=tool_id, field_key=field_key,
                                state=SourceCoverageState.SEARCHED, source_version="deterministic-domain-v1",
                                coverage_limit="Deterministic local utility; settlement validates graph/G32",
                                reason="exact_parse"),
                            candidate_json=(canonical_json(parsed),))


class DurableSourceEffects:
    """Production broker adapter; SQL holds/capture/replay precede tool return.

Offline permits only the exact FixtureSourceTransport instance. Actual HTTP is
always execution_class live and subject to the inherited reconciled program HOLD.
"""

    def __init__(self, broker, scope, lease, *, transport: SourceTransport,
                 execution_class: str = "live", reservation_micro_usd: int = 1):
        if execution_class not in {"offline", "live"}:
            raise ValueError("Source execution class is explicit")
        if execution_class == "offline" and type(transport) is not FixtureSourceTransport:
            raise ValueError("Actual network transport cannot use offline budget admission")
        if type(reservation_micro_usd) is not int or reservation_micro_usd <= 0:
            raise ValueError("Source effect requires positive conservative reservation")
        self.broker, self.scope, self.lease = broker, scope, lease
        self.transport, self.execution_class = transport, execution_class
        self.reservation_micro_usd = reservation_micro_usd

    def validate_transport(self, transport: SourceTransport) -> None:
        if transport is not self.transport:
            raise ValueError("Source effect transport differs from its pinned execution class")

    async def __call__(self, request: SpecialistRequest, tool_id: str, arguments: dict,
                       invoke: Callable[[], Awaitable[str]]) -> ToolReceipt:
        from .persistence import CapturedResult, HeldUnknown, StaleWork
        try:
            request = SpecialistRequest.model_validate(request.model_dump(mode="json"))
        except ValueError:
            raise ValueError("durable_source_request_contract_changed") from None
        query = SourceQuery.model_validate(arguments)
        if tool_id != "source_lookup" or query.field_key not in request.field_keys:
            raise ValueError("Durable source effect escaped typed tool/field")
        identity = self.scope.identity()
        if any(identity.get(key) != getattr(request.scope, key) for key in identity):
            raise PermissionError("Durable source scope/generation differs from specialist")
        if self.scope.sensitive != request.scope.sensitive:
            raise PermissionError("Durable source sensitivity differs from request")
        # Missing captures mean revision zero only, matching initial request
        # factories. The authoritative job check below rejects that default
        # after a field has advanced.
        field_revision = request.field_revisions.get(query.field_key, 0)
        logical_request = {"tool_id": tool_id, "arguments": query.model_dump(mode="json"),
                           "scope": request.scope.model_dump(mode="json"),
                           "field_revision": field_revision,
                           "prompt_digest": request.prompt.digest,
                           "source_registry_digest": request.prompt.source_registry_digest,
                           "purpose_policy": PUBLIC_METADATA_POLICY if query.source_id == "field_museum_ipt" else "insects-research-v1"}
        operation_key = "source_lookup:" + digest(logical_request)

        def validate_current_request():
            document = self.broker.store._read(self.scope)
            job = self.broker.store._lease(document.state, self.scope, self.lease, document.server_time)
            pins = job["pins"]
            if (pins["input_digest"] != request.scope.input_digest
                or digest(pins["profile"]) != request.scope.profile_digest
                or pins["prompts"].get(str(request.role)) != request.prompt.model_dump(mode="json")
                or pins["sources"].get("registry_digest") != request.prompt.source_registry_digest):
                raise PermissionError("Durable source request/profile/prompt/source pins changed")
            field = job["fields"].get(str(query.field_key))
            if not field or field["locked"] or field["revision"] != field_revision:
                raise StaleWork("durable_source_field_revision_or_lock_changed")
            for effect in document.state["effects"].values():
                if effect["job_key"] != self.scope.key or str(query.field_key) not in effect["field_keys"]:
                    continue
                # The original logical effect may discover and reconcile its
                # capture through DurableEffectBroker. A new investigation
                # cannot bypass a sent/unknown result by changing its identity.
                if effect["scope"] == self.scope.identity() and effect["operation_key"] == operation_key:
                    continue
                if (effect["status"] in {"sending", "held_unknown"}
                    or (effect["receipt"] is not None and effect["actual_micro_usd"] is None)):
                    raise HeldUnknown("durable_source_field_has_unreconciled_effect")

        validate_current_request()

        async def dispatch(attempt_id, provider_idempotency_key):
            # Revision/lock changes after reservation still forbid invocation.
            validate_current_request()
            raw = await invoke()
            if len(raw.encode()) > 32768:
                raise ValueError("Source semantic capture exceeds pinned output bound")
            payload = json.loads(raw)
            result = SourceResult.model_validate(payload)
            if result.coverage.source_id != query.source_id or result.coverage.field_key != query.field_key:
                raise PermissionError("Typed source result escaped query field/source")
            # Registry permits only free public reads. Actual price is known zero;
            # this does not reopen paid source/model access under an unreconciled HOLD.
            return CapturedResult(typed_payload=payload, actual_micro_usd=0,
                                  usage={"source_requests": 1, "semantic_bytes": len(raw.encode())})

        durable = await self.broker.execute(
            self.scope, self.lease, operation_key, logical_request,
            self.reservation_micro_usd, dispatch, execution_class=self.execution_class,
            field_keys=(str(query.field_key),),
        )
        effect = self.broker.store.effect(self.scope, durable.effect_id)
        payload = SourceResult.model_validate(durable.typed_payload)
        raw = result_envelope(payload)
        return ToolReceipt(
            id="effect:" + durable.effect_id, scope=request.scope, tool_id=tool_id,
            source_id=query.source_id, field_keys=(query.field_key,), effect_id=durable.effect_id,
            attempt_ids=tuple(item["attempt_id"] for item in effect["attempts"]),
            request_digest=effect["request_digest"], binding_digest=effect["binding_digest"],
            outcome=payload.status, effect_status="completed", evidence_ids=tuple(item.id for item in payload.evidence),
            capture_locator=durable.capture.locator, response_digest=durable.capture.sha256,
            reservation_micro_usd=effect["reservation_micro_usd"], settled_micro_usd=durable.actual_micro_usd,
            held_micro_usd=durable.held_micro_usd, result_json=raw,
            result_digest=hashlib.sha256(raw.encode()).hexdigest(),
        )
