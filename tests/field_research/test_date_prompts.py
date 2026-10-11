"""The date experts' briefs and FIELD_RESEARCH.md name what the date check returns.

The check's notes and the way it found a year are words the expert reads in
`parse_date`'s result; a brief that does not name them leaves the expert to
guess at them, and a note the document does not name is a rule nobody can look
up. These tests tie the words in the code to both.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specimen_digitization.field_research import checks
from specimen_digitization.field_research.prompts import instructions

DOCUMENT = (Path(__file__).resolve().parents[2] / "docs/execution/golive/FIELD_RESEARCH.md").read_text(
    encoding="utf-8")
PILOT = {"version": "date-rules-v1", "two_digit_year_century": 1900, "roman_numeral_months": True}
LABEL = "Guatemala, IV-25\n1948, R.D. Mitchell"


def run(literal, text=LABEL, **more):
    return checks.parse_date(literal, reading_texts=[text], date_rules=PILOT, **more)


def emitted() -> dict[str, checks.DateCheck]:
    """One check for each note and each way of finding a year the code can return."""
    return {
        "day_month_order_ambiguous": run("4-5-48", "4-5-48"),
        "year_missing": run("14.IX", "14.IX"),
        "split_lines": run("IV-25\n1948"),
        "year_on_next_line": run("IV-25", "Guatemala, IV-25\n1948\nR.D. Mitchell"),
        "year_on_previous_line": run("IV-25", "1948\nIV-25 Guatemala"),
        "year_literal": run("IV-25", LABEL, year_literal="1948"),
        "split_lines_hold_another_date": run("IV-25\n1948", "Cali 3.VI, IV-25\n1948"),
        "split_lines_state_two_years": run("IV-25-48\n1948", "IV-25-48\n1948"),
        "range_end_before_start": run("5-3.IX.1946", "5-3.IX.1946"),
        "readers_disagree_on_date": checks.parse_date("IV-25", reading_texts=[
            "Guatemala, IV-25\n1948", "Guatemala, IV-25\n1949"], date_rules=PILOT),
        "split_lines_year_not_alone": run("IV-25\n1948", "Guatemala, IV-25\n1948 m"),
        "split_lines_not_adjacent": run("IV-25\n\n1948", "Guatemala, IV-25\n\n1948"),
        "literal_spans_a_line_break": run("3\nSept.\n1946", "Davao 3\nSept.\n1946"),
        # The follow-ups to review 297c.
        "one_line": run("IV-25 1948", "Guatemala, IV-25 1948"),
        "one_line_year_not_alone": run("IV-25 1948", "Guatemala, IV-25 1948 m"),
        "one_line_holds_another_date": run("IV-25 1948", "Guatemala, 3.VI, IV-25 1948"),
        "one_line_year_may_be_a_measurement": run("25.IV 1900", "Bolivia, 25.IV 1900 m"),
        "split_lines_year_may_be_a_measurement": run("1900\nIV-25", "Alt.\n1900\nIV-25 Guatemala"),
        "split_lines_year_may_be_a_determination": run("1950\nIV-25", "det. J. Smith\n1950\nIV-25 x"),
        "split_lines_date_not_read": run("Davao\n1948", "Mindanao, Davao\n1948"),
        "range_shaped_like_a_code": run("III-V-46", "Davao III-V-46"),
    }


def words(check: checks.DateCheck) -> set[str]:
    return set(check.notes) | {via for reading in check.readings for via in reading.via}


def test_the_check_returns_each_word_the_briefs_and_the_document_name():
    found = emitted()

    for word, check in found.items():
        assert word in words(check), (word, check.as_dict())


@pytest.mark.parametrize("key", ["date_visited_from", "date_visited_to", "date_identified"])
def test_each_date_brief_names_how_the_check_reads_a_split_date_and_an_ambiguous_numeric_one(key):
    brief = instructions(key)

    for word in ("day_month_order_ambiguous", "split_lines", "year_on_next_line", "year_on_previous_line",
                 "readers_disagree_on_date", "one_line", "year_literal never settles a value"):
        assert word in brief, (key, word)
    if key == "date_visited_from":
        assert "split_lines_not_adjacent" in brief and "literal_spans_a_line_break" in brief
        for word in ("split_lines_year_may_be_a_measurement", "split_lines_year_may_be_a_determination",
                     "split_lines_date_not_read", "one_line_year_not_alone", "one_line_year_may_be_a_measurement",
                     "one_line_holds_another_date", "range_shaped_like_a_code"):
            assert word in brief, word
        # The brief no longer promises that a year passed as year_literal resolves the date.
        assert "pass that year as year_literal." not in brief


def test_the_range_briefs_say_which_end_each_field_takes():
    start, end = instructions("date_visited_from"), instructions("date_visited_to")

    assert "Resolve with the start" in start
    assert "the value you may resolve to is the end" in end
    assert "never the range's start" in end


LOWERCASE_READ = ["3.iv.1948", "3.ix.46", "3-ix-46", "1946.ix.14", "3.iv"]
LOWERCASE_NOT_READ = ["iv-23-48", "iv.1948", "1946.ix", "12 vi 1946", "12 x 46"]


def test_the_document_says_exactly_which_lowercase_numerals_are_read():
    from specimen_digitization.application.field_validators import date_parser

    for literal in LOWERCASE_READ:
        assert f"`{literal}`" in DOCUMENT, literal
        assert date_parser(literal, source_text=literal, date_rules=PILOT).parsed is not None, literal
    for literal in LOWERCASE_NOT_READ:
        assert f"`{literal}`" in DOCUMENT, literal
        assert date_parser(literal, source_text=literal, date_rules=PILOT).parsed is None, literal
    # The sentence that said "the day or the four-digit year beside it" was wrong:
    # a two-digit year is read after a lowercase numeral too.
    assert "to the day or the four-digit year beside it" not in DOCUMENT


def test_the_document_names_every_word_the_check_returns():
    for word in emitted():
        assert word in DOCUMENT, word
    for word in ("date-parser-v2", "year_literal_decides", "written_range", "DATE_PART", "century_rule"):
        assert word in DOCUMENT, word
