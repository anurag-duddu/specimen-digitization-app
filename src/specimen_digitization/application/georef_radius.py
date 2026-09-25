"""Tier 3: the point-radius uncertainty, computed in-house (GEO.md 9, D13).

The arithmetic is the Georeferencing Calculator's (VertNet/georefcalculator at
1cc9f4c, Apache-2.0), read from its published code and checked against its
worked examples: each locality type adds its sources of uncertainty, except
that orthogonal offsets count their distance precision in two dimensions and an
offset at a heading widens into a cone. Everything is in meters. The module
computes; it sends nothing and reads no file.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MILE = 1609.344  # meters, exactly
FOOT = 0.3048  # meters, exactly
UNKNOWN_DATUM_M = 5359.0  # the Calculator's worst case when the datum is not recorded
DEGREE_HEADING = 1.0  # the precision of a heading written in degrees, as the Calculator takes it


@dataclass(frozen=True, slots=True)
class Ellipsoid:
    name: str
    semi_major_m: float
    flattening: float


WGS84 = Ellipsoid("WGS84", 6378137.0, 1 / 298.257223563)
GRS80 = Ellipsoid("GRS80", 6378137.0, 1 / 298.257222101)
CLARKE_1866 = Ellipsoid("Clarke 1866", 6378206.4, 1 / 294.9786982)
ELLIPSOIDS = {"WGS84": WGS84, "NAD83": GRS80, "NAD27": CLARKE_1866}


@dataclass(frozen=True, slots=True)
class Errors:
    """The sources of uncertainty a locality type combines, each in meters."""

    radial_m: float = 0.0
    source_m: float = 0.0
    measurement_m: float = 0.0
    precision_m: float = 0.0
    datum_m: float = 0.0
    offset_precision_m: float = 0.0

    def __post_init__(self) -> None:
        values = (
            self.radial_m,
            self.source_m,
            self.measurement_m,
            self.precision_m,
            self.datum_m,
            self.offset_precision_m,
        )
        if not all(math.isfinite(value) and value >= 0 for value in values):
            raise ValueError("every source of uncertainty is a finite distance, zero or more")

    @property
    def base_m(self) -> float:
        """What every locality type adds: datum, source, measurement and precision."""
        return self.datum_m + self.source_m + self.measurement_m + self.precision_m


def ellipsoid_for(datum: str | None) -> Ellipsoid:
    """The ellipsoid of a named datum; WGS84 for any other, as the Calculator does."""
    return ELLIPSOIDS.get(datum or "", WGS84)


def meters_per_degree(latitude: float, ellipsoid: Ellipsoid = WGS84) -> tuple[float, float]:
    """Meters in one degree of latitude and in one of longitude at a latitude
    (NIMA 8350.2, as the Calculator computes them)."""
    _latitude(latitude)
    f = ellipsoid.flattening
    e_squared = 2 * f - f * f
    sine_squared = math.sin(math.radians(latitude)) ** 2
    prime_vertical = ellipsoid.semi_major_m / math.sqrt(1 - e_squared * sine_squared)
    meridian = ellipsoid.semi_major_m * (1 - e_squared) / (1 - e_squared * sine_squared) ** 1.5
    longitude_radius = prime_vertical * math.cos(math.radians(latitude))
    return math.pi * meridian / 180, math.pi * longitude_radius / 180


def precision_error(
    latitude: float, precision_degrees: float, ellipsoid: Ellipsoid = WGS84
) -> float:
    """The diagonal of one precision cell at a latitude: a coordinate given to
    the nearest second has `precision_degrees` 1/3600."""
    if not math.isfinite(precision_degrees) or precision_degrees < 0:
        raise ValueError("a coordinate precision is zero or more degrees")
    return math.hypot(*meters_per_degree(latitude, ellipsoid)) * precision_degrees


def datum_error(recorded: bool, place_m: float | None = None) -> float:
    """None for a recorded datum; for an unrecorded one, the place's value, else
    the Calculator's worst case."""
    if recorded:
        return 0.0
    return UNKNOWN_DATUM_M if place_m is None else place_m


def offset_precision(unit_m: float) -> float:
    """Half the unit a distance is written to: 0.5 mi for "5 mi" to the mile."""
    if not math.isfinite(unit_m) or unit_m <= 0:
        raise ValueError("a distance is written to a unit greater than zero")
    return unit_m / 2


def compass_precision(bearing: float) -> float:
    """Half the angle between neighbouring points of the compass a bearing is
    written with: 45 for N, E, S and W, down to 5.625 for the "by" points."""
    for spacing in (90.0, 45.0, 22.5, 11.25):
        if math.isclose(bearing % spacing, 0.0, abs_tol=1e-9) or math.isclose(
            bearing % spacing, spacing, abs_tol=1e-9
        ):
            return spacing / 2
    raise ValueError("not a bearing of the 32-point compass; a heading in degrees is ±1")


def coordinates_only(errors: Errors) -> float:
    return errors.base_m


def feature_only(errors: Errors) -> float:
    return errors.base_m + errors.radial_m


def distance_only(errors: Errors, offset_m: float) -> float:
    return feature_only(errors) + _distance(offset_m) + errors.offset_precision_m


def along_path(errors: Errors) -> float:
    return feature_only(errors) + errors.offset_precision_m


def orthogonal(errors: Errors) -> float:
    return feature_only(errors) + errors.offset_precision_m * math.sqrt(2)


def at_heading(errors: Errors, offset_m: float, heading_precision: float) -> float:
    """The cone's error, from the point `offset_m + e` along the heading to the
    point `offset_m` along the cone's edge, plus precision."""
    distance = _distance(offset_m)
    if not 0 < heading_precision <= 90:
        raise ValueError("a heading's precision is more than 0 and at most 90 degrees")
    alpha = math.radians(heading_precision)
    spread = (
        errors.datum_m
        + errors.radial_m
        + errors.measurement_m
        + errors.offset_precision_m
        + errors.source_m
    )
    along = distance + spread - distance * math.cos(alpha)
    return math.hypot(along, distance * math.sin(alpha)) + errors.precision_m


def heading_offset(offset_m: float, bearing: float) -> tuple[float, float]:
    """Meters north and east of an offset at a bearing, as the Calculator splits it."""
    distance = _distance(offset_m)
    return (
        distance * math.cos(math.radians(bearing)),
        distance * math.cos(math.radians(bearing - 90)),
    )


def moved(
    latitude: float,
    longitude: float,
    north_m: float,
    east_m: float,
    ellipsoid: Ellipsoid = WGS84,
) -> tuple[float, float]:
    """The point an offset reaches, by the meters per degree at the starting
    latitude, rounded to seven decimals as the Calculator rounds it. A longitude
    past the antimeridian wraps; an offset past a pole is refused."""
    if not -180 <= longitude <= 180:
        raise ValueError("a longitude lies between -180 and 180 degrees")
    per_latitude, per_longitude = meters_per_degree(latitude, ellipsoid)
    new_latitude = latitude + north_m / per_latitude
    if not -90 <= new_latitude <= 90:
        raise ValueError("the offset passes a pole")
    new_longitude = (longitude + east_m / per_longitude + 180) % 360 - 180
    return round(new_latitude, 7), round(new_longitude, 7)


def sector(radial_m: float, heading_precision: float) -> tuple[float, float]:
    """The smallest circle around the part of a feature's circle (radial R)
    within a heading's cone ("E. slope of X"): its center's distance from the
    feature's center along the heading, and its radius."""
    radial = _distance(radial_m)
    if not 0 < heading_precision <= 90:
        raise ValueError("a heading's precision is more than 0 and at most 90 degrees")
    alpha = math.radians(heading_precision)
    if heading_precision >= 45:  # the chord between the arc's ends is a diameter
        return radial * math.cos(alpha), radial * math.sin(alpha)
    # A narrower cone: the circle through X's center and the arc's ends.
    through_center = radial / (2 * math.cos(alpha))
    return through_center, through_center


def _distance(value: float) -> float:
    if not math.isfinite(value) or value < 0:
        raise ValueError("a distance is finite and zero or more")
    return value


def _latitude(value: float) -> None:
    if not -90 <= value <= 90:
        raise ValueError("a latitude lies between -90 and 90 degrees")
