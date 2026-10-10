"""A date written over two lines of one label.

A label sometimes breaks a date at the end of a line: the day and month on one
line and the year alone on the next ("Guatemala, IV-25" above "1948"), or the
reverse. A person reads that as one date, and so does the date check, but only
under all of these rules, none of them a guess:

- the date and the year are on adjacent lines, with nothing between them but
  the line break (the date ends its line and the year starts the next, or the
  year ends a line and the date starts the next);
- the year is bare, and never a measurement or a determination's year:
  - a day and month written alone take a year from the line beside them only
    when that line holds nothing but a four-digit year, optionally followed by a
    period or a comma (`year_beside`): "1948" yes; "1948 m", "1948'", "1948 ft.",
    "1948-49", "El. 1948", "det. J. Smith 1950", "1948, R.D. Mitchell" no;
  - a literal of two lines is the organiser's own quote of the date and its
    year, so the year may be followed by a comma, semicolon or period and
    then other text ("1948, R.D. Mitchell"), but not by a unit, an apostrophe,
    a dash and a number, a second number or a word without such a mark ("1948
    m", "1948'", "1948-49", "1948 det."), and a year that ends the line above
    the date must stand alone on its line (`split_problem`);
- nothing else on either line could be a date: no other year, Roman or written
  month, or numeric date (`could_be_a_date`);
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
# A line that holds nothing but a year, with at most a period or comma after it.
_BARE_YEAR = re.compile(r"\s*(?P<y>[0-9]{4})[.,]?\s*")
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


# The line breaks str.splitlines() splits at: one definition of a line for the date
# parser (`literal_spans_a_line_break`), these rules, the checks and the step.
_BREAK = re.compile("\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}]")


def _lines(literal: str) -> list[str]:
    return [line.strip() for line in literal.strip().splitlines()]


def _spans(text: str) -> list[tuple[int, int]]:
    """Where each line of the text starts and ends: the lines str.splitlines() gives."""
    spans, start = [], 0
    for hit in _BREAK.finditer(text):
        spans.append((start, hit.start()))
        start = hit.end()
    return [*spans, (start, len(text))]


def _line_of(spans: list[tuple[int, int]], position: int) -> int:
    """The line a position of the text is on (inside a line break: the line before it)."""
    return max(index for index, (start, _) in enumerate(spans) if start <= position)


def _unmarked(line: str) -> str:
    """The line without the period, comma, semicolon or colon a sentence leaves
    after its last word ("1948." is the year 1948), as the date parser reads it."""
    return line.strip().rstrip(" .,;:")


def split_literal(literal: str) -> tuple[str, str] | None:
    """A literal of two lines (blank lines aside) one of which is a year alone,
    with at most a period or comma after it: the other line (the date that
    states no year, if it is one) and the year without its mark. None for any
    other literal. Whether the two lines are adjacent is `split_problem`'s."""
    lines = [line for line in _lines(literal) if line]
    if len(lines) != 2:
        return None
    first, second = lines
    year_first, year_second = bool(_ALONE.fullmatch(_unmarked(first))), bool(_ALONE.fullmatch(_unmarked(second)))
    if year_second and not year_first:
        return first, _unmarked(second)
    if year_first and not year_second:
        return second, _unmarked(first)
    return None


def _around(spans: list[tuple[int, int]], start: int, end: int) -> tuple[int, int, int, int]:
    """The lines a span of the text starts and ends on, and where the first
    starts and the last ends."""
    first, last = _line_of(spans, start), _line_of(spans, end)
    return first, last, spans[first][0], spans[last][1]


OTHER_DATE = "split_lines_hold_another_date"
YEAR_NOT_ALONE = "split_lines_year_not_alone"
NOT_ADJACENT = "split_lines_not_adjacent"


def split_problem(literal: str, text: str) -> str | None:
    """Why the (two-line) literal, where it stands in the text, is not a date and
    its year (a note: `split_lines_not_adjacent`, `split_lines_hold_another_date`
    or `split_lines_year_not_alone`), or None when some place of it is clear.

    The two lines are adjacent: no blank line between them. The date's own line
    holds nothing else that could be a date. A year that ends the line above the
    date must stand alone on its line; one that starts the line below it may be
    followed by a comma, semicolon or period (and then other text), never by a
    unit, an apostrophe, a dash and a number, a second number, or a word. A
    period or comma the literal itself quotes after the year counts as following
    it."""
    lines = _lines(literal)
    if len(lines) != 2:
        return NOT_ADJACENT
    year_first = bool(_ALONE.fullmatch(_unmarked(lines[0])))
    # The mark the literal quotes after a year that ends it ("1948." in "3 Sept.\n1948.").
    tail = lines[1][len(_unmarked(lines[1])) :] if not year_first else ""
    problem = OTHER_DATE
    spans = _spans(text)
    for hit in re.finditer(re.escape(literal), text):
        _, _, line_start, line_end = _around(spans, hit.start(), hit.end())
        before, after = text[line_start : hit.start()], tail + text[hit.end() : line_end]
        if year_first:
            # The year ends its line: it stands alone there; the date's line is after.
            if could_be_a_date(before) or could_be_a_date(after):
                continue
            if before.strip():
                problem = YEAR_NOT_ALONE
                continue
            return None
        if could_be_a_date(before):
            continue
        rest = after.strip()
        if not rest or (after[0] in ",;." and not after[1:2].isdigit()):
            if not could_be_a_date(after[1:]):
                return None
            continue
        if could_be_a_date(after):
            continue
        problem = YEAR_NOT_ALONE
    return problem


def _bare_year(line: str) -> str | None:
    hit = _BARE_YEAR.fullmatch(line)
    return hit["y"] if hit and _plausible(hit["y"]) else None


def year_beside(literal: str, text: str) -> tuple[str, str] | None:
    """The year a date written without one takes from the line beside it, with
    where it stands ("next_line" or "previous_line"); None when no line does, or
    when they give two different years.

    The date must end its line and the line below hold nothing but a four-digit
    year (and at most a period or comma), or the date must start its line and
    the line above hold nothing else; the rest of the date's own line must hold
    nothing that could be a date."""
    found: dict[str, str] = {}
    spans = _spans(text)
    for hit in re.finditer(re.escape(literal), text):
        first, last, line_start, line_end = _around(spans, hit.start(), hit.end())
        before, after = text[line_start : hit.start()], text[hit.end() : line_end]
        if not after.strip() and last + 1 < len(spans) and not could_be_a_date(before):
            year = _bare_year(text[slice(*spans[last + 1])])
            if year:
                found.setdefault(year, "next_line")
        if not before.strip() and first > 0 and not could_be_a_date(after):
            year = _bare_year(text[slice(*spans[first - 1])])
            if year:
                found.setdefault(year, "previous_line")
    if len(found) != 1:
        return None
    year, where = next(iter(found.items()))
    return year, where
