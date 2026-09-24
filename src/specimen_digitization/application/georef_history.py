"""History: was a place in use on the label's date, and what replaced it (GEO.md 5).

Dates are intervals at the precision written: "1946" is the whole year, "1946-09"
the whole month (G24). A place's start and end are intervals too, at the
precision its source states. A place is in use on a label date only when it is
certainly in use throughout it. A name used after its place ended is a finding
with the gap in days; no tolerance widens the dates while D5 is held.
"""

from __future__ import annotations

import calendar
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from .georef_places import Place, Ref


@dataclass(frozen=True, slots=True)
class Use:
    """How a place stands on a label date: "in_use", "ended" (with the days
    from its latest possible end to the label's earliest day), "not_started",
    "partly" (in use for only part of the label's interval) or "undated"."""

    state: str
    gap_days: int | None = None


def interval(written: str) -> tuple[date, date]:
    """The first and last day an ISO date written to a year, a month or a day
    can mean."""
    parts = [int(part) for part in written.split("-")]
    year = parts[0]
    if len(parts) == 1:
        return date(year, 1, 1), date(year, 12, 31)
    month = parts[1]
    if len(parts) == 2:
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    return date(year, month, parts[2]), date(year, month, parts[2])


def use_on(place: Place, written: str) -> Use:
    """Whether the place is certainly in use throughout the label's date."""
    if place.valid_from is None and place.valid_to is None:
        return Use("undated")
    first, last = interval(written)
    if place.valid_to is not None:
        end_earliest, end_latest = interval(place.valid_to)
        if end_latest < first:
            return Use("ended", gap_days=(first - end_latest).days)
    if place.valid_from is not None:
        start_earliest, start_latest = interval(place.valid_from)
        if start_earliest > last:
            return Use("not_started")
    started = place.valid_from is None or interval(place.valid_from)[1] <= first
    lasting = place.valid_to is None or interval(place.valid_to)[0] >= last
    return Use("in_use") if started and lasting else Use("partly")


def role(place: Place) -> str:
    """ "historical" for a place its source says ended, else "modern"."""
    return "historical" if place.valid_to is not None else "modern"


def parents_on(place: Place, written: str) -> tuple[Ref, ...]:
    """The units a place lay in on the label's date: those whose link has no
    stated start or end, or whose stated start and end cover the whole date."""
    first, last = interval(written)
    return tuple(
        ref
        for ref in place.parents
        if (ref.start is None or interval(ref.start)[1] <= first)
        and (ref.end is None or interval(ref.end)[0] >= last)
    )


def modern_successors(place: Place, places: Mapping[str, Place]) -> tuple[Ref, ...]:
    """The places that replaced this one, followed through `places` until a
    successor has no end; a successor `places` does not hold is kept as is."""
    found: list[Ref] = []
    seen = {place.record_id}
    pending = list(place.replaced_by)
    while pending:
        ref = pending.pop(0)
        if ref.id in seen:
            continue
        seen.add(ref.id)
        successor = places.get(ref.id)
        if successor is not None and successor.valid_to is not None and successor.replaced_by:
            pending.extend(successor.replaced_by)
        else:
            found.append(ref)
    return tuple(found)
