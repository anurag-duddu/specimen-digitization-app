"""Reading locality text for the retrospective georeferencing tool (GEO.md 1)."""

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
    ],
)
def test_offsets_keep_distance_and_heading(text, distance, unit, heading, bearing, name):
    reading = read_locality(text)
    (part,) = reading.parts
    assert (part.relation, part.distance, part.distance_unit) == ("offset", distance, unit)
    assert (part.heading.text, part.heading.degrees, part.name) == (heading, bearing, name)
    assert reading.elevations == ()


@pytest.mark.parametrize(
    ("text", "written", "low", "high", "unit"),
    [
        ("Yepocapa, 1,463 m", "1,463 m", "1,463", None, "m"),
        ("Yepocapa, 4000-4500 ft", "4000-4500 ft", "4000", "4500", "ft"),
        ("Yepocapa, Elev. 6400'", "Elev. 6400'", "6400", None, "ft"),
        ("Yepocapa, alt. 1500 m", "alt. 1500 m", "1500", None, "m"),
        ("Mt. McKinley 6400'", "6400'", "6400", None, "ft"),
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


def test_fold_and_comparison_keys():
    assert fold("Chimaltenángo,") == "chimaltenango"
    assert fold("P.I.") == "p i"
    assert fold("Davao-del-Norte") == "davao del norte"
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
    assert same[0].locality.verbatim == "Davao Prov."
    assert variants([("", "empty")])[0].keys == ()
