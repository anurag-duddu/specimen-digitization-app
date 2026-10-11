"""Each field expert's instructions: the shared rules, then the field's own brief.

The files ship inside the package (hatch includes every file under
src/specimen_digitization), like research_harness/prompts.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

from ..contracts import FIELD_TOOLS

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


@cache
def instructions(key: str) -> str:
    """The expert's whole instructions for one field; an unknown field is refused."""
    if key not in FIELD_TOOLS or key not in FIELD_LABELS:
        raise KeyError(f"no field brief for {key!r}")
    common = (_ROOT / "common.txt").read_text(encoding="utf-8").strip()
    brief = (_ROOT / f"{key}.txt").read_text(encoding="utf-8").strip()
    return common + "\n\n" + brief + "\n"
