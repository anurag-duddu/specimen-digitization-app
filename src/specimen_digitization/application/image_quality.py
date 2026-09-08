"""Bounded image diagnostics; metrics are uncalibrated signals, never accuracy."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from typing import Literal, Protocol

from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError
from pydantic import Field

from .collection_profiles import FrozenRecord


class ImageLimits(FrozenRecord):
    max_bytes: int = Field(default=25_000_000, gt=0, le=25_000_000)
    max_axis: int = Field(default=20_000, gt=0, le=20_000)
    max_pixels: int = Field(default=40_000_000, gt=0, le=40_000_000)
    allowed_formats: tuple[Literal["JPEG", "PNG", "TIFF"], ...] = ("JPEG", "PNG")
    sample_axis: int = Field(default=256, ge=8, le=512)


class ViewTransform(FrozenRecord):
    """Affine map of original pixel EDGES to view edges, exclusive upper bounds."""

    orientation: int = Field(ge=1, le=8)
    original_width: int = Field(gt=0)
    original_height: int = Field(gt=0)
    view_width: int = Field(gt=0)
    view_height: int = Field(gt=0)
    matrix: tuple[int, int, int, int, int, int]
    coordinate_space: Literal["pixel_edges"] = "pixel_edges"
    algorithm_version: str = "exif-edge-affine-v1"

    def to_view(self, x: float, y: float) -> tuple[float, float]:
        if not (0 <= x <= self.original_width and 0 <= y <= self.original_height):
            raise ValueError("point outside original")
        a, b, c, d, e, f = self.matrix
        return a * x + b * y + c, d * x + e * y + f

    def to_original(self, x: float, y: float) -> tuple[float, float]:
        if not (0 <= x <= self.view_width and 0 <= y <= self.view_height):
            raise ValueError("point outside view")
        a, b, c, d, e, f = self.matrix
        determinant = a * e - b * d
        return (e * (x - c) - b * (y - f)) / determinant, (
            -d * (x - c) + a * (y - f)
        ) / determinant


def orientation_transform(width: int, height: int, orientation: int) -> ViewTransform:
    matrices = {
        1: (1, 0, 0, 0, 1, 0),
        2: (-1, 0, width, 0, 1, 0),
        3: (-1, 0, width, 0, -1, height),
        4: (1, 0, 0, 0, -1, height),
        5: (0, 1, 0, 1, 0, 0),
        6: (0, -1, height, 1, 0, 0),
        7: (0, -1, height, -1, 0, width),
        8: (0, 1, 0, -1, 0, width),
    }
    if orientation not in matrices:
        raise ValueError("invalid EXIF orientation")
    return ViewTransform(
        orientation=orientation,
        original_width=width,
        original_height=height,
        view_width=height if orientation >= 5 else width,
        view_height=width if orientation >= 5 else height,
        matrix=matrices[orientation],
    )


class QualityMetrics(FrozenRecord):
    algorithm_version: str = "thumbnail-luminance-gradient-v1"
    calibrated: Literal[False] = False
    mean_luminance: float
    contrast_stddev: float
    dark_fraction: float
    bright_fraction: float
    mean_neighbor_gradient: float
    sample_width: int
    sample_height: int


class ImageDiagnostics(FrozenRecord):
    status: Literal["valid", "rejected"]
    input_sha256: str
    size_bytes: int
    format: str | None = None
    width: int | None = None
    height: int | None = None
    issues: tuple[str, ...] = ()
    limits: ImageLimits
    transform: ViewTransform | None = None
    metrics: QualityMetrics | None = None
    limitations: tuple[str, ...] = (
        "uncalibrated_quality_metrics",
        "focus_glare_framing_occlusion_not_determined",
        "no_heic_or_raw_decoder",
    )


def diagnose_image(
    data: bytes, limits: ImageLimits = ImageLimits()
) -> ImageDiagnostics:
    base = dict(
        input_sha256=sha256(data).hexdigest(), size_bytes=len(data), limits=limits
    )

    def reject(reason, **metadata):
        return ImageDiagnostics(status="rejected", issues=(reason,), **base, **metadata)

    if not data:
        return reject("empty_image")
    if len(data) > limits.max_bytes:
        return reject("byte_limit_exceeded")
    metadata = {}
    try:
        with Image.open(BytesIO(data)) as image:
            metadata = dict(format=image.format, width=image.width, height=image.height)
            if image.format not in limits.allowed_formats:
                return reject("unsupported_or_unapproved_format", **metadata)
            if (
                max(image.size) > limits.max_axis
                or image.width * image.height > limits.max_pixels
            ):
                return reject("resolution_limit_exceeded", **metadata)
            if getattr(image, "n_frames", 1) != 1:
                return reject("multi_frame_image_not_supported", **metadata)
            orientation = image.getexif().get(274, 1)
            if type(orientation) is not int or orientation not in range(1, 9):
                return reject("invalid_exif_orientation", **metadata)
        with Image.open(BytesIO(data)) as verification_image:
            verification_image.verify()
        with Image.open(BytesIO(data)) as image:
            image.load()  # Full decode detects malformed/truncated pixel payloads.
            view = ImageOps.exif_transpose(image)
            view.thumbnail((limits.sample_axis, limits.sample_axis))
            gray = view.convert("L")
            histogram = gray.histogram()
            count = gray.width * gray.height
            values = list(gray.tobytes())
            gradients = [
                abs(values[y * gray.width + x] - values[y * gray.width + x - 1])
                for y in range(gray.height)
                for x in range(1, gray.width)
            ]
            gradients += [
                abs(values[y * gray.width + x] - values[(y - 1) * gray.width + x])
                for y in range(1, gray.height)
                for x in range(gray.width)
            ]
            stats = ImageStat.Stat(gray)
            metrics = QualityMetrics(
                mean_luminance=stats.mean[0],
                contrast_stddev=stats.stddev[0],
                dark_fraction=sum(histogram[:6]) / count,
                bright_fraction=sum(histogram[250:]) / count,
                mean_neighbor_gradient=sum(gradients) / len(gradients)
                if gradients
                else 0,
                sample_width=gray.width,
                sample_height=gray.height,
            )
            issues = ("uniform_luminance",) if stats.stddev[0] == 0 else ()
            return ImageDiagnostics(
                status="valid",
                **base,
                **metadata,
                issues=issues,
                metrics=metrics,
                transform=orientation_transform(image.width, image.height, orientation),
            )
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        return reject("decompression_limit_exceeded", **metadata)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError):
        return reject("malformed_image", **metadata)


class RegionBox(FrozenRecord):
    id: str = Field(min_length=1)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class CoverageObservation(FrozenRecord):
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    algorithm_version: str = Field(min_length=1)
    raw_response_ref: str = Field(min_length=1)
    missing_regions: tuple[RegionBox, ...] = ()
    complete: bool = False
    synthetic: bool = False


class CoverageAdapter(Protocol):
    """Owner supplies approved full-image detector; not a region-count heuristic."""

    def check_coverage(
        self, input_sha256: str, regions: tuple[RegionBox, ...]
    ) -> CoverageObservation: ...


class GeometryDiagnostics(FrozenRecord):
    issues: tuple[str, ...]
    overlapping_pairs: tuple[tuple[str, str], ...]
    coverage_state: Literal["unmeasured", "incomplete", "reported_complete"]
    reviewer_confirmation_required: Literal[True] = True


def check_regions(
    width: int,
    height: int,
    regions: tuple[RegionBox, ...],
    input_sha256: str,
    coverage: CoverageObservation | None = None,
) -> GeometryDiagnostics:
    if width <= 0 or height <= 0 or len(regions) > 1000:
        raise ValueError("invalid dimensions or region limit exceeded")
    if len({r.id for r in regions}) != len(regions):
        raise ValueError("duplicate region ID")
    issues = [] if regions else ["zero_regions"]
    if any(r.x + r.width > width or r.y + r.height > height for r in regions):
        issues.append("region_out_of_bounds")
    overlaps = tuple(
        (a.id, b.id)
        for i, a in enumerate(regions)
        for b in regions[i + 1 :]
        if max(a.x, b.x) < min(a.x + a.width, b.x + b.width)
        and max(a.y, b.y) < min(a.y + a.height, b.y + b.height)
    )
    if overlaps:
        issues.append("overlapping_regions")
    state = "unmeasured"
    if coverage:
        if coverage.input_sha256 != input_sha256:
            raise ValueError("coverage input mismatch")
        state = (
            "reported_complete"
            if coverage.complete and not coverage.missing_regions
            else "incomplete"
        )
        if coverage.missing_regions:
            issues.append("missing_regions")
    return GeometryDiagnostics(
        issues=tuple(issues), overlapping_pairs=overlaps, coverage_state=state
    )


class DerivativeProvenance(FrozenRecord):
    original_sha256: str
    derivative_sha256: str
    transform: ViewTransform
    algorithm_version: str = "exif-transpose-png-v1"
    metadata_policy: Literal["strip_all"] = "strip_all"


def orientation_view(
    data: bytes, limits: ImageLimits = ImageLimits()
) -> tuple[bytes, DerivativeProvenance]:
    diagnostics = diagnose_image(data, limits)
    if diagnostics.status != "valid" or diagnostics.transform is None:
        raise ValueError("image rejected: " + ",".join(diagnostics.issues))
    with Image.open(BytesIO(data)) as original:
        view = ImageOps.exif_transpose(original).convert("RGB")
        # A new pixel-only image prevents EXIF, GPS, comments or ICC propagation.
        clean = Image.new("RGB", view.size)
        clean.paste(view)
        output = BytesIO()
        clean.save(output, format="PNG")
    derivative = output.getvalue()
    return derivative, DerivativeProvenance(
        original_sha256=diagnostics.input_sha256,
        derivative_sha256=sha256(derivative).hexdigest(),
        transform=diagnostics.transform,
    )
