"""Tier 1: Getty TGN's requests and answers (GEO.md 7).

The module builds requests to TGN's reconciliation service and SPARQL endpoint
and reads the answers into `Place` records, with one `LookupStatus` per answer.
It sends nothing: the tool sends each request and records it as a sub-call. A
reconciliation query carries one reading's name as S4's place-request filter
returns it (PLAN 4.8); a SPARQL query carries TGN ids only. Both services answer
anonymously, and Getty's token-gated gateway is not used (PLAN 2.3).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

from .domain import LookupStatus
from .georef_places import Place, Ref

SOURCE = "tgn"
RECONCILE = "https://services.getty.edu/vocab/reconcile/"
SPARQL = "https://vocab.getty.edu/sparql.json"
LICENSE = "ODC-By-1.0"
# The credit line Getty's data-services page asks for (checked 2026-09-24).
CREDIT = (
    "Contains information from the J. Paul Getty Trust, Getty Research Institute, "
    "Thesaurus of Geographic Names, which is made available under the ODC Attribution License"
)
LIMIT = 10  # reconciliation hits per reading
MAX_IDS = 50  # records per SPARQL query
RECORD_ID = re.compile(r"[0-9]{1,10}")
TGN = "http://vocab.getty.edu/tgn/"
AAT = "http://vocab.getty.edu/aat/"
ENGLISH = AAT + "300388277"
NATIONS = AAT + "300128207"
STATUSES = {
    401: LookupStatus.AUTHENTICATION,
    403: LookupStatus.AUTHORIZATION,
    429: LookupStatus.RATE_LIMITED,
}
PREFIXES = """PREFIX gvp: <http://vocab.getty.edu/ontology#>
PREFIX xl: <http://www.w3.org/2008/05/skos-xl#>
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX wgs: <http://www.w3.org/2003/01/geo/wgs84_pos#>
PREFIX tgn: <http://vocab.getty.edu/tgn/>
"""
# Each record's GVP name, place types, preferred type, point, preferred parent,
# and every ancestor on the preferred chain with its name, type and parent.
RECORDS = (
    PREFIXES
    + """SELECT ?place ?name ?type ?typeName ?preferredType ?lat ?long ?parent
       ?ancestor ?ancestorName ?ancestorType ?ancestorParent
WHERE {
  VALUES ?place { %s }
  { ?place gvp:prefLabelGVP/xl:literalForm ?name . }
  UNION { ?place gvp:placeType ?type . ?type gvp:prefLabelGVP/xl:literalForm ?typeName . }
  UNION { ?place gvp:placeTypePreferred ?preferredType . }
  UNION { ?place foaf:focus ?focus . ?focus wgs:lat ?lat ; wgs:long ?long . }
  UNION { ?place gvp:broaderPreferred ?parent . }
  UNION {
    ?place gvp:broaderPreferredExtended ?ancestor .
    FILTER(?ancestor != ?place)
    ?ancestor gvp:prefLabelGVP/xl:literalForm ?ancestorName .
    OPTIONAL { ?ancestor gvp:placeTypePreferred ?ancestorType . }
    OPTIONAL { ?ancestor gvp:broaderPreferred ?ancestorParent . }
  }
}"""
)
# Every preferred and alternate term of each record, with its language.
NAMES = (
    PREFIXES
    + """SELECT ?place ?name ?language ?preferred
WHERE {
  VALUES ?place { %s }
  { ?place xl:prefLabel ?term . BIND(true AS ?preferred) }
  UNION { ?place xl:altLabel ?term . BIND(false AS ?preferred) }
  ?term xl:literalForm ?name .
  OPTIONAL { ?term dct:language ?language . }
}"""
)


@dataclass(frozen=True, slots=True)
class Hit:
    """One reconciliation result: the TGN id, its name and the service's score."""

    id: str
    name: str | None = None
    score: float | None = None


@dataclass(frozen=True, slots=True)
class Term:
    """One of a record's names, with its language and whether it is preferred."""

    name: str
    language: str | None = None
    preferred: bool = False


def reconcile_params(reading: str) -> dict[str, str]:
    """Parameters for finding TGN places by one reading's name."""
    query = {"q0": {"query": reading, "type": "/tgn", "limit": LIMIT}}
    return {"queries": json.dumps(query)}


def records_params(ids: Iterable[str]) -> dict[str, str]:
    """Parameters for reading up to 50 records with their types, points and parents."""
    return {"query": RECORDS % _values(ids)}


def names_params(ids: Iterable[str]) -> dict[str, str]:
    """Parameters for reading every name of up to 50 records."""
    return {"query": NAMES % _values(ids)}


def parse_reconcile(status: int, body: bytes) -> tuple[LookupStatus, tuple[Hit, ...]]:
    outcome, data = _answer(status, body)
    answer = data.get("q0") if isinstance(data.get("q0"), dict) else {}
    results = answer.get("result")
    if outcome is None and not isinstance(results, list):
        outcome = LookupStatus.MALFORMED
    if outcome is not None:
        return outcome, ()
    hits = tuple(hit for item in results if (hit := _hit(item)) is not None)
    return (LookupStatus.SUCCESS if hits else LookupStatus.NO_MATCH), hits


def parse_records(status: int, body: bytes) -> tuple[LookupStatus, tuple[Place, ...]]:
    """Places from a records answer, each with its GVP name only until
    `with_names` adds the rest; an id TGN does not hold is skipped."""
    outcome, rows = _bindings(status, body)
    if outcome is not None:
        return outcome, ()
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        record = _tgn_id(row.get("place"))
        if record is not None:
            grouped.setdefault(record, []).append(row)
    places = tuple(
        place for record, found in grouped.items() if (place := _place(record, found)) is not None
    )
    return (LookupStatus.SUCCESS if places else LookupStatus.NO_MATCH), places


def parse_names(status: int, body: bytes) -> tuple[LookupStatus, dict[str, tuple[Term, ...]]]:
    outcome, rows = _bindings(status, body)
    if outcome is not None:
        return outcome, {}
    names: dict[str, list[Term]] = {}
    for row in rows:
        record, name = _tgn_id(row.get("place")), row.get("name")
        if record is not None and name:
            term = Term(name, row.get("language"), row.get("preferred") == "true")
            names.setdefault(record, []).append(term)
    found = {record: tuple(dict.fromkeys(terms)) for record, terms in names.items()}
    return (LookupStatus.SUCCESS if found else LookupStatus.NO_MATCH), found


def with_names(places: Iterable[Place], names: Mapping[str, Iterable[Term]]) -> tuple[Place, ...]:
    """The places with their names: an English preferred name when TGN has one,
    else the GVP name, then every other term, preferred terms first."""
    named = []
    for place in places:
        terms = sorted(
            names.get(place.record_id, ()),
            key=lambda term: (not term.preferred, term.language != ENGLISH, term.name.casefold()),
        )
        english = [term.name for term in terms if term.preferred and term.language == ENGLISH]
        name = english[0] if english else place.name
        others = [place.name, *(term.name for term in terms)]
        country = place.country
        if country is not None and country.id == place.record_id:
            country = Ref(place.record_id, name)  # a nation names itself as it is named
        named.append(
            replace(
                place,
                name=name,
                names=tuple(dict.fromkeys(other for other in others if other != name)),
                country=country,
            )
        )
    return tuple(named)


def _values(ids: Iterable[str]) -> str:
    ids = list(dict.fromkeys(ids))
    if not ids or len(ids) > MAX_IDS:
        raise ValueError(f"a TGN query reads 1 to {MAX_IDS} records, not {len(ids)}")
    if not all(isinstance(record, str) and RECORD_ID.fullmatch(record) for record in ids):
        raise ValueError("a TGN id is digits only")
    return " ".join(f"tgn:{record}" for record in ids)


def _answer(status: int, body: bytes) -> tuple[LookupStatus | None, dict]:
    """The outcome of an answer that cannot be read, else None and its JSON."""
    if status != 200:
        return STATUSES.get(status, LookupStatus.PROVIDER), {}
    if not body.strip():
        return LookupStatus.EMPTY, {}
    try:
        data = json.loads(body)
    except ValueError:
        return LookupStatus.MALFORMED, {}
    if not isinstance(data, dict):
        return LookupStatus.MALFORMED, {}
    return None, data


def _bindings(status: int, body: bytes) -> tuple[LookupStatus | None, list[dict[str, str]]]:
    """A SPARQL answer's rows as variable-to-value maps."""
    outcome, data = _answer(status, body)
    results = data.get("results") if isinstance(data.get("results"), dict) else {}
    bindings = results.get("bindings")
    if outcome is None and not isinstance(bindings, list):
        outcome = LookupStatus.MALFORMED
    if outcome is not None:
        return outcome, []
    rows = []
    for binding in bindings:
        if isinstance(binding, dict):
            rows.append(
                {
                    variable: cell["value"]
                    for variable, cell in binding.items()
                    if isinstance(cell, dict) and isinstance(cell.get("value"), str)
                }
            )
    return None, rows


def _hit(item: object) -> Hit | None:
    if not isinstance(item, dict):
        return None
    identifier = item.get("id")
    match = re.fullmatch(r"tgn/([0-9]{1,10})", identifier) if isinstance(identifier, str) else None
    if match is None:
        return None
    name = item.get("name") if isinstance(item.get("name"), str) else None
    score = item.get("score")
    return Hit(match[1], name, float(score) if isinstance(score, int | float) else None)


def _tgn_id(uri: str | None) -> str | None:
    if uri and uri.startswith(TGN) and RECORD_ID.fullmatch(uri[len(TGN) :]):
        return uri[len(TGN) :]
    return None


def _place(record: str, rows: list[dict[str, str]]) -> Place | None:
    name = next((row["name"] for row in rows if row.get("name")), None)
    if name is None:
        return None
    preferred = next((row["preferredType"] for row in rows if row.get("preferredType")), None)
    types = {row["type"]: row.get("typeName") for row in rows if row.get("type")}
    kinds = tuple(
        Ref(_aat(uri), types[uri])
        for uri in sorted(types, key=lambda uri: (uri != preferred, (types[uri] or "").casefold()))
    )
    ancestors: dict[str, tuple[str, str | None, str | None]] = {}
    for row in rows:
        ancestor = _tgn_id(row.get("ancestor"))
        if ancestor is not None and row.get("ancestorName"):
            ancestors[ancestor] = (
                row["ancestorName"],
                row.get("ancestorType"),
                _tgn_id(row.get("ancestorParent")),
            )
    chain, step = [], _tgn_id(next((row["parent"] for row in rows if row.get("parent")), None))
    while step in ancestors and step not in chain:
        chain.append(step)
        step = ancestors[step][2]
    country, parents = None, tuple(Ref(ancestor, ancestors[ancestor][0]) for ancestor in chain)
    if preferred == NATIONS:
        country, parents = Ref(record, name), ()
    else:
        for depth, ancestor in enumerate(chain):
            if ancestors[ancestor][1] == NATIONS:
                country, parents = Ref(ancestor, ancestors[ancestor][0]), parents[:depth]
                break
    point = next(filter(None, map(_point, rows)), None)
    return Place(
        source=SOURCE,
        record_id=record,
        name=name,
        kinds=kinds,
        country=country,
        parents=parents,
        point=point,
        license=LICENSE,
    )


def _point(row: dict[str, str]) -> tuple[float, float] | None:
    try:
        latitude, longitude = float(row["lat"]), float(row["long"])
    except (KeyError, ValueError):
        return None
    if -90 <= latitude <= 90 and -180 <= longitude <= 180:
        return latitude, longitude
    return None


def _aat(uri: str) -> str:
    return "aat:" + uri[len(AAT) :] if uri.startswith(AAT) else uri
