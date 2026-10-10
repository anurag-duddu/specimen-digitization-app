"""A date written over two lines of one label.

A label sometimes breaks a date at the end of a line: the day and month on one
line and the year alone on the next ("Guatemala, IV-25" above "1948, R.D.
Mitchell"), or the reverse. A person reads that as one date, and so does the
date check, but only under all of these rules, none of them a guess:

- the date and the year are on adjacent lines, with nothing between them but
  the line break (the date ends its line and the year starts the next, or the
  year ends a line and the date starts the next);
- the year is a token of its own, four digits or two after an apostrophe (a
  bare two-digit number alone could be anything);
- nothing else on either line could be a date: no other year, no Roman or
  written month, no numeric date (`could_be_a_date`);
- the date states no year of its own (the date parser says so);
- the lines above and below do not each give a different year.

Where any rule fails, the date stays as the parser reads it alone, with its
year missing, and goes to review.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from specimen_digitization.application.date_months import MONTH_WORDS, fold
from specimen_digitization.application.date_notations import APOSTROPHES, ROMAN
from specimen_digitization.application.field_validators import EARLIEST_YEAR

# A year standing as a token of its own: 1948 or '48.
YEAR_TOKEN = rf"(?:[{APOSTROPHES}][0-9]{{2}}|[0-9]{{4}})"
_ALONE = re.compile(YEAR_TOKEN)
_YEAR_AT_START = re.compile(rf"\s*(?P<y>{YEAR_TOKEN})(?![0-9A-Za-z])")
_YEAR_AT_END = re.compile(rf"(?<![0-9A-Za-z])(?P<y>{YEAR_TOKEN})\s*$")
_ANY_YEAR = re.compile(rf"(?<![0-9A-Za-z])(?P<y>{YEAR_TOKEN})(?![0-9A-Za-z])")
_NUMERIC = re.compile(r"(?<![0-9])[0-9]{1,2}\s*[-./]\s*[0-9]{1,2}(?![0-9])")
_NUMERALS = "|".join(reversed(ROMAN))
_ROMAN_BY_NUMBER = re.compile(
    rf"(?<![A-Za-z0-9])(?:{_NUMERALS})\s*[-./]\s*[0-9]|[0-9]\s*[-./]\s*(?:{_NUMERALS})(?![A-Za-z])"
)
_WORD = re.compile(r"[^\W\d_]+")


def could_be_a_date(text: str) -> bool:
    """Whether anything in the text could be (part of) a date: a year, a numeric
    date, a Roman month beside a number, or a month word of any language. The
    test is deliberately wide; it only ever keeps two lines from being joined."""
    for hit in _ANY_YEAR.finditer(text):
        if _plausible(hit["y"]):
            return True
    if _NUMERIC.search(text) or _ROMAN_BY_NUMBER.search(text):
        return True
    return any(fold(word).lower() in MONTH_WORDS for word in _WORD.findall(text))


def _plausible(year: str) -> bool:
    """A year token that could be a year: any two-digit one after an apostrophe,
    a four-digit one from the earliest plausible year to this one (an elevation
    such as 4800 is not one)."""
    return year[0] in APOSTROPHES or EARLIEST_YEAR <= int(year) <= datetime.now(UTC).year


def split_literal(literal: str) -> tuple[str, str] | None:
    """A literal of exactly two lines, one of them a year alone: the other line
    (the date that states no year, if it is one) and the year. None for any
    other literal."""
    lines = [line.strip() for line in literal.strip().replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    if len(lines) != 2 or not all(lines):
        return None
    first, second = lines
    year_first, year_second = bool(_ALONE.fullmatch(first)), bool(_ALONE.fullmatch(second))
    if year_second and not year_first:
        return first, second
    if year_first and not year_second:
        return second, first
    return None


def _line_around(text: str, start: int, end: int) -> tuple[int, int]:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    return line_start, len(text) if line_end < 0 else line_end


def lines_hold_no_other_date(literal: str, text: str) -> bool:
    """Whether, where the (two-line) literal stands in the text, the rest of its
    two lines could be no date: the text before it on its first line and after it
    on its second."""
    for hit in re.finditer(re.escape(literal), text):
        line_start, line_end = _line_around(text, hit.start(), hit.end())
        if not (could_be_a_date(text[line_start : hit.start()])
                or could_be_a_date(text[hit.end() : line_end])):
            return True
    return False


def year_beside(literal: str, text: str) -> tuple[str, str] | None:
    """The year a date written without one takes from the line beside it, with
    where it stands ("next_line" or "previous_line"); None when no line does, or
    when they give two different years.

    The date must end its line and the year start the next, or the date start
    its line and the year end the line above; the rest of both lines, and the
    year's own, must hold nothing that could be a date."""
    found: dict[str, str] = {}
    for hit in re.finditer(re.escape(literal), text):
        line_start, line_end = _line_around(text, hit.start(), hit.end())
        before, after = text[line_start : hit.start()], text[hit.end() : line_end]
        if not after.strip() and line_end < len(text):
            below_start = line_end + 1
            below_end = text.find("\n", below_start)
            below = text[below_start : len(text) if below_end < 0 else below_end]
            year = _YEAR_AT_START.match(below)
            if (year and _plausible(year["y"]) and not could_be_a_date(before)
                    and not could_be_a_date(below[year.end() :])):
                found.setdefault(year["y"], "next_line")
        if not before.strip() and line_start > 0:
            above_end = line_start - 1
            above = text[text.rfind("\n", 0, above_end) + 1 : above_end]
            year = _YEAR_AT_END.search(above)
            if (year and _plausible(year["y"]) and not could_be_a_date(above[: year.start()])
                    and not could_be_a_date(after)):
                found.setdefault(year["y"], "previous_line")
    if len(found) != 1:
        return None
    year, where = next(iter(found.items()))
    return year, where
