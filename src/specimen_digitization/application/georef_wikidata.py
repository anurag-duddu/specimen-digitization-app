"""Tier 1: Wikidata's Action API requests and answers (GEO.md 2).

The module builds `wbsearchentities` and `wbgetentities` parameters and reads the
answers into `Place` records, with one `LookupStatus` per answer. It sends
nothing: the tool sends each request with retries and records it as a sub-call
(G23). Every search string comes from PLAN 4.8's filter (S4's `place_request_text`),
item ids come from Wikidata's own answers, and the fixed parameters are reviewed
constants that carry no label text.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

from .domain import LookupStatus
from .georef_places import Place, Ref

SOURCE = "wikidata"
API = "https://www.wikidata.org/w/api.php"
LICENSE = "CC0-1.0"
LANGUAGES = ("en", "es", "mul")
# A place's name is its English label, else the multilingual one, else Spanish.
NAME_ORDER = ("en", "mul", "es")
MAX_IDS = 50  # wbgetentities reads at most 50 items a request
EARTH = "http://www.wikidata.org/entity/Q2"
STATUSES = {
    401: LookupStatus.AUTHENTICATION,
    403: LookupStatus.AUTHORIZATION,  # Wikimedia refuses a missing User-Agent
    429: LookupStatus.RATE_LIMITED,
}
RATE_ERRORS = frozenset({"maxlag", "ratelimited"})
STARTS = ("P571", "P580")
ENDS = ("P576", "P582")
RANKS = {"preferred": 0, "normal": 1}  # deprecated statements are ignored


@dataclass(frozen=True, slots=True)
class Hit:
    """One search result: the item, its label and description, and the label or
    alias text that matched."""

    id: str
    label: str | None = None
    description: str | None = None
    matched: str | None = None
    match_type: str | None = None


def search_params(reading: str, language: str = "en", limit: int = 7) -> dict[str, str]:
    """Parameters for finding items by one reading's name."""
    return {
        "action": "wbsearchentities",
        "search": reading,
        "language": language,
        "uselang": language,
        "type": "item",
        "limit": str(limit),
        "format": "json",
    }


def entities_params(ids: Iterable[str]) -> dict[str, str]:
    """Parameters for reading up to 50 items with their names and statements."""
    return _get(ids, "labels|aliases|descriptions|claims", LANGUAGES)


def labels_params(ids: Iterable[str]) -> dict[str, str]:
    """Parameters for naming the items that statements point to."""
    return _get(ids, "labels", ("en", "mul"))


def parse_search(status: int, body: bytes) -> tuple[LookupStatus, tuple[Hit, ...]]:
    outcome, data = _answer(status, body)
    items = data.get("search")
    if outcome is None and not isinstance(items, list):
        outcome = LookupStatus.MALFORMED
    if outcome is not None:
        return outcome, ()
    hits = tuple(_hit(item) for item in items if isinstance(item, dict) and item.get("id"))
    return (LookupStatus.SUCCESS if hits else LookupStatus.NO_MATCH), hits


def parse_entities(status: int, body: bytes) -> tuple[LookupStatus, tuple[Place, ...]]:
    """Places from a `wbgetentities` answer; an item reported missing is skipped.
    Their references carry ids only until `name_refs` names them."""
    outcome, entities = _entities(status, body)
    if outcome is not None:
        return outcome, ()
    places = tuple(
        _place(entity)
        for entity in entities.values()
        if isinstance(entity, dict) and entity.get("id") and "missing" not in entity
    )
    return (LookupStatus.SUCCESS if places else LookupStatus.NO_MATCH), places


def parse_labels(status: int, body: bytes) -> tuple[LookupStatus, dict[str, str]]:
    outcome, entities = _entities(status, body)
    if outcome is not None:
        return outcome, {}
    labels = {
        item: name
        for item, entity in entities.items()
        if isinstance(entity, dict) and (name := _label(entity.get("labels")))
    }
    return (LookupStatus.SUCCESS if labels else LookupStatus.NO_MATCH), labels


def referenced_ids(places: Iterable[Place]) -> set[str]:
    """The ids the places point to, less those the places already name."""
    places = tuple(places)
    return {ref.id for place in places for ref in _refs(place)} - {
        place.record_id for place in places
    }


def name_refs(places: Iterable[Place], labels: Mapping[str, str]) -> tuple[Place, ...]:
    """The places with every reference named, from `labels` or from the places."""
    places = tuple(places)
    names = {place.record_id: place.name for place in places} | dict(labels)

    def named(refs: tuple[Ref, ...]) -> tuple[Ref, ...]:
        return tuple(replace(ref, name=names.get(ref.id, ref.name)) for ref in refs)

    return tuple(
        replace(
            place,
            kinds=named(place.kinds),
            country=named((place.country,))[0] if place.country else None,
            parents=named(place.parents),
            replaces=named(place.replaces),
            replaced_by=named(place.replaced_by),
        )
        for place in places
    )


def _get(ids: Iterable[str], props: str, languages: tuple[str, ...]) -> dict[str, str]:
    ids = list(ids)
    if not ids or len(ids) > MAX_IDS:
        raise ValueError(f"wbgetentities reads 1 to {MAX_IDS} items, not {len(ids)}")
    return {
        "action": "wbgetentities",
        "ids": "|".join(ids),
        "props": props,
        "languages": "|".join(languages),
        "format": "json",
    }


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
    if "error" in data:
        error = data["error"]
        code = error.get("code") if isinstance(error, dict) else None
        if code in RATE_ERRORS:
            return LookupStatus.RATE_LIMITED, {}
        if code == "no-such-entity":
            return LookupStatus.NO_MATCH, {}
        return LookupStatus.PROVIDER, {}
    return None, data


def _entities(status: int, body: bytes) -> tuple[LookupStatus | None, dict]:
    outcome, data = _answer(status, body)
    entities = data.get("entities")
    if outcome is None and not isinstance(entities, dict):
        outcome = LookupStatus.MALFORMED
    return outcome, entities if outcome is None else {}


def _hit(item: dict) -> Hit:
    match = item.get("match") if isinstance(item.get("match"), dict) else {}
    return Hit(
        id=item["id"],
        label=_text(item.get("label")),
        description=_text(item.get("description")),
        matched=_text(match.get("text")),
        match_type=_text(match.get("type")),
    )


def _place(entity: dict) -> Place:
    claims = entity.get("claims") if isinstance(entity.get("claims"), dict) else {}
    labels = entity.get("labels") if isinstance(entity.get("labels"), dict) else {}
    aliases = entity.get("aliases") if isinstance(entity.get("aliases"), dict) else {}
    name = _label(labels) or entity["id"]
    others = [
        text
        for language in NAME_ORDER
        for text in [_value(labels.get(language)), *map(_value, aliases.get(language) or [])]
    ]
    descriptions = (
        entity.get("descriptions") if isinstance(entity.get("descriptions"), dict) else {}
    )
    starts = [date for prop in STARTS for date in map(_time, _values(claims, prop)) if date]
    ends = [date for prop in ENDS for date in map(_time, _values(claims, prop)) if date]
    countries = _refs_of(claims, "P17")
    codes = [value for value in _values(claims, "P297") if isinstance(value, str)]
    return Place(
        source=SOURCE,
        record_id=entity["id"],
        name=name,
        names=tuple(dict.fromkeys(text for text in others if text and text != name)),
        description=_value(descriptions.get("en")),
        kinds=_refs_of(claims, "P31"),
        country=countries[0] if countries else None,
        iso_code=codes[0] if codes else None,
        parents=_refs_of(claims, "P131"),
        point=next(filter(None, map(_point, _values(claims, "P625"))), None),
        valid_from=min(starts) if starts else None,
        valid_to=max(ends) if ends else None,
        replaces=_refs_of(claims, "P1365"),
        replaced_by=_refs_of(claims, "P1366"),
        license=LICENSE,
    )


def _statements(claims: dict, prop: str) -> list[dict]:
    """A property's statements with a value, preferred first, deprecated ignored."""
    kept = [
        statement
        for statement in claims.get(prop) or []
        if isinstance(statement, dict)
        and statement.get("rank") in RANKS
        and isinstance(statement.get("mainsnak"), dict)
        and isinstance(statement["mainsnak"].get("datavalue"), dict)
    ]
    return sorted(kept, key=lambda statement: RANKS[statement["rank"]])


def _values(claims: dict, prop: str) -> list[object]:
    return [
        statement["mainsnak"]["datavalue"].get("value") for statement in _statements(claims, prop)
    ]


def _refs_of(claims: dict, prop: str) -> tuple[Ref, ...]:
    """References with the start and end qualifiers of their statements."""
    refs = []
    for statement in _statements(claims, prop):
        value = statement["mainsnak"]["datavalue"].get("value")
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            qualifiers = (
                statement.get("qualifiers") if isinstance(statement.get("qualifiers"), dict) else {}
            )
            refs.append(
                Ref(
                    value["id"],
                    start=_qualifier_time(qualifiers, "P580"),
                    end=_qualifier_time(qualifiers, "P582"),
                )
            )
    return tuple(refs)


def _qualifier_time(qualifiers: dict, prop: str) -> str | None:
    for snak in qualifiers.get(prop) or []:
        datavalue = snak.get("datavalue") if isinstance(snak, dict) else None
        if isinstance(datavalue, dict) and (date := _time(datavalue.get("value"))):
            return date
    return None


def _time(value: object) -> str | None:
    """A Wikidata time at its precision: day, month or year; a coarser time
    keeps the year Wikidata stores."""
    if not isinstance(value, dict):
        return None
    time, precision = value.get("time"), value.get("precision")
    if not isinstance(time, str) or not isinstance(precision, int):
        return None
    sign = "-" if time.startswith("-") else ""
    parts = time.lstrip("+-").split("T")[0].split("-")
    if len(parts) != 3:
        return None
    year, month, day = parts
    if precision >= 11:
        return f"{sign}{year}-{month}-{day}"
    if precision == 10:
        return f"{sign}{year}-{month}"
    return f"{sign}{year}"


def _point(value: object) -> tuple[float, float] | None:
    """A point on Earth; coordinates on another globe are not places here."""
    if not isinstance(value, dict) or value.get("globe") != EARTH:
        return None
    latitude, longitude = value.get("latitude"), value.get("longitude")
    if isinstance(latitude, int | float) and isinstance(longitude, int | float):
        return float(latitude), float(longitude)
    return None


def _refs(place: Place) -> tuple[Ref, ...]:
    country = (place.country,) if place.country else ()
    return (*place.kinds, *country, *place.parents, *place.replaces, *place.replaced_by)


def _label(labels: object) -> str | None:
    if not isinstance(labels, dict):
        return None
    return next(filter(None, (_value(labels.get(language)) for language in NAME_ORDER)), None)


def _value(entry: object) -> str | None:
    return _text(entry.get("value")) if isinstance(entry, dict) else None


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
