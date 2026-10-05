"""Pinned administrative boundaries and whole-circle derivations."""

import hashlib
import json
from dataclasses import replace

import pytest

from specimen_digitization.application import georef_boundaries as boundaries
from specimen_digitization.application.georef_datasets import dataset
from specimen_digitization.application.georef_geometry import shape_from_geojson


def square(west, south, size):
    return [[west, south], [west + size, south], [west + size, south + size],
            [west, south + size], [west, south]]


def test_verified_boundary_bytes_produce_units_with_their_simplification_margin(monkeypatch):
    features = [
        {"type": "Feature", "properties": {"shapeType": "ADM1", "shapeName": name,
         "shapeID": name.lower()}, "geometry": {"type": "Polygon", "coordinates": [square(west, 0, .1)]}}
        for name, west in (("West", 0), ("East", .1))
    ]
    data = json.dumps({"type": "FeatureCollection", "features": features}).encode()
    digest = hashlib.sha256(data).hexdigest()
    dataset_id = "geoboundaries/PH/ADM1/41af8f1"
    entry = replace(dataset(dataset_id), size=len(data), sha256=digest)
    monkeypatch.setattr(boundaries, "dataset", lambda key: entry if key == dataset_id else dataset(key))

    units = boundaries.pinned_units(dataset_id, data)
    assert [(unit.name, unit.margin_m) for unit in units] == [("West", 101.2), ("East", 101.2)]
    assert boundaries.holding_circle(units, (.05, .05), 1_000)[1].name == "West"
    assert 1 not in boundaries.holding_circle(units, (.05, .0005), 0)
    assert boundaries.extent(units[0]).radial_m == pytest.approx(
        boundaries.extent(replace(units[0], margin_m=0.0)).radial_m + 101.2
    )
    with pytest.raises(ValueError, match="not the reviewed file"):
        boundaries.pinned_units(dataset_id, data + b" ")


def test_hole_and_competing_units_never_derive_an_ambiguous_level():
    framed = shape_from_geojson({"type": "Polygon", "coordinates": [square(0, 0, .1),
                                                                      square(.04, .04, .02)]})
    unit = boundaries.Unit("PH", 2, "Framed", "one", None, framed, "sample", 0)
    assert 2 not in boundaries.holding_circle([unit], (.05, .05), 0)
    assert 2 not in boundaries.holding_circle([unit, unit], (.02, .02), 10)
    assert boundaries.holding_circle([unit], (.02, .02), 10)[2].code == "one"


def test_unreviewed_boundary_identity_is_rejected():
    with pytest.raises(ValueError, match="not pinned"):
        boundaries.pinned_units("unknown/XX", b"{}")
