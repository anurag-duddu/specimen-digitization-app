"""Reference datasets the retrospective tool reads from the project's storage (GEO.md 3).

Each entry names a file by the SHA-256 of its exact bytes: the object is
`application/sha256/<digest>` in the bucket the runtime configures, never named
here. The owner uploads each file with a command S2 writes from this manifest.
A reader recomputes the digest of what it reads and refuses a mismatch, because
the worker can also write under that prefix (S2, 2026-09-24).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

GLO30_SOURCE = "https://copernicus-dem-30m.s3.amazonaws.com"
GLO30_LICENSE = "Copernicus DEM GLO-30, free license"
GLO30_LICENSE_URL = (
    "https://dataspace.copernicus.eu/explore-data/data-collections/"
    "copernicus-contributing-missions/collections-description/COP-DEM"
)
# The notice for adapted data, as that page's licensing section gives it
# (checked 2026-09-24); derived elevations adapt the data.
GLO30_CREDIT = (
    "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and "
    "Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; "
    "all rights reserved"
)
GEONAMES_SOURCE = "https://download.geonames.org/export/dump"
GEONAMES_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
# The dumps' own readme states CC BY 4.0 and supplies the data as it is.
GEONAMES_CREDIT = "GeoNames (https://www.geonames.org/), licensed under CC BY 4.0"
# Administrative boundaries for containment and a unit's extent (G37, G38), by
# the coordinator's rulings of 2026-09-24: the Philippines from geoBoundaries'
# simplified files, Guatemala from CONRED's COD-AB file on HDX, credited per file
# as each source's metadata states it.
BOUNDARY_LICENSE = "CC BY 3.0 IGO"
BOUNDARY_LICENSE_URL = "https://creativecommons.org/licenses/by/3.0/igo/"
GEOBOUNDARIES_SOURCE = "https://github.com/wmgeolab/geoBoundaries/raw"
GEOBOUNDARIES_PHL_CREDIT = (
    "National Mapping and Resource Information Authority (NAMRIA), Philippines Statistics "
    "Authority (PSA), OCHA Philippines, via geoBoundaries (https://www.geoboundaries.org/), "
    "licensed under CC BY 3.0 IGO"
)
# geoBoundaries' builder simplifies with mapshaper's Douglas-Peucker at 100 m and
# snaps at 0.00001 degree, about 1.1 m, so containment keeps this much more room.
SIMPLIFIED_MARGIN_M = 101.2
COD_AB_GTM_SOURCE = (
    "https://data.humdata.org/dataset/0b20f310-7d22-479c-b7e2-e1bb9737fa72/resource/"
    "77e5e79b-d7b0-497c-aea2-2753768ec5f0/download/gtm_admin_boundaries.geojson.zip"
)
COD_AB_GTM_CREDIT = (
    "Coordinadora Nacional Para La Reducción De Desastres (CONRED), via OCHA's Common "
    "Operational Datasets on HDX (https://data.humdata.org/dataset/cod-ab-gtm), licensed "
    "under CC BY 3.0 IGO"
)


@dataclass(frozen=True, slots=True)
class Dataset:
    """One reference file: what it is for, where and when its bytes came from,
    the size and SHA-256 that prove a copy is the reviewed file, its credit, and
    the content type S2's upload sets.
    `stable_source` is False when the source keeps no copy of these bytes, so
    the pinned file is the only one (GeoNames' daily dumps).
    `margin_m` is a boundary file's simplification error, which containment adds
    to a circle's radius (section 10); zero for a file not simplified."""

    id: str
    purpose: str
    source_url: str
    retrieved: str
    size: int
    sha256: str
    license: str
    license_url: str
    credit: str
    stable_source: bool
    content_type: str
    margin_m: float = 0.0

    @property
    def object_name(self) -> str:
        return f"application/sha256/{self.sha256}"


class DigestMismatch(ValueError):
    """The bytes read are not the file the manifest names."""


def _glo30(cell: str, size: int, sha256: str) -> Dataset:
    name = f"Copernicus_DSM_COG_10_{cell}_DEM"
    return Dataset(
        id=f"copernicus-glo30/{cell}",
        purpose="elevation measurements and derived elevations (D11, G37)",
        source_url=f"{GLO30_SOURCE}/{name}/{name}.tif",
        retrieved="2026-09-24",
        size=size,
        sha256=sha256,
        license=GLO30_LICENSE,
        license_url=GLO30_LICENSE_URL,
        credit=GLO30_CREDIT,
        stable_source=True,
        content_type="image/tiff",  # Cloud Optimized GeoTIFF
    )


def _geonames(country: str, dumped: str, size: int, sha256: str) -> Dataset:
    return Dataset(
        id=f"geonames/{country}/{dumped}",
        purpose="tier-1 names and administrative units (G35); nothing is sent to GeoNames",
        source_url=f"{GEONAMES_SOURCE}/{country}.zip",
        retrieved=dumped,
        size=size,
        sha256=sha256,
        license="CC BY 4.0",
        license_url=GEONAMES_LICENSE_URL,
        credit=GEONAMES_CREDIT,
        stable_source=False,  # GeoNames regenerates its dumps daily and keeps no archive
        content_type="application/zip",
    )


def _geoboundaries(level: str, commit: str, size: int, sha256: str) -> Dataset:
    name = f"geoBoundaries-PHL-{level}_simplified.geojson"
    return Dataset(
        id=f"geoboundaries/PH/{level}/{commit}",
        purpose="containment for derived county and city, and a unit's extent (G37, G38)",
        source_url=f"{GEOBOUNDARIES_SOURCE}/{commit}/releaseData/gbOpen/PHL/{level}/{name}",
        retrieved="2026-09-24",
        size=size,
        sha256=sha256,
        license=BOUNDARY_LICENSE,
        license_url=BOUNDARY_LICENSE_URL,
        credit=GEOBOUNDARIES_PHL_CREDIT,
        stable_source=True,  # a release commit keeps these bytes
        content_type="application/geo+json",
        margin_m=SIMPLIFIED_MARGIN_M,
    )


# The pilot's files, read on 2026-09-24: the GLO-30 tiles from the anonymous
# open-data bucket (each MD5 equal to its ETag, each size to its Content-Length),
# the GeoNames dumps generated that day, and the boundary files.
MANIFEST = (
    _glo30(
        "N07_00_E125_00",
        45446782,
        "7a9189637a5af9677a92e765b9448bdfe425383fae8e39a6808a96b8fe8f19d0",  # pragma: allowlist secret (public file digest)
    ),
    _glo30(
        "N06_00_E125_00",
        26799517,
        "155424cb1ede34d2b0e4e92b51b5c359164e3d0834507166d1b28969389e2e5c",  # pragma: allowlist secret (public file digest)
    ),
    _glo30(
        "N14_00_W091_00",
        44328513,
        "0f6f645d310b4aa02fffc0cba0f3ad130a5fd2303d953e5f8931ba48817b0c6c",  # pragma: allowlist secret (public file digest)
    ),
    _geonames(
        "PH",
        "2026-09-24",
        2555475,
        "7a8dc145e57ea42c26b35393a281f248ff35e70aaf794eed20c989ff2d718759",  # pragma: allowlist secret (public file digest)
    ),
    _geonames(
        "GT",
        "2026-09-24",
        1047133,
        "24965821b5541833efb63ced996ac9a508feb049ec02442727f28cbdf15dfe96",  # pragma: allowlist secret (public file digest)
    ),
    _geoboundaries(
        "ADM1",
        "41af8f1",
        2812222,
        "8eeef6a9a525a81a647dcaac85e1337b990fc527c4a0e9c70556d5b0905be087",  # pragma: allowlist secret (public file digest)
    ),
    _geoboundaries(
        "ADM2",
        "41af8f1",
        3140454,
        "fa77b9f17db2e419acaae714a935f7812be4409e2983675d34020e8426a3e189",  # pragma: allowlist secret (public file digest)
    ),
    _geoboundaries(
        "ADM3",
        "9469f09",
        7071267,
        "2ece3d44a5c6a2afb385ffbf3a6b88d83e4d3a3e7eed9a52cb3be1bc59e289fc",  # pragma: allowlist secret (public file digest)
    ),
    Dataset(
        id="cod-ab/GT/2026-09-24",
        purpose="containment for derived county and city, and a unit's extent (G37, G38)",
        source_url=COD_AB_GTM_SOURCE,
        retrieved="2026-09-24",
        size=3366983,
        sha256="f178eda98c46329380bdbb43f0637b4c43535bc843de6a0b8b960193b8f4363f",  # pragma: allowlist secret (public file digest)
        license=BOUNDARY_LICENSE,
        license_url=BOUNDARY_LICENSE_URL,
        credit=COD_AB_GTM_CREDIT,
        stable_source=False,  # HDX serves only its latest file
        content_type="application/zip",
    ),
)
_BY_ID = {entry.id: entry for entry in MANIFEST}


def dataset(dataset_id: str) -> Dataset:
    return _BY_ID[dataset_id]


def verified(entry: Dataset, data: bytes) -> bytes:
    """The bytes, if their size and SHA-256 are the manifest's; else an error."""
    if len(data) != entry.size or hashlib.sha256(data).hexdigest() != entry.sha256:
        raise DigestMismatch(f"{entry.id}: the bytes read are not the reviewed file")
    return data


def elevation_tile(latitude: float, longitude: float) -> Dataset | None:
    """The GLO-30 tile of the 1-degree cell a point falls in, named for the
    cell's south-west corner; None when the manifest has no such tile."""
    south, west = math.floor(latitude), math.floor(longitude)
    cell = (
        f"{'N' if south >= 0 else 'S'}{abs(south):02d}_00_"
        f"{'E' if west >= 0 else 'W'}{abs(west):03d}_00"
    )
    return _BY_ID.get(f"copernicus-glo30/{cell}")


def boundary_files(country: str) -> tuple[Dataset, ...]:
    """The pinned boundary files of a country, by ISO 3166-1 code."""
    return tuple(
        entry
        for entry in MANIFEST
        if entry.id.startswith((f"geoboundaries/{country}/", f"cod-ab/{country}/"))
    )


def geonames_dump(country: str) -> Dataset | None:
    """The latest pinned GeoNames dump of a country, by ISO 3166-1 code."""
    dumps = [entry for entry in MANIFEST if entry.id.startswith(f"geonames/{country}/")]
    return max(dumps, key=lambda entry: entry.retrieved) if dumps else None
