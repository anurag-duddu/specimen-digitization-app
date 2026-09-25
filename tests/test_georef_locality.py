"""Reading locality text for the retrospective georeferencing tool (GEO.md 1)."""

import itertools
import time

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


@pytest.mark.parametrize(("text", "count"), [("4 800 ft. " * 20000, 0), ("1 m " * 20000, 20000)])
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


# Every date form the module reads, by separator and month form, with the pilot's
# two-digit and apostrophe years ("IV-26", "3 Sept. '46").
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
    ],
)
def test_a_range_never_reads_its_top_alone(text):
    reading = read_locality(text)
    assert (reading.elevations, reading.parts, reading.unplaced) == ((), (), (text,))


def test_a_number_after_another_number_and_one_word_is_set_aside():
    # The word may join a range no table lists, so "Camp 3 at 1500 m" costs its
    # elevation too. Right after another elevation a number is its pair.
    reading = read_locality("Camp 3 at 1500 m")
    assert (reading.elevations, reading.unplaced) == ((), ("Camp 3 at 1500 m",))
    for text in ("4800 ft 1463 m", "4800 ft/1463 m", "1500 m and 2000 m"):
        assert len(read_locality(text).elevations) == 2


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
