"""Deterministic validators among the stage 7 harness tools (PRD HAR-006).

`date_parser` reads a date literal by the owner's rules (G24 as amended by
G29): it returns every reading the notation allows, at the precision written
and within the plausible years, and the harness settles which one the
evidence supports. The notations are `date_notations`' (Roman and written
months in seven languages, ranges, years written first); each reading's
`order` names the rule that matched. `catalog_number_validator` recognizes a
Field Museum insect catalog number. Neither calls a provider, so neither makes a
source call. Neither changes the literal or invents a value, and each answers
only for a literal that occurs in the reading it was copied from.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from functools import partial

from .date_months import MONTH_WORDS_BY_LANGUAGE
from .date_notations import (  # noqa: F401 (ROMAN and ROMAN_MONTHS are re-exported)
    APOSTROPHES,
    AS_YEAR,
    NO_MONTH,
    NO_YEAR,
    NOTATIONS,
    ROMAN,
    ROMAN_MONTHS,
    YEAR,
    month_of,
    normalize,
    ranges,
)
from .domain import LookupStatus
from .harness_tools import ToolResult

EARLIEST_YEAR = 1750  # HAR-006: a plausible year is from 1750 to the current one.
# An English month name or its 3-to-4-letter abbreviation (sep, sept); the month
# words of every language the parser reads are `date_months.MONTH_WORDS`.
MONTH_NAMES = MONTH_WORDS_BY_LANGUAGE["en"]
CATALOG = re.compile(
    r"\s*(?:FMNH[\s#-]*INS[\s#-]*)?(?P<digits>[0-9]{5,9})\s*", re.IGNORECASE
)
_date_result = partial(ToolResult, tool="date_parser", tool_version="date-parser-v2")
_catalog_result = partial(
    ToolResult, tool="catalog_number_validator", tool_version="catalog-number-v1"
)


def date_parser(
    literal: str,
    *,
    source_text: str,
    year_literal: str | None = None,
    date_rules: dict | None = None,
    year_literal_decides: bool = False,
) -> ToolResult:
    """Every reading of a date literal that its notation allows. `source_text`
    is the reading the literal was copied from; `year_literal`, a year the same
    label states elsewhere, is the only year a month and a day alone can take.

    A bare number after a month is its day, or under the century rule also a
    two-digit year (`IV-25`: April 25, or April 1925). By default a year literal
    leaves both readings, which the research harness's explicit-event rules
    (`research_harness/temporal_context.py`, hash-pinned) still read. With
    `year_literal_decides` the year literal is the date's year and `IV-25` beside
    1948 is April 25, 1948 only (field research, `field_research/checks.py`)."""
    version, century, roman_months = _rules(date_rules)
    if literal not in source_text or (
        year_literal is not None and year_literal not in source_text
    ):
        return _date_result(
            outcome=LookupStatus.POLICY, warnings=["literal_not_in_source"]
        )
    text = literal.strip()
    enclosing = _enclosing_tokens(literal, source_text)
    if enclosing or _slide_code(text):
        # No date: a slide-preparation code or a date-shaped part of one
        # (IV-29-68 in IV-29-68-4), or a part of any other hyphen-joined token.
        codes = all(_slide_code(token) for token in enclosing or [text])
        warning = "slide_code" if codes else "part_of_hyphenated_token"
        return _date_result(outcome=LookupStatus.NO_MATCH, warnings=[warning])
    if "\n" in text or "\r" in text:
        # A notation never reads across a line break; a date split over two lines
        # is the research harness's rule (field_research/date_lines.py), which
        # hands this parser one line and the year beside it.
        return _date_result(
            outcome=LookupStatus.NO_MATCH, warnings=["literal_spans_a_line_break"]
        )
    text = normalize(text)
    order, g = next(
        ((o, hit.groupdict()) for o, p in NOTATIONS if (hit := p.fullmatch(text))),
        (None, {}),
    )
    if order is None:
        return _range_reading(text, version, century, roman_months)
    roman = g.get("roman")
    if roman and not roman_months:
        warnings = ["roman_numeral_months_not_enabled"]
        return _date_result(outcome=LookupStatus.NO_MATCH, warnings=warnings)
    # A letter that matches a numeral only under Unicode case rules (U+0130)
    # is none, so the literal is no date.
    month = month_of(g)
    if month is None and order not in NO_MONTH:
        return _date_result(outcome=LookupStatus.NO_MATCH)
    roman_rule = [f"{version}:roman_numeral_months=true"] if roman else []
    found = []  # Each reading with the warning for its missing year, if any.
    shapes = _shapes(order, g, month, century, year_literal, year_literal_decides)
    for shape, m, d, token in shapes:
        year, century_rule, warning, probe = _year(token, version, century)
        if _exists(probe, m, d):
            rules = roman_rule + ([century_rule] if century_rule else [])
            found.append((_reading(shape, year, m, d, century_rule, rules), warning))
    if not found:
        warnings = ["invalid_calendar_date"]
        return _date_result(outcome=LookupStatus.NO_MATCH, warnings=warnings)
    found = [(r, w) for r, w in found if _plausible(r["year"])]
    if not found:
        return _date_result(
            outcome=LookupStatus.NO_MATCH, warnings=["implausible_year"]
        )
    unique = {}  # Identical readings collapse to the first (5-5-48).
    for r, w in found:
        unique.setdefault((r["year"], r["month"], r["day"], *r["rules"]), (r, w))
    readings = [r for r, _ in unique.values()]
    warnings = ["several_readings"] if len(readings) > 1 else []
    if len(readings) > 1 and order in ("numeric", "year-numeric"):
        # Which of the two numbers is the month is not written, and no part
        # over 12 decides it.
        warnings.append("day_month_order_ambiguous")
    warnings += [w for w in dict.fromkeys(w for _, w in unique.values()) if w]
    borrowed = any(r["order"] in AS_YEAR or r["order"] in NO_YEAR for r in readings)
    return _date_result(
        outcome=LookupStatus.AMBIGUOUS if warnings else LookupStatus.SUCCESS,
        parsed={
            "readings": readings,
            "year_literal": year_literal if borrowed else None,
        },
        warnings=warnings,
    )


def _range_reading(
    text: str, version: str, century: int | None, roman_months: bool
) -> ToolResult:
    """A literal no single notation fits, read as a range of two dates (3-5.IX.1946,
    VIII-IX.46, 3.IX-5.X.1946): the start is the reading, its `end` the last day
    or month of the range. Both ends are read by the rules of a single date."""
    candidates = ranges(text)
    if not candidates:
        return _date_result(outcome=LookupStatus.NO_MATCH)
    if len(candidates) > 1:
        warnings = ["range_notation_ambiguous"]
        return _date_result(outcome=LookupStatus.NO_MATCH, warnings=warnings)
    order, start, end = candidates[0]
    if (start.roman or end.roman) and not roman_months:
        warnings = ["roman_numeral_months_not_enabled"]
        return _date_result(outcome=LookupStatus.NO_MATCH, warnings=warnings)
    ends, warnings = [], []
    for spec in (start, end):
        year, century_rule, warning, probe = _year(spec.year, version, century)
        if not _exists(probe, spec.month, spec.day):
            warnings = ["invalid_calendar_date"]
            return _date_result(outcome=LookupStatus.NO_MATCH, warnings=warnings)
        rules = ([f"{version}:roman_numeral_months=true"] if spec.roman else []) + (
            [century_rule] if century_rule else []
        )
        ends.append(_reading(order, year, spec.month, spec.day, century_rule, rules))
        warnings += [warning] if warning else []
    first, last = ends
    if not all(_plausible(r["year"]) for r in ends):
        return _date_result(outcome=LookupStatus.NO_MATCH, warnings=["implausible_year"])
    if first["year"] and last["year"] and _calendar(last) < _calendar(first):
        warnings = ["range_end_before_start"]
        return _date_result(outcome=LookupStatus.NO_MATCH, warnings=warnings)
    first["end"] = {
        key: last[key] for key in ("iso", "year", "month", "day", "precision", "century_rule")
    }
    warnings = list(dict.fromkeys(warnings))
    return _date_result(
        outcome=LookupStatus.AMBIGUOUS if warnings else LookupStatus.SUCCESS,
        parsed={"readings": [first], "year_literal": None},
        warnings=warnings,
    )


def written_range(literal: str) -> bool:
    """Whether the literal is written as a range of two dates, whatever the
    profile's rules (a Roman month or a two-digit year may not be readable yet)."""
    return bool(ranges(normalize(literal)))


def catalog_number_validator(literal: str, *, source_text: str) -> ToolResult:
    """A Field Museum insect catalog number: 5 to 9 digits, optionally after an
    `FMNH INS` prefix, and nothing else. The digits come back as written."""
    if literal not in source_text:
        warnings = ["literal_not_in_source"]
        return _catalog_result(outcome=LookupStatus.POLICY, warnings=warnings)
    if (match := CATALOG.fullmatch(literal)) is None:
        return _catalog_result(outcome=LookupStatus.NO_MATCH)
    parsed = {"catalog_number": match["digits"]}
    return _catalog_result(outcome=LookupStatus.SUCCESS, parsed=parsed)


def _rules(date_rules: dict | None) -> tuple[str, int | None, bool]:
    """The profile's date rules, checked minimally (G24, G29)."""
    if date_rules is None:
        return "", None, False
    version = date_rules.get("version")
    century = date_rules.get("two_digit_year_century")
    roman = date_rules.get("roman_numeral_months", False)
    if (
        not isinstance(version, str)
        or type(roman) is not bool
        or not (century is None or (type(century) is int and century % 100 == 0))
    ):
        raise ValueError(f"malformed date_rules: {date_rules!r}")
    return version, century, roman


def _enclosing_tokens(literal: str, source: str) -> list[str]:
    """The longer hyphen-joined tokens the literal is part of, when it is only
    ever part of one (1946 in 6-Sept-1946); otherwise none."""
    tokens, width = [], len(literal)
    for hit in re.finditer(f"(?={re.escape(literal)})", source):
        start = hit.start()
        # The joined parts either side; those before are matched reversed.
        before = re.match(r"(?:-\w+)*", source[:start][::-1]).group()[::-1]
        after = re.match(r"(?:-\w+)*", source[start + width :]).group()
        if not (before or after):
            return []
        tokens.append(before + literal + after)
    return tokens


def _slide_code(token: str) -> bool:
    """A date-shaped slide-preparation code: a date's three hyphen-joined parts
    and more (IV-29-68-4, 10-6-78-1a)."""
    parts = token.split("-")
    head = "-".join(parts[:3])
    return len(parts) > 3 and any(p.fullmatch(head) for _, p in NOTATIONS)


def _shapes(
    order: str,
    g: dict,
    month: int | None,
    century: int | None,
    year_literal: str | None,
    year_literal_decides: bool = False,
) -> list[tuple[str, int | None, int | None, str | None]]:
    """Each reading's order, month, day and year token (G29)."""
    if order in ("numeric", "year-numeric"):
        a, b = int(g["a"]), int(g["b"])
        first, second = (
            ("month-day-year", "day-month-year")
            if order == "numeric"
            else ("year-month-day", "year-day-month")
        )
        return [(first, a, b, g["y"]), (second, b, a, g["y"])]
    if order not in AS_YEAR and order not in NO_YEAR:
        return [(order, month, int(g["d"]) if g.get("d") else None, g.get("y"))]
    # A month and a day alone: the day, whose year only the year literal gives.
    token = (year_literal or "").strip()
    usable = token if YEAR.fullmatch(token) else None
    if order in NO_YEAR:
        return [(order, month, int(g["d"]), usable)]
    # A bare number after a month: under the century rule also a two-digit year,
    # unless the year literal is decided to be the year ("IV-25" beside 1948 is
    # not also April 1925).
    shapes = [(order, month, int(g["n"]), usable)]
    if century is not None and len(g["n"]) == 2 and not (year_literal_decides and usable):
        shapes.append((AS_YEAR[order], month, None, g["n"]))
    return shapes


def _year(
    token: str | None, version: str, century: int | None
) -> tuple[int | None, str | None, str | None, int]:
    """The year a token states, the century rule it needed, the warning when it
    states none, and the year the calendar check uses. With the year or its
    century unknown the day need only exist in some year that fits: 2000 is a
    leap year, and 2000 + yy is one whenever any century's yy is."""
    if token is None:
        return None, None, "year_missing", 2000
    digits = token.lstrip(APOSTROPHES)
    if len(digits) == 4:
        return int(digits), None, None, int(digits)
    if century is None:
        return None, None, "century_unresolved", 2000 + int(digits)
    year = century + int(digits)
    return year, f"{version}:two_digit_year_century={century}", None, year


def _exists(year: int, month: int | None, day: int | None) -> bool:
    try:
        date(year, 1 if month is None else month, 1 if day is None else day)
    except (ValueError, OverflowError):
        return False
    return True


def _calendar(reading: dict) -> tuple[int, int, int]:
    """A reading's place on the calendar, to order the two ends of a range."""
    return reading["year"], reading["month"] or 1, reading["day"] or 1


def _plausible(year: int | None) -> bool:
    """HAR-006's range check; a reading without a year is not judged."""
    return year is None or EARLIEST_YEAR <= year <= datetime.now(UTC).year


def _reading(
    order: str,
    year: int | None,
    month: int | None,
    day: int | None,
    century_rule: str | None,
    rules: list[str],
) -> dict:
    iso = None
    if year is not None:
        parts = [f"{part:02d}" for part in (month, day) if part is not None]
        iso = "-".join([f"{year:04d}", *parts])
    return {
        "iso": iso,
        "year": year,
        "month": month,
        "day": day,
        "precision": "day" if day else "month" if month else "year",
        "century_rule": century_rule,
        "order": order,
        "rules": rules,
    }
