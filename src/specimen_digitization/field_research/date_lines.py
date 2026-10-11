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
  - no marker makes the year a measurement or a determination's year: no unit is
    attached right after it ("1948. m", or "1900" above "m"), the nearest line
    above it is not only a marker waiting for its number ("Alt." above "1900"),
    and, for a year on a line of its own, no determination stands on the line
    above it unless that line holds the date ("det. J. Smith" above "1950" above
    "IV-25") (`_year_marker`). A measurement with its own number elsewhere does not
    count ("1948, 1900m"; "4800 ft. IV-25" above "1948"; "m 1200"), nor does a
    Title-case Mt., Ft. or the initial M. before a name (`_unit_here`). On one line,
    a unit after the year or an elevation word before it ("25.IV 1900 m", "Alt.
    1948") makes it a measurement whatever notation reads the date
    (`one_line_year_problem`), and the line above is not asked. A determination
    before the date on its line makes it Date Identified's
    (`determination_before`, `checks.parse_date`'s field rule);
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

from specimen_digitization.application import field_validators
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


# What makes a number a measurement and not a year: a marker attached to it (coordinator's
# ruling of 2026-10-10 on PR #306). Words are matched folded (accents dropped) and in any
# case, in the languages of the month tables.
# - An elevation or depth word stands before its number: alt., altitude (en, fr, pt),
#   altitud, altura (es, pt), altitudine, quota (it), altitudo (la), elev., elevation (en;
#   the es, pt and fr spellings fold to the three below), Hohe, Seehohe, Meereshohe (de,
#   with the umlaut or "oe"), depth, profundidad, profundidade, profondeur, profondita,
#   Tiefe; "El." only with its period ("El" alone is the Spanish article).
# - A unit, or a height above sea level, stands after its number: m, mt, mts, metros,
#   metres, meters, metri, ft, feet, pies, pieds, piedi, Fuss (1900 m, 4800ft, 6000 pies),
#   msnm, m.s.n.m., snm, s.l.m., a.s.l., m.a.s.l.; or a tick (4800'). A distance (5 mi W,
#   3 km) is not one.
_SEA_LEVEL = frozenset({"msnm", "snm", "slm", "asl", "masl"})
_ELEVATION_WORDS = frozenset({
    "alt", "altitude", "altitud", "altura", "altitudine", "altitudo", "quota",
    "elev", "elevation", "elevacion", "elevacao",
    "hohe", "hoehe", "seehohe", "seehoehe", "meereshohe", "meereshoehe",
    "depth", "profundidad", "profundidade", "profondeur", "profondita", "tiefe",
})
_UNITS = frozenset({"m", "mt", "mts", "metro", "metros", "metre", "metres", "meter", "meters", "metri",
    "ft", "feet", "foot", "pies", "pes", "pieds", "piedi", "fuss", "fu\N{LATIN SMALL LETTER SHARP S}"})
TICKS = APOSTROPHES + "\N{PRIME}"
# An elevation or depth word at the end of a text, perhaps with "ca." after it: the
# number after it is the measurement ("Alt. 1900", "Elev.: 1900", "Altitud ca. 1900").
_WORD_AT_END = re.compile(
    r"(?<![^\W\d_])(?:" + "|".join(sorted(_ELEVATION_WORDS, key=len, reverse=True)) + r"|el\.)"
    r"(?:[\s.:]*(?:ca|c|circa|approx|aprox))?[\s.:]*$")
# A determination: det., determ., determinavit, determined, ident., identified (en),
# determino, identificado (es, pt), determinou (pt), determine, identifie (fr, accents
# folded).
_DETERMINATION_WORDS = frozenset({
    "det", "determ", "determinavit", "determined", "determino", "determinou", "determine",
    "ident", "identified", "identificado", "identifie"})
# A collector right after a year on one line: leg., legit, coll., col., colr., collector,
# and the Spanish and Portuguese colector and coletor ("IV-25 1948 leg. Smith"). A
# determination word there is allowed too ("IV-25 1948 det. Smith").
_COLLECTOR_WORDS = frozenset({"leg", "legit", "coll", "col", "colr", "collector", "colector", "coletor"})
# A word of letters, with the periods inside or after it (m.s.n.m., Alt., R.D.).
_TOKEN = re.compile(r"[^\W\d_](?:[^\W\d_]|\.(?=[^\W\d_]))*\.?")
MEASUREMENT, DETERMINATION = "measurement", "determination"


def _first_word(text: str) -> str:
    """The first word of a text that starts with a letter, folded, without its periods."""
    token = _TOKEN.match(fold(text))
    return token.group().replace(".", "") if token else ""


_UNIT_WORDS = _UNITS | _SEA_LEVEL
# The Title-case abbreviations of a place name (Mount, Mounts, Fort, Monte, Puerto),
# written with or without their period, and the initial "M.": before a capitalised name
# they are no unit ("Mt. Apo", "Ft. Collins", "M. Smith").
_PLACE_ABBREVIATIONS = re.compile(r"(?:Mts?|Ft|Mte|Pto)\.?|M\.")


def _unit_here(text: str) -> bool:
    """Whether `text` starts with a unit that belongs to a number before it: a unit or a
    height above sea level, in any case and with or without its periods ("m", "m.",
    "metros", "Metros", "FT.", "MTS.", "MSNM", "M.S.N.M.", "pes"), unless a number of its
    own follows it ("m 1200", "M. 1200", "mt 1800": the unit written before its number,
    as Italian labels do). One waiver: a Title-case Mt., Mts., Ft., Mte. or Pto., or the
    initial M., before a capitalised name is a place or a person ("Mt. Apo", "Ft.
    Collins", "Mts. Rwenzori", "M. Smith"). A unit in lower case or in capitals stays a
    unit whatever follows it ("m R.D. Mitchell", "ft. Coll. Smith", "FT. COLL. SMITH",
    "MT. APO"), and so does a Title-case unit word ("Metro Manila", "Metros San Pedro")."""
    folded = fold(text)
    token = _TOKEN.match(folded)
    if token is None:
        return False
    written = token.group()
    if written.replace(".", "").lower() not in _UNIT_WORDS:
        return False
    rest = folded[token.end() :].lstrip(" \t.)]")
    if rest[:1].isdigit():
        return False
    name = _TOKEN.match(rest)
    return not (_PLACE_ABBREVIATIONS.fullmatch(written) and name and name.group()[0].isupper()
        and name.group().replace(".", "").lower() not in _UNIT_WORDS)


def _unit_after(after: str) -> bool:
    """Whether a unit is attached right after a year, `after` being what follows the
    year on its line: a tick at once (1948'), or, after nothing but spaces, periods,
    commas or an opening bracket, a unit with no number of its own between (1900 m,
    1900m, 1948. m, 1948.ft, 1948, m, 1948 msnm, 1900 M., 1900 (m)) that `_unit_here`
    counts: "1948, M. Smith", "1948 Mt. Apo" and "1948, m 1200" leave the year a year.
    A measurement with a number of its own does not count ("1948, 1900m")."""
    if after and after[0] in TICKS:
        return True
    return _unit_here(after.lstrip(" \t.,(["))


def _word_before(before: str) -> bool:
    """Whether an elevation or depth word stands right before a number, `before`
    being the text before it on its line ("Alt. 1900", "Elev.: 1900")."""
    return bool(_WORD_AT_END.search(fold(before).lower()))


def _awaits_its_number(line: str) -> bool:
    """Whether a line is only a measurement marker, its number on the next line: it
    ends in an elevation or depth word ("Alt.", "Guatemala, Elev.:"), or it holds no
    digit and an elevation or depth word or a unit that `_unit_here` counts ("m.s.n.m.",
    "Metros", "Alt. aprox."; not "E. slope Mt. McKinley"). A line whose marker has its own number
    ("Alt. 1500 m", "Yepocapa, 4800 ft. IV-25") does not."""
    if _word_before(line):
        return True
    if any(ch.isdigit() for ch in line):
        return False
    folded = fold(line)
    for token in _TOKEN.finditer(folded):
        word = token.group().lower().replace(".", "")
        if word in _ELEVATION_WORDS or token.group().lower() == "el." or _unit_here(folded[token.start() :]):
            return True
    return False


def _determination(line: str) -> bool:
    return any(token.lower().replace(".", "") in _DETERMINATION_WORDS for token in _TOKEN.findall(fold(line)))


def _starts_with_a_unit(line: str) -> bool:
    """Whether a line begins with a unit of the number that ends the line above, in any
    spelling the unit table holds and in any case ("m", "metros", "Metros", "FT.",
    "MSNM", "M.S.N.M.", "pes"), by `_unit_here`'s rules: "m 1200" and "M 1200" are
    measurements of their own, and "Mt. Apo" and "M. Smith" are names."""
    return _unit_here(line.lstrip(" \t(["))


def _neighbour(lines: list[str], line: int, step: int) -> int | None:
    """The nearest line above (step -1) or below (step 1) that is not blank."""
    index = line + step
    while 0 <= index < len(lines):
        if lines[index].strip():
            return index
        index += step
    return None


def _unit_follows(after: str, lines: list[str], line: int) -> bool:
    """Whether a unit is attached right after a year that `after` follows on line
    `line`: on its line (`_unit_after`), or, when nothing but punctuation follows it
    there, at the start of the nearest line below that is not blank ("1900" above "m")."""
    if _unit_after(after):
        return True
    below = _neighbour(lines, line, 1)
    return not after.strip(" .,;:") and below is not None and _starts_with_a_unit(lines[below])


def _year_marker(text: str, spans: list[tuple[int, int]], line: int, dated: range, after: str) -> str | None:
    """Why a number that is the year on line `line`, `after` following it there, may
    not be the year of the date on the lines `dated`; None when nothing says so.

    `measurement`: a unit is attached right after it (`_unit_follows`), or the nearest
    line above it that is not blank is only a marker waiting for its number
    (`_awaits_its_number`: "Alt." above "1900"). A measurement that has its own number,
    after a comma on the year's line or on the line above, does not count ("1948,
    1900m"; "4800 ft. IV-25" above "1948").

    `determination`: a determination stands before the year, on the nearest line above
    it that is not blank and does not hold the date: "det. J. Smith" above "1950" above
    "IV-25" makes 1950 the determination's year. A determination after the year
    ("1948, det. R.D. Mitchell") does not, nor one on the date's own line ("det. J. Smith
    IV-25" above "1950": the date written whole, which `checks.parse_date` gives to Date
    Identified only)."""
    lines = [text[start:end] for start, end in spans]
    above = _neighbour(lines, line, -1)
    if _unit_follows(after, lines, line) or (above is not None and _awaits_its_number(lines[above])):
        return MEASUREMENT
    if line not in dated and above is not None and above not in dated and _determination(lines[above]):
        return DETERMINATION
    return None


# The line breaks str.splitlines() splits at: one definition of a line for the date
# parser (`literal_spans_a_line_break`) and these rules. (step._excerpt_span and the
# taxon helpers checks.word_before, token_before and token_after find a quote's own
# line by "\n" alone; they read no date.)
_BREAK = re.compile("\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}]")


def places(literal: str, text: str) -> list[re.Match]:
    """Where the literal stands in the text as a token of its own: not glued to a
    letter or a digit before its first character or after its last, when that
    character is one ("IV-25 1948" stands in "Lot IV-25 1948", not in "XIV-25 1948";
    "25.IV.1948" not in "125.IV.1948" or "25.IV.19489")."""
    found = []
    for hit in re.finditer(re.escape(literal), text):
        before = text[hit.start() - 1] if hit.start() else ""
        after = text[hit.end()] if hit.end() < len(text) else ""
        if (literal[:1].isalnum() and before.isalnum()) or (literal[-1:].isalnum() and after.isalnum()):
            continue
        found.append(hit)
    return found


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
    with nothing after it but periods, commas, semicolons or colons: the other line
    (the date that states no year, if it is one) and the year without its mark.
    None for any other literal. Whether the two lines are adjacent, and whether a
    mark after a year below the date is allowed (a colon is not), is
    `split_problem`'s."""
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


def _year_after(before: str, after: str, collectors: bool = False) -> str | None:
    """Why a year that follows its date (starting the next line, or later on the
    date's own line) is not the date's year, from the text before the date and
    after the year on their lines: "other" (something there could be a date) or
    "alone" (the year is followed by more than a comma, semicolon or period and
    other text); None when neither. With `collectors` (one line), a collector or a
    determination after a space is like a comma ("IV-25 1948 leg. Smith", "IV-25 1948
    det. Smith"): which date the line is, collecting or determination, is
    `checks.parse_date`'s field rule (`determination_before`)."""
    if could_be_a_date(before):
        return "other"
    if not after.strip() or (after[0] in ",;." and not after[1:2].isdigit()):
        return "other" if could_be_a_date(after[1:]) else None
    if collectors and after[:1].isspace() and _first_word(after.lstrip()).lower() in (
            _COLLECTOR_WORDS | _DETERMINATION_WORDS):
        return "other" if could_be_a_date(after) else None
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
    for hit in places(literal, text):
        first, last, line_start, line_end = _around(spans, hit.start(), hit.end())
        before, after = text[line_start : hit.start()], tail + text[hit.end() : line_end]
        if year_first:
            # The year ends its line: it stands alone there; the date's line is after.
            reason = "other" if could_be_a_date(before) or could_be_a_date(after) else (
                "alone" if before.strip() else None)
            year_line, date_line, after_year = first, last, lines[0][len(_unmarked(lines[0])) :]
        else:
            reason = _year_after(before, after)
            year_line, date_line, after_year = last, first, after
        reason = reason or _year_marker(text, spans, year_line, range(date_line, date_line + 1), after_year)
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
_ONE_LINE_NOTES = {"alone": ONE_LINE_NOT_ALONE, MEASUREMENT: ONE_LINE_MEASUREMENT,
    "other": ONE_LINE_OTHER_DATE}


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
    `one_line_year_may_be_a_measurement` or `one_line_holds_another_date`), or None
    when some place of it is clear. The rules are those of a year on the line below its
    date (`split_problem`), with these differences: nothing else on the line could be
    a date; the year may be followed by a comma, semicolon or period and other text,
    or by a collector or a determination ("1948 leg. Smith", "1948 leg. et det.
    Smith", "1948 det. Smith"), never by a unit, an apostrophe, a dash and a number, a
    second number, another word or a colon; and no unit is attached right after it
    (`_unit_follows`: "IV-25 1948. m"). The line above is not asked ("Alt. 1500 m"
    above "IV-25 1948" reads)."""
    quoted = literal.strip()
    tail = quoted[len(_unmarked(quoted)) :]
    found = set()
    spans = _spans(text)
    lines = [text[start:end] for start, end in spans]
    for hit in places(literal, text):
        _, last, line_start, line_end = _around(spans, hit.start(), hit.end())
        before, after = text[line_start : hit.start()], tail + text[hit.end() : line_end]
        reason = _year_after(before, after, collectors=True) or (
            MEASUREMENT if _unit_follows(after, lines, last) else None)
        if reason is None:
            return None
        found.add(reason)
    return _note(found, _ONE_LINE_NOTES)


# The year a one-line literal ends with (four digits, or two with or without an
# apostrophe) or starts with (four digits).
_YEAR_AT_END = re.compile(rf"(?<![0-9])(?:[{APOSTROPHES}]?[0-9]{{2}}|[0-9]{{4}})$")
_YEAR_AT_START = re.compile(r"[0-9]{4}(?![0-9])")


def one_line_year_problem(literal: str, text: str) -> str | None:
    """`one_line_year_may_be_a_measurement` when the year a one-line literal ends or
    starts with is a measurement at every place the literal stands in the text, whatever
    notation reads it: a unit attached right after it (`_unit_follows`: "25.IV 1900 m",
    "25 IV 1900 M.", "25 IV 1900 (m)", "25.IV 1900 m R.D. Mitchell") or an elevation or
    depth word right before it (`_word_before`: "Alt. 1948"); otherwise None. The line
    above is not asked: "Alt. 1500 m" above "25 IV 1948" leaves 1948 a year."""
    quoted = literal.strip()
    if not quoted or len(quoted.splitlines()) != 1:
        return None
    unmarked = _unmarked(quoted)
    at_end, at_start = bool(_YEAR_AT_END.search(unmarked)), bool(_YEAR_AT_START.match(unmarked))
    if not (at_end or at_start):
        return None
    tail = quoted[len(unmarked) :]
    spans = _spans(text)
    lines = [text[start:end] for start, end in spans]
    found = False
    for hit in places(literal, text):
        _, last, line_start, line_end = _around(spans, hit.start(), hit.end())
        before, after = text[line_start : hit.start()], tail + text[hit.end() : line_end]
        if not ((at_end and _unit_follows(after, lines, last)) or (at_start and _word_before(before))):
            return None
        found = True
    return ONE_LINE_MEASUREMENT if found else None


def determination_before(literal: str, text: str) -> bool:
    """Whether a determination stands before the literal on its (first) line at every
    place it stands in the text ("det. J. Smith 1950", "det. 25.IV.1950", "det. J.
    Smith, IV-25 1950"): the date is then the determination's. A determination after
    the date ("25.IV.1948 leg. et det. J. Smith") or on another line does not count."""
    spans = _spans(text)
    found = places(literal, text)
    return bool(found) and all(
        _determination(text[spans[_line_of(spans, hit.start())][0] : hit.start()]) for hit in found)


def written_range(literal: str) -> bool:
    """Whether the literal writes a range of two dates (G44 never copies its start to
    its end): whole ("3-5.IX.1946"), or with its year on the line beside it or after
    it on its line ("3-5.IX\\n1946", "3-5.IX, 1946")."""
    parts = split_literal(literal) or one_line_literal(literal)
    return field_validators.written_range(literal) or (
        parts is not None and field_validators.written_range(parts[0], year=parts[1]))


def _bare_year(line: str) -> str | None:
    hit = _BARE_YEAR.fullmatch(line)
    return hit["y"] if hit and _plausible(hit["y"]) else None


def _after_bare(line: str) -> str:
    """What follows the year on a line that holds nothing but it (a period, a comma)."""
    hit = _BARE_YEAR.fullmatch(line)
    return line[hit.end("y") :] if hit else ""


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
    for hit in places(literal, text):
        first, last, line_start, line_end = _around(spans, hit.start(), hit.end())
        before, after = text[line_start : hit.start()], text[hit.end() : line_end]
        if not after.strip() and last + 1 < len(spans) and not could_be_a_date(before):
            line = text[slice(*spans[last + 1])]
            year = _bare_year(line)
            if year and not _year_marker(text, spans, last + 1, range(first, last + 1), _after_bare(line)):
                found.setdefault(year, "next_line")
        if not before.strip() and first > 0 and not could_be_a_date(after):
            line = text[slice(*spans[first - 1])]
            year = _bare_year(line)
            if year and not _year_marker(text, spans, first - 1, range(first, last + 1), _after_bare(line)):
                found.setdefault(year, "previous_line")
    if len(found) != 1:
        return None
    year, where = next(iter(found.items()))
    return year, where
