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


def _read(name: str) -> str:
    """A file of this folder, stripped."""
    return (_ROOT / name).read_text(encoding="utf-8").strip()


@cache
def instructions(key: str) -> str:
    """The expert's whole instructions for one field; an unknown field is refused: the shared
    rules, then the specimen ontology's brief text (ontology.render(brief=True), as the first
    pass carries it), then the instructions of the ontology's rules that name this field
    (ontology.render_instructions("expert", key)), when any does, then the field's brief.
    Every request an expert sends carries its instructions, which budget.input_token_bound
    counts against budget.DEFAULT_MAX_INPUT_TOKENS."""
    if key not in FIELD_TOOLS or key not in FIELD_LABELS:
        raise KeyError(f"no field brief for {key!r}")
    common = _read("common.txt")
    for marker, line in ((RANGE_MARKER, range_line()), (UNIT_MARKER, unit_line())):
        if common.count(marker) != 1:
            raise ValueError(f"common.txt must hold the marker {marker!r} once")
        common = common.replace(marker, line)
    brief = _read(f"{key}.txt")
    from specimen_digitization.ontology import render, render_instructions

    common += "\n\n" + render(brief=True).strip()
    if rules := render_instructions("expert", key).strip():
        common += "\n\n" + rules
    return common + "\n\n" + brief + "\n"
