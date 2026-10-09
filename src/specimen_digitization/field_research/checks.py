"""Deterministic checks a field's expert may call: dates, elevations, catalog numbers;
and the rule tying a taxon's GBIF question to its literal.

Each wraps the repository's pinned parser unchanged (HARNESS.md sections 8 and 13),
calls no provider and never changes the literal. Like the validators it wraps,
a check answers only for a literal that occurs in one of the record's readings;
otherwise it is policy_blocked with the note literal_not_in_source.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any, Literal

from specimen_digitization.application.derivations import HUNDREDTH, METRES_PER_FOOT
from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.field_validators import (
    catalog_number_validator,
    date_parser,
)

# The elevation parser and the taxon marker projection live with the
# six-specialist harness; they move with these imports when that harness is deleted.
from specimen_digitization.research_harness.evidence import EvidenceError, parse_measurement
from specimen_digitization.research_harness.taxonomy import taxonomy_scientific_name

NOT_IN_SOURCE = "literal_not_in_source"
# The date parser's notes for a literal that is (part of) a hyphen-joined code.
_CODE_NOTES = frozenset({"slide_code", "part_of_hyphenated_token"})


def _as_dict(result: Any) -> dict[str, Any]:
    """The compact form an expert is shown: empty and None values left out."""
    out: dict[str, Any] = {"check": result.check}
    for item in fields(result):
        value = getattr(result, item.name)
        if value is None or value == ():
            continue
        if isinstance(value, tuple):
            value = [v.as_dict() if hasattr(v, "as_dict") else v for v in value]
        out[item.name] = str(value) if isinstance(value, LookupStatus) else value
    return out


@dataclass(frozen=True)
class DateReading:
    """One reading a date's notation allows (G29)."""

    # None when the notation states no year (or no century rule gives one).
    iso: str | None
    precision: Literal["day", "month", "year"]
    order: str
    century_rule: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in vars(self).items() if v is not None}


@dataclass(frozen=True)
class DateCheck:
    literal: str
    status: LookupStatus
    readings: tuple[DateReading, ...] = ()
    notes: tuple[str, ...] = ()
    check: str = "date_parser"

    @property
    def values(self) -> tuple[str, ...]:
        """The dates the literal can be: each reading's ISO form."""
        return tuple(r.iso for r in self.readings if r.iso)

    def as_dict(self) -> dict[str, Any]:
        return _as_dict(self)


@dataclass(frozen=True)
class ElevationCheck:
    literal: str
    status: LookupStatus
    unit: Literal["m", "ft"] | None = None
    # The written numbers, as plain decimals (thousands commas dropped).
    low: str | None = None
    high: str | None = None
    single: bool | None = None
    approximate: bool | None = None
    uncertainty: str | None = None
    notes: tuple[str, ...] = ()
    check: str = "elevation_parser"

    @property
    def values(self) -> tuple[str, ...]:
        """The numbers the label writes, in its own unit; never a conversion (G41)."""
        return tuple(dict.fromkeys(v for v in (self.low, self.high) if v is not None))

    def as_dict(self) -> dict[str, Any]:
        return _as_dict(self)


@dataclass(frozen=True)
class CatalogCheck:
    literal: str
    status: LookupStatus
    catalog_number: str | None = None
    notes: tuple[str, ...] = ()
    check: str = "catalog_number_validator"

    @property
    def values(self) -> tuple[str, ...]:
        return (self.catalog_number,) if self.catalog_number else ()

    def as_dict(self) -> dict[str, Any]:
        return _as_dict(self)


CheckResult = DateCheck | ElevationCheck | CatalogCheck


def _sources(literal: str, reading_texts: Sequence[str]) -> list[str]:
    if not literal or not literal.strip():
        return []
    return [text for text in reading_texts if literal in text]


def _date_rules(date_rules: Any) -> dict | None:
    """The profile's DateRules (a record or its dict) as the date parser reads it."""
    if date_rules is None:
        return None
    if isinstance(date_rules, Mapping):
        return dict(date_rules)
    return date_rules.model_dump()


def parse_date(
    literal: str,
    *,
    reading_texts: Sequence[str],
    date_rules: Any = None,
    year_literal: str | None = None,
) -> DateCheck:
    """Every reading a date literal's notation allows (G24, G29; HARNESS.md section 8).

    `date_rules` is the profile's (century rule, Roman months); without it a
    two-digit year stays partial and a Roman month is not read. `year_literal`
    is a year the same reading states elsewhere, the only year a month and day
    alone can take. A literal that is part of a slide-preparation code, or of
    any other hyphen-joined token, in any reading is no date.
    """
    texts = _sources(literal, reading_texts)
    if not texts:
        return DateCheck(literal, LookupStatus.POLICY, notes=(NOT_IN_SOURCE,))
    rules = _date_rules(date_rules)
    results = [
        date_parser(literal, source_text=t, year_literal=year_literal, date_rules=rules)
        for t in texts
    ]
    # A year literal must be in the same reading as the date it completes.
    results = [r for r in results if r.outcome != LookupStatus.POLICY]
    if not results:
        return DateCheck(literal, LookupStatus.POLICY, notes=("year_literal_not_in_reading",))
    # Where one reader shows the literal inside a code, it is not a date at all.
    result = next(
        (r for r in results if _CODE_NOTES & set(r.warnings)), results[0]
    )
    readings = tuple(
        DateReading(
            iso=r["iso"],
            precision=r["precision"],
            order=r["order"],
            century_rule=r["century_rule"],
        )
        for r in (result.parsed or {}).get("readings", ())
    )
    return DateCheck(literal, result.outcome, readings, tuple(result.warnings))


def collapse(text: str) -> str:
    """Text as two readers' literals, or a query and a name, are compared: NFC
    and whitespace collapsed, nothing else. Case, punctuation and the spacing
    between words still differ ("E. slope" is not "E.slope")."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def taxon_queries(literal: str) -> frozenset[str]:
    """The GBIF queries that ask about the whole name a taxon literal writes.

    The scientific-name parser's query for the literal (the genus, any
    subgenus, the species epithet and any infraspecific epithet with its
    marker, as written, and the author and year when written), and the same
    without the author and year. What is not part of the name the parser
    leaves out (sex signs, counts, specimen numbers). For a genus-level
    identification ("Epipsocus sp. 1", G25) its query is the genus alone. A
    literal it reads only in part ("Aus bus n. sp."), or that writes no genus
    ("sp. 30"), has none. This is the native rule: the deciding query is the
    declared reading's complete name (research_harness.evidence
    _validate_taxon_inputs, with _taxon_assertions' complete()).
    """
    name = taxonomy_scientific_name(literal)
    if name is None or not name.genus or name.partly_read is not None:
        return frozenset()
    forms = {name.query}
    if name.authorship:
        forms.add(replace(name, authorship=None).query)
    return frozenset(collapse(form) for form in forms)


def taxon_query_grounded(query: str, literal: str) -> bool:
    """Whether GBIF was asked about the whole name this taxon literal writes
    (taxon_queries). A query for part of it ("Danaus plexippus" for "Danaus
    plexippus megalippe") or for another name on its line is not."""
    return collapse(query) in taxon_queries(literal)


def _evidence_error_note(message: str) -> str:
    text = message.casefold()
    if "unit" in text and "required" in text:
        return "unit_not_written"
    if "reversed" in text:
        return "range_reversed"
    if "uncertainty" in text:
        return "uncertainty_unclear"
    return "not_an_elevation"


def parse_elevation(literal: str, *, reading_texts: Sequence[str]) -> ElevationCheck:
    """A written elevation: its number or range, unit, and approximate marker (G41).

    The unit is only ever the one written ("m", "ft.", "'", "feet"); a bare number
    has none and is no_match here, since a unit is never guessed.
    """
    if not _sources(literal, reading_texts):
        return ElevationCheck(literal, LookupStatus.POLICY, notes=(NOT_IN_SOURCE,))
    try:
        parsed = parse_measurement(literal)
    except EvidenceError as error:
        return ElevationCheck(
            literal, LookupStatus.NO_MATCH, notes=(_evidence_error_note(str(error)),)
        )
    approximate = bool(parsed.qualifiers)
    if parsed.from_unit != parsed.to_unit:
        return ElevationCheck(
            literal,
            LookupStatus.AMBIGUOUS,
            low=parsed.from_quantity,
            high=parsed.to_quantity,
            single=False,
            approximate=approximate,
            notes=("mixed_units",),
        )
    return ElevationCheck(
        literal,
        LookupStatus.SUCCESS,
        unit=parsed.from_unit,
        low=parsed.from_quantity,
        high=parsed.to_quantity,
        single=parsed.single,
        approximate=approximate,
        uncertainty=parsed.uncertainty,
    )


def check_catalog_number(literal: str, *, reading_texts: Sequence[str]) -> CatalogCheck:
    """A Field Museum insect catalog number: 5 to 9 digits after an optional FMNH INS."""
    texts = _sources(literal, reading_texts)
    if not texts:
        return CatalogCheck(literal, LookupStatus.POLICY, notes=(NOT_IN_SOURCE,))
    result = catalog_number_validator(literal, source_text=texts[0])
    number = (result.parsed or {}).get("catalog_number")
    return CatalogCheck(literal, result.outcome, number, tuple(result.warnings))


def _hundredths(value: Decimal) -> str:
    text = format(value.quantize(HUNDREDTH, rounding=ROUND_HALF_EVEN), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _quantity(text: str) -> Decimal:
    try:
        value = Decimal(text.replace(",", ""))
    except InvalidOperation:
        raise ValueError("not a plain decimal quantity") from None
    if not value.is_finite():
        raise ValueError("not a plain decimal quantity")
    return value


def feet_to_metres(quantity: str) -> str:
    """Feet to metres by the exact factor (1 ft = 0.3048 m), kept to hundredths (G41)."""
    return _hundredths(_quantity(quantity) * METRES_PER_FOOT)


def metres_to_feet(quantity: str) -> str:
    """Metres to feet by the exact factor (1 m = 1/0.3048 ft), kept to hundredths (G41)."""
    return _hundredths(_quantity(quantity) / METRES_PER_FOOT)
