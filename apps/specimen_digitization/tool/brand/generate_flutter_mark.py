#!/usr/bin/env python3
"""Generate Flutter paths from the canonical trace of the owner's logo.

No runtime SVG dependency is needed. Refuse unsupported SVG commands rather
than silently dropping part of the identity.
"""

from pathlib import Path
import re
import xml.etree.ElementTree as ET

APP = Path(__file__).resolve().parents[2]
SOURCE = APP / "assets/brand/specimen-mark.svg"
TARGET = APP / "packages/specimen_ui/lib/src/foundation/mark_geometry.dart"
NS = {"svg": "http://www.w3.org/2000/svg"}


def gradient_code(gradient: ET.Element) -> str:
    """Keep both artwork treatments tied to their canonical SVG stops."""
    colors = {
        "#7B61FF": "iris",
        "#F5A45B": "amber",
        "#0E0E11": "ink",
        "#573F49": "Color.lerp(Color.lerp(amber, iris, 0.4), ink, 0.6)!",
    }
    stops = gradient.findall("svg:stop", NS)
    expressions = [colors[stop.attrib["stop-color"]] for stop in stops]
    offsets = [stop.attrib["offset"] for stop in stops]
    return (
        "Gradient.linear(\n"
        f"const Offset({gradient.attrib['x1']}, {gradient.attrib['y1']}),\n"
        f"const Offset({gradient.attrib['x2']}, {gradient.attrib['y2']}),\n"
        f"<Color>[{', '.join(expressions)}], <double>[{', '.join(offsets)}],\n"
        ")"
    )


def path_code(data: str) -> str:
    tokens = re.findall(r"[A-Za-z]|-?\d+(?:\.\d+)?", data)
    methods = {"M": ("moveTo", 2), "L": ("lineTo", 2), "Q": ("quadraticBezierTo", 4)}
    lines = ["Path()..fillType = PathFillType.evenOdd"]
    while tokens:
        command = tokens.pop(0)
        if command == "Z":
            lines.append("..close()")
            continue
        if command not in methods:
            raise ValueError(f"Unsupported SVG command: {command}")
        method, count = methods[command]
        values, tokens = tokens[:count], tokens[count:]
        lines.append(f"..{method}({', '.join(values)})")
    return "\n    ".join(lines)


def main() -> None:
    root = ET.parse(SOURCE).getroot()
    assert root.attrib["viewBox"] == "0 0 512 512"
    group = root.find("svg:g", NS)
    assert group is not None and group.attrib["transform"] == "translate(1 42)"
    gradients = {
        gradient.attrib["id"]: gradient_code(gradient)
        for gradient in root.findall("svg:defs/svg:linearGradient", NS)
    }
    paths = {
        path.attrib["id"]: path_code(path.attrib["d"])
        for path in group.findall("svg:path", NS)
    }
    source = """// GENERATED from assets/brand/specimen-mark.svg. Do not edit by hand.
// Regenerate with tool/brand/generate_flutter_mark.py, then dart format.
import 'dart:ui';

/// Canonical geometry traced from the owner's selected primary brand mark.
abstract final class MarkGeometry {
  /// Paints the same three interlocking ribbons without mirroring or a disc.
  static void paint(Canvas canvas, Size size, {
    required Color ink,
    required Color amber,
    required Color iris,
    required bool monochrome,
    required bool appIcon,
  }) {
    final scale = size.shortestSide / 512;
    canvas.save();
    canvas.translate((size.width - size.shortestSide) / 2,
        (size.height - size.shortestSide) / 2);
    canvas.scale(scale);
    canvas.translate(1, 42);
    final brush = Paint()..color = ink;
    canvas.drawPath(_upper, brush);
    if (!monochrome) {
      brush.shader = appIcon ? ICON_GRADIENT : PRIMARY_GRADIENT;
    }
    canvas.drawPath(_folded, brush);
    brush.shader = null;
    canvas.drawPath(_lower, brush);
    canvas.restore();
  }

  static final Path _upper = UPPER;
  static final Path _folded = FOLDED;
  static final Path _lower = LOWER;
}
"""
    replacements = {
        "ICON_GRADIENT": gradients["fold-app-icon"],
        "PRIMARY_GRADIENT": gradients["fold"],
        "UPPER": paths["upper"],
        "FOLDED": paths["folded"],
        "LOWER": paths["lower"],
    }
    for token, value in replacements.items():
        source = source.replace(token, value)
    TARGET.write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
