"""Measurement markers, determinations after a year, and literals inside longer tokens
(the review of PR #306 at d305db77e, comment 6107514345).

A unit belongs to the year only when it is attached to it: not when a capitalised name
follows it ("Mt. Apo", "Ft. Collins": a place), not when a number of its own follows it
("m 1200": the unit written before its number, as Italian labels do). A unit starting
the next line counts in every spelling and case. For a collecting date, a determination
after the year on its line makes the year the determination's. A literal counts only
where it stands as a token of its own.
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
E_ACUTE = "\N{LATIN SMALL LETTER E WITH ACUTE}"


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


# -- 1. Mount and Fort are names, not units ------------------------------------------------------

NAMES = [
    ("Davao, 3.IX.1946 Mt. Apo", "3.IX.1946", "1946-09-03"),
    ("Davao, 3.IX.1946, Mt. Apo", "3.IX.1946", "1946-09-03"),
    ("Aug. 3, 1948 Mt. Rainier Nat. Pk.", "Aug. 3, 1948", "1948-08-03"),
    ("VII-3-1948 Ft. Collins, Colo.", "VII-3-1948", "1948-07-03"),
    ("25 IV 1948, Ft. Sherman, Canal Zone", "25 IV 1948", "1948-04-25"),
    ("Uganda, 25.IV.1948 Mts. Rwenzori", "25.IV.1948", "1948-04-25"),
    ("Luzon, 25.IV.1948 Metro Manila", "25.IV.1948", "1948-04-25"),
    ("Alaska, 3 Sept. '46 Mt. McKinley", "3 Sept. '46", "1946-09-03"),
    ("Davao IV-25\n1948, Mt. Apo", "IV-25\n1948", "1948-04-25"),
    ("C.Z. IV-25\n1948, Ft. Clayton", "IV-25\n1948", "1948-04-25"),
    ("Uganda IV-25\n1948, Mts. Rwenzori", "IV-25\n1948", "1948-04-25"),
    ("Davao, IV-25, 1948, Mt. Apo", "IV-25, 1948", "1948-04-25"),
    ("C.Z. 25.IV.1948\nft. Clayton", "25.IV.1948", "1948-04-25"),
]


@pytest.mark.parametrize(("text", "literal", "iso"), NAMES, ids=[r[0] for r in NAMES])
def test_mount_and_fort_before_a_name_are_no_unit_and_the_date_reads(
    text, literal, iso
):
    result = date(literal, [text])

    assert result.status == LookupStatus.SUCCESS and result.values == (iso,), (
        result.as_dict()
    )
    assert row(literal, iso, [text]) is not None


@pytest.mark.parametrize(
    ("text", "literal"),
    [
        # The pilot's 105526321 writes "E. slope Mt. McKinley": no marker above a year either.
        ("E. slope Mt. McKinley\n1946\nIX-3 Alaska", "1946\nIX-3"),
        ("Davao 25.IV.1948\nmt. Apo", "25.IV.1948"),
        ("Guatemala IV-25\n1948\nMt. Apo", "IV-25\n1948"),
    ],
)
def test_a_name_beside_the_year_on_other_lines_still_reads(text, literal):
    assert date(literal, [text]).status == LookupStatus.SUCCESS


@pytest.mark.parametrize(
    ("text", "literal", "note"),
    [
        # The same abbreviations with nothing after them are units.
        ("Bolivia, 25 IV 1900 Ft.", "25 IV 1900", "one_line_year_may_be_a_measurement"),
        (
            "Bolivia, 25.IV 1900 mts.",
            "25.IV 1900",
            "one_line_year_may_be_a_measurement",
        ),
        (
            "Guatemala IV-25\n1900, ft.",
            "IV-25\n1900",
            "split_lines_year_may_be_a_measurement",
        ),
    ],
)
def test_a_unit_with_no_name_after_it_still_makes_the_year_a_measurement(
    text, literal, note
):
    result = date(literal, [text])

    assert result.status == LookupStatus.NO_MATCH and result.notes == (note,), (
        result.as_dict()
    )


# -- 2. A unit written before its own number is a measurement of its own -------------------------

ITALIAN = [
    ("Monte Baldo, 25.VI.1948 m 1200", "25.VI.1948", "1948-06-25"),
    ("Monte Baldo, 25.VI.1948, m 1200 s.l.m.", "25.VI.1948", "1948-06-25"),
    ("Monte Baldo, 25.VI.1948 m. 1200", "25.VI.1948", "1948-06-25"),
    ("Monte Baldo 25.VI.1948\nm 1200, leg. Rossi", "25.VI.1948", "1948-06-25"),
    ("Abruzzo, 25 giugno 1948, m 1800", "25 giugno 1948", "1948-06-25"),
    ("Gran Sasso, 25.VI.1948, mt 1800", "25.VI.1948", "1948-06-25"),
    ("Sierra Nevada, 3-IX-1946, m 1200", "3-IX-1946", "1946-09-03"),
    ("Monte Baldo VI-25\n1948, m 1200", "VI-25\n1948", "1948-06-25"),
    ("Monte Baldo VI-25\n1948\nm 1200", "VI-25\n1948", "1948-06-25"),
    ("Monte Baldo, VI-25, 1948, m 1200", "VI-25, 1948", "1948-06-25"),
]


@pytest.mark.parametrize(
    ("text", "literal", "iso"), ITALIAN, ids=[r[0] for r in ITALIAN]
)
def test_a_unit_before_its_own_number_leaves_the_year_a_year(text, literal, iso):
    result = date(literal, [text])

    assert result.status == LookupStatus.SUCCESS and result.values == (iso,), (
        result.as_dict()
    )
    assert row(literal, iso, [text]) is not None


def test_a_day_and_month_alone_borrow_a_year_whose_next_line_writes_a_unit_before_its_number():
    result = date("VI-25", ["Monte Baldo VI-25\n1948\nm 1200"])

    assert result.values == ("1948-06-25",) and result.readings[0].via == (
        "year_on_next_line",
    )


@pytest.mark.parametrize(
    ("text", "literal"),
    [
        ("Monte Baldo, 25.VI.1900 m", "25.VI.1900"),
        ("Monte Baldo, 25.VI.1900 m s.l.m.", "25.VI.1900"),
    ],
)
def test_a_unit_after_the_year_with_no_number_of_its_own_still_refuses(text, literal):
    assert date(literal, [text]).notes == ("one_line_year_may_be_a_measurement",)


# -- 3. A unit starting the next line counts in every spelling ------------------------------------

NEXT_LINE_UNITS = [
    "metros",
    "meters",
    "metres",
    "Metros",
    "feet",
    "pies",
    f"p{E_ACUTE}s",
    "MSNM",
    "M.S.N.M.",
    "FT.",
    "MTS.",
    "M",
    "M.",
    "M 1200",
]


@pytest.mark.parametrize("unit", NEXT_LINE_UNITS)
def test_a_unit_starting_the_next_line_makes_the_year_a_measurement_in_every_spelling(
    unit,
):
    split = date("IV-25\n1900", [f"Guatemala IV-25\n1900\n{unit}"])
    alone = date("IV-25", [f"Guatemala IV-25\n1900\n{unit}"])
    one_line = date("25 IV 1900", [f"Guatemala 25 IV 1900\n{unit}"])

    assert split.notes == ("split_lines_year_may_be_a_measurement",), split.as_dict()
    assert alone.status == LookupStatus.AMBIGUOUS and "year_missing" in alone.notes, (
        alone.as_dict()
    )
    assert one_line.notes == ("one_line_year_may_be_a_measurement",), one_line.as_dict()
    for literal in ("IV-25\n1900", "IV-25"):
        assert row(literal, "1900-04-25", [f"Guatemala IV-25\n1900\n{unit}"]) is None


@pytest.mark.parametrize(
    "text",
    ["Bolivia, 25 IV 1900 M.", "Bolivia, 25 IV 1900 (m)", "Bolivia, 25 IV 1900 M"],
)
def test_a_capital_or_bracketed_unit_after_the_year_makes_it_a_measurement(text):
    result = date("25 IV 1900", [text])

    assert result.notes == ("one_line_year_may_be_a_measurement",), result.as_dict()
    assert row("25 IV 1900", "1900-04-25", [text]) is None


@pytest.mark.parametrize(
    ("text", "literal", "iso"),
    [
        # A collector's initial below the year, or after it: a name, not metres.
        ("Guatemala IV-25\n1948\nM. Smith", "IV-25\n1948", "1948-04-25"),
        ("Guatemala IV-25\n1948\nM. Smith", "IV-25", "1948-04-25"),
        ("Guatemala 25 IV 1948\nM. Smith", "25 IV 1948", "1948-04-25"),
        ("Guatemala 25 IV 1948, M. Smith", "25 IV 1948", "1948-04-25"),
        ("Davao 25.IV.1948\nm. Smith leg.", "25.IV.1948", "1948-04-25"),
    ],
)
def test_a_collector_s_initial_below_or_after_the_year_is_no_unit(text, literal, iso):
    result = date(literal, [text])

    assert result.status == LookupStatus.SUCCESS and result.values == (iso,), (
        result.as_dict()
    )


# -- 4. A determination after the year: no collecting date ---------------------------------------

DETERMINED = [
    ("Guatemala, IV-25 1948 leg. et det. R.D. Mitchell", "IV-25 1948"),
    ("Guatemala, IV-25 1948 coll. Jones det. Smith", "IV-25 1948"),
    ("Guatemala, IV-25 1948, det. Smith", "IV-25 1948"),
    ("Bolivia, 25 IV 1948 det. Smith", "25 IV 1948"),
    ("Bolivia, 25.IV.1948 det. Smith", "25.IV.1948"),
    ("Bolivia, 25 IV 1948, ident. Smith", "25 IV 1948"),
    ("Bolivia, 25 IV 1948 identified by Smith", "25 IV 1948"),
]


@pytest.mark.parametrize(
    ("text", "literal"), DETERMINED, ids=[r[0] for r in DETERMINED]
)
def test_a_determination_after_the_year_makes_it_no_collecting_date(text, literal):
    for field in (None, "date_visited_from", "date_visited_to"):
        result = date(literal, [text], field=field)
        assert result.status == LookupStatus.NO_MATCH, (field, result.as_dict())
        assert result.notes == ("one_line_year_may_be_a_determination",)
    for key in ("date_visited_from", "date_visited_to"):
        assert row(literal, "1948-04-25", [text], key=key) is None


@pytest.mark.parametrize(
    ("text", "literal"), DETERMINED, ids=[r[0] for r in DETERMINED]
)
def test_date_identified_still_reads_a_date_a_determination_follows(text, literal):
    result = date(literal, [text], field="date_identified")

    assert result.status == LookupStatus.SUCCESS and result.values == ("1948-04-25",), (
        result.as_dict()
    )
    assert row(literal, "1948-04-25", [text], key="date_identified") is not None


def test_a_determination_right_after_the_year_is_named_for_the_collecting_date():
    text = "Guatemala, IV-25 1948 det. Smith"

    assert date("IV-25 1948", [text]).notes == ("one_line_year_may_be_a_determination",)
    # For Date Identified the word right after the year is still no collector.
    assert date("IV-25 1948", [text], field="date_identified").notes == (
        "one_line_year_not_alone",
    )


def test_a_determination_before_the_date_leaves_it_the_determination_s_date():
    for field in (None, "date_identified"):
        result = date("IV-25 1950", ["det. J. Smith, IV-25 1950"], field=field)
        assert result.values == ("1950-04-25",)


# -- 5. A literal inside a longer token ----------------------------------------------------------

INSIDE = [
    ("VIII-25 1948", "III-25 1948"),
    ("Lot XIV-25-1948", "IV-25-1948"),
    ("Lot XIV.25.1948", "IV.25.1948"),
    ("125.IV.1948", "25.IV.1948"),
    ("25.IV.19489", "25.IV.1948"),
    ("125.IV, 1948", "25.IV, 1948"),
    ("XIV-25\n1948", "IV-25\n1948"),
    ("XIV-25\n1948", "IV-25"),
    ("Bolivia, 25 IV 1900m", "25 IV 1900"),
]


@pytest.mark.parametrize(
    ("text", "literal"), INSIDE, ids=[f"{r[1]} in {r[0]}" for r in INSIDE]
)
def test_a_literal_inside_a_longer_token_is_no_date(text, literal):
    result = date(literal, [text])

    assert result.status == LookupStatus.NO_MATCH and result.notes == (
        "literal_inside_a_longer_token",
    )
    assert result.values == ()
    for value in ("1948-03-25", "1948-04-25", "1900-04-25"):
        assert row(literal, value, [text]) is None


@pytest.mark.parametrize(
    ("text", "literal", "iso"),
    [
        ("Lot IV-25-1948", "IV-25-1948", "1948-04-25"),
        ("Guatemala,IV-25 1948", "IV-25 1948", "1948-04-25"),
        ("Davao (25.IV.1948)", "25.IV.1948", "1948-04-25"),
    ],
)
def test_a_literal_beside_punctuation_stands_as_a_token(text, literal, iso):
    assert date(literal, [text]).values == (iso,)


def test_a_reading_that_holds_the_literal_only_inside_a_token_is_not_asked():
    # The second reader writes another token ("XIV-25 1948"); the first reads the date.
    result = date("IV-25 1948", ["Guatemala IV-25 1948", "Guatemala XIV-25 1948"])

    assert result.status == LookupStatus.SUCCESS and result.values == ("1948-04-25",)
