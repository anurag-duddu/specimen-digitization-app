"""Reference datasets in the project's storage, named by digest (GEO.md 3)."""

import hashlib
import re

import pytest

from specimen_digitization.application.georef_datasets import (
    COD_AB_GTM_CREDIT,
    GEOBOUNDARIES_PHL_CREDIT,
    GLO30_CREDIT,
    MANIFEST,
    SIMPLIFIED_MARGIN_M,
    Dataset,
    DigestMismatch,
    boundary_files,
    dataset,
    elevation_tile,
    geonames_dump,
    verified,
)


def test_every_entry_is_named_by_the_digest_of_its_bytes():
    ids = [entry.id for entry in MANIFEST]
    assert len(ids) == len(set(ids))
    for entry in MANIFEST:
        assert re.fullmatch(r"[0-9a-f]{64}", entry.sha256)
        assert entry.object_name == f"application/sha256/{entry.sha256}"
        assert entry.size > 0
        assert entry.source_url.startswith("https://")
        assert entry.license and entry.license_url.startswith("https://")
        assert entry.credit and re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry.retrieved)
        # The runtime configures the bucket; the manifest never names one.
        assert "gs://" not in entry.source_url and "firebasestorage" not in entry.source_url


def test_the_pilot_needs_three_glo30_tiles():
    tiles = {entry.id: entry for entry in MANIFEST if entry.id.startswith("copernicus-glo30/")}
    assert set(tiles) == {
        "copernicus-glo30/N07_00_E125_00",
        "copernicus-glo30/N06_00_E125_00",
        "copernicus-glo30/N14_00_W091_00",
    }
    talomo = tiles["copernicus-glo30/N07_00_E125_00"]
    assert talomo.source_url == (
        "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N07_00_E125_00_DEM/"
        "Copernicus_DSM_COG_10_N07_00_E125_00_DEM.tif"
    )
    assert (talomo.size, talomo.sha256) == (
        45446782,
        "7a9189637a5af9677a92e765b9448bdfe425383fae8e39a6808a96b8fe8f19d0",  # pragma: allowlist secret (public file digest)
    )
    assert all(tile.credit == GLO30_CREDIT and tile.stable_source for tile in tiles.values())
    assert {tile.content_type for tile in tiles.values()} == {"image/tiff"}
    assert GLO30_CREDIT == (
        "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and "
        "Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; "
        "all rights reserved"
    )


@pytest.mark.parametrize(
    ("latitude", "longitude", "tile"),
    [
        (7.0364, 125.3125, "copernicus-glo30/N07_00_E125_00"),  # Mount Talomo
        (6.9875, 125.2708, "copernicus-glo30/N06_00_E125_00"),  # Mount Apo
        (14.502, -90.954, "copernicus-glo30/N14_00_W091_00"),  # Yepocapa
    ],
)
def test_a_point_reads_the_tile_of_its_one_degree_cell(latitude, longitude, tile):
    assert elevation_tile(latitude, longitude) == dataset(tile)


def test_a_point_outside_the_manifest_has_no_tile():
    assert elevation_tile(63.0692, -151.0064) is None  # Denali
    assert elevation_tile(-0.5, -78.5) is None


def test_geonames_dumps_are_pinned_as_the_only_copy():
    philippines, guatemala = geonames_dump("PH"), geonames_dump("GT")
    assert (philippines.id, philippines.size, philippines.sha256) == (
        "geonames/PH/2026-09-24",
        2555475,
        "7a8dc145e57ea42c26b35393a281f248ff35e70aaf794eed20c989ff2d718759",  # pragma: allowlist secret (public file digest)
    )
    assert (guatemala.id, guatemala.size, guatemala.sha256) == (
        "geonames/GT/2026-09-24",
        1047133,
        "24965821b5541833efb63ced996ac9a508feb049ec02442727f28cbdf15dfe96",  # pragma: allowlist secret (public file digest)
    )
    for dump in (philippines, guatemala):
        assert dump.source_url == f"https://download.geonames.org/export/dump/{dump.id[9:11]}.zip"
        assert dump.stable_source is False  # GeoNames keeps no archive
        assert "GeoNames" in dump.credit and dump.license == "CC BY 4.0"
        assert dump.content_type == "application/zip"
    assert geonames_dump("US") is None


def test_the_philippines_boundaries_are_geoboundaries_simplified_files():
    files = boundary_files("PH")
    assert [(entry.id, entry.size, entry.sha256) for entry in files] == [
        (
            "geoboundaries/PH/ADM1/41af8f1",
            2812222,
            "8eeef6a9a525a81a647dcaac85e1337b990fc527c4a0e9c70556d5b0905be087",  # pragma: allowlist secret (public file digest)
        ),
        (
            "geoboundaries/PH/ADM2/41af8f1",
            3140454,
            "fa77b9f17db2e419acaae714a935f7812be4409e2983675d34020e8426a3e189",  # pragma: allowlist secret (public file digest)
        ),
        (
            "geoboundaries/PH/ADM3/9469f09",
            7071267,
            "2ece3d44a5c6a2afb385ffbf3a6b88d83e4d3a3e7eed9a52cb3be1bc59e289fc",  # pragma: allowlist secret (public file digest)
        ),
    ]
    for entry in files:
        level, commit = entry.id.split("/")[2:]
        assert entry.source_url == (
            f"https://github.com/wmgeolab/geoBoundaries/raw/{commit}/releaseData/gbOpen/PHL/"
            f"{level}/geoBoundaries-PHL-{level}_simplified.geojson"
        )
        assert entry.margin_m == SIMPLIFIED_MARGIN_M == 101.2
        assert entry.stable_source  # a release commit keeps its bytes
        assert entry.content_type == "application/geo+json"
        assert entry.credit == GEOBOUNDARIES_PHL_CREDIT
        assert (entry.license, entry.license_url) == (
            "CC BY 3.0 IGO",
            "https://creativecommons.org/licenses/by/3.0/igo/",
        )
    assert GEOBOUNDARIES_PHL_CREDIT.startswith(
        "National Mapping and Resource Information Authority (NAMRIA), Philippines Statistics "
        "Authority (PSA), OCHA Philippines, via geoBoundaries"
    )


def test_the_guatemala_boundaries_are_conreds_cod_ab_file_pinned_as_the_only_copy():
    (entry,) = boundary_files("GT")
    assert (entry.id, entry.size, entry.sha256) == (
        "cod-ab/GT/2026-09-24",
        3366983,
        "f178eda98c46329380bdbb43f0637b4c43535bc843de6a0b8b960193b8f4363f",  # pragma: allowlist secret (public file digest)
    )
    assert entry.source_url.startswith("https://data.humdata.org/dataset/")
    assert entry.source_url.endswith("/gtm_admin_boundaries.geojson.zip")
    assert entry.margin_m == 0  # full resolution
    assert entry.stable_source is False  # HDX serves only its latest file
    assert entry.content_type == "application/zip"
    assert entry.credit == COD_AB_GTM_CREDIT and entry.license == "CC BY 3.0 IGO"
    assert COD_AB_GTM_CREDIT.startswith(
        "Coordinadora Nacional Para La Reducción De Desastres (CONRED)"
    )
    assert boundary_files("US") == ()


def test_only_the_simplified_boundary_files_carry_a_margin():
    assert {entry.id for entry in MANIFEST if entry.margin_m} == {
        entry.id for entry in boundary_files("PH")
    }


def test_no_boundary_comes_from_openstreetmap_or_gadm():
    # The coordinator's rulings: Guatemala's departments never from geoBoundaries'
    # OpenStreetMap file (ODbL), and GADM not at all.
    for entry in MANIFEST:
        assert "ODbL" not in entry.license
        assert "gadm" not in entry.source_url.lower()
        assert "/GTM/" not in entry.source_url


def test_only_the_reviewed_bytes_are_read():
    data = b"elevation tile bytes"
    reviewed = Dataset(
        id="test/tile",
        purpose="test",
        source_url="https://example.org/tile.tif",
        retrieved="2026-09-24",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        license="test",
        license_url="https://example.org/licence",
        credit="test",
        stable_source=True,
        content_type="image/tiff",
    )
    assert verified(reviewed, data) == data
    with pytest.raises(DigestMismatch):
        verified(reviewed, data + b"!")
    with pytest.raises(DigestMismatch):
        verified(reviewed, b"elevation tile byteZ")
    with pytest.raises(DigestMismatch):
        verified(dataset("copernicus-glo30/N06_00_E125_00"), data)


def test_an_unknown_dataset_is_an_error():
    with pytest.raises(KeyError):
        dataset("gadm/PHL")
