"""Canonical original-coordinate ROI crop and explicit clockwise quarter turns."""

import io
from PIL import Image


def region_png(image, region):
    crop = image.crop(
        (region.x, region.y, region.x + region.width, region.y + region.height)
    ).convert("RGB")
    transpose = {
        1: Image.Transpose.ROTATE_270,
        2: Image.Transpose.ROTATE_180,
        3: Image.Transpose.ROTATE_90,
    }.get(region.rotation_quarter_turns)
    if transpose is not None:
        crop = crop.transpose(transpose)
    output = io.BytesIO()
    crop.save(output, format="PNG")
    return output.getvalue()
