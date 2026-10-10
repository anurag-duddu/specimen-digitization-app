"""Field model v2: part names, groups, basis and the v1 mirror adapter.

The design is the PRD section "Field model v2: four groups". The module under
test is additive and pure; nothing imports it yet.
"""

import ast
import itertools
import json
import subprocess
import sys
from decimal import ROUND_DOWN, Decimal, localcontext
from pathlib import Path

import pytest

from specimen_digitization.application import field_model
from specimen_digitization.application.field_model import (
    BASES,
    COLLECTORS_JOINER,
    METRES_PER_FOOT,
    V1_KEYS,
    V1_SOURCES,
    VALUE_GROUP,
    VALUE_SPECS,
    Basis,
    FieldModelError,
    Group,
    PartPath,
    ValueName,
    display_basis,
    format_part_path,
    group_of,
    parse_part_path,
    v1_mirror,
)

PILOT = json.loads(
    (Path(__file__).parent / "fixtures" / "field_model_pilot_rows.json").read_text()
)
ROWS = {row["subject"]: row for row in PILOT["rows"]}

# Never filled by the mirror, whatever the parts hold.
NEVER_FILLED = {"verbatim_dts", "identified_by_irn"}


# --- part paths ---------------------------------------------------------------

VALID_PATHS = {
    "ids/catalog_number": PartPath(ValueName.IDS, "catalog_number"),
    "ids/collection": PartPath(ValueName.IDS, "collection"),
    "location/verbatim": PartPath(ValueName.LOCATION, "verbatim"),
    "location/country": PartPath(ValueName.LOCATION, "country"),
    "location/island": PartPath(ValueName.LOCATION, "island"),
    "location/department": PartPath(ValueName.LOCATION, "department"),
    "location/place": PartPath(ValueName.LOCATION, "place"),
    "location/place/2": PartPath(ValueName.LOCATION, "place", 2),
    "location/place/13": PartPath(ValueName.LOCATION, "place", 13),
    "location/named_place": PartPath(ValueName.LOCATION, "named_place"),
    "elevation/from": PartPath(ValueName.ELEVATION, "from"),
    "elevation/to": PartPath(ValueName.ELEVATION, "to"),
    "elevation/unit": PartPath(ValueName.ELEVATION, "unit"),
    "elevation/kind": PartPath(ValueName.ELEVATION, "kind"),
    "collectors/1": PartPath(ValueName.COLLECTORS, None, 1),
    "collectors/12": PartPath(ValueName.COLLECTORS, None, 12),
    "habitat/text": PartPath(ValueName.HABITAT, "text"),
    "collection_method/text": PartPath(ValueName.COLLECTION_METHOD, "text"),
    "when/collected/start": PartPath(ValueName.WHEN, "collected/start"),
    "when/collected/end": PartPath(ValueName.WHEN, "collected/end"),
    "when/collected/time": PartPath(ValueName.WHEN, "collected/time"),
    "when/identified/start": PartPath(ValueName.WHEN, "identified/start"),
    "taxon/name": PartPath(ValueName.TAXON, "name"),
    "taxon/accepted": PartPath(ValueName.TAXON, "accepted"),
    "taxon/rank": PartPath(ValueName.TAXON, "rank"),
    "taxon/authorship": PartPath(ValueName.TAXON, "authorship"),
    "taxon/status": PartPath(ValueName.TAXON, "status"),
    "identified_by/1": PartPath(ValueName.IDENTIFIED_BY, None, 1),
}

INVALID_PATHS = [
    "",
    "location",
    "location/",
    "/country",
    "ids",
    "ids/",
    "ids/unknown",
    "ids/catalog_number/2",
    "ids/catalogue_number",  # the British spelling is not a part; the part is catalog_number
    "country/name",  # a v1 key, not a value
    "collection/ids",  # a group, not a value: the first segment is the value
    "Location/country",
    "location/Country",
    "location/country ",
    " location/country",
    "location/country name",
    "location//country",
    "location/country/",
    "location/place/1",  # the first node has no index
    "location/place/0",
    "location/place/02",
    "location/place/-2",
    "location/place/+2",
    "location/place/two",
    "location/place/2/3",
    "location/place/1000000",
    "location/verbatim/2",  # the root takes no index
    "location/1country",
    "location/_country",
    "location/country_",
    "location/co__untry",
    "location/pläce",
    "collectors",
    "collectors/",
    "collectors/0",
    "collectors/01",
    "collectors/a",
    "collectors/1/2",
    "collectors/name",
    "identified_by/0",
    "elevation/from/2",
    "elevation/uncertainty",
    "elevation/",
    "habitat/habitat",
    "habitat",
    "when/start",  # a short form that is not a part; the parts are when/collected/... and when/identified/...
    "when/collected",
    "when/collected/",
    "when/collected/start/2",
    "when/collected/duration",
    "when/identified/end",
    "taxon/resolved",  # not a part; the parts are accepted, rank, authorship, status
    "taxon/accepted/2",
]


@pytest.mark.parametrize("path", sorted(VALID_PATHS))
def test_valid_part_paths_parse_and_round_trip(path):
    parsed = parse_part_path(path)
    assert parsed == VALID_PATHS[path]
    assert parsed.path == path == str(parsed)
    assert parse_part_path(parsed.path) == parsed


@pytest.mark.parametrize("path", INVALID_PATHS)
def test_invalid_part_paths_are_refused(path):
    with pytest.raises(FieldModelError):
        parse_part_path(path)


@pytest.mark.parametrize("path", [None, 3, b"ids/collection", ("ids", "collection"), 1.5])
def test_a_part_path_must_be_text(path):
    with pytest.raises(FieldModelError):
        parse_part_path(path)


def test_the_field_model_error_is_a_value_error():
    assert issubclass(FieldModelError, ValueError)


def test_unknown_value_names_the_value_in_the_message():
    with pytest.raises(FieldModelError, match="unknown value 'bogus'"):
        parse_part_path("bogus/part")


def test_format_builds_the_canonical_path():
    assert format_part_path("location", "place", index=2) == "location/place/2"
    assert format_part_path("location", "country") == "location/country"
    assert format_part_path("collectors", index=1) == "collectors/1"
    assert format_part_path("identified_by", index=3) == "identified_by/3"
    assert format_part_path("when", "collected/start") == "when/collected/start"
    assert format_part_path("elevation", "unit") == "elevation/unit"
    assert format_part_path(ValueName.TAXON, "accepted") == "taxon/accepted"


@pytest.mark.parametrize(
    "call",
    [
        lambda: format_part_path("bogus", "x"),
        lambda: format_part_path("location"),
        lambda: format_part_path("location", "place", index=1),
        lambda: format_part_path("location", "place", index=0),
        lambda: format_part_path("location", "place", index="2"),
        lambda: format_part_path("location", "verbatim", index=2),
        lambda: format_part_path("collectors"),
        lambda: format_part_path("collectors", index=0),
        lambda: format_part_path("collectors", index=-1),
        lambda: format_part_path("collectors", index=True),
        lambda: format_part_path("collectors", index=1.0),
        lambda: format_part_path("collectors", "name", index=1),
        lambda: format_part_path("habitat", "text", index=2),
        lambda: format_part_path("ids", "nope"),
        lambda: format_part_path("when", "collected"),
        lambda: format_part_path("when", ""),
    ],
)
def test_format_refuses_what_the_parser_refuses(call):
    with pytest.raises(FieldModelError):
        call()


def test_every_valid_path_formats_from_its_parts():
    for path, parsed in VALID_PATHS.items():
        assert format_part_path(parsed.value, parsed.part, index=parsed.index) == path


# --- the nine values and their groups -----------------------------------------

EXPECTED_GROUPS = {
    "ids": Group.IDS,
    "location": Group.COLLECTION,
    "elevation": Group.COLLECTION,
    "collectors": Group.COLLECTION,
    "habitat": Group.COLLECTION,
    "collection_method": Group.COLLECTION,
    "when": Group.DATE,
    "taxon": Group.TAXA,
    "identified_by": Group.TAXA,
}


def test_there_are_nine_values_in_four_groups():
    assert {value.value for value in ValueName} == set(EXPECTED_GROUPS)
    assert len(ValueName) == 9
    assert {group.value for group in Group} == {"ids", "collection", "date", "taxa"}
    assert set(VALUE_SPECS) == set(ValueName) == set(VALUE_GROUP)


@pytest.mark.parametrize("value", sorted(EXPECTED_GROUPS))
def test_group_of_each_value(value):
    assert group_of(value) == EXPECTED_GROUPS[value]
    assert group_of(ValueName(value)) == EXPECTED_GROUPS[value]
    assert VALUE_GROUP[ValueName(value)] == EXPECTED_GROUPS[value]
    assert VALUE_SPECS[ValueName(value)].group == EXPECTED_GROUPS[value]


@pytest.mark.parametrize("name", ["", "country", "collection", "date", "taxa", "Location", "when/collected"])
def test_group_of_refuses_anything_that_is_not_a_value(name):
    with pytest.raises(FieldModelError):
        group_of(name)


def test_a_part_knows_its_group():
    assert parse_part_path("when/identified/start").group == Group.DATE
    assert parse_part_path("identified_by/1").group == Group.TAXA
    assert parse_part_path("ids/collection").group == Group.IDS
    assert parse_part_path("elevation/unit").group == Group.COLLECTION


def test_the_part_names_of_each_fixed_value():
    parts = {name.value: spec.parts for name, spec in VALUE_SPECS.items()}
    assert parts["ids"] == ("catalog_number", "collection")
    assert parts["elevation"] == ("from", "to", "unit", "kind")
    assert parts["habitat"] == ("text",)
    assert parts["collection_method"] == ("text",)
    assert parts["when"] == (
        "collected/start",
        "collected/end",
        "collected/time",
        "identified/start",
    )
    assert parts["taxon"] == ("name", "accepted", "rank", "authorship", "status")
    assert parts["location"] == ("verbatim",)  # the root; every other part is a level
    assert parts["collectors"] == parts["identified_by"] == ()  # numbered entries


def test_every_fixed_part_parses():
    for name, spec in VALUE_SPECS.items():
        if spec.shape == "fixed":
            for part in spec.parts:
                assert parse_part_path(f"{name.value}/{part}").part == part


# --- basis --------------------------------------------------------------------


def test_the_basis_vocabulary():
    assert [basis.value for basis in BASES] == ["label", "derived", "inferred"]
    assert {basis.value for basis in Basis} == {"label", "derived", "inferred"}
    assert Basis("label") is Basis.LABEL
    assert Basis.LABEL == "label"


@pytest.mark.parametrize(
    ("layer", "literal", "parsed", "normalized", "expected"),
    [
        # "P.I." settled as the Philippines: the values differ.
        ("settled", "P.I.", None, "Philippines", Basis.DERIVED),
        # A written foot mark parsed as a plain number: the same once the mark is ignored.
        ("settled", "6400'", "6400", None, Basis.LABEL),
        # "Mindanao" confirmed by a lookup: literal and normalized agree.
        ("settled", "Mindanao", None, "Mindanao", Basis.LABEL),
        # The label misspells the department and a lookup settles the right one.
        ("settled", "Chimaltenago", None, "Chimaltenango", Basis.DERIVED),
        # Nothing stored: nothing shown.
        ("settled", None, None, None, None),
        # The layer decides the other two cases.
        ("verbatim", "E. slope Mt. McKinley", None, None, Basis.LABEL),
        ("verbatim", None, None, None, Basis.LABEL),
        ("derived", None, "1950.72", "1950.72", Basis.DERIVED),
        ("derived", "6400'", "1950.72", None, Basis.DERIVED),
        # Case, spacing and unit marks are ignored.
        ("settled", "MINDANAO", None, "mindanao", Basis.LABEL),
        ("settled", "Mt.  McKinley", None, "Mt. McKinley", Basis.LABEL),
        ("settled", "Mt.McKinley", None, "Mt. McKinley", Basis.LABEL),
        ("settled", "6400 ft.", "6400", None, Basis.LABEL),
        ("settled", "6400 ft", None, "6400", Basis.LABEL),
        ("settled", "6400 feet", "6400", "6400", Basis.LABEL),
        ("settled", "1950.72 m", "1950.72", None, Basis.LABEL),
        ("settled", "1950.72 m.", "1950.72", None, Basis.LABEL),
        ("settled", "6400′", "6400", None, Basis.LABEL),
        ("settled", "6400’", "6400", None, Basis.LABEL),
        # A mark that is not a unit still differs.
        ("settled", "6400'", "6401", None, Basis.DERIVED),
        ("settled", "6400 ft", "1950.72", None, Basis.DERIVED),
        # A plain number is compared by value: live display_decimal writes "6400.00"
        # for a written "6400'", and a trailing zero after the point is no difference.
        ("settled", "6400'", "6400", "6400.00", Basis.LABEL),
        ("settled", "1950.7 m", "1950.7", "1950.70", Basis.LABEL),
        ("settled", "6400'", None, "6400.00", Basis.LABEL),
        ("settled", "6400.0", "6400", "6400.00", Basis.LABEL),
        ("settled", "1950.72 m", "1950.72", "1950.720", Basis.LABEL),
        ("settled", "0.50 m", "0.5", None, Basis.LABEL),
        ("settled", "-0", "0", None, Basis.LABEL),
        # ...but a different value still differs, and leading zeros are not trailing zeros.
        ("settled", "1950.72 m", "1950.7248", "1950.72", Basis.DERIVED),
        ("settled", "6400'", "6400", "6400.50", Basis.DERIVED),
        ("settled", "6400'", "640", "6400.00", Basis.DERIVED),
        ("settled", "0012345", "12345", None, Basis.DERIVED),
        ("settled", "0012345", "0012345", None, Basis.LABEL),
        # A Roman-numeral date settled as an ISO date.
        ("settled", "IX-14-46", "1946-09-14", "1946-09-14", Basis.DERIVED),
        ("settled", "3 Sept. '46", "1946-09-03", None, Basis.DERIVED),
        # An "m" inside a word is not a unit mark.
        ("settled", "5 mile", None, "5 ile", Basis.DERIVED),
        # Three values: all must agree.
        ("settled", "Mindanao", "Mindanao", "Mindanao", Basis.LABEL),
        ("settled", "Mindanao", "Mindanao", "Davao", Basis.DERIVED),
        ("settled", "Mindanao", "Davao", "Mindanao", Basis.DERIVED),
        # Cannot tell: one value alone says nothing about how it was obtained.
        ("settled", "Mindanao", None, None, None),
        ("settled", None, "1950.72", None, None),
        ("settled", None, None, "Philippines", None),
        # Cannot tell: two machine outputs that agree prove nothing about the wording.
        ("settled", None, "Philippines", "Philippines", None),
        # Empty text is absent text.
        ("settled", "", None, "Philippines", None),
        ("settled", "  ", "  ", None, None),
        ("settled", "Mindanao", "", "Mindanao", Basis.LABEL),
        # Differing machine outputs, with no literal, still show a transformation.
        ("settled", None, "1950.7248", "1950.72", Basis.DERIVED),
        # Not a layer the model knows: nothing shown.
        (None, "Mindanao", None, "Mindanao", None),
        ("", "Mindanao", None, "Mindanao", None),
        ("unknown", "Mindanao", None, "Mindanao", None),
        ("Settled", "Mindanao", None, "Mindanao", None),
    ],
)
def test_display_basis(layer, literal, parsed, normalized, expected):
    assert display_basis(layer, literal, parsed, normalized) is expected


def test_display_basis_is_never_inferred():
    texts = [None, "", "Mindanao", "mindanao", "Philippines", "6400'", "6400", "1950.72", "P.I."]
    layers = [None, "", "verbatim", "settled", "derived", "unknown"]
    seen = set()
    for layer, literal, parsed, normalized in itertools.product(layers, texts, texts, texts):
        seen.add(display_basis(layer, literal, parsed, normalized))
    assert Basis.INFERRED not in seen
    assert seen == {None, Basis.LABEL, Basis.DERIVED}


def test_display_basis_returns_basis_members_not_text():
    result = display_basis("verbatim", "x", None, None)
    assert isinstance(result, Basis)


def test_display_basis_agrees_with_what_live_display_decimal_writes():
    # parse_measurement("6400'") gives parsed "6400"; display_decimal always
    # writes two decimals, so the stored normalized text is "6400.00".
    from specimen_digitization.research_harness.evidence import display_decimal

    for written, number in (("6400'", "6400"), ("1950.7 m", "1950.7"), ("3300 ft", "3300")):
        normalized = display_decimal(Decimal(number))
        assert normalized != number  # the stored texts really do differ
        assert display_basis("settled", written, number, normalized) is Basis.LABEL
    # A rounded conversion is a different value from the stated one.
    assert display_basis("settled", "1950.7248 m", "1950.7248", display_decimal(Decimal("1950.7248"))) is (
        Basis.DERIVED
    )


def test_display_basis_does_not_depend_on_the_ambient_decimal_context():
    long_number = "1" * 39 + ".5"
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_DOWN
        assert display_basis("settled", "6400'", "6400", "6400.00") is Basis.LABEL
        assert display_basis("settled", long_number, None, long_number + "0") is Basis.LABEL
        assert display_basis("settled", long_number, None, "1" * 39 + ".6") is Basis.DERIVED


@pytest.mark.parametrize("bad", [3, 1.5, b"x", ["x"], Decimal("1")])
def test_display_basis_refuses_non_text_values(bad):
    with pytest.raises(FieldModelError):
        display_basis("settled", bad, None, "x")
    with pytest.raises(FieldModelError):
        display_basis("settled", None, bad, "x")
    with pytest.raises(FieldModelError):
        display_basis("settled", "x", None, bad)


# --- the v1 mirror: the key set -----------------------------------------------


def test_v1_keys_are_the_twenty_native_keys_in_native_order():
    from specimen_digitization.application.domain import MANDATORY
    from specimen_digitization.research_harness.contracts import FieldKey

    assert len(V1_KEYS) == len(set(V1_KEYS)) == 20
    assert V1_KEYS == MANDATORY == tuple(key.value for key in FieldKey)


def test_every_v1_key_has_a_stated_source():
    assert tuple(V1_SOURCES) == V1_KEYS
    assert all(isinstance(text, str) and text for text in V1_SOURCES.values())
    assert V1_SOURCES["verbatim_dts"].startswith("never filled")
    assert V1_SOURCES["identified_by_irn"].startswith("never filled")


def test_the_conversion_factor_is_the_exact_definition():
    assert METRES_PER_FOOT == Decimal("0.3048")
    assert isinstance(METRES_PER_FOOT, Decimal)
    assert COLLECTORS_JOINER == " & "


def test_an_empty_mapping_fills_nothing():
    assert v1_mirror({}) == {}


def test_the_result_is_in_native_key_order_and_uses_only_native_keys():
    parts = {
        "when/identified/start": "1950",
        "collectors/1": "R.D. Mitchell",
        "taxon/accepted": "Epipsocus",
        "habitat/text": "cut branch trap",
        "location/verbatim": "Yepocapa",
        "ids/catalog_number": "4486776",
        "ids/collection": "FMNH-INS",
        "when/collected/start": "1948-04-23",
        "collection_method/text": "trap",
    }
    result = v1_mirror(parts)
    assert list(result) == [key for key in V1_KEYS if key in result]
    assert set(result) <= set(V1_KEYS)
    assert not NEVER_FILLED & set(result)
    assert result == {
        "fmnh_ins_number": "4486776",
        "collection_code": "FMNH-INS",
        "precise_location": "Yepocapa",
        "habitat": "cut branch trap",
        "collection_method": "trap",
        "date_visited_from": "1948-04-23",
        "date_visited_to": "1948-04-23",
        "collectors": "R.D. Mitchell",
        "taxon": "Epipsocus",
        "date_identified": "1950",
    }


def test_the_input_mapping_is_not_changed():
    parts = {"ids/catalog_number": "4486776", "when/collected/start": "1948-04-23"}
    before = dict(parts)
    v1_mirror(parts)
    assert parts == before


def test_unknown_and_malformed_paths_are_refused():
    for path in ("country", "location/place/1", "elevation/uncertainty", "collectors"):
        with pytest.raises(FieldModelError):
            v1_mirror({path: "x"})


# --- the v1 mirror: values copied as written ------------------------------------


def test_the_catalogue_number_is_text_with_leading_zeros_kept():
    assert v1_mirror({"ids/catalog_number": "0004486"}) == {"fmnh_ins_number": "0004486"}
    for number in (4486784, Decimal("4486784"), 4486784.0):
        with pytest.raises(FieldModelError):
            v1_mirror({"ids/catalog_number": number})


def test_the_catalogue_number_is_copied_unvalidated():
    # Live `catalog_literal` would return "4486784" for this literal; the adapter does
    # not apply it, so the caller must pass the digits.
    assert v1_mirror({"ids/catalog_number": "FMNH-INS 4486784"}) == {
        "fmnh_ins_number": "FMNH-INS 4486784"
    }
    assert v1_mirror({"ids/catalog_number": "4486784"}) == {"fmnh_ins_number": "4486784"}


def test_copied_parts():
    result = v1_mirror(
        {
            "ids/collection": "INS",
            "habitat/text": "Mossy forest",
            "collection_method/text": "Cut branch trap",
            "location/verbatim": "  E. slope\nMt. McKinley",
        }
    )
    assert result == {
        "collection_code": "INS",
        "precise_location": "  E. slope\nMt. McKinley",  # as read, never trimmed
        "habitat": "Mossy forest",
        "collection_method": "Cut branch trap",
    }


@pytest.mark.parametrize("path", ["ids/collection", "habitat/text", "location/verbatim", "taxon/accepted"])
@pytest.mark.parametrize("bad", ["", "   ", None, 3, Decimal("1"), b"x"])
def test_text_values_must_be_nonempty_text(path, bad):
    with pytest.raises(FieldModelError):
        v1_mirror({path: bad})


def test_taxon_fills_only_from_the_resolved_name():
    assert v1_mirror({"taxon/name": "Epipsocus sp."}) == {}
    only_extras = {
        "taxon/name": "Epipsocus sp.",
        "taxon/rank": "genus",
        "taxon/authorship": "Enderlein, 1903",
        "taxon/status": "accepted",
    }
    assert v1_mirror(only_extras) == {}
    assert v1_mirror({**only_extras, "taxon/accepted": "Epipsocus"}) == {"taxon": "Epipsocus"}


def test_identified_by_never_fills_the_irn():
    result = v1_mirror({"identified_by/1": "E. L. Mockford", "identified_by/2": "A. Person"})
    assert result == {}
    with pytest.raises(FieldModelError):
        v1_mirror({"identified_by/2": "A. Person"})  # entry 1 is missing


def test_verbatim_dts_is_never_filled():
    result = v1_mirror(
        {
            "when/collected/start": "1946-09-03",
            "when/collected/end": "1946-09-05",
            "when/collected/time": "sunrise",
            "when/identified/start": "1950",
        }
    )
    assert "verbatim_dts" not in result
    assert "identified_by_irn" not in result
    assert set(result) == {"date_visited_from", "date_visited_to", "date_identified"}


# --- the v1 mirror: the place tree, by role ---------------------------------------


def test_philippine_island_has_no_mirror_and_province_is_first_administrative_level():
    result = v1_mirror(
        {
            "location/country": "Philippines",
            "location/island": "Mindanao",
            "location/province": "Davao",
            "location/place": "E. slope Mt. McKinley",
            "location/place/2": "Mt. Talomo",
        }
    )
    assert result == {"country": "Philippines", "province_state": "Davao"}


@pytest.mark.parametrize("level", ["province", "state", "department", "prefecture"])
def test_first_administrative_levels_fill_province_state(level):
    assert v1_mirror({f"location/{level}": "X"}) == {"province_state": "X"}


@pytest.mark.parametrize("level", ["county", "district"])
def test_second_administrative_levels_fill_county(level):
    assert v1_mirror({f"location/{level}": "X"}) == {"county": "X"}


@pytest.mark.parametrize("level", ["city", "town", "village", "settlement"])
def test_settlement_levels_fill_city(level):
    assert v1_mirror({f"location/{level}": "X"}) == {"city": "X"}


def test_a_united_states_tree_fills_every_place_key():
    result = v1_mirror(
        {
            "location/verbatim": "Chicago, Cook Co., Ill.",
            "location/country": "United States",
            "location/state": "Illinois",
            "location/county": "Cook",
            "location/city": "Chicago",
        }
    )
    assert result == {
        "country": "United States",
        "province_state": "Illinois",
        "county": "Cook",
        "city": "Chicago",
        "precise_location": "Chicago, Cook Co., Ill.",
    }


def test_a_municipality_is_not_a_county_and_no_county_is_invented():
    result = v1_mirror(
        {
            "location/country": "Guatemala",
            "location/department": "Chimaltenango",
            "location/municipality": "Yepocapa",
        }
    )
    assert result == {"country": "Guatemala", "province_state": "Chimaltenango"}
    assert "county" not in result
    assert "city" not in result


def test_levels_outside_the_roles_live_only_in_the_tree():
    result = v1_mirror(
        {
            "location/island": "Mindanao",
            "location/subregion": "East",
            "location/place": "Mt. Apo",
            "location/place/2": "East slope",
            "location/municipality": "Yepocapa",
        }
    )
    assert result == {}


@pytest.mark.parametrize(
    "parts",
    [
        {"location/province": "Davao", "location/state": "Mindanao"},
        {"location/department": "A", "location/province": "B"},
        {"location/county": "A", "location/district": "B"},
        {"location/city": "A", "location/town": "B"},
        {"location/city": "A", "location/city/2": "B"},
        {"location/country": "A", "location/country/2": "B"},
    ],
)
def test_two_nodes_in_one_role_are_not_guessed_between(parts):
    with pytest.raises(FieldModelError, match="more than one"):
        v1_mirror(parts)


def test_a_role_is_chosen_by_level_not_by_name():
    # A province called "Cook" is a province; a county called "Illinois" is a county.
    assert v1_mirror({"location/province": "Cook", "location/county": "Illinois"}) == {
        "province_state": "Cook",
        "county": "Illinois",
    }


# --- the v1 mirror: elevation ---------------------------------------------------


def elevation(kind, unit, low=None, high=None):
    parts = {"elevation/kind": kind}
    if unit is not None:
        parts["elevation/unit"] = unit
    if low is not None:
        parts["elevation/from"] = low
    if high is not None:
        parts["elevation/to"] = high
    return v1_mirror(parts)


def test_a_point_stated_in_feet_fills_both_bounds_alike():
    assert elevation("point", "ft", "1950.72") == {
        "elevation_from_m": "1950.72",
        "elevation_to_m": "1950.72",
        "elevation_from_ft": "6400",
        "elevation_to_ft": "6400",
    }


def test_a_point_stated_in_metres_fills_both_bounds_alike():
    assert elevation("point", "m", "1950") == {
        "elevation_from_m": "1950",
        "elevation_to_m": "1950",
        "elevation_from_ft": "6397.64",
        "elevation_to_ft": "6397.64",
    }


def test_a_range_fills_its_two_bounds():
    assert elevation("range", "m", "1000", "1500") == {
        "elevation_from_m": "1000",
        "elevation_to_m": "1500",
        "elevation_from_ft": "3280.84",
        "elevation_to_ft": "4921.26",
    }
    assert elevation("range", "ft", "914.4", "1219.2") == {
        "elevation_from_m": "914.4",
        "elevation_to_m": "1219.2",
        "elevation_from_ft": "3000",
        "elevation_to_ft": "4000",
    }


def test_an_equal_range_is_allowed_and_a_reversed_one_is_not():
    assert elevation("range", "m", "100", "100")["elevation_to_m"] == "100"
    with pytest.raises(FieldModelError, match="above elevation/to"):
        elevation("range", "m", "1500", "1000")


def test_an_above_limit_fills_only_the_lower_bound():
    result = elevation("above", "m", "2000")
    assert result == {"elevation_from_m": "2000", "elevation_from_ft": "6561.68"}
    assert not any(key.startswith("elevation_to") for key in result)


def test_a_below_limit_fills_only_the_upper_bound():
    result = elevation("below", "ft", None, "304.8")
    assert result == {"elevation_to_ft": "1000", "elevation_to_m": "304.8"}
    assert not any(key.startswith("elevation_from") for key in result)


def test_elevation_numbers_with_no_unit_fill_nothing():
    assert elevation("point", None, "1950.72") == {}
    assert elevation("range", None, "1", "2") == {}
    # The rest of the record is unaffected.
    assert v1_mirror(
        {"elevation/kind": "point", "elevation/from": "5", "location/country": "Peru"}
    ) == {"country": "Peru"}


POINT_IN_FEET = {
    "location/country": "Philippines",
    "elevation/kind": "point",
    "elevation/from": "1950.72",
    "elevation/unit": "ft",
}


def test_an_inferred_unit_withholds_the_whole_elevation():
    as_given = v1_mirror(POINT_IN_FEET)
    assert as_given["elevation_from_m"] == "1950.72"
    for bases in ({"elevation/unit": "inferred"}, {"elevation/unit": Basis.INFERRED}):
        assert v1_mirror(POINT_IN_FEET, bases=bases) == {"country": "Philippines"}


def test_other_bases_are_ignored():
    as_given = v1_mirror(POINT_IN_FEET)
    for basis in ("label", "derived"):
        assert v1_mirror(POINT_IN_FEET, bases={"elevation/unit": basis}) == as_given
    assert v1_mirror(POINT_IN_FEET, bases={"elevation/from": "inferred"}) == as_given
    assert v1_mirror(POINT_IN_FEET, bases={"location/country": "inferred"}) == as_given
    assert v1_mirror(POINT_IN_FEET, bases={}) == v1_mirror(POINT_IN_FEET, bases=None) == as_given


@pytest.mark.parametrize(
    "bases",
    [
        {"elevation/unit": "guess"},
        {"elevation/unit": None},
        {"elevation/unit": "Inferred"},
        {"habitat/text": "label"},  # not among the parts
        {"elevation/uncertainty": "label"},  # not a part at all
        {"elevation": "label"},
    ],
)
def test_bases_must_name_parts_and_bases_exactly(bases):
    with pytest.raises(FieldModelError):
        v1_mirror(POINT_IN_FEET, bases=bases)


def test_an_inferred_unit_still_validates_the_elevation():
    bad = {**POINT_IN_FEET, "elevation/kind": "box"}
    with pytest.raises(FieldModelError):
        v1_mirror(bad, bases={"elevation/unit": "inferred"})


def test_a_unit_alone_fills_nothing():
    assert v1_mirror({"elevation/unit": "ft"}) == {}


@pytest.mark.parametrize(
    "parts",
    [
        {"elevation/from": "5", "elevation/unit": "m"},  # no kind
        {"elevation/to": "5", "elevation/unit": "m"},
        {"elevation/kind": "point", "elevation/unit": "m"},  # no number
        {"elevation/kind": "point", "elevation/from": "5", "elevation/to": "5", "elevation/unit": "m"},
        {"elevation/kind": "point", "elevation/to": "5", "elevation/unit": "m"},
        {"elevation/kind": "range", "elevation/from": "5", "elevation/unit": "m"},
        {"elevation/kind": "range", "elevation/to": "5", "elevation/unit": "m"},
        {"elevation/kind": "above", "elevation/to": "5", "elevation/unit": "m"},
        {"elevation/kind": "above", "elevation/from": "5", "elevation/to": "9", "elevation/unit": "m"},
        {"elevation/kind": "below", "elevation/from": "5", "elevation/unit": "m"},
        {"elevation/kind": "below", "elevation/from": "5", "elevation/to": "9", "elevation/unit": "m"},
        {"elevation/kind": "box", "elevation/from": "5", "elevation/unit": "m"},
        {"elevation/kind": "Point", "elevation/from": "5", "elevation/unit": "m"},
        {"elevation/kind": "point", "elevation/from": "5", "elevation/unit": "yd"},
        {"elevation/kind": "point", "elevation/from": "5", "elevation/unit": "feet"},
        {"elevation/kind": "point", "elevation/from": "5", "elevation/unit": "FT"},
        {"elevation/kind": "point", "elevation/from": "5", "elevation/unit": ""},
        {"elevation/kind": "point", "elevation/from": "5", "elevation/unit": None},
    ],
)
def test_malformed_elevations_are_refused(parts):
    with pytest.raises(FieldModelError):
        v1_mirror(parts)


@pytest.mark.parametrize(
    "number",
    [1950.72, True, False, None, "", " 5", "5 ", "5m", "1e3", "1E3", "0x10", "abc", "NaN", "Infinity",
     "1,000", ".5", "5.", "--5", "+-5", "1" * 41, "1." + "1" * 21, Decimal("NaN"), Decimal("Infinity"), [5]],
)
def test_an_elevation_number_is_exact_decimal_never_float(number):
    with pytest.raises(FieldModelError):
        v1_mirror({"elevation/kind": "point", "elevation/unit": "m", "elevation/from": number})


@pytest.mark.parametrize("number", ["5", "-5", "+5", "0", "0.0", "5.25", "007", 5, Decimal("5.25"), Decimal("1E+3")])
def test_an_elevation_number_may_be_text_int_or_decimal(number):
    assert v1_mirror({"elevation/kind": "point", "elevation/unit": "m", "elevation/from": number})


def test_a_below_sea_level_elevation_and_zero():
    assert elevation("point", "m", "-10") == {
        "elevation_from_m": "-10",
        "elevation_to_m": "-10",
        "elevation_from_ft": "-32.81",
        "elevation_to_ft": "-32.81",
    }
    assert elevation("point", "m", "0") == {
        "elevation_from_m": "0",
        "elevation_to_m": "0",
        "elevation_from_ft": "0",
        "elevation_to_ft": "0",
    }
    assert elevation("point", "m", "-0.001")["elevation_from_ft"] == "0"  # no negative zero


def test_int_and_decimal_inputs_match_text_input():
    from_text = elevation("point", "ft", "1950.72")
    assert elevation("point", "ft", Decimal("1950.72")) == from_text
    assert elevation("point", "m", 1950) == elevation("point", "m", "1950")
    assert elevation("point", "m", Decimal("1950.00")) == elevation("point", "m", "1950")


def test_a_written_number_is_kept_as_stated_in_its_own_unit():
    # 6400.5 ft is 1950.8724 m exactly: feet come back as stated, metres to 0.01.
    assert elevation("point", "ft", "1950.8724") == {
        "elevation_from_m": "1950.87",
        "elevation_to_m": "1950.87",
        "elevation_from_ft": "6400.5",
        "elevation_to_ft": "6400.5",
    }
    # 3.3 ft is exactly 1.00584 m.
    assert elevation("point", "ft", "1.00584")["elevation_from_ft"] == "3.3"
    # In metres the stated number keeps every digit it was given, minus trailing zeros.
    assert elevation("point", "m", "1950.7200")["elevation_from_m"] == "1950.72"
    assert elevation("point", "m", "1950.123456")["elevation_from_m"] == "1950.123456"


def test_a_converted_value_is_rounded_to_a_hundredth_half_even():
    # The converted metres of a feet-stated elevation: a tie goes to the even hundredth.
    assert elevation("point", "ft", "1.005")["elevation_from_m"] == "1"  # 1.00
    assert elevation("point", "ft", "1.015")["elevation_from_m"] == "1.02"
    assert elevation("point", "ft", "1.025")["elevation_from_m"] == "1.02"
    assert elevation("point", "ft", "1.035")["elevation_from_m"] == "1.04"
    # Feet that are not finite are rounded too, never carried at 34 digits.
    assert elevation("point", "ft", "1.005")["elevation_from_ft"] == "3.3"
    # Feet converted from a metre-stated elevation.
    assert elevation("point", "m", "1")["elevation_from_ft"] == "3.28"
    assert elevation("point", "m", "0.3048")["elevation_from_ft"] == "1"
    assert elevation("point", "m", "1.5")["elevation_from_ft"] == "4.92"
    assert elevation("point", "m", "1000")["elevation_from_ft"] == "3280.84"


def test_the_conversions_agree_with_exact_decimal_arithmetic():
    for metres in ("0.01", "1", "37.5", "913.44", "1000", "1950.72", "2954", "8848.86"):
        exact = Decimal(metres) / Decimal("0.3048")
        expected = str(exact.quantize(Decimal("0.01"))).rstrip("0").rstrip(".")
        assert elevation("point", "m", metres)["elevation_from_ft"] == expected
    for feet in ("1", "3300", "4800", "6400", "6400.5", "29031.7"):
        metres = str(Decimal(feet) * Decimal("0.3048"))
        result = elevation("point", "ft", metres)
        assert result["elevation_from_ft"] == feet
        quantized = (Decimal(feet) * Decimal("0.3048")).quantize(Decimal("0.01"))
        assert result["elevation_from_m"] == str(quantized).rstrip("0").rstrip(".")


def test_elevation_text_differs_from_display_decimal_only_in_trailing_zeros():
    from specimen_digitization.research_harness.evidence import display_decimal

    # 1000 ft is 304.8 m: derivations.py _text writes "304.8", display_decimal "304.80".
    result = elevation("point", "ft", "304.8")
    live = display_decimal(Decimal("304.8"))
    assert result["elevation_from_m"] == "304.8"
    assert live == "304.80" != result["elevation_from_m"]
    assert Decimal(live) == Decimal(result["elevation_from_m"])
    for feet in ("1", "10", "1000", "3300", "4800", "6400", "6400.5", "29031.7"):
        metres = Decimal(feet) * Decimal("0.3048")
        mirrored = elevation("point", "ft", str(metres))["elevation_from_m"]
        assert Decimal(mirrored) == Decimal(display_decimal(metres))


def test_no_float_drift():
    # Values whose float arithmetic drifts come out exact as Decimal text.
    drifting = [
        x for x in range(1, 20000) if Decimal(repr(x * 0.3048)) != Decimal(x) * Decimal("0.3048")
    ]
    assert drifting, "the guard needs at least one value where float arithmetic drifts"
    for feet in drifting[:200]:
        exact = Decimal(feet) * Decimal("0.3048")
        result = elevation("point", "ft", str(exact))
        assert result["elevation_from_ft"] == str(feet)
        assert Decimal(result["elevation_from_m"]) == exact.quantize(Decimal("0.01"))
        assert all("e" not in value.lower() for value in result.values())


def test_the_result_does_not_depend_on_the_ambient_decimal_context():
    expected = elevation("point", "m", "1500")
    with localcontext() as context:
        context.prec = 5
        context.rounding = ROUND_DOWN
        assert elevation("point", "m", "1500") == expected
        assert elevation("point", "ft", "1.005") == {
            "elevation_from_m": "1",
            "elevation_to_m": "1",
            "elevation_from_ft": "3.3",
            "elevation_to_ft": "3.3",
        }


def test_elevation_values_are_plain_decimal_text():
    result = elevation("range", "m", "0.0000001", "123456789012345678901234567890")
    for value in result.values():
        assert isinstance(value, str)
        assert "e" not in value.lower()
        assert not value.endswith(".")
        assert "." not in value or not value.endswith("0")


# --- the v1 mirror: dates ---------------------------------------------------------


def dates(**parts):
    return v1_mirror({f"when/{key.replace('__', '/')}": value for key, value in parts.items()})


def test_a_single_collecting_date_fills_both_ends_at_the_written_precision():
    assert dates(collected__start="1946-09-03") == {
        "date_visited_from": "1946-09-03",
        "date_visited_to": "1946-09-03",
    }
    assert dates(collected__start="1946-11") == {
        "date_visited_from": "1946-11",
        "date_visited_to": "1946-11",
    }
    assert dates(collected__start="1946") == {
        "date_visited_from": "1946",
        "date_visited_to": "1946",
    }


def test_a_collecting_range_fills_its_ends():
    assert dates(collected__start="1946-09-03", collected__end="1946-09-06") == {
        "date_visited_from": "1946-09-03",
        "date_visited_to": "1946-09-06",
    }
    assert dates(collected__start="1946-08", collected__end="1946-09-03") == {
        "date_visited_from": "1946-08",
        "date_visited_to": "1946-09-03",
    }
    assert dates(collected__start="1946-03-01", collected__end="1946-03-01") == {
        "date_visited_from": "1946-03-01",
        "date_visited_to": "1946-03-01",
    }


def test_an_end_alone_fills_only_the_end():
    assert dates(collected__end="1946-09-06") == {"date_visited_to": "1946-09-06"}


def test_the_identification_date_is_its_own_key():
    assert dates(identified__start="1950-06") == {"date_identified": "1950-06"}
    both = dates(collected__start="1946-09-03", identified__start="1950-06")
    assert both == {
        "date_visited_from": "1946-09-03",
        "date_visited_to": "1946-09-03",
        "date_identified": "1950-06",
    }


def test_a_time_fills_no_key():
    assert dates(collected__time="sunrise") == {}
    assert dates(collected__start="1946-09-03", collected__time="08:30") == {
        "date_visited_from": "1946-09-03",
        "date_visited_to": "1946-09-03",
    }


@pytest.mark.parametrize(
    "text",
    ["1946-13", "1946-00", "1946-02-30", "1947-02-29", "0000", "46", "194", "1946/09/03", "1946-9-3",
     "September 1946", "1946-09-03T00:00", "19460903", "1946-09-3", " 1946", "1946 ", "", "IX-14-46"],
)
def test_a_date_must_be_a_calendar_date_at_written_precision(text):
    with pytest.raises(FieldModelError):
        dates(collected__start=text)
    with pytest.raises(FieldModelError):
        dates(identified__start=text)


def test_leap_days_are_calendar_dates():
    assert dates(collected__start="1948-02-29")["date_visited_from"] == "1948-02-29"


@pytest.mark.parametrize("value", [None, 1946, Decimal("1946")])
def test_a_date_is_text(value):
    with pytest.raises(FieldModelError):
        dates(collected__start=value)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("1946-09-14", "1946-09-03"),
        ("1946-10", "1946-09"),
        ("1947", "1946"),
    ],
)
def test_a_reversed_range_is_refused(start, end):
    with pytest.raises(FieldModelError, match="end is before when/collected/start"):
        dates(collected__start=start, collected__end=end)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        # Different precision follows the live G44 endpoint check: the latest day of
        # the start must not pass the earliest day of the end.
        ("1946-09", "1946-09-14"),
        ("1946-09-03", "1946-09"),
        ("1946", "1946-06-01"),
        ("1946-12-31", "1946"),
    ],
)
def test_a_precision_conflict_between_the_ends_is_named_as_one(start, end):
    with pytest.raises(FieldModelError, match="conflict in precision") as refused:
        dates(collected__start=start, collected__end=end)
    assert start in str(refused.value)
    assert end in str(refused.value)
    assert "before" not in str(refused.value)


# --- the v1 mirror: collectors ----------------------------------------------------


def test_collectors_are_joined_in_written_order():
    assert v1_mirror({"collectors/1": "F.G. Werner"}) == {"collectors": "F.G. Werner"}
    assert v1_mirror({"collectors/1": "Werner", "collectors/2": "Mockford"}) == {
        "collectors": "Werner & Mockford"
    }
    # By index, not by the order of the mapping.
    assert v1_mirror(
        {"collectors/3": "C", "collectors/1": "A", "collectors/2": "B"}
    ) == {"collectors": "A & B & C"}
    assert v1_mirror({f"collectors/{n}": f"N{n}" for n in range(10, 0, -1)})["collectors"].count(
        COLLECTORS_JOINER
    ) == 9


def test_the_collectors_join_is_the_form_the_live_list_check_accepts():
    # research_harness/people.py splits a list on "&", ";" or "and"; the joiner is one of them.
    from specimen_digitization.research_harness.people import name_problem

    joined = v1_mirror({"collectors/1": "H. Hoogstraal", "collectors/2": "F.G. Werner"})["collectors"]
    assert joined == "H. Hoogstraal & F.G. Werner"
    assert name_problem(joined) is None


@pytest.mark.parametrize(
    "parts",
    [
        {"collectors/2": "B"},
        {"collectors/1": "A", "collectors/3": "C"},
        {"collectors/1": "A", "collectors/2": ""},
        {"collectors/1": "  "},
    ],
)
def test_collector_entries_run_one_to_n_with_none_empty(parts):
    with pytest.raises(FieldModelError):
        v1_mirror(parts)


# --- the v1 mirror: the pilot rows ------------------------------------------------


def test_the_fixture_embeds_all_ten_pilot_slides():
    assert sorted(ROWS) == [f"1055263{n}" for n in range(21, 31)]
    for subject, row in ROWS.items():
        assert row["barcode"].startswith("FMNHINS ")
        assert row["parts"]["ids/catalog_number"] == row["barcode"].split()[1]
        assert set(row["as_written"]) == {"locality", "date", "elevation", "collector"}
        assert row["parts"]["location/verbatim"] == row["as_written"]["locality"], subject


@pytest.mark.parametrize("subject", sorted(ROWS))
def test_the_pilot_rows_mirror_as_worked_by_hand(subject):
    row = ROWS[subject]
    result = v1_mirror(row["parts"])
    assert result == row["expected"]
    assert list(result) == [key for key in V1_KEYS if key in result]
    assert not NEVER_FILLED & set(result)
    for key in ("collection_code", "county", "city", "habitat", "collection_method", "taxon",
                "date_identified"):
        assert key not in result


def test_105526321_philippines_point_elevation_in_feet():
    result = v1_mirror(ROWS["105526321"]["parts"])
    assert result["country"] == "Philippines"
    assert result["province_state"] == "Davao"
    assert "Mindanao" not in result.values()  # the island level has no mirror
    assert result["precise_location"] == "E. slope Mt. McKinley\nDavao Prov.\nMindanao, P.I."
    assert (result["elevation_from_m"], result["elevation_to_m"]) == ("1950.72", "1950.72")
    assert (result["elevation_from_ft"], result["elevation_to_ft"]) == ("6400", "6400")
    assert (result["date_visited_from"], result["date_visited_to"]) == ("1946-09-03", "1946-09-03")
    assert result["collectors"] == "F.G. Werner"
    assert result["fmnh_ins_number"] == "4486784"


@pytest.mark.parametrize("subject", sorted(s for s, row in ROWS.items() if "bases" in row))
def test_a_pilot_row_with_an_inferred_unit_withholds_its_elevation(subject):
    row = ROWS[subject]
    withheld = v1_mirror(row["parts"], bases=row["bases"])
    assert withheld == row["expected_with_bases"]
    assert not any(key.startswith("elevation_") for key in withheld)
    # Everything else is the same as without the basis.
    assert withheld == {k: v for k, v in row["expected"].items() if not k.startswith("elevation_")}


def test_105526322_the_unit_inferred_as_feet_gives_the_same_exact_metres():
    # "Elev. 6400" read with the foot mark lost; feet inferred, 6400 ft stored as 1950.72 m.
    # Passed with no bases the adapter maps the values as given; passed with the unit's
    # basis (see the test above) it withholds the elevation.
    parts = ROWS["105526322"]["parts"]
    assert parts["elevation/unit"] == "ft"
    assert ROWS["105526322"]["bases"] == {"elevation/unit": "inferred"}
    result = v1_mirror(parts)
    assert result["elevation_from_m"] == result["elevation_to_m"] == "1950.72"
    assert result["elevation_from_ft"] == result["elevation_to_ft"] == "6400"
    # The same stored metres read as a metre-stated label would convert instead.
    as_metres = v1_mirror({**parts, "elevation/unit": "m"})
    assert as_metres["elevation_from_m"] == "1950.72"
    assert as_metres["elevation_from_ft"] == "6400"  # 1950.72 / 0.3048 is exactly 6400
    assert result["date_visited_from"] == "1946-09-06"


def test_105526327_month_precision_invents_no_day():
    result = v1_mirror(ROWS["105526327"]["parts"])
    assert result["date_visited_from"] == "1946-11"
    assert result["date_visited_to"] == "1946-11"  # G44: one date fills both, at the same precision
    assert not any(key.startswith("elevation_") for key in result)  # the label has no elevation
    assert result["country"] == "Philippines"
    assert result["province_state"] == "Davao"


def test_105526324_a_roman_numeral_date():
    result = v1_mirror(ROWS["105526324"]["parts"])
    assert result["date_visited_from"] == result["date_visited_to"] == "1946-09-14"
    assert result["elevation_from_ft"] == result["elevation_to_ft"] == "3300"
    assert result["elevation_from_m"] == result["elevation_to_m"] == "1005.84"
    assert result["collectors"] == "H. Hoogstraal"


def test_105526329_guatemala_keeps_the_labels_spelling_only_in_the_verbatim_locality():
    result = v1_mirror(ROWS["105526329"]["parts"])
    assert result["country"] == "Guatemala"
    assert result["province_state"] == "Chimaltenango"  # the department, derived
    assert "Chimaltenago" in result["precise_location"]  # the label's spelling, as read
    assert "Chimaltenango" not in result["precise_location"]
    assert "county" not in result  # a municipality is not a county; none is invented
    assert "city" not in result
    assert result["elevation_from_ft"] == "4800"
    assert result["elevation_from_m"] == "1463.04"
    assert result["date_visited_from"] == result["date_visited_to"] == "1948-04-23"


# --- hygiene: nothing pinned is imported ---------------------------------------

PINNED_APPLICATION = ("domain", "projection", "storage", "active_graph")
PINNED_RESEARCH_HARNESS = (
    "native_canonical",
    "accepted_output",
    "contracts",
    "evidence",
    "taxonomy",
    "temporal_context",
    "measurement",
    "people",
    "collection",
    "geography_context",
    "geography_strategy",
    "dependency_context",
    "output_admission",
    "engine",
    "journal",
)


def imported_modules():
    tree = ast.parse(Path(field_model.__file__).read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append("." * node.level + (node.module or ""))
    return modules


def test_the_module_imports_only_the_standard_library():
    modules = imported_modules()
    assert modules, "the scan found no imports"
    for name in modules:
        assert not name.startswith("."), f"relative import {name}"
        assert name.split(".")[0] in sys.stdlib_module_names, name


def test_the_module_imports_none_of_the_byte_pinned_files():
    pinned = {f"specimen_digitization.application.{name}" for name in PINNED_APPLICATION}
    pinned |= {f"specimen_digitization.research_harness.{name}" for name in PINNED_RESEARCH_HARNESS}
    source = Path(field_model.__file__).read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = node.module or ""
            for alias in node.names:
                assert f"{base}.{alias.name}" not in pinned
            assert base not in pinned
            assert not base.startswith("specimen_digitization")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in pinned
                assert not alias.name.startswith("specimen_digitization")
    # No dynamic import either.
    assert "importlib" not in source
    assert "__import__" not in source


def test_importing_the_module_loads_no_other_package_module():
    code = (
        "import sys\n"
        "import specimen_digitization.application.field_model\n"
        "print('\\n'.join(sorted(n for n in sys.modules if n.startswith('specimen_digitization'))))\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    loaded = set(done.stdout.split())
    assert loaded == {
        "specimen_digitization",
        "specimen_digitization.application",
        "specimen_digitization.application.field_model",
    }
    assert "specimen_digitization.application.domain" not in loaded
    assert "specimen_digitization.application.projection" not in loaded


def test_the_public_names_are_all_defined():
    for name in field_model.__all__:
        assert hasattr(field_model, name), name
