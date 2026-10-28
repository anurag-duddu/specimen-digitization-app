"""A label's reading units: its text cut at logical breaks, one judgement of the image each.

The record of FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md section 3, "What each unit holds",
stored on the run (`Run.reading_units`, one entry per label). Work package 1.1 of
docs/execution/units/PLAN.md stores and carries the record; nothing in this module makes units
or settles a field on them.

Only what a unit says about itself is checked here. Section 3's tiling and range checks need the
readings' whole texts and are not made here.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# What the image shows at a unit when it names no reader's text (section 3, `image`).
UNCERTAIN = "uncertain"
NOT_VISIBLE = "not visible"

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
        if self.image not in {UNCERTAIN, NOT_VISIBLE} | {
            reading.text for reading in self.readers.values()
        }:
            raise ValueError("The image names one reader's text, uncertain or not visible")
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
