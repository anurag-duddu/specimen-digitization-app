"""Deterministic validators among the stage 7 harness tools (PRD HAR-006).

`date_parser` reads a date literal by the owner's rules (G24 as amended by
G29): it returns every reading the notation allows, at the precision written
and within the plausible years, and the harness settles which one the
evidence supports. `catalog_number_validator` recognizes a Field Museum insect
catalog number. Neither calls a provider, so neither makes a source call.
Neither changes the literal or invents a value, and each answers only for a
literal that occurs in the reading it was copied from.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from functools import partial

from .domain import LookupStatus
from .harness_tools import ToolResult

MONTHS = (
    *("january", "february", "march", "april", "may", "june"),
    *("july", "august", "september", "october", "november", "december"),
)
# An English month name or its 3-to-4-letter abbreviation (sep, sept).
MONTH_NAMES = {
    n: i for i, full in enumerate(MONTHS, 1) for n in (full[:3], full[:4], full)
}
ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")
EARLIEST_YEAR = 1750  # HAR-006: a plausible year is from 1750 to the current one.
APOSTROPHES = "'’‘"  # A two-digit year's mark, straight or curly.
_YEAR = rf"(?P<y>[{APOSTROPHES}]?[0-9]{{2}}|[0-9]{{4}})"
_MARKED_YEAR = rf"(?P<y>[{APOSTROPHES}][0-9]{{2}}|[0-9]{{4}})"
_NUMBER = "(?P<n>[0-9]{1,2})"  # A day, or under the century rule a year.
_SEP, _AGAIN = r"\s*(?P<sep>[-./])\s*", r"\s*(?P=sep)\s*"
_GAP, _COMMA = r"(?:\s*[-./]\s*|\s+)", r"(?:\s*[-./,]\s*|\s+)"
_DOT = r"\s*[-.]\s*"
_DAY, _NAME = "(?P<d>[0-9]{1,2})", r"(?P<name>[a-z]+)\.?"
# Roman months I to XII. Lowercase only between a day and a year joined by "."
# or "-" (12.x.46): with spaces, 12 x 46 may be a measurement.
_ROMAN = "(?P<roman>" + "|".join(reversed(ROMAN)) + ")"
_UPPER_ROMAN = "(?-i:" + _ROMAN + ")"
# The notations G24 and G29 approve, and no other; "numeric" reads both orders.
NOTATIONS = [
    (order, re.compile(pattern, re.IGNORECASE))
    for order, pattern in (
        ("month-day-year", _UPPER_ROMAN + _SEP + _DAY + _AGAIN + _YEAR),
        ("month-day", _UPPER_ROMAN + _SEP + _NUMBER),
        ("month-year", _UPPER_ROMAN + "(?:" + _DOT + r"|\s+)(?P<y>[0-9]{4})"),
        ("day-month-year", _DAY + _GAP + _UPPER_ROMAN + _GAP + _YEAR),
        ("day-month-year", _DAY + _DOT + _ROMAN + _DOT + _YEAR),
        ("numeric", "(?P<a>[0-9]{1,2})" + _SEP + "(?P<b>[0-9]{1,2})" + _AGAIN + _YEAR),
        ("day-monthname-year", _DAY + _GAP + _NAME + _GAP + _YEAR),
        ("monthname-day-year", _NAME + _GAP + _DAY + _COMMA + _YEAR),
        ("monthname-year", _NAME + _GAP + _MARKED_YEAR),
        ("monthname-day", _NAME + _GAP + _NUMBER),
        ("year", "(?P<y>[0-9]{4})"),
    )
]
# A bare number after a month is its day, or under the century rule its year.
AS_YEAR = {"month-day": "month-year", "monthname-day": "monthname-year"}
YEAR = re.compile(_YEAR)
CATALOG = re.compile(
    r"\s*(?:FMNH[\s#-]*INS[\s#-]*)?(?P<digits>[0-9]{5,9})\s*", re.IGNORECASE
)
_date_result = partial(ToolResult, tool="date_parser", tool_version="date-parser-v1")
_catalog_result = partial(
    ToolResult, tool="catalog_number_validator", tool_version="catalog-number-v1"
)


def date_parser(
    literal: str,
    *,
    source_text: str,
    year_literal: str | None = None,
    date_rules: dict | None = None,
) -> ToolResult:
    """Every reading of a date literal that its notation allows. `source_text`
    is the reading the literal was copied from; `year_literal`, a year the same
    label states elsewhere, is the only year a month and a day alone can take."""
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
    order, g = next(
        ((o, hit.groupdict()) for o, p in NOTATIONS if (hit := p.fullmatch(text))),
        (None, {}),
    )
    roman, name = g.get("roman"), (g.get("name") or "").lower()
    if roman and not roman_months:
        warnings = ["roman_numeral_months_not_enabled"]
        return _date_result(outcome=LookupStatus.NO_MATCH, warnings=warnings)
    month = ROMAN.index(roman.upper()) + 1 if roman else MONTH_NAMES.get(name)
    if order is None or (month is None and order not in ("numeric", "year")):
        return _date_result(outcome=LookupStatus.NO_MATCH)
    roman_rule = [f"{version}:roman_numeral_months=true"] if roman else []
    found = []  # Each reading with the warning for its missing year, if any.
    for shape, m, d, token in _shapes(order, g, month, century, year_literal):
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
    warnings += [w for w in dict.fromkeys(w for _, w in unique.values()) if w]
    borrowed = any(r["order"] in AS_YEAR for r in readings)
    return _date_result(
        outcome=LookupStatus.AMBIGUOUS if warnings else LookupStatus.SUCCESS,
        parsed={
            "readings": readings,
            "year_literal": year_literal if borrowed else None,
        },
        warnings=warnings,
    )


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
) -> list[tuple[str, int | None, int | None, str | None]]:
    """Each reading's order, month, day and year token (G29)."""
    if order == "numeric":
        a, b = int(g["a"]), int(g["b"])
        return [("month-day-year", a, b, g["y"]), ("day-month-year", b, a, g["y"])]
    if order not in AS_YEAR:
        return [(order, month, int(g["d"]) if g.get("d") else None, g.get("y"))]
    # A bare number after a month: the day, whose year only the year literal
    # gives, and under the century rule also a two-digit year.
    token = (year_literal or "").strip()
    shapes = [(order, month, int(g["n"]), token if YEAR.fullmatch(token) else None)]
    if century is not None and len(g["n"]) == 2:
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
