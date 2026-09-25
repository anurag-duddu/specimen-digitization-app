"""Elevations from the pinned Copernicus GLO-30 tiles (GEO.md 11, D11).

Where a label states no elevation, the elevation fields are derived as the
lowest and highest ground within the uncertainty circle (G37; PLAN 4.8). A tile
is the verified bytes of one pinned file (section 3). The module reads the
GeoTIFF's structure and decodes only the internal tiles and rows a circle
touches. It sends nothing.
"""

from __future__ import annotations

import itertools
import math
import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field

from .georef_radius import WGS84, Ellipsoid, meters_per_degree

Point = tuple[float, float]  # latitude, longitude

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
    _inflated: dict[int, bytes] = field(default_factory=dict, repr=False)

    def covers(self, latitude: float, longitude: float) -> bool:
        """Whether the point lies within the grid's cells, each half a step
        around its pixel center."""
        south = self.north - (self.height - 0.5) * self.step_latitude
        east = self.west + (self.width - 0.5) * self.step_longitude
        return (
            south <= latitude <= self.north + self.step_latitude / 2
            and self.west - self.step_longitude / 2 <= longitude <= east
        )

    def value(self, row: int, column: int) -> float | None:
        return self.row(row, column, column)[column]

    def row(self, row: int, first: int, last: int) -> dict[int, float | None]:
        """Columns `first` to `last` of one row, decoding only the internal
        tiles they fall in; a missing value is None."""
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
                self._inflated[index] = zlib.decompress(block) if self.compressed else block
            except zlib.error as error:
                raise ValueError("an internal tile does not inflate") from error
        return self._inflated[index]


def read_tile(data: bytes) -> Tile:
    """The first image of a GLO-30 GeoTIFF: tiled, float32, one sample per pixel,
    deflated or stored, with or without the floating-point predictor."""
    if data[:4] not in (b"II*\0", b"MM\0*"):
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
    if len(counts) != len(offsets) or any(o + c > len(data) for o, c in zip(offsets, counts)):
        raise ValueError("the internal tiles' offsets and sizes do not fit the file")
    return Tile(
        data=data,
        order=order,
        width=int(one("width")),
        height=int(one("height")),
        tile_width=int(one("tile_width")),
        tile_height=int(one("tile_height")),
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
    """The lowest and highest elevation among the pixels whose centers lie in
    the circle, or the pixel under the center when none does. The tiles must
    cover the whole circle."""
    if not math.isfinite(radius_m) or radius_m < 0:
        raise ValueError("a radius is finite and zero or more")
    latitude, longitude = center
    per_latitude, per_longitude = meters_per_degree(latitude, ellipsoid)
    reach_latitude, reach_longitude = radius_m / per_latitude, radius_m / per_longitude
    corners = [
        (latitude + dy, longitude + dx)
        for dy in (-reach_latitude, reach_latitude)
        for dx in (-reach_longitude, reach_longitude)
    ]
    if not all(any(tile.covers(*corner) for tile in tiles) for corner in [center, *corners]):
        raise ValueError("the circle reaches beyond the tiles given")
    found: list[float] = []
    for tile in tiles:
        first_row = max(0, math.ceil((tile.north - latitude - reach_latitude) / tile.step_latitude))
        last_row = min(
            tile.height - 1,
            math.floor((tile.north - latitude + reach_latitude) / tile.step_latitude),
        )
        first_column = max(
            0, math.ceil((longitude - reach_longitude - tile.west) / tile.step_longitude)
        )
        last_column = min(
            tile.width - 1,
            math.floor((longitude + reach_longitude - tile.west) / tile.step_longitude),
        )
        if first_row > last_row or first_column > last_column:
            continue
        for row in range(first_row, last_row + 1):
            values = tile.row(row, first_column, last_column)
            dy = (tile.north - row * tile.step_latitude - latitude) * per_latitude
            for column in range(first_column, last_column + 1):
                dx = (tile.west + column * tile.step_longitude - longitude) * per_longitude
                if math.hypot(dx, dy) <= radius_m and values[column] is not None:
                    found.append(values[column])
    if not found:
        found = _under(tiles, center)
    if not found:
        raise ValueError("no elevation under the circle")
    return min(found), max(found)


def _under(tiles: Sequence[Tile], center: Point) -> list[float]:
    """The value of the pixel whose cell holds the point."""
    latitude, longitude = center
    for tile in tiles:
        if tile.covers(latitude, longitude):
            row = round((tile.north - latitude) / tile.step_latitude)
            column = round((longitude - tile.west) / tile.step_longitude)
            row, column = min(max(row, 0), tile.height - 1), min(max(column, 0), tile.width - 1)
            value = tile.value(row, column)
            return [] if value is None else [value]
    return []


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
