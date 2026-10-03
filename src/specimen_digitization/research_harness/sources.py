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
from dataclasses import dataclass
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Protocol
from urllib.parse import urlencode, urlsplit

import httpx
from pydantic import Field

from specimen_digitization.application.domain import LookupStatus, now
from specimen_digitization.application.lookup import (
    COL_XR, _shape_ok, cleared_synonym, row_one, scientific_name,
)

from .contracts import (
    Digest, EvidenceItem, FieldKey, FrozenRecord, SourceCoverageReceipt,
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
    max_response_bytes: int = Field(default=150_000, gt=0, le=1_000_000)
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
                     and (not qualified_only or policy.ready))


def insects_registry(*, qualification_overrides: Mapping[str, dict] | None = None) -> SourceRegistry:
    """All eight owner-selected sources; no unqualified site grants a tool."""
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
_GEOLOCATE_REQUIRED = ("country", "locality", "place", "value", "latitude", "longitude", "radius_km")
_GEOLOCATE_BOUNDS = {"latitude": (-90.0, 90.0), "longitude": (-180.0, 180.0), "radius_km": (1.0, 100.0)}


@dataclass(frozen=True, slots=True)
class GeolocateInterpretation:
    """The historian's reading of one locality, as sent to GEOLocate and checked against it."""

    country: str
    state: str
    county: str
    locality: str
    place: str
    value: str
    latitude: float
    longitude: float
    radius_km: float


@dataclass(frozen=True, slots=True)
class _GeolocateMatch:
    latitude: float
    longitude: float
    name: str
    admin: str
    precision: str
    score: int
    distance_km: float


def geolocate_interpretation(query_text: str) -> GeolocateInterpretation:
    """Parse the query_text JSON; the ValueError message tells the agent what to correct."""
    try:
        value = _source_json(query_text.encode())
    except ValueError:
        value = None
    if not isinstance(value, dict):
        raise ValueError("GEOLocate query_text must be one JSON object")
    unknown = sorted(set(value) - set(_GEOLOCATE_TEXT) - set(_GEOLOCATE_BOUNDS))
    missing = [key for key in _GEOLOCATE_REQUIRED if key not in value]
    if unknown or missing:
        raise ValueError("GEOLocate query_text keys: " + "; ".join(
            part for part in ("unknown " + ", ".join(unknown) if unknown else "",
                              "missing " + ", ".join(missing) if missing else "") if part))
    for key in _GEOLOCATE_TEXT:
        item = value.get(key, "")
        if (type(item) is not str or item != item.strip() or len(item) > 200
                or any(ord(character) < 32 for character in item) or (key in _GEOLOCATE_REQUIRED and not item)):
            raise ValueError(f"GEOLocate {key} must be trimmed text of at most 200 characters")
    for key, (low, high) in _GEOLOCATE_BOUNDS.items():
        item = value[key]
        if type(item) not in (int, float) or not math.isfinite(item) or not low <= item <= high:
            raise ValueError(f"GEOLocate {key} must be a number from {low:g} to {high:g}")
    return GeolocateInterpretation(
        country=value["country"], state=value.get("state", ""), county=value.get("county", ""),
        locality=value["locality"], place=value["place"], value=value["value"], latitude=float(value["latitude"]),
        longitude=float(value["longitude"]), radius_km=float(value["radius_km"]))


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
        if (not isinstance(properties, dict) or geometry.get("type") != "Point"
                or not isinstance(point, list) or len(point) != 2
                or any(type(item) not in (int, float) or not math.isfinite(item) for item in point)
                or type(properties.get("parsePattern")) is not str or type(properties.get("precision")) is not str
                or type(properties.get("score")) is not int or type(properties.get("debug")) is not str):
            raise ValueError("GEOLocate feature schema mismatch")
        longitude, latitude = (float(item) for item in point)
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("GEOLocate coordinates out of range")
        admin = re.search(r"(?:^|\|):Adm=([^|]*)", properties["debug"])
        matches.append(_GeolocateMatch(
            latitude=latitude, longitude=longitude, name=properties["parsePattern"],
            admin=admin.group(1) if admin else "", precision=properties["precision"],
            score=properties["score"],
            distance_km=_distance_km(place.latitude, place.longitude, latitude, longitude)))
    return engine, count, matches


def _geolocate_agrees(field_key: FieldKey, place: GeolocateInterpretation, match: _GeolocateMatch) -> bool:
    """The match must be the named place, near the historian's placement, inside the claimed unit."""
    if match.distance_km > place.radius_km or _fold_words(match.name) != _fold_words(place.place):
        return False
    if field_key in {FieldKey.PROVINCE_STATE, FieldKey.COUNTY}:
        return bool(match.admin) and _fold_words(match.admin) == _fold_words(place.value)
    return True


def geolocate_verdict(policy: SourcePolicy, query: SourceQuery, payload) -> tuple[LookupStatus, list[dict], int, str]:
    """Verify every GEOLocate match against the interpretation; only agreeing points become candidates."""
    place = geolocate_interpretation(query.query_text)
    engine, count, matches = _geolocate_matches(payload, place)
    agreeing = sorted((item for item in matches if _geolocate_agrees(query.field_key, place, item)),
                      key=lambda item: (-item.score, item.distance_km))
    if not agreeing:
        named = sorted({item.admin or "no unit" for item in matches if item.distance_km <= place.radius_km
                        and _fold_words(item.name) == _fold_words(place.place)})
        if named:
            return (LookupStatus.NO_MATCH, [], count,
                    f"GEOLocate places {place.place!r} in {', '.join(named)}, not {place.value!r}")
        return (LookupStatus.NO_MATCH, [], count,
                f"GEOLocate returned {count} match(es); none is {place.place!r} "
                f"within {place.radius_km:g} km of the interpreted placement")
    best = agreeing[0]
    spread = max(_distance_km(best.latitude, best.longitude, item.latitude, item.longitude) for item in agreeing)
    chosen = [best] if spread <= GEOLOCATE_AGREEMENT_KM else agreeing[:policy.result_limit]
    candidates = [{
        "field_key": str(query.field_key), "value": place.value,
        "authority_id": f"geolocate:{item.latitude:.6f},{item.longitude:.6f}",
        "authority_role": policy.authority_role, "input_literal": place.locality, "rank": rank,
        "decimal_latitude": item.latitude, "decimal_longitude": item.longitude, "geodetic_datum": "EPSG:4326",
        "match_name": item.name, "match_admin": item.admin, "match_precision": item.precision,
        "match_score": item.score, "distance_km": round(item.distance_km, 1), "engine_version": engine,
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

    async def wait(self, source_id: str) -> None:
        interval = self._intervals.get(source_id)
        if not interval:
            return
        with self._lock:
            current = self._clock()
            start = max(current, self._next_start.get(source_id, current))
            self._next_start[source_id] = start + interval
        if start > current:
            await self._sleep(start - current)


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
                                 headers={"Accept": "application/json", "Accept-Encoding": "identity"}) as response:
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
                 effect_dispatch: EffectDispatch | None = None):
        self.registry = registry
        self.transport = transport or BoundedHTTPTransport()
        self.effect_dispatch = effect_dispatch
        if type(self.transport) is BoundedHTTPTransport and effect_dispatch is not None and type(effect_dispatch) is not DurableSourceEffects:
            raise ValueError("Actual HTTP source calls require the durable live effect adapter")
        if effect_dispatch is not None and hasattr(effect_dispatch, "validate_transport"):
            effect_dispatch.validate_transport(self.transport)
        self.trusted_results: list[SourceResult] = []

    def available_sources(self, request: SpecialistRequest) -> tuple[str, ...]:
        return tuple(item.id for item in self.registry.allowed(request))

    async def query_source(self, request: SpecialistRequest, query: SourceQuery) -> SourceResult:
        return await self.query(request, query)

    async def dispatch(self, request: SpecialistRequest, tool_id: str, arguments: dict) -> SourceResult:
        if tool_id != "source_lookup":
            raise ValueError("Tool is outside source capability")
        return await self.query(request, SourceQuery.model_validate(arguments))

    async def query(self, request: SpecialistRequest, query: SourceQuery) -> SourceResult:
        if type(self.transport) is BoundedHTTPTransport and self.effect_dispatch is not None and type(self.effect_dispatch) is not DurableSourceEffects:
            raise ValueError("Actual HTTP source calls require the durable live effect adapter")
        if self.effect_dispatch is not None and hasattr(self.effect_dispatch, "validate_transport"):
            self.effect_dispatch.validate_transport(self.transport)
        policy = self.registry.get(query.source_id)
        if query.field_key not in request.field_keys or request.role not in policy.roles or query.field_key not in policy.fields:
            raise ValueError("Source lookup escaped specialist field scope")
        if request.prompt.source_registry_digest != self.registry.digest:
            raise ValueError("Source registry differs from durable prompt/job pin")
        if query.source_id == "bugguide" and not query.north_american:
            return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED, "BugGuide applicability requires established US/Canada evidence")
        if not policy.ready:
            return self._unavailable(policy, query, policy.qualification_state, "Source endpoint/schema/terms/version qualification incomplete")
        if policy.source_type not in {"public_api", "public_publisher_metadata"}:
            return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED, "Approved managed browser or licensed credentialed adapter prerequisite")
        if request.scope.sensitive:
            return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED, "No sensitive source disclosure authorization")
        if self.effect_dispatch is None:
            return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED, "Durable effect dispatcher required before source execution")
        if query.source_id == "geolocate":
            # Checked before effect dispatch: a request that cannot be sent must never hold an effect.
            try:
                geolocate_interpretation(query.query_text)
            except ValueError as error:
                return self._unavailable(policy, query, SourceCoverageState.UNQUALIFIED, str(error))

        async def invoke() -> str:
            if hasattr(self.effect_dispatch, "validate_transport"):
                self.effect_dispatch.validate_transport(self.transport)
            return result_envelope(await self._execute(policy, request, query))

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

    async def _execute(self, policy, request, query):
        if query.source_id == "field_museum_ipt":
            return await self._museum(policy, query)
        try:
            if query.source_id == "gbif":
                parsed = scientific_name(query.query_text)
                if parsed is None or not parsed.genus:
                    raise ValueError("Scientific name cannot be parsed at stated rank")
                params = {"scientificName": parsed.query, "taxonRank": parsed.rank,
                          "kingdom": "Animalia", "class": "Insecta", "checklistKey": COL_XR, "verbose": "true"}
                url = "https://api.gbif.org/v2/species/match?" + urlencode(params)
            elif query.source_id == "global_names_verifier":
                from urllib.parse import quote
                url = "https://verifier.globalnames.org/api/v1/verifications/" + quote(query.query_text, safe="")
            elif query.source_id == "catalogue_of_life":
                if not re.fullmatch(r"[1-9][0-9]*", policy.source_release or ""):
                    raise ValueError("COL immutable integer release key must be pinned; aliases are mutable")
                url = f"https://api.checklistbank.org/dataset/{policy.source_release}/nameusage/search?" + urlencode({"q": query.query_text, "limit": policy.result_limit})
            elif query.source_id == "geolocate":
                place = geolocate_interpretation(query.query_text)
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
                status, candidates, count, reason = geolocate_verdict(policy, query, payload)
                return self._result(policy, query, status, raw, url, candidates, count=count, reason=reason)
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
                if isinstance(chosen, dict):
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
        except (ValueError, KeyError, TypeError):
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
        from .evidence import catalog_literal, parse_measurement, parse_temporal
        allowed = {"parse_measurement": SpecialistRole.MEASUREMENT,
                   "parse_temporal": SpecialistRole.TEMPORAL,
                   "catalog_number": SpecialistRole.COLLECTION}
        if tool_id not in allowed or request.role != allowed[tool_id]:
            raise ValueError("Utility is outside reviewed role/tool roster")
        if set(arguments) != {"text", "field_key"}:
            raise ValueError("Utility accepts only typed measurement text/field")
        field_key = FieldKey(arguments["field_key"])
        if field_key not in request.field_keys:
            raise ValueError("Utility field exceeds scoped request")
        if not any(arguments["text"] == assembly.interpreted_text for assembly in request.assemblies):
            raise ValueError("Utility text must come from an available evidenced assembly")
        if tool_id == "catalog_number":
            parsed = {"field_key": str(field_key), "value": catalog_literal(arguments["text"]),
                      "rule_version": "catalog-number-v1"}
        else:
            parsed = (parse_measurement(arguments["text"]) if tool_id == "parse_measurement"
                      else parse_temporal(arguments["text"])).model_dump(mode="json")
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
