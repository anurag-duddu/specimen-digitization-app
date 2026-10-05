"""Curated entries: places and itineraries only the museum's own records know (GEO.md 6).

S8 drafts each entry with its sources. The Insects collection manager, or a
curator they name, confirms it (G36). An entry becomes confirmed only in a pull
request that cites the owner's recorded confirmation (PLAN 4.8), and the
repository then records the confirming role and date, never a name. Until then
an entry is a hypothesis: it is shown with its sources and settles nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from .georef_history import interval
from .georef_locality import comparison_key, fold


@dataclass(frozen=True, slots=True)
class Confirmation:
    """Who confirmed an entry, by role, when, and where the owner recorded it;
    never a personal name (G36)."""

    role: str
    date: str
    record: str

    def __post_init__(self) -> None:
        if not (self.role and self.record) or len(self.date) != 10:
            raise ValueError("a confirmation needs a role, an ISO date and the owner's record")


@dataclass(frozen=True, slots=True)
class CuratedPlace:
    """A name no gazetteer holds, with the modern place S8 proposes for it."""

    id: str
    country: str
    names: tuple[str, ...]
    within: tuple[str, ...]
    proposed: str
    proposed_ids: tuple[str, ...]
    sources: tuple[str, ...]
    confirmation: Confirmation | None = None


@dataclass(frozen=True, slots=True)
class Camp:
    name: str
    elevation_ft: int | None
    start: str
    end: str
    slope: str | None = None


@dataclass(frozen=True, slots=True)
class Itinerary:
    """An expedition's dated camps on one mountain, from a published narrative."""

    id: str
    place: str
    collectors: tuple[str, ...]
    camps: tuple[Camp, ...]
    sources: tuple[str, ...]
    confirmation: Confirmation | None = None


HOOGSTRAAL = (
    "Hoogstraal, H. (1951). Philippine Zoological Expedition 1946-1947: Narrative and "
    "Itinerary. Fieldiana: Zoology 33(1): 1-86"
)

PLACES = (
    CuratedPlace(
        id="PH/Davao/Mount McKinley",
        country="PH",
        names=("Mount McKinley", "Mt. McKinley"),
        within=("Davao", "Mindanao"),
        proposed="Mount Talomo",
        proposed_ids=("wikidata:Q31472786", "geonames:1683778"),
        sources=(
            f"{HOOGSTRAAL}, p. 40: the names Mount McKinley and Mount Washington appear on no map "
            "and came from a US Army intelligence report",
            f"{HOOGSTRAAL}, pp. 23, 41-42: camps on the east slope, reached from Toril on the "
            "Davao-Cotabato road",
            "Hymenoptera Online: a 'Mount McKinley, 6800 ft' label placed 2.3 km from Mount "
            "Talomo's summit, 'from Google Earth'",
        ),
    ),
)

ITINERARIES = (
    Itinerary(
        id="Philippine Zoological Expedition 1946-1947/Mount McKinley",
        place="PH/Davao/Mount McKinley",
        collectors=("Hoogstraal", "Werner"),
        camps=(
            Camp("base camp", 3300, "1946-08-09", "1946-10-06"),
            Camp("valley camp", 2800, "1946-08-17", "1946-08-23"),
            Camp("5,200-foot camp", 5200, "1946-08-18", "1946-09-01"),
            Camp("5,200-foot camp", 5200, "1946-09-28", "1946-10-02"),
            Camp("6,400-foot camp", 6400, "1946-09-01", "1946-09-12"),
            Camp("7,200-foot camp", 7200, "1946-09-09", "1946-09-30"),
        ),
        sources=(f"{HOOGSTRAAL}, pp. 23, 41-42",),
    ),
    Itinerary(
        id="Philippine Zoological Expedition 1946-1947/Mount Apo",
        place="wikidata:Q455963",
        collectors=("Hoogstraal",),
        camps=(
            Camp("Todaya village", 2800, "1946-10-17", "1946-11-23"),
            Camp("Lake Linau", 7800, "1946-10-27", "1946-11-05", slope="north"),
            Camp("Meran", 6000, "1946-11-03", "1946-11-10", slope="east"),
            Camp("Baclayan", 6500, "1946-11-09", "1946-11-17", slope="east"),
            Camp("Baclayan River fumarole", 7700, "1946-11-12", "1946-11-18", slope="east"),
            Camp("Crater Lake", 9000, "1946-11-14", "1946-11-17"),
            Camp("Mainit", 4300, "1946-11-17", "1946-11-21", slope="east"),
        ),
        sources=(f"{HOOGSTRAAL}, p. 24",),
    ),
)


def settles(entry: CuratedPlace | Itinerary) -> bool:
    """Only a confirmed entry settles a field (G36)."""
    return entry.confirmation is not None


def curated_place(country: str, written: str) -> CuratedPlace | None:
    """The curated entry for a name as a label writes it, confirmed or not."""
    key = comparison_key(written)
    for entry in PLACES:
        if entry.country == country and key in {comparison_key(name) for name in entry.names}:
            return entry
    return None


def matching_camps(
    itinerary: Itinerary,
    collector: str,
    written_date: str,
    elevation_ft: int | None = None,
    slope: str | None = None,
) -> tuple[Camp, ...]:
    """The camps a label fits: a collector the itinerary names, a date whose
    interval overlaps the camp's dates (a label written to the month fits every
    camp of that month), and, when the label states them, the camp's elevation
    and a slope the camp shares or leaves unstated."""
    words = set(fold(collector).split())
    if not any(fold(name) in words for name in itinerary.collectors):
        return ()
    first, last = interval(written_date)
    return tuple(
        camp
        for camp in itinerary.camps
        if interval(camp.start)[0] <= last
        and first <= interval(camp.end)[1]
        and (elevation_ft is None or camp.elevation_ft == elevation_ft)
        and (slope is None or camp.slope in (None, slope))
    )
