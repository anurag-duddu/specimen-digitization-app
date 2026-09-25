"""Administrative units from the pinned boundary files (GEO.md 12).

Section 3's manifest pins geoBoundaries' simplified files for the Philippines'
regions, provinces and municipalities, and CONRED's COD-AB file for Guatemala's
departments and municipios. `read_units` turns a file's verified bytes into its
units, each carrying its file's margin (section 10). The module reads no file
itself and sends nothing. It maps no level to a Darwin Core field: which level
fills which field waits with D8.
"""

from __future__ import annotations

import dataclasses
import io
import json
import re
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass

from .georef_datasets import Dataset
from .georef_geometry import (
    Circle,
    Point,
    Shape,
    circle_within,
    enclosing_circle,
    shape_from_geojson,
)
from .georef_places import Ref
from .georef_radius import WGS84, Ellipsoid

GEOBOUNDARIES_LEVELS = {"ADM1": 1, "ADM2": 2, "ADM3": 3}
COD_AB_LAYER = re.compile(r"[a-z]{3}_admin([12])\.geojson")  # departments, municipios
# Longitude and latitude on WGS 84, the only coordinates GeoJSON has had since
# RFC 7946; older files may still name them.
CRS84 = "urn:ogc:def:crs:OGC:1.3:CRS84"


@dataclass(frozen=True, slots=True)
class Unit:
    """One administrative unit as its file gives it: its level below the
    country (1 is the largest), name and code, the unit above it when the file
    names one, its boundary, and the dataset id and margin of its file."""

    country: str  # ISO 3166-1 alpha-2, from the dataset id
    level: int
    name: str
    code: str
    parent: Ref | None
    shape: Shape
    dataset: str
    margin_m: float


def read_units(entry: Dataset, data: bytes) -> tuple[Unit, ...]:
    """The units of one pinned boundary file, from bytes the caller verified
    against the manifest (section 3)."""
    source, _, rest = entry.id.partition("/")
    country = rest.partition("/")[0]
    if source == "geoboundaries":
        return _geoboundaries(entry, country, data)
    if source == "cod-ab":
        return _cod_ab(entry, country, data)
    raise ValueError(f"{entry.id} is not a boundary file")


def holding_circle(
    units: Iterable[Unit], point: Point, radius_m: float, ellipsoid: Ellipsoid = WGS84
) -> dict[int, Unit]:
    """For each level, the unit that holds the whole circle with its file's
    margin to spare (G37). A level is left out when no unit holds the circle,
    or when more than one does."""
    held: dict[int, list[Unit]] = {}
    for unit in units:
        if circle_within(unit.shape, point, radius_m, unit.margin_m, ellipsoid):
            held.setdefault(unit.level, []).append(unit)
    return {level: found[0] for level, found in sorted(held.items()) if len(found) == 1}


def extent(unit: Unit, ellipsoid: Ellipsoid = WGS84) -> Circle:
    """The unit's corrected center and geographic radial (G38). A simplified
    file's margin adds to the radial, so the circle covers the unit's true
    boundary as well as the simplified one."""
    circle = enclosing_circle(unit.shape, ellipsoid)
    return dataclasses.replace(circle, radial_m=circle.radial_m + unit.margin_m)


def _geoboundaries(entry: Dataset, country: str, data: bytes) -> tuple[Unit, ...]:
    units = []
    for feature in _features(data):
        properties = _properties(feature)
        level = GEOBOUNDARIES_LEVELS.get(properties.get("shapeType"))
        name, code = properties.get("shapeName"), properties.get("shapeID")
        if level is None or not _text(name) or not _text(code):
            raise ValueError("a geoBoundaries unit needs its level, name and id")
        units.append(
            Unit(
                country=country,
                level=level,
                name=name,
                code=code,
                parent=None,  # geoBoundaries names no unit above
                shape=shape_from_geojson(feature.get("geometry")),
                dataset=entry.id,
                margin_m=entry.margin_m,
            )
        )
    return tuple(units)


def _cod_ab(entry: Dataset, country: str, data: bytes) -> tuple[Unit, ...]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ValueError("a COD-AB file is a zip") from error
    layers = {
        int(match[1]): archive.read(name)
        for name in archive.namelist()
        if (match := COD_AB_LAYER.fullmatch(name))
    }
    if sorted(layers) != [1, 2]:
        raise ValueError("a COD-AB zip needs its admin1 and admin2 layers")
    units = []
    for level in (1, 2):
        for feature in _features(layers[level]):
            properties = _properties(feature)
            name, code = properties.get(f"adm{level}_name"), properties.get(f"adm{level}_pcode")
            if not _text(name) or not _text(code):
                raise ValueError("a COD-AB unit needs its name and P-code")
            above_code, above_name = properties.get("adm1_pcode"), properties.get("adm1_name")
            units.append(
                Unit(
                    country=country,
                    level=level,
                    name=name,
                    code=code,
                    parent=(
                        Ref(above_code, above_name)
                        if level == 2 and _text(above_code) and _text(above_name)
                        else None
                    ),
                    shape=shape_from_geojson(feature.get("geometry")),
                    dataset=entry.id,
                    margin_m=entry.margin_m,
                )
            )
    return tuple(units)


def _features(data: bytes) -> list:
    try:
        collection = json.loads(data)
    except ValueError as error:
        raise ValueError("a boundary file is GeoJSON") from error
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise ValueError("a boundary file is a GeoJSON FeatureCollection")
    crs = collection.get("crs")
    named = crs.get("properties") if isinstance(crs, dict) else None
    if crs is not None and (not isinstance(named, dict) or named.get("name") != CRS84):
        raise ValueError("a boundary file is in longitude and latitude on WGS 84")
    features = collection.get("features")
    if not isinstance(features, list):
        raise ValueError("a boundary file lists its features")
    return features


def _properties(feature: object) -> dict:
    properties = feature.get("properties") if isinstance(feature, dict) else None
    if not isinstance(properties, dict):
        raise ValueError("a boundary feature needs its properties")
    return properties


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
