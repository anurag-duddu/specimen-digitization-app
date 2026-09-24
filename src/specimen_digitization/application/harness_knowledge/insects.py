"""The Insects harness's knowledge (G29): the label notations of the pilot
subcollection and every reading each allows.

G29 makes it the harness's principle to work through every reading a notation
allows, for dates and for every other field, and to settle only what the
evidence supports. Each subcollection's profile names its knowledge by id and
version; this is the pilot's. It is rendered into the harness's system prompt,
and its aliases are the only names the geography tool accepts beyond a place's
own (HARNESS.md section 7).
"""

from __future__ import annotations

from dataclasses import dataclass

KNOWLEDGE_ID = "insects"
KNOWLEDGE_VERSION = "insects-harness-knowledge-v1"


@dataclass(frozen=True)
class Notation:
    written: str  # As labels write it, e.g. "P.I."
    readings: tuple[str, ...]  # Every reading it allows.
    fields: tuple[str, ...]  # The fields it can belong to.


NOTATIONS = (
    Notation("P.I.", ("Philippine Islands, the Philippines",), ("country",)),
    Notation("Guat.", ("Guatemala",), ("country",)),
    Notation(
        "Prov.",
        ("province, a word of the province's name, not the name",),
        ("province_state",),
    ),
    Notation(
        "Dept.",
        ("department, a word of the province's name, not the name",),
        ("province_state",),
    ),
    Notation("Mt.", ("mount, part of the place's name",), ("precise_location",)),
    Notation(
        "Is.", ("island or islands",), ("precise_location", "county", "province_state")
    ),
    Notation("nr.", ("near",), ("precise_location",)),
    Notation(
        "E. slope, W. side",
        ("a direction qualifying the place that follows",),
        ("precise_location",),
    ),
    Notation(
        "leg., coll., Coll.", ("collected by, marking the collectors",), ("collectors",)
    ),
    Notation(
        "det.",
        ("determined by, marking who identified the specimen",),
        ("identified_by_irn",),
    ),
    Notation(
        "m, ft., ', alt., el.",
        ("metres or feet of elevation",),
        ("elevation_from_m", "elevation_to_m", "elevation_from_ft", "elevation_to_ft"),
    ),
    Notation(
        "ca., c.",
        ("about: the value is approximate",),
        ("elevation_from_m", "elevation_from_ft", "date_visited_from"),
    ),
    Notation(
        "I to XII in a date",
        ("the month, January to December, when the profile allows Roman months",),
        ("date_visited_from", "date_visited_to", "date_identified"),
    ),
    Notation(
        "Jan., Feb., Mar., Apr., Jun., Jul., Aug., Sep., Sept., Oct., Nov., Dec.",
        ("the month",),
        ("date_visited_from", "date_visited_to", "date_identified"),
    ),
    Notation(
        "4-5-48, 4.5.48, 4/5/48",
        ("month 4, day 5", "day 4, month 5"),
        ("date_visited_from", "date_visited_to", "date_identified"),
    ),
    Notation(
        "'46, -46",
        ("the year 1946, under the profile's century rule",),
        ("date_visited_from", "date_visited_to", "date_identified"),
    ),
    Notation("?", ("the preceding value is uncertain as written",), ()),
)

# Folded label forms and the place names they may be read as, for the
# geography tool (`fold` of `geography_tool`: lower case, no punctuation).
PLACE_ALIASES = {
    "pi": ("philippines",),
    "philippine islands": ("philippines",),
    "guat": ("guatemala",),
}

RULES = """\
Copy every literal exactly as the reading has it, character for character; a
literal that is not in the reading is refused. Never complete, correct or
translate a literal: readings of a notation are for calling the tools, never
for the literal itself. Work through every reading a notation allows before a
field is left for review, and let the tools and the specimen's other evidence
decide between them. A field the label does not have stays empty."""


def render() -> str:
    """The knowledge as it enters the harness's system prompt."""
    lines = [
        f"Label knowledge ({KNOWLEDGE_VERSION}):",
        RULES,
        "",
        "Notations and the readings each allows:",
    ]
    for notation in NOTATIONS:
        readings = "; or ".join(notation.readings)
        where = f" [{', '.join(notation.fields)}]" if notation.fields else ""
        lines.append(f"- {notation.written}: {readings}{where}")
    return "\n".join(lines)
