#!/usr/bin/env python3
"""Render platform artwork from the owner's canonical interlocking SVG.

Run from the application root, using pinned, self-contained raster tools:

    uv run --with resvg-py==0.5.0 --with pillow==11.3.0 python tool/brand/render_mark.py
    dart run flutter_launcher_icons
    dart run flutter_native_splash:create
    uv run --with resvg-py==0.5.0 --with pillow==11.3.0 python tool/brand/render_mark.py --only web

The SVG, not a second Python path description, owns the three ribbons, aperture,
and fold gradient. resvg renders the vector; Pillow composes the Paper plate and
resolves supersampling with premultiplied alpha. iOS and legacy launcher sources
are opaque squares: the platform supplies the rounded mask. Splash and favicon
plates have rounded transparent corners so the mark remains legible on dark
surfaces. Android adaptive and Android 12 artwork respect their safe area.
"""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw
import resvg_py

APP_ROOT = Path(__file__).resolve().parents[2]
PALETTE_PATH = APP_ROOT / "packages/specimen_ui/lib/src/foundation/palette.dart"
SVG_PATH = APP_ROOT / "assets/brand/specimen-mark.svg"
SVG_NS = "{http://www.w3.org/2000/svg}"
SUPERSAMPLE = 4
ADAPTIVE_FRAME_FRACTION = 0.66
MASKABLE_FRAME_FRACTION = 0.80
ANDROID12_FRAME_FRACTION = 2.0 / 3.0
PLATE_RADIUS_FRACTION = 0.22


def brand_seed(name: str) -> tuple[int, int, int]:
    """Read an exact opaque seed from Flutter's BrandPalette, failing closed."""
    source = PALETTE_PATH.read_text(encoding="utf-8")
    table = re.search(r"class BrandPalette\s*\{(.*?)\n\}", source, flags=re.DOTALL)
    if table is None:
        raise ValueError("BrandPalette is missing from the Flutter palette")
    matches = re.findall(
        rf"static const Color {re.escape(name)} = Color\(0xFF([0-9A-Fa-f]{{6}})\);",
        table.group(1),
    )
    if len(matches) != 1:
        raise ValueError(f"Expected one opaque BrandPalette.{name} seed")
    value = matches[0]
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


IRIS = brand_seed("iris")
AMBER = brand_seed("amber")
OBSIDIAN = brand_seed("obsidian")
PAPER = brand_seed("paper")


def hexed(colour: tuple[int, int, int]) -> str:
    """Return an upper-case RGB triplet."""
    return "#{:02X}{:02X}{:02X}".format(*colour)


def vector(*, monochrome: bool = False, app_icon: bool = False) -> str:
    """Load the vector, selecting its named app-icon or monochrome treatment."""
    source = SVG_PATH.read_text(encoding="utf-8")
    root = ET.fromstring(source)
    paths = root.findall(f".//{SVG_NS}path")
    if root.get("viewBox") != "0 0 512 512" or [p.get("id") for p in paths] != [
        "upper", "folded", "lower"
    ]:
        raise ValueError("The canonical mark must retain its three interlocking ribbons")
    if app_icon:
        if root.find(f".//{SVG_NS}linearGradient[@id='fold-app-icon']") is None:
            raise ValueError("The canonical app-icon fold gradient is missing")
        paths[1].set("fill", "url(#fold-app-icon)")
    if monochrome:
        for path in paths:
            path.set("fill", hexed(OBSIDIAN))
    return ET.tostring(root, encoding="unicode") if monochrome or app_icon else source


def raster(
    size: int,
    *,
    frame: float = 1.0,
    ground: bool = False,
    rounded_plate: bool = False,
    monochrome: bool = False,
    app_icon: bool = False,
) -> Image.Image:
    """Render the SVG in a centered frame, optionally on the owner's Paper plate."""
    px = size * SUPERSAMPLE
    art_side = round(px * frame)
    art = Image.open(BytesIO(resvg_py.svg_to_bytes(
        svg_string=vector(monochrome=monochrome, app_icon=app_icon),
        width=art_side,
        height=art_side,
        skip_system_fonts=True,
    ))).convert("RGBA")
    plate = Image.new("RGBA", (px, px), PAPER + ((255,) if ground else (0,)))
    if rounded_plate:
        ImageDraw.Draw(plate).rounded_rectangle(
            (0, 0, px - 1, px - 1),
            radius=round(px * PLATE_RADIUS_FRACTION),
            fill=PAPER + (255,),
        )
    inset = (px - art_side) // 2
    plate.alpha_composite(art, (inset, inset))
    # Resolve colour and coverage together; transparent edges retain their colour.
    resolved = plate.convert("RGBa").resize(
        (size, size), Image.Resampling.LANCZOS
    ).convert("RGBA")
    return resolved.convert("RGB") if ground else resolved


def write(path: Path, rendered: Image.Image) -> Path:
    """Write a deterministic PNG without timestamps or ancillary metadata."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered.save(path, format="PNG", optimize=True)
    return path


def render_sources() -> list[Path]:
    """Render the seven reference and native-generator inputs."""
    brand = APP_ROOT / "assets/brand"
    return [
        write(brand / "mark-1024.png", raster(1024, ground=True)),
        write(brand / "mark-mono-1024.png", raster(1024, ground=True, monochrome=True)),
        write(brand / "splash-mark-1024.png", raster(1024, rounded_plate=True, app_icon=True)),
        write(brand / "splash-mark-android12-1024.png", raster(
            1024, frame=ANDROID12_FRAME_FRACTION, app_icon=True,
        )),
        write(brand / "icon-1024.png", raster(1024, ground=True, app_icon=True)),
        write(brand / "icon-foreground-1024.png", raster(
            1024, frame=ADAPTIVE_FRAME_FRACTION, app_icon=True,
        )),
        write(brand / "icon-maskable-1024.png", raster(
            1024, frame=MASKABLE_FRAME_FRACTION, ground=True, app_icon=True,
        )),
    ]


def render_web() -> list[Path]:
    """Restore the high-resolution favicon and correct maskable safe areas."""
    web = APP_ROOT / "web"
    return [
        write(web / "favicon.png", raster(64, rounded_plate=True, app_icon=True)),
        write(web / "icons/apple-touch-icon-180.png", raster(180, ground=True, app_icon=True)),
        write(web / "icons/Icon-maskable-192.png", raster(
            192, frame=MASKABLE_FRAME_FRACTION, ground=True, app_icon=True,
        )),
        write(web / "icons/Icon-maskable-512.png", raster(
            512, frame=MASKABLE_FRAME_FRACTION, ground=True, app_icon=True,
        )),
    ]


def check_colours() -> list[str]:
    """Fail if the canonical vector or platform colours drift from Flutter."""
    expected = {
        SVG_PATH: [hexed(OBSIDIAN), hexed(AMBER), hexed(IRIS)],
        APP_ROOT / "flutter_launcher_icons.yaml": [hexed(PAPER)],
        APP_ROOT / "flutter_native_splash.yaml": [hexed(PAPER), hexed(OBSIDIAN)],
        APP_ROOT / "web/index.html": [hexed(PAPER), hexed(OBSIDIAN)],
    }
    drift: list[str] = []
    for path, colours in expected.items():
        if not path.exists():
            drift.append(f"{path.relative_to(APP_ROOT)} is missing")
            continue
        source = path.read_text(encoding="utf-8")
        for colour in colours:
            if not re.search(colour, source, flags=re.IGNORECASE):
                drift.append(f"{path.relative_to(APP_ROOT)} does not carry {colour}")
    manifest = APP_ROOT / "web/manifest.json"
    if manifest.exists():
        loaded = json.loads(manifest.read_text(encoding="utf-8"))
        for key in ("background_color", "theme_color"):
            value = str(loaded.get(key, ""))
            if value.upper() != hexed(PAPER):
                drift.append(f"web/manifest.json {key} is {value or 'unset'}")
    else:
        drift.append("web/manifest.json is missing")
    return drift


def main() -> int:
    """Validate sources, then render the requested assets."""
    parser = argparse.ArgumentParser(description="Render the canonical brand SVG.")
    parser.add_argument(
        "--only", choices=("sources", "web", "all"), default="all",
        help="render brand sources, web shell assets, or both",
    )
    arguments = parser.parse_args()
    drift = check_colours()
    if drift:
        for line in drift:
            print(f"colour drift: {line}", file=sys.stderr)
        return 1
    written: list[Path] = []
    if arguments.only in ("sources", "all"):
        written += render_sources()
    if arguments.only in ("web", "all"):
        written += render_web()
    for path in written:
        print(f"{path.relative_to(APP_ROOT)} {path.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
