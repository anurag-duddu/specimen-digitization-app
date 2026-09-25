"""A unit's extent, and whether a circle lies inside it (GEO.md 10).

County and city are derived only when the whole uncertainty circle lies inside
one unit (the coordinator's reading of G37), and a location found only as its
county sits at the county's precision (the coordinator's reading of G38). Both
read a unit's boundary. The module is pure: the caller passes a boundary it has
read, and distances use the ellipsoid's meters per degree (section 9).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .georef_radius import WGS84, Ellipsoid, meters_per_degree

Point = tuple[float, float]  # latitude, longitude
Ring = tuple[Point, ...]
Polygon = tuple[Ring, ...]  # the outer ring, then its holes
Shape = tuple[Polygon, ...]


@dataclass(frozen=True, slots=True)
class Circle:
    """A unit's corrected center and geographic radial; `center_inside` is false
    when the smallest enclosing circle's center fell outside the unit and the
    center was moved onto its boundary, as the Quick Reference Guide asks."""

    center: Point
    radial_m: float
    center_inside: bool


def shape_from_geojson(geometry: Mapping) -> Shape:
    """A GeoJSON Polygon or MultiPolygon of [longitude, latitude] pairs."""
    kind = geometry.get("type") if isinstance(geometry, Mapping) else None
    coordinates = geometry.get("coordinates") if isinstance(geometry, Mapping) else None
    if kind == "Polygon":
        polygons = [coordinates]
    elif kind == "MultiPolygon" and isinstance(coordinates, Sequence):
        polygons = list(coordinates)
    else:
        raise ValueError("a boundary is a GeoJSON Polygon or MultiPolygon")
    shape = tuple(tuple(_ring(ring) for ring in _rings(polygon)) for polygon in polygons)
    if not shape:
        raise ValueError("a boundary has at least one polygon")
    longitudes = [longitude for polygon in shape for ring in polygon for _, longitude in ring]
    if max(longitudes) - min(longitudes) > 180:
        raise ValueError("a boundary spanning more than 180 degrees of longitude is not read")
    return shape


def inside(shape: Shape, point: Point) -> bool:
    """Whether a ray from the point crosses the boundary's rings an odd number
    of times; a point in a hole is outside."""
    latitude, longitude = point
    crossings = 0
    for polygon in shape:
        for ring in polygon:
            for (lat_a, lon_a), (lat_b, lon_b) in _edges(ring):
                if (lat_a > latitude) != (lat_b > latitude):
                    at = lon_a + (latitude - lat_a) * (lon_b - lon_a) / (lat_b - lat_a)
                    if longitude < at:
                        crossings += 1
    return crossings % 2 == 1


def clearance(shape: Shape, point: Point, ellipsoid: Ellipsoid = WGS84) -> float:
    """Meters from the point to the boundary's nearest edge."""
    flat = _flat(point, ellipsoid)
    here = flat(point)
    return min(
        _segment_distance(here, flat(start), flat(end))
        for polygon in shape
        for ring in polygon
        for start, end in _edges(ring)
    )


def circle_within(
    shape: Shape,
    point: Point,
    radius_m: float,
    margin_m: float = 0.0,
    ellipsoid: Ellipsoid = WGS84,
) -> bool:
    """Whether the whole circle lies inside the unit by at least the margin (a
    simplified file's simplification error)."""
    if not math.isfinite(radius_m) or radius_m < 0 or not math.isfinite(margin_m) or margin_m < 0:
        raise ValueError("a radius and a margin are finite and zero or more")
    return inside(shape, point) and clearance(shape, point, ellipsoid) >= radius_m + margin_m


def enclosing_circle(shape: Shape, ellipsoid: Ellipsoid = WGS84) -> Circle:
    """The unit's corrected center and geographic radial: the smallest circle
    around its outer rings, its center moved onto the boundary when it falls
    outside the unit (the Quick Reference Guide, 1.6.2 and 1.6.3)."""
    vertices = [point for polygon in shape for point in polygon[0]]
    latitudes = [latitude for latitude, _ in vertices]
    longitudes = [longitude for _, longitude in vertices]
    middle = ((min(latitudes) + max(latitudes)) / 2, (min(longitudes) + max(longitudes)) / 2)
    flat = _flat(middle, ellipsoid)
    unflat = _unflat(middle, ellipsoid)
    hull = _hull([flat(point) for point in vertices])
    center, radius = _smallest_circle(hull)
    if inside(shape, unflat(center)):
        return Circle(unflat(center), radius, True)
    best, best_radius = None, math.inf
    candidates = []
    for polygon in shape:
        for ring in polygon:
            for start, end in _edges(ring):
                a, b = flat(start), flat(end)
                bound = max(_segment_distance(vertex, a, b) for vertex in hull)
                candidates.append((bound, a, b))
    for bound, a, b in sorted(candidates, key=lambda candidate: candidate[0]):
        if bound >= best_radius:
            break
        point, reach = _nearest_on_segment(a, b, hull)
        if reach < best_radius:
            best, best_radius = point, reach
    return Circle(unflat(best), best_radius, False)


def _rings(polygon: object) -> list:
    if not isinstance(polygon, Sequence) or not polygon:
        raise ValueError("a polygon is an outer ring and its holes")
    return list(polygon)


def _ring(coordinates: object) -> Ring:
    if not isinstance(coordinates, Sequence):
        raise ValueError("a ring is a list of [longitude, latitude] pairs")
    points = []
    for pair in coordinates:
        if not isinstance(pair, Sequence) or len(pair) < 2:
            raise ValueError("a ring is a list of [longitude, latitude] pairs")
        longitude, latitude = float(pair[0]), float(pair[1])
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("a vertex lies outside latitude and longitude")
        points.append((latitude, longitude))
    if points and points[0] == points[-1]:
        points.pop()  # GeoJSON closes a ring by repeating its first point
    if len(set(points)) < 3:
        raise ValueError("a ring has at least three distinct points")
    return tuple(points)


def _edges(ring: Ring) -> list[tuple[Point, Point]]:
    return [(ring[index - 1], ring[index]) for index in range(len(ring))]


def _flat(origin: Point, ellipsoid: Ellipsoid):
    """Local east-north meters around the origin, on the meters per degree there."""
    per_latitude, per_longitude = meters_per_degree(origin[0], ellipsoid)

    def flat(point: Point) -> tuple[float, float]:
        return (point[1] - origin[1]) * per_longitude, (point[0] - origin[0]) * per_latitude

    return flat


def _unflat(origin: Point, ellipsoid: Ellipsoid):
    per_latitude, per_longitude = meters_per_degree(origin[0], ellipsoid)

    def unflat(xy: tuple[float, float]) -> Point:
        return origin[0] + xy[1] / per_latitude, origin[1] + xy[0] / per_longitude

    return unflat


def _segment_distance(point, a, b) -> float:
    return math.dist(point, _closest(point, a, b))


def _closest(point, a, b) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    if length == 0:
        return a
    t = max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length))
    return a[0] + t * dx, a[1] + t * dy


def _reach(point, hull) -> float:
    return max(math.dist(point, vertex) for vertex in hull)


def _nearest_on_segment(a, b, hull) -> tuple[tuple[float, float], float]:
    """The point of a segment whose farthest hull vertex is nearest: the reach
    is convex along the segment, so a ternary search finds it."""
    low, high = 0.0, 1.0
    for _ in range(100):
        first, second = low + (high - low) / 3, high - (high - low) / 3
        at_first = _reach((a[0] + first * (b[0] - a[0]), a[1] + first * (b[1] - a[1])), hull)
        at_second = _reach((a[0] + second * (b[0] - a[0]), a[1] + second * (b[1] - a[1])), hull)
        if at_first <= at_second:
            high = second
        else:
            low = first
    t = (low + high) / 2
    point = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    return point, _reach(point, hull)


def _hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The convex hull's vertices (Andrew's monotone chain)."""
    points = sorted(set(points))
    if len(points) <= 2:
        return points

    def turn(o, a, b) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list = []
    for point in points:
        while len(lower) >= 2 and turn(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list = []
    for point in reversed(points):
        while len(upper) >= 2 and turn(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _smallest_circle(points: list[tuple[float, float]]) -> tuple[tuple[float, float], float]:
    """The smallest circle around the points (Welzl's incremental method, in the
    order given, so the result does not depend on chance)."""
    center, radius = points[0], 0.0
    for i, p in enumerate(points):
        if math.dist(center, p) <= radius * (1 + 1e-12) + 1e-9:
            continue
        center, radius = p, 0.0
        for j, q in enumerate(points[:i]):
            if math.dist(center, q) <= radius * (1 + 1e-12) + 1e-9:
                continue
            center = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
            radius = math.dist(p, q) / 2
            for r in points[:j]:
                if math.dist(center, r) <= radius * (1 + 1e-12) + 1e-9:
                    continue
                center = _circumcenter(p, q, r)
                radius = math.dist(center, p)
    return center, max(math.dist(center, point) for point in points)


def _circumcenter(a, b, c) -> tuple[float, float]:
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if d == 0:  # collinear: the circle on the farthest pair
        pair = max(((a, b), (a, c), (b, c)), key=lambda pq: math.dist(*pq))
        return (pair[0][0] + pair[1][0]) / 2, (pair[0][1] + pair[1][1]) / 2
    a2, b2, c2 = a[0] ** 2 + a[1] ** 2, b[0] ** 2 + b[1] ** 2, c[0] ** 2 + c[1] ** 2
    return (
        (a2 * (b[1] - c[1]) + b2 * (c[1] - a[1]) + c2 * (a[1] - b[1])) / d,
        (a2 * (c[0] - b[0]) + b2 * (a[0] - c[0]) + c2 * (b[0] - a[0])) / d,
    )
