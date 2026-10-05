"""Elevations from the pinned Copernicus GLO-30 tiles (GEO.md 11, D11).

Where a label states no elevation, the elevation fields are derived as the
lowest and highest ground within the uncertainty circle (G37; PLAN 4.8). A tile
is the verified bytes of one pinned file (section 3). The module reads the
GeoTIFF's structure and decodes only the internal tiles and rows a circle
touches. It sends nothing.
"""

from __future__ import annotations

import itertools
import hashlib
import math
import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field

from .georef_datasets import dataset, verified
from .georef_radius import WGS84, Ellipsoid, meters_per_degree

Point = tuple[float, float]  # latitude, longitude


class ElevationCoverageError(ValueError):
    """A valid location has no complete, usable DEM coverage for its circle."""

DEFLATE = (8, 32946)  # Adobe's code and the older one
NO_COMPRESSION = 1
FLOAT_PREDICTOR = 3
PIXEL_IS_POINT = 2  # GTRasterTypeGeoKey: a pixel's value is at its center point
TAGS = {
    "width": 256,
    "height": 257,
    "bits": 258,
    "compression": 259,
    "samples": 277,
    "planar": 284,
    "predictor": 317,
    "tile_width": 322,
    "tile_height": 323,
    "tile_offsets": 324,
    "tile_counts": 325,
    "sample_format": 339,
    "pixel_scale": 33550,
    "tiepoint": 33922,
    "geokeys": 34735,
    "nodata": 42113,
}
TYPES = {1: "B", 2: "s", 3: "H", 4: "I", 11: "f", 12: "d", 16: "Q"}
WIDTHS = {"B": 1, "s": 1, "H": 2, "I": 4, "f": 4, "d": 8, "Q": 8}


@dataclass
class Tile:
    """One GeoTIFF's first image: a grid of float32 elevations in meters."""

    data: bytes
    order: str
    width: int
    height: int
    tile_width: int
    tile_height: int
    offsets: tuple[int, ...]
    counts: tuple[int, ...]
    compressed: bool
    predicted: bool
    north: float  # latitude of the first row's pixel centers
    west: float  # longitude of the first column's pixel centers
    step_latitude: float
    step_longitude: float
    nodata: float | None
    dataset_id: str | None = None
    _inflated: dict[int, bytes] = field(default_factory=dict, repr=False)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """South, west, north, east edges of the raster cells."""
        return (
            self.north - (self.height - 0.5) * self.step_latitude,
            self.west - self.step_longitude / 2,
            self.north + self.step_latitude / 2,
            self.west + (self.width - 0.5) * self.step_longitude,
        )

    def covers(self, latitude: float, longitude: float) -> bool:
        """Whether the point lies within the grid's cells, each half a step
        around its pixel center."""
        south, west, north, east = self.bounds
        return (
            south <= latitude <= north and west <= longitude <= east
        )

    def value(self, row: int, column: int) -> float | None:
        return self.row(row, column, column)[column]

    def row(self, row: int, first: int, last: int) -> dict[int, float | None]:
        """Columns `first` to `last` of one row, decoding only the internal
        tiles they fall in; a missing value is None."""
        if not (0 <= row < self.height and 0 <= first <= last < self.width):
            raise ValueError("a requested DEM row or column lies outside the tile")
        across = math.ceil(self.width / self.tile_width)
        tile_row, offset = divmod(row, self.tile_height)
        values: dict[int, float | None] = {}
        for tile_column in range(first // self.tile_width, last // self.tile_width + 1):
            decoded = self._tile_row(tile_row * across + tile_column, offset)
            start = tile_column * self.tile_width
            for column in range(max(first, start), min(last, start + self.tile_width - 1) + 1):
                value = decoded[column - start]
                missing = value is None or (self.nodata is not None and value == self.nodata)
                values[column] = None if missing else value
        return values

    def _tile_row(self, index: int, offset: int) -> list[float | None]:
        raw = self._inflate(index)
        size = self.tile_width * 4
        chunk = raw[offset * size : (offset + 1) * size]
        if len(chunk) != size:
            raise ValueError("an internal tile is shorter than its dimensions")
        if self.predicted:
            # TIFF's floating-point predictor: the row's bytes are grouped by
            # significance, most significant first, then differenced byte by byte.
            summed = bytes(total & 0xFF for total in itertools.accumulate(chunk))
            ordered = bytearray(size)
            for plane in range(4):
                ordered[plane::4] = summed[plane * self.tile_width : (plane + 1) * self.tile_width]
            numbers = struct.unpack(f">{self.tile_width}f", ordered)
        else:
            numbers = struct.unpack(f"{self.order}{self.tile_width}f", chunk)
        return [None if math.isnan(number) else number for number in numbers]

    def _inflate(self, index: int) -> bytes:
        if index not in self._inflated:
            start, length = self.offsets[index], self.counts[index]
            block = self.data[start : start + length]
            try:
                raw = zlib.decompress(block) if self.compressed else block
            except zlib.error as error:
                raise ValueError("an internal tile does not inflate") from error
            if len(raw) != self.tile_width * self.tile_height * 4:
                raise ValueError("an internal tile has the wrong decoded size")
            if len(self._inflated) >= 16:
                self._inflated.pop(next(iter(self._inflated)))
            self._inflated[index] = raw
        return self._inflated[index]


def read_pinned_tile(dataset_id: str, data: bytes) -> Tile:
    """Read an exact reviewed Copernicus GLO-30 tile, never an unpinned DEM."""
    try:
        entry = dataset(dataset_id)
    except KeyError as error:
        raise ValueError("the DEM dataset is not pinned") from error
    if not entry.id.startswith("copernicus-glo30/"):
        raise ValueError("the dataset is not a pinned Copernicus DEM")
    verified(entry, data)
    tile = read_tile(data)
    tile.dataset_id = dataset_id
    return tile


def read_tile(data: bytes) -> Tile:
    """The first image of a GLO-30 GeoTIFF: tiled, float32, one sample per pixel,
    deflated or stored, with or without the floating-point predictor."""
    if data[:4] not in (b"II*\0", b"MM\0*") or len(data) < 8:
        raise ValueError("not a TIFF file")
    order = "<" if data[:2] == b"II" else ">"
    tags = _tags(data, order, struct.unpack(f"{order}I", data[4:8])[0])

    def one(name: str, default: object = None) -> object:
        values = tags.get(TAGS[name])
        return values[0] if values else default

    if tags.get(TAGS["tile_offsets"]) is None:
        raise ValueError("only tiled GeoTIFFs are read")
    if (one("bits"), one("sample_format"), one("samples", 1), one("planar", 1)) != (32, 3, 1, 1):
        raise ValueError("only one float32 sample per pixel is read")
    compression, predictor = one("compression", 1), one("predictor", 1)
    if compression not in (*DEFLATE, NO_COMPRESSION) or predictor not in (1, FLOAT_PREDICTOR):
        raise ValueError(
            "only deflated or stored tiles, with or without the float predictor, are read"
        )
    scale, tiepoint = tags.get(TAGS["pixel_scale"]), tags.get(TAGS["tiepoint"])
    if not scale or not tiepoint or len(scale) < 2 or len(tiepoint) < 6:
        raise ValueError("a GeoTIFF needs its pixel scale and tie point")
    keys = tags.get(TAGS["geokeys"]) or ()
    raster_type = next(
        (keys[i + 3] for i in range(4, len(keys) - 3, 4) if keys[i] == 1025), 1
    )
    step_longitude, step_latitude = float(scale[0]), float(scale[1])
    # The tie point maps raster (i, j) to (longitude, latitude). A point-registered
    # grid's first pixel center is the tie point; an area grid's is half a step in.
    column, row, longitude, latitude = tiepoint[0], tiepoint[1], tiepoint[3], tiepoint[4]
    shift = 0.0 if raster_type == PIXEL_IS_POINT else 0.5
    nodata_text = tags.get(TAGS["nodata"])
    offsets = tuple(int(value) for value in tags[TAGS["tile_offsets"]])
    counts = tuple(int(value) for value in tags.get(TAGS["tile_counts"]) or ())
    width, height = int(one("width") or 0), int(one("height") or 0)
    tile_width, tile_height = int(one("tile_width") or 0), int(one("tile_height") or 0)
    if not all(math.isfinite(value) and value > 0 for value in (step_longitude, step_latitude)):
        raise ValueError("a DEM needs positive finite pixel scales")
    if not all(value > 0 for value in (width, height, tile_width, tile_height)):
        raise ValueError("a DEM needs positive raster and internal tile dimensions")
    expected_tiles = math.ceil(width / tile_width) * math.ceil(height / tile_height)
    if len(offsets) != expected_tiles or len(counts) != expected_tiles or any(
        o < 8 or c <= 0 or o + c > len(data) for o, c in zip(offsets, counts)
    ):
        raise ValueError("the internal tiles' offsets and sizes do not fit the file")
    if not all(math.isfinite(value) for value in (longitude, latitude, column, row)):
        raise ValueError("a DEM needs finite geographic tie points")
    return Tile(
        data=data,
        order=order,
        width=width,
        height=height,
        tile_width=tile_width,
        tile_height=tile_height,
        offsets=offsets,
        counts=counts,
        compressed=compression in DEFLATE,
        predicted=predictor == FLOAT_PREDICTOR,
        north=latitude - (shift - row) * step_latitude,
        west=longitude + (shift - column) * step_longitude,
        step_latitude=step_latitude,
        step_longitude=step_longitude,
        nodata=float(nodata_text.strip("\0 ")) if isinstance(nodata_text, str) else None,
    )


def elevation_range(
    tiles: Sequence[Tile], center: Point, radius_m: float, ellipsoid: Ellipsoid = WGS84
) -> tuple[float, float]:
    """Conservative DEM extrema over every cell intersecting the circle.

    Missing cells or any no-data value under the circle refuse the derivation;
    skipping either would make the extrema appear better supported than they are.
    A bounding rectangle is required to be covered, so this can decline a circle
    whose corners are outside available tiles even when the circle itself fits.
    """
    if not math.isfinite(radius_m) or radius_m < 0:
        raise ValueError("a radius is finite and zero or more")
    if not tiles:
        raise ElevationCoverageError("an elevation requires at least one DEM tile")
    latitude, longitude = center
    south, west, north, east = circle_bounds(center, radius_m, ellipsoid)
    min_latitude_scale = meters_per_degree(0.0, ellipsoid)[0] * (1 - 1e-9)
    _, per_longitude = meters_per_degree(max(abs(south), abs(north)), ellipsoid)
    if not _covered_box(tiles, south, west, north, east):
        raise ElevationCoverageError("the circle reaches beyond the tiles given")
    low, high = math.inf, -math.inf
    found = False
    for tile in tiles:
        half_lat, half_lon = tile.step_latitude / 2, tile.step_longitude / 2
        first_row = max(0, math.ceil((tile.north - half_lat - north) / tile.step_latitude))
        last_row = min(
            tile.height - 1,
            math.floor((tile.north + half_lat - south) / tile.step_latitude),
        )
        first_column = max(
            0, math.ceil((west - half_lon - tile.west) / tile.step_longitude)
        )
        last_column = min(
            tile.width - 1, math.floor((east + half_lon - tile.west) / tile.step_longitude),
        )
        if first_row > last_row or first_column > last_column:
            continue
        for row in range(first_row, last_row + 1):
            values = tile.row(row, first_column, last_column)
            dy = max(abs(tile.north - row * tile.step_latitude - latitude) - half_lat, 0.0)
            for column in range(first_column, last_column + 1):
                dx = max(abs(tile.west + column * tile.step_longitude - longitude) - half_lon, 0.0)
                if math.hypot(dx * per_longitude, dy * min_latitude_scale) <= radius_m + 1e-9:
                    value = values[column]
                    if value is None or not math.isfinite(value):
                        raise ElevationCoverageError("the DEM circle touches a no-data cell")
                    low, high = min(low, value), max(high, value)
                    found = True
    if not found:
        raise ElevationCoverageError("no elevation under the circle")
    return low, high


def circle_bounds(
    center: Point, radius_m: float, ellipsoid: Ellipsoid = WGS84
) -> tuple[float, float, float, float]:
    """Conservative south, west, north, east bounds for a geodesic circle.

    Latitude uses the minimum meridional scale and longitude the smallest
    parallel scale over the latitude band. The adapter must select tiles using
    these same bounds before `elevation_range` checks complete cell coverage.
    """
    if not math.isfinite(radius_m) or radius_m < 0:
        raise ValueError("a radius is finite and zero or more")
    latitude, longitude = center
    if not (math.isfinite(latitude) and -90 <= latitude <= 90
            and math.isfinite(longitude) and -180 <= longitude <= 180):
        raise ValueError("a center has finite geographic coordinates")
    min_latitude_scale = meters_per_degree(0.0, ellipsoid)[0] * (1 - 1e-9)
    reach_latitude = radius_m / min_latitude_scale
    if abs(latitude) + reach_latitude >= 90:
        raise ElevationCoverageError("a DEM circle reaches a pole")
    _, per_longitude = meters_per_degree(abs(latitude) + reach_latitude, ellipsoid)
    reach_longitude = radius_m / per_longitude
    south, west = latitude - reach_latitude, longitude - reach_longitude
    north, east = latitude + reach_latitude, longitude + reach_longitude
    if west < -180 or east > 180:
        raise ElevationCoverageError("a DEM circle crosses the antimeridian")
    return south, west, north, east


def pinned_elevation_range(
    tiles: Sequence[Tile], center: Point, radius_m: float, ellipsoid: Ellipsoid = WGS84
) -> tuple[float, float]:
    """Production entry point: extrema only from digest-checked GLO-30 tiles."""
    if not tiles:
        raise ElevationCoverageError("an elevation requires at least one DEM tile")
    if any(tile.dataset_id is None for tile in tiles):
        raise ValueError("all elevation tiles must be pinned Copernicus GLO-30 files")
    if len({tile.dataset_id for tile in tiles}) != len(tiles):
        raise ValueError("an elevation tile is repeated")
    for tile in tiles:
        try:
            entry = dataset(tile.dataset_id)
        except KeyError as error:
            raise ValueError("the DEM dataset is not pinned") from error
        if not entry.id.startswith("copernicus-glo30/"):
            raise ValueError("the dataset is not a pinned Copernicus DEM")
        if len(tile.data) != entry.size or hashlib.sha256(tile.data).hexdigest() != entry.sha256:
            raise ValueError("the DEM bytes do not match the pinned tile")
    return elevation_range(tiles, center, radius_m, ellipsoid)


def _covered_box(
    tiles: Sequence[Tile], south: float, west: float, north: float, east: float
) -> bool:
    """Whether the union of rectangular tile footprints covers the box."""
    if south == north and west == east:
        return any(tile.covers(south, west) for tile in tiles)
    latitudes = {south, north}
    longitudes = {west, east}
    for tile in tiles:
        tile_south, tile_west, tile_north, tile_east = tile.bounds
        latitudes.update(value for value in (tile_south, tile_north) if south < value < north)
        longitudes.update(value for value in (tile_west, tile_east) if west < value < east)
    ys, xs = sorted(latitudes), sorted(longitudes)
    y_intervals = list(zip(ys, ys[1:])) if len(ys) > 1 else [(south, north)]
    x_intervals = list(zip(xs, xs[1:])) if len(xs) > 1 else [(west, east)]
    return all(
        any(tile.covers((y0 + y1) / 2, (x0 + x1) / 2) for tile in tiles)
        for y0, y1 in y_intervals for x0, x1 in x_intervals
    )


def _tags(data: bytes, order: str, offset: int) -> dict[int, tuple | str]:
    """The first image file directory's tags and their values."""
    if not 8 <= offset <= len(data) - 2:
        raise ValueError("the first image directory lies outside the file")
    (count,) = struct.unpack(f"{order}H", data[offset : offset + 2])
    tags: dict[int, tuple | str] = {}
    for n in range(count):
        entry = data[offset + 2 + 12 * n : offset + 14 + 12 * n]
        if len(entry) != 12:
            raise ValueError("an image directory entry is cut short")
        tag, kind, number = struct.unpack(f"{order}HHI", entry[:8])
        code = TYPES.get(kind)
        if code is None:
            continue
        size = WIDTHS[code] * number
        if size <= 4:
            raw = entry[8 : 8 + size]
        else:
            (start,) = struct.unpack(f"{order}I", entry[8:12])
            raw = data[start : start + size]
            if len(raw) != size:
                raise ValueError("a tag's values lie outside the file")
        if code == "s":
            tags[tag] = raw.rstrip(b"\0").decode("latin-1")
        else:
            tags[tag] = struct.unpack(f"{order}{number}{code}", raw)
    return tags
