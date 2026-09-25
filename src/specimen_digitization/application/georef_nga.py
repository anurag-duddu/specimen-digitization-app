"""Tier 1: the NGA GEOnet Names Server's requests and answers (GEO.md 8).

The module builds requests to GNS's anonymous ArcGIS REST service and reads the
answers into `Place` records, with one `LookupStatus` per answer. It sends
nothing: the tool sends each request and records it as a sub-call. A name search
carries one reading's name as S4's place-request filter returns it (PLAN 4.8),
quoted as a literal in a fixed where clause; the other requests carry GNS
feature ids or first-order codes only.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import replace

from .domain import LookupStatus
from .georef_places import Place, Ref

SOURCE = "nga"
SERVICE = "https://geonames.nga.mil/geon-ags/rest/services/RESEARCH/GIS_OUTPUT/MapServer"
NAMES = SERVICE + "/0/query"  # one row per name of a feature
UNITS = SERVICE + "/1/query"  # the first-order administrative units
CREDIT = "NGA GEOnet Names Server"
LICENSE = None  # NGA's pages state no license (#94, S33); G35 stores its coordinates, credited
FIELDS = "ufi,uni,full_name,full_nm_nd,nt,fc,desig_cd,adm1,lat_dd,long_dd,term_dt_f,name_rank"
# A feature's name is its first name in this order of GNS name types: approved,
# conventional, approved non-authoritative, approved transitional, provisional,
# anglicized, then variant; non-Roman scripts come last.
NAME_TYPES = ("N", "C", "D", "T", "P", "VA", "V")
MAX_IDS = 50
MAX_NAME = 200
FEATURE_ID = re.compile(r"-?[0-9]{1,10}")
UNIT_CODE = re.compile(r"[A-Z]{2}-[A-Z0-9]{1,3}")
STATUSES = {
    401: LookupStatus.AUTHENTICATION,
    403: LookupStatus.AUTHORIZATION,
    429: LookupStatus.RATE_LIMITED,
}
# ArcGIS reports its own errors inside an HTTP 200 answer.
ERRORS = {
    400: LookupStatus.MALFORMED,  # a query the service cannot run: an adapter defect
    401: LookupStatus.AUTHENTICATION,
    498: LookupStatus.AUTHENTICATION,  # invalid token
    499: LookupStatus.AUTHENTICATION,  # token required
    403: LookupStatus.AUTHORIZATION,
    429: LookupStatus.RATE_LIMITED,
}


def search_params(reading: str) -> dict[str, str]:
    """Parameters for the features one reading's name names exactly, case and
    diacritics aside."""
    literal = _literal(reading)
    return {
        "where": f"UPPER(full_name) = UPPER({literal}) OR UPPER(full_nm_nd) = UPPER({literal})",
        "outFields": FIELDS,
        "returnGeometry": "false",
        "orderByFields": "ufi,uni",
        "f": "json",
    }


def features_params(ids: Iterable[str]) -> dict[str, str]:
    """Parameters for every name of up to 50 features."""
    ids = _checked(ids, FEATURE_ID, "a GNS feature id is an integer")
    return {
        "where": f"ufi IN ({', '.join(ids)})",
        "outFields": FIELDS,
        "returnGeometry": "false",
        "orderByFields": "ufi,uni",
        "f": "json",
    }


def units_params(codes: Iterable[str]) -> dict[str, str]:
    """Parameters for the names of up to 50 first-order units."""
    codes = _checked(codes, UNIT_CODE, "a first-order code reads like PH-DAV")
    quoted = [f"'{code}'" for code in codes]
    return {
        "where": f"adm1 IN ({', '.join(quoted)})",
        "outFields": "adm1,adm1_name",
        "orderByFields": "adm1",
        "f": "json",
    }


def parse_search(status: int, body: bytes) -> tuple[LookupStatus, tuple[str, ...]]:
    """The ids of the current features a name search found, in the answer's order."""
    outcome, rows, more = _rows(status, body)
    if outcome is None and more:
        outcome = LookupStatus.AMBIGUOUS  # more features share the name than one answer lists
    if outcome is not None:
        return outcome, ()
    ids = tuple(dict.fromkeys(row["ufi"] for row in rows if _current(row)))
    return (LookupStatus.SUCCESS if ids else LookupStatus.NO_MATCH), ids


def parse_features(status: int, body: bytes) -> tuple[LookupStatus, tuple[Place, ...]]:
    """Places from a features answer, their first-order units unnamed until
    `name_units` names them; features GNS marks terminated are skipped."""
    outcome, rows, more = _rows(status, body)
    if outcome is None and more:
        outcome = LookupStatus.MALFORMED  # the adapter asked for more than one answer holds
    if outcome is not None:
        return outcome, ()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        if _current(row):
            grouped.setdefault(row["ufi"], []).append(row)
    places = tuple(place for ufi, found in grouped.items() if (place := _place(ufi, found)))
    return (LookupStatus.SUCCESS if places else LookupStatus.NO_MATCH), places


def parse_units(status: int, body: bytes) -> tuple[LookupStatus, dict[str, str]]:
    outcome, rows, _ = _rows(status, body)
    if outcome is not None:
        return outcome, {}
    units = {
        row["adm1"]: row["adm1_name"]
        for row in rows
        if isinstance(row.get("adm1"), str) and isinstance(row.get("adm1_name"), str)
    }
    return (LookupStatus.SUCCESS if units else LookupStatus.NO_MATCH), units


def unit_codes(places: Iterable[Place]) -> set[str]:
    """The first-order codes the places lie in, which `units_params` names."""
    return {parent.id for place in places for parent in place.parents}


def name_units(places: Iterable[Place], units: Mapping[str, str]) -> tuple[Place, ...]:
    """The places with their first-order units named."""
    return tuple(
        replace(
            place,
            parents=tuple(replace(ref, name=units.get(ref.id, ref.name)) for ref in place.parents),
        )
        for place in places
    )


def _literal(reading: str) -> str:
    """One name as a quoted where-clause literal, its quotes doubled."""
    if (
        not isinstance(reading, str)
        or not reading.strip()
        or len(reading) > MAX_NAME
        or any(unicodedata.category(character).startswith("C") for character in reading)
    ):
        raise ValueError("a GNS name search takes one printable name")
    return "'" + reading.replace("'", "''") + "'"


def _checked(values: Iterable[str], pattern: re.Pattern[str], message: str) -> list[str]:
    values = list(dict.fromkeys(values))
    if not values or len(values) > MAX_IDS:
        raise ValueError(f"a GNS query reads 1 to {MAX_IDS} values, not {len(values)}")
    if not all(isinstance(value, str) and pattern.fullmatch(value) for value in values):
        raise ValueError(message)
    return values


def _rows(status: int, body: bytes) -> tuple[LookupStatus | None, list[dict], bool]:
    """An answer's rows and whether the service held more back, or its outcome."""
    if status != 200:
        return STATUSES.get(status, LookupStatus.PROVIDER), [], False
    if not body.strip():
        return LookupStatus.EMPTY, [], False
    try:
        data = json.loads(body)
    except ValueError:
        return LookupStatus.MALFORMED, [], False
    if not isinstance(data, dict):
        return LookupStatus.MALFORMED, [], False
    if "error" in data:
        error = data["error"]
        code = error.get("code") if isinstance(error, dict) else None
        return ERRORS.get(code, LookupStatus.PROVIDER), [], False
    features = data.get("features")
    if not isinstance(features, list):
        return LookupStatus.MALFORMED, [], False
    rows = []
    for feature in features:
        attributes = feature.get("attributes") if isinstance(feature, dict) else None
        if isinstance(attributes, dict):
            row = dict(attributes)
            ufi = row.get("ufi")
            row["ufi"] = str(ufi) if isinstance(ufi, int) and not isinstance(ufi, bool) else None
            rows.append(row)
    return None, rows, data.get("exceededTransferLimit") is True


def _current(row: dict) -> bool:
    """A row of a feature GNS has not marked terminated."""
    return isinstance(row.get("ufi"), str) and row.get("term_dt_f") is None


def _place(ufi: str, rows: list[dict]) -> Place | None:
    named = sorted(
        (row for row in rows if isinstance(row.get("full_name"), str) and row["full_name"]),
        key=lambda row: (
            NAME_TYPES.index(row.get("nt")) if row.get("nt") in NAME_TYPES else len(NAME_TYPES),
            row["name_rank"] if isinstance(row.get("name_rank"), int) else 999,
            str(row.get("uni")),
        ),
    )
    if not named:
        return None
    first = named[0]
    names = [text for row in named for text in (row["full_name"], row.get("full_nm_nd"))]
    unit = first.get("adm1") if isinstance(first.get("adm1"), str) else ""
    country = unit[:2] if UNIT_CODE.fullmatch(unit) else None
    designation = first.get("desig_cd") if isinstance(first.get("desig_cd"), str) else ""
    # A first-order unit's own code is its own; a country-wide code ("PH-000") names no unit.
    in_unit = (
        country is not None and not unit.endswith("-000") and not designation.startswith("ADM1")
    )
    return Place(
        source=SOURCE,
        record_id=ufi,
        name=first["full_name"],
        names=tuple(dict.fromkeys(text for text in names if text and text != first["full_name"])),
        kinds=(Ref(f"{first.get('fc')}.{designation}"),),
        country=Ref(country) if country else None,
        iso_code=country if designation.startswith("PCL") else None,
        parents=(Ref(unit),) if in_unit else (),
        point=_point(first),
        license=LICENSE,
    )


def _point(row: dict) -> tuple[float, float] | None:
    latitude, longitude = row.get("lat_dd"), row.get("long_dd")
    if not isinstance(latitude, int | float) or not isinstance(longitude, int | float):
        return None
    if -90 <= latitude <= 90 and -180 <= longitude <= 180:
        return float(latitude), float(longitude)
    return None
