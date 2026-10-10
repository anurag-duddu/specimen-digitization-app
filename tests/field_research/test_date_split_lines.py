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


def test_a_day_and_month_alone_take_a_year_that_is_alone_on_the_next_line():
    result = date("IV-25", ["Guatemala, IV-25\n1948\nR.D. Mitchell"])

    assert result.status == LookupStatus.SUCCESS
    assert result.values == ("1948-04-25",)
    assert result.readings[0].via == ("year_on_next_line",)
    assert "1925-04" not in result.values


@pytest.mark.parametrize("year_line", ["1948", "1948.", "1948,", "  1948 ", "1948,  "])
def test_the_borrowed_year_may_carry_a_period_or_a_comma_and_nothing_else(year_line):
    result = date("IV-25", [f"Guatemala, IV-25\n{year_line}\nR.D. Mitchell"])

    assert result.status == LookupStatus.SUCCESS and result.values == ("1948-04-25",)


def test_the_pilots_day_and_month_alone_do_not_take_a_year_that_shares_its_line():
    # "1948, R.D. Mitchell": the line holds a name too, so a bare IV-25 stays open.
    # The organiser's two-line literal "IV-25\n1948" is what reads (the first test).
    result = date("IV-25", PILOT_READINGS)

    assert result.status == LookupStatus.AMBIGUOUS and "year_missing" in result.notes
    assert result.values == ("1925-04",) and all(r.via == () for r in result.readings)


def test_the_check_shows_the_rule_that_matched_to_the_expert():
    shown = date(SPLIT, PILOT_READINGS).as_dict()

    assert shown["status"] == "success" and shown["literal"] == SPLIT
    assert shown["readings"] == [
        {"iso": "1948-04-25", "precision": "day", "order": "month-day", "via": ("split_lines",)}]


@pytest.mark.parametrize(
    ("text", "literal", "iso", "via"),
    [
        # The year ends the line above, the date starts the next.
        ("Guatemala\n1948\nIV-25 Yepocapa", "IV-25", "1948-04-25", "year_on_previous_line"),
        ("Guatemala\n1948\nIV-25 Yepocapa", "1948\nIV-25", "1948-04-25", "split_lines"),
        # The day and month by name, in another language.
        ("Cali\n14 sept.\n1946", "14 sept.", "1946-09-14", "year_on_next_line"),
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
        # The line holds more than the year (review 297): an elevation, a unit, a
        # determination, a range, a second number or a name.
        ("Guatemala, IV-25\n1900 m, R.D. Mitchell", "an elevation in metres"),
        ("Guatemala, IV-25\n1948', R.D. Mitchell", "feet written with a tick"),
        ("Guatemala, IV-25\n1948 m", "a metre mark"),
        ("Guatemala, IV-25\n1948 ft.", "a foot mark"),
        ("Guatemala, IV-25\n1948 msnm", "metres above sea level"),
        ("Guatemala, IV-25\n1948-49", "a year range"),
        ("Guatemala, IV-25\n1948-2", "a number after a dash"),
        ("Guatemala, IV-25\n1948 5", "a second number"),
        ("Guatemala, IV-25\n1950 det. J. Smith", "a determination below"),
        ("Guatemala, IV-25\n1948, R.D. Mitchell", "a name on the year's line"),
        ("det. J. Smith 1950\nIV-25 Guatemala", "a determination above"),
        ("El. 1948\nIV-25 Guatemala", "an elevation label above"),
        ("alt. 1948\nIV-25 Guatemala", "an altitude label above"),
        ("R.D. Mitchell 1948\nIV-25 Guatemala", "a name on the year's line above"),
        ("1948 m\nIV-25 Guatemala", "a unit above"),
        ("1948'\nIV-25 Guatemala", "a tick above"),
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


@pytest.mark.parametrize(
    ("text", "literal"),
    [
        # The year the organiser quoted is a measurement or a mark (review 297).
        ("Guatemala, IV-25\n1900 m, R.D. Mitchell", "IV-25\n1900"),
        ("Guatemala, IV-25\n1948', R.D. Mitchell", "IV-25\n1948"),
        ("Guatemala, IV-25\n1948 m, R.D. Mitchell", "IV-25\n1948"),
        ("Guatemala, IV-25\n1948 ft.", "IV-25\n1948"),
        ("Guatemala, IV-25\n1948 msnm", "IV-25\n1948"),
        ("Guatemala, IV-25\n1948.5", "IV-25\n1948"),
        ("Guatemala, IV-25\n1948-49", "IV-25\n1948"),
        ("Guatemala, IV-25\n1948-2", "IV-25\n1948"),
        ("Guatemala, IV-25\n1948 5", "IV-25\n1948"),
        ("Guatemala, IV-25\n1950 det. J. Smith", "IV-25\n1950"),
        # The year ends the line above the date and does not stand alone there.
        ("det. J. Smith 1950\nIV-25 Guatemala", "1950\nIV-25"),
        ("El. 1948\nIV-25 Guatemala", "1948\nIV-25"),
        ("alt. 1948\nIV-25 Guatemala", "1948\nIV-25"),
    ],
)
def test_a_two_line_literal_whose_year_is_marked_or_not_alone_is_no_date(text, literal):
    result = date(literal, [text])

    assert result.status == LookupStatus.NO_MATCH, result.as_dict()
    assert result.notes == ("split_lines_year_not_alone",)
    assert result.values == ()


@pytest.mark.parametrize(
    ("text", "literal"),
    [
        ("Guatemala, IV-25\n1948, R.D. Mitchell", "IV-25\n1948"),
        ("Guatemala, IV-25\n1948; R.D. Mitchell", "IV-25\n1948"),
        ("Guatemala, IV-25\n1948. R.D. Mitchell", "IV-25\n1948"),
        ("Guatemala, IV-25\n1948", "IV-25\n1948"),
        ("Guatemala\n1948\nIV-25 Yepocapa", "1948\nIV-25"),
        ("  1948  \nIV-25 Yepocapa", "1948  \nIV-25"),
    ],
)
def test_a_two_line_literal_whose_year_stands_alone_or_ends_at_a_comma_reads(text, literal):
    result = date(literal, [text])

    assert result.status == LookupStatus.SUCCESS, result.as_dict()
    assert result.values == ("1948-04-25",)


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


READER_1948 = "Guatemala, IV-25\n1948\nR.D. Mitchell"
READER_1949 = "Guatemala, IV-25\n1949\nR.D. Mitchell"


@pytest.mark.parametrize("order", [(READER_1948, READER_1949), (READER_1949, READER_1948)])
def test_readers_that_give_different_years_leave_the_date_ambiguous_in_either_order(order):
    # Review 297: the first reader's year used to settle the date, so [A, B] gave
    # 1948 and [B, A] gave 1949, with nothing said.
    first, second = order
    result = date("IV-25", [first, second], reading_names=["1A", "1B"])

    assert result.status == LookupStatus.AMBIGUOUS
    assert result.notes[0] == "readers_disagree_on_date"
    assert set(result.values) == {"1948-04-25", "1949-04-25"}
    years = {"1A": first[first.index("\n") + 1 :][:4], "1B": second[second.index("\n") + 1 :][:4]}
    assert result.notes[1] == f"1A: {years['1A']}-04-25; 1B: {years['1B']}-04-25"


def test_the_readers_are_named_by_number_when_no_names_are_given():
    result = date("IV-25", [READER_1948, READER_1949])

    assert result.notes == ("readers_disagree_on_date", "1: 1948-04-25; 2: 1949-04-25")


@pytest.mark.parametrize("value", ["1948-04-25", "1949-04-25"])
@pytest.mark.parametrize("order", [(READER_1948, READER_1949), (READER_1949, READER_1948)])
def test_the_step_keeps_no_check_row_for_a_date_the_readers_disagree_on(value, order):
    row = field_step._check_row("date_visited_from", ("date_parser",), "IV-25", value,
        texts=list(order), date_rules=PILOT, asset_id=None, blobs=None)

    assert row is None


def test_readers_that_agree_on_the_date_settle_it_whichever_is_first():
    other = "Guatemala, IV-25\n1948.\nlot 2"

    for texts in ([READER_1948, other], [other, READER_1948]):
        result = date("IV-25", texts)
        assert result.status == LookupStatus.SUCCESS and result.values == ("1948-04-25",)


def test_a_reader_that_drops_the_year_line_disagrees_with_one_that_keeps_it():
    texts = [READER_1948, "Guatemala, IV-25\nR.D. Mitchell"]

    result = date("IV-25", texts, reading_names=["2A", "2B"])

    assert result.status == LookupStatus.AMBIGUOUS
    assert result.notes[0] == "readers_disagree_on_date"
    assert result.notes[1] == "2A: 1948-04-25; 2B: no year/1925-04"


def test_a_reader_whose_year_is_marked_disagrees_with_one_whose_year_stands_alone():
    texts = ["Guatemala, IV-25\n1948, R.D. Mitchell", "Guatemala, IV-25\n1948 m, R.D. Mitchell"]

    result = date(SPLIT, texts, reading_names=["1A", "1B"])

    assert result.status == LookupStatus.AMBIGUOUS
    assert result.notes == ("readers_disagree_on_date",
        "1A: 1948-04-25; 1B: not a date (split_lines_year_not_alone)")


def test_a_reader_that_shows_the_literal_inside_a_code_still_decides_it_is_no_date():
    texts = [READER_1948, "Guatemala, IV-25-4\n1948"]

    result = date("IV-25", texts)

    assert result.status == LookupStatus.NO_MATCH and "part_of_hyphenated_token" in result.notes


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
