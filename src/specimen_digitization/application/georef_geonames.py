"""Tier 1: the GeoNames country dumps, read from their pinned copies (GEO.md 4).

A dump is the verified bytes of one pinned file (`georef_datasets`): nothing is
sent to GeoNames (PLAN 4.8). Rows stay as the dump gives them until a search
returns them as `Place` records. Names compare by section 1's keys: `find`
returns the places a reading names exactly and, only when there are none and the
reading is a full name, those one letter off (G34, the coordinator's reading).
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field

from .domain import LookupStatus
from .georef_locality import comparison_key, is_full_name, letters_apart
from .georef_places import Place, Ref

SOURCE = "geonames"
LICENSE = "CC BY 4.0"
COLUMNS = 19  # geonameid ... modification date, per the dump's readme
ADMIN_CODES = ("ADM1", "ADM2", "ADM3", "ADM4")


@dataclass(frozen=True, slots=True)
class Matches:
    """Places a reading names: `exact` by key, else `near`, one letter off."""

    exact: tuple[Place, ...] = ()
    near: tuple[Place, ...] = ()


@dataclass(slots=True)
class Dump:
    """One country's rows, indexed by the key of every name a row carries."""

    country: str
    rows: list[list[str]]
    keys: dict[str, set[int]] = field(default_factory=dict)
    admins: dict[tuple[str, ...], int] = field(default_factory=dict)

    def place(self, index: int) -> Place:
        row = self.rows[index]
        names = [row[1], row[2], *filter(None, row[3].split(","))]
        codes = (row[10], row[11], row[12], row[13])
        parents = []
        for depth in (3, 2, 1):  # nearest first: ADM3, ADM2, ADM1
            parent = self.admins.get(codes[:depth]) if all(codes[:depth]) else None
            if parent is not None and parent != index:
                parents.append(Ref(self.rows[parent][0], self.rows[parent][1]))
        country = self.admins.get(("PCLI",))
        return Place(
            source=SOURCE,
            record_id=row[0],
            name=row[1],
            names=tuple(dict.fromkeys(n for n in names if n and n != row[1])),
            kinds=(Ref(f"{row[6]}.{row[7]}"),),
            country=Ref(self.country, self.rows[country][1] if country is not None else None),
            iso_code=self.country if row[7].startswith("PCL") else None,
            parents=tuple(parents),
            point=(float(row[4]), float(row[5])),
            license=LICENSE,
        )


def read_dump(country: str, data: bytes) -> tuple[LookupStatus, Dump | None]:
    """Index a pinned dump's `{country}.txt`; the caller has verified the bytes."""
    if not data:
        return LookupStatus.EMPTY, None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            text = archive.read(f"{country}.txt").decode("utf-8")
    except (zipfile.BadZipFile, KeyError, UnicodeDecodeError):
        return LookupStatus.MALFORMED, None
    rows = [line.split("\t") for line in text.splitlines() if line]
    if not rows or any(len(row) != COLUMNS for row in rows):
        return LookupStatus.MALFORMED, None
    dump = Dump(country=country, rows=rows)
    for index, row in enumerate(rows):
        for name in {row[1], row[2], *filter(None, row[3].split(","))}:
            key = comparison_key(name)
            if key:
                dump.keys.setdefault(key, set()).add(index)
        code = row[7]
        if code.startswith("PCL"):
            dump.admins[("PCLI",)] = index
        elif code in ADMIN_CODES:
            depth = ADMIN_CODES.index(code) + 1
            dump.admins[(row[10], row[11], row[12], row[13])[:depth]] = index
    return LookupStatus.SUCCESS, dump


def find(dump: Dump, reading: str, kinds: Iterable[str] | None = None) -> Matches:
    """Places whose names key as the reading does; when there are none and the
    reading is a full name, places with a full name one letter off (G34).
    `kinds` limits the places to feature classes ("A") or class and code ("A.ADM2")."""
    wanted = set(kinds) if kinds is not None else None
    key = comparison_key(reading)

    def allowed(index: int) -> bool:
        row = dump.rows[index]
        return wanted is None or row[6] in wanted or f"{row[6]}.{row[7]}" in wanted

    exact = sorted(index for index in dump.keys.get(key, ()) if allowed(index))
    if exact or not key or not is_full_name(reading):
        return Matches(exact=tuple(map(dump.place, exact)))
    near = set()
    for other, indexes in dump.keys.items():
        if abs(len(other) - len(key)) <= 1 and letters_apart(key, other) == 1:
            near.update(
                index
                for index in indexes
                if allowed(index) and _full_name_keyed(dump, index, other)
            )
    return Matches(near=tuple(map(dump.place, sorted(near))))


def _full_name_keyed(dump: Dump, index: int, key: str) -> bool:
    """True when one of the row's full names (never a code or an abbreviation)
    has the key; G34's gate compares full names only."""
    row = dump.rows[index]
    names = [row[1], row[2], *filter(None, row[3].split(","))]
    return any(is_full_name(name) and comparison_key(name) == key for name in names)
