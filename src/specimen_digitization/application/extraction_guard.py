"""A value the owner's written rules call wrong is not stored at extraction.

`harness.apply_candidates` checks that the organiser's quote occurs in the
reading it cites and its literal in the quote. This guard adds three checks on
what a literal means, each resting on a written rule, and nothing else (no
repair, no re-routing, no new product rule). It reads the text of the CITED
reading, decided or raw, since that is the text the literal was taken from:

- Elevation unit. G41 (docs/execution/golive/PLAN.md:99, LAB.md:131-150) fills
  the unit the label writes; "a unit is never guessed"
  (docs/product-requirements/GEOREFERENCING.md:172) and the tick, "ft." and "m"
  give the unit (docs/execution/golive/HARNESS.md:976-977). A number the label marks
  with the other unit does not belong in this field. A bare number is left alone.
- Slide-preparation code. G45 (PLAN.md:103, LAB.md:173-179): in a field no lookup
  checks, a code such as "VI-24-68-7" is not a value of its kind. Only a value that
  is such a code (`field_validators._slide_code`) is refused. A piece of a code
  ("IX" from "IX-17-66-2") is not: what Collection Code may hold is an open owner
  question, so nothing here refuses it. `verbatim_dts` is not checked: there it is
  a finding only, under the coordinator's hold (PLAN.md:227).
- Date. "preparation codes such as 10-6-78-1a or IX-17-66-2 are never dates"
  (GEOREFERENCING.md:173) names whole codes: `date_parser` says `slide_code`. Its
  own written rule (HARNESS.md:648-651) also says `slide_code` for a date-shaped
  part of a code ("IV-29-68" in "IV-29-68-4") and `part_of_hyphenated_token` for a
  part of any other hyphen-joined token. The guard follows the parser on all three.
  Consequences, none of which touches a stored value: the end of a hyphenated year
  range ("1948" in "1948-1950"), a part of a written day range ("10" in
  "10-12 Sept. 1946"), a date touching a hyphen-joined neighbour, a hyphen-written
  day range ("IV-23-25-48") and an unspaced two-date range ("12-IV-48-15-IV-48",
  "IV-23-48-IV-25-48", whole and at each end) are refused; the whole written range
  literal ("10-12 Sept. 1946") and a spaced two-date range are not.

The helpers are the repo's own (`field_validators`), imported unchanged: an edit
there would change the pinned validator's behaviour without moving its hash.
"""

import re

from .domain import LookupStatus
from .field_validators import _slide_code, date_parser

ELEVATION_UNIT = {
    "elevation_from_m": "m",
    "elevation_to_m": "m",
    "elevation_from_ft": "ft",
    "elevation_to_ft": "ft",
}
# The fields no lookup checks (G45), without `verbatim_dts`.
CODE_FREE_FIELDS = frozenset(
    {"collection_code", "habitat", "collection_method", "collectors"}
)
DATE_FIELDS = frozenset({"date_visited_from", "date_visited_to", "date_identified"})

_NUMBER = r"[0-9][0-9,]*(?:\.[0-9]+)?"
_BLANKS = r"[^\S\n]*"  # on the same line: a unit on the next line is not this number's
_TICKS = "'\N{RIGHT SINGLE QUOTATION MARK}\N{PRIME}"  # a tick mark: feet
_MARK = re.compile(
    rf"(?:{_BLANKS}(?P<m>m\b\.?|met(?:er|re)s?\b)|{_BLANKS}(?:ft\b\.?|feet\b|foot\b)"
    rf"|[{_TICKS}](?![0-9A-Za-z]))",
    re.IGNORECASE,
)
# "3300-3500 ft": the mark that ends a range is the unit of both ends.
_RANGE_END = re.compile(
    _BLANKS + r"(?:[-\N{EN DASH}\N{EM DASH}]|to\b)" + _BLANKS + _NUMBER
)


def _written_units(literal: str, text: str) -> list[str]:
    """The unit each whole-number occurrence of `literal` is written with."""
    units = []
    # A whole number: not the tail of 1300 or 3,300, nor the head of 3300.5.
    for hit in re.finditer(
        rf"(?<![0-9])(?<![0-9][.,]){re.escape(literal)}(?![0-9]|[.,][0-9])", text
    ):
        rest = text[hit.end() :]
        mark = _MARK.match(rest)
        if mark is None and (span := _RANGE_END.match(rest)):
            mark = _MARK.match(rest, span.end())
        if mark:
            units.append("m" if mark["m"] else "ft")
    return units


def extraction_refusal(field_key: str, literal: str, text: str) -> str | None:
    """Why `literal`, copied from the cited reading's `text`, is refused as a
    value of `field_key`; None when no rule above refuses it, and when unsure."""
    if unit := ELEVATION_UNIT.get(field_key):
        units = _written_units(literal, text)
        # Refuse only when every unit written for this number is the other one.
        return "elevation_unit_conflict" if units and unit not in units else None
    if field_key in DATE_FIELDS:
        # `date_parser` decides a slide code or a hyphen-joined part without the
        # profile's date rules (it only validates them first, then applies them to
        # a literal that is a date). None are passed: the extraction child process
        # has no profile snapshot, and this answer does not depend on them.
        result = date_parser(literal, source_text=text)
        if result.outcome == LookupStatus.NO_MATCH:
            if "slide_code" in result.warnings:
                return "preparation_code_is_not_a_date"
            if "part_of_hyphenated_token" in result.warnings:
                return "part_of_hyphenated_token_is_not_a_date"
    elif field_key in CODE_FREE_FIELDS:
        if _slide_code(literal.strip()):
            return "slide_preparation_code"
    return None
