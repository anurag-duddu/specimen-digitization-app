"""A label's reading units: its text cut at logical breaks, one judgement of the image each.

The record of FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 3, "What each unit holds",
stored on the run (`Run.reading_units`, one entry per label). Work package 1.1 of
docs/execution/units/PLAN.md stores and carries the record; work package 1.2's first pass
(application/first_pass.py) makes it. Nothing here settles a field.

The models check what a unit says about itself. Section 3's tiling and range checks need the
readings' whole texts: `problems` makes them on a label's units against its readings, for the
first pass's answer, the workflow's step and the integrity check of a stored run.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# What the image shows at a unit when it names no reader's text (section 3, `image`).
UNCERTAIN = "uncertain"
NOT_VISIBLE = "not visible"

# The switch of the units path (docs/execution/units/PLAN.md, WP 1.2), read once per run: when
# the run is created (`Run.first_pass_path`, every construction site in src passes it). The run
# keeps that path for good, so the first pass, the model child and the experts follow the run,
# and turning the switch off or on changes only the runs created afterwards. The processes that
# create runs carry it: the API and the intake job (scripts/ci/runtime_settings.py).
#
# Rollback: main before this change (WP 1.1 included) loads `Run.reading_units` but not
# `Run.first_pass_path` (`Record` refuses an unknown key, domain.py), so the boundary is the path
# field, in the run and in its previous runs; before WP 1.1 units are unknown too. The switch is
# turned on only once this runtime (or a later one) serves the API, the intake job and the
# worker; a rollback past it first turns the switch off and waits until no record the older
# runtime would load names the units path.
SETTING = "SPECIMEN_FIRST_PASS_UNITS"
OLD, UNITS = "old", "units"


def first_pass_path(environ) -> str:
    """The path a run created now takes: "units" when SPECIMEN_FIRST_PASS_UNITS is "on", "old"
    when it is "off", empty or unset. Any other value raises, naming the setting and never its
    value, so a mistyped value never decides the path."""
    value = environ.get(SETTING, "")
    if value in ("", "off"):
        return OLD
    if value == "on":
        return UNITS
    raise ValueError(f"{SETTING} must be on or off")

Line = Annotated[int, Field(ge=1)]


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UnitText(_Record):
    """What one reader wrote at a unit, and where in that reader's text.

    `start` and `end` are Python string indices into the reader's text, so they count code points,
    not UTF-16 code units: `text` is `reading[start:end]`. A reader that wrote nothing at the unit
    has an empty `text`, with `start` equal to `end`.
    """

    text: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def spans_its_text(self):
        if self.end - self.start != len(self.text):
            raise ValueError("A unit's text spans exactly end - start code points")
        return self


class ReadingUnit(_Record):
    """One unit of a label: the keys of section 3's table."""

    # "<label>:<n>", n counting from 1 in reading order.
    id: str
    label: str = Field(min_length=1)
    # The first and last line the unit covers, counting from 1; a unit may cross a line.
    lines: tuple[Line, Line]
    # Each reader's text here, keyed by reading; every unit of a label names the same readings.
    readers: dict[str, UnitText] = Field(min_length=1)
    # One reader's text, `uncertain` or `not visible`: a judgement of the image, never a text no
    # reader wrote.
    image: str
    # The first pass's own interpretation; may be text no reader wrote, never a literal.
    means: str = ""
    # The part of a field's value this unit is, when it is one.
    role: Literal["", "genus", "species", "author", "day", "month", "year"] = ""
    # The fields this unit could belong to, most likely first: advice only.
    fields: list[str] = Field(default_factory=list)
    note: str = ""

    @field_validator("lines")
    @classmethod
    def in_order(cls, lines):
        if lines[0] > lines[1]:
            raise ValueError("A unit's first line comes before its last")
        return lines

    @field_validator("readers")
    @classmethod
    def keyed(cls, readers):
        if any(not key for key in readers):
            raise ValueError("Every reader at a unit has a key")
        return readers

    @field_validator("fields")
    @classmethod
    def distinct(cls, fields):
        if any(not field for field in fields) or len(set(fields)) != len(fields):
            raise ValueError("A unit names each field once")
        return fields

    @model_validator(mode="after")
    def names_a_reading(self):
        # A reader that wrote nothing here has an empty text, which names nothing the image
        # could show: the image is a reader's non-empty text, uncertain or not visible.
        if self.image not in {UNCERTAIN, NOT_VISIBLE} | {
            reading.text for reading in self.readers.values() if reading.text
        }:
            raise ValueError(
                "The image names one reader's non-empty text, uncertain or not visible"
            )
        return self


class ReadingUnits(_Record):
    """One label's units, in reading order. An empty list is refused."""

    label: str = Field(min_length=1)
    units: list[ReadingUnit] = Field(min_length=1)

    @model_validator(mode="after")
    def numbered(self):
        for number, unit in enumerate(self.units, 1):
            if unit.label != self.label or unit.id != f"{self.label}:{number}":
                raise ValueError("A label's units are <label>:1, <label>:2, ... in reading order")
        readers = set(self.units[0].readers)
        if any(set(unit.readers) != readers for unit in self.units):
            raise ValueError("Every unit of a label names the label's same readers")
        return self


# Section 3, "What code checks on every answer": the range. A range is a number or a date, a
# joiner, then a number or a date of the same kind. The token rules (WP 1.2's decision):
# - A value is digits, or a Roman month (I to XII, in capitals), and further such parts joined
#   by ".", "/" or ",": "6400", "1,200", "1.5", "15.VII.1968", "7/15/68". It starts and ends at a
#   word's edge, so no part of a letter-digit code ("1a2", "B12") is one.
# - A sign ("+", "-" or the minus sign) belongs to a value only before a digit at the start of a
#   token: "-20" is a value, so "6400 -7000" is two values and no range.
# - A joiner is a hyphen or an en dash, with or without white space around it, or one of the
#   words "to", "bis", "au" and "a" standing alone between white space.
# - A value with a Roman month is a date, any other a number. The same kind: two numbers, two
#   dates, or a number and a date that starts with a number (a day range: "12-15.VII.1968").
# - Values joined in a chain are one range ("10-6-78" in a slide code).
# A line-end hyphen inside a word ("Mos-\nsy") joins letters, never values, so it is no range.
_MONTH = r"(?:XII|XI|IX|X|VIII|VII|VI|IV|V|III|II|I)"
_PART = rf"(?:\d+|{_MONTH})"
_VALUE = re.compile(
    rf"(?:(?<!\S)[+\-\u2212](?=\d))?(?<!\w){_PART}(?:[./,]{_PART})*(?!\w)"
)
_JOINER = re.compile(r"\s*[-\u2013]\s*|\s+(?:to|bis|au|a)\s+", re.IGNORECASE)
_DATE = re.compile(rf"(?<![A-Z]){_MONTH}(?![A-Z])")


def _kind(value: str) -> str:
    return "date" if _DATE.search(value) else "number"


def _same_kind(left: str, right: str) -> bool:
    kinds = _kind(left), _kind(right)
    return kinds[0] == kinds[1] or (
        kinds == ("number", "date") and right.lstrip("+-\u2212")[:1].isdigit()
    )


def range_spans(text: str) -> list[tuple[int, int]]:
    """Each range in a reading as [start, end) code-point offsets, in reading order."""
    values = list(_VALUE.finditer(text))
    spans: list[list[int]] = []
    for left, right in zip(values, values[1:]):
        if _JOINER.fullmatch(text, left.end(), right.start()) and _same_kind(
            left.group(), right.group()
        ):
            if spans and spans[-1][1] == left.end():
                spans[-1][1] = right.end()
            else:
                spans.append([left.start(), right.end()])
    return [(start, end) for start, end in spans]


def splits_a_range(text: str, end: int, start: int) -> bool:
    """Whether a boundary between two units, from `end` (where the first ends) to `start`
    (where the next begins), lies inside a range of the reading `text`."""
    return any(low < end and start < high for low, high in range_spans(text))


def problems(units: ReadingUnits, readings: dict[str, str]) -> list[str]:
    """Why a label's units fail section 3's checks against its readings, by reading key.

    Tiling: every unit names exactly the label's readings; each reading's units, in order,
    cover every character of it, with only white space before, between and after them; and a
    unit holds some reader's text. Range: no unit ends inside a range of any reading.
    """
    if set(units.units[0].readers) != set(readings):
        return ["the units do not name exactly the label's readings"]
    found = []
    for key, text in readings.items():
        cursor, previous = 0, None
        for unit in units.units:
            span = unit.readers[key]
            if (
                span.start < cursor
                or span.end > len(text)
                or text[span.start : span.end] != span.text
                or text[cursor : span.start].strip()
            ):
                found.append(f"{unit.id} does not go on in reading {key} where the unit before ended")
                break
            if previous is not None and splits_a_range(text, previous.end, span.start):
                found.append(f"{unit.id} begins inside a range of reading {key}")
            cursor, previous = span.end, span
        else:
            if text[cursor:].strip():
                found.append(f"the units do not cover the end of reading {key}")
    found += [
        f"{unit.id} holds no reader's text"
        for unit in units.units
        if not any(span.text for span in unit.readers.values())
    ]
    return found
