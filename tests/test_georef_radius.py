"""Tier 3's point-radius uncertainty against the Georeferencing Calculator's
worked examples (GEO.md 9).

The examples are the Calculator's own (VertNet/georefcalculator at 1cc9f4c,
`test_data.js`), all near Bakersfield, California. Each expected value is the
one the Calculator shows, to the decimals it shows.
"""

import math

import pytest

from specimen_digitization.application.georef_radius import (
    CLARKE_1866,
    FOOT,
    MILE,
    UNKNOWN_DATUM_M,
    WGS84,
    Errors,
    along_path,
    at_heading,
    compass_precision,
    coordinates_only,
    datum_error,
    distance_only,
    ellipsoid_for,
    feature_only,
    heading_offset,
    moved,
    offset_precision,
    orthogonal,
    precision_error,
    sector,
)

# The four examples whose datum was not recorded used the Calculator's 2015 grid of datum
# errors: 79 m at Bakersfield. Its 2019 grid gives 3,045 m there, so the value is passed in.
BAKERSFIELD_DATUM_2015_M = 79.0
SECOND = 1 / 3600


def dms(degrees, minutes, seconds=0.0):
    """A coordinate as the Calculator stores it: decimal degrees to seven decimals."""
    return round(degrees + minutes / 60 + seconds / 3600, 7)


def test_coordinates_only_to_the_nearest_second_with_no_datum():
    errors = Errors(
        precision_m=precision_error(dms(35, 22, 24), SECOND, WGS84),
        datum_m=datum_error(recorded=False, place_m=BAKERSFIELD_DATUM_2015_M),
    )
    assert round(coordinates_only(errors), 3) == 118.837


def test_coordinates_only_from_a_usgs_map_on_nad27():
    errors = Errors(source_m=40 * FOOT, precision_m=precision_error(35.37, 0.01, CLARKE_1866))
    assert round(coordinates_only(errors), 3) == 1446.325


def test_a_named_place_only():
    # "Bakersfield": 3 km from its center to the farthest city limit.
    errors = Errors(
        radial_m=3000,
        precision_m=precision_error(dms(35, 22, 24), SECOND, WGS84),
        datum_m=BAKERSFIELD_DATUM_2015_M,
    )
    assert round(feature_only(errors) / 1000, 3) == 3.119


def test_a_distance_only():
    # "5 mi from Bakersfield", written to the mile, the city 2 mi across to its farthest limit.
    errors = Errors(
        radial_m=2 * MILE,
        precision_m=precision_error(35.373, 0.001, CLARKE_1866),
        offset_precision_m=offset_precision(MILE),
    )
    assert round(distance_only(errors, 5 * MILE) / MILE, 3) == 7.589


def test_a_distance_along_a_path():
    # "13 mi E (by road) Bakersfield", read to 0.1 minute from a USGS 1:100,000 map (167 ft).
    errors = Errors(
        radial_m=2 * MILE,
        source_m=167 * FOOT,
        measurement_m=0.03107 * MILE,
        precision_m=precision_error(dms(35, 26.1), 1 / 600, CLARKE_1866),
        offset_precision_m=offset_precision(MILE),
    )
    assert round(along_path(errors) / MILE, 3) == 2.711


def test_distances_along_orthogonal_directions():
    # "2 mi E and 3 mi N of Bakersfield".
    latitude, longitude = dms(35, 25, 4), -dms(118, 58, 54)
    errors = Errors(
        radial_m=2 * MILE,
        precision_m=precision_error(latitude, SECOND, WGS84),
        datum_m=BAKERSFIELD_DATUM_2015_M,
        offset_precision_m=offset_precision(MILE),
    )
    assert round(orthogonal(errors) / MILE, 3) == 2.781
    reached = moved(latitude, longitude, 3 * MILE, 2 * MILE, WGS84)
    assert reached[0] == 35.4612939
    # The Calculator shows -118.946227. Its mile (1,609.3445 m) and the exact one both give
    # -118.9462271, 1e-7 degree (about 1 cm) away.
    assert reached[1] == pytest.approx(-118.946227, abs=1.5e-7)


def test_a_distance_at_a_cardinal_heading():
    # "10 mi E (by air) Bakersfield", written to ten miles.
    latitude, longitude = dms(35, 22, 24), -dms(118, 50, 56)
    errors = Errors(
        radial_m=2 * MILE,
        precision_m=precision_error(latitude, SECOND, WGS84),
        datum_m=BAKERSFIELD_DATUM_2015_M,
        offset_precision_m=offset_precision(10 * MILE),
    )
    assert round(at_heading(errors, 10 * MILE, compass_precision(90)) / MILE, 3) == 12.254
    assert moved(latitude, longitude, *heading_offset(10 * MILE, 90), WGS84) == (
        35.3733333,
        -118.671788,
    )


def test_a_distance_at_a_three_letter_heading():
    # "10 mi ENE (by air) Bakersfield", read to the second from a USGS 1:24,000 map on NAD27.
    latitude, longitude = dms(35, 24, 21), -dms(118, 51, 25)
    errors = Errors(
        radial_m=2 * MILE,
        source_m=40 * FOOT,
        measurement_m=0.007 * MILE,
        precision_m=precision_error(latitude, SECOND, CLARKE_1866),
        offset_precision_m=offset_precision(10 * MILE),
    )
    assert round(at_heading(errors, 10 * MILE, compass_precision(67.5)) / MILE, 3) == 7.491
    assert moved(latitude, longitude, *heading_offset(10 * MILE, 67.5), CLARKE_1866) == (
        35.4613445,
        -118.6932627,
    )


def test_the_datum_rule():
    assert datum_error(recorded=True) == 0.0
    assert datum_error(recorded=False) == UNKNOWN_DATUM_M == 5359.0
    assert datum_error(recorded=False, place_m=79.0) == 79.0
    assert ellipsoid_for("NAD27") is CLARKE_1866
    assert ellipsoid_for(None) is WGS84 and ellipsoid_for("Tokyo") is WGS84


def test_offset_precision_is_half_the_unit_written_to():
    assert offset_precision(MILE) == MILE / 2
    assert offset_precision(10 * MILE) == 5 * MILE
    with pytest.raises(ValueError):
        offset_precision(0)


@pytest.mark.parametrize(
    ("bearings", "precision"),
    [
        ((0, 90, 180, 270), 45.0),
        ((45, 135, 225, 315), 22.5),
        ((22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5), 11.25),
        ((11.25, 33.75, 56.25, 78.75, 101.25, 123.75, 146.25, 168.75), 5.625),
        ((191.25, 213.75, 236.25, 258.75, 281.25, 303.75, 326.25, 348.75), 5.625),
    ],
)
def test_the_heading_precision_of_every_compass_point(bearings, precision):
    assert {compass_precision(bearing) for bearing in bearings} == {precision}


def test_a_heading_in_degrees_is_not_a_compass_point():
    with pytest.raises(ValueError):
        compass_precision(30)


@pytest.mark.parametrize("half_width", [90.0, 45.0, 22.5, 11.25])
def test_the_sector_circle_encloses_the_center_and_the_whole_arc(half_width):
    radial = 1000.0
    offset, radius = sector(radial, half_width)
    center = (offset, 0.0)  # along the heading, which lies on the x axis
    arc = [
        (radial * math.cos(math.radians(angle)), radial * math.sin(math.radians(angle)))
        for angle in [half_width * step / 50 for step in range(-50, 51)]
    ]
    assert all(math.dist(center, point) <= radius + 1e-9 for point in [(0.0, 0.0), *arc])
    # The circle is the smallest: the arc's ends lie on it.
    assert math.dist(center, arc[0]) == pytest.approx(radius)


def test_an_east_slope_is_a_circle_of_0_707_times_the_radial():
    assert sector(1000.0, compass_precision(90)) == pytest.approx((707.1068, 707.1068))


def test_offsets_wrap_the_antimeridian_and_stop_at_the_poles():
    assert moved(0.0, 179.99, 0.0, 10_000.0) == pytest.approx((0.0, -179.920168), abs=1e-6)
    with pytest.raises(ValueError):
        moved(89.9, 0.0, 50_000.0, 0.0)


@pytest.mark.parametrize(
    "call",
    [
        lambda: Errors(radial_m=-1.0),
        lambda: Errors(datum_m=math.nan),
        lambda: precision_error(95.0, SECOND),
        lambda: precision_error(10.0, -SECOND),
        lambda: moved(10.0, 200.0, 0.0, 0.0),
        lambda: at_heading(Errors(), MILE, 0.0),
        lambda: at_heading(Errors(), -MILE, 45.0),
        lambda: sector(-1.0, 45.0),
    ],
)
def test_impossible_inputs_are_refused(call):
    with pytest.raises(ValueError):
        call()
