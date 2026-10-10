"""A date written over two lines of one label, a range's two ends, and the rule
that records how each date was read (G24, G29, G44; field_research/date_lines).

The first label is the pilot's 105526330 as its readers wrote it: "IV-25" ends
one line and "1948" starts the next.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.field_research import checks, derive
from specimen_digitization.field_research import step as field_step

PILOT = {"version": "date-rules-v1", "two_digit_year_century": 1900, "roman_numeral_months": True}
NO_CENTURY = {"version": "date-rules-v1", "roman_numeral_months": True}
READER_A = "IV-29-68-2\nYepocapa,4800 ft.\nChimaltenago\nGuatemala,IV-25\n1948, R.D. Mitchell\nfemale legs Sp.#1"
READER_B = "IV-29-68-a\nYepocapa, 4800 ft.\nChimaltenango\nGuatemala, IV-25\n1948, R.D. Mitchell\nfemale legs Sp.#1"
PILOT_READINGS = [READER_A, READER_B]
SPLIT = "IV-25\n1948"


def date(literal, texts, *, rules=PILOT, **more):
    return checks.parse_date(literal, reading_texts=texts, date_rules=rules, **more)


def test_the_pilots_split_date_reads_as_one_date():
    result = date(SPLIT, PILOT_READINGS)

    assert result.status == LookupStatus.SUCCESS
    assert result.values == ("1948-04-25",)
    [reading] = result.readings
    assert (reading.iso, reading.precision, reading.order) == ("1948-04-25", "day", "month-day")
    assert reading.via == ("split_lines",)
    assert reading.century_rule is None  # the year is written whole
    assert result.notes == ()


def test_the_pilots_day_and_month_alone_take_the_year_on_the_next_line():
    result = date("IV-25", PILOT_READINGS)

    assert result.status == LookupStatus.SUCCESS
    assert result.values == ("1948-04-25",)
    assert result.readings[0].via == ("year_on_next_line",)
    assert "1925-04" not in result.values


def test_the_check_shows_the_rule_that_matched_to_the_expert():
    shown = date(SPLIT, PILOT_READINGS).as_dict()

    assert shown["status"] == "success" and shown["literal"] == SPLIT
    assert shown["readings"] == [
        {"iso": "1948-04-25", "precision": "day", "order": "month-day", "via": ("split_lines",)}]


@pytest.mark.parametrize(
    ("text", "literal", "iso", "via"),
    [
        # The year ends the line above, the date starts the next.
        ("Guatemala\nR.D. Mitchell 1948\nIV-25 Yepocapa", "IV-25", "1948-04-25", "year_on_previous_line"),
        ("Guatemala\nR.D. Mitchell 1948\nIV-25 Yepocapa", "1948\nIV-25", "1948-04-25", "split_lines"),
        # The day and month by name, in another language.
        ("Cali\n14 sept.\n1946 leg. X", "14 sept.", "1946-09-14", "year_on_next_line"),
        ("Cali\n14 de septiembre\n1946", "14 de septiembre\n1946", "1946-09-14", "split_lines"),
        ("Cali\n3.IX\n1946", "3.IX", "1946-09-03", "year_on_next_line"),
        # A year after an apostrophe: the century is inferred and recorded.
        ("Davao\n3 Sept.\n'46", "3 Sept.\n'46", "1946-09-03", "split_lines"),
    ],
)
def test_a_date_and_a_year_on_adjacent_lines_read_as_one(text, literal, iso, via):
    result = date(literal, [text])

    assert result.status == LookupStatus.SUCCESS, result.notes
    assert result.values == (iso,)
    assert result.readings[0].via == (via,)


def test_an_apostrophe_year_on_the_next_line_records_the_century_rule():
    result = date("3 Sept.\n'46", ["Davao\n3 Sept.\n'46"])

    assert result.readings[0].century_rule == "date-rules-v1:two_digit_year_century=1900"
    # Without the profile's century rule the year stays open.
    open_ = date("3 Sept.\n'46", ["Davao\n3 Sept.\n'46"], rules=NO_CENTURY)
    assert open_.status == LookupStatus.AMBIGUOUS and open_.values == ()


@pytest.mark.parametrize(
    ("text", "why"),
    [
        # A blank line, or another line, between the date and the year.
        ("Guatemala, IV-25\n\n1948", "a blank line between"),
        ("Guatemala, IV-25\nR.D. Mitchell\n1948", "another line between"),
        # The year is not alone: a bare two-digit number could be anything.
        ("Guatemala, IV-25\n48", "a bare two-digit number"),
        ("Guatemala, IV-25\n4800 ft.", "an elevation"),
        # Something else on the lines could be a date.
        ("Guatemala, IV-25 and 3.VI\n1948", "another date on the date's line"),
        ("Guatemala, IV-25\n1948, 12 Sept.", "another date on the year's line"),
        ("Guatemala, IV-25 1947\n1948", "another year on the date's line"),
        ("Guatemala, Mai IV-25\n1948", "a month word on the date's line"),
        # The line above and the line below give different years.
        ("1947\nIV-25\n1948", "two different years"),
        # The date is not the end of its line.
        ("IV-25 Guatemala\n1948", "text after the date on its line"),
    ],
)
def test_lines_that_are_not_clearly_one_date_stay_apart(text, why):
    result = date("IV-25", [text])

    assert result.status == LookupStatus.AMBIGUOUS, why
    assert "year_missing" in result.notes
    assert result.values == ("1925-04",)  # only the month-and-year reading, never a day
    assert all(r.via == () for r in result.readings)


@pytest.mark.parametrize(
    "text",
    [
        "Guatemala 3.VI, IV-25\n1948",
        "Guatemala, IV-25\n1948, 12 Sept.",
        "1947 Guatemala IV-25\n1948",
    ],
)
def test_a_two_line_literal_with_another_date_on_its_lines_is_no_date(text):
    result = date("IV-25\n1948", [text])

    assert result.status == LookupStatus.NO_MATCH
    assert result.notes == ("split_lines_hold_another_date",)


def test_a_date_that_states_its_own_year_is_not_joined_to_a_year_beside_it():
    result = date("IV-25-48\n1948", ["Guatemala, IV-25-48\n1948"])

    assert result.status == LookupStatus.NO_MATCH
    assert result.notes == ("split_lines_state_two_years",)


def test_a_literal_of_two_lines_that_is_no_date_and_year_is_read_by_the_parser_alone():
    result = date("Davao\n1948", ["Mindanao, Davao\n1948, Hoogstraal"])

    assert result.status == LookupStatus.NO_MATCH and result.values == ()


def test_an_expert_s_year_literal_is_the_year_wherever_the_reading_writes_it():
    # The year is three lines away: not adjacent, but the expert named it.
    text = "Guatemala, IV-25\nR.D. Mitchell\nlot 2\n1948"

    alone = date("IV-25", [text])
    named = date("IV-25", [text], year_literal="1948")

    assert alone.status == LookupStatus.AMBIGUOUS and "year_missing" in alone.notes
    assert named.status == LookupStatus.SUCCESS and named.values == ("1948-04-25",)
    assert named.readings[0].via == ("year_literal",)


def test_two_readers_that_differ_are_each_read_by_their_own_text():
    # Reader B drops the year line: the date alone stays open there.
    texts = ["Guatemala, IV-25\n1948, R.D. Mitchell", "Guatemala, IV-25\nR.D. Mitchell"]

    result = date("IV-25", texts)

    assert result.status == LookupStatus.SUCCESS and result.values == ("1948-04-25",)


# -- ranges and the field that takes their end ---------------------------------------------------

RANGE_TEXT = "Mindanao, P.I.\n3-5.IX.1946 Davao\nF. G. Werner"


def test_a_range_reads_as_a_start_and_an_end_with_the_start_as_the_value():
    result = date("3-5.IX.1946", [RANGE_TEXT])

    assert result.status == LookupStatus.SUCCESS
    [reading] = result.readings
    assert (reading.iso, reading.end, reading.precision, reading.end_precision) == (
        "1946-09-03", "1946-09-05", "day", "day")
    assert reading.order == "range:day..date"
    assert result.values == ("1946-09-03",)
    assert result.as_dict()["readings"] == [{"iso": "1946-09-03", "precision": "day",
        "order": "range:day..date", "end": "1946-09-05", "end_precision": "day"}]


def test_date_visited_to_takes_a_ranges_end_and_never_its_start():
    start = date("3-5.IX.1946", [RANGE_TEXT])
    end = date("3-5.IX.1946", [RANGE_TEXT], part=checks.DATE_PART["date_visited_to"])

    assert start.values == ("1946-09-03",) and end.values == ("1946-09-05",)
    assert end.part == "end" and end.as_dict()["part"] == "end"
    assert "part" not in start.as_dict()


def test_a_single_date_is_its_own_end_for_an_explicit_end_date():
    # "to 14.X.1946" written as its own date: the To field may take it as written.
    result = date("14.X.1946", ["3.IX.1946 to 14.X.1946"], part="end")

    assert result.values == ("1946-10-14",)


def test_a_month_range_has_month_precision_at_both_ends():
    result = date("VIII-IX.46", ["Davao VIII-IX.46"], part="end")

    assert result.values == ("1946-09",)
    assert result.readings[0].end_precision == "month"
    assert result.readings[0].century_rule == "date-rules-v1:two_digit_year_century=1900"


def test_a_range_without_the_century_rule_is_open_at_both_ends():
    result = date("VIII-IX.46", ["Davao VIII-IX.46"], rules=NO_CENTURY)

    assert result.status == LookupStatus.AMBIGUOUS and result.values == ()


def test_the_step_keeps_a_check_row_for_the_end_only_on_the_end_field():
    texts = ["Davao\n3-5.IX.1946"]
    start_row = field_step._check_row("date_visited_from", ("date_parser",), "3-5.IX.1946", "1946-09-03",
        texts=texts, date_rules=PILOT, asset_id=None, blobs=None)
    end_row = field_step._check_row("date_visited_to", ("date_parser",), "3-5.IX.1946", "1946-09-05",
        texts=texts, date_rules=PILOT, asset_id=None, blobs=None)
    wrong_start = field_step._check_row("date_visited_from", ("date_parser",), "3-5.IX.1946", "1946-09-05",
        texts=texts, date_rules=PILOT, asset_id=None, blobs=None)
    wrong_end = field_step._check_row("date_visited_to", ("date_parser",), "3-5.IX.1946", "1946-09-03",
        texts=texts, date_rules=PILOT, asset_id=None, blobs=None)

    assert start_row is not None and "1946-09-03" in start_row.excerpt
    assert end_row is not None and "1946-09-05" in end_row.excerpt and '"end"' in end_row.excerpt
    assert wrong_start is None and wrong_end is None


def test_the_step_keeps_a_check_row_for_a_split_date_and_names_how_it_was_read():
    row = field_step._check_row("date_visited_from", ("date_parser",), SPLIT, "1948-04-25",
        texts=PILOT_READINGS, date_rules=PILOT, asset_id=None, blobs=None)

    assert row is not None and "IV-25\n1948 reads as 1948-04-25" in row.excerpt
    assert '"via": ["split_lines"]' in row.excerpt


@pytest.mark.parametrize("literal", ["3 sept. '46", "3.IX.46", "VIII-IX.46"])
def test_an_inferred_century_is_recorded_in_the_check_row_the_value_cites(literal):
    row = field_step._check_row("date_visited_from", ("date_parser",), literal,
        "1946-09-03" if literal != "VIII-IX.46" else "1946-08",
        texts=[f"Davao\n{literal}"], date_rules=PILOT, asset_id=None, blobs=None)

    assert row is not None
    assert '"century_rule": "date-rules-v1:two_digit_year_century=1900"' in row.excerpt


def test_a_year_written_whole_records_no_century_rule():
    row = field_step._check_row("date_visited_from", ("date_parser",), "3 sept. 1946", "1946-09-03",
        texts=["Davao\n3 sept. 1946"], date_rules=PILOT, asset_id=None, blobs=None)

    assert row is not None and "century_rule" not in row.excerpt


# -- G44 never copies a range's start to its end ---------------------------------------------------


def run_with(start: FieldValue, end: FieldValue):
    return SimpleNamespace(fields={"date_visited_from": start, "date_visited_to": end}, evidence=[])


@pytest.mark.parametrize(
    ("literal", "copied"),
    [("3 sept. '46", True), ("IV-25\n1948", True), ("3-5.IX.1946", False), ("VIII-IX.46", False),
     ("3.IX-5.X.1946", False), ("10-12 Sept. 1946", False)],
)
def test_a_range_s_start_is_not_copied_to_its_end(literal, copied):
    start = FieldValue(state=ValueState.SUPPORTED, literal=literal, parsed="1946-09-03", layer="settled")
    run = run_with(start, FieldValue(state=ValueState.NOT_PRESENT))

    filled = derive.fill(run, eligible=["date_visited_to"], asset_id=None)

    assert (filled == ["date_visited_to"]) is copied
    assert (run.fields["date_visited_to"].state == ValueState.SUPPORTED) is copied
