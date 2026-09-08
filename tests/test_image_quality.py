from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image, ImageFilter

from specimen_digitization.application.image_quality import (
    CoverageObservation,
    ImageLimits,
    RegionBox,
    check_regions,
    diagnose_image,
    orientation_transform,
    orientation_view,
)


def encoded(image, format="PNG", **kwargs):
    output = BytesIO()
    image.save(output, format=format, **kwargs)
    return output.getvalue()


@pytest.mark.parametrize("data", [b"", b"not an image", b"\x89PNG\r\n\x1a\n"])
def test_malformed_images(data):
    assert diagnose_image(data).status == "rejected"


def test_limits_formats_truncation_and_metadata():
    data = encoded(Image.new("RGB", (20, 10)))
    assert diagnose_image(data, ImageLimits(max_pixels=199)).issues == (
        "resolution_limit_exceeded",
    )
    assert diagnose_image(data, ImageLimits(max_bytes=len(data) - 1)).issues == (
        "byte_limit_exceeded",
    )
    assert diagnose_image(data, ImageLimits(max_axis=19)).status == "rejected"
    assert (
        diagnose_image(
            data, ImageLimits(max_pixels=200, max_bytes=len(data), max_axis=20)
        ).status
        == "valid"
    )
    assert diagnose_image(data[:-15]).status == "rejected"
    tiff = encoded(Image.new("RGB", (4, 4)), "TIFF")
    assert diagnose_image(tiff).issues == ("unsupported_or_unapproved_format",)
    assert (
        diagnose_image(tiff, ImageLimits(allowed_formats=("TIFF",))).status == "valid"
    )
    multiple = encoded(
        Image.new("RGB", (4, 4)),
        "TIFF",
        save_all=True,
        append_images=[Image.new("RGB", (4, 4))],
    )
    assert diagnose_image(multiple, ImageLimits(allowed_formats=("TIFF",))).issues == (
        "multi_frame_image_not_supported",
    )


@pytest.mark.parametrize("orientation", range(1, 9))
def test_orientation_pixel_and_edge_roundtrip(orientation):
    image = Image.new("RGB", (3, 2))
    image.putdata([(i * 30, i * 20, i * 10) for i in range(6)])
    exif = Image.Exif()
    exif[274] = orientation
    exif[270] = "metadata must not survive"
    data = encoded(image, exif=exif)
    derivative, provenance = orientation_view(data)
    assert provenance.original_sha256 == sha256(data).hexdigest()
    transform = provenance.transform
    with Image.open(BytesIO(derivative)) as view:
        assert not view.getexif() and not view.info
        for y in range(2):
            for x in range(3):
                vx, vy = transform.to_view(x + 0.5, y + 0.5)
                assert view.getpixel((int(vx), int(vy))) == image.getpixel((x, y))
                assert transform.to_original(vx, vy) == (x + 0.5, y + 0.5)
    for point in [(0, 0), (3, 0), (0, 2), (3, 2)]:
        assert transform.to_original(*transform.to_view(*point)) == point
    with pytest.raises(ValueError):
        transform.to_view(-1, 0)


def test_quality_responds_to_controlled_blur_exposure():
    image = Image.new("L", (128, 128))
    image.putdata(
        [255 if (x // 8 + y // 8) % 2 else 0 for y in range(128) for x in range(128)]
    )
    sharp = diagnose_image(encoded(image)).metrics
    blurred = diagnose_image(encoded(image.filter(ImageFilter.GaussianBlur(3)))).metrics
    assert blurred.mean_neighbor_gradient < sharp.mean_neighbor_gradient
    assert blurred.contrast_stddev < sharp.contrast_stddev
    dark = diagnose_image(encoded(Image.new("L", (32, 32), 0)))
    bright = diagnose_image(encoded(Image.new("L", (32, 32), 255)))
    assert dark.metrics.dark_fraction == bright.metrics.bright_fraction == 1
    assert dark.metrics.calibrated is False
    assert "uniform_luminance" in dark.issues


def test_geometry_coverage_and_boundaries():
    digest = sha256(b"synthetic").hexdigest()
    assert check_regions(10, 10, (), digest).issues == ("zero_regions",)
    a = RegionBox(id="a", x=0, y=0, width=5, height=5)
    adjacent = RegionBox(id="b", x=5, y=0, width=5, height=5)
    assert not check_regions(10, 10, (a, adjacent), digest).issues
    overlap = RegionBox(id="c", x=4, y=4, width=7, height=7)
    report = check_regions(10, 10, (a, overlap), digest)
    assert report.issues == ("region_out_of_bounds", "overlapping_regions")
    coverage = CoverageObservation(
        input_sha256=digest,
        algorithm_version="synthetic-v1",
        raw_response_ref="fixture://coverage",
        missing_regions=(adjacent,),
        synthetic=True,
    )
    assert check_regions(10, 10, (a,), digest, coverage).coverage_state == "incomplete"
    with pytest.raises(ValueError, match="input mismatch"):
        check_regions(10, 10, (a,), sha256(b"different").hexdigest(), coverage)
    with pytest.raises(ValueError):
        orientation_transform(10, 10, 9)


def test_invalid_orientation_and_bounded_samples():
    exif = Image.Exif()
    exif[274] = 9
    data = encoded(Image.new("RGB", (16, 16)), exif=exif)
    assert diagnose_image(data).issues == ("invalid_exif_orientation",)
    result = diagnose_image(
        encoded(Image.new("RGB", (512, 256))), ImageLimits(sample_axis=64)
    )
    assert (result.metrics.sample_width, result.metrics.sample_height) == (64, 32)
