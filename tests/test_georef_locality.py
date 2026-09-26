"""Reading locality text for the retrospective georeferencing tool (GEO.md 1)."""

import itertools
import random
import re
import sys
import time
import unicodedata

import pytest

from specimen_digitization.application.georef_locality import (
    comparison_key,
    fold,
    is_full_name,
    letters_apart,
    one_letter_apart,
    read_locality,
    variants,
)

MCKINLEY = ("Mt. McKinley", None, "mountain", 90.0, "slope", "mount mckinley")
DAVAO = ("Davao", "province", None, None, None, "davao")
MINDANAO = ("Mindanao", None, None, None, None, "mindanao")
PI = ("P.I.", None, None, None, None, "philippine islands")
ISLANDS = ("Philippine Islands", None, None, None, None, "philippine islands")
GUATEMALA = ("Guatemala", None, None, None, None, "guatemala")


def summary(text):
    """Each part as (name, unit, feature, bearing, relation, key)."""
    return [
        (
            part.name,
            part.unit,
            part.feature,
            part.heading.degrees if part.heading else None,
            part.relation,
            part.key,
        )
        for part in read_locality(text).parts
    ]


# The ten pilot labels' locality lines as S8 read them (line breaks kept).
S8_READING = {
    "105526321": (
        "E. slope Mt. McKinley\nDavao Prov.\nMindanao, P.I.",
        [MCKINLEY, DAVAO, MINDANAO, PI],
    ),
    "105526322": (
        "CNHM. E Slope Mt.\nMcKinley, Davao Prov.\nMindanao, P.I.",
        [MCKINLEY, DAVAO, MINDANAO, PI],
    ),
    "105526323": (
        "CNHM. E. Slope Mt.\nMcKinley, Davao\nProv., Mindanao, P.I.",
        [MCKINLEY, DAVAO, MINDANAO, PI],
    ),
    "105526324": (
        "E. slope Mt. McKinley\n3300', Davao Prov.\nMindanao,\nPhilippine Islands",
        [MCKINLEY, DAVAO, MINDANAO, ISLANDS],
    ),
    "105526325": (
        "E. Slope Mt.\nMcKinley, Davao\nProv., Mindanao,\nPhilippine Islands",
        [MCKINLEY, DAVAO, MINDANAO, ISLANDS],
    ),
    "105526326": (
        "E. slope Mt. McKinley\nDavao, Prov. 3300'\nMindanao, P.I.",
        [MCKINLEY, DAVAO, MINDANAO, PI],
    ),
    "105526327": (
        "E. slope Mt. Apo,\nDavao Prov.,\nMindanao, P.I.",
        [("Mt. Apo", None, "mountain", 90.0, "slope", "mount apo"), DAVAO, MINDANAO, PI],
    ),
    "105526328": (
        "Yepocapa, Mun.\nYepocapa,\nchimaltenago,\nGuatemala.",
        [
            ("Yepocapa", None, None, None, None, "yepocapa"),
            ("Yepocapa", "municipality", None, None, None, "yepocapa"),
            ("chimaltenago", None, None, None, None, "chimaltenago"),
            GUATEMALA,
        ],
    ),
    "105526329": (
        "Yepocapa, 4800 ft.\nChimaltenago,\nGuatemala",
        [
            ("Yepocapa", None, None, None, None, "yepocapa"),
            ("Chimaltenago", None, None, None, None, "chimaltenago"),
            GUATEMALA,
        ],
    ),
    "105526330": (
        "Yepocapa, 4800 ft.\nChimaltenago\nGuatemala",
        [
            ("Yepocapa", None, None, None, None, "yepocapa"),
            ("Chimaltenago", None, None, None, None, "chimaltenago"),
            GUATEMALA,
        ],
    ),
}


@pytest.mark.parametrize("subject", sorted(S8_READING))
def test_pilot_labels_read_into_their_parts(subject):
    text, expected = S8_READING[subject]
    assert summary(text) == expected
    assert read_locality(text).verbatim == text


def test_pilot_elevations_and_institutions_are_set_apart():
    mckinley = read_locality(S8_READING["105526326"][0])
    assert [(e.text, e.low, e.high, e.unit) for e in mckinley.elevations] == [
        ("3300'", "3300", None, "ft")
    ]
    yepocapa = read_locality(S8_READING["105526329"][0])
    assert [(e.text, e.low, e.unit) for e in yepocapa.elevations] == [("4800 ft.", "4800", "ft")]
    assert read_locality(S8_READING["105526323"][0]).institutions == ("CNHM.",)
    assert read_locality(S8_READING["105526321"][0]).elevations == ()


def test_pilot_parts_keep_their_readings():
    parts = read_locality(S8_READING["105526321"][0]).parts
    assert [part.readings for part in parts] == [
        ("Mount McKinley",),
        ("Davao Province", "Davao"),
        ("Mindanao",),
        ("Philippine Islands",),
    ]
    assert parts[0].heading.text == "E."
    assert [part.full_name for part in parts] == [True, True, True, False]
    joined = read_locality(S8_READING["105526326"][0]).parts[1]
    assert (joined.text, joined.readings) == ("Davao Prov.", ("Davao Province", "Davao"))
    municipality = read_locality(S8_READING["105526328"][0]).parts[1]
    assert (municipality.text, municipality.readings) == (
        "Mun. Yepocapa",
        ("Yepocapa Municipality", "Yepocapa"),
    )


# The same lines as the S7 baseline readers wrote them, slips included.
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "CNHM. ESlope Mt.\nMcKinley, Davao Prov.\nMindanao, P.I.",
            [MCKINLEY, DAVAO, MINDANAO, PI],
        ),
        ("E. slope Mt. McKinley\nDavao Prov.\nMindanao, P.I.", [MCKINLEY, DAVAO, MINDANAO, PI]),
        (
            "Yepocapa, 4800ft.\nChimaltenango,\nGuatemala",
            [
                ("Yepocapa", None, None, None, None, "yepocapa"),
                ("Chimaltenango", None, None, None, None, "chimaltenango"),
                GUATEMALA,
            ],
        ),
    ],
)
def test_reader_slips_read_like_the_label(text, expected):
    assert summary(text) == expected


def test_reader_lines_set_dates_and_bare_elevations_aside():
    joined = read_locality("CNHM. ESlope Mt.\nMcKinley, Davao Prov.")
    assert joined.parts[0].heading.text == "E"
    dated = read_locality("Mindanao, P.I.\n6-Sept-1946, Elev.6400")
    assert dated.unplaced == ("6-Sept-1946",)
    assert [(e.text, e.low, e.unit) for e in dated.elevations] == [("Elev.6400", "6400", None)]
    assert summary("Yepocapa,4800 ft.\nChimaltenago\nGuatemala,IV-26\n1948")[-1] == GUATEMALA
    assert read_locality("Yepocapa,4800 ft.\nChimaltenago\nGuatemala,IV-26\n1948").unplaced == (
        "IV-26",
        "1948",
    )


@pytest.mark.parametrize(
    ("text", "name", "unit", "readings"),
    [
        ("Cook Co.", "Cook", "county", ("Cook County", "Cook")),
        (
            "Depto. Chimaltenango",
            "Chimaltenango",
            "department",
            ("Chimaltenango Department", "Chimaltenango"),
        ),
        (
            "Departamento de Chimaltenango",
            "Chimaltenango",
            "department",
            ("Chimaltenango Department", "Chimaltenango"),
        ),
        ("Provincia de Davao", "Davao", "province", ("Davao Province", "Davao")),
        ("Estado de Chiapas", "Chiapas", "state", ("Chiapas State", "Chiapas")),
        ("Davao Region", "Davao", "region", ("Davao Region", "Davao")),
        ("Phil. Is.", "Phil. Is.", None, ("Phil. Is.",)),
    ],
)
def test_notations_give_units_and_readings(text, name, unit, readings):
    (part,) = read_locality(text).parts
    assert (part.name, part.unit, part.readings) == (name, unit, readings)


def test_unknown_abbreviations_and_institutions():
    (part,) = read_locality("Phil. Is.").parts
    assert part.full_name is False
    reading = read_locality("FMNH, Mt. Apo")
    assert reading.institutions == ("FMNH",)
    assert [part.name for part in reading.parts] == ["Mt. Apo"]


@pytest.mark.parametrize(
    ("text", "heading", "bearing", "relation"),
    [
        ("NNE slope of Mt. Apo", "NNE", 22.5, "slope"),
        ("N.E. side Mt. Apo", "N.E.", 45.0, "side"),
        ("eastern slope Mt. Apo", "eastern", 90.0, "slope"),
        ("south-west flank Mt. Apo", "south-west", 225.0, "flank"),
        ("Mt. Apo east slope", "east", 90.0, "slope"),
        ("Mt. Apo, east slope", "east", 90.0, "slope"),
        ("E. slope,\nMt. Apo", "E.", 90.0, "slope"),
    ],
)
def test_headings_join_their_feature(text, heading, bearing, relation):
    (part,) = read_locality(text).parts
    assert (part.name, part.heading.text, part.heading.degrees, part.relation) == (
        "Mt. Apo",
        heading,
        bearing,
        relation,
    )


def test_a_heading_phrase_prefers_an_adjacent_feature():
    parts = read_locality("Mindanao, E. slope, Mt. Apo").parts
    assert [(p.name, p.relation) for p in parts] == [("Mindanao", None), ("Mt. Apo", "slope")]
    assert read_locality("E. slope").parts == ()
    assert read_locality("E. slope").unplaced == ("E. slope",)


def test_place_names_are_not_headings():
    for name in ("Seaside", "Riverside", "Eastside"):
        (part,) = read_locality(name).parts
        assert (part.name, part.heading, part.relation) == (name, None, None)


@pytest.mark.parametrize(
    ("text", "distance", "unit", "heading", "bearing", "name"),
    [
        ("5 km NE of Yepocapa", "5", "km", "NE", 45.0, "Yepocapa"),
        ("12 mi. N Chicago", "12", "mi", "N", 0.0, "Chicago"),
        ("1.5 km S of Davao", "1.5", "km", "S", 180.0, "Davao"),
        ("50 m N of Yepocapa", "50", "m", "N", 0.0, "Yepocapa"),
        ("0,5 km N of Yepocapa", "0,5", "km", "N", 0.0, "Yepocapa"),
        ("0,25 km S of Davao", "0,25", "km", "S", 180.0, "Davao"),
    ],
)
def test_offsets_keep_distance_and_heading(text, distance, unit, heading, bearing, name):
    reading = read_locality(text)
    (part,) = reading.parts
    assert (part.relation, part.distance, part.distance_unit) == ("offset", distance, unit)
    assert (part.heading.text, part.heading.degrees, part.name) == (heading, bearing, name)
    assert reading.elevations == ()


def test_an_offsets_place_follows_the_rules_for_any_part():
    reading = read_locality("5 km NE of Yepocapa 1500 m")
    (part,) = reading.parts
    assert (part.name, part.relation, part.distance) == ("Yepocapa", "offset", "5")
    assert [(e.text, e.low, e.unit) for e in reading.elevations] == [("1500 m", "1500", "m")]
    reading = read_locality("5 km N of Davao 3300'")
    assert [(part.name, part.relation) for part in reading.parts] == [("Davao", "offset")]
    assert [e.text for e in reading.elevations] == ["3300'"]
    for text in ("10 m S of Camp 3", "5 km N of 1946", "5 km N Davao 3 Sept 1946"):
        reading = read_locality(text)
        assert (reading.parts, reading.unplaced) == ((), (text,))
    slope = read_locality("1500 m N slope Mt. Apo")
    (part,) = slope.parts
    assert (part.name, part.relation, part.heading.degrees) == ("Mt. Apo", "slope", 0.0)
    assert [e.text for e in slope.elevations] == ["1500 m"]
    dash = read_locality("E. slope -")
    assert (dash.parts, dash.unplaced) == ((), ("E. slope -",))


@pytest.mark.parametrize(
    ("text", "written", "low", "high", "unit"),
    [
        ("Yepocapa, 1,463 m", "1,463 m", "1,463", None, "m"),
        ("Yepocapa, 4000-4500 ft", "4000-4500 ft", "4000", "4500", "ft"),
        ("Yepocapa, Elev. 6400'", "Elev. 6400'", "6400", None, "ft"),
        ("Yepocapa, alt. 1500 m", "alt. 1500 m", "1500", None, "m"),
        ("Mt. McKinley 6400'", "6400'", "6400", None, "ft"),
        ("Yepocapa, 4800ft.", "4800ft.", "4800", None, "ft"),
        # Numbers are read whole, dots and commas included (G36): never cut short.
        ("Yepocapa, 1.463 m", "1.463 m", "1.463", None, "m"),
        ("Yepocapa, 6.400 ft.", "6.400 ft.", "6.400", None, "ft"),
        ("Yepocapa, 1463,5 m", "1463,5 m", "1463,5", None, "m"),
        ("Yepocapa, 1.200-1.500 m", "1.200-1.500 m", "1.200", "1.500", "m"),
    ],
)
def test_elevations_are_kept_as_written(text, written, low, high, unit):
    reading = read_locality(text)
    assert [(e.text, e.low, e.high, e.unit) for e in reading.elevations] == [
        (written, low, high, unit)
    ]
    assert len(reading.parts) == 1 and not any(ch.isdigit() for ch in reading.parts[0].name)


def test_unplaced_text_is_never_a_part():
    reading = read_locality("Camp 3, Mt. Apo")
    assert reading.unplaced == ("Camp 3",)
    assert [part.name for part in reading.parts] == ["Mt. Apo"]
    assert read_locality("").parts == ()
    # A part is kept aside whole: "P.I." goes with the date beside it.
    dated = read_locality("Mindanao, P.I. 3 Sept. '46")
    assert [part.name for part in dated.parts] == ["Mindanao"]
    assert dated.unplaced == ("P.I. 3 Sept. '46",)


@pytest.mark.parametrize(
    ("text", "names", "elevations", "unplaced"),
    [
        ("Mindanao, P.I.\n6-Sept-1946,6400'", ["Mindanao", "P.I."], ["6400'"], ["6-Sept-1946"]),
        ("15-IV-1948,1500 m", [], ["1500 m"], ["15-IV-1948"]),
        ("Guatemala,IV-26,4800 ft.", ["Guatemala"], ["4800 ft."], ["IV-26"]),
        ("Camp 3,4800 ft.", [], ["4800 ft."], ["Camp 3"]),
    ],
)
def test_a_bare_comma_between_a_date_and_an_elevation_separates_them(
    text, names, elevations, unplaced
):
    # A comma between digits belongs to the number only in a thousands group led by
    # one to three digits ("1,463") or as a one- or two-digit decimal ("0,5", "1463,5").
    reading = read_locality(text)
    assert [part.name for part in reading.parts] == names
    assert [e.text for e in reading.elevations] == elevations
    assert list(reading.unplaced) == unplaced


def test_space_grouped_digits_are_set_aside():
    for text in ("4 800 ft.", "Elev. 4 800 ft."):
        reading = read_locality(text)
        assert (reading.parts, reading.elevations, reading.unplaced) == ((), (), (text,))
    reading = read_locality("Yepocapa, 1 463 m")
    assert [part.name for part in reading.parts] == ["Yepocapa"]
    assert (reading.elevations, reading.unplaced) == ((), ("1 463 m",))
    # A year and a four-digit elevation are two numbers, not one grouped number.
    reading = read_locality("6-Sept-1946 1500 m")
    assert [e.text for e in reading.elevations] == ["1500 m"]
    assert reading.unplaced == ("6-Sept-1946",)


def test_a_line_starting_with_a_linking_word_joins_the_line_before():
    (part,) = read_locality("E. slope\nof Mt. Apo").parts
    assert (part.name, part.relation) == ("Mt. Apo", "slope")
    (part,) = read_locality("5 km NE\nof Yepocapa").parts
    assert (part.name, part.relation, part.distance) == ("Yepocapa", "offset", "5")
    (part,) = read_locality("Mt.\n\n\nApo").parts
    assert part.name == "Mt. Apo"


def test_a_letterless_or_dangling_name_is_set_aside():
    for text in ("Depto. de ?", "E. slope Prov. -", "Depto. de", "of"):
        reading = read_locality(text)
        assert (reading.parts, reading.unplaced) == ((), (text,))
    reading = read_locality("Davao, de")
    assert ([part.name for part in reading.parts], reading.unplaced) == (["Davao"], ("de",))


def test_any_unicode_number_keeps_a_part_aside():
    reading = read_locality("\u00bd mi. N of Davao")
    assert (reading.parts, reading.unplaced) == ((), ("\u00bd mi. N of Davao",))


@pytest.mark.parametrize(
    ("text", "elevations", "unplaced"),
    [
        # A four-digit year can't lead a thousands group: the comma separates.
        ("6-Sept-1946,640'", ["640'"], ["6-Sept-1946"]),
        ("15-IV-1948,850 m", ["850 m"], ["15-IV-1948"]),
        # A number glued to a date is set aside.
        ("12-IV-1948,95 m", [], ["12-IV-1948,95 m"]),
        ("12-IV-1948.95 m", [], ["12-IV-1948.95 m"]),
        # Thousands groups and decimals stay whole.
        ("1,463,200 m", ["1,463,200 m"], []),
        ("1946,63 m", ["1946,63 m"], []),
        # A malformed grouping is set aside.
        ("1,5,3 m", [], ["1,5,3 m"]),
        ("12,34,567 m", [], ["12,34,567 m"]),
        # An apostrophe year is no digit group beside the elevation.
        ("3 Sept. '46 850 m", ["850 m"], ["3 Sept. '46"]),
    ],
)
def test_a_comma_or_space_between_digits_keeps_numbers_whole_or_sets_them_aside(
    text, elevations, unplaced
):
    reading = read_locality(text)
    assert [e.text for e in reading.elevations] == elevations
    assert list(reading.unplaced) == unplaced
    assert reading.parts == ()


def test_an_offset_with_a_malformed_or_three_decimal_distance():
    (part,) = read_locality("0,125 km S of Davao").parts
    assert (part.name, part.distance) == ("Davao", "0,125")
    reading = read_locality("1,5,3 km N of Davao")
    assert (reading.parts, reading.unplaced) == ((), ("1,5,3 km N of Davao",))


def test_a_capitalised_linking_word_at_a_line_start_begins_a_name():
    assert [(p.name, p.unit) for p in read_locality("Surigao Prov.\nDel Carmen").parts] == [
        ("Surigao", "province"),
        ("Del Carmen", None),
    ]
    assert [(p.name, p.unit) for p in read_locality("Bukidnon Prov.\nDel Monte").parts] == [
        ("Bukidnon", "province"),
        ("Del Monte", None),
    ]
    assert [p.name for p in read_locality("Mindanao\nDe la Paz").parts] == ["Mindanao", "De la Paz"]


@pytest.mark.parametrize(
    ("text", "count"),
    [("4 800 ft. " * 20000, 0), ("1 m " * 20000, 20000)],
    ids=["grouped", "single"],
)
def test_space_grouped_numbers_are_checked_in_linear_time(text, count):
    started = time.monotonic()
    reading = read_locality(text)
    assert time.monotonic() - started < 5
    assert len(reading.elevations) == count


def test_names_that_key_to_nothing_or_hold_a_numeral_form_are_set_aside():
    for text in ("Prov. Dept.", "5 km N of Mun. ?", "Camp \u2163", "Davao \u33e0"):
        reading = read_locality(text)
        assert (reading.parts, reading.unplaced) == ((), (text,))
    reading = read_locality("Davao, \ufe70")
    assert ([part.name for part in reading.parts], reading.unplaced) == (["Davao"], ("\ufe70",))
    reading = read_locality("Davao, \u3164")
    assert ([part.name for part in reading.parts], reading.unplaced) == (["Davao"], ("\u3164",))


# Every date form the module reads, by separator and month form, with two-digit
# and apostrophe years. "IV-26" reads like a two-digit year, though on 105526330
# it is 26 April, with 1948 on the next line.
DATE_FORMS = (
    # Day, month and year.
    "12-IV-1948",
    "12-4-1948",
    "12-Sept-1948",
    "12\u2013IV\u20131948",
    "12.IV.1948",
    "12.4.1948",
    "12.Sept.1948",
    "12 IV 1948",
    "12 4 1948",
    "12 Sept. 1948",
    "12/IV/1948",
    "12/4/1948",
    "12/Sept/1948",
    # Month and year.
    "IV-1948",
    "4-1948",
    "Sept-1948",
    "IV.1948",
    "4.1948",
    "Sept.1948",
    "IV 1948",
    "Sept. 1948",
    "IV/1948",
    "4/1948",
    "Sept/1948",
    # Two-digit and apostrophe years.
    "IV-26",
    "IV.26",
    "IV/26",
    "IV 26",
    "12-IV-48",
    "12.IV.48",
    "12/4/48",
    "12 IV 48",
    "12 4 48",
    "Sept. 46",
    "3 Sept. 46",
    "3 Sept. '46",
    "Sept. '46",
    "Sept.'46",
)


@pytest.mark.parametrize(
    ("date", "mark", "tail", "unit"),
    list(itertools.product(DATE_FORMS, ",.", ("9", "95", "950", "9500"), (" m", " ft", "'"))),
)
def test_a_year_never_joins_an_elevation(date, mark, tail, unit):
    # The comma rule splits a comma before four digits, or before three after a
    # four-digit year: the tail then reads whole and the date is set aside. Every
    # other row sets the whole text aside. No elevation holds the year's digits,
    # and no date or month is a part.
    text = f"{date}{mark}{tail}{unit}"
    split = mark == "," and (len(tail) == 4 or (len(tail) == 3 and date[-4:].isdigit()))
    expected = ([f"{tail}{unit}".strip()], (date,)) if split else ([], (text,))
    reading = read_locality(text)
    assert ([e.text for e in reading.elevations], reading.unplaced) == expected
    assert reading.parts == ()


# Every way a range joins its numbers: a dash of any kind or a slash, with or
# without spaces, "to", and "a", "and" and "y" between spaces.
DASHES = "-\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d"
RANGE_JOINS = (
    *DASHES,
    "/",
    *(f" {join} " for join in (*DASHES, "/")),
    "to",
    " to ",
    " a ",
    " and ",
    " y ",
)


@pytest.mark.parametrize(
    ("join", "low", "high", "unit"),
    [
        (join, low, high, unit)
        for join in RANGE_JOINS
        for low, high in (("4000", "4500"), ("1,200", "1,500"), ("1.200", "1.500"))
        for unit in (" m", " ft.", "'")
    ],
)
def test_a_range_is_read_whole(join, low, high, unit):
    text = f"{low}{join}{high}{unit}"
    reading = read_locality(text)
    assert [(e.text, e.low, e.high) for e in reading.elevations] == [(text, low, high)]
    assert (reading.parts, reading.unplaced) == ((), ())


@pytest.mark.parametrize(
    "text",
    [
        "4'800 m",
        "4\u2019800 m",
        "6-Sept-1946-640'",
        "4000-4500-5000 m",
        "4000a4500 ft",
        "4000 hasta 4500 ft",
        "4000 bis 4500 m",
        "4000 ~ 4500 m",
        "4000 -- 4500 ft",
        "4000 & 4500 ft",
        "4000 \u301c 4500 m",
        "1500 up to 2000 m",
        "4000 ha\u0301sta 4500 ft",
        "4000 bis-zu 4500 m",
        "4000 has\u00adta 4500 m",
        "4000 ha\u200bsta 4500 m",
        "4000 - 4500 - 5000 m",
        "4000~ 4500 ft",
        "4000\u301c 4500 m",
        "4000-- 4500 m",
        "4000hasta 4500 ft",
        "4000\u2026 4500 m",
        "4000 " + "~ " * 20 + "4500 m",
        "Elev. 1500 ~ 2000 m",
        "Elev. 1500 hasta 2000 m",
    ],
)
def test_a_range_never_reads_its_top_alone(text):
    reading = read_locality(text)
    assert (reading.elevations, reading.parts, reading.unplaced) == ((), (), (text,))


# Years that start their own part, after a comma or at a line start.
PART_START_DATES = ("Sept. 6, 1946", "July 4, 1946", "IV-26\n1948", "26 IV\n1948")


# Every axis the round-6 review named, generated and crossed. Each year form is read
# with its year as written, or moved after ", ", "," or a line break, which puts a
# part of only a month before it in the month-and-year forms; then comes a glued
# comma or dot, a space, a line break, or each range join unspaced, spaced,
# touching either number or beside a line break; then each tail and unit.
MONTH_YEARS = tuple(
    f"{month} 1946"
    for month in (
        *("July", "Julio", "agosto", "Agto.", "SEPT.", "sept"),
        *("viii", "VIII/IX", "de julio"),
    )
)
YEAR_FORMS = (*DATE_FORMS, *MONTH_YEARS, *PART_START_DATES)
RANGE_WORDS = (*DASHES, "/", "to", "a", "and", "y")
TAILS = ("9", "95", "950", "9500")
UNITS = (" m", " ft", "'")
# What may come between a year and the number after it, and whether it joins a range.
TAIL_MARKS = (
    *((mark, False) for mark in (",", ".", " ", "\n")),
    *(
        (form, True)
        for join in RANGE_WORDS
        for form in (join, f" {join} ", f"{join} ", f" {join}", f"{join}\n", f"\n{join}")
    ),
)
# Zero in each digit script the tables use: ASCII, full-width, Devanagari and
# Arabic-Indic.
ZEROS = ("0", "\uff10", "\u0966", "\u0660")


def in_digits(text, zero):
    """The text with its ASCII digits written in the script whose zero is `zero`."""
    return "".join(chr(ord(zero) + int(c)) if "0" <= c <= "9" else c for c in text)


def year_positions(date):
    """The date as written, then its year moved after ", ", "," or a line break."""
    head, year = re.fullmatch(r"(.*?)[\s,\-./\u2013]*('?\d+)", date).groups()
    return (date, *(f"{head}{mark}{year}" for mark in (", ", ",", "\n")))


def assert_no_year_reaches_an_elevation(text, tail, joins):
    reading = read_locality(text)
    # No elevation holds the date's number: only the tail may read, and after a
    # range join not even the tail, which would be the range's top alone.
    assert all((e.low, e.high) == (tail, None) for e in reading.elevations), text
    assert not (joins and reading.elevations), text
    # No month or date fragment becomes a part.
    assert reading.parts == (), text


@pytest.mark.parametrize("date", YEAR_FORMS)
def test_no_year_reaches_an_elevation_on_any_axis(date):
    for dated, (mark, joins), tail, unit in itertools.product(
        year_positions(date), TAIL_MARKS, TAILS, UNITS
    ):
        assert_no_year_reaches_an_elevation(f"{dated}{mark}{tail}{unit}", tail, joins)


@pytest.mark.parametrize(("date", "zero"), list(itertools.product(YEAR_FORMS, ZEROS[1:])))
def test_no_year_reaches_an_elevation_in_other_digits(date, zero):
    for dated, (mark, joins), tail in itertools.product(
        year_positions(date), TAIL_MARKS, ("95", "9500")
    ):
        text = in_digits(f"{dated}{mark}{tail} m", zero)
        assert_no_year_reaches_an_elevation(text, in_digits(tail, zero), joins)


def summary_of(text):
    reading = read_locality(text)
    return [e.text for e in reading.elevations], [p.name for p in reading.parts], reading.unplaced


# Every line break `str.splitlines` knows besides "\n", U+2028 and U+0085 among them.
LINE_BREAKS = ("\r", "\r\n", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029")


@pytest.mark.parametrize("line_break", LINE_BREAKS)
def test_every_line_break_reads_as_a_newline(line_break):
    # In a year's place and between a year and the number after it.
    for date in YEAR_FORMS:
        broken = year_positions(date)[-1]
        for mark in (",", ".", " ", "\n", "-", " - ", "-\n", "\n-", " to\n", "\ny "):
            for text in (f"{broken}{mark}950 m", f"{date}{mark}950 m"):
                if "\n" in text:
                    assert summary_of(text.replace("\n", line_break)) == summary_of(text), text


# Joins no rule lists, which may still join a range's numbers.
OTHER_JOINS = (
    *("~", "\u301c", "--", "hasta", "bis", "&", "up to", "\u2026", "bis-zu"),
    *("ha\u0301sta", "has\u00adta", "ha\u200bsta"),
)


def range_spacings(join):
    """A join unspaced, spaced, touching either number, and broken across lines."""
    yield from (join, f" {join} ", f"{join} ", f" {join}")
    for line_break in ("\n", "\u2028", "\x85"):
        yield from (
            f" {join}{line_break}",
            f"{line_break}{join} ",
            f"{join}{line_break}",
            f"{line_break}{join}",
            f"{line_break}{join}{line_break}",
        )


@pytest.mark.parametrize(
    ("join", "prefix"),
    list(itertools.product((*RANGE_WORDS, *OTHER_JOINS), ("", "Elev. ", "Alt. ", "el. "))),
)
def test_a_range_reads_whole_or_not_at_all(join, prefix):
    # However two numbers are joined, spaced or broken across lines, and in any
    # digits, the range reads whole or not at all, never one of its numbers alone.
    # A word alone on its own line between them stays a part, as any line of words
    # does.
    for (low, high), spacing, zero, unit in itertools.product(
        (("4000", "4500"), ("1,200", "1,500"), ("1.200", "1.500")),
        range_spacings(join),
        ZEROS,
        (" m", " ft.", "'"),
    ):
        text = in_digits(f"{prefix}{low}{spacing}{high}{unit}", zero)
        reading = read_locality(text)
        whole = (in_digits(low, zero), in_digits(high, zero))
        assert [(e.low, e.high) for e in reading.elevations] in ([], [whole]), text
        alone = spacing[0] == spacing[-1] in ("\n", "\u2028", "\x85")
        worded = join in OTHER_JOINS and any(c.isalpha() for c in join)
        assert [p.name for p in reading.parts] == ([join] if alone and worded else []), text


@pytest.mark.parametrize(
    ("text", "places"),
    [
        ("Mindanao, Sept. 1946 - 850 m", ["Mindanao"]),
        ("Davao Prov., IV 1948 \u2014 1500 m", ["Davao"]),
        ("IV 26 y 850 m", []),
        ("Sept. 1946 and 850 m", []),
        ("Camp 3 and 1500 m", []),
        ("Km 42 a 1500 m", []),
        ("July 4, 1946.9500 ft", []),
        ("Guatemala,IV-26\n1948.950 m", ["Guatemala"]),
        ("Mindanao, 1946 - 850 m", ["Mindanao"]),
        # The cost: a range after a place in the same part takes the part with it.
        ("Mt. Apo 1500-2000 m", []),
        ("between 1500 and 2000 m", []),
    ],
)
def test_a_range_after_other_text_or_a_number_is_set_aside(text, places):
    reading = read_locality(text)
    assert (reading.elevations, [part.name for part in reading.parts]) == ((), places)


def test_a_range_reads_at_its_parts_start_or_after_its_prefix():
    for text, elevation in (
        ("Mt. Apo, 1500-2000 m", "1500-2000 m"),
        ("Mt. Apo Elev. 1500-2000 m", "Elev. 1500-2000 m"),
        ("1500 y 2000 m", "1500 y 2000 m"),
    ):
        assert [e.text for e in read_locality(text).elevations] == [elevation]


# The coordinator's reading of G36 and G40 at 15:32Z on 2026-09-25: a range whose
# lower number could be a year is set aside unless its prefix comes first.
@pytest.mark.parametrize(
    ("text", "places"),
    [
        ("Mindanao, 1946 - 2500 m", ["Mindanao"]),
        ("Guatemala, 26 - 850 m", ["Guatemala"]),
        ("1800-2200 m", []),
        ("Mt. Apo, 1800-2200 m", ["Mt. Apo"]),
        ("10-50 m", []),
    ],
)
def test_a_range_whose_low_could_be_a_year_is_set_aside(text, places):
    reading = read_locality(text)
    assert (reading.elevations, [part.name for part in reading.parts]) == ((), places)


@pytest.mark.parametrize(
    "text",
    [
        "Elev. 1800-2200 m",
        "Alt. 1800-2200 m",
        "el. 1800-2200 m",
        "1500-2000 m",
        "4000-4500 ft",
        "1946 m",
    ],
)
def test_a_prefix_or_a_low_no_year_could_be_still_reads(text):
    assert [e.text for e in read_locality(text).elevations] == [text]


# The coordinator's reading at 17:40Z on 2026-09-25, extending 15:32Z: next to another
# elevation, such a range reads only when the two convert (1 ft = 0.3048 m, each end
# within the larger of 10 m and 2% of the metric value), in either order.
@pytest.mark.parametrize(
    ("text", "read"),
    [
        ("6000-7000 ft 1829-2134 m", ["6000-7000 ft", "1829-2134 m"]),
        ("6000-7000 ft 1830-2130 m", ["6000-7000 ft", "1830-2130 m"]),
        ("1829-2134 m 6000-7000 ft", ["1829-2134 m", "6000-7000 ft"]),
        ("4800 ft 1946-2500 m", ["4800 ft"]),
        # The tolerance's edges, compared exactly: 1866 is within 2%, 1867 is not, and
        # "6375 ft" is exactly 2% off "1905 m".
        ("6000-7000 ft 1866-2134 m", ["6000-7000 ft", "1866-2134 m"]),
        ("6000-7000 ft 1867-2134 m", ["6000-7000 ft"]),
        ("6375-7375 ft 1905-2248 m", ["6375-7375 ft", "1905-2248 m"]),
        # With the range first and set aside, the elevation after it is checked
        # against the range's numbers and set aside too.
        ("1946-2500 m 4800 ft", []),
        ("1792-2134 m 6000-7000 ft", []),
    ],
)
def test_a_year_like_range_beside_another_elevation_reads_only_if_they_convert(text, read):
    assert [e.text for e in read_locality(text).elevations] == read


@pytest.mark.parametrize(
    "text",
    [
        "July, 1946.950 m",
        "Sept.\n1946,95 m",
        "IV\n1948.950 m",
        "Sept., 1946,95 m",
        "de julio, 1946.950 m",
        "of July, 1946.950 m",
        "julio del, 1946.950 m",
        "VIII/IX\n1948,95 m",
    ],
)
def test_a_part_of_only_a_month_is_kept_aside_with_the_year_after_it(text):
    reading = read_locality(text)
    assert (reading.elevations, reading.parts) == ((), ())


# The month words the Insects profile lists for PLAN 4.8's filter (S4's #183), and
# the Roman months I to XII (G29).
PROFILE_MONTHS = (
    *("January", "February", "March", "April", "May", "June", "July", "August"),
    *("September", "October", "November", "December", "Jan.", "Feb.", "Mar.", "Apr."),
    *("Jun.", "Jul.", "Aug.", "Sep.", "Sept.", "Oct.", "Nov.", "Dec.", "enero", "febrero"),
    *("marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "setiembre"),
    *("octubre", "noviembre", "diciembre", "ene.", "feb.", "mar.", "abr.", "may.", "jun."),
    *("jul.", "ago.", "sep.", "sept.", "set.", "oct.", "nov.", "dic.", "agto.", "sbre."),
    *("obre.", "nbre.", "dbre.", "febr.", "mzo.", "ag."),
    *("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"),
)


@pytest.mark.parametrize("month", PROFILE_MONTHS)
def test_every_month_the_profile_lists_reads_in_any_case(month):
    bare = month.rstrip(".")
    for written in (month, month.lower(), month.upper(), bare, f"{bare}."):
        reading = read_locality(f"Mindanao, {written}, 1946.950 m")
        assert ([part.name for part in reading.parts], reading.elevations) == (
            ["Mindanao"],
            (),
        ), written


def test_the_cost_of_reading_months():
    # A part that is only a month word is no place, and a month the list does not
    # hold is read as a name, so the part after it reads as after any name. Reading
    # every part after another as one after a number would have set the last two
    # elevations aside too.
    reading = read_locality("Mindanao, Mayo, Davao")
    assert ([part.name for part in reading.parts], reading.unplaced) == (
        ["Mindanao", "Davao"],
        ("Mayo",),
    )
    reading = read_locality("Sepbr., 1946.950 m")
    assert ([part.name for part in reading.parts], [e.text for e in reading.elevations]) == (
        ["Sepbr"],
        ["1946.950 m"],
    )
    for text, elevation in (
        ("Mt. Apo, 12,300 ft", "12,300 ft"),
        ("Mt. Apo, 1500-2000 m", "1500-2000 m"),
    ):
        assert [e.text for e in read_locality(text).elevations] == [elevation]


@pytest.mark.parametrize(
    ("text", "unplaced"),
    [
        ("4000 -\n4500 ft", ("4000 -", "4500 ft")),
        ("1500-\n2000 m", ("1500-", "2000 m")),
        ("entre 1500 y\n2000 m", ("entre 1500 y", "2000 m")),
        ("Elev. 1500-\n2000 m", ("Elev. 1500-", "2000 m")),
        ("4000 -\u20284500 ft", ("4000 -", "4500 ft")),
        ("4000 -\x854500 ft", ("4000 -", "4500 ft")),
        ("4000\n~ 4500 m", ("4000", "~ 4500 m")),
        ("4000\nhasta 4500 m", ("4000", "hasta 4500 m")),
        ("4000\nto\n4500 m", ("4000", "to", "4500 m")),
    ],
)
def test_a_line_break_inside_a_range_sets_it_aside(text, unplaced):
    reading = read_locality(text)
    assert (reading.elevations, reading.parts, reading.unplaced) == ((), (), unplaced)


def test_a_line_break_reads_as_a_space_between_two_numbers():
    # The cost: after a line that ends in a number no elevation took, an elevation
    # that words come before on the next lines is set aside, as on one line.
    reading = read_locality("12-IV-1948\nChimaltenango\n1500 m")
    assert ([part.name for part in reading.parts], reading.elevations) == (["Chimaltenango"], ())
    reading = read_locality("12-IV-1948\nChimaltenango 1500 m")
    assert (reading.parts, reading.unplaced) == ((), ("12-IV-1948", "Chimaltenango 1500 m"))
    assert read_locality("Elev.6400\nSept. 3, 1946").elevations == ()
    reading = read_locality("4000\nhasta\n4500 m")
    assert ([part.name for part in reading.parts], reading.elevations) == (["hasta"], ())
    # An elevation or its prefix starting the next line reads, and an elevation read
    # before stops the check. A comma or semicolon stops it after a number that could
    # be no range's low, such as a date's glued year (the coordinator's refinement at
    # 00:38Z on 2026-09-26, and its ruling at 00:52Z).
    for text, read in (
        ("3 Sept. '46\nElev. 6400'", ["Elev. 6400'"]),
        ("3 Sept. '46\n850 m", ["850 m"]),
        ("Elev.6400\n3 Sept. '46", ["Elev.6400"]),
        ("12-IV-1948,\nChimaltenango 1500 m", ["1500 m"]),
        ("12-IV-1948\nChimaltenango;\n1500 m", ["1500 m"]),
        ("Yepocapa 4800 ft.\nChimaltenango\n1500 m", ["4800 ft.", "1500 m"]),
        ("Elev.6400\nAlt. 1950 m", ["Elev.6400", "Alt. 1950 m"]),
    ):
        assert [e.text for e in read_locality(text).elevations] == read, text


@pytest.mark.parametrize("zero", ZEROS[1:])
def test_a_year_in_other_digits_is_still_a_year(zero):
    reading = read_locality(in_digits("Mindanao, 1946 - 2500 m", zero))
    assert ([part.name for part in reading.parts], reading.elevations) == (["Mindanao"], ())
    text = in_digits("Elev. 1800-2200 m", zero)
    assert [e.text for e in read_locality(text).elevations] == [text]


def test_a_range_runs_upward_by_its_whole_parts_in_any_digits():
    # A decimal part, in thousands groups or not, sets a range aside too (round 8).
    for text in ("4500-\uff14\uff10\uff10\uff10 m", "2,000-1,463.5 ft", "1,200-1,463.5 ft"):
        assert read_locality(text).elevations == (), text
    for text in ("1,200-1,500 ft", "1.200-1.500 m", "\uff11\uff15\uff10\uff10-2000 m"):
        assert [e.text for e in read_locality(text).elevations] == [text], text


def test_the_prefixes_include_the_profiles_el():
    # "el." is the Insects profile's, with its period (the coordinator's reading at
    # 15:32Z: prefixes "as the profile's notations list them"). A word between a
    # prefix and its number leaves the prefix unread.
    for text in (
        "el. 1800-2200 m",
        "EL.1500 m",
        "Elev: 1800-2200 m",
        "Elevation 1800-2200 m",
        "ALTITUDE: 1800-2200 m",
    ):
        assert [e.text for e in read_locality(text).elevations] == [text], text
    for text in ("Elev. ca. 1800-2200 m", "el 1800-2200 m"):
        assert read_locality(text).elevations == (), text


@pytest.mark.parametrize(
    ("text", "count"),
    [
        ("4000 ~ " * 20000 + "4500 m", 0),
        ("4000 -\n" * 20000 + "4500 m", 0),
        ("Elev. 1 ~ " * 20000, 0),
        ("a\n" * 20000 + "1 m", 1),
        ("1 m ~ " * 20000, 20000),
        # The run check reads only to the next letter, digit or space.
        ("Elev.1(" * 100000, 1),
        ("Elev.1( " * 100000, 100000),
    ],
    ids=[
        *("tildes", "broken dashes", "prefixed tildes", "word lines", "unit tildes"),
        *("run into marks", "runs ending in spaces"),
    ],
)
def test_the_check_between_two_numbers_is_linear(text, count):
    started = time.monotonic()
    reading = read_locality(text)
    assert time.monotonic() - started < 5
    assert len(reading.elevations) == count


@pytest.mark.parametrize(
    "text",
    [
        "Sept., ?, 1946,95 m",
        "Sept.\nCNHM\n1946,95 m",
        "IV\nCNHM.\n1948.950 m",
        "Sept.\n\u200b\n1946,95 m",
        "12 IV, ?, FMNH, 1948,95 m",
    ],
)
def test_a_part_that_folds_to_nothing_passes_the_date_on(text):
    # A part with no letter or digit, or only an institution code, stands between
    # a month or a number and the year without resetting it.
    reading = read_locality(text)
    assert (reading.elevations, reading.parts) == ((), ())


def test_a_link_before_a_month_begins_a_date_not_a_name():
    reading = read_locality("Mindanao\nde julio, 1946,95 m")
    assert ([part.name for part in reading.parts], reading.elevations) == (["Mindanao"], ())
    reading = read_locality("Mindanao\nof July,1934\n9500 m")
    assert [part.name for part in reading.parts] == ["Mindanao"]
    assert [part.name for part in read_locality("E. slope\nof Mt. Apo").parts] == ["Mt. Apo"]


def test_a_range_with_a_decimal_in_either_number_is_set_aside():
    # A year may have run into the decimal, a prefix before it or not.
    for text, places in (
        ("Mindanao, 1946,95-2500 m", ["Mindanao"]),
        ("Guatemala, 26,5-850 m", ["Guatemala"]),
        ("Elev. 1946,95-2500 m", []),
        ("Alt. 620,31 -9500 m", []),
        ("ELEV: 1.463,26 -9500 ft", []),
    ):
        reading = read_locality(text)
        assert (reading.elevations, [part.name for part in reading.parts]) == ((), places), text
    # A number in thousands groups has no decimal, and reads.
    assert [e.text for e in read_locality("1,946-2,500 m").elevations] == ["1,946-2,500 m"]


@pytest.mark.parametrize(
    "text", ["Del Mar", "de Mayo", "Mar", "May", "Set", "Ene", "Ag", "I", "V", "X"]
)
def test_a_part_of_only_month_words_is_no_place(text):
    reading = read_locality(text)
    assert (reading.parts, reading.unplaced) == ((), (text,))


def test_after_a_part_of_only_month_words_a_range_is_set_aside():
    # The cost: "Mayo" is a month, so the part after it counts as one after a number.
    for text in ("Mayo, 1500-2000 m", "Mayo, 12,300 ft"):
        assert read_locality(text).elevations == (), text


@pytest.mark.parametrize(
    ("text", "month"),
    [("mid-Sept., 1946.950 m", "mid-Sept"), ("late Aug., 1946,95 m", "late Aug.")],
)
def test_a_month_that_shares_its_part_reads_as_a_name(text, month):
    # The stated cost: a qualifier list would be new design (G5).
    reading = read_locality(text)
    assert [part.name for part in reading.parts] == [month]
    assert [e.text for e in reading.elevations] == [text.split(", ")[1]]


# The two baseline readers' transcripts of 105526321, whole, from the lab run of
# 2026-09-25. Read as one literal, "6400'" comes after "3 Sept. '46" with words
# between, so it is set aside. The tool reads each place field's own literal
# (GEOREFERENCING.md 1.1, "Input"), which leaves such lines out.
BASELINE_105526321 = (
    "10-6-78-la\nE. slope Mt. McKinley\nDavao Prov.\nMindanao, P.I.\nF.G. Werner\n"
    "3 sept. '46\nMossy forest 6400'\nsp. 30 \u2640",
    "10-6-78-1a\nE. slope Mt. McKinley\nDavao Prov.\nMindanao, P.I.\nF. G. wermer\n"
    "3 sept. '46\nMossy forest 6400'\nSp. 30 \u2640\nFMNHINS\n4486784",
)


@pytest.mark.parametrize("text", BASELINE_105526321)
def test_the_line_break_rule_costs_a_whole_transcript_its_elevation(text):
    reading = read_locality(text)
    assert reading.elevations == ()
    names = [part.name for part in reading.parts]
    assert names[:4] == ["Mt. McKinley", "Davao", "Mindanao", "P.I."]


def test_across_a_comma_the_check_goes_on_only_from_a_bare_number():
    # The coordinator's reading at 22:22Z on 2026-09-25 (coordinator.md:468), refined
    # at 00:38Z on 2026-09-26 (:498): after a bare number, with no unit or prefix of
    # its own and nothing glued before it (00:52Z, :501), any word or mark continues
    # the check across a comma or semicolon, so its range is never read by the top.
    for text in (
        "4000, ~ 4500 m",
        "4000 ~, 4500 m",
        "4000, ?, 4500 m",
        "4000 to, 4500 m",
        "4000 ~,\n4500 m",
        "4000, hasta 4500 m",
        "4000, up to 4500 m",
        "1500, bis 2000 m",
        "4000, at\u00e9 4500 m",
        "4000, \u00e0 4500 m",
        "4000 hasta, 4500 m",
        "Camp 3, Mt. Apo 1500 m",
        "Km 42, a 1500 m",
    ):
        reading = read_locality(text)
        assert (reading.elevations, reading.parts) == ((), ()), text
    # A number with its own unit or prefix is a complete elevation, and a glued one,
    # such as a date's year, could be no range's low: either ends the check. With
    # nothing but the comma after a bare number, the next elevation reads too.
    for text, read in (
        ("6-Sept-1946, Elev.6400", ["Elev.6400"]),
        ("12-IV-1948, Yepocapa, 1500 m", ["1500 m"]),
        ("12-IV-1948, Yepocapa, Elev. 1500 m", ["Elev. 1500 m"]),
        ("1946, 950 m", ["950 m"]),
    ):
        assert [e.text for e in read_locality(text).elevations] == read, text
    # A word alone in its own part stays a part, a lookup candidate the lookups
    # verify (the coordinator's ruling at 22:25Z, coordinator.md:470).
    for text, name in (
        ("4000, hasta, 4500 m", "hasta"),
        ("12-IV-1948, Yepocapa, 1500 m", "Yepocapa"),
    ):
        assert [part.name for part in read_locality(text).parts] == [name], text


def test_the_comma_rule_s_stated_costs():
    # The coordinator's rulings at 00:52Z on 2026-09-26 (coordinator.md:502): (1) a
    # prefixed low with a comma or semicolon in its join reads both ends as separate
    # elevations; (2) a date's glued year before such a join reads only the
    # elevation after it; (3) a low glued into the number before it by a comma reads
    # the top, and the number before too when it reads, the low's digits in it. A
    # leftover range word is a lookup candidate that matches no place; so is one
    # after an elevation read, as on one line.
    for text, read, names in (
        ("Elev. 4000, hasta 4500 m", ["Elev. 4000", "4500 m"], ["hasta"]),
        ("alt 6000 & ; 7000 ft.", ["alt 6000", "7000 ft."], []),
        ("ene.-1983, to 950 ft.", ["950 ft."], []),
        ("IV-1948, hasta 95 m", ["95 m"], ["hasta"]),
        ("Elevation 3300,10 - ; 50 m", ["50 m"], []),
        ("Elev.3300,26 up to ; 750 feet", ["Elev.3300,26", "750 feet"], ["up to"]),
        ("4000 m hasta 4500 m", ["4000 m", "4500 m"], ["hasta"]),
        ("4000 m up to 4500 m", ["4000 m", "4500 m"], ["up to"]),
    ):
        reading = read_locality(text)
        elevations = [e.text for e in reading.elevations]
        assert (elevations, [part.name for part in reading.parts]) == (read, names), text


# The two baseline readers' whole transcripts of 105526322, 105526329 and
# 105526330, from the reader baseline of 2026-09-23. Each states its elevation, which
# round 9's comma reading set aside and its refinement at 00:38Z on 2026-09-26 reads
# again (coordinator.md:498).
BASELINE_STATED = (
    (
        "CNHM. ESlope Mt.\nMcKinley, Davao Prov.\nMindanao, P.I.\n6-Sept-1946, Elev. 6400\n"
        "H. Hoogstraal leg.\nshrubs, mostly forest\nwings 4 head\nsp. 30 \u2640\n9-25-81-16",
        "Elev. 6400",
    ),
    (
        "CNHM. E Slope Mt.\nMcKinley, Davao Prov.\nMindanao, P.I.\n6-Sept-1946, Elev.6400\n"
        "H. Hoogstraal leg.\nShrubs, mostly forest\nWings 4 head\nSp.30 \u2640\np-95-81-16",
        "Elev.6400",
    ),
    (
        "IV-29-68-4\nYepocapa, 4800ft.\nChimaltenango,\nGuatemala\nIV-23-48\nR.D.mitchell\n"
        "sp #1 \u2642\nhead & legs",
        "4800ft.",
    ),
    (
        "IV- 29-68-4\nYepocapa, 4800ft.\nChimaltenago,\nGuatemala\nIV-23-48\nR.D.Mitchell\n"
        "Sp#1 \u2642\nhead & legs",
        "4800ft.",
    ),
    (
        "IV-29-68-a\nYepocapa, 4800 ft.\nChimaltenango\nGuatemala, IV-25\n1948, R.D. Mitchell\n"
        "\u2640 legs Sp.#1",
        "4800 ft.",
    ),
    (
        "IV-29-68-2\nYepocapa,4800 ft.\nChimaltenago\nGuatemala,IV-26\n1948, R.D. Mitchell\n"
        "\u2640 legs Sp.#1",
        "4800 ft.",
    ),
)


@pytest.mark.parametrize(("text", "stated"), BASELINE_STATED)
def test_a_baseline_transcript_reads_its_stated_elevation(text, stated):
    assert [e.text for e in read_locality(text).elevations] == [stated]


def test_a_number_with_no_unit_running_into_a_date_is_set_aside():
    # It runs straight into more letters or digits, or has a decimal part that a
    # number or a month follows, in its part or the next. A unit outside the list
    # glued on is set aside with it ("Alt. 2100msnm"); what fold drops is nothing.
    for text in (
        "Elevation 6400,13.sbre.",
        "alt 1.463,27-of jun.",
        "Elev.6400,13.XI",
        "el. 6400,12 Sep",
        "el. 6400,12 de julio",
        "Elev.3300,12 4 1948",
        "el. 1.463,18 of may.",
        "Alt. 2100msnm",
        "Elev.6400pies",
    ):
        assert read_locality(text).elevations == (), text
    for text in (
        "Elev. 6400.",
        "Elev. 6400)",
        "Elev.6400",
        "Elev. 1463,5 Davao",
        "Elev. 6400 Sept.",
        "Elev.6400\u3164",
    ):
        assert len(read_locality(text).elevations) == 1, text


# The letters Python counts as alphanumeric that `fold` drops, the 21 the steward's
# round-8 review names. `fold` drops six of them outright; the other fifteen are
# spacing marks, whose compatibility form is a space and combining marks.
FOLD_DROPPED_LETTERS = (
    *("\u037a", "\u115f", "\u1160", "\u3164", "\uffa0"),
    *(chr(code) for code in range(0xFC5E, 0xFC64)),
    *(chr(code) for code in range(0xFE70, 0xFE7F, 2)),
    *("\uff9e", "\uff9f"),
)


def spacing_mark(c):
    """Whether the character's compatibility form is a space and combining marks."""
    form = unicodedata.normalize("NFKD", c)
    return (
        not c.isspace()
        and form[:1] == " "
        and len(form) > 1
        and all(unicodedata.category(mark) in ("Mn", "Me") for mark in form[1:])
    )


# Every spacing mark in the Unicode data this Python holds, "\u02dc" and "\u203e"
# among them (the round-9 review counts 50).
SPACING_MARKS = tuple(filter(spacing_mark, map(chr, range(sys.maxunicode + 1))))
# What `fold` drops outright: the six letters, format characters and a combining mark.
DROPPED = (
    *(c for c in FOLD_DROPPED_LETTERS if not spacing_mark(c)),
    *("\u200b", "\u00ad", "\u2060", "\ufeff", "\u0301"),
)


def test_the_spacing_marks_hold_the_review_s_examples():
    assert {"\u02dc", "\u203e", "\u037a", "\ufe70", "\ufc5e"} <= set(SPACING_MARKS)
    assert len(DROPPED) == 11


@pytest.mark.parametrize("dropped", DROPPED)
def test_what_fold_drops_is_nothing(dropped):
    # The reader's patterns read the text without it (the round-9 review's first
    # blocker). A part of it passes the date on; beside a join word or a mark it hides
    # nothing; inside or beside a number it splits nothing; before a month it is no
    # word; after a link it hides no month.
    for text in (f"Sept.\n{dropped}\n1946,95 m", f"IV, {dropped}, 1948.950 m"):
        reading = read_locality(text)
        assert (reading.elevations, reading.parts) == ((), ()), text
    for text in (
        f"4000, ~{dropped} 4500 m",
        f"4000, t{dropped}o 4500 m",
        f"el. 6400,12 {dropped} Sep",
        f"Elev. 4{dropped} 800 ft.",
        f"14 m{dropped}arzo 1948",
        f"Sept. 3 '{dropped}46",
    ):
        assert read_locality(text).elevations == (), text
    for text, numbers in (
        (f"3 Sept. '46 {dropped} 850 m", [("850", None)]),
        (f"Elev. 1463{dropped},5 m", [("1463,5", None)]),
        (f"Mt. Apo 1{dropped},463 m", [("1,463", None)]),
        (f"el. {dropped}1,200 - 1{dropped},500 ft", [("1,200", "1,500")]),
        (f"Elev. 64{dropped}00", [("6400", None)]),
    ):
        assert [(e.low, e.high) for e in read_locality(text).elevations] == numbers, text
    reading = read_locality(f"Mindanao\nde {dropped} julio 1946,95 m")
    assert ([part.name for part in reading.parts], reading.elevations) == (["Mindanao"], ())


@pytest.mark.parametrize("mark", SPACING_MARKS)
def test_a_spacing_mark_is_a_mark(mark):
    # The round-9 review's second blocker: between two numbers it joins them, on one
    # line and across a line break, or a comma after a bare number; a part of only it
    # passes the date on.
    for text in (
        f"4000 {mark} 4500 m",
        f"Elev. 1500 {mark} 2000 m",
        f"Alt. 1,200 {mark} 1,500 ft",
        f"3 Sept. '46 {mark} 850 m",
        f"4000 {mark}, 4500 m",
        f"4000, {mark} 4500 m",
        f"4000 {mark}\n4500 m",
        f"4000\n{mark} 4500 m",
        f"Sept.\n{mark}\n1946,95 m",
    ):
        assert read_locality(text).elevations == (), text
    # The stated cost (1): a prefixed low with a comma in its join reads apart.
    reading = read_locality(f"Elev. 1500 {mark}, 2000 m")
    assert [e.text for e in reading.elevations] == ["Elev. 1500", "2000 m"]


def test_the_patterns_read_what_shows_and_keep_what_was_written():
    zero = "\u200b"
    reading = read_locality(f"Elev. 1463{zero},5 m")
    assert [(e.text, e.low) for e in reading.elevations] == [(f"Elev. 1463{zero},5 m", "1463,5")]
    reading = read_locality(f"Mt. Apo (1463{zero} m)")
    elevations = [e.text for e in reading.elevations]
    assert (elevations, [part.name for part in reading.parts]) == ([f"1463{zero} m"], ["Mt. Apo"])
    (part,) = read_locality(f"5 km N{zero} of Yepo{zero}capa").parts
    assert (part.name, part.key, part.relation) == (f"Yepo{zero}capa", "yepocapa", "offset")
    for text in (f"E.{zero} slope Mt. Apo", "E. slope\n\u3164 of Mt. Apo"):
        (part,) = read_locality(text).parts
        assert (part.name, part.relation) == ("Mt. Apo", "slope"), text
    assert read_locality(f"Mindanao, P.{zero}I.").parts[1].readings == ("Philippine Islands",)
    reading = read_locality("Mindanao, CNHM\u0301.")
    assert (reading.institutions, reading.unplaced) == (("CNHM\u0301.",), ())
    # A soft hyphen that ends a line, what `fold` drops after it aside, shows as a
    # hyphen: here it breaks a range.
    for text in ("Elev. 1500\u00ad\n2000 m", f"Elev. 1500\u00ad{zero}\n2000 m"):
        assert read_locality(text).elevations == (), text


def shown(text):
    """Whether the text holds something other than spaces, marks, format characters and
    Hangul fillers."""
    return any(
        not c.isspace() and unicodedata.category(c) not in ("Mn", "Me", "Cf")
        for c in unicodedata.normalize("NFKD", text)
        if c not in "\u115f\u1160\u3164\uffa0"
    )


def reading_values(text):
    """A reading by value: elevation numbers and folded texts, part keys with their
    relations and units, and the folded unplaced texts that show."""
    reading = read_locality(text)
    return (
        [(e.low, e.high, e.unit, fold(e.text)) for e in reading.elevations],
        [(p.key, p.relation, p.distance, p.unit) for p in reading.parts],
        [fold(u) for u in reading.unplaced if shown(u)],
        [fold(i) for i in reading.institutions],
    )


@pytest.mark.parametrize("seed", range(4))
def test_what_fold_drops_changes_no_reading(seed):
    # Put anywhere in a random layout, what `fold` drops changes nothing read, save a
    # soft hyphen that ends a line (only spaces and what `fold` drops after it),
    # which shows as a hyphen.
    rng = random.Random(seed)
    for _ in range(500):
        text = RandomLayout(rng).build()
        changed = text
        for _ in range(rng.randint(1, 4)):
            cut = rng.randint(0, len(changed))
            lines = changed[cut:].splitlines(keepends=True)
            dropped = rng.choice(DROPPED)
            if dropped == "\u00ad" and lines and not shown(lines[0]):
                continue
            changed = changed[:cut] + dropped + changed[cut:]
        assert reading_values(changed) == reading_values(text), (text, changed)


def test_an_institution_code_in_any_width_is_matched_as_fold_reads_it():
    wide = "\uff23\uff2e\uff28\uff2d"
    reading = read_locality(f"Sept.\n{wide}\n1946,95 m")
    assert (reading.elevations, reading.parts, reading.institutions) == ((), (), (wide,))
    reading = read_locality(f"{wide}. E. Slope Mt. Apo")
    assert [part.name for part in reading.parts] == ["Mt. Apo"]
    assert reading.institutions == (f"{wide}.",)


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("Vi\u00f1a\ndel Mar", "Vi\u00f1a del Mar"),
        ("Isle\nof May", "Isle of May"),
        ("Plaza\nde Mayo", "Plaza de Mayo"),
    ],
)
def test_a_link_and_a_month_with_no_number_after_them_join_as_a_name(text, name):
    assert [part.name for part in read_locality(text).parts] == [name]


def test_a_link_and_a_month_begin_a_date_only_with_a_number_right_after_the_month():
    # A number after a name that starts with a month is no date's.
    for text, read in (
        ("E. slope\nof May Hill", []),
        ("E. slope\nof May Hill\n1500 m", ["1500 m"]),
        ("E. slope\nof May Hill 1500 m", ["1500 m"]),
    ):
        reading = read_locality(text)
        (part,) = reading.parts
        assert (part.name, part.relation) == ("May Hill", "slope"), text
        assert [e.text for e in reading.elevations] == read, text
    (part,) = read_locality("5 km N\nof Mar Chiquita").parts
    assert (part.name, part.relation, part.distance) == ("Mar Chiquita", "offset", "5")
    # The number may be glued to the month, since the line is read as `fold` reads
    # it, come after a link after the month, or start the next line that holds more
    # than what folds to nothing or an institution code. An institution code
    # between them is no word.
    for text in (
        "Mindanao\nde julio, 1946,95 m",
        "Mindanao\nde julio,1946,95 m",
        "Mindanao\nde julio-1946.95 m",
        "Mindanao\nde julio de 1946",
        "Mindanao\nde julio, CNHM, 1946,95 m",
        "Mindanao\nde julio\n1946,95 m",
        "Mindanao\nde julio\n?\n1946,95 m",
        "Mindanao\nde julio\nCNHM\n1946,95 m",
        "Mindanao\nde julio, \u02bc46",
        "Mindanao\nde julio \u02bc46",
        "Mindanao\nde julio\n\u02bc46",
    ):
        reading = read_locality(text)
        names = [part.name for part in reading.parts]
        assert (names, reading.elevations) == (["Mindanao"], ()), text
    # The costs: a name of a link and a month with a number after it reads as a
    # date, and a date with no number right after its month reads as a name.
    reading = read_locality("Vi\u00f1a\ndel Mar\n1500-2000 m")
    assert ([part.name for part in reading.parts], reading.elevations) == (["Vi\u00f1a"], ())
    reading = read_locality("Isle\nof May\n1500 m")
    names, read = [part.name for part in reading.parts], [e.text for e in reading.elevations]
    assert (names, read) == (["Isle"], ["1500 m"])
    for text in ("Mindanao\nde julio", "Mindanao\nde julio\nCamp 3"):
        assert [part.name for part in read_locality(text).parts] == ["Mindanao de julio"], text


def test_a_day_is_looked_for_in_the_next_part_too():
    assert read_locality("Elev.6400,12, XI.1946").elevations == ()
    assert [e.text for e in read_locality("Elev. 1463,5, Mt. Apo").elevations] == ["Elev. 1463,5"]


# A seeded random generator over every token class the reviews found: months with
# and without qualifiers and links; years, decimals and grouped numbers; parts that
# fold to nothing and institution codes; prefixes, joins and marks; line breaks and
# commas; digit scripts and units. Every number's digit groups are unique in its
# layout, so a reading traces back to what the layout wrote, and what `fold` drops
# goes anywhere now and then. Joins with a word beside a comma are generated too.
# Two kinds of stated cost are exempt, by name: a month that shares its part with a
# qualifier reads as a name; and a range whose join holds a comma or semicolon may
# read an end alone when its low has a prefix or is glued to the text before it (the
# coordinator's rulings at 00:52Z on 2026-09-26: a prefixed low, a date's glued year,
# a low glued into the number before it by a comma).
RANDOM_PLACES = (
    *("Mindanao", "Davao", "Guatemala", "Yepocapa"),
    *("Chimaltenango", "Mt. Apo", "Davao Prov."),
)
RANDOM_FILLERS = (
    *("?", "-", "\u2014", "\u2026", "\u200b", "*", "\u00b7"),
    *("\u3164", "\uffa0", "\u037a", "\ufe72"),
    *("CNHM", "CNHM.", "FMNH", "fmnh", "( )", "\uff23\uff2e\uff28\uff2d"),
)
# Characters fold drops, put anywhere in a layout now and then.
RANDOM_DROPPED = ("\u200b", "\u00ad", "\u3164", "\u2060", "\ufeff", "\u0301")
RANDOM_BREAKS = (
    *("\n", "\r\n", "\r", "\x0b", "\x0c", "\x1c"),
    *("\x1d", "\x1e", "\x85", "\u2028", "\u2029"),
)
RANDOM_SEPARATORS = (", ", ",", "; ", " ,", ",\n", ";\n")
RANDOM_PREFIXES = (
    *("Elev. ", "Elev.", "ELEV: ", "Elevation ", "Alt. "),
    *("alt ", "el. ", "Altitude: ", "El."),
)
RANDOM_UNITS = (" m", " ft", " ft.", "'", " feet", " metres", "m", "ft", " M", " FT")
RANDOM_TAILS = ("95", "950", "9500", "75", "750", "7500")
RANDOM_SINGLES = ("4800", "3300", "6400", "1,463", "1.463", "12,300", "2,954", "620", "3,048")
RANDOM_PAIRS = (
    *(("4000", "4500"), ("1,200", "1,500"), ("1.200", "1.500"), ("2500", "3000")),
    *(("6000", "7000"), ("1800", "2200"), ("10", "50"), ("1500", "2000"), ("5,500", "6,000")),
)
QUALIFIERS = ("mid-", "late ", "early ", "end of ", "fin de ")


def glued_before(text, start):
    """Whether something is glued to the number at `start` as the reader sees it: no
    space, line break, opening bracket or semicolon comes before it, and no comma but
    one after a digit, which may put the number inside the one before."""
    if start == 0:
        return False
    before = text[start - 1]
    if before.isspace() or before in "([{;":
        return False
    return before != "," or (start > 1 and text[start - 2].isdecimal())


def digit_groups(number):
    """A number's digit groups in ASCII: "1,463" is {"1", "463"}."""
    ascii_digits = "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in number)
    return set(re.split(r"[.,]", ascii_digits))


class RandomLayout:
    """One random layout, with what it wrote: date numbers, ranges and month words."""

    def __init__(self, rng):
        self.rng = rng
        self.chunks = []
        self.used = set()
        self.date_groups = set()
        self.ranges = []
        self.date_words = set()
        self.exempt_words = set()
        # Ranges the comma rule's stated costs let read an end alone, and the chunks
        # whose range becomes one if the comma before the chunk glues its low.
        self.apart = set()
        self.comma_chunks = {}

    def fresh(self, values):
        def groups(value):
            numbers = [value] if isinstance(value, str) else value
            return set().union(*(digit_groups(n) for n in numbers))

        pool = [v for v in values if not groups(v) & self.used]
        if not pool:
            return None
        value = self.rng.choice(pool)
        self.used |= groups(value)
        return value

    def zero(self):
        return self.rng.choice(ZEROS) if self.rng.random() < 0.3 else "0"

    def boundary(self):
        r = self.rng.random()
        if r < 0.45:
            return self.rng.choice(RANDOM_SEPARATORS)
        if r < 0.9:
            return self.rng.choice(RANDOM_BREAKS)
        return self.rng.choice(RANDOM_SEPARATORS) + self.rng.choice(RANDOM_BREAKS)

    def join(self):
        """A range join, spaced or not, maybe broken across lines, by a comma or by a
        part with no letter."""
        rng = self.rng
        join = rng.choice((*RANGE_WORDS, *OTHER_JOINS))
        form = rng.choice((join, f" {join} ", f"{join} ", f" {join}"))
        r = rng.random()
        if r < 0.2:
            line_break = rng.choice(RANDOM_BREAKS)
            form = rng.choice(
                (f"{form}{line_break}", f"{line_break}{form}", f"{line_break}{join}{line_break}")
            )
        elif r < 0.3:
            separator = rng.choice((",", ", ", ";", "; "))
            form = rng.choice((f"{separator}{form}", f"{form}{separator}"))
        elif r < 0.38:
            filler = rng.choice(("?", "-", "*", "CNHM", "\u2026"))
            form = f"{form}{self.boundary()}{filler}{self.boundary()}"
        return form

    def comma_join(self, pair, join, apart):
        """Note a range whose join holds a comma or semicolon: it may read an end
        alone when its low has a prefix or is glued to the text before it (`apart`), or
        when the comma before its chunk glues the low to the number before (`build`)."""
        if any(c in join for c in ",;"):
            if apart:
                self.apart.add(pair)
            else:
                self.comma_chunks[len(self.chunks) - 1] = pair

    def month(self):
        rng = self.rng
        unused = [m for m in PROFILE_MONTHS if fold(m) not in self.date_words]
        month = rng.choice(unused or PROFILE_MONTHS)
        bare = month.rstrip(".")
        written = rng.choice((month, month.lower(), month.upper(), bare, f"{bare}."))
        if rng.random() < 0.15:
            written = rng.choice(("de ", "del ", "of ")) + written
        return fold(month), written

    def place(self):
        self.chunks.append(self.rng.choice(RANDOM_PLACES))

    def filler(self):
        self.chunks.append(self.rng.choice(RANDOM_FILLERS))

    def single(self):
        value = self.fresh(RANDOM_SINGLES)
        if value is not None:
            prefix = self.rng.choice(("", "", "", *RANDOM_PREFIXES))
            unit = self.rng.choice(RANDOM_UNITS) if not prefix or self.rng.random() < 0.6 else ""
            self.chunks.append(f"{prefix}{in_digits(value, self.zero())}{unit}")

    def range(self):
        pair = self.fresh(RANDOM_PAIRS)
        if pair is not None:
            zero = self.zero()
            low, high = (in_digits(n, zero) for n in pair)
            prefix = self.rng.choice(("", "", "", *RANDOM_PREFIXES))
            join = self.join()
            self.chunks.append(f"{prefix}{low}{join}{high}{self.rng.choice(RANDOM_UNITS)}")
            self.ranges.append((low, high))
            self.comma_join((low, high), join, apart=bool(prefix))

    def date(self):
        rng = self.rng
        zero = self.zero()
        kinds = ("month", "month", "qualified", "day-month", "numeric", "bare", "month-day")
        kind = rng.choice(kinds)
        years = (str(rng.randint(1700, 2099)), rng.choice(("26", "46", "48", "31")))
        year_value = self.fresh(years)
        if year_value is None:
            return
        year = in_digits(year_value, zero)
        if len(year_value) == 2 and rng.random() < 0.3:
            year = rng.choice(("'", "\u2019")) + year
        numbers, head, words, qualified = [year_value], "", None, False
        if kind in ("month", "qualified"):
            words, head = self.month()
            if kind == "qualified":
                head, qualified = rng.choice(QUALIFIERS) + head, True
        elif kind in ("day-month", "month-day"):
            words, month = self.month()
            day = self.fresh([str(d) for d in range(1, 29)])
            numbers.append(day)
            day = in_digits(day, zero)
            if kind == "day-month":
                head = f"{day}{rng.choice((' ', '-', '.', '/', ', '))}{month}"
            else:
                head = f"{month} {day}"
        elif kind == "numeric":
            day = self.fresh([str(d) for d in range(13, 29)])
            month_number = self.fresh([str(m) for m in range(1, 13)])
            numbers += [day, month_number]
            mark = rng.choice(("-", ".", "/"))
            head = f"{in_digits(day, zero)}{mark}{in_digits(month_number, zero)}"
        split = False
        if head:
            if rng.random() < 0.6:
                split, link = True, self.boundary()
                for _ in range(rng.choice((0, 0, 1, 2))):
                    link += rng.choice(RANDOM_FILLERS) + self.boundary()
            else:
                link = rng.choice((" ", "-", ".", "/", "\u2013", ", "))
                split = link == ", "
            dated = f"{head}{link}{year}"
        else:
            dated = year
        if words is not None:
            self.date_words.add(words)
        if qualified and split:
            self.exempt_words.add(words)
        elif head:
            # A bare year is a number like any other; with a head, the date's
            # numbers are its year, day and month number.
            self.date_groups.update(numbers)
        tail_kind = rng.choice(("none", "glued", "space", "break", "join", "join", "join"))
        tail = self.fresh(RANDOM_TAILS) if tail_kind != "none" else None
        if tail is None:
            self.chunks.append(dated)
            return
        tail, unit = in_digits(tail, zero), rng.choice(RANDOM_UNITS)
        if tail_kind == "glued":
            self.chunks.append(f"{dated}{rng.choice((',', '.'))}{tail}{unit}")
        elif tail_kind == "space":
            self.chunks.append(f"{dated} {tail}{unit}")
        elif tail_kind == "break":
            self.chunks.append(f"{dated}{rng.choice(RANDOM_BREAKS)}{tail}{unit}")
        else:
            join = self.join()
            self.chunks.append(f"{dated}{join}{tail}{unit}")
            digits = year.lstrip("'\u2019")
            self.ranges.append((digits, tail))
            glued = glued_before(dated, len(dated) - len(digits))
            self.comma_join((digits, tail), join, apart=glued)

    def build(self):
        makers = (
            *(self.place, self.filler, self.single, self.range),
            *(self.date, self.date, self.range),
        )
        for _ in range(self.rng.randint(1, 5)):
            self.rng.choice(makers)()
        text = ""
        for index, chunk in enumerate(self.chunks):
            if text:
                text += self.boundary()
            if index in self.comma_chunks and glued_before(text, len(text)):
                self.apart.add(self.comma_chunks[index])
            text += chunk
        for _ in range(self.rng.choice((0, 0, 1, 2))):
            cut = self.rng.randint(0, len(text))
            text = text[:cut] + self.rng.choice(RANDOM_DROPPED) + text[cut:]
        return text


@pytest.mark.parametrize("seed", range(16))
def test_random_layouts_keep_the_three_properties(seed):
    rng = random.Random(seed)
    for _ in range(1000):
        layout = RandomLayout(rng)
        text = layout.build()
        reading = read_locality(text)
        for e in reading.elevations:
            held = digit_groups(e.low) | (digit_groups(e.high) if e.high else set())
            # No elevation holds a date's number.
            assert not held & layout.date_groups, (text, e.text)
            # No range is read by one of its numbers alone, or by part of one, save the
            # comma rule's stated costs, which read its ends apart: no elevation holds
            # both, though a low glued into the number before it is read in that one.
            for low, high in layout.ranges:
                ends = digit_groups(low) | digit_groups(high)
                if not held & ends or (e.low, e.high) == (low, high):
                    continue
                both = digit_groups(low) <= held and digit_groups(high) <= held
                assert (low, high) in layout.apart and not both, (text, e.text)
        # No date fragment is a part, save the stated cost.
        for part in reading.parts:
            dated = set(fold(part.text).split()) & layout.date_words
            assert not dated - layout.exempt_words, (text, part.text)


def test_brackets_open_a_part_and_a_colon_glues():
    for text, elevation in (("(12,300 ft)", "12,300 ft"), ("(1946,63 m)", "1946,63 m")):
        assert [e.text for e in read_locality(text).elevations] == [elevation]
    reading = read_locality("Mt. Apo\uff081463 m\uff09")
    assert [part.name for part in reading.parts] == ["Mt. Apo"]
    assert [e.text for e in reading.elevations] == ["1463 m"]
    for text in ("Yepocapa:1500 m", "Altitud:1500 m"):
        reading = read_locality(text)
        assert (reading.elevations, reading.unplaced) == ((), (text,))


def test_a_number_after_another_number_and_one_word_is_set_aside():
    # The word may join a range no table lists, so "Camp 3 at 1500 m" costs its
    # elevation too. Right after another elevation a number is its pair.
    reading = read_locality("Camp 3 at 1500 m")
    assert (reading.elevations, reading.unplaced) == ((), ("Camp 3 at 1500 m",))
    for text in ("4800 ft 1463 m", "4800 ft/1463 m", "1500 m and 2000 m"):
        assert len(read_locality(text).elevations) == 2


def test_a_touching_word_counts_and_a_number_with_no_unit_looks_ahead():
    # A word or mark touching the number before counts as one between them, and a
    # number with no unit is checked against the number after it, that number's
    # own prefix aside.
    for text in ("Camp 3a 1500 m", "5km 1500 m", "Elev.6400 Camp 3", "Elev.6400,12-IV-1948"):
        reading = read_locality(text)
        assert (reading.elevations, reading.unplaced) == ((), (text,)), text
    assert len(read_locality("Elev. 1500 Elev. 2000 m").elevations) == 2


def test_two_or_four_leading_digits_after_other_text_may_be_a_year():
    # "12,300" could be the year '12 run into "300", so after other text it is set
    # aside; after a comma it starts its own part and reads.
    reading = read_locality("Mt. Apo 12,300 ft")
    assert (reading.elevations, reading.unplaced) == ((), ("Mt. Apo 12,300 ft",))
    reading = read_locality("Mt. Apo, 12,300 ft")
    assert [e.text for e in reading.elevations] == ["12,300 ft"]
    assert [e.text for e in read_locality("Mt. Apo 1,463 m").elevations] == ["1,463 m"]


def test_a_bracketed_elevation_takes_its_brackets():
    reading = read_locality("Mt. Apo (1463 m)")
    assert [part.name for part in reading.parts] == ["Mt. Apo"]
    assert [e.text for e in reading.elevations] == ["1463 m"]


def test_of_at_a_line_start_joins_the_line_before_in_any_case():
    (part,) = read_locality("E. SLOPE\nOF MT. APO").parts
    assert (part.name, part.relation) == ("MT. APO", "slope")
    (part,) = read_locality("5 KM NE\nOF YEPOCAPA").parts
    assert (part.name, part.relation, part.distance) == ("YEPOCAPA", "offset", "5")
    (part,) = read_locality("County\nOf Cook").parts
    assert (part.name, part.unit) == ("Cook", "county")


def test_only_a_two_digit_year_after_an_apostrophe_is_no_digit_group():
    reading = read_locality("'4 800 ft.")
    assert (reading.elevations, reading.unplaced) == ((), ("'4 800 ft.",))
    reading = read_locality("'46 850 m")
    assert ([e.text for e in reading.elevations], reading.unplaced) == (["850 m"], ("'46",))


def test_semicolons_separate_parts():
    assert [part.name for part in read_locality("Yepocapa; Chimaltenango; Guatemala").parts] == [
        "Yepocapa",
        "Chimaltenango",
        "Guatemala",
    ]


def test_a_line_ending_in_a_linking_word_joins_the_next():
    (part,) = read_locality("Departamento de\nChimaltenango").parts
    assert (part.name, part.unit) == ("Chimaltenango", "department")
    (part,) = read_locality("5 km NE of\nYepocapa").parts
    assert (part.name, part.relation, part.distance) == ("Yepocapa", "offset", "5")


def test_a_lone_unit_word_falls_back_to_its_other_neighbour():
    (part,) = read_locality("Prov., Davao").parts
    assert (part.name, part.unit) == ("Davao", "province")
    assert part.readings == ("Davao Province", "Davao")


def test_a_heading_phrase_between_features_or_beside_none():
    parts = read_locality("Mt. Apo, E. slope, Mt. Talomo").parts
    assert [(p.name, p.relation) for p in parts] == [("Mt. Apo", "slope"), ("Mt. Talomo", None)]
    parts = read_locality("Davao, E. slope, Mindanao").parts
    assert [(p.name, p.relation) for p in parts] == [("Davao", "slope"), ("Mindanao", None)]


def test_the_link_after_a_leading_unit_word():
    (part,) = read_locality("County of Cook").parts
    assert (part.name, part.unit) == ("Cook", "county")
    assert comparison_key("County of Cook") == "cook"


@pytest.mark.parametrize(
    ("text", "name", "unit"),
    [
        ("DAVAO PROV", "DAVAO", "province"),
        ("davao prov.", "davao", "province"),
        ("Davao PROVINCE", "Davao", "province"),
        ("Guatemala DEPT.", "Guatemala", "department"),
        ("Guatemala department", "Guatemala", "department"),
        ("Cook CO", "Cook", "county"),
        ("Cook county", "Cook", "county"),
        ("Chiapas STATE", "Chiapas", "state"),
        ("Davao region", "Davao", "region"),
        ("MUN Yepocapa", "Yepocapa", "municipality"),
        ("municipio Yepocapa", "Yepocapa", "municipality"),
        ("Municipality Yepocapa", "Yepocapa", "municipality"),
        ("DEPTO. Chimaltenango", "Chimaltenango", "department"),
        ("departamento Chimaltenango", "Chimaltenango", "department"),
        ("PROVINCIA Davao", "Davao", "province"),
        ("estado Chiapas", "Chiapas", "state"),
    ],
)
def test_unit_words_read_in_any_case_with_or_without_the_period(text, name, unit):
    (part,) = read_locality(text).parts
    assert (part.name, part.unit) == (name, unit)


@pytest.mark.parametrize(
    ("text", "reading"),
    [
        ("mt apo", "Mount apo"),
        ("MT. APO", "Mount APO"),
        ("Mount Apo", "Mount Apo"),
        ("p.i.", "Philippine Islands"),
        ("P.I", "Philippine Islands"),
    ],
)
def test_feature_and_country_notations_read_in_any_case(text, reading):
    (part,) = read_locality(text).parts
    assert part.readings[0] == reading


def test_institutions_read_in_any_case():
    assert read_locality("cnhm, Mt. Apo").institutions == ("cnhm",)
    assert read_locality("FMNH. Mt. Apo").institutions == ("FMNH.",)


def test_fold_and_comparison_keys():
    assert fold("Chimaltenángo,") == "chimaltenango"
    assert fold("P.I.") == "p i"
    assert fold("Davao-del-Norte") == "davao del norte"
    # Format characters (Unicode Cf) are dropped, not turned into spaces.
    assert fold("Dava\u200bo") == fold("\ufeffDavao") == fold("Dav\u200fao") == "davao"
    # Other marks with no letter of their own go too (U+FE0F, a variation selector).
    assert fold("Dava\ufe0fo") == "davao"
    assert fold("Dava\u20ddo") == "davao"  # U+20DD, an enclosing mark
    assert fold("Davao\u3164") == "davao"  # U+3164, an invisible Hangul filler
    assert fold("\u115fDa\u1160vao\uffa0") == "davao"
    assert fold("Dava\u0345o") == "davao"  # U+0345 casefolds to an iota; marks go first
    assert comparison_key("Mt. Apo") == comparison_key("Mount Apo") == "mount apo"
    assert comparison_key("Departamento de Chimaltenango") == "chimaltenango"
    assert comparison_key("Chimaltenango Department") == "chimaltenango"
    assert comparison_key("Provincia de Davao") == comparison_key("Davao Prov.") == "davao"
    assert comparison_key("Davao del Norte") == "davao del norte"


def test_letters_apart_counts_single_edits_up_to_two():
    assert letters_apart("chimaltenago", "chimaltenango") == 1
    assert letters_apart("chimaltenango", "chimaltenago") == 1
    assert letters_apart("yepocapa", "yepocapa") == 0
    assert letters_apart("apo", "ago") == 1
    assert letters_apart("abc", "cba") == 2
    assert letters_apart("davao", "davao del sur") == 2
    assert letters_apart("kitten", "sitting") == 2  # three edits, capped
    # Long keys: the count stays exact within the cap's band.
    assert letters_apart("a" * 3000, "a" * 2999 + "b") == 1
    assert letters_apart("x" + "a" * 3000, "a" * 3000) == 1
    assert letters_apart("ab" * 1500, "ba" * 1500) == 2


@pytest.mark.parametrize(
    ("name", "full"),
    [
        ("Chimaltenago", True),
        ("Mt. McKinley", True),
        ("Davao Prov.", True),
        ("Guatemala.", True),
        ("GUATEMALA", True),
        ("PERU", True),
        ("Davao del Norte", True),
        ("P.I.", False),
        ("PH", False),
        ("PHL", False),
        ("RP", False),
        ("Phil.", False),
        ("Phil. Is.", False),
        ("Km 20", False),
        ("APO", False),
        ("Mt.", False),
        ("Mount", False),
        ("-", False),
        ("", False),
    ],
)
def test_full_names_exclude_codes_and_abbreviations(name, full):
    assert is_full_name(name) is full


def test_the_one_letter_gate_compares_full_names_only():
    assert one_letter_apart("Chimaltenago", "Chimaltenango")
    assert one_letter_apart("Chimaltenago", "Departamento de Chimaltenango")
    assert one_letter_apart("Mt. Apo", "Mount Ago")
    assert not one_letter_apart("P.I.", "P.R.")
    assert not one_letter_apart("PI", "PH")
    assert not one_letter_apart("Yepocapa", "Yepocapa")
    assert not one_letter_apart("Mt. Apo", "Mount Apo")
    assert not one_letter_apart("Talomo", "Davao")


def test_variants_keep_each_readers_literal():
    split = variants([("Chimaltenango", "obs-qwen"), ("Chimaltenago", "obs-muse")])
    assert [(v.keys, v.observations, v.literals) for v in split] == [
        (("chimaltenango",), ("obs-qwen",), ("Chimaltenango",)),
        (("chimaltenago",), ("obs-muse",), ("Chimaltenago",)),
    ]
    same = variants([("Davao Prov.", "a"), ("Davao, Prov.", "b"), ("Davao Province", "c")])
    assert [(v.keys, v.observations, v.literals) for v in same] == [
        (("davao",), ("a", "b", "c"), ("Davao Prov.", "Davao, Prov.", "Davao Province")),
    ]
    assert [reading.verbatim for reading in same[0].localities] == [
        "Davao Prov.",
        "Davao, Prov.",
        "Davao Province",
    ]
    assert variants([("", "empty")])[0].keys == ()


def test_variants_keep_each_readers_own_reading():
    (variant,) = variants(
        [
            ("5 km NE of Yepocapa", "obs-a"),
            ("5 km SW of Yepocapa, 4800 ft.", "obs-b"),
            ("Yepocapa, 1463 m", "obs-c"),
        ]
    )
    assert (variant.keys, variant.observations) == (("yepocapa",), ("obs-a", "obs-b", "obs-c"))
    headings = [
        reading.parts[0].heading.text if reading.parts[0].heading else None
        for reading in variant.localities
    ]
    assert headings == ["NE", "SW", None]
    assert [tuple(e.text for e in reading.elevations) for reading in variant.localities] == [
        (),
        ("4800 ft.",),
        ("1463 m",),
    ]
