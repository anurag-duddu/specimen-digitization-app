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
        ("IV-25\n\n1948", ("IV-25", "1948")),  # not adjacent: split_problem says so
        ("3 Sept.\n1948.", ("3 Sept.", "1948")),
        ("3 Sept.\n1948,", ("3 Sept.", "1948")),
        ("1948.\nIX-3", ("IX-3", "1948")),
        ("25.IV.\n1948.", ("25.IV.", "1948")),
        ("1948-\nIX-3", None),
        ("3 Sept.\n1948.5", None),
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


def test_year_beside_lends_no_year_a_marker_makes_a_measurement_or_a_determination():
    # Review 297 (rounds 2 and 3): "Alt." above "1900" lent 1900 to the date below it.
    for text in ("x\nAlt.\n1900\nIV-25 y", "x\nEl.\n1900\nIV-25 y", "x\nAlt.\n\n1900\nIV-25 y",
                 "x, Alt.\n1900\nIV-25 y", "x\ndet. J. Smith\n1950\nIV-25 y", "x, IV-25\n1900\nm",
                 "x, IV-25\n1900\nm.s.n.m."):
        assert date_lines.year_beside("IV-25", text) is None, text
    # A marker further away, one with a number of its own (coordinator's ruling on PR #306),
    # or a word that is no marker, lends the year.
    assert date_lines.year_beside("IV-25", "Alt. 1500 m\nx, IV-25\n1948") == ("1948", "next_line")
    assert date_lines.year_beside("IV-25", "4800 ft. IV-25\n1948") == ("1948", "next_line")
    assert date_lines.year_beside("IV-25", "x, 1500 m, IV-25\n1948") == ("1948", "next_line")
    assert date_lines.year_beside("IV-25", "Alt. 1500 m\n1948\nIV-25 y") == ("1948", "previous_line")
    assert date_lines.year_beside("IV-25", "El Salvador\n1948\nIV-25 y") == ("1948", "previous_line")
    assert date_lines.year_beside("IV-25", "x, IV-25\n1948\nM. Smith") == ("1948", "next_line")
    # A determination on the date's own line: that date is the determination's, read whole.
    assert date_lines.year_beside("IV-25", "det. J. Smith IV-25\n1950") == ("1950", "next_line")


@pytest.mark.parametrize(
    ("literal", "text", "problem"),
    [
        ("IV-25\n1948", "x, IV-25\n1948", None),
        # A marker on the year's line or the line above it, or a unit starting the line below.
        ("1900\nIV-25", "Alt.\n1900\nIV-25 x", date_lines.YEAR_MEASUREMENT),
        ("IV-25\n1900", "x, IV-25\n1900\nm", date_lines.YEAR_MEASUREMENT),
        ("IV-25\n1948", "x, IV-25\n1948. m", date_lines.YEAR_MEASUREMENT),
        ("IV-25\n1948", "x, IV-25\n1948, m", date_lines.YEAR_MEASUREMENT),
        ("1900\nIV-25", "x, Alt.\n1900\nIV-25 x", date_lines.YEAR_MEASUREMENT),
        # A measurement with its own number is not attached to the year.
        ("IV-25\n1948", "x, IV-25\n1948, 1900m", None),
        ("IV-25\n1948", "4800 ft. IV-25\n1948", None),
        ("1948\nIV-25", "Alt. 1500 m\n1948\nIV-25 x", None),
        ("1950\nIV-25", "det. J. Smith\n1950\nIV-25 x", date_lines.YEAR_DETERMINATION),
        ("IV-25\n1948", "x, IV-25\n1948, det. y", date_lines.YEAR_DETERMINATION),
        # The year is not alone and a marker is there too: the year's own reason is named.
        ("IV-25\n1948", "Alt.\nx, IV-25\n1948 m", date_lines.YEAR_NOT_ALONE),
        # The colon after a year below the date is no sentence mark (review 297c, note 2).
        ("3 Sept.\n1948:", "Guatemala, 3 Sept.\n1948: R.D. Mitchell", date_lines.YEAR_NOT_ALONE),
        ("3 Sept.\n1948;", "Guatemala, 3 Sept.\n1948; R.D. Mitchell", None),
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
        ("IV-25\n\n1948", "x, IV-25\n\n1948", date_lines.NOT_ADJACENT),
        ("1948\n\nIV-25", "1948\n\nIV-25", date_lines.NOT_ADJACENT),
        # The mark the literal itself quotes after the year counts as following it.
        ("3 Sept.\n1948.", "Guatemala, 3 Sept.\n1948.5 m", date_lines.YEAR_NOT_ALONE),
        ("3 Sept.\n1948.", "3.VI.1947, 3 Sept.\n1948.", date_lines.OTHER_DATE),
        ("3 Sept.\n1948,", "Guatemala, 3 Sept.\n1948, 1900 m", date_lines.OTHER_DATE),
        ("3 Sept.\n1948,", "Guatemala, 3 Sept.\n1948, R.D. Mitchell", None),
        ("3 Sept.\n1948.", "Guatemala, 3 Sept.\n1948. R.D. Mitchell", None),
        ("1948.\nIX-3", "det. J. Smith 1948.\nIX-3 Guatemala", date_lines.YEAR_NOT_ALONE),
        ("1948.\nIX-3", "1948.\nIX-3 Guatemala", None),
        ("25.IV.\n1948.", "Guatemala 25.IV.\n1948.5 m", date_lines.YEAR_NOT_ALONE),
    ],
)
def test_split_problem(literal, text, problem):
    assert date_lines.split_problem(literal, text) == problem
