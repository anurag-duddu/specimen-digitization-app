"""The notations a date literal is read by (G24, G29; HARNESS.md section 8).

Each notation is one named rule: a pattern for the whole literal and the name
the parser records as the reading's `order`, so a trace shows which rule
matched. The list is not a closed one (the owner's G29 answer: the harness
works out "all possible cases"), but each rule is explicit and none guesses:

- A month is a Roman numeral I to XII (when the profile allows it), or a month
  word of the seven languages in `date_months`.
- A day may carry an ordinal (3rd, 1er, 1o) and may be joined to its month by
  "de", "del", "of" or "di" ("14 de septiembre de 1946").
- A year is four digits, or two with or without an apostrophe ('46, 46), which
  the profile's century rule reads.
- A numeric date gives both orders unless a part over 12 fixes it; a year
  written first (1946-04-05) is read the same way and never taken for the ISO
  order.
- A range ("3-5.IX.1946", "VIII-IX.46", "3.IX-5.X.1946") is two dates, the first
  borrowing what it leaves out (the month, the year) from the second.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .date_months import MONTH_WORDS, fold

ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")
ROMAN_MONTHS = {numeral: month for month, numeral in enumerate(ROMAN, 1)}
# A two-digit year's mark, straight or curly.
APOSTROPHES = "'\N{RIGHT SINGLE QUOTATION MARK}\N{LEFT SINGLE QUOTATION MARK}"
# The dash that joins the two ends of a range.
DASHES = "-\N{EN DASH}\N{EM DASH}"

_YEAR = rf"(?P<y>[{APOSTROPHES}]?[0-9]{{2}}|[0-9]{{4}})"
_MARKED_YEAR = rf"(?P<y>[{APOSTROPHES}][0-9]{{2}}|[0-9]{{4}})"
_YEAR4 = "(?P<y>[0-9]{4})"
_NUMBER = "(?P<n>[0-9]{1,2})"  # A day, or under the century rule a year.
_SEP, _AGAIN = r"\s*(?P<sep>[-./])\s*", r"\s*(?P=sep)\s*"
_GAP, _COMMA = r"(?:\s*[-./]\s*|\s+)", r"(?:\s*[-./,]\s*|\s+)"
_DOT = r"\s*[-.]\s*"
_DAY = "(?P<d>[0-9]{1,2})"
# A day's ordinal mark: 3rd, 1er, and the masculine ordinal sign, degree sign or
# plain "o" of the Romance languages (1o, and 1 with either sign).
_ORDINAL = "(?:st|nd|rd|th|er|\N{MASCULINE ORDINAL INDICATOR}|\N{DEGREE SIGN}|o)?"
_DAY_ORDINAL = _DAY + _ORDINAL
# "de", "del", "of", "di" between a day and its month, or a month and its year.
_OF = r"(?:(?:de|del|of|di|da|do)\s+)?"
# Any letters: a month word is looked up folded (accents dropped), so "Aout" and its
# accented spelling are one word.
_NAME = r"(?P<name>[^\W\d_]+)\.?"
# Roman months I to XII. Lowercase only between a day and a year joined by "."
# or "-" (12.x.46): with spaces, 12 x 46 may be a measurement.
_ROMAN = "(?P<roman>" + "|".join(reversed(ROMAN)) + ")"
_UPPER_ROMAN = "(?-i:" + _ROMAN + ")"
_MONTH_SEP = "(?:" + _DOT + r"|\s+)"

# The notations S4 reads under G24 and G29, each fully matching one literal, in
# the order they are tried. "numeric" and "year-numeric" read both orders.
_NOTATIONS = (
    ("month-day-year", _UPPER_ROMAN + _SEP + _DAY + _AGAIN + _YEAR),
    ("month-day", _UPPER_ROMAN + _SEP + _NUMBER),
    ("month-year", _UPPER_ROMAN + _MONTH_SEP + _MARKED_YEAR),
    ("day-month-year", _DAY + _GAP + _UPPER_ROMAN + _GAP + _YEAR),
    ("day-month-year", _DAY + _DOT + _ROMAN + _DOT + _YEAR),
    ("year-month-day", _YEAR4 + _GAP + _UPPER_ROMAN + _GAP + _DAY),
    ("year-month-day", _YEAR4 + _DOT + _ROMAN + _DOT + _DAY),
    ("year-month", _YEAR4 + _MONTH_SEP + _UPPER_ROMAN),
    ("day-month", _DAY + _GAP + _UPPER_ROMAN),
    ("day-month", _DAY + _DOT + _ROMAN),
    ("numeric", "(?P<a>[0-9]{1,2})" + _SEP + "(?P<b>[0-9]{1,2})" + _AGAIN + _YEAR),
    ("year-numeric", _YEAR4 + _SEP + "(?P<a>[0-9]{1,2})" + _AGAIN + "(?P<b>[0-9]{1,2})"),
    ("day-monthname-year", _DAY_ORDINAL + _GAP + _OF + _NAME + _COMMA + _OF + _YEAR),
    ("monthname-day-year", _NAME + _GAP + _DAY_ORDINAL + _COMMA + _YEAR),
    ("monthname-year", _NAME + _COMMA + _OF + _MARKED_YEAR),
    ("monthname-day", _NAME + _GAP + _NUMBER),
    ("day-monthname", _DAY_ORDINAL + _GAP + _OF + _NAME),
    ("year-monthname-day", _YEAR4 + _GAP + _NAME + _GAP + _DAY_ORDINAL),
    ("year-monthname", _YEAR4 + _GAP + _NAME),
    ("year", "(?P<y>[0-9]{4})"),
    ("year", rf"(?P<y>[{APOSTROPHES}][0-9]{{2}})"),
)
NOTATIONS = [(order, re.compile(pattern, re.IGNORECASE)) for order, pattern in _NOTATIONS]
# The orders that name no month, and those that state no year of their own: the
# year literal (a year the same reading writes elsewhere) is the only year they take.
NO_MONTH = frozenset({"numeric", "year-numeric", "year"})
NO_YEAR = frozenset({"day-month", "day-monthname"})
# A bare number after a month is its day, or under the century rule its year.
AS_YEAR = {"month-day": "month-year", "monthname-day": "monthname-year"}
YEAR = re.compile(_YEAR)

# The pieces of a range: what each end may be written as (kind -> patterns). A
# complete date is any notation that states a day, a month and a year.
_PARTS = {
    "day": (_DAY_ORDINAL,),
    "day-month": (
        _DAY + _GAP + _UPPER_ROMAN,
        _DAY + _DOT + _ROMAN,
        _DAY_ORDINAL + _GAP + _OF + _NAME,
    ),
    "month": (_UPPER_ROMAN, _NAME),
    # Next to a month alone, a bare two-digit number is the year.
    "month-year": (_UPPER_ROMAN + _MONTH_SEP + _YEAR, _NAME + _COMMA + _OF + _YEAR),
    "month-day": (_NAME + _GAP + _DAY_ORDINAL,),
    "day-year": (_DAY_ORDINAL + _COMMA + _YEAR,),
}
PARTS = {
    kind: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for kind, patterns in _PARTS.items()
}
COMPLETE = frozenset({
    "month-day-year", "day-month-year", "day-monthname-year", "monthname-day-year",
    "year-month-day", "year-monthname-day",
})
RANGE_DASH = re.compile(f"[{DASHES}]")


def normalize(text: str) -> str:
    """The text a notation is matched against: the punctuation a line or a
    sentence may add after it (a closing period, comma or semicolon) left off.
    Nothing else changes: a letter that is a numeral only under Unicode case
    rules (U+0130) must stay what it is."""
    return text.strip().rstrip(" .,;:")


def month_of(group: dict) -> int | None:
    """The month a matched Roman numeral or month word names."""
    if group.get("roman"):
        return ROMAN_MONTHS.get(group["roman"].upper())
    return MONTH_WORDS.get(fold(group.get("name") or "").lower())


@dataclass(frozen=True)
class Part:
    """One end of a range, as far as its own words state it."""

    kind: str
    month: int | None
    day: int | None
    year: str | None
    roman: bool


@dataclass(frozen=True)
class Spec:
    """One end of a range, completed: what the parser reads a date from."""

    month: int | None
    day: int | None
    year: str | None
    roman: bool


def _part(kind: str, group: dict) -> Part | None:
    month = month_of(group)
    named = bool(group.get("roman") or group.get("name"))
    if named and month is None:
        return None  # A word that is no month.
    return Part(kind, month, int(group["d"]) if group.get("d") else None, group.get("y"),
        bool(group.get("roman")))


def _parts(text: str) -> list[Part]:
    """Every way a fragment of a range reads, by the kind of end it is."""
    found = []
    for order, pattern in NOTATIONS:
        if order in COMPLETE and (hit := pattern.fullmatch(text)):
            found.append(_part("date", hit.groupdict()))
    for kind, patterns in PARTS.items():
        for pattern in patterns:
            if hit := pattern.fullmatch(text):
                found.append(_part(kind, hit.groupdict()))
    return [part for part in dict.fromkeys(found) if part is not None]


def _combine(left: Part, right: Part) -> tuple[str, Spec, Spec] | None:
    """The two ends the fragments make: the first takes the month, or the year,
    that it leaves out from the second."""
    roman = left.roman or right.roman
    if right.kind == "date":
        if left.kind == "date":
            start = Spec(left.month, left.day, left.year, left.roman)
        elif left.kind == "day":
            start = Spec(right.month, left.day, right.year, right.roman)
        elif left.kind in ("day-month", "month-day"):
            start = Spec(left.month, left.day, right.year, left.roman)
        else:
            return None
        return (f"range:{left.kind}..date", start,
            Spec(right.month, right.day, right.year, right.roman))
    if right.kind == "day-year" and left.kind == "month-day":
        return (f"range:{left.kind}..{right.kind}", Spec(left.month, left.day, right.year, roman),
            Spec(left.month, right.day, right.year, roman))
    if right.kind == "month-year":
        if left.kind == "month":
            start = Spec(left.month, None, right.year, left.roman)
        elif left.kind == "month-year":
            start = Spec(left.month, None, left.year, left.roman)
        else:
            return None
        return (f"range:{left.kind}..month-year", start, Spec(right.month, None, right.year, right.roman))
    return None


def ranges(text: str) -> list[tuple[str, Spec, Spec]]:
    """Every distinct way `text` reads as a range of two dates joined by a dash.

    The text is split at each dash; each side must read as an end by itself, and
    the first only borrows what it leaves out from the second."""
    found = []
    for dash in RANGE_DASH.finditer(text):
        left_text = text[: dash.start()].strip(" .,;:")
        right_text = text[dash.end() :].strip(" .,;:")
        if not left_text or not right_text:
            continue
        for left in _parts(left_text):
            for right in _parts(right_text):
                if (pair := _combine(left, right)) is not None and pair not in found:
                    found.append(pair)
    return found
