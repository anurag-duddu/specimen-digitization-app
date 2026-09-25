"""A unit's extent, and whether a circle lies inside it (GEO.md 10), on synthetic boundaries."""

import math

import pytest

from specimen_digitization.application.georef_geometry import (
    circle_within,
    clearance,
    enclosing_circle,
    inside,
    shape_from_geojson,
)
from specimen_digitization.application.georef_radius import WGS84, meters_per_degree


def square(west, south, size):
    return [[west, south], [west + size, south], [west + size, south + size], [west, south + size],
            [west, south]]


# A square 0.1 degree wide at the equator, with a hole 0.02 degree wide in its middle.
FRAMED = shape_from_geojson(
    {"type": "Polygon", "coordinates": [square(0.0, 0.0, 0.1), square(0.04, 0.04, 0.02)]}
)
# Two islands 0.1 degree apart.
ISLANDS = shape_from_geojson(
    {"type": "MultiPolygon",
     "coordinates": [[square(10.0, 5.0, 0.05)], [square(10.15, 5.0, 0.05)]]}
)
# A U: a 0.03-degree square with a notch cut down from its top middle.
U_SHAPE = shape_from_geojson(
    {"type": "Polygon",
     "coordinates": [[[0.0, 0.0], [0.03, 0.0], [0.03, 0.03], [0.02, 0.03], [0.02, 0.01],
                      [0.01, 0.01], [0.01, 0.03], [0.0, 0.03], [0.0, 0.0]]]}
)
PER_LATITUDE, PER_LONGITUDE = meters_per_degree(0.05, WGS84)


def test_a_point_is_inside_the_rings_but_not_their_holes():
    assert inside(FRAMED, (0.02, 0.02))
    assert not inside(FRAMED, (0.05, 0.05))  # in the hole
    assert not inside(FRAMED, (0.2, 0.2))
    assert inside(ISLANDS, (5.02, 10.02)) and inside(ISLANDS, (5.02, 10.17))
    assert not inside(ISLANDS, (5.02, 10.1))  # the strait between them


def test_clearance_is_the_distance_to_the_nearest_edge():
    # From (0.02, 0.02) the nearest edges are the outer square's south and west sides,
    # 0.02 degree away.
    expected = 0.02 * min(meters_per_degree(0.02, WGS84))
    assert clearance(FRAMED, (0.02, 0.02)) == pytest.approx(expected)
    # From (0.03, 0.05) the hole's west side is 0.01 degree away, nearer than any outer side.
    assert clearance(FRAMED, (0.05, 0.03)) == pytest.approx(0.01 * meters_per_degree(0.05)[1])


def test_a_circle_lies_inside_only_with_room_to_spare():
    point = (0.02, 0.02)
    room = clearance(FRAMED, point)
    assert circle_within(FRAMED, point, room - 1)
    assert not circle_within(FRAMED, point, room + 1)
    # A simplified file's margin (101.2 m for geoBoundaries' simplified files) must also fit.
    assert circle_within(FRAMED, point, room - 102, margin_m=101.2)
    assert not circle_within(FRAMED, point, room - 100, margin_m=101.2)
    assert not circle_within(FRAMED, (0.05, 0.05), 1.0)  # its center is in the hole


def test_a_units_extent_is_its_smallest_enclosing_circle():
    plain = shape_from_geojson({"type": "Polygon", "coordinates": [square(0.0, 0.0, 0.1)]})
    circle = enclosing_circle(plain)
    assert circle.center_inside
    assert circle.center == pytest.approx((0.05, 0.05))
    assert circle.radial_m == pytest.approx(math.hypot(0.05 * PER_LATITUDE, 0.05 * PER_LONGITUDE))


def test_a_center_in_a_hole_moves_onto_the_holes_edge():
    # The framed square's smallest circle is centered in its hole. The best point of the boundary
    # is the middle of the hole's south (or north) edge, 0.06 and 0.05 degree from the far corners.
    circle = enclosing_circle(FRAMED)
    assert not circle.center_inside
    assert clearance(FRAMED, circle.center) == pytest.approx(0.0, abs=1e-6)
    assert circle.radial_m == pytest.approx(
        math.hypot(0.06 * PER_LATITUDE, 0.05 * PER_LONGITUDE), rel=1e-6
    )


def test_a_center_outside_the_unit_moves_onto_its_boundary():
    circle = enclosing_circle(U_SHAPE)
    assert not circle.center_inside
    assert clearance(U_SHAPE, circle.center) == pytest.approx(0.0, abs=1e-6)
    corners = [(0.0, 0.0), (0.0, 0.03), (0.03, 0.0), (0.03, 0.03)]
    per_latitude, per_longitude = meters_per_degree(0.015)

    def meters(a, b):
        return math.hypot((a[0] - b[0]) * per_latitude, (a[1] - b[1]) * per_longitude)

    assert all(meters(circle.center, corner) <= circle.radial_m + 1e-6 for corner in corners)
    # No vertex of the boundary reaches every corner with a smaller radius.
    vertices = [(0.0, 0.0), (0.0, 0.03), (0.03, 0.03), (0.03, 0.02), (0.01, 0.02), (0.01, 0.01),
                (0.03, 0.01), (0.03, 0.0)]
    assert all(max(meters(vertex, corner) for corner in corners) >= circle.radial_m - 1e-6
               for vertex in vertices)
    # The notch's floor, midway, is the boundary point nearest to every corner at once.
    assert circle.radial_m == pytest.approx(meters((0.01, 0.015), (0.03, 0.0)), rel=1e-4)


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [0, 0]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]},
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 95], [0, 0]]]},
        {"type": "Polygon", "coordinates": [[[-179, 0], [179, 0], [179, 1], [-179, 0]]]},
        {"type": "MultiPolygon", "coordinates": []},
    ],
)
def test_boundaries_that_cannot_be_read_are_refused(geometry):
    with pytest.raises(ValueError):
        shape_from_geojson(geometry)
