"""Option (a2): the written elevation notations the validator's parser refused (a foot mark, a trailing period, an elev label).

evidence.parse_measurement is the validator's own parser (VALIDATOR_SOURCE_SHA256 pins its bytes). Its unit set was
``ft|feet|foot|m|metre(s)|meter(s)`` with nothing after the unit, so a label that writes ``3300'`` or ``4800 ft.`` or
``Elev. 4800 ft.`` could never reach a settled elevation. These tests pin the widened notation and, as important, every
refusal that must stay: a missing unit, ``mt``, a thousands comma, a reversed range, a doubled mark, a mark in front.
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
    "100", "Elev 4800", "Elev. ft", "100 mt", "3300''", "'3300", "100 ft..", "100 ft'", "1,000 ft", "25 -- ft", "NaN m",
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
