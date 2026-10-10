"""The helpers behind a date split over two lines (field_research/date_lines)."""

from __future__ import annotations

import pytest

from specimen_digitization.field_research import date_lines


@pytest.mark.parametrize(
    ("literal", "split"),
    [
        ("IV-25\n1948", ("IV-25", "1948")),
        ("1948\nIV-25", ("IV-25", "1948")),
        (" IV-25 \n '48 ", ("IV-25", "'48")),
        ("IV-25\r\n1948", ("IV-25", "1948")),
        ("3 Sept.\n1946", ("3 Sept.", "1946")),
        ("IV-25\n48", None),
        ("IV-25", None),
        ("IV-25\n\n1948", None),
        ("1948\n1949", None),
        ("IV-25\nV-3", None),
        ("a\nb\n1948", None),
    ],
)
def test_split_literal(literal, split):
    assert date_lines.split_literal(literal) == split


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Guatemala,", False), (", R.D. Mitchell", False), ("4800 ft.", False), ("6400'", False),
        ("lot #2 cut branch", False), ("R.D.", False), ("", False),
        ("1948", True), ("'48", True), ("3.IX", True), ("IV-25", True), ("4-5", True),
        ("Sept.", True), ("sept", True), ("Mai", True), ("enero", True), ("Okt.", True),
        ("Mar del Plata", True),
    ],
)
def test_could_be_a_date(text, expected):
    assert date_lines.could_be_a_date(text) is expected


def test_year_beside_needs_the_date_to_end_or_start_its_line_and_the_year_alone():
    assert date_lines.year_beside("IV-25", "x, IV-25\n1948\ny") == ("1948", "next_line")
    assert date_lines.year_beside("IV-25", "x, IV-25\n1948,\ny") == ("1948", "next_line")
    assert date_lines.year_beside("IV-25", "x\n1948.\nIV-25 y") == ("1948", "previous_line")
    assert date_lines.year_beside("IV-25", "IV-25 x\n1948") is None
    assert date_lines.year_beside("IV-25", "1948\nx IV-25") is None
    assert date_lines.year_beside("IV-25", "x IV-25\n1948 5.IX") is None
    assert date_lines.year_beside("IV-25", "IV-25") is None
    # Anything else on the year's line, either side (review 297), lends no year.
    for line in ("1948, R.D. Mitchell", "1948 m", "1948'", "1948 ft.", "1948-49", "1948-2", "1948 5",
                 "El. 1948", "alt. 1948", "det. J. Smith 1950", "R.D. Mitchell 1948", "'48", "48", "4800"):
        assert date_lines.year_beside("IV-25", f"x, IV-25\n{line}") is None, line
        assert date_lines.year_beside("IV-25", f"{line}\nIV-25 x") is None, line


@pytest.mark.parametrize(
    ("literal", "text", "problem"),
    [
        ("IV-25\n1948", "x, IV-25\n1948", None),
        ("IV-25\n1948", "x, IV-25\n1948, R.D. Mitchell", None),
        ("IV-25\n1948", "x, IV-25\n1948; y", None),
        ("IV-25\n1948", "x, IV-25\n1948. y", None),
        ("IV-25\n1948", "x, IV-25\n1948 m", date_lines.YEAR_NOT_ALONE),
        ("IV-25\n1948", "x, IV-25\n1948' y", date_lines.YEAR_NOT_ALONE),
        ("IV-25\n1948", "x, IV-25\n1948-49", date_lines.YEAR_NOT_ALONE),
        ("IV-25\n1948", "x, IV-25\n1948.5", date_lines.YEAR_NOT_ALONE),
        ("IV-25\n1948", "x, IV-25\n1948 det. y", date_lines.YEAR_NOT_ALONE),
        ("IV-25\n1948", "3.VI IV-25\n1948", date_lines.OTHER_DATE),
        ("IV-25\n1948", "IV-25\n1948, 3.VI", date_lines.OTHER_DATE),
        ("IV-25\n1948", "IV-25\n1948 3.VI", date_lines.OTHER_DATE),
        ("1948\nIV-25", "1948\nIV-25 x", None),
        ("1948\nIV-25", "det. x 1948\nIV-25 x", date_lines.YEAR_NOT_ALONE),
        ("1948\nIV-25", "1948\nIV-25 3.VI", date_lines.OTHER_DATE),
    ],
)
def test_split_problem(literal, text, problem):
    assert date_lines.split_problem(literal, text) == problem
