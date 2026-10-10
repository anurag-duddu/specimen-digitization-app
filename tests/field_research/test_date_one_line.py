"""A day and month followed on the same line by their year, which no notation reads
whole ("IV-25 1948", "IV-25, 1948", "25.IV, 1948"; field_research/date_lines).

Before this, such a literal was no date, and the brief's other route (the year
passed as `year_literal`) never settled: step._check_row runs the check again on
the literal alone, so the value stayed unsupported (review 297c, note 5). The
check now reads the line as one date under the rules of a year on the line below
its date, and the step keeps its row.
"""

from __future__ import annotations

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.field_research import checks
from specimen_digitization.field_research import step as field_step

PILOT = {
    "version": "date-rules-v1",
    "two_digit_year_century": 1900,
    "roman_numeral_months": True,
}
E_GRAVE = "\N{LATIN SMALL LETTER E WITH GRAVE}"
N_TILDE = "\N{LATIN SMALL LETTER N WITH TILDE}"


def date(literal, texts, **more):
    return checks.parse_date(literal, reading_texts=texts, date_rules=PILOT, **more)


def row(literal, value, texts, key="date_visited_from"):
    return field_step._check_row(
        key,
        ("date_parser",),
        literal,
        value,
        texts=texts,
        date_rules=PILOT,
        asset_id=None,
        blobs=None,
    )


# Labels from several countries, as their collectors wrote the date: the reading's text,
# the literal, the date.
READ = [
    ("Guatemala, IV-25 1948, R.D. Mitchell", "IV-25 1948", "1948-04-25"),
    ("Mexico, Chiapas, Tapachula, IV-25, 1948", "IV-25, 1948", "1948-04-25"),
    ("Venezuela, Rancho Grande, IV.25 1948", "IV.25 1948", "1948-04-25"),
    ("Brasil, Nova Teutonia, 25.IV, 1948, F. Plaumann", "25.IV, 1948", "1948-04-25"),
    (f"France, Is{E_GRAVE}re, 25 IV, 1948", "25 IV, 1948", "1948-04-25"),
    ("Deutschland, Bayern, 25-IV, 1948, leg. Schmidt", "25-IV, 1948", "1948-04-25"),
    ("Italia, Bolzano, 25.iv 1948", "25.iv 1948", "1948-04-25"),
    (f"Espa{N_TILDE}a, Madrid, IV-25. 1948. leg. Lopez", "IV-25. 1948.", "1948-04-25"),
    ("Peru, Cusco, 3.XII,1946", "3.XII,1946", "1946-12-03"),
    ("Colombia, Cali, IV-25 '48", "IV-25 '48", "1948-04-25"),
    # A determination's date written whole on its line reads too (Date Identified's).
    ("det. J. Smith, IV-25 1950", "IV-25 1950", "1950-04-25"),
    ("det. J. Smith\nIV-25 1950", "IV-25 1950", "1950-04-25"),
]


@pytest.mark.parametrize(("text", "literal", "iso"), READ, ids=[r[1] for r in READ])
def test_a_day_and_month_then_their_year_on_one_line_read_as_one_date(
    text, literal, iso
):
    result = date(literal, [text])

    assert result.status == LookupStatus.SUCCESS, result.as_dict()
    assert result.values == (iso,)
    assert result.readings[0].via == ("one_line",)


@pytest.mark.parametrize(("text", "literal", "iso"), READ, ids=[r[1] for r in READ])
def test_the_step_keeps_a_check_row_for_a_one_line_date_and_names_how_it_was_read(
    text, literal, iso
):
    kept = row(literal, iso, [text])

    assert kept is not None and f"{literal} reads as {iso}" in kept.excerpt
    assert '"via": ["one_line"]' in kept.excerpt


def test_a_month_and_a_bare_number_read_as_a_day_once_the_year_is_on_their_line():
    # "IV-25" alone is April 25 or, under the century rule, April 1925; with 1948 on its
    # line it is April 25, 1948 only.
    result = date("IV-25 1948", ["Guatemala, IV-25 1948"])

    assert result.values == ("1948-04-25",)
    assert row("IV-25 1948", "1925-04", ["Guatemala, IV-25 1948"]) is None


def test_an_apostrophe_year_records_the_century_rule():
    result = date("IV-25 '48", ["Colombia, Cali, IV-25 '48"])

    assert (
        result.readings[0].century_rule == "date-rules-v1:two_digit_year_century=1900"
    )


@pytest.mark.parametrize(
    ("text", "literal", "note"),
    [
        # The year is followed by more than a comma, semicolon or period and other text.
        ("Guatemala, IV-25 1948 m", "IV-25 1948", "one_line_year_not_alone"),
        ("Guatemala, IV-25 1948 5", "IV-25 1948", "one_line_year_not_alone"),
        ("Guatemala, IV-25 1948.5", "IV-25 1948", "one_line_year_not_alone"),
        (
            "Guatemala, IV-25, 1948', R.D. Mitchell",
            "IV-25, 1948",
            "one_line_year_not_alone",
        ),
        (
            "Guatemala, IV-25 1948 det. J. Smith",
            "IV-25 1948",
            "one_line_year_not_alone",
        ),
        (
            "Guatemala, IV-25 1948 R.D. Mitchell",
            "IV-25 1948",
            "one_line_year_not_alone",
        ),
        (
            "Guatemala, IV-25 1948: R.D. Mitchell",
            "IV-25 1948:",
            "one_line_year_not_alone",
        ),
        # Something else on the line could be a date.
        (
            "Guatemala, 3.VI.1947, IV-25 1948",
            "IV-25 1948",
            "one_line_holds_another_date",
        ),
        ("Guatemala, IV-25 1948, 3 Sept.", "IV-25 1948", "one_line_holds_another_date"),
        # A measurement on the line or on the line above, or a unit below.
        (
            "Guatemala, Alt. 1500 m, IV-25 1948",
            "IV-25 1948",
            "one_line_year_may_be_a_measurement",
        ),
        (
            "Guatemala, IV-25 1948, 4800 ft.",
            "IV-25 1948",
            "one_line_year_may_be_a_measurement",
        ),
        (
            "Guatemala\nAlt.\nIV-25 1900",
            "IV-25 1900",
            "one_line_year_may_be_a_measurement",
        ),
        (
            "Guatemala, IV-25 1900\nm",
            "IV-25 1900",
            "one_line_year_may_be_a_measurement",
        ),
        (
            "Bolzano\nQuota 1900 m\n25.IV, 1948",
            "25.IV, 1948",
            "one_line_year_may_be_a_measurement",
        ),
    ],
)
def test_a_one_line_date_that_breaks_a_rule_is_no_date_and_names_the_rule(
    text, literal, note
):
    result = date(literal, [text])
    year = literal.rstrip(".:,").split()[-1].lstrip("'")
    value = f"{'19' if len(year) == 2 else ''}{year}-04-25"

    assert result.status == LookupStatus.NO_MATCH and result.notes == (note,), (
        result.as_dict()
    )
    assert row(literal, value, [text]) is None


@pytest.mark.parametrize(
    "literal",
    [
        # A semicolon or a colon between the date and the year, or no separator.
        "IV-25; 1948",
        "IV-25: 1948",
        # A bare two-digit number, a month and a day joined by a space, a lowercase
        # numeral month-first: none is read on its own either.
        "IV-25 48",
        "IV 25 1948",
        "iv-25 1948",
        # An all-numeric date: which number is the month is never picked.
        "4-25 1948",
        "25.4 1948",
        "4/25 1948",
        "3.4 1948",
        # A date that states its own year, then another year.
        "25.IV.48 1948",
    ],
)
def test_a_line_that_is_not_a_day_and_month_then_a_year_is_no_date(literal):
    text = f"Guatemala, {literal}"
    result = date(literal, [text])

    assert result.status == LookupStatus.NO_MATCH and result.values == (), (
        result.as_dict()
    )
    assert all(
        row(literal, value, [text]) is None
        for value in ("1948-04-25", "1948-03-04", "1948-04-03")
    )


@pytest.mark.parametrize(
    ("literal", "iso", "order"),
    [
        # Forms a notation reads whole are read as before, not by this rule.
        ("25 IV 1948", "1948-04-25", "day-month-year"),
        ("25.IV 1948", "1948-04-25", "day-month-year"),
        ("IV-25-1948", "1948-04-25", "month-day-year"),
        ("3 Sept. 1948", "1948-09-03", "day-monthname-year"),
        ("25 de abril, 1948", "1948-04-25", "day-monthname-year"),
        ("25. April, 1948", "1948-04-25", "day-monthname-year"),
        ("25.4. 1948", "1948-04-25", "day-month-year"),  # 25 is no month
    ],
)
def test_a_form_a_notation_reads_whole_is_read_as_before(literal, iso, order):
    result = date(literal, [f"Guatemala, {literal}"])

    assert result.status == LookupStatus.SUCCESS and result.values == (iso,)
    assert result.readings[0].order == order and result.readings[0].via == ()


def test_an_all_numeric_date_with_a_space_before_its_year_stays_ambiguous():
    result = date("3.4. 1948", ["Guatemala, 3.4. 1948"])

    assert (
        result.status == LookupStatus.AMBIGUOUS
        and "day_month_order_ambiguous" in result.notes
    )
    assert row("3.4. 1948", "1948-03-04", ["Guatemala, 3.4. 1948"]) is None


def test_readers_that_disagree_on_a_one_line_date_leave_it_ambiguous():
    texts = [
        "Guatemala, IV-25 1948, R.D. Mitchell",
        "Guatemala, IV-25 1948 m, R.D. Mitchell",
    ]

    result = date("IV-25 1948", texts, reading_names=["1A", "1B"])

    assert result.status == LookupStatus.AMBIGUOUS
    assert result.notes == (
        "readers_disagree_on_date",
        "1A: 1948-04-25; 1B: not a date (one_line_year_not_alone)",
    )
    assert row("IV-25 1948", "1948-04-25", texts) is None


def test_readers_that_agree_on_a_one_line_date_settle_it():
    texts = [
        "Guatemala, IV-25 1948, R.D. Mitchell",
        "Guatemala, IV-25 1948. R.D. Mitchell",
    ]

    assert date("IV-25 1948", texts).values == ("1948-04-25",)
    assert row("IV-25 1948", "1948-04-25", texts) is not None


@pytest.mark.parametrize("text", ["IV-25 1948-4 Guatemala", "Guatemala, IV-25 1948-49"])
def test_a_one_line_date_inside_a_hyphen_joined_token_is_still_no_date(text):
    result = date("IV-25 1948", [text])

    assert result.status == LookupStatus.NO_MATCH and result.notes == (
        "part_of_hyphenated_token",
    )
    assert row("IV-25 1948", "1948-04-25", [text]) is None
