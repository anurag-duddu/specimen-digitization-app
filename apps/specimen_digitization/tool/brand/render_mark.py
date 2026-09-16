#!/usr/bin/env python3
"""Render every brand raster from one geometry.

Run from the application root:

    uv run --with pillow python tool/brand/render_mark.py

The mark is the pin (`design/09-brand-direction.md` section 9): a vertical
`ink` stroke with a filled circular head, standing in a disc of `accent`.
Every number below is stated once, at the 24 dp mark 09 specifies, and every
raster scales from it. Nothing here is hand placed, so a change to the
specification is a change to one constant and a re-run.

Drawing happens at four times the output side and is resolved down with a
Lanczos filter, which is where the anti-aliasing comes from: Pillow itself
draws hard edged polygons. Colour and coverage are carried in separate
channels and resolved separately, so a disc on transparency keeps a clean
edge instead of the dark halo an un-premultiplied RGBA resize leaves behind.

The two generators that consume these files overwrite four of the web shell
renders, so the documented order is:

    uv run --with pillow python tool/brand/render_mark.py
    dart run flutter_launcher_icons
    dart run flutter_native_splash:create
    uv run --with pillow python tool/brand/render_mark.py --only web

The last pass restores `web/favicon.png`, the Apple touch icon and the two
maskable web icons. `--only sources` renders the other half on its own.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

APP_ROOT = Path(__file__).resolve().parents[2]

# Colour, 09 section 3. The roles, not the values, are what the product reads;
# these literals exist here because a PNG cannot look a token up.
ACCENT = (0xE8, 0xFF, 0x47)
ON_ACCENT = (0x11, 0x12, 0x14)
INK = (0x11, 0x12, 0x14)
PAPER = (0xFF, 0xFF, 0xFF)
GROUND_LIGHT = (0xF6, 0xF6, 0xF4)
GROUND_DARK = (0x0E, 0x0F, 0x11)

# Geometry, 09 section 9, stated at the 24 dp mark.
MARK_BOX = 24.0
PIN_HEIGHT = 16.0
PIN_STROKE = 2.0
HEAD_DIAMETER = 5.0

# Optical centring. 09 puts the head 1 dp above the geometric centre at 24 dp,
# which is the whole pin nudged up by one unit: a head heavy shape sitting on
# the exact centre reads as low. The nudge scales with the mark like every
# other number here.
OPTICAL_RISE = 1.0

SUPERSAMPLE = 4

# The app icon's shape, 09 sections 5 and 9. Five is the iOS icon exponent: an
# n = 5 superellipse inscribed in a 1024 square passes 446 px from its centre
# at 45 degrees and Apple's own mask passes 445 px, so the ground that fills
# the corners here is removed by the platform mask rather than surviving as a
# sliver.
SQUIRCLE_EXPONENT = 5.0
SQUIRCLE_SAMPLES = 8192

# The pin's height as a fraction of the icon it stands in (09 section 9).
ICON_PIN_FRACTION = 0.44

# An Android adaptive icon's foreground is a canvas whose central 66 percent
# is the icon a launcher mask actually shows, and a web maskable icon's is its
# central 80 percent. The pin is 44 percent of that frame in each, never 44
# percent of the canvas, so the masked Android icon, the masked maskable icon
# and the iOS icon all carry a pin of the same optical size.
ADAPTIVE_FRAME_FRACTION = 0.66
MASKABLE_FRAME_FRACTION = 0.80

# Android 12 and later clip the splash icon to a circle and mask a third of
# the foreground away, so the art has to sit inside the central two thirds.
# The mark's own head reaches three quarters of the disc's radius, so the
# full bleed disc would come back with a flattened head. The splash source
# for that platform carries the same disc drawn two thirds of the size.
ANDROID12_FRAME_FRACTION = 2.0 / 3.0


class Plate:
    """One square raster, drawn at SUPERSAMPLE times its output side.

    Colour and coverage are two images. Painting a shape means painting it
    into `colour`, into `cover`, or into both; what separates an opaque plate
    from a cut out one is only which of the two the caller reaches for.
    """

    def __init__(self, size: int, colour: tuple[int, int, int], cover: int) -> None:
        self.size = size
        self.px = size * SUPERSAMPLE
        self._colour = Image.new("RGB", (self.px, self.px), colour)
        self._cover = Image.new("L", (self.px, self.px), cover)
        self.colour = ImageDraw.Draw(self._colour)
        self.cover = ImageDraw.Draw(self._cover)

    @property
    def centre(self) -> float:
        """The centre of the plate, in supersampled pixels."""
        return self.px / 2

    def write(self, path: Path, *, opaque: bool) -> None:
        """Resolve the plate to its output size and write it to `path`."""
        image = self._colour.resize((self.size, self.size), Image.Resampling.LANCZOS)
        if not opaque:
            image.putalpha(
                self._cover.resize((self.size, self.size), Image.Resampling.LANCZOS)
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, format="PNG", optimize=True)


def full_bleed(plate: Plate) -> list[float]:
    """The bounding box of a shape that touches all four edges."""
    return [0, 0, plate.px - 1, plate.px - 1]


def superellipse(
    centre: float, half: float, exponent: float
) -> list[tuple[float, float]]:
    """The superellipse `|x / half| ** n + |y / half| ** n == 1`, as a polygon."""
    points: list[tuple[float, float]] = []
    power = 2.0 / exponent
    for step in range(SQUIRCLE_SAMPLES):
        angle = 2.0 * math.pi * step / SQUIRCLE_SAMPLES
        cosine = math.cos(angle)
        sine = math.sin(angle)
        points.append(
            (
                centre + half * math.copysign(abs(cosine) ** power, cosine),
                centre + half * math.copysign(abs(sine) ** power, sine),
            )
        )
    return points


def draw_pin(
    draw: ImageDraw.ImageDraw,
    centre_x: float,
    centre_y: float,
    height: float,
    fill: tuple[int, int, int] | int,
) -> None:
    """Draw the pin of `height`, centred on the point given plus the rise.

    The pin is one object in three pieces: the head, the shaft, and the round
    cap that ends it. The cap is why the shaft stops half a stroke short of
    the tip, and it is what keeps the pin's total height exactly `height`.
    """
    unit = height / PIN_HEIGHT
    top = centre_y - OPTICAL_RISE * unit - height / 2
    bottom = top + height
    head_radius = HEAD_DIAMETER * unit / 2
    head_y = top + head_radius
    shaft_half = PIN_STROKE * unit / 2
    draw.ellipse(
        [
            centre_x - head_radius,
            head_y - head_radius,
            centre_x + head_radius,
            head_y + head_radius,
        ],
        fill=fill,
    )
    draw.rectangle(
        [centre_x - shaft_half, head_y, centre_x + shaft_half, bottom - shaft_half],
        fill=fill,
    )
    draw.ellipse(
        [
            centre_x - shaft_half,
            bottom - 2 * shaft_half,
            centre_x + shaft_half,
            bottom,
        ],
        fill=fill,
    )


def mark(
    size: int,
    *,
    disc: tuple[int, int, int],
    pin: tuple[int, int, int],
    ground: tuple[int, int, int] | None,
    frame: float = 1.0,
) -> Plate:
    """The mark: the pin standing in a disc of `frame` times the square.

    With a `ground` the plate is opaque and whatever the disc leaves carries
    it. With `None` that area is cut away and the colour under it stays the
    disc's own, so the resolved edge never darkens toward a transparent black.
    """
    cut_out = ground is None
    plate = Plate(size, disc if cut_out else ground, 0 if cut_out else 255)
    diameter = plate.px * frame
    inset = (plate.px - diameter) / 2
    box = [inset, inset, inset + diameter - 1, inset + diameter - 1]
    if cut_out:
        plate.cover.ellipse(box, fill=255)
    else:
        plate.colour.ellipse(box, fill=disc)
    draw_pin(
        plate.colour,
        plate.centre,
        plate.centre,
        diameter * PIN_HEIGHT / MARK_BOX,
        pin,
    )
    return plate


def app_icon(size: int) -> Plate:
    """The app icon: an accent superellipse with the pin at 44 percent."""
    plate = Plate(size, GROUND_LIGHT, 255)
    plate.colour.polygon(
        superellipse(plate.centre, plate.px / 2, SQUIRCLE_EXPONENT), fill=ACCENT
    )
    draw_pin(
        plate.colour,
        plate.centre,
        plate.centre,
        plate.px * ICON_PIN_FRACTION,
        ON_ACCENT,
    )
    return plate


def adaptive_foreground(size: int) -> Plate:
    """The Android adaptive foreground: the pin alone, on nothing.

    The background layer is a flat accent declared in the launcher icon
    configuration, so this layer carries coverage and one colour.
    """
    plate = Plate(size, INK, 0)
    frame = plate.px * ADAPTIVE_FRAME_FRACTION
    draw_pin(plate.cover, plate.centre, plate.centre, frame * ICON_PIN_FRACTION, 255)
    return plate


def maskable_icon(size: int) -> Plate:
    """The web maskable icon: accent to every edge, pin inside the safe zone."""
    plate = Plate(size, ACCENT, 255)
    frame = plate.px * MASKABLE_FRAME_FRACTION
    draw_pin(
        plate.colour, plate.centre, plate.centre, frame * ICON_PIN_FRACTION, ON_ACCENT
    )
    return plate


def render_sources() -> list[Path]:
    """The six brand rasters the two generators read."""
    brand = APP_ROOT / "assets" / "brand"
    written: list[Path] = []
    for name, plate, opaque in (
        (
            "mark-1024.png",
            mark(1024, disc=ACCENT, pin=ON_ACCENT, ground=GROUND_LIGHT),
            True,
        ),
        (
            "splash-mark-1024.png",
            mark(1024, disc=ACCENT, pin=ON_ACCENT, ground=None),
            False,
        ),
        (
            "splash-mark-android12-1024.png",
            mark(
                1024,
                disc=ACCENT,
                pin=ON_ACCENT,
                ground=None,
                frame=ANDROID12_FRAME_FRACTION,
            ),
            False,
        ),
        (
            "mark-mono-1024.png",
            mark(1024, disc=PAPER, pin=INK, ground=GROUND_LIGHT),
            True,
        ),
        ("icon-1024.png", app_icon(1024), True),
        ("icon-foreground-1024.png", adaptive_foreground(1024), False),
        ("icon-maskable-1024.png", maskable_icon(1024), True),
    ):
        path = brand / name
        plate.write(path, opaque=opaque)
        written.append(path)
    return written


def render_web() -> list[Path]:
    """The four web shell rasters the generators cannot produce correctly.

    `flutter_launcher_icons` resizes one source into all of them, which gives
    the favicon a square of ground it should not have and gives the two
    maskable icons corners a launcher mask may well show. Each is rendered
    here from the geometry that suits it instead.
    """
    web = APP_ROOT / "web"
    written: list[Path] = []
    for path, plate, opaque in (
        (
            web / "favicon.png",
            mark(64, disc=ACCENT, pin=ON_ACCENT, ground=None),
            False,
        ),
        (web / "icons" / "apple-touch-icon-180.png", app_icon(180), True),
        (web / "icons" / "Icon-maskable-192.png", maskable_icon(192), True),
        (web / "icons" / "Icon-maskable-512.png", maskable_icon(512), True),
    ):
        plate.write(path, opaque=opaque)
        written.append(path)
    return written


def hexed(colour: tuple[int, int, int]) -> str:
    """`colour` as an upper case hex triplet."""
    return "#{:02X}{:02X}{:02X}".format(*colour)


def check_colours() -> list[str]:
    """Report any place the shipped configuration drifted from the palette.

    The rasters and the platform configuration carry the same five colours in
    four file formats, and nothing else compares them.
    """
    expected = {
        APP_ROOT / "flutter_launcher_icons.yaml": [hexed(ACCENT), hexed(GROUND_LIGHT)],
        APP_ROOT / "flutter_native_splash.yaml": [
            hexed(GROUND_LIGHT),
            hexed(GROUND_DARK),
        ],
        APP_ROOT / "web" / "index.html": [hexed(GROUND_LIGHT)],
    }
    drift: list[str] = []
    for path, colours in expected.items():
        if not path.exists():
            drift.append("{} is missing".format(path.relative_to(APP_ROOT)))
            continue
        text = path.read_text(encoding="utf-8")
        for colour in colours:
            if not re.search(colour, text, flags=re.IGNORECASE):
                drift.append(
                    "{} does not carry {}".format(path.relative_to(APP_ROOT), colour)
                )

    manifest = APP_ROOT / "web" / "manifest.json"
    if manifest.exists():
        loaded = json.loads(manifest.read_text(encoding="utf-8"))
        for key in ("background_color", "theme_color"):
            value = str(loaded.get(key, ""))
            if value.upper() != hexed(GROUND_LIGHT):
                drift.append(
                    "web/manifest.json {} is {}".format(key, value or "unset")
                )
    else:
        drift.append("web/manifest.json is missing")
    return drift


def main() -> int:
    """Render the assets named by `--only` and report what moved."""
    parser = argparse.ArgumentParser(description="Render the brand rasters.")
    parser.add_argument(
        "--only",
        choices=("sources", "web", "all"),
        default="all",
        help="render the brand sources, the web shell renders, or both",
    )
    arguments = parser.parse_args()

    written: list[Path] = []
    if arguments.only in ("sources", "all"):
        written += render_sources()
    if arguments.only in ("web", "all"):
        written += render_web()

    for path in written:
        print("{} {}".format(path.relative_to(APP_ROOT), path.stat().st_size))

    drift = check_colours()
    for line in drift:
        print("colour drift: {}".format(line), file=sys.stderr)
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
