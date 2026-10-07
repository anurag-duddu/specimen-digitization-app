"""Option (a2): the written elevation notations the validator's parser refused (a foot mark, a trailing period, an elev label).

evidence.parse_measurement is the validator's own parser (VALIDATOR_SOURCE_SHA256 pins its bytes). Its unit set was
``ft|feet|foot|m|metre(s)|meter(s)`` with nothing after the unit, so a label that writes ``3300'`` or ``4800 ft.`` or
``Elev. 4800 ft.`` could never reach a settled elevation. These tests pin the widened notation and, as important, every
refusal that must stay: a missing unit, ``mt``, malformed comma grouping, a reversed range, a doubled mark, a mark in front.
Abstract numbers only.
"""
import pytest

from specimen_digitization.research_harness.evidence import EvidenceError, parse_measurement


@pytest.mark.parametrize(("written", "first", "last", "unit"), (
    ("4800 ft.", "4800", "4800", "ft"),
    ("Elev. 4800 ft.", "4800", "4800", "ft"),
    ("Elev.: 4800 ft", "4800", "4800", "ft"),
    ("Elevation 4800 feet", "4800", "4800", "ft"),
    ("3300'", "3300", "3300", "ft"),
    ("Elev. 3300 '", "3300", "3300", "ft"),
    ("4800 ft. to 5000 ft.", "4800", "5000", "ft"),
    ("4800' - 5000'", "4800", "5000", "ft"),
    ("Alt. 100 m.", "100", "100", "m"),
    ("Altitude 100 metres", "100", "100", "m"),
))
def test_a_written_foot_mark_period_or_label_is_read_as_the_unit_it_is(written, first, last, unit):
    parsed = parse_measurement(written)
    assert (parsed.from_quantity, parsed.to_quantity, parsed.from_unit, parsed.to_unit) == (first, last, unit, unit)
    assert parsed.literal == written


@pytest.mark.parametrize("written", (
    "100", "Elev 4800", "Elev. ft", "100 mt", "3300''", "'3300", "100 ft..", "100 ft'", "25 -- ft", "NaN m",
    "-5 to -25 ft", "4800 ' ft", "Elev. 4800 ft. extra", "ft. 4800",
))
def test_the_widened_notation_keeps_every_refusal(written):
    with pytest.raises(EvidenceError):
        parse_measurement(written)


def test_the_original_notations_parse_exactly_as_before():
    for written, expected in (("100 ft", ("100", "100", "ft")), ("100 m", ("100", "100", "m")), ("5 foot", ("5", "5", "ft")),
                              ("10 feet", ("10", "10", "ft")), ("100 metres", ("100", "100", "m")),
                              ("~100 \u00b1 2 ft", ("100", "100", "ft")), ("-25 to -5 ft", ("-25", "-5", "ft"))):
        parsed = parse_measurement(written)
        assert (parsed.from_quantity, parsed.to_quantity, parsed.from_unit) == expected, written


@pytest.mark.parametrize(("written", "first", "last", "uncertainty"), (
    ("1,000 ft", "1000", "1000", None),
    ("6,400 ft", "6400", "6400", None),
    ("-6,400 ft", "-6400", "-6400", None),
    ("+6,400.50 ft", "6400.50", "6400.50", None),
    ("1,234,567 m", "1234567", "1234567", None),
    ("6,400 to 6,500 ft", "6400", "6500", None),
    ("6,400 ft - 6,500 ft", "6400", "6500", None),
    ("-6,400 to -6,300 ft", "-6400", "-6300", None),
    ("~6,400 \u00b1 1,000.25 ft", "6400", "6400", "1000.25"),
    ("6,400 ft \u00b1 +1,000 ft", "6400", "6400", "+1000"),
))
def test_complete_thousands_groups_keep_the_literal_and_normalize_only_quantities(written, first, last, uncertainty):
    parsed = parse_measurement(written)
    assert (parsed.from_quantity, parsed.to_quantity, parsed.uncertainty) == (first, last, uncertainty)
    assert parsed.literal == written


@pytest.mark.parametrize("written", (
    "6,40 ft", "64,00 ft", "6400,000 ft", "1,23,456 ft", "1,,000 ft", "1,000,00 ft", "1,000, ft",
    "6,4 ft", "0,125 m", "01,234 ft", "1.234,56 m", "6,400.5,0 ft", "6,400 unknown",
    "6,400 to 6,300 ft", "-6,300 to -6,400 ft", "6,400 \u00b1 -1,000 ft", "6,400 \u00b1 1,00 ft",
    "6,400 to 6,500", "NaN ft", "Infinity ft",
))
def test_grouping_does_not_admit_decimal_commas_malformed_or_unsupported_assertions(written):
    with pytest.raises(EvidenceError):
        parse_measurement(written)


def test_grouped_quantities_retain_the_existing_decimal_digit_bounds():
    forty_digits = "1" + ",000" * 13
    fraction = "1" * 20
    parsed = parse_measurement(f"{forty_digits}.{fraction} ft")
    assert parsed.from_quantity == "1" + "000" * 13 + "." + fraction
    for quantity in ("10" + ",000" * 13, "6,400." + "1" * 21):
        with pytest.raises(EvidenceError):
            parse_measurement(f"{quantity} ft")
        with pytest.raises(EvidenceError):
            parse_measurement(f"6,400 \u00b1 {quantity} ft")
