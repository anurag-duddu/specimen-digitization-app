"""Date and catalog-number validators (PRD HAR-006; owner decisions G24, G29).

The literals are the pilot's: F.G. Werner's 1946 Philippine labels and
R.D. Mitchell's 1948 Guatemalan ones, whose top edge carries date-shaped
slide-preparation codes.
"""

from datetime import UTC, datetime

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.field_validators import (
    catalog_number_validator,
    date_parser,
)

INSECTS = {
    "version": "date-rules-v1",
    "two_digit_year_century": 1900,
    "roman_numeral_months": True,
}
ROMAN_ONLY = {"version": "date-rules-v1", "roman_numeral_months": True}
CENTURY = "date-rules-v1:two_digit_year_century=1900"
ROMAN = "date-rules-v1:roman_numeral_months=true"
WERNER = "F.G. Werner\n3 sept. '46\nMossy forest 6400'"
MITCHELL = "IV-29-68-4\nYepocapa, 4800ft.\nIV-23-48\nR.D.Mitchell"
GUATEMALA = "Guatemala, IV-25\n1948, R.D. Mitchell"
THIS_YEAR = datetime.now(UTC).year


def reading(iso, year, month, day, precision, order, rules=()):
    return {
        "iso": iso,
        "year": year,
        "month": month,
        "day": day,
        "precision": precision,
        "century_rule": CENTURY if CENTURY in rules else None,
        "order": order,
        "rules": list(rules),
    }


def test_werner_date_clears_at_the_day_under_the_insects_century_rule():
    result = date_parser("3 sept. '46", source_text=WERNER, date_rules=INSECTS)
    assert (result.tool, result.tool_version) == ("date_parser", "date-parser-v1")
    assert result.outcome == LookupStatus.SUCCESS
    assert result.parsed == {
        "readings": [
            reading("1946-09-03", 1946, 9, 3, "day", "day-monthname-year", [CENTURY])
        ],
        "year_literal": None,
    }
    assert result.parsed["readings"][0]["century_rule"] == CENTURY
    assert result.warnings == [] and result.sub_calls == []


@pytest.mark.parametrize(
    "rules", [None, {"version": "date-rules-v1", "two_digit_year_century": None}]
)
def test_without_a_century_rule_a_two_digit_year_stays_unresolved(rules):
    result = date_parser("3 sept. '46", source_text=WERNER, date_rules=rules)
    assert result.outcome == LookupStatus.AMBIGUOUS
    assert result.warnings == ["century_unresolved"]
    assert result.parsed == {
        "readings": [reading(None, None, 9, 3, "day", "day-monthname-year")],
        "year_literal": None,
    }


def test_mitchell_roman_month_reads_as_the_month_under_the_profile_rule():
    result = date_parser("IV-23-48", source_text=MITCHELL, date_rules=INSECTS)
    assert result.outcome == LookupStatus.SUCCESS
    assert result.parsed["readings"] == [
        reading("1948-04-23", 1948, 4, 23, "day", "month-day-year", [ROMAN, CENTURY])
    ]
    assert result.warnings == []


def test_roman_months_without_a_century_rule_leave_the_year_open():
    rules = {"version": "date-rules-v1", "roman_numeral_months": True}
    result = date_parser("IV-23-48", source_text=MITCHELL, date_rules=rules)
    assert result.outcome == LookupStatus.AMBIGUOUS
    assert result.warnings == ["century_unresolved"]
    assert result.parsed["readings"] == [
        reading(None, None, 4, 23, "day", "month-day-year", [ROMAN])
    ]


@pytest.mark.parametrize(
    "rules",
    [
        None,
        {"version": "date-rules-v1", "two_digit_year_century": 1900},
        {**INSECTS, "roman_numeral_months": False},
    ],
)
@pytest.mark.parametrize(
    "literal,source_text,year_literal",
    [
        ("IV-23-48", MITCHELL, None),
        ("IV-25", GUATEMALA, "1948"),
        ("12.VI.1946", "12.VI.1946", None),
        ("12.vi.46", "12.vi.46", None),
        ("IV 1948", "IV 1948", None),
    ],
)
def test_a_roman_month_is_not_read_unless_the_profile_enables_it(
    rules, literal, source_text, year_literal
):
    result = date_parser(
        literal, source_text=source_text, year_literal=year_literal, date_rules=rules
    )
    assert result.outcome == LookupStatus.NO_MATCH
    assert result.warnings == ["roman_numeral_months_not_enabled"]
    assert result.parsed is None


@pytest.mark.parametrize(
    "literal,source_text",
    [
        ("IV-29-68", MITCHELL),
        ("10-6-78", "10-6-78-1a"),
        ("IV-29-68-4", MITCHELL),
        ("10-6-78-1a", "10-6-78-1a"),
        ("VII-18-66-1", "VII-18-66-1"),
    ],
)
def test_a_slide_preparation_code_or_a_date_shaped_part_of_one_is_no_date(
    literal, source_text
):
    result = date_parser(literal, source_text=source_text, date_rules=INSECTS)
    assert result.outcome == LookupStatus.NO_MATCH
    assert result.warnings == ["slide_code"] and result.parsed is None


@pytest.mark.parametrize(
    "literal,source_text", [("1946", "6-Sept-1946"), ("IV-23", MITCHELL)]
)
def test_a_literal_seen_only_inside_a_longer_hyphenated_token_is_no_date(
    literal, source_text
):
    result = date_parser(literal, source_text=source_text, date_rules=INSECTS)
    assert result.outcome == LookupStatus.NO_MATCH
    assert result.warnings == ["part_of_hyphenated_token"] and result.parsed is None


def test_a_literal_that_also_stands_alone_in_the_reading_is_read_as_a_date():
    source = "IV-29-68-4\nYepocapa\nIV-29-68"
    result = date_parser("IV-29-68", source_text=source, date_rules=INSECTS)
    assert result.outcome == LookupStatus.SUCCESS
    assert result.parsed["readings"][0]["iso"] == "1968-04-29"


@pytest.mark.parametrize(
    "source_text,year_literal,outcome,warnings,expected",
    [
        (
            GUATEMALA,
            "1948",
            LookupStatus.SUCCESS,
            [],
            reading("1948-04-25", 1948, 4, 25, "day", "month-day", [ROMAN]),
        ),
        (
            "Guatemala, IV-25\n'48, R.D. Mitchell",
            "'48",
            LookupStatus.AMBIGUOUS,
            ["century_unresolved"],
            reading(None, None, 4, 25, "day", "month-day", [ROMAN]),
        ),
        (
            GUATEMALA,
            None,
            LookupStatus.AMBIGUOUS,
            ["year_missing"],
            reading(None, None, 4, 25, "day", "month-day", [ROMAN]),
        ),
    ],
)
def test_a_roman_month_and_day_takes_its_year_only_from_the_year_literal(
    source_text, year_literal, outcome, warnings, expected
):
    result = date_parser(
        "IV-25",
        source_text=source_text,
        year_literal=year_literal,
        date_rules=ROMAN_ONLY,
    )
    assert result.outcome == outcome
    assert result.warnings == warnings
    assert result.parsed == {"readings": [expected], "year_literal": year_literal}


@pytest.mark.parametrize(
    "literal,source_text,year_literal,warnings,readings",
    [
        (
            "IV-25",
            GUATEMALA,
            "1948",
            ["several_readings"],
            [
                reading("1948-04-25", 1948, 4, 25, "day", "month-day", [ROMAN]),
                reading(
                    "1925-04", 1925, 4, None, "month", "month-year", [ROMAN, CENTURY]
                ),
            ],
        ),
        (
            "IV-25",
            GUATEMALA,
            None,
            ["several_readings", "year_missing"],
            [
                reading(None, None, 4, 25, "day", "month-day", [ROMAN]),
                reading(
                    "1925-04", 1925, 4, None, "month", "month-year", [ROMAN, CENTURY]
                ),
            ],
        ),
        (
            "IV-25",
            "Guatemala, IV-25\n'48, R.D. Mitchell",
            "'48",
            ["several_readings"],
            [
                reading(
                    "1948-04-25", 1948, 4, 25, "day", "month-day", [ROMAN, CENTURY]
                ),
                reading(
                    "1925-04", 1925, 4, None, "month", "month-year", [ROMAN, CENTURY]
                ),
            ],
        ),
        (
            "Dec. 25",
            "Dec. 25\n1948",
            "1948",
            ["several_readings"],
            [
                reading("1948-12-25", 1948, 12, 25, "day", "monthname-day"),
                reading(
                    "1925-12", 1925, 12, None, "month", "monthname-year", [CENTURY]
                ),
            ],
        ),
        (
            "Dec. 25",
            "Dec. 25",
            None,
            ["several_readings", "year_missing"],
            [
                reading(None, None, 12, 25, "day", "monthname-day"),
                reading(
                    "1925-12", 1925, 12, None, "month", "monthname-year", [CENTURY]
                ),
            ],
        ),
    ],
)
def test_under_the_century_rule_a_number_after_a_month_is_a_day_or_a_year(
    literal, source_text, year_literal, warnings, readings
):
    result = date_parser(
        literal, source_text=source_text, year_literal=year_literal, date_rules=INSECTS
    )
    assert result.outcome == LookupStatus.AMBIGUOUS
    assert result.warnings == warnings
    assert result.parsed == {"readings": readings, "year_literal": year_literal}


@pytest.mark.parametrize(
    "literal,rules,warning,expected",
    [
        (
            "Dec. 25",
            None,
            "year_missing",
            reading(None, None, 12, 25, "day", "monthname-day"),
        ),
        (
            "Dec. 5",
            INSECTS,
            "year_missing",
            reading(None, None, 12, 5, "day", "monthname-day"),
        ),
        (
            "5-5-48",
            None,
            "century_unresolved",
            reading(None, None, 5, 5, "day", "month-day-year"),
        ),
        (
            "12.vi.46",
            ROMAN_ONLY,
            "century_unresolved",
            reading(None, None, 6, 12, "day", "day-month-year", [ROMAN]),
        ),
        (
            "Sept 3 46",
            None,
            "century_unresolved",
            reading(None, None, 9, 3, "day", "monthname-day-year"),
        ),
    ],
)
def test_a_single_reading_without_a_year_is_ambiguous(
    literal, rules, warning, expected
):
    result = date_parser(literal, source_text=literal, date_rules=rules)
    assert result.outcome == LookupStatus.AMBIGUOUS
    assert result.warnings == [warning]
    assert result.parsed == {"readings": [expected], "year_literal": None}


@pytest.mark.parametrize(
    "literal,rules,expected",
    [
        (
            "6-Sept-1946",
            None,
            reading("1946-09-06", 1946, 9, 6, "day", "day-monthname-year"),
        ),
        (
            "6-Sept.-1946",
            INSECTS,
            reading("1946-09-06", 1946, 9, 6, "day", "day-monthname-year"),
        ),
        (
            "Sept. 1946",
            None,
            reading("1946-09", 1946, 9, None, "month", "monthname-year"),
        ),
        (
            "Sept. '46",
            INSECTS,
            reading("1946-09", 1946, 9, None, "month", "monthname-year", [CENTURY]),
        ),
        ("1946", INSECTS, reading("1946", 1946, None, None, "year", "year")),
        (
            "13-5-48",
            INSECTS,
            reading("1948-05-13", 1948, 5, 13, "day", "day-month-year", [CENTURY]),
        ),
        (
            "5/13/1948",
            None,
            reading("1948-05-13", 1948, 5, 13, "day", "month-day-year"),
        ),
        (
            "II-29-48",
            INSECTS,
            reading(
                "1948-02-29", 1948, 2, 29, "day", "month-day-year", [ROMAN, CENTURY]
            ),
        ),
        # Identical readings collapse to one.
        (
            "5-5-48",
            INSECTS,
            reading("1948-05-05", 1948, 5, 5, "day", "month-day-year", [CENTURY]),
        ),
        # A number that cannot be the day is the two-digit year.
        (
            "V-48",
            INSECTS,
            reading("1948-05", 1948, 5, None, "month", "month-year", [ROMAN, CENTURY]),
        ),
        (
            "Sept. 46",
            INSECTS,
            reading("1946-09", 1946, 9, None, "month", "monthname-year", [CENTURY]),
        ),
        # Day, Roman month, year: uppercase with any separator, lowercase only
        # with "." or "-".
        *(
            (
                literal,
                INSECTS,
                reading("1946-06-12", 1946, 6, 12, "day", "day-month-year", [ROMAN]),
            )
            for literal in ("12.VI.1946", "12-VI-1946", "12 VI 1946", "12-vi-1946")
        ),
        *(
            (
                literal,
                INSECTS,
                reading(
                    iso, 1946, month, 12, "day", "day-month-year", [ROMAN, CENTURY]
                ),
            )
            for literal, iso, month in (
                ("12.vi.46", "1946-06-12", 6),
                ("12.x.46", "1946-10-12", 10),
                ("12 X 46", "1946-10-12", 10),
            )
        ),
        # Roman month and four-digit year, with no century rule needed.
        *(
            (
                literal,
                rules,
                reading("1948-04", 1948, 4, None, "month", "month-year", [ROMAN]),
            )
            for literal, rules in (
                ("IV-1948", ROMAN_ONLY),
                ("IV.1948", INSECTS),
                ("IV 1948", INSECTS),
            )
        ),
        # Month name, day, year.
        *(
            (
                literal,
                None,
                reading("1946-09-03", 1946, 9, 3, "day", "monthname-day-year"),
            )
            for literal in ("Sept. 3, 1946", "Sept 3 1946")
        ),
        (
            "Sept. 3, '46",
            INSECTS,
            reading("1946-09-03", 1946, 9, 3, "day", "monthname-day-year", [CENTURY]),
        ),
        # Curly apostrophes mark a two-digit year.
        (
            "3 sept. ’46",
            INSECTS,
            reading("1946-09-03", 1946, 9, 3, "day", "day-monthname-year", [CENTURY]),
        ),
        (
            "Sept. ‘46",
            INSECTS,
            reading("1946-09", 1946, 9, None, "month", "monthname-year", [CENTURY]),
        ),
        # The plausible years run from 1750 to the current year.
        ("1750", None, reading("1750", 1750, None, None, "year", "year")),
        (
            str(THIS_YEAR),
            None,
            reading(str(THIS_YEAR), THIS_YEAR, None, None, "year", "year"),
        ),
    ],
)
def test_a_date_with_one_reading_clears_at_the_precision_written(
    literal, rules, expected
):
    source = f"Mindanao, P.I.\n{literal}\nF.G. Werner"
    result = date_parser(literal, source_text=source, date_rules=rules)
    assert result.outcome == LookupStatus.SUCCESS
    assert result.parsed == {"readings": [expected], "year_literal": None}
    assert result.warnings == []


@pytest.mark.parametrize(
    "literal,rules,readings,warnings",
    [
        (
            "4-5-48",
            INSECTS,
            [
                reading("1948-04-05", 1948, 4, 5, "day", "month-day-year", [CENTURY]),
                reading("1948-05-04", 1948, 5, 4, "day", "day-month-year", [CENTURY]),
            ],
            ["several_readings"],
        ),
        (
            "3.9.1946",
            None,
            [
                reading("1946-03-09", 1946, 3, 9, "day", "month-day-year"),
                reading("1946-09-03", 1946, 9, 3, "day", "day-month-year"),
            ],
            ["several_readings"],
        ),
        (
            "12/10/1946",
            INSECTS,
            [
                reading("1946-12-10", 1946, 12, 10, "day", "month-day-year"),
                reading("1946-10-12", 1946, 10, 12, "day", "day-month-year"),
            ],
            ["several_readings"],
        ),
        (
            "4-5-48",
            None,
            [
                reading(None, None, 4, 5, "day", "month-day-year"),
                reading(None, None, 5, 4, "day", "day-month-year"),
            ],
            ["several_readings", "century_unresolved"],
        ),
    ],
)
def test_a_numeric_date_returns_every_order_its_notation_allows(
    literal, rules, readings, warnings
):
    result = date_parser(literal, source_text=f"{literal}\n", date_rules=rules)
    assert result.outcome == LookupStatus.AMBIGUOUS
    assert result.parsed == {"readings": readings, "year_literal": None}
    assert result.warnings == warnings


@pytest.mark.parametrize(
    "literal", ["30 Feb. 1946", "II-30-48", "30.2.1946", "II-29-47"]
)
def test_a_day_the_calendar_lacks_is_no_date(literal):
    result = date_parser(literal, source_text=literal, date_rules=INSECTS)
    assert result.outcome == LookupStatus.NO_MATCH
    assert result.warnings == ["invalid_calendar_date"] and result.parsed is None


@pytest.mark.parametrize(
    "literal,source_text,rules",
    [
        ("4800", MITCHELL, INSECTS),
        ("6400", WERNER, INSECTS),
        ("1749", "1749", None),
        (str(THIS_YEAR + 1), str(THIS_YEAR + 1), None),
        ("3.9.1700", "3.9.1700", None),
        ("IV-1700", "IV-1700", INSECTS),
        (
            "3 sept. '46",
            WERNER,
            {"version": "date-rules-v1", "two_digit_year_century": 1600},
        ),
    ],
)
def test_a_year_outside_1750_to_the_current_year_is_no_date(
    literal, source_text, rules
):
    result = date_parser(literal, source_text=source_text, date_rules=rules)
    assert result.outcome == LookupStatus.NO_MATCH
    assert result.warnings == ["implausible_year"] and result.parsed is None


# Lowercase Roman numerals are months only between a day and a year, joined by
# "." or "-"; "12 x 46" may be a measurement.
@pytest.mark.parametrize(
    "literal",
    ["46", "Mossy forest", "iv-23-48", "iv-1948", "12 x 46", "12 vi 1946"],
)
def test_a_literal_no_approved_notation_fits_is_no_date(literal):
    result = date_parser(literal, source_text=literal, date_rules=INSECTS)
    assert result.outcome == LookupStatus.NO_MATCH
    assert result.warnings == [] and result.parsed is None


@pytest.mark.parametrize(
    "literal,source_text,year_literal",
    [("3 Sept. '46", WERNER, None), ("IV-25", GUATEMALA, "1947")],
)
def test_a_literal_the_reading_does_not_contain_is_blocked(
    literal, source_text, year_literal
):
    result = date_parser(
        literal, source_text=source_text, year_literal=year_literal, date_rules=INSECTS
    )
    assert result.outcome == LookupStatus.POLICY
    assert result.warnings == ["literal_not_in_source"] and result.parsed is None


@pytest.mark.parametrize(
    "rules",
    [
        {"version": "date-rules-v1", "two_digit_year_century": 1950},
        {"version": "date-rules-v1", "two_digit_year_century": "1900"},
        {"version": "date-rules-v1", "two_digit_year_century": True},
        {"two_digit_year_century": 1900},
        {"version": "date-rules-v1", "roman_numeral_months": "true"},
        {"version": "date-rules-v1", "roman_numeral_months": 1},
    ],
)
def test_a_malformed_date_rule_set_is_refused(rules):
    with pytest.raises(ValueError):
        date_parser("1946", source_text="1946", date_rules=rules)


@pytest.mark.parametrize(
    "literal,digits",
    [
        ("FMNHINS\n4486784", "4486784"),
        ("4486784", "4486784"),
        ("FMNHINS 4486784", "4486784"),
        ("FMNH-INS #4486784", "4486784"),
        ("fmnh ins 0012345", "0012345"),
    ],
)
def test_a_catalog_number_is_its_digits_exactly_as_written(literal, digits):
    source = "FMNHINS\n4486784\nFMNHINS 4486784 FMNH-INS #4486784 fmnh ins 0012345"
    result = catalog_number_validator(literal, source_text=source)
    assert (result.tool, result.tool_version) == (
        "catalog_number_validator",
        "catalog-number-v1",
    )
    assert result.outcome == LookupStatus.SUCCESS
    assert result.parsed == {"catalog_number": digits}
    assert result.warnings == [] and result.sub_calls == []


@pytest.mark.parametrize(
    "literal", ["4486784a", "FMNH 12", "1234", "1234567890", "FMNHINS #", "Mindanao"]
)
def test_anything_else_is_no_catalog_number(literal):
    result = catalog_number_validator(literal, source_text=f"P.I.\n{literal}\n")
    assert result.outcome == LookupStatus.NO_MATCH
    assert result.parsed is None


def test_a_catalog_number_the_reading_does_not_contain_is_blocked():
    result = catalog_number_validator("FMNHINS 4486784", source_text="FMNHINS\n4486784")
    assert result.outcome == LookupStatus.POLICY
    assert result.warnings == ["literal_not_in_source"] and result.parsed is None
