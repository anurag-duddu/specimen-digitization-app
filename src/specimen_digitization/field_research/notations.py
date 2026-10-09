"""The place notations the labels use (G29), read into the names a place source knows.

One table: the notation as labels write it, the name it stands for (the
expansion a place source is asked), the field it names, and how the experts'
shared brief reads it. The brief's notation line is rendered from this table
(prompts.instructions), and the place rule (agreement.place_basis, P4 of #284)
accepts a lookup of an entry's expansion as a lookup of the label's own text
for that entry's field. A notation is matched by the place tool's comparison
key (agreement.place_name), so "P. I." is "P.I."; nothing else is expanded.
"""

from __future__ import annotations

from dataclasses import dataclass

from specimen_digitization.application.georef_locality import comparison_key


@dataclass(frozen=True)
class Notation:
    notation: str
    # The name a place source is asked for it.
    expansion: str
    field: str
    # How the brief reads it.
    reading: str


NOTATIONS = (
    Notation("P.I.", "Philippine Islands", "country", "the Philippine Islands, now the Philippines"),
    Notation("Guat.", "Guatemala", "country", "Guatemala"),
)
# The stand-in common.txt holds for the rendered notation line.
MARKER = "- PLACE_NOTATIONS"


def expansion(literal: str, field: str) -> Notation | None:
    """The table's entry for this field whose notation the literal is, or None."""
    key = comparison_key(literal)
    return next((entry for entry in NOTATIONS
        if entry.field == field and key and comparison_key(entry.notation) == key), None)


def brief_line() -> str:
    """The brief's line for the table: each notation, how it reads, its field
    and the name to look it up by."""
    return "- " + " ".join(
        f'"{entry.notation}": {entry.reading} ({entry.field}; look it up as "{entry.expansion}").'
        for entry in NOTATIONS)
