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


def test_year_beside_needs_the_date_to_end_or_start_its_line():
    assert date_lines.year_beside("IV-25", "x, IV-25\n1948, y") == ("1948", "next_line")
    assert date_lines.year_beside("IV-25", "x 1948\nIV-25 y") == ("1948", "previous_line")
    assert date_lines.year_beside("IV-25", "IV-25 x\n1948") is None
    assert date_lines.year_beside("IV-25", "1948\nx IV-25") is None
    assert date_lines.year_beside("IV-25", "x IV-25\n1948 5.IX") is None
    assert date_lines.year_beside("IV-25", "IV-25") is None
