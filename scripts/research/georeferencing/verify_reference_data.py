"""Offline custody and algorithm smoke over the actual reference data files.

Run with `uv run python scripts/research/georeferencing/verify_reference_data.py
--dataset-root /path/to/datasets`. This command makes no network request and
does not claim runtime, curator, publication, or live specimen acceptance.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from specimen_digitization.application.georef_boundaries import extent, read_units
from specimen_digitization.application.georef_datasets import MANIFEST, Dataset, verified
from specimen_digitization.application.georef_elevation import pinned_elevation_range, read_pinned_tile
from specimen_digitization.application.georef_geonames import find, read_dump


def reference_path(root: Path, entry: Dataset) -> Path:
    if entry.id.startswith("geonames/"):
        return root / "geonames" / entry.retrieved / (entry.id.split("/")[1] + ".zip")
    if entry.id.startswith("geoboundaries/"):
        return root / "geoboundaries" / entry.retrieved / (
            "geoBoundaries-PHL-" + entry.id.split("/")[2] + "_simplified.geojson")
    if entry.id.startswith("cod-ab/"):
        return root / "cod-ab-gtm" / entry.retrieved / "gtm_admin_boundaries.geojson.zip"
    if entry.id.startswith("copernicus-glo30/"):
        return root / "copernicus-glo30" / entry.retrieved / entry.source_url.rsplit("/", 1)[1]
    raise ValueError("Unknown reference dataset layout")


def verify_references(root: Path) -> dict:
    report = {"version": "georeferencing-offline-reference-smoke-v1", "execution": "offline",
              "claim": "Reference custody and algorithm execution only; not live specimen acceptance",
              "files": [], "checks": []}
    tiles = {}
    yepocapa = None
    for entry in MANIFEST:
        data = verified(entry, reference_path(root, entry).read_bytes())
        item = {"id": entry.id, "sha256": entry.sha256, "size": len(data),
                "retrieved": entry.retrieved, "object_name": entry.object_name, "credit": entry.credit}
        if entry.id.startswith("geonames/"):
            status, gazetteer = read_dump(entry.id.split("/")[1], data)
            if gazetteer is None:
                raise ValueError(f"{entry.id}: {status}")
            item["rows"] = len(gazetteer.rows)
            name = "Mount McKinley" if gazetteer.country == "PH" else "Yepocapa"
            matches = find(gazetteer, name)
            item["example"] = {"name": name, "exact_ids": [p.record_id for p in matches.exact]}
        elif entry.id.startswith(("geoboundaries/", "cod-ab/")):
            units = read_units(entry, data)
            item["units"] = len(units)
            if entry.id.startswith("cod-ab/GT/"):
                yepocapa = extent(next(unit for unit in units if unit.code == "GT0412"))
        else:
            tile = read_pinned_tile(entry.id, data)
            tiles[entry.id] = tile
            item["raster"] = {"width": tile.width, "height": tile.height,
                              "north": tile.north, "west": tile.west}
        report["files"].append(item)
    ids = ("copernicus-glo30/N14_00_W091_00", "copernicus-glo30/N14_00_W092_00")
    if yepocapa is None:
        raise ValueError("Yepocapa reference footprint was not read")
    center, radius = yepocapa.center, yepocapa.radial_m
    heights = pinned_elevation_range([tiles[key] for key in ids], center, radius)
    try:
        pinned_elevation_range([tiles[ids[0]]], center, radius)
    except ValueError:
        incomplete_refused = True
    else:
        raise AssertionError("Incomplete DEM coverage was not refused")
    report["checks"].append({"check": "yepocapa_municipio_circle_dem", "center": center,
                             "radius_m": radius, "minimum_m": heights[0], "maximum_m": heights[1],
                             "datasets": ids, "one_tile_refused": incomplete_refused,
                             "interpretation": "Conditional DEM result, not an accepted specimen location"})
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_references(args.dataset_root), indent=2))
