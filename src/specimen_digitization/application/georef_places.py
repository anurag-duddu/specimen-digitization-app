"""The record every tier-1 gazetteer answers with (GEO.md 2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Ref:
    """An item a place points to: its id, the name its source gives it, and the
    start and end the source states for that link."""

    id: str
    name: str | None = None
    start: str | None = None
    end: str | None = None


@dataclass(frozen=True, slots=True)
class Place:
    """One place as its gazetteer gives it. Dates keep the source's precision
    (day, month or year); `point` is latitude, longitude; `iso_code` is set only
    when the place is itself a country."""

    source: str
    record_id: str
    name: str
    names: tuple[str, ...] = ()
    description: str | None = None
    kinds: tuple[Ref, ...] = ()
    country: Ref | None = None
    iso_code: str | None = None
    parents: tuple[Ref, ...] = ()
    point: tuple[float, float] | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    replaces: tuple[Ref, ...] = ()
    replaced_by: tuple[Ref, ...] = ()
    license: str | None = None
