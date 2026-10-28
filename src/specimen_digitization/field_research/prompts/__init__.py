"""Each field expert's instructions: the shared rules, then the field's own brief.

The files ship inside the package (hatch includes every file under
src/specimen_digitization), like research_harness/prompts. The shared rules'
range and elevation-unit lines are rendered from field_research.written, the
tables the range and unit rules read, so they cannot drift.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from ..contracts import FIELD_TOOLS
from ..written import RANGE_MARKER, UNIT_MARKER, range_line, unit_line

# The display names of PRD's mandatory-field table.
FIELD_LABELS = {
    "fmnh_ins_number": "FMNH-INS#",
    "collection_code": "Collection Code",
    "country": "Country",
    "province_state": "Province/State",
    "county": "County",
    "city": "City",
    "precise_location": "Precise Location",
    "elevation_from_m": "Elevation From (m)",
    "elevation_to_m": "Elevation To (m)",
    "elevation_from_ft": "Elevation From (ft)",
    "elevation_to_ft": "Elevation To (ft)",
    "habitat": "Habitat",
    "collection_method": "Collection Method",
    "date_visited_from": "Date Visited From",
    "date_visited_to": "Date Visited To",
    "collectors": "Collectors",
    "verbatim_dts": "Verbatim D/T/S",
    "taxon": "Taxon",
    "identified_by_irn": "Identified by IRN",
    "date_identified": "Date Identified",
}

_ROOT = Path(__file__).parent


def parse_replacements(text: str) -> dict[str, tuple[tuple[str, str], ...]]:
    """units.txt's form: for each file named on a "== <file>" line, each "<<< " line's text
    with the ">>> " line's text after it, in order. Empty lines and "#" lines are skipped;
    any other line, a "<<< " line before a file or after another "<<< " line, a ">>> " line
    with no "<<< " line before it, or a "<<< " line last, is refused."""
    found: dict[str, list[tuple[str, str]]] = {}
    name, old = None, None
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        if line.startswith("== ") and old is None:
            name = line[3:]
        elif line.startswith("<<< ") and name is not None and old is None:
            old = line[4:]
        elif line.startswith(">>> ") and old is not None:
            found.setdefault(name, []).append((old, line[4:]))
            old = None
        else:
            raise ValueError(f"units.txt cannot read the line {line[:40]!r}")
    if old is not None:
        raise ValueError("units.txt ends with a text and nothing to replace it")
    return {name: tuple(pairs) for name, pairs in found.items()}


@cache
def units_replacements() -> dict[str, tuple[tuple[str, str], ...]]:
    """units.txt (parse_replacements): for each file of this folder, the texts the units
    path replaces in it, each with the text that stands in its place, in the file's order."""
    return parse_replacements((_ROOT / "units.txt").read_text(encoding="utf-8"))


def _read(name: str, units: bool) -> str:
    """A file of this folder, stripped; on the units path with its replacements made, each
    text found in it exactly once (units_replacements)."""
    text = (_ROOT / name).read_text(encoding="utf-8").strip()
    for old, new in units_replacements().get(name, ()) if units else ():
        if text.count(old) != 1:
            raise ValueError(f"{name} must hold each text units.txt replaces once")
        text = text.replace(old, new)
    return text


@cache
def instructions(key: str, units: bool = False) -> str:
    """The expert's whole instructions for one field; an unknown field is refused. With
    `units` (a run whose first-pass path is units): the texts units.txt names replaced,
    and the specimen ontology's brief text (ontology.render(brief=True), as the units
    path's first pass carries it) between the shared rules and the brief: every request
    an expert sends carries its instructions, which budget.input_token_bound counts
    against budget.DEFAULT_MAX_INPUT_TOKENS."""
    if key not in FIELD_TOOLS or key not in FIELD_LABELS:
        raise KeyError(f"no field brief for {key!r}")
    common = _read("common.txt", units)
    for marker, line in ((RANGE_MARKER, range_line()), (UNIT_MARKER, unit_line())):
        if common.count(marker) != 1:
            raise ValueError(f"common.txt must hold the marker {marker!r} once")
        common = common.replace(marker, line)
    brief = _read(f"{key}.txt", units)
    if units:
        from specimen_digitization.ontology import render

        common += "\n\n" + render(brief=True).strip()
    return common + "\n\n" + brief + "\n"
