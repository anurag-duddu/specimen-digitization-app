"""Field model v2: the key set, part names, bases and the v1 adapter.

The design is `docs/product-requirements/PRD.md`, section "Field model v2: four
groups" (owner-confirmed groups of 2026-10-08; names are descriptive). This
module is the first code for it and is purely additive: standard library only,
no I/O, no clock, no randomness, and nothing imports it yet. It deliberately
imports nothing from the rest of the package, because several sources are
byte-pinned by tests (`application/domain.py`, `projection.py`, `storage.py`,
`active_graph.py`, and the validator closure of `research_harness/`); a pure
module cannot disturb them and can be tested without loading them.

It provides:

- the nine v2 values, their parts and the group of each, as data;
- a strict parser and formatter for part paths (`<value>/<part>[/n]`);
- the basis vocabulary (`label`, `derived`, `inferred`) and `display_basis`,
  which computes a display-only basis for records written before v2;
- `v1_mirror`, the adapter from v2 parts to the twenty v1 "mirror" keys that
  stay mandatory while v1 records and the publish operation remain in use.

Every number is a `Decimal`; a `float` is refused.

What the adapter reproduces from live code (each checked against the source
named):

- `application/derivations.py`: `METRES_PER_FOOT`; `_text` (a value copied as
  stated keeps its digits, a converted one is rounded to 0.01 with
  round-half-even, and trailing zeros are dropped); `elevation_derivations`
  (the label's own number fills both ends of its unit and the other unit is
  converted).
- `research_harness/evidence.py`: `_convert` (metres to feet at 34 digits,
  round-half-even); the 0.01 rounding of `display_decimal` but not its text
  form; the G44 copy of a single collecting date to the same precision and the
  range-order check; `dts_policy_resolution` and `missing_irn_resolution`
  (`verbatim_dts` and `identified_by_irn` stay unfilled).
- `research_harness/prompts/specimen_geography-v9.txt`: an island is not a
  province, a municipality is not a county, no county is invented, and the
  verbatim locality is kept as `precise_location`.

Where two live paths disagree, this module follows `derivations.py`:
`_text` drops trailing zeros ("1950.7") and `display_decimal` keeps them
("1950.70"). The field-research path of PR #284 calls `elevation_derivations`,
which is why. Compare elevation text from either path as `Decimal`, never as
a string.

New here, not live behaviour (choices for a reviewer to confirm):

- `elevation/kind` is required, and an above or below limit fills one bound
  (live v1 has no one-sided elevation);
- `taxon` fills only from `taxon/accepted`; the part names, the place-tree
  levels and the role each level plays are this module's own;
- feet are recovered exactly from the stored metres as `metres / 0.3048`;
- `collectors/1..n` are joined with " & ", a joiner `research_harness/people.py`
  accepts; live code has no join of separate names, and the label's own joiner
  is lost;
- `ids/catalog_number` is copied as given and not validated. Live
  `catalog_literal` (an optional "FMNH INS" prefix, then 5 to 9 digits, and the
  digits come back) is not applied, so a caller passes the digits: an input
  such as "FMNH-INS 4486784" passes through unchanged;
- the optional `bases` argument of `v1_mirror` (see there).
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import StrEnum
from typing import Final

__all__ = [
    "BASES",
    "COLLECTORS_JOINER",
    "LOCATION_ROOT",
    "METRES_PER_FOOT",
    "V1_KEYS",
    "V1_SOURCES",
    "VALUE_GROUP",
    "VALUE_SPECS",
    "Basis",
    "ElevationKind",
    "ElevationUnit",
    "FieldModelError",
    "Group",
    "PartPath",
    "ValueName",
    "ValueSpec",
    "display_basis",
    "format_part_path",
    "group_of",
    "parse_part_path",
    "v1_mirror",
]


class FieldModelError(ValueError):
    """A part path, a part value or a basis input the field model refuses."""


class Group(StrEnum):
    """The four groups of the PRD table "The four groups"."""

    IDS = "ids"
    COLLECTION = "collection"
    DATE = "date"
    TAXA = "taxa"


class ValueName(StrEnum):
    """The nine v2 values. The first segment of a part path is one of these,
    never a group name: `elevation/unit` and `collectors/1` are valid."""

    IDS = "ids"
    LOCATION = "location"
    ELEVATION = "elevation"
    COLLECTORS = "collectors"
    HABITAT = "habitat"
    COLLECTION_METHOD = "collection_method"
    WHEN = "when"
    TAXON = "taxon"
    IDENTIFIED_BY = "identified_by"


class Basis(StrEnum):
    """How a value, or a part of one, was obtained (PRD "How every value is
    recorded"): the label states it, it follows from a stated fact, rule or
    lookup, or it is a probable but uncertain conclusion."""

    LABEL = "label"
    DERIVED = "derived"
    INFERRED = "inferred"


BASES: Final = tuple(Basis)


class ElevationKind(StrEnum):
    """The kinds of one elevation value (PRD "Value kinds")."""

    POINT = "point"
    RANGE = "range"
    ABOVE = "above"
    BELOW = "below"


class ElevationUnit(StrEnum):
    """The unit the label stated. Stored numbers are metres either way."""

    M = "m"
    FT = "ft"


# Shapes of the part names a value takes.
_FIXED = "fixed"  # <value>/<part>, the part from a fixed set (may contain "/")
_LIST = "list"  # <value>/<n>, n from 1
_TREE = "tree"  # <value>/<level>[/<n>], a level name; n from 2 for repeats

LOCATION_ROOT: Final = "verbatim"  # the locality as read, the root of the tree


@dataclass(frozen=True)
class ValueSpec:
    """One v2 value: its group and the names its parts may take."""

    name: ValueName
    group: Group
    shape: str
    parts: tuple[str, ...] = ()
    note: str = ""


VALUE_SPECS: Final[Mapping[ValueName, ValueSpec]] = {
    spec.name: spec
    for spec in (
        ValueSpec(
            ValueName.IDS,
            Group.IDS,
            _FIXED,
            ("catalog_number", "collection"),
            "catalogue number as text, leading zeros kept; the collection reference",
        ),
        ValueSpec(
            ValueName.LOCATION,
            Group.COLLECTION,
            _TREE,
            (LOCATION_ROOT,),
            "a tree: `verbatim` is the locality as read, the root; every other "
            "part is a level name such as `country`, `island`, `province`, "
            "`department`, `municipality` or `place`. A level that repeats is "
            "`<level>/<n>` from 2; the first has no index. The set of levels is "
            "not fixed, because it differs by country.",
        ),
        ValueSpec(
            ValueName.ELEVATION,
            Group.COLLECTION,
            _FIXED,
            ("from", "to", "unit", "kind"),
            "bounds in exact metres; `unit` is the unit the label stated "
            "(m or ft); `kind` is point, range, above or below",
        ),
        ValueSpec(
            ValueName.COLLECTORS,
            Group.COLLECTION,
            _LIST,
            note="the recorded names, collectors/1 to collectors/n, in written order",
        ),
        ValueSpec(
            ValueName.HABITAT,
            Group.COLLECTION,
            _FIXED,
            ("text",),
            "read as written; no lookup applies",
        ),
        ValueSpec(
            ValueName.COLLECTION_METHOD,
            Group.COLLECTION,
            _FIXED,
            ("text",),
            "read as written; no lookup applies",
        ),
        ValueSpec(
            ValueName.WHEN,
            Group.DATE,
            _FIXED,
            (
                "collected/start",
                "collected/end",
                "collected/time",
                "identified/start",
            ),
            "the reusable date value of the collecting event and the identification",
        ),
        ValueSpec(
            ValueName.TAXON,
            Group.TAXA,
            _FIXED,
            ("name", "accepted", "rank", "authorship", "status"),
            "`name` as written; the rest is the resolved taxonomy",
        ),
        ValueSpec(
            ValueName.IDENTIFIED_BY,
            Group.TAXA,
            _LIST,
            note="the recorded determiner names, identified_by/1 to identified_by/n",
        ),
    )
}
VALUE_GROUP: Final[Mapping[ValueName, Group]] = {
    name: spec.group for name, spec in VALUE_SPECS.items()
}


def group_of(value: str) -> Group:
    """The group a value belongs to; the argument is a value name, not a group."""
    try:
        return VALUE_GROUP[ValueName(value)]
    except ValueError:
        raise FieldModelError(f"unknown value {value!r}") from None


_INDEX = re.compile(r"[1-9][0-9]{0,5}")
_LEVEL = re.compile(r"[a-z]+(?:_[a-z]+)*")


@dataclass(frozen=True)
class PartPath:
    """A parsed part name: `value`, then a `part` (a fixed part or a location
    level, `None` for a list entry) and an `index` (a list entry, or the n-th
    repeat of a location level from 2)."""

    value: ValueName
    part: str | None = None
    index: int | None = None

    @property
    def group(self) -> Group:
        return VALUE_GROUP[self.value]

    @property
    def path(self) -> str:
        pieces = [self.value.value]
        if self.part is not None:
            pieces.append(self.part)
        if self.index is not None:
            pieces.append(str(self.index))
        return "/".join(pieces)

    def __str__(self) -> str:
        return self.path


def _index(text: str, path: str) -> int:
    if _INDEX.fullmatch(text) is None:
        raise FieldModelError(f"bad index {text!r} in {path!r}: a whole number from 1")
    return int(text)


def parse_part_path(path: str) -> PartPath:
    """Parse `<value>/<part>[/n]`, refusing unknown values, empty or unknown
    parts, bad indexes, and any spelling other than the canonical one."""
    if not isinstance(path, str):
        raise FieldModelError("a part path is text")
    if not path or not path.isascii() or any(ch.isspace() for ch in path):
        raise FieldModelError(f"bad part path {path!r}: no spaces, non-ASCII or empty text")
    head, slash, rest = path.partition("/")
    try:
        value = ValueName(head)
    except ValueError:
        raise FieldModelError(f"unknown value {head!r} in {path!r}") from None
    if not slash or not rest:
        raise FieldModelError(f"{path!r} names no part: write {head}/<part>")
    segments = rest.split("/")
    if any(not segment for segment in segments):
        raise FieldModelError(f"empty part in {path!r}")
    spec = VALUE_SPECS[value]
    if spec.shape == _FIXED:
        if rest not in spec.parts:
            raise FieldModelError(
                f"unknown part {rest!r} of {head!r}: one of {', '.join(spec.parts)}"
            )
        return PartPath(value, rest)
    if spec.shape == _LIST:
        if len(segments) != 1:
            raise FieldModelError(f"{head!r} entries are {head}/<n>, got {path!r}")
        return PartPath(value, None, _index(segments[0], path))
    level = segments[0]
    if _LEVEL.fullmatch(level) is None:
        raise FieldModelError(f"bad location level {level!r} in {path!r}")
    if len(segments) == 1:
        return PartPath(value, level)
    if len(segments) > 2:
        raise FieldModelError(f"too many segments in {path!r}")
    if level == LOCATION_ROOT:
        raise FieldModelError("the verbatim locality is the root and takes no index")
    index = _index(segments[1], path)
    if index < 2:
        raise FieldModelError(
            f"{path!r}: the first {level} has no index; repeats start at {level}/2"
        )
    return PartPath(value, level, index)


def format_part_path(
    value: str, part: str | None = None, *, index: int | None = None
) -> str:
    """The canonical path of a part, validated by parsing it back:
    `format_part_path("location", "place", index=2)` is `location/place/2`,
    `format_part_path("collectors", index=1)` is `collectors/1`."""
    pieces = [str(value)]
    if part is not None:
        pieces.append(part)
    if index is not None:
        if isinstance(index, bool) or not isinstance(index, int):
            raise FieldModelError("an index is a whole number")
        pieces.append(str(index))
    return parse_part_path("/".join(pieces)).path


# ---------------------------------------------------------------------------
# Basis for records written before v2 (display only).
# ---------------------------------------------------------------------------

# A unit mark counts only right after a digit and not inside a longer word:
# "6400'", "6400 ft.", "1950.72 m" lose it; "Mindanao" keeps its "m".
_UNIT_MARK = re.compile(
    r"(?<=[0-9])(?:(?:ft|feet|foot|metres?|meters?|m)\.?(?![^\W\d_])|['′’\"″])"
)


# A plain number with no leading zeros to lose (an identifier such as "0012345"
# is not a quantity), comparable by value.
_PLAIN_NUMBER = re.compile(r"[+-]?(?:0|[1-9][0-9]{0,39})(?:\.[0-9]{1,20})?")


def _comparable(text: str) -> str:
    """The text with case, spacing and unit marks ignored, and a plain number
    in its canonical form, so that 6400 and 6400.00, or 1950.7 and 1950.70,
    agree while 1950.7248 and 1950.72 do not."""
    squeezed = "".join(unicodedata.normalize("NFKC", text).casefold().split())
    stripped = _UNIT_MARK.sub("", squeezed)
    if _PLAIN_NUMBER.fullmatch(stripped) is None:
        return stripped
    with localcontext() as context:
        context.prec = 80  # wide enough that normalize never rounds
        number = Decimal(stripped).normalize()
    return "0" if number == 0 else format(number, "f")


def _present(label: str, text: str | None) -> str | None:
    if text is None:
        return None
    if not isinstance(text, str):
        raise FieldModelError(f"{label} is text or None")
    return text if text.strip() else None


def display_basis(
    layer: str | None,
    literal: str | None,
    parsed: str | None,
    normalized: str | None,
) -> Basis | None:
    """The basis to show for a record written before v2, or `None` to show
    nothing. Display only and approximate (PRD "Basis is a separate thing from
    the layer"):

    - layer `verbatim` gives `label`; layer `derived` gives `derived`;
    - layer `settled` gives `label` when the values that are present (literal,
      parsed, normalized) agree once case, spacing and unit marks are ignored
      ("6400'" parsed as 6400; "Mindanao" confirmed by a lookup), and
      `derived` when they differ ("P.I." settled as Philippines, "Chimaltenago"
      settled as Chimaltenango);
    - nothing where the stored values cannot tell the two apart: fewer than two
      values present, or agreeing values with no literal to say that the label
      itself states them (two machine outputs that agree prove nothing about
      the wording);
    - an old record is never `inferred`.

    A plain number is compared by value, so "6400" and "6400.00" agree (live
    `display_decimal` writes the second form for a written "6400'"), and
    "1950.7248" and "1950.72" differ. Leading zeros are not dropped: an
    identifier "0012345" and "12345" differ.
    """
    if layer == "verbatim":
        return Basis.LABEL
    if layer == "derived":
        return Basis.DERIVED
    if layer != "settled":
        return None
    stored = {
        name: _present(name, text)
        for name, text in (("literal", literal), ("parsed", parsed), ("normalized", normalized))
    }
    present = {name: text for name, text in stored.items() if text is not None}
    if len(present) < 2:
        return None
    if len({_comparable(text) for text in present.values()}) > 1:
        return Basis.DERIVED
    return Basis.LABEL if "literal" in present else None


# ---------------------------------------------------------------------------
# The v1 mirror.
# ---------------------------------------------------------------------------

# The twenty native v1 keys, in the native order (`FieldKey`, `domain.MANDATORY`).
V1_KEYS: Final = (
    "fmnh_ins_number",
    "collection_code",
    "country",
    "province_state",
    "county",
    "city",
    "precise_location",
    "elevation_from_m",
    "elevation_to_m",
    "elevation_from_ft",
    "elevation_to_ft",
    "habitat",
    "collection_method",
    "date_visited_from",
    "date_visited_to",
    "collectors",
    "verbatim_dts",
    "taxon",
    "identified_by_irn",
    "date_identified",
)

# Where each v1 key comes from, as data (PRD "v1 keys from v2 parts"), after the
# live code where it differs from that table.
V1_SOURCES: Final[Mapping[str, str]] = {
    "fmnh_ins_number": "ids/catalog_number, as text with leading zeros kept",
    "collection_code": "ids/collection",
    "country": "location/country",
    "province_state": "the one location node at a first-level administrative role "
    "(province, state, department, prefecture); an island is not one",
    "county": "the one location node at a second-level administrative role "
    "(county, district); a municipality is not one; never invented",
    "city": "the one location node at a settlement role (city, town, village, settlement)",
    "precise_location": "location/verbatim, the locality as read, as live v1 keeps it",
    "elevation_from_m": "elevation, metres: a point fills from and to alike, a range "
    "its two bounds, above only from, below only to",
    "elevation_to_m": "as elevation_from_m",
    "elevation_from_ft": "the same elevation in feet: 1 ft = 0.3048 m, the stated "
    "feet when the label gave feet, else converted to 0.01 (round-half-even)",
    "elevation_to_ft": "as elevation_from_ft",
    "habitat": "habitat/text",
    "collection_method": "collection_method/text",
    "date_visited_from": "when/collected/start",
    "date_visited_to": "when/collected/end, else when/collected/start (G44)",
    "collectors": "collectors/1..n joined with COLLECTORS_JOINER",
    "verbatim_dts": "never filled: waits for the owner's policy, as in live v1",
    "taxon": "taxon/accepted; the name as written is not a resolved taxon",
    "identified_by_irn": "never filled: waits for EMu Parties (G16)",
    "date_identified": "when/identified/start",
}

METRES_PER_FOOT: Final = Decimal("0.3048")  # exact, by the 1959 definition
COLLECTORS_JOINER: Final = " & "  # accepted by the live collector-list checks

_HUNDREDTH = Decimal("0.01")
_ELEVATION_NUMBER = re.compile(r"[+-]?\d{1,40}(?:\.\d{1,20})?")
_DATE = re.compile(r"\d{4}(?:-\d{2}(?:-\d{2})?)?")

# Parts copied as written to one v1 key.
_COPIED: Final = {
    "ids/catalog_number": "fmnh_ins_number",
    "ids/collection": "collection_code",
    "habitat/text": "habitat",
    "collection_method/text": "collection_method",
    "taxon/accepted": "taxon",
    "location/verbatim": "precise_location",
}
_DATE_PARTS: Final = ("when/collected/start", "when/collected/end", "when/identified/start")

# Location levels that fill a v1 key, by role and never by name alone.
_COUNTRY_LEVELS: Final = ("country",)
_FIRST_ADMIN_LEVELS: Final = ("province", "state", "department", "prefecture")
_SECOND_ADMIN_LEVELS: Final = ("county", "district")
_SETTLEMENT_LEVELS: Final = ("city", "town", "village", "settlement")


def _text(path: str, raw: object) -> str:
    if not isinstance(raw, str):
        raise FieldModelError(f"{path}: the value is text, not {type(raw).__name__}")
    if not raw.strip():
        raise FieldModelError(f"{path}: the value is empty")
    return raw


def _decimal(path: str, raw: object) -> Decimal:
    if isinstance(raw, bool) or isinstance(raw, float):
        raise FieldModelError(f"{path}: a number is a Decimal, an int or plain decimal text")
    if isinstance(raw, int):
        raw = str(raw)
    if isinstance(raw, Decimal):
        if not raw.is_finite():
            raise FieldModelError(f"{path}: not a finite number")
        raw = format(raw, "f")
    if not isinstance(raw, str) or _ELEVATION_NUMBER.fullmatch(raw) is None:
        raise FieldModelError(f"{path}: not a plain decimal number")
    return Decimal(raw)


def _enum(path: str, raw: object, kind: type[StrEnum]):
    try:
        return kind(raw)
    except ValueError:
        options = ", ".join(member.value for member in kind)
        raise FieldModelError(f"{path}: {raw!r} is not one of {options}") from None


def _iso(path: str, raw: object) -> str:
    text = _text(path, raw)
    if _DATE.fullmatch(text) is None:
        raise FieldModelError(f"{path}: {text!r} is not YYYY, YYYY-MM or YYYY-MM-DD")
    try:
        _bounds(text)
    except ValueError:
        raise FieldModelError(f"{path}: {text!r} is not a calendar date") from None
    return text


def _bounds(text: str) -> tuple[date, date]:
    """The earliest and latest day a date of any written precision covers;
    raises `ValueError` for a date that is not on the calendar."""
    year, *rest = (int(piece) for piece in text.split("-"))
    if not rest:
        return date(year, 1, 1), date(year, 12, 31)
    month = rest[0]
    first = date(year, month, 1)
    if len(rest) == 2:
        day = date(year, month, rest[1])
        return day, day
    return first, date(year, month, calendar.monthrange(year, month)[1])


def _plain(value: Decimal) -> str:
    """A plain decimal: no exponent, no trailing zeros (derivations.py `_text`)."""
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _to_hundredth(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 80
        return value.quantize(_HUNDREDTH, rounding=ROUND_HALF_EVEN)


def _feet(metres: Decimal) -> tuple[Decimal, bool]:
    """Feet for metres, at 1 ft = 0.3048 m: (value, exact). Exact when the
    quotient is finite, which recovers the feet a label stated."""
    with localcontext() as context:
        context.prec = 34  # evidence.py INVERSE_PRECISION
        context.rounding = ROUND_HALF_EVEN
        feet = metres / METRES_PER_FOOT
    with localcontext() as context:
        context.prec = 80
        return feet, feet * METRES_PER_FOOT == metres


def _elevation(found: dict[str, object], *, unit_inferred: bool = False) -> dict[str, str]:
    """The four elevation mirrors from `elevation/from`, `/to`, `/unit`, `/kind`.

    Numbers are exact metres. The kind says which bounds exist: a point fills
    from and to with the same value (the live G41 copy), a range fills both, an
    above limit only from and a below limit only to. The unit is what the label
    stated: its own bound is written as stated and the other unit is converted
    at 1 ft = 0.3048 m, to 0.01 with round-half-even, as the live rules do.
    Numbers with no unit fill nothing, and neither do numbers whose unit was
    inferred (`unit_inferred`): live v1 waits for a policy when the label gives
    no unit, and until the unit is known the metres are not known to be metres.
    """
    low = found.get("elevation/from")
    high = found.get("elevation/to")
    unit = found.get("elevation/unit")
    kind = found.get("elevation/kind")
    if low is None and high is None and kind is None:
        return {}
    if kind is None:
        raise FieldModelError("elevation/kind is required with elevation/from or /to")
    kind = _enum("elevation/kind", kind, ElevationKind)
    stated = {
        ElevationKind.POINT: ("from",),
        ElevationKind.RANGE: ("from", "to"),
        ElevationKind.ABOVE: ("from",),
        ElevationKind.BELOW: ("to",),
    }[kind]
    if tuple(end for end, bound in (("from", low), ("to", high)) if bound is not None) != stated:
        raise FieldModelError(
            f"an elevation of kind {kind.value} has exactly " + " and ".join(
                f"elevation/{end}" for end in stated
            )
        )
    if kind == ElevationKind.RANGE and low > high:
        raise FieldModelError("elevation/from is above elevation/to")
    if unit is None or unit_inferred:
        return {}
    unit = _enum("elevation/unit", unit, ElevationUnit)
    filled = {
        ElevationKind.POINT: {"from": low, "to": low},
        ElevationKind.RANGE: {"from": low, "to": high},
        ElevationKind.ABOVE: {"from": low},
        ElevationKind.BELOW: {"to": high},
    }[kind]
    result: dict[str, str] = {}
    for end, metres in filled.items():
        feet, exact = _feet(metres)
        if unit == ElevationUnit.M:
            result[f"elevation_{end}_m"] = _plain(metres)
            result[f"elevation_{end}_ft"] = _plain(_to_hundredth(feet))
        else:
            result[f"elevation_{end}_ft"] = _plain(feet if exact else _to_hundredth(feet))
            result[f"elevation_{end}_m"] = _plain(_to_hundredth(metres))
    return result


def _collected_dates(found: dict[str, object]) -> dict[str, str]:
    start = found.get("when/collected/start")
    end = found.get("when/collected/end")
    result: dict[str, str] = {}
    if start is not None:
        result["date_visited_from"] = start
        # G44: one stated date is both ends, at the precision written.
        result["date_visited_to"] = start if end is None else end
    elif end is not None:
        result["date_visited_to"] = end
    if start is not None and end is not None:
        if len(start) == len(end):
            if end < start:
                raise FieldModelError("when/collected/end is before when/collected/start")
        elif _bounds(start)[1] > _bounds(end)[0]:
            raise FieldModelError(
                f"when/collected/start ({start}) and when/collected/end ({end}) conflict "
                "in precision: the order of the endpoints is not established"
            )
    return result


def _role(nodes: list[PartPath], levels: tuple[str, ...], role: str) -> str | None:
    matches = [node for node in nodes if node.part in levels]
    if len(matches) > 1:
        names = ", ".join(node.path for node in matches)
        raise FieldModelError(f"more than one {role} node ({names}); one must be chosen first")
    return matches[0].path if matches else None


def _ordered(kind: str, entries: dict[int, str]) -> list[str]:
    if sorted(entries) != list(range(1, len(entries) + 1)):
        raise FieldModelError(f"{kind}/<n> entries run 1 to n with none missing")
    return [entries[number] for number in sorted(entries)]


def _checked_bases(
    parts: Mapping[str, object], bases: Mapping[str, object] | None
) -> dict[str, Basis]:
    checked: dict[str, Basis] = {}
    for path, basis in (bases or {}).items():
        if parse_part_path(path).path not in parts:
            raise FieldModelError(f"bases names {path!r}, which is not among the parts")
        checked[path] = _enum(f"bases[{path}]", basis, Basis)
    return checked


def v1_mirror(
    parts: Mapping[str, object], *, bases: Mapping[str, object] | None = None
) -> dict[str, str]:
    """The v1 mirror keys that the v2 `parts` fill, keyed by the exact native
    key strings. `parts` maps part paths to plain values: text, dates as
    `YYYY`, `YYYY-MM` or `YYYY-MM-DD`, elevation numbers as `Decimal`, `int` or
    plain decimal text in metres. A key with no v2 source is absent from the
    result: `verbatim_dts` and `identified_by_irn` always are, and so are
    `county` and `city` where no part supports them, since none is invented.
    The result is in native key order. Anything malformed raises
    `FieldModelError`; nothing is repaired or guessed.

    The adapter reads values, not bases. `bases` is optional: it maps part
    paths among `parts` to `label`, `derived` or `inferred`, and the one thing
    the adapter does with it is withhold the whole elevation when
    `elevation/unit` is `inferred` (the pilot's 105526322, where the foot mark
    was lost): live v1 fills no elevation without a written unit and waits for
    a policy. Every other basis is ignored, and a caller that passes no `bases`
    gets the mirror of the values as given, so it must withhold an inferred
    unit itself. Whether any other inferred or derived value belongs in the v1
    mirror is the caller's decision.

    Elevation text follows `application/derivations.py` `_text`: a converted
    value is rounded to 0.01 with round-half-even and trailing zeros are
    dropped ("1950.7"), where `research_harness/evidence.py` `display_decimal`
    keeps them ("1950.70"). Compare such values as `Decimal`, not as strings.

    Differences from the PRD table "v1 keys from v2 parts". Following live code:
    the stated unit is written as stated and the other is converted and rounded
    as above; a point fills both bounds alike; a single collecting date fills
    both ends at the written precision (G44); a municipality is not a county;
    `verbatim_dts` and `identified_by_irn` are never filled. New in this module
    and not live behaviour: `elevation/kind` is required (the PRD table's point,
    range, above and below need it to be told apart) and an above or below
    limit fills one bound; a bare elevation number with no `elevation/unit`
    fills nothing; `taxon` fills only from `taxon/accepted`; collectors join
    with " & "; `ids/catalog_number` is copied unvalidated. See the module
    docstring.
    """
    basis_of = _checked_bases(parts, bases)
    found: dict[str, object] = {}
    nodes: list[PartPath] = []
    names: dict[ValueName, dict[int, str]] = {ValueName.COLLECTORS: {}, ValueName.IDENTIFIED_BY: {}}
    for path, raw in parts.items():
        parsed = parse_part_path(path)
        if parsed.value == ValueName.ELEVATION and parsed.part in ("from", "to"):
            found[path] = _decimal(path, raw)
        elif parsed.value == ValueName.ELEVATION and parsed.part == "unit":
            found[path] = _enum(path, raw, ElevationUnit)
        elif parsed.value == ValueName.ELEVATION:
            found[path] = _enum(path, raw, ElevationKind)
        elif path in _DATE_PARTS:
            found[path] = _iso(path, raw)
        else:
            found[path] = _text(path, raw)
        if parsed.value in names:
            names[parsed.value][parsed.index] = found[path]
        elif parsed.value == ValueName.LOCATION:
            nodes.append(parsed)

    mirror: dict[str, str] = {key: found[path] for path, key in _COPIED.items() if path in found}
    for key, levels, role in (
        ("country", _COUNTRY_LEVELS, "country"),
        ("province_state", _FIRST_ADMIN_LEVELS, "first-level administrative"),
        ("county", _SECOND_ADMIN_LEVELS, "second-level administrative"),
        ("city", _SETTLEMENT_LEVELS, "settlement"),
    ):
        if (source := _role(nodes, levels, role)) is not None:
            mirror[key] = found[source]
    mirror.update(
        _elevation(found, unit_inferred=basis_of.get("elevation/unit") == Basis.INFERRED)
    )
    mirror.update(_collected_dates(found))
    if "when/identified/start" in found:
        mirror["date_identified"] = found["when/identified/start"]
    if names[ValueName.COLLECTORS]:
        mirror["collectors"] = COLLECTORS_JOINER.join(
            _ordered("collectors", names[ValueName.COLLECTORS])
        )
    _ordered("identified_by", names[ValueName.IDENTIFIED_BY])  # validated, no v1 key
    return {key: mirror[key] for key in V1_KEYS if key in mirror}
