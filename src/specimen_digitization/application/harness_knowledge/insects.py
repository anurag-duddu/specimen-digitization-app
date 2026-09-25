"""The Insects harness's knowledge (G29): the label notations of the pilot
subcollection and every reading each allows.

G29 makes it the harness's principle to work through every reading a notation
allows, for dates and for every other field, and to settle only what the
evidence supports. Each subcollection's profile names its knowledge by id and
version; this is the pilot's. It is rendered into the harness's system prompt,
and its aliases are the only names the geography tool accepts beyond a place's
own (HARNESS.md section 7). Its markers, months and full forms are what PLAN
4.8's place-request filter cuts and writes out.
"""

from __future__ import annotations

from dataclasses import dataclass

KNOWLEDGE_ID = "insects"
# v2: slide-preparation codes and single written values (coordinator, 2026-09-24);
# v3: the tables PLAN 4.8's place-request filter reads (HARNESS.md section 7).
KNOWLEDGE_VERSION = "insects-harness-knowledge-v3"


@dataclass(frozen=True)
class Notation:
    written: str  # As labels write it, e.g. "P.I."
    readings: tuple[str, ...]  # Every reading it allows.
    fields: tuple[str, ...]  # The fields it can belong to.


# Each month in full and abbreviated, in English and in Spanish, the pilot
# labels' languages (PLAN 4.8 in #191).
MONTHS_ENGLISH = (
    *("January", "February", "March", "April", "May", "June", "July"),
    *("August", "September", "October", "November", "December"),
    *("Jan.", "Feb.", "Mar.", "Apr.", "Jun.", "Jul.", "Aug.", "Sep.", "Sept."),
    *("Oct.", "Nov.", "Dec."),
)
MONTHS_SPANISH = (
    *("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio"),
    *("agosto", "septiembre", "octubre", "noviembre", "diciembre"),
    *("ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sep."),
    *("sept.", "oct.", "nov.", "dic."),
)

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
        ", ".join(MONTHS_ENGLISH),
        ("the month",),
        ("date_visited_from", "date_visited_to", "date_identified"),
    ),
    Notation(
        ", ".join(MONTHS_SPANISH),
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
    # S8's pilot research: these look like dates but are not collection dates.
    Notation(
        "IX-17-66-2, IV-29-68-a, VI-24-68-7, 10-6-78-la at a label's top edge",
        (
            (
                "the slide's preparation code, the date it was made and a serial:"
                " never a collection date, and it belongs in no field"
            ),
        ),
        (),
    ),
)

# Folded label forms and the place names they may be read as, for the
# geography tool (`fold` of `geography_tool`: lower case, punctuation as spaces,
# so "P.I." is "p i", as S8's tool folds it).
PLACE_ALIASES = {
    "p i": ("philippines",),
    "philippine islands": ("philippines",),
    "guat": ("guatemala",),
}

RULES = """\
Copy every literal exactly as the reading has it, character for character; a
literal that is not in the reading is refused. Never complete, correct or
translate a literal: readings of a notation are for calling the tools, never
for the literal itself. Work through every reading a notation allows before a
field is left for review, and let the tools and the specimen's other evidence
decide between them. A field the label does not have stays empty.
A single elevation written once is given once, as the From field of its unit:
the harness fills the other end and the other unit. A single date written once
is given once, as Date Visited From: the harness fills Date Visited To."""

# G45 (the owner, 2026-09-24: "In fields no lookup checks, a value that doesn't
# look like its field's kind goes to review with a reason"): what a value in
# each such field must not look like. Minimal, and each rule is a real run's
# case; the queue decision applies them to the harness's runs.
SHAPE_PATTERNS = {
    # Month, day, two-digit year and a serial: IV-29-68-a, 10-6-78-la.
    "preparation_code": r"(?<![\w-])(?:[IVX]{1,4}|\d{1,2})-\d{1,2}-\d{2}-[0-9A-Za-z]{1,3}(?![\w-])",
    # A written date: 14-5-48, 12.v.1946, IV-25, '46.
    "numeric_date": (
        r"(?<![\w-])(?:\d{1,2}|[IVXivx]{1,4})[-./](?:\d{1,2}|[IVXivx]{1,4})"
        r"[-./](?:\d{4}|\d{2})(?![\w-])"
        r"|(?<![\w-])[IVX]{1,4}-\d{1,2}(?![\w-])|['’]\d{2}(?!\w)"
    ),
    "digit": r"\d",  # Names carry none.
    # The specimen's own marks: ♀, ♂, Sp.#1, sp. 30.
    "specimen_mark": r"[♀♂]|(?<![A-Za-z])[Ss]p\.\s*#?\s*\d",
}
_NOT_THE_SPECIMEN = ("preparation_code", "numeric_date", "specimen_mark")
SHAPES = {
    "collectors": (*_NOT_THE_SPECIMEN, "digit"),  # "VI-24-68-7" (105526328).
    "collection_code": _NOT_THE_SPECIMEN,  # "IV-29-68-a" (105526330).
    "habitat": _NOT_THE_SPECIMEN,  # "♀ legs Sp.#1" (105526330).
    "collection_method": _NOT_THE_SPECIMEN,
    "precise_location": _NOT_THE_SPECIMEN,  # "VI-24-68-7" (105526328).
    "verbatim_dts": ("preparation_code",),  # "10-6-78-la" (105526321).
}
# PRD 522 leaves verbatim_dts's meaning unconfirmed: a finding, never a reason.
FINDING_ONLY = frozenset({"verbatim_dts"})

# What PLAN 4.8's place-request filter reads (HARNESS.md section 7): the
# collector and determiner markers the notations name,
PERSON_MARKERS = ("leg.", "coll.", "Coll.", "det.")
# the month names and abbreviations the date notations list,
MONTH_WORDS = (*MONTHS_ENGLISH, *MONTHS_SPANISH)
# the Roman months, cut too (the coordinator's ruling of 2026-09-24),
ROMAN_MONTHS = (
    *("I", "II", "III", "IV", "V", "VI"),
    *("VII", "VIII", "IX", "X", "XI", "XII"),
)
# and the full forms of the notations assigned to place fields alone, each a
# form a request may carry in its place. "nr." relates a place; it is not part
# of the place's name.
FULL_FORMS = {
    "P.I.": ("Philippine Islands",),
    "Guat.": ("Guatemala",),
    "Prov.": ("Province",),
    "Dept.": ("Department",),
    "Mt.": ("Mount",),
    "Is.": ("Island", "Islands"),
}


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
