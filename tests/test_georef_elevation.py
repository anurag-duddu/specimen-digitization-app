"""Elevations from GLO-30-style GeoTIFFs (GEO.md 11).

The tests write small GeoTIFFs in the pinned tiles' layout: tiled float32
elevations, deflated, with TIFF's floating-point predictor (Technical Note 3),
on a point raster. Variants cover byte order, stored tiles, no predictor, an
area raster and a missing-value marker.
"""

import hashlib
import math
import struct
import zlib
from dataclasses import replace

import pytest

from specimen_digitization.application import georef_elevation as elevation
from specimen_digitization.application.georef_datasets import dataset
from specimen_digitization.application.georef_elevation import (
    ElevationCoverageError,
    circle_bounds,
    elevation_range,
    pinned_elevation_range,
    read_pinned_tile,
    read_tile,
)
from specimen_digitization.application.georef_radius import meters_per_degree

STEP = 0.001  # degrees, about 110 m at the test latitudes


def encode_row(row, predictor, order):
    if not predictor:
        return struct.pack(f"{order}{len(row)}f", *row)
    big = struct.pack(f">{len(row)}f", *row)
    planes = b"".join(big[plane::4] for plane in range(4))
    return bytes(
        (planes[i] - (planes[i - 1] if i else 0)) & 0xFF for i in range(len(planes))
    )


def geotiff(values, *, north, west, tile=4, point=True, predictor=True, deflate=True,
            order="<", nodata=None, tiled=True):
    """A GeoTIFF of the grid `values` (rows north to south), first pixel at (north, west)."""
    height, width = len(values), len(values[0])
    across, down = math.ceil(width / tile), math.ceil(height / tile)
    blocks = []
    for tile_row in range(down):
        for tile_column in range(across):
            rows = []
            for r in range(tile):
                y = tile_row * tile + r
                row = [
                    values[y][x] if y < height and x < width else 0.0
                    for x in (tile_column * tile + c for c in range(tile))
                ]
                rows.append(encode_row(row, predictor, order))
            raw = b"".join(rows)
            blocks.append(zlib.compress(raw) if deflate else raw)
    shift = 0.0 if point else 0.5
    keys = (1, 1, 0, 1, 1025, 0, 1, 2 if point else 1)
    entries = [
        (256, 3, (width,)), (257, 3, (height,)), (258, 3, (32,)), (259, 3, (8 if deflate else 1,)),
        (262, 3, (1,)), (277, 3, (1,)), (284, 3, (1,)), (317, 3, (3 if predictor else 1,)),
        (339, 3, (3,)), (33550, 12, (STEP, STEP, 0.0)),
        (33922, 12, (0.0, 0.0, 0.0, west - shift * STEP, north + shift * STEP, 0.0)),
        (34735, 3, keys),
    ]
    if tiled:
        entries += [(322, 3, (tile,)), (323, 3, (tile,)), (324, 4, None), (325, 4, None)]
    else:
        entries += [(273, 4, (0,)), (279, 4, (0,))]
    if nodata is not None:
        entries.append((42113, 2, f"{nodata}\0".encode()))
    entries.sort()
    codes = {2: "s", 3: "H", 4: "I", 12: "d"}
    ifd_size = 2 + 12 * len(entries) + 4
    extra = bytearray()
    data_start = 8 + ifd_size
    counts = [len(block) for block in blocks]
    first_block = data_start + 4096  # room for tag values
    offsets = list(running_sum([first_block] + counts[:-1]))
    ifd = bytearray(struct.pack(f"{order}H", len(entries)))
    for tag, kind, value in entries:
        if tag == 324:
            value = tuple(offsets)
        elif tag == 325:
            value = tuple(counts)
        payload = value if kind == 2 else struct.pack(f"{order}{len(value)}{codes[kind]}", *value)
        number = len(value)
        if len(payload) <= 4:
            field = payload.ljust(4, b"\0")
        else:
            field = struct.pack(f"{order}I", data_start + len(extra))
            extra += payload + (b"\0" if len(payload) % 2 else b"")
        ifd += struct.pack(f"{order}HHI", tag, kind, number) + field
    ifd += struct.pack(f"{order}I", 0)
    header = (b"II*\0" if order == "<" else b"MM\0*") + struct.pack(f"{order}I", 8)
    body = header + bytes(ifd) + bytes(extra)
    assert len(body) <= first_block
    return body.ljust(first_block, b"\0") + b"".join(blocks)


def running_sum(values):
    total = 0
    for value in values:
        total += value
        yield total


def grid(height=10, width=10, base=0.0):
    return [[base + 100.0 * row + column for column in range(width)] for row in range(height)]


def center_of(row, column, north=7.0, west=125.0):
    return north - row * STEP, west + column * STEP


def test_a_pixel_under_the_point_across_internal_tiles():
    tile = read_tile(geotiff(grid(), north=7.0, west=125.0))
    for row, column in ((0, 0), (5, 6), (9, 9), (3, 8)):
        assert elevation_range([tile], center_of(row, column), 0.0) == (
            100.0 * row + column,
            100.0 * row + column,
        )


def test_the_range_over_a_circle_includes_every_intersected_dem_cell():
    tile = read_tile(geotiff(grid(), north=7.0, west=125.0))
    # The circle clips the adjacent cells' corners, even when their centers
    # lie beyond it. Omitting them could miss the high or low ground.
    assert elevation_range([tile], center_of(5, 5), 112.0) == (404.0, 606.0)
    assert elevation_range([tile], center_of(5, 5), 200.0) == (304.0, 706.0)


def test_a_circle_smaller_than_a_pixel_takes_the_pixel_under_its_center():
    tile = read_tile(geotiff(grid(), north=7.0, west=125.0))
    latitude, longitude = center_of(4, 4)
    assert elevation_range([tile], (latitude - 0.0003, longitude + 0.0004), 10.0) == (404.0, 404.0)


@pytest.mark.parametrize(
    "options",
    [
        {"order": ">"},
        {"deflate": False},
        {"predictor": False},
        {"order": ">", "predictor": False, "deflate": False},
    ],
)
def test_byte_order_compression_and_predictor_variants_read_alike(options):
    tile = read_tile(geotiff(grid(), north=7.0, west=125.0, **options))
    assert elevation_range([tile], center_of(5, 5), 112.0) == (404.0, 606.0)


def test_an_area_raster_puts_the_first_pixel_center_half_a_step_in():
    tile = read_tile(geotiff(grid(), north=7.0, west=125.0, point=False))
    assert (tile.north, tile.west) == pytest.approx((7.0, 125.0))
    assert elevation_range([tile], center_of(2, 3), 0.0) == (203.0, 203.0)


def test_a_missing_value_under_the_circle_blocks_an_extremum():
    values = grid()
    values[4][5] = -32767.0
    tile = read_tile(geotiff(values, north=7.0, west=125.0, nodata=-32767))
    with pytest.raises(ElevationCoverageError, match="no-data"):
        elevation_range([tile], center_of(5, 5), 112.0)


def test_a_circle_needs_every_tile_it_touches():
    west_tile = read_tile(geotiff(grid(), north=7.0, west=125.0))
    east_tile = read_tile(geotiff(grid(base=10_000.0), north=7.0, west=125.0 + 10 * STEP))
    edge = center_of(5, 9)
    with pytest.raises(ElevationCoverageError):
        elevation_range([west_tile], edge, 200.0)
    assert elevation_range([west_tile, east_tile], edge, 112.0) == (408.0, 10_600.0)


def test_a_gap_between_tiles_blocks_extrema_even_when_center_and_corners_are_covered():
    west = read_tile(geotiff(grid(width=3), north=7.005, west=124.998))
    east = read_tile(geotiff(grid(width=3), north=7.005, west=125.0015))
    with pytest.raises(ElevationCoverageError, match="beyond the tiles"):
        elevation_range([west, east], (7.0, 125.0), 150.0)


def test_shared_bounds_select_the_tile_across_a_latitude_adjusted_seam():
    center, radius = (14.5, -90.87603), 13_360.0
    center_scale_west = center[1] - radius / meters_per_degree(center[0])[1]
    assert center_scale_west > -91  # center-only scale misses the west tile
    south, west, north, east = circle_bounds(center, radius)
    assert south < center[0] < north and west < -91 < east


def test_no_manifest_tile_is_a_coverage_gap():
    with pytest.raises(ElevationCoverageError, match="at least one DEM"):
        pinned_elevation_range([], center_of(5, 5), 10)


def test_production_requires_exact_pinned_dem_bytes():
    data = geotiff(grid(), north=7.0, west=125.0)
    with pytest.raises(ValueError, match="not the reviewed file"):
        read_pinned_tile("copernicus-glo30/N07_00_E125_00", data)
    with pytest.raises(ValueError, match="pinned"):
        pinned_elevation_range([read_tile(data)], center_of(5, 5), 0)


def test_a_verified_manifest_tile_flows_to_the_production_extrema(monkeypatch):
    data = geotiff(grid(), north=7.0, west=125.0)
    dataset_id = "copernicus-glo30/N07_00_E125_00"
    synthetic_pin = replace(dataset(dataset_id), size=len(data), sha256=hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(elevation, "dataset", lambda key: synthetic_pin if key == dataset_id else dataset(key))
    tile = read_pinned_tile(dataset_id, data)
    assert pinned_elevation_range([tile], center_of(5, 5), 112) == (404, 606)
    tile.data += b" "
    with pytest.raises(ValueError, match="do not match"):
        pinned_elevation_range([tile], center_of(5, 5), 112)


@pytest.mark.parametrize(
    "data",
    [
        b"not a tiff at all",
        geotiff(grid(), north=7.0, west=125.0, tiled=False),
    ],
)
def test_files_that_are_not_tiled_float_geotiffs_are_refused(data):
    with pytest.raises(ValueError):
        read_tile(data)


def test_a_negative_radius_is_refused():
    tile = read_tile(geotiff(grid(), north=7.0, west=125.0))
    with pytest.raises(ValueError):
        elevation_range([tile], center_of(5, 5), -1.0)
