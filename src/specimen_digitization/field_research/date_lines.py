"""A date written over two lines of one label, or a day and month and their year
on one line that no notation reads whole.

A label sometimes breaks a date at the end of a line: the day and month on one
line and the year alone on the next ("Guatemala, IV-25" above "1948"), or the
reverse; or it writes the year after the day and month with only a space, a
comma or a period between them ("IV-25 1948", "25.IV, 1948": `one_line_literal`,
`one_line_problem`, the rules of a year on the line below its date). A person
reads that as one date, and so does the date check, but only under all of these
rules, none of them a guess (a line is what str.splitlines() gives):

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
  - no marker makes the year a measurement or a determination's year: its own
    line and the nearest line above it hold no elevation or depth word, no
    unit after a number and no determination ("Alt." above "1900", "1948,
    1900m", "det. J. Smith" above "1950"), and the nearest line below it does
    not start with a unit ("1900" above "m") (`_year_marker`);
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


# What makes a bare number beside it a measurement or a determination's year, not a
# collecting date's year. Words are matched folded (accents dropped) and in lower case,
# in the languages of the month tables: alt., altitude (en, fr, pt), altitud, altura
# (es, pt), altitudine, quota (it), altitudo (la), elev. and elevation (en; the es, pt
# and fr spellings fold to the three below), Hohe, Seehohe, Meereshohe (de, with the
# umlaut or "oe"), depth, profundidad, profundidade, profondeur, profondita, Tiefe; and
# the marks of a height above sea level (msnm, m.s.n.m., snm, s.n.m., s.l.m., a.s.l.,
# m.a.s.l.). "El." counts only with its period: "El" alone is the Spanish article.
_SEA_LEVEL = frozenset({"msnm", "snm", "slm", "asl", "masl"})
_MEASURE_WORDS = _SEA_LEVEL | {
    "alt", "altitude", "altitud", "altura", "altitudine", "altitudo", "quota",
    "elev", "elevation", "elevacion", "elevacao",
    "hohe", "hoehe", "seehohe", "seehoehe", "meereshohe", "meereshoehe",
    "depth", "profundidad", "profundidade", "profondeur", "profondita", "tiefe",
}
# The units of an elevation or a depth after a number, in any case (1900 m, 4800ft,
# 6000 pies, 1200 M, 4800'); a distance (5 mi W, 3 km) is not one. The short marks
# also count as a word of their own in lower case ("1948. m"): a word such as "foot"
# or "metro" alone does not ("foot of Volcan Fuego").
_UNITS = ("m", "mt", "mts", "metro", "metros", "metre", "metres", "meter", "meters", "metri",
    "ft", "feet", "foot", "pies", "pes", "pieds", "piedi", "fuss", "fu\N{LATIN SMALL LETTER SHARP S}")
_SHORT_UNITS = frozenset({"m", "mts", "ft"})
_UNIT_AFTER_NUMBER = re.compile(
    r"[0-9]\s*(?:" + "|".join(_UNITS) + r")(?![^\W\d_])"
    "|[0-9]['\N{RIGHT SINGLE QUOTATION MARK}\N{PRIME}]", re.IGNORECASE)
# A determination: det., determ., determinavit, determined (en), determino (es),
# determinou (pt), determine (fr, accent folded).
_DETERMINATION_WORDS = frozenset({
    "det", "determ", "determinavit", "determined", "determino", "determinou", "determine"})
# A word of letters, with the periods inside or after it (m.s.n.m., Alt., R.D.).
_TOKEN = re.compile(r"[^\W\d_](?:[^\W\d_]|\.(?=[^\W\d_]))*\.?")
MEASUREMENT, DETERMINATION = "measurement", "determination"


def _marker(line: str) -> str | None:
    """Whether a line marks the numbers on it, and on the line below it, as an
    elevation, a depth or another measurement (`measurement`), or as a
    determination's (`determination`); None when it marks neither."""
    folded = fold(line)
    if _UNIT_AFTER_NUMBER.search(folded):
        return MEASUREMENT
    found = None
    for token in _TOKEN.findall(folded):
        word = token.lower().replace(".", "")
        if word in _MEASURE_WORDS or token.lower() == "el." or (word in _SHORT_UNITS and token.islower()):
            return MEASUREMENT
        if word in _DETERMINATION_WORDS:
            found = DETERMINATION
    return found


def _starts_with_a_unit(line: str) -> bool:
    """Whether a line begins with a short unit or a height above sea level in lower
    case ("m", "ft.", "msnm", "m.s.n.m."): the unit of a number that ends the line above."""
    token = _TOKEN.match(fold(line).lstrip())
    word = token.group().replace(".", "") if token else ""
    return bool(token) and word.islower() and (word in _SHORT_UNITS or word in _SEA_LEVEL)


def _year_marker(text: str, spans: list[tuple[int, int]], line: int) -> str | None:
    """Why a number that is the year on the given line of the text may be no
    collecting date's year (`measurement` or `determination`): its own line, or the
    nearest line above it that is not blank, marks it (`_marker`), or the nearest
    line below it that is not blank starts with a unit. None when nothing does."""
    lines = [text[start:end] for start, end in spans]
    above = next((lines[i] for i in range(line - 1, -1, -1) if lines[i].strip()), "")
    below = next((lines[i] for i in range(line + 1, len(lines)) if lines[i].strip()), "")
    for marked in (lines[line], above):
        if kind := _marker(marked):
            return kind
    return MEASUREMENT if _starts_with_a_unit(below) else None


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
YEAR_MEASUREMENT = "split_lines_year_may_be_a_measurement"
YEAR_DETERMINATION = "split_lines_year_may_be_a_determination"
_SPLIT_NOTES = {"alone": YEAR_NOT_ALONE, MEASUREMENT: YEAR_MEASUREMENT,
    DETERMINATION: YEAR_DETERMINATION, "other": OTHER_DATE}


def _year_after(before: str, after: str) -> str | None:
    """Why a year that follows its date (starting the next line, or later on the
    date's own line) is not the date's year, from the text before the date and
    after the year on their lines: "other" (something there could be a date) or
    "alone" (the year is followed by more than a comma, semicolon or period and
    other text); None when neither."""
    if could_be_a_date(before):
        return "other"
    if not after.strip() or (after[0] in ",;." and not after[1:2].isdigit()):
        return "other" if could_be_a_date(after[1:]) else None
    return "other" if could_be_a_date(after) else "alone"


def _note(found: set[str], notes: dict[str, str]) -> str:
    """The note for the reasons the literal's places gave, the first of `notes` that applies."""
    return next((note for reason, note in notes.items() if reason in found), notes["other"])


def split_problem(literal: str, text: str) -> str | None:
    """Why the (two-line) literal, where it stands in the text, is not a date and
    its year (a note: `split_lines_not_adjacent`, `split_lines_year_not_alone`,
    `split_lines_year_may_be_a_measurement`, `split_lines_year_may_be_a_determination`
    or `split_lines_hold_another_date`), or None when some place of it is clear.

    The two lines are adjacent: no blank line between them. The date's own line
    holds nothing else that could be a date. A year that ends the line above the
    date must stand alone on its line; one that starts the line below it may be
    followed by a comma, semicolon or period (and then other text), never by a
    unit, an apostrophe, a dash and a number, a second number, or a word. A
    period, comma or semicolon the literal itself quotes after the year counts as
    following it (a colon does not: "1948:" is not alone). And no marker makes the
    year a measurement or a determination's year (`_year_marker`)."""
    lines = _lines(literal)
    if len(lines) != 2:
        return NOT_ADJACENT
    year_first = bool(_ALONE.fullmatch(_unmarked(lines[0])))
    # The mark the literal quotes after a year that ends it ("1948." in "3 Sept.\n1948.").
    tail = lines[1][len(_unmarked(lines[1])) :] if not year_first else ""
    found = set()
    spans = _spans(text)
    for hit in re.finditer(re.escape(literal), text):
        first, last, line_start, line_end = _around(spans, hit.start(), hit.end())
        before, after = text[line_start : hit.start()], tail + text[hit.end() : line_end]
        if year_first:
            # The year ends its line: it stands alone there; the date's line is after.
            reason = "other" if could_be_a_date(before) or could_be_a_date(after) else (
                "alone" if before.strip() else None)
        else:
            reason = _year_after(before, after)
        reason = reason or _year_marker(text, spans, first if year_first else last)
        if reason is None:
            return None
        found.add(reason)
    return _note(found, _SPLIT_NOTES)


# A one-line literal that ends in a year joined to what comes before it only by
# spaces, a comma or a period ("IV-25 1948", "IV-25, 1948", "25.IV, 1948"); a
# semicolon or a colon between them is not that ("IV-25; 1948").
_ONE_LINE = re.compile(rf"(?P<date>.*?[^\s,;:])(?:\s*[,.]\s*|\s+)(?P<year>{YEAR_TOKEN})")
ONE_LINE_OTHER_DATE = "one_line_holds_another_date"
ONE_LINE_NOT_ALONE = "one_line_year_not_alone"
ONE_LINE_MEASUREMENT = "one_line_year_may_be_a_measurement"
ONE_LINE_DETERMINATION = "one_line_year_may_be_a_determination"
_ONE_LINE_NOTES = {"alone": ONE_LINE_NOT_ALONE, MEASUREMENT: ONE_LINE_MEASUREMENT,
    DETERMINATION: ONE_LINE_DETERMINATION, "other": ONE_LINE_OTHER_DATE}


def one_line_literal(literal: str) -> tuple[str, str] | None:
    """A literal of one line that ends in a year (four digits, or two after an
    apostrophe) joined to what comes before it only by spaces, a comma or a period:
    what comes before (the date that states no year, if the date parser reads it
    as one) and the year. A period, comma or semicolon after the year is left off
    (`one_line_problem` judges it, and a colon). None for any other literal."""
    text = literal.strip()
    if len(text.splitlines()) != 1:
        return None
    hit = _ONE_LINE.fullmatch(_unmarked(text))
    return (hit["date"], hit["year"]) if hit else None


def one_line_problem(literal: str, text: str) -> str | None:
    """Why the one-line literal, a date and then its year, is not one date where it
    stands in the text (a note: `one_line_year_not_alone`,
    `one_line_year_may_be_a_measurement`, `one_line_year_may_be_a_determination` or
    `one_line_holds_another_date`), or None when some place of it is clear. The
    rules are those of a year on the line below its date (`split_problem`): nothing
    else on the line could be a date; the year may be followed by a comma,
    semicolon or period and other text, never by a unit, an apostrophe, a dash and
    a number, a second number or a word; and no marker on the line, on the nearest
    line above it or starting the nearest line below it makes the year a
    measurement or a determination's year (`_year_marker`)."""
    quoted = literal.strip()
    tail = quoted[len(_unmarked(quoted)) :]
    found = set()
    spans = _spans(text)
    for hit in re.finditer(re.escape(literal), text):
        _, last, line_start, line_end = _around(spans, hit.start(), hit.end())
        before, after = text[line_start : hit.start()], tail + text[hit.end() : line_end]
        reason = _year_after(before, after) or _year_marker(text, spans, last)
        if reason is None:
            return None
        found.add(reason)
    return _note(found, _ONE_LINE_NOTES)


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
    nothing that could be a date; and no marker may make the year a measurement
    or a determination's year (`_year_marker`: "Alt." above "1900")."""
    found: dict[str, str] = {}
    spans = _spans(text)
    for hit in re.finditer(re.escape(literal), text):
        first, last, line_start, line_end = _around(spans, hit.start(), hit.end())
        before, after = text[line_start : hit.start()], text[hit.end() : line_end]
        if not after.strip() and last + 1 < len(spans) and not could_be_a_date(before):
            year = _bare_year(text[slice(*spans[last + 1])])
            if year and not _year_marker(text, spans, last + 1):
                found.setdefault(year, "next_line")
        if not before.strip() and first > 0 and not could_be_a_date(after):
            year = _bare_year(text[slice(*spans[first - 1])])
            if year and not _year_marker(text, spans, first - 1):
                found.setdefault(year, "previous_line")
    if len(found) != 1:
        return None
    year, where = next(iter(found.items()))
    return year, where
