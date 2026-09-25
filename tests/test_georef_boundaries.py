"""Administrative units from the pinned boundary files (GEO.md 12), on excerpts of those files."""

import dataclasses
import io
import json
import zipfile
from pathlib import Path

import pytest

from specimen_digitization.application.georef_boundaries import (
    extent,
    holding_circle,
    read_units,
)
from specimen_digitization.application.georef_datasets import SIMPLIFIED_MARGIN_M, dataset
from specimen_digitization.application.georef_geometry import (
    circle_within,
    clearance,
    enclosing_circle,
)
from specimen_digitization.application.georef_places import Ref

FIXTURES = Path(__file__).parent / "fixtures" / "georeferencing"
PH_ADM3 = dataset("geoboundaries/PH/ADM3/9469f09")
GT = dataset("cod-ab/GT/2026-09-24")
TALOMO = (7.0364, 125.3125)  # Wikidata's Mount Talomo
APO = (6.9875, 125.27083333333)  # Wikidata's Mount Apo, the summit
YEPOCAPA = (14.50195, -90.95396)  # GeoNames 3587636, the town
SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def cod_ab_zip(layers: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in layers.items():
            archive.writestr(name, data)
    return buffer.getvalue()


# The pinned zip's two polygon layers, beside the members the reader leaves alone.
GT_LAYERS = {
    "gtm_admin0.geojson": b"not read",
    "gtm_admin1.geojson": fixture("cod_ab_GT_admin1.geojson"),
    "gtm_admin2.geojson": fixture("cod_ab_GT_admin2.geojson"),
    "gtm_adminlines.geojson": b"not read",
    "gtm_adminpoints.geojson": b"not read",
}


def collection(*features: dict, **members: object) -> bytes:
    return json.dumps({"type": "FeatureCollection", **members, "features": list(features)}).encode()


def unit_feature(**properties: object) -> dict:
    named = {"shapeName": "Test", "shapeID": "T1", "shapeType": "ADM3", **properties}
    return {"type": "Feature", "properties": named, "geometry": SQUARE}


@pytest.fixture(scope="module")
def philippines():
    return read_units(PH_ADM3, fixture("geoboundaries_PH_ADM3.geojson"))


@pytest.fixture(scope="module")
def guatemala():
    return read_units(GT, cod_ab_zip(GT_LAYERS))


def named(units, name):
    return next(unit for unit in units if unit.name == name)


def test_a_geoboundaries_file_gives_its_units_without_parents(philippines):
    (feature,) = json.loads(fixture("geoboundaries_PH_ADM3.geojson"))["features"]
    (unit,) = philippines
    assert (unit.name, unit.level, unit.code) == ("Davao City", 3, feature["properties"]["shapeID"])
    assert (unit.country, unit.parent, unit.dataset) == ("PH", None, PH_ADM3.id)
    assert unit.margin_m == SIMPLIFIED_MARGIN_M


def test_a_cod_ab_file_gives_departments_and_municipios_in_their_department(guatemala):
    chimaltenango = Ref("GT04", "Chimaltenango")
    assert [(unit.level, unit.name, unit.code, unit.parent) for unit in guatemala] == [
        (1, "Chimaltenango", "GT04", None),
        (2, "Yepocapa", "GT0412", chimaltenango),
        (2, "Acatenango", "GT0411", chimaltenango),
    ]
    for unit in guatemala:
        assert (unit.country, unit.dataset, unit.margin_m) == ("GT", "cod-ab/GT/2026-09-24", 0.0)


def test_a_municipio_whose_file_names_no_department_has_no_parent():
    municipios = json.loads(fixture("cod_ab_GT_admin2.geojson"))
    for feature in municipios["features"]:
        del feature["properties"]["adm1_pcode"]
    layers = {**GT_LAYERS, "gtm_admin2.geojson": json.dumps(municipios).encode()}
    units = read_units(GT, cod_ab_zip(layers))
    assert [unit.parent for unit in units if unit.level == 2] == [None, None]


def test_a_circle_is_held_at_each_level_whose_unit_it_clears(guatemala):
    yepocapa = named(guatemala, "Yepocapa")
    room = clearance(yepocapa.shape, YEPOCAPA)
    assert room == pytest.approx(2063.1, abs=0.1)
    held = holding_circle(guatemala, YEPOCAPA, room - 1)
    assert {level: unit.name for level, unit in held.items()} == {1: "Chimaltenango", 2: "Yepocapa"}
    held = holding_circle(guatemala, YEPOCAPA, room + 1)
    assert {level: unit.name for level, unit in held.items()} == {1: "Chimaltenango"}
    assert holding_circle(guatemala, YEPOCAPA, 7000) == {}


def test_a_simplified_file_needs_its_margin_to_spare(philippines):
    davao = named(philippines, "Davao City")
    assert holding_circle(philippines, TALOMO, 2000) == {3: davao}
    # Mount Apo's summit is 123 m inside Davao City's simplified boundary, so only a
    # circle of 22 m or less clears it by the margin.
    room = clearance(davao.shape, APO)
    assert room == pytest.approx(123.2, abs=0.1)
    assert holding_circle(philippines, APO, room - SIMPLIFIED_MARGIN_M - 1) == {3: davao}
    assert holding_circle(philippines, APO, room - SIMPLIFIED_MARGIN_M + 1) == {}
    assert circle_within(davao.shape, APO, room - SIMPLIFIED_MARGIN_M + 1)  # without the margin


def test_a_point_outside_every_unit_is_held_by_none(philippines, guatemala):
    assert holding_circle(philippines, (14.5995, 120.9842), 0) == {}  # Manila
    assert holding_circle(guatemala, (14.6349, -90.5069), 0) == {}  # Guatemala City


def test_a_level_held_by_two_units_is_left_out(guatemala):
    twin = dataclasses.replace(named(guatemala, "Yepocapa"), code="GT0412-twin")
    held = holding_circle([*guatemala, twin], YEPOCAPA, 100)
    assert {level: unit.name for level, unit in held.items()} == {1: "Chimaltenango"}


def test_an_extent_from_a_simplified_file_adds_its_margin(philippines, guatemala):
    davao = named(philippines, "Davao City")
    circle, plain = extent(davao), enclosing_circle(davao.shape)
    assert (circle.center, circle.center_inside) == (plain.center, True)
    assert circle.radial_m == plain.radial_m + SIMPLIFIED_MARGIN_M
    assert circle.radial_m == pytest.approx(35_671, abs=1)
    yepocapa, chimaltenango = named(guatemala, "Yepocapa"), named(guatemala, "Chimaltenango")
    assert extent(yepocapa) == enclosing_circle(yepocapa.shape)
    assert extent(yepocapa).radial_m == pytest.approx(13_357, abs=1)
    assert extent(chimaltenango).radial_m == pytest.approx(37_142, abs=1)


def test_a_file_without_a_coordinate_system_is_read_as_longitude_and_latitude():
    (unit,) = read_units(PH_ADM3, collection(unit_feature()))
    assert (unit.name, unit.code, unit.level) == ("Test", "T1", 3)
    assert unit.shape[0][0][1] == (0.0, 1.0)  # latitude, longitude


@pytest.mark.parametrize(
    "data",
    [
        b"not json",
        json.dumps([]).encode(),
        json.dumps({"type": "Feature", "properties": {}, "geometry": SQUARE}).encode(),
        json.dumps({"type": "FeatureCollection", "features": {}}).encode(),
        collection(
            unit_feature(),
            crs={"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::3857"}},
        ),
        collection(unit_feature(), crs="CRS84"),
        collection({"type": "Feature", "geometry": SQUARE}),
        collection(unit_feature(shapeType="ADM4")),
        collection(unit_feature(shapeName=" ")),
        collection(unit_feature(shapeID=None)),
        collection({**unit_feature(), "geometry": {"type": "Point", "coordinates": [0, 0]}}),
    ],
)
def test_a_geoboundaries_file_that_cannot_be_read_is_refused(data):
    with pytest.raises(ValueError):
        read_units(PH_ADM3, data)


def test_a_cod_ab_file_that_cannot_be_read_is_refused():
    with pytest.raises(ValueError):
        read_units(GT, b"not a zip")
    without_municipios = {name: data for name, data in GT_LAYERS.items() if "admin2" not in name}
    with pytest.raises(ValueError):
        read_units(GT, cod_ab_zip(without_municipios))
    departments = json.loads(fixture("cod_ab_GT_admin1.geojson"))
    departments["features"][0]["properties"]["adm1_pcode"] = None
    layers = {**GT_LAYERS, "gtm_admin1.geojson": json.dumps(departments).encode()}
    with pytest.raises(ValueError):
        read_units(GT, cod_ab_zip(layers))


def test_only_a_boundary_file_is_read_as_one():
    with pytest.raises(ValueError):
        read_units(dataset("copernicus-glo30/N07_00_E125_00"), collection(unit_feature()))
