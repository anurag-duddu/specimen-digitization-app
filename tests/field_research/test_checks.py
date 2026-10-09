"""The deterministic checks a field's expert may call (HARNESS.md sections 8 and 13)."""

from __future__ import annotations

import pytest

from specimen_digitization.application.collection_profiles import DateRules
from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.field_research.checks import (
    check_catalog_number,
    feet_to_metres,
    metres_to_feet,
    parse_date,
    parse_elevation,
    taxon_queries,
    taxon_query_grounded,
)

# The pilot profile's rules (application/profiles/published.json).
PILOT = {"version": "date-rules-v1", "two_digit_year_century": 1900, "roman_numeral_months": True}
READINGS = [
    "Mindanao, P.I.\nDavao 12.VI.1946\nF. G. Werner",
    "XI.'46 4-5-48\nslide IV-29-68-4",
    "alt. 1500 ft\n300-450 m ca. 1200 m 6,400 ft\nFMNH INS 0012345 IX-17-66-2",
]


def test_a_roman_month_date_reads_at_day_precision():
    result = parse_date("12.VI.1946", reading_texts=READINGS, date_rules=PILOT)

    assert result.status == LookupStatus.SUCCESS
    assert [(r.iso, r.precision) for r in result.readings] == [("1946-06-12", "day")]
    assert result.values == ("1946-06-12",)


def test_a_two_digit_year_follows_the_profile_century_rule():
    result = parse_date("XI.'46", reading_texts=READINGS, date_rules=DateRules(
        two_digit_year_century=1900, roman_numeral_months=True))

    assert result.status == LookupStatus.SUCCESS
    assert result.values == ("1946-11",)
    assert result.readings[0].precision == "month"
    assert result.readings[0].century_rule == "date-rules-v1:two_digit_year_century=1900"
    # Without the profile's rules neither the Roman month nor the century is read.
    assert parse_date("XI.'46", reading_texts=READINGS).status == LookupStatus.NO_MATCH


def test_a_numeric_date_gives_both_orders():
    result = parse_date("4-5-48", reading_texts=READINGS, date_rules=PILOT)

    assert result.status == LookupStatus.AMBIGUOUS
    assert set(result.values) == {"1948-04-05", "1948-05-04"}
    assert "several_readings" in result.notes
    assert result.as_dict()["readings"][0]["order"] in {"month-day-year", "day-month-year"}


def test_a_slide_code_is_never_a_date():
    for literal in ("IV-29-68", "IV-29-68-4"):
        result = parse_date(literal, reading_texts=READINGS, date_rules=PILOT)
        assert result.status == LookupStatus.NO_MATCH
        assert result.notes == ("slide_code",) and result.values == ()


def test_a_date_inside_a_code_in_any_reading_is_no_date():
    # One reader drops the code's last part; the other shows it is a code.
    readings = ["Date IV-29-68", "Date IV-29-68-4"]

    result = parse_date("IV-29-68", reading_texts=readings, date_rules=PILOT)

    assert result.status == LookupStatus.NO_MATCH and "slide_code" in result.notes


def test_a_check_answers_only_for_a_literal_in_the_readings():
    for result in (
        parse_date("13.VI.1946", reading_texts=READINGS, date_rules=PILOT),
        parse_elevation("1600 ft", reading_texts=READINGS),
        check_catalog_number("0099999", reading_texts=READINGS),
        parse_date("  ", reading_texts=["  "], date_rules=PILOT),
    ):
        assert result.status == LookupStatus.POLICY
        assert result.notes == ("literal_not_in_source",)
        assert result.values == ()


def test_a_year_literal_must_be_in_the_same_reading():
    readings = ["IV-25 1946", "IV-25"]

    with_year = parse_date("IV-25", reading_texts=readings, date_rules=PILOT, year_literal="1946")
    elsewhere = parse_date("IV-25", reading_texts=["IV-25", "1946"], date_rules=PILOT,
                           year_literal="1946")

    assert "1946-04-25" in with_year.values
    assert elsewhere.status == LookupStatus.POLICY


@pytest.mark.parametrize(
    ("literal", "unit", "low", "high", "single", "approximate"),
    [
        ("alt. 1500 ft", "ft", "1500", "1500", True, False),
        ("1500 ft", "ft", "1500", "1500", True, False),
        ("300-450 m", "m", "300", "450", False, False),
        ("ca. 1200 m", "m", "1200", "1200", True, True),
        ("6,400 ft", "ft", "6400", "6400", True, False),
    ],
)
def test_elevations(literal, unit, low, high, single, approximate):
    result = parse_elevation(literal, reading_texts=READINGS)

    assert result.status == LookupStatus.SUCCESS
    assert (result.unit, result.low, result.high, result.single, result.approximate) == (
        unit, low, high, single, approximate)
    assert result.values == tuple(dict.fromkeys((low, high)))


def test_a_unit_is_never_guessed():
    result = parse_elevation("1500", reading_texts=READINGS)

    assert result.status == LookupStatus.NO_MATCH
    assert result.notes == ("unit_not_written",) and result.values == ()


def test_exact_conversions_to_hundredths():
    assert feet_to_metres("1500") == "457.2"
    assert feet_to_metres("3,300") == "1005.84"
    assert metres_to_feet("1200") == "3937.01"
    assert metres_to_feet("300") == "984.25"
    with pytest.raises(ValueError):
        feet_to_metres("about 3")


def test_a_taxon_query_is_the_whole_name_the_label_writes():
    # Genus, species and any infraspecific epithet with its marker, as written;
    # the author and year may be left off.
    trinomial = "Danaus plexippus megalippe"
    assert taxon_query_grounded(trinomial, trinomial)
    assert taxon_query_grounded(trinomial, trinomial + " (Hubner, 1819)")
    assert taxon_query_grounded(trinomial + " (Hubner, 1819)", trinomial + " (Hubner, 1819)")
    assert not taxon_query_grounded("Danaus plexippus", trinomial)
    assert taxon_query_grounded("Aus bus var. cus", "Aus bus var. cus")
    assert not taxon_query_grounded("Aus bus cus", "Aus bus var. cus")
    # Another name on the literal's line is not its name.
    assert taxon_query_grounded("Bombus impatiens", "Bombus impatiens on Solidago canadensis")
    assert not taxon_query_grounded("Solidago canadensis", "Bombus impatiens on Solidago canadensis")
    # A sex sign and a count are no part of the name.
    assert taxon_query_grounded("Danaus plexippus", "Danaus plexippus \u2640 3")
    # G25: a genus-level identification is asked as its genus.
    assert taxon_query_grounded("Epipsocus", "Epipsocus sp.")
    assert not taxon_query_grounded("Epipsocus", "Epipsocus pallidus")


def test_a_label_with_no_genus_has_no_groundable_taxon_query():
    # 105526321's taxon line: a morphocode and a sex sign, no genus.
    assert taxon_queries("sp. 30 \u2640") == frozenset()
    for query in ("sp. 30", "sp.", "sp. 30 \u2640"):
        assert not taxon_query_grounded(query, "sp. 30 \u2640")


def test_catalog_numbers():
    prefixed = check_catalog_number("FMNH INS 0012345", reading_texts=READINGS)
    bare = check_catalog_number("0012345", reading_texts=READINGS)
    code = check_catalog_number("IX-17-66-2", reading_texts=READINGS)

    assert (prefixed.status, prefixed.catalog_number) == (LookupStatus.SUCCESS, "0012345")
    assert bare.values == ("0012345",)
    assert code.status == LookupStatus.NO_MATCH and code.values == ()
    assert prefixed.as_dict() == {
        "check": "catalog_number_validator", "literal": "FMNH INS 0012345",
        "status": "success", "catalog_number": "0012345",
    }
