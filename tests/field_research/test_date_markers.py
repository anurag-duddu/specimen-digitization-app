"""Measurement markers, determinations and literals inside longer tokens (the reviews of
PR #306 at d305db77e and f89292766, and the coordinator's rulings on them).

A unit belongs to the year only when it is attached to it. A unit followed by a number
of its own ("m 1200", "M 1200": the unit written before its number, as Italian labels
do) is a measurement of its own. Only a Title-case Mt., Mts., Ft., Mte. or Pto., or the
initial M., before a capitalised name is a place or a person ("Mt. Apo", "M. Smith"); a
unit in lower case or capitals stays a unit whatever follows it. A unit starting the
next line counts in every spelling and case. A date a determination stands before on
its line is the determination's: Date Identified settles only from such a date, and the
collecting date never does. A literal counts only where it stands as a token of its own.
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
U_UMLAUT = "\N{LATIN SMALL LETTER U WITH DIAERESIS}"
ONE_LINE_MEASURE = ("one_line_year_may_be_a_measurement",)
SPLIT_MEASURE = ("split_lines_year_may_be_a_measurement",)
COLLECTING = ("date_visited_from", "date_visited_to")


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


# -- 1. Mount and Fort, in Title case before a name, are no unit ---------------------------------

NAMES = [
    ("Davao, 3.IX.1946 Mt. Apo", "3.IX.1946", "1946-09-03"),
    ("Davao, 3.IX.1946, Mt. Apo", "3.IX.1946", "1946-09-03"),
    ("Davao, 3.IX.1946 Mt Apo", "3.IX.1946", "1946-09-03"),
    ("Aug. 3, 1948 Mt. Rainier Nat. Pk.", "Aug. 3, 1948", "1948-08-03"),
    ("VII-3-1948 Ft. Collins, Colo.", "VII-3-1948", "1948-07-03"),
    ("25 IV 1948, Ft. Sherman, Canal Zone", "25 IV 1948", "1948-04-25"),
    ("Uganda, 25.IV.1948 Mts. Rwenzori", "25.IV.1948", "1948-04-25"),
    ("Alaska, 3 Sept. '46 Mt. McKinley", "3 Sept. '46", "1946-09-03"),
    ("Davao IV-25\n1948, Mt. Apo", "IV-25\n1948", "1948-04-25"),
    ("C.Z. IV-25\n1948, Ft. Clayton", "IV-25\n1948", "1948-04-25"),
    ("Uganda IV-25\n1948, Mts. Rwenzori", "IV-25\n1948", "1948-04-25"),
    ("Davao, IV-25, 1948, Mt. Apo", "IV-25, 1948", "1948-04-25"),
]


@pytest.mark.parametrize(("text", "literal", "iso"), NAMES, ids=[r[0] for r in NAMES])
def test_mount_and_fort_in_title_case_before_a_name_are_no_unit_and_the_date_reads(
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
        ("Guatemala IV-25\n1948\nMt. Apo", "IV-25\n1948"),
    ],
)
def test_a_name_beside_the_year_on_other_lines_still_reads(text, literal):
    assert date(literal, [text]).status == LookupStatus.SUCCESS


# A unit in lower case or in capitals right after the year stays a unit, whatever follows
# it (review of f89292766, finding 1): a collector or a place written after the elevation
# is the usual layout. So does a Title-case unit word that is no listed abbreviation.
STAYS_A_UNIT = [
    ("25.IV 1900 m R.D. Mitchell", "25.IV 1900", ONE_LINE_MEASURE),
    ("25.IV 1900 m. R.D. Mitchell", "25.IV 1900", ONE_LINE_MEASURE),
    ("IV-25-1900 ft. Coll. Smith", "IV-25-1900", ONE_LINE_MEASURE),
    ("3 Sept. 1900 msnm Guatemala", "3 Sept. 1900", ONE_LINE_MEASURE),
    ("25 IV 1900 metros San Pedro", "25 IV 1900", ONE_LINE_MEASURE),
    ("25 IV 1900 m.s.n.m. Coll. Smith", "25 IV 1900", ONE_LINE_MEASURE),
    ("GUATEMALA 25 IV 1900 FT. COLL. SMITH", "25 IV 1900", ONE_LINE_MEASURE),
    ("25 IV 1900 M LEG. SMITH", "25 IV 1900", ONE_LINE_MEASURE),
    ("Davao, 25 IV 1900 MT. APO", "25 IV 1900", ONE_LINE_MEASURE),
    ("Luzon, 25.IV.1900 Metro Manila", "25.IV.1900", ONE_LINE_MEASURE),
    ("25 IV 1900\nm R.D. Mitchell", "25 IV 1900", ONE_LINE_MEASURE),
    ("C.Z. 25.IV.1900\nft. Clayton", "25.IV.1900", ONE_LINE_MEASURE),
    ("Davao 25.IV.1900\nmt. Apo", "25.IV.1900", ONE_LINE_MEASURE),
    ("Davao 25.IV.1900\nm. Smith leg.", "25.IV.1900", ONE_LINE_MEASURE),
    ("IV-25\n1900, m R.D. Mitchell", "IV-25\n1900", SPLIT_MEASURE),
    ("IV-25\n1900\nm Yepocapa", "IV-25\n1900", SPLIT_MEASURE),
    ("IV-25\n1900\nMT. APO", "IV-25\n1900", SPLIT_MEASURE),
]


@pytest.mark.parametrize(
    ("text", "literal", "notes"), STAYS_A_UNIT, ids=[r[0] for r in STAYS_A_UNIT]
)
def test_a_unit_in_lower_case_or_capitals_stays_a_unit_whatever_follows_it(
    text, literal, notes
):
    result = date(literal, [text])

    assert result.status == LookupStatus.NO_MATCH and result.notes == notes, (
        result.as_dict()
    )
    assert row(literal, "1900-04-25", [text]) is None


def test_a_bare_month_and_day_take_no_year_a_lower_case_unit_follows_on_the_next_line():
    result = date("IV-25", ["Guatemala IV-25\n1900\nm R.D. Mitchell"])

    assert result.status == LookupStatus.AMBIGUOUS and "year_missing" in result.notes, (
        result.as_dict()
    )
    assert (
        row("IV-25", "1900-04-25", ["Guatemala IV-25\n1900\nm R.D. Mitchell"]) is None
    )


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
    # In capitals too (review of f89292766, non-blocking note 1).
    ("Monte Baldo 25.VI.1948\nM 1200, leg. Rossi", "25.VI.1948", "1948-06-25"),
    ("MONTE BALDO 25.VI.1948\nM 1200 S.L.M.", "25.VI.1948", "1948-06-25"),
    ("Monte Baldo 25.VI.1948\nM. 1200", "25.VI.1948", "1948-06-25"),
    ("Monte Baldo VI-25\n1948\nM 1200", "VI-25\n1948", "1948-06-25"),
    ("Monte Baldo, 25.VI.1948, M. 1200", "25.VI.1948", "1948-06-25"),
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


@pytest.mark.parametrize("unit", ["m 1200", "M 1200"])
def test_a_day_and_month_alone_borrow_a_year_whose_next_line_writes_a_unit_before_its_number(
    unit,
):
    result = date("VI-25", [f"Monte Baldo VI-25\n1948\n{unit}"])

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
    assert date(literal, [text]).notes == ONE_LINE_MEASURE


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
]


@pytest.mark.parametrize("unit", NEXT_LINE_UNITS)
def test_a_unit_starting_the_next_line_makes_the_year_a_measurement_in_every_spelling(
    unit,
):
    split = date("IV-25\n1900", [f"Guatemala IV-25\n1900\n{unit}"])
    alone = date("IV-25", [f"Guatemala IV-25\n1900\n{unit}"])
    one_line = date("25 IV 1900", [f"Guatemala 25 IV 1900\n{unit}"])

    assert split.notes == SPLIT_MEASURE, split.as_dict()
    assert alone.status == LookupStatus.AMBIGUOUS and "year_missing" in alone.notes, (
        alone.as_dict()
    )
    assert one_line.notes == ONE_LINE_MEASURE, one_line.as_dict()
    for literal in ("IV-25\n1900", "IV-25"):
        assert row(literal, "1900-04-25", [f"Guatemala IV-25\n1900\n{unit}"]) is None


@pytest.mark.parametrize(
    "text",
    ["Bolivia, 25 IV 1900 M.", "Bolivia, 25 IV 1900 (m)", "Bolivia, 25 IV 1900 M"],
)
def test_a_capital_or_bracketed_unit_after_the_year_makes_it_a_measurement(text):
    result = date("25 IV 1900", [text])

    assert result.notes == ONE_LINE_MEASURE, result.as_dict()
    assert row("25 IV 1900", "1900-04-25", [text]) is None


@pytest.mark.parametrize(
    ("text", "literal", "iso"),
    [
        # A collector's initial below the year, or after it: a name, not metres.
        ("Guatemala IV-25\n1948\nM. Smith", "IV-25\n1948", "1948-04-25"),
        ("Guatemala IV-25\n1948\nM. Smith", "IV-25", "1948-04-25"),
        ("Guatemala 25 IV 1948\nM. Smith", "25 IV 1948", "1948-04-25"),
        ("Guatemala 25 IV 1948, M. Smith", "25 IV 1948", "1948-04-25"),
    ],
)
def test_a_collector_s_initial_below_or_after_the_year_is_no_unit(text, literal, iso):
    result = date(literal, [text])

    assert result.status == LookupStatus.SUCCESS and result.values == (iso,), (
        result.as_dict()
    )


# -- 4. A determination: before the date it is the determination's date ---------------------------

# A determination after the date, joined to the collector or not, leaves the collecting date
# (review of f89292766, finding 2, and the coordinator's ruling).
DETERMINATION_AFTER = [
    ("25.IV.1948 leg. et det. J. Smith", "25.IV.1948", "1948-04-25"),
    ("25.IV.1948 leg. & det. J. Smith", "25.IV.1948", "1948-04-25"),
    ("25.IV.1948 leg./det. J. Smith", "25.IV.1948", "1948-04-25"),
    (f"25.IV.1948 leg. u. det. H. M{U_UMLAUT}ller", "25.IV.1948", "1948-04-25"),
    (f"3-IX-1946, col. y det. J. P{E_ACUTE}rez", "3-IX-1946", "1946-09-03"),
    ("Monte Baldo, 25.VI.1948, leg. Rossi det. Bianchi", "25.VI.1948", "1948-06-25"),
    ("25.IV.1948 J. Smith leg. et det.", "25.IV.1948", "1948-04-25"),
    ("Bolivia, 25 IV 1948 det. Smith", "25 IV 1948", "1948-04-25"),
    ("Guatemala, IV-25 1948 leg. et det. R.D. Mitchell", "IV-25 1948", "1948-04-25"),
    ("Guatemala, IV-25 1948 det. Smith", "IV-25 1948", "1948-04-25"),
    ("Guatemala, IV-25 1948, det. Smith", "IV-25 1948", "1948-04-25"),
    ("Guatemala, IV-25 1948 identified by R.D. Mitchell", "IV-25 1948", "1948-04-25"),
    ("Guatemala, IV-25\n1948, det. R.D. Mitchell", "IV-25\n1948", "1948-04-25"),
]


@pytest.mark.parametrize(
    ("text", "literal", "iso"),
    DETERMINATION_AFTER,
    ids=[r[0] for r in DETERMINATION_AFTER],
)
def test_a_determination_after_the_date_leaves_it_the_collecting_date(
    text, literal, iso
):
    for field in (None, *COLLECTING):
        result = date(literal, [text], field=field)
        assert result.status == LookupStatus.SUCCESS and result.values == (iso,), (
            field,
            result.as_dict(),
        )
    assert row(literal, iso, [text], key="date_visited_from") is not None


@pytest.mark.parametrize(
    ("text", "literal", "iso"),
    DETERMINATION_AFTER,
    ids=[r[0] for r in DETERMINATION_AFTER],
)
def test_date_identified_takes_no_date_a_determination_follows(text, literal, iso):
    result = date(literal, [text], field="date_identified")

    assert result.status == LookupStatus.NO_MATCH, result.as_dict()
    assert result.notes == ("date_follows_no_determination",)
    assert row(literal, iso, [text], key="date_identified") is None


# A determination before the date on its line: the determination's date.
DETERMINATION_BEFORE = [
    ("det. J. Smith 1950", "1950", "1950"),
    ("det. 25.IV.1950", "25.IV.1950", "1950-04-25"),
    ("det. J. Smith, IV-25 1950", "IV-25 1950", "1950-04-25"),
    ("det. J. Smith IV-25\n1950", "IV-25\n1950", "1950-04-25"),
    ("Det. E. L. Mockford 1952", "1952", "1952"),
]


@pytest.mark.parametrize(
    ("text", "literal", "iso"),
    DETERMINATION_BEFORE,
    ids=[r[0] for r in DETERMINATION_BEFORE],
)
def test_a_date_a_determination_stands_before_is_date_identified_s_only(
    text, literal, iso
):
    identified = date(literal, [text], field="date_identified")

    assert identified.status == LookupStatus.SUCCESS and identified.values == (iso,), (
        identified.as_dict()
    )
    assert row(literal, iso, [text], key="date_identified") is not None
    for field in (None, *COLLECTING):
        result = date(literal, [text], field=field)
        assert result.status == LookupStatus.NO_MATCH, (field, result.as_dict())
        assert result.notes == ("date_follows_a_determination",)
    for key in COLLECTING:
        assert row(literal, iso, [text], key=key) is None


def test_a_determination_on_another_line_makes_no_date_the_determination_s():
    # Date Identified settles only from a date that follows a determination on its line.
    text = "det. J. Smith\n25.IV.1950"

    assert date("25.IV.1950", [text], field="date_identified").notes == (
        "date_follows_no_determination",
    )
    assert date("25.IV.1950", [text], field="date_visited_from").values == (
        "1950-04-25",
    )


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
