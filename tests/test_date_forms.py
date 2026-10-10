"""The date parser's notations, by form: Roman and written months in seven
languages, years written first, ordinals, two-digit years and ranges (G24, G29).

Each accepted row names what the parser must return (the start, the end of a
range, the precision) and the rule it records as the reading's `order`, so a
trace shows which rule matched. Every literal stands alone in its reading.
The pilot's own labels, and the slide codes beside their dates, are the last
tables; the split-line forms are in `field_research/test_date_split_lines.py`.
"""

from __future__ import annotations

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.field_validators import date_parser

INSECTS = {
    "version": "date-rules-v1",
    "two_digit_year_century": 1900,
    "roman_numeral_months": True,
}
NO_CENTURY = {"version": "date-rules-v1", "roman_numeral_months": True}
NO_ROMAN = {"version": "date-rules-v1", "two_digit_year_century": 1900}
MASCULINE_ORDINAL = "\N{MASCULINE ORDINAL INDICATOR}"
E_ACUTE = "\N{LATIN SMALL LETTER E WITH ACUTE}"
U_CIRCUMFLEX = "\N{LATIN SMALL LETTER U WITH CIRCUMFLEX}"
A_UMLAUT = "\N{LATIN SMALL LETTER A WITH DIAERESIS}"
C_CEDILLA = "\N{LATIN SMALL LETTER C WITH CEDILLA}"
EN_DASH = "\N{EN DASH}"


def read(literal, rules=INSECTS, **more):
    result = date_parser(literal, source_text=literal, date_rules=rules, **more)
    return result, (result.parsed or {}).get("readings", [])


# literal, start, end (None for one date), precision, the rule that matched.
SINGLE_DATES = [
    # Roman months in every position.
    ("14.IX.1946", "1946-09-14", None, "day", "day-month-year"),
    ("IX-14-46", "1946-09-14", None, "day", "month-day-year"),
    ("3.iv.1948", "1948-04-03", None, "day", "day-month-year"),
    ("14 IX 1946", "1946-09-14", None, "day", "day-month-year"),
    ("IV-24-48", "1948-04-24", None, "day", "month-day-year"),
    ("IX - 14 - 46", "1946-09-14", None, "day", "month-day-year"),
    ("IX/14/46", "1946-09-14", None, "day", "month-day-year"),
    ("14.IX.'46", "1946-09-14", None, "day", "day-month-year"),
    ("1946.IX.14", "1946-09-14", None, "day", "year-month-day"),
    ("1946-IX-14", "1946-09-14", None, "day", "year-month-day"),
    ("1946 IX 14", "1946-09-14", None, "day", "year-month-day"),
    ("1946.ix.14", "1946-09-14", None, "day", "year-month-day"),
    ("1946.IX", "1946-09", None, "month", "year-month"),
    ("IX.1946", "1946-09", None, "month", "month-year"),
    ("XI .46", "1946-11", None, "month", "month-year"),
    ("XI.'46", "1946-11", None, "month", "month-year"),
    # English.
    ("3 sept. '46", "1946-09-03", None, "day", "day-monthname-year"),
    ("6-Sept-1946", "1946-09-06", None, "day", "day-monthname-year"),
    ("6-Sept.-1946", "1946-09-06", None, "day", "day-monthname-year"),
    ("Sept. 3, 1946", "1946-09-03", None, "day", "monthname-day-year"),
    ("September 1946", "1946-09", None, "month", "monthname-year"),
    ("Sept '46", "1946-09", None, "month", "monthname-year"),
    ("3rd Sept. 1946", "1946-09-03", None, "day", "day-monthname-year"),
    ("Sept. 3rd, 1946", "1946-09-03", None, "day", "monthname-day-year"),
    ("3rd of May 1946", "1946-05-03", None, "day", "day-monthname-year"),
    ("1946 Sept. 3", "1946-09-03", None, "day", "year-monthname-day"),
    ("1946 Sept", "1946-09", None, "month", "year-monthname"),
    # Spanish.
    ("14 de septiembre de 1946", "1946-09-14", None, "day", "day-monthname-year"),
    ("14 sept. 1946", "1946-09-14", None, "day", "day-monthname-year"),
    ("3 ene. 1948", "1948-01-03", None, "day", "day-monthname-year"),
    ("agosto de 1946", "1946-08", None, "month", "monthname-year"),
    ("1o de mayo de 1946", "1946-05-01", None, "day", "day-monthname-year"),
    (f"1{MASCULINE_ORDINAL} mayo 1946", "1946-05-01", None, "day", "day-monthname-year"),
    ("dic. 5, 1946", "1946-12-05", None, "day", "monthname-day-year"),
    ("5 setiembre 1946", "1946-09-05", None, "day", "day-monthname-year"),
    # French.
    ("3 janv. 1946", "1946-01-03", None, "day", "day-monthname-year"),
    ("1er sept. 1946", "1946-09-01", None, "day", "day-monthname-year"),
    (f"12 f{E_ACUTE}vr. 1946", "1946-02-12", None, "day", "day-monthname-year"),
    (f"5 ao{U_CIRCUMFLEX}t 1946", "1946-08-05", None, "day", "day-monthname-year"),
    ("3 mars 1946", "1946-03-03", None, "day", "day-monthname-year"),
    ("14 juil. 1946", "1946-07-14", None, "day", "day-monthname-year"),
    # German.
    ("3 Mai 1946", "1946-05-03", None, "day", "day-monthname-year"),
    ("3. Mai 1946", "1946-05-03", None, "day", "day-monthname-year"),
    ("14. Okt. 1946", "1946-10-14", None, "day", "day-monthname-year"),
    (f"5 M{A_UMLAUT}rz 1946", "1946-03-05", None, "day", "day-monthname-year"),
    ("12 Dez. 1946", "1946-12-12", None, "day", "day-monthname-year"),
    ("Juni 1946", "1946-06", None, "month", "monthname-year"),
    # Portuguese.
    ("12 de outubro de 1946", "1946-10-12", None, "day", "day-monthname-year"),
    ("3 set. 1946", "1946-09-03", None, "day", "day-monthname-year"),
    ("5 fev. 1946", "1946-02-05", None, "day", "day-monthname-year"),
    (f"14 mar{C_CEDILLA}o 1946", "1946-03-14", None, "day", "day-monthname-year"),
    # Italian.
    ("12 ott. 1946", "1946-10-12", None, "day", "day-monthname-year"),
    ("3 sett. 1946", "1946-09-03", None, "day", "day-monthname-year"),
    ("15 maggio 1946", "1946-05-15", None, "day", "day-monthname-year"),
    ("5 giu. 1946", "1946-06-05", None, "day", "day-monthname-year"),
    ("20 gen. 1946", "1946-01-20", None, "day", "day-monthname-year"),
    # Latin.
    ("3 Septembris 1946", "1946-09-03", None, "day", "day-monthname-year"),
    ("14 Octobris 1946", "1946-10-14", None, "day", "day-monthname-year"),
    ("5 Junii 1946", "1946-06-05", None, "day", "day-monthname-year"),
    ("17 Martii 1946", "1946-03-17", None, "day", "day-monthname-year"),
    # Numeric, settled only where a part over 12 or the written year fixes it.
    ("13-5-48", "1948-05-13", None, "day", "day-month-year"),
    ("5/13/1948", "1948-05-13", None, "day", "month-day-year"),
    ("5-5-48", "1948-05-05", None, "day", "month-day-year"),
    ("1946-09-14", "1946-09-14", None, "day", "year-month-day"),
    ("1946/13/04", "1946-04-13", None, "day", "year-day-month"),
    # A year alone, with or without its century.
    ("1946", "1946", None, "year", "year"),
    ("'46", "1946", None, "year", "year"),
    # Ranges, read into a start and an end.
    ("3-5.IX.1946", "1946-09-03", "1946-09-05", "day", "range:day..date"),
    ("3-5.ix.1946", "1946-09-03", "1946-09-05", "day", "range:day..date"),
    ("VIII-IX.46", "1946-08", "1946-09", "month", "range:month..month-year"),
    ("3.IX-5.X.1946", "1946-09-03", "1946-10-05", "day", "range:day-month..date"),
    ("3.IX.1946-5.X.1946", "1946-09-03", "1946-10-05", "day", "range:date..date"),
    ("10-12 Sept. 1946", "1946-09-10", "1946-09-12", "day", "range:day..date"),
    ("Sept. 3-5, 1946", "1946-09-03", "1946-09-05", "day", "range:month-day..day-year"),
    ("3 Sept.-5 Oct. 1946", "1946-09-03", "1946-10-05", "day", "range:day-month..date"),
    ("Sept.-Oct. 1946", "1946-09", "1946-10", "month", "range:month..month-year"),
    (f"3{EN_DASH}5 ao{U_CIRCUMFLEX}t 1946", "1946-08-03", "1946-08-05", "day", "range:day..date"),
    ("12-14 de septiembre de 1946", "1946-09-12", "1946-09-14", "day", "range:day..date"),
    ("IV-23-48 - IV-25-48", "1948-04-23", "1948-04-25", "day", "range:date..date"),
]


@pytest.mark.parametrize(
    ("literal", "start", "end", "precision", "rule"),
    SINGLE_DATES,
    ids=[row[0] for row in SINGLE_DATES],
)
def test_a_form_reads_as_its_start_end_and_precision(literal, start, end, precision, rule):
    result, readings = read(literal)

    assert result.outcome == LookupStatus.SUCCESS, result.warnings
    assert result.warnings == []
    assert len(readings) == 1
    reading = readings[0]
    assert (reading["iso"], reading["precision"], reading["order"]) == (start, precision, rule)
    assert reading.get("end", {}).get("iso") == end
    if end is not None:
        assert reading["end"]["precision"] == precision


def test_there_are_at_least_sixty_forms_in_seven_languages():
    assert len(SINGLE_DATES) >= 60
    words = {row[0] for row in SINGLE_DATES}
    assert {"3 Septembris 1946", "12 ott. 1946", "14 juil. 1946", "3 Mai 1946"} <= words


# A form that states no year, or only the order of two numbers, is not settled.
AMBIGUOUS = [
    ("4-5-48", ["several_readings", "day_month_order_ambiguous"], ["1948-04-05", "1948-05-04"]),
    ("3.9.1946", ["several_readings", "day_month_order_ambiguous"], ["1946-03-09", "1946-09-03"]),
    ("12/10/1946", ["several_readings", "day_month_order_ambiguous"], ["1946-12-10", "1946-10-12"]),
    ("1946-04-05", ["several_readings", "day_month_order_ambiguous"], ["1946-04-05", "1946-05-04"]),
    ("14.IX", ["year_missing"], [None]),
    ("14 IX", ["year_missing"], [None]),
    ("3 Sept.", ["year_missing"], [None]),
    ("14 de septiembre", ["year_missing"], [None]),
]


@pytest.mark.parametrize(("literal", "warnings", "isos"), AMBIGUOUS, ids=[r[0] for r in AMBIGUOUS])
def test_a_form_that_leaves_a_choice_names_it_and_settles_nothing(literal, warnings, isos):
    result, readings = read(literal)

    assert result.outcome == LookupStatus.AMBIGUOUS
    assert result.warnings == warnings
    assert [r["iso"] for r in readings] == isos


def test_numeric_dates_say_which_ambiguity_is_left():
    # A part over 12 fixes day against month; a written four-digit year fixes the year.
    assert read("13-5-48")[0].outcome == LookupStatus.SUCCESS
    assert read("5-13-1948")[0].outcome == LookupStatus.SUCCESS
    result, readings = read("4-5-1948")
    assert "day_month_order_ambiguous" in result.warnings
    assert {r["year"] for r in readings} == {1948}


@pytest.mark.parametrize(
    ("literal", "rules", "warning"),
    [
        ("3-5 sept. '46", NO_CENTURY, "century_unresolved"),
        ("VIII-IX.46", NO_CENTURY, "century_unresolved"),
        ("14.IX.'46", NO_CENTURY, "century_unresolved"),
    ],
)
def test_a_two_digit_year_needs_the_century_rule_in_every_form(literal, rules, warning):
    result, readings = read(literal, rules)

    assert result.outcome == LookupStatus.AMBIGUOUS and warning in result.warnings
    assert all(r["iso"] is None or r["iso"] != "1946-09-03" for r in readings)


@pytest.mark.parametrize(
    "literal", ["14.IX", "1946.IX.14", "1946-IX-14", "VIII-IX.46", "3-5.IX.1946", "3.IX-5.X.1946"]
)
def test_a_roman_month_is_not_read_unless_the_profile_enables_it(literal):
    result, readings = read(literal, NO_ROMAN)

    assert result.outcome == LookupStatus.NO_MATCH
    assert result.warnings == ["roman_numeral_months_not_enabled"] and readings == []


REFUSED = [
    # Not dates at all.
    ("Mossy forest", None),
    ("6400'", None),
    ("Davao Prov.", None),
    ("IV-a3-48", None),
    ("3 Mossy 1946", None),
    ("46", None),
    ("Sept.", None),
    # Dates the calendar or the plausible years refuse.
    ("30 Feb. 1946", "invalid_calendar_date"),
    ("31 juin 1946", "invalid_calendar_date"),
    ("3 sept. 1700", "implausible_year"),
    ("31-IX-1946", "invalid_calendar_date"),
    # Ranges and years the parser does not read.
    ("3.9-5.10.1946", None),
    ("1946-48", None),
    ("12 vi 1946", None),
    # A range that ends before it starts, and one the months make impossible.
    ("5-3.IX.1946", "range_end_before_start"),
    ("IX-VIII.46", "range_end_before_start"),
    ("30-31 Feb. 1946", "invalid_calendar_date"),
]


@pytest.mark.parametrize(("literal", "warning"), REFUSED, ids=[r[0] for r in REFUSED])
def test_a_form_that_is_no_date_is_refused_with_its_reason(literal, warning):
    result, readings = read(literal)

    assert result.outcome == LookupStatus.NO_MATCH
    assert result.warnings == ([warning] if warning else [])
    assert readings == []


# Every date and code the ten pilot labels write (the readings of the real run
# of 2026-10-09), each as its readers wrote it.
PILOT_DATES = [
    ("3 sept. '46", "1946-09-03", "day-monthname-year"),  # 105526321, reader 2A
    ("3 Sept. '46", "1946-09-03", "day-monthname-year"),  # 105526321, reader 2B
    ("6-Sept-1946", "1946-09-06", "day-monthname-year"),  # 105526322
    ("6-Sept.-1946", "1946-09-06", "day-monthname-year"),  # 105526323, reader 2A
    ("6-Sept.-1948", "1948-09-06", "day-monthname-year"),  # 105526323, reader 2B misread
    ("IX-14-46", "1946-09-14", "month-day-year"),  # 105526324, 105526325
    ("IX - 14 - 46", "1946-09-14", "month-day-year"),  # 105526326
    ("XI .46", "1946-11", "month-year"),  # 105526327
    ("IV-24-48", "1948-04-24", "month-day-year"),  # 105526328
    ("IV-23-48", "1948-04-23", "month-day-year"),  # 105526329, reader 2B
]


@pytest.mark.parametrize(("literal", "iso", "rule"), PILOT_DATES, ids=[r[0] for r in PILOT_DATES])
def test_every_date_the_pilot_labels_write_reads(literal, iso, rule):
    source = f"Mindanao, P.I.\n{literal}\nH. Hoogstraal"
    result = date_parser(literal, source_text=source, date_rules=INSECTS)

    assert result.outcome == LookupStatus.SUCCESS
    assert [(r["iso"], r["order"]) for r in result.parsed["readings"]] == [(iso, rule)]


PILOT_NOT_DATES = [
    ("10-6-78-la", "slide_code"),
    ("10-6-78-1a", "slide_code"),
    ("9-25-81-la", "slide_code"),
    ("9-25-81-1a", "slide_code"),
    ("IX-17-66-2", "slide_code"),
    ("IX-17-66-1", "slide_code"),
    ("IX - 3 - 66 - 10", None),  # spaced: no code reason, still no date
    ("IX-3-66-10", "slide_code"),
    ("V-4-67-1", "slide_code"),
    ("VI-24-68-7.", "slide_code"),
    ("VII-18-66-1", "slide_code"),
    ("IV-29-68-4", "slide_code"),
    ("IV- 29-68-4", "slide_code"),
    ("IV-29-68-2", "slide_code"),
    ("IV-29-68-a", "slide_code"),
    ("p-95-81-16", "slide_code"),
]


@pytest.mark.parametrize(("literal", "warning"), PILOT_NOT_DATES, ids=[r[0] for r in PILOT_NOT_DATES])
def test_a_slide_code_the_pilot_labels_write_is_still_no_date(literal, warning):
    source = f"{literal}\nE. slope Mt. McKinley"
    result = date_parser(literal, source_text=source, date_rules=INSECTS)

    assert result.outcome == LookupStatus.NO_MATCH
    assert result.warnings == ([warning] if warning else [])


def test_the_date_beside_an_elevation_reads_without_it():
    # 105526325: "IX-14-46 3300'" is one line, and the date is the literal.
    source = "H. Hoogstraal\nIX-14-46 3300'\nCNHM"
    result = date_parser("IX-14-46", source_text=source, date_rules=INSECTS)

    assert result.outcome == LookupStatus.SUCCESS
    assert result.parsed["readings"][0]["iso"] == "1946-09-14"


def test_a_date_range_is_not_a_slide_code():
    # Four or more hyphen-joined parts whose first three are date-shaped are a
    # code (HARNESS.md section 8); a written range is not that.
    for literal in ("12-14 de septiembre de 1946", "3-5.IX.1946", "VIII-IX.46"):
        assert read(literal)[0].warnings == []
