"""Optional local decoders in a bounded child process. No global PIL registration."""

from __future__ import annotations

from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from io import BytesIO
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Literal

from PIL import Image, ImageOps
from pydantic import Field

from .collection_profiles import FrozenRecord
from .image_quality import (
    ImageLimits,
    ViewTransform,
    orientation_transform,
    orientation_view,
)


class CodecPolicy(FrozenRecord):
    version: str = "local-codecs-v1"
    enable_heic: bool = False
    approved_raw_families: tuple[Literal["DNG"], ...] = ()
    heif_package_version: str = "1.7.0"
    raw_package_version: str = "0.27.1"
    limits: ImageLimits = ImageLimits()
    wall_seconds: float = Field(default=15, gt=0, le=30)
    cpu_seconds: int = Field(default=10, ge=1, le=20)
    memory_bytes: int = Field(default=1_500_000_000, ge=256_000_000, le=2_000_000_000)
    max_output_bytes: int = Field(default=25_000_000, ge=1024, le=25_000_000)
    require_memory_limit: bool = True


class CodecCapability(FrozenRecord):
    family: str
    status: Literal["available", "disabled", "missing", "version_mismatch"]
    package: str
    installed_version: str | None
    required_version: str | None = None
    reason: str


def codec_capabilities(policy: CodecPolicy) -> tuple[CodecCapability, ...]:
    result = [
        CodecCapability(
            family="JPEG/PNG/TIFF",
            status="available",
            package="Pillow",
            installed_version=version("Pillow"),
            reason="subject_to_profile_formats",
        )
    ]
    for family, package, enabled, required in (
        ("HEIC", "pillow-heif", policy.enable_heic, policy.heif_package_version),
        (
            "DNG",
            "rawpy",
            "DNG" in policy.approved_raw_families,
            policy.raw_package_version,
        ),
    ):
        try:
            installed = version(package)
        except PackageNotFoundError:
            installed = None
        status = (
            "disabled"
            if not enabled
            else "missing"
            if installed is None
            else "version_mismatch"
            if installed != required
            else "available"
        )
        result.append(
            CodecCapability(
                family=family,
                status=status,
                package=package,
                installed_version=installed,
                required_version=required,
                reason="codec_" + status,
            )
        )
    return tuple(result)


class DecodeProvenance(FrozenRecord):
    original_sha256: str
    derivative_sha256: str
    family: str
    actual_format: str
    codec: str
    codec_version: str
    native_library_version: str | None = None
    algorithm_version: str = "bounded-codec-png-v1"
    coordinate_space: Literal[
        "original_pixel_edges",
        "decoded_heif_primary_pixel_edges",
        "raw_active_area_pixel_edges",
    ]
    transform: ViewTransform
    sensor_crop: tuple[int, int, int, int] | None = None
    conversion: tuple[str, ...]
    memory_limit_enforced: bool
    cpu_limit_enforced: bool
    metadata_policy: Literal["strip_all"] = "strip_all"


class DecodeResult(FrozenRecord):
    status: Literal["decoded", "blocked", "rejected"]
    input_sha256: str
    size_bytes: int
    family: str
    reason: str
    provenance: DecodeProvenance | None = None


def _family(data: bytes, hint: str) -> str:
    # Hints choose a restricted decoder, never establish file validity.
    normalized = hint.upper().lstrip(".")
    if _is_dng(data):
        return "DNG"
    if normalized in {"DNG", "RAW", "CR2", "CR3", "NEF", "ARW", "RAF", "ORF", "RW2"}:
        return normalized
    if data[4:8] == b"ftyp" and any(
        brand in data[8:64] for brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1")
    ):
        return "HEIC"
    if normalized in {"HEIC", "HEIF"}:
        return "HEIC"
    return "RASTER"


def _is_dng(data: bytes) -> bool:
    if len(data) < 8 or data[:4] not in (b"II*\x00", b"MM\x00*"):
        return False
    endian = "<" if data[:2] == b"II" else ">"
    offset = struct.unpack_from(endian + "I", data, 4)[0]
    if offset + 2 > len(data):
        return False
    count = struct.unpack_from(endian + "H", data, offset)[0]
    if count > 4096 or offset + 2 + 12 * count > len(data):
        return False
    for index in range(count):
        entry = offset + 2 + 12 * index
        tag, kind, length = struct.unpack_from(endian + "HHI", data, entry)
        if tag == 50706 and kind == 1 and length == 4:
            return data[entry + 8] == 1
    return False


def decode_image(
    data: bytes, format_hint: str = "", policy: CodecPolicy = CodecPolicy()
) -> tuple[DecodeResult, bytes | None]:
    digest = sha256(data).hexdigest()
    family = _family(data, format_hint)

    def fail(status, reason):
        return DecodeResult(
            status=status,
            input_sha256=digest,
            size_bytes=len(data),
            family=family,
            reason=reason,
        ), None

    if not data or len(data) > policy.limits.max_bytes:
        return fail("rejected", "empty_or_oversize_input")
    if family not in {"RASTER", "HEIC", "DNG"}:
        return fail("blocked", "raw_family_not_approved")
    if family in {"HEIC", "DNG"}:
        capability = next(c for c in codec_capabilities(policy) if c.family == family)
        if capability.status != "available":
            return fail("blocked", capability.reason)
    with TemporaryDirectory(prefix="specimen-codec-") as directory:
        root = Path(directory)
        (root / "input").write_bytes(data)
        request = dict(
            directory=directory, family=family, policy=policy.model_dump(mode="json")
        )
        try:
            completed = subprocess.run(
                [sys.executable, "-m", __name__, "--decode-worker"],
                input=json.dumps(request).encode(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=policy.wall_seconds,
                check=False,
                env={
                    **{
                        key: os.environ[key]
                        for key in (
                            "PATH",
                            "PYTHONPATH",
                            "VIRTUAL_ENV",
                            "SYSTEMROOT",
                            "LANG",
                        )
                        if key in os.environ
                    },
                    "OMP_NUM_THREADS": "1",
                },
            )
        except subprocess.TimeoutExpired:
            return fail("blocked", "codec_wall_timeout")
        result_path, output_path = root / "result.json", root / "output.png"
        if completed.returncode != 0 or not result_path.is_file():
            return fail("blocked", "codec_process_failed_or_resource_limit")
        if result_path.stat().st_size > 32_000:
            return fail("blocked", "codec_result_limit_exceeded")
        record = json.loads(result_path.read_text())
        if "error" in record:
            return fail(record["status"], record["error"])
        if (
            not output_path.is_file()
            or output_path.stat().st_size > policy.max_output_bytes
        ):
            return fail("blocked", "codec_output_limit_exceeded")
        output = output_path.read_bytes()
        provenance = DecodeProvenance.model_validate(record)
        if (
            provenance.original_sha256 != digest
            or provenance.derivative_sha256 != sha256(output).hexdigest()
        ):
            return fail("blocked", "codec_digest_mismatch")
        return DecodeResult(
            status="decoded",
            input_sha256=digest,
            size_bytes=len(data),
            family=family,
            reason="decoded_local",
            provenance=provenance,
        ), output


def _limits(policy: CodecPolicy) -> tuple[bool, bool]:
    import resource

    cpu = memory = False
    try:
        resource.setrlimit(
            resource.RLIMIT_CPU, (policy.cpu_seconds, policy.cpu_seconds)
        )
        cpu = True
        resource.setrlimit(
            resource.RLIMIT_FSIZE, (policy.max_output_bytes, policy.max_output_bytes)
        )
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ValueError, OSError):
        pass
    try:
        resource.setrlimit(
            resource.RLIMIT_AS, (policy.memory_bytes, policy.memory_bytes)
        )
        memory = True
    except (ValueError, OSError):
        pass
    return cpu, memory


def _check_size(width: int, height: int, limits: ImageLimits):
    if (
        min(width, height) <= 0
        or max(width, height) > limits.max_axis
        or width * height > limits.max_pixels
    ):
        raise ValueError("resolution_limit_exceeded")


def _decode_worker(request: dict) -> None:
    root = Path(request["directory"])
    policy = CodecPolicy.model_validate(request["policy"])
    cpu, memory = _limits(policy)
    if policy.require_memory_limit and not memory:
        (root / "result.json").write_text(
            json.dumps(dict(status="blocked", error="memory_limit_unavailable"))
        )
        return
    try:
        data = (root / "input").read_bytes()
        family = request["family"]
        crop = None
        native_version = None
        if family == "RASTER":
            output, old = orientation_view(data, policy.limits)
            with Image.open(BytesIO(data)) as header:
                actual_format = header.format
            transform = old.transform
            codec, codec_version = "Pillow", version("Pillow")
            coordinate_space = "original_pixel_edges"
            conversion = ("exif_orientation", "rgb8", "metadata_strip")
        elif family == "HEIC":
            import pillow_heif

            actual_format = "HEIC"
            # Keep libheif security limits enabled; no global Pillow registration.
            if pillow_heif.options.DISABLE_SECURITY_LIMITS:
                raise ValueError("codec_security_limits_disabled")
            if pillow_heif.get_file_mimetype(data) not in {"image/heic", "image/heif"}:
                raise ValueError("heic_signature_missing")
            heif = pillow_heif.open_heif(BytesIO(data), convert_hdr_to_8bit=True)
            if len(heif) != 1:
                raise ValueError("multi_frame_image_not_supported")
            _check_size(*heif.size, policy.limits)
            image = Image.frombytes(
                heif.mode, heif.size, heif.data, "raw", heif.mode, heif.stride
            ).convert("RGB")
            # libheif applies container transforms; EXIF must not rotate twice.
            transform = orientation_transform(image.width, image.height, 1)
            coordinate_space = "decoded_heif_primary_pixel_edges"
            codec, codec_version = "pillow-heif", pillow_heif.__version__
            native_version = pillow_heif.libheif_info()["libheif"]
            conversion = (
                "libheif_container_orientation",
                "hdr_to_rgb8",
                "metadata_strip",
                "encoded_grid_to_primary_mapping_unavailable",
            )
        elif family == "DNG":
            import rawpy

            actual_format = "DNG"
            # DNG identity is checked from its container, not extension alone.
            if not _is_dng(data):
                raise ValueError("dng_signature_missing")
            with rawpy.RawPy() as raw:
                raw.open_buffer(BytesIO(data))
                sizes = raw.sizes
                _check_size(sizes.raw_width, sizes.raw_height, policy.limits)
                if sizes.pixel_aspect != 1 or sizes.flip not in {0, 3, 5, 6}:
                    raise ValueError("raw_geometry_not_supported")
                raw.unpack()
                rgb = raw.postprocess(
                    user_flip=0,
                    output_bps=8,
                    no_auto_bright=True,
                    use_auto_wb=False,
                    use_camera_wb=False,
                )
                image = Image.fromarray(rgb, "RGB")
                _check_size(image.width, image.height, policy.limits)
                if image.size != (sizes.width, sizes.height):
                    raise ValueError("raw_active_area_mapping_mismatch")
                orientation = {0: 1, 3: 3, 5: 8, 6: 6}[sizes.flip]
                transform = orientation_transform(
                    image.width, image.height, orientation
                )
                image.info["exif"] = b""
                exif = Image.Exif()
                exif[274] = orientation
                image.info["exif"] = exif.tobytes()
                image = ImageOps.exif_transpose(image)
                crop = (sizes.left_margin, sizes.top_margin, sizes.width, sizes.height)
            coordinate_space = "raw_active_area_pixel_edges"
            codec, codec_version = "rawpy", rawpy.__version__
            native_version = ".".join(map(str, rawpy.libraw_version))
            conversion = (
                "libraw_demosaic",
                "no_auto_bright",
                "default_white_balance",
                "srgb8",
                "native_flip_to_exif",
                "metadata_strip",
            )
        else:
            raise ValueError("raw_family_not_approved")
        if family != "RASTER":
            clean = Image.new("RGB", image.size)
            clean.paste(image)
            buffer = BytesIO()
            clean.save(buffer, format="PNG")
            output = buffer.getvalue()
        if len(output) > policy.max_output_bytes:
            raise ValueError("codec_output_limit_exceeded")
        (root / "output.png").write_bytes(output)
        provenance = DecodeProvenance(
            original_sha256=sha256(data).hexdigest(),
            derivative_sha256=sha256(output).hexdigest(),
            family=family,
            actual_format=actual_format,
            codec=codec,
            codec_version=codec_version,
            native_library_version=native_version,
            coordinate_space=coordinate_space,
            transform=transform,
            sensor_crop=crop,
            conversion=conversion,
            memory_limit_enforced=memory,
            cpu_limit_enforced=cpu,
        )
        (root / "result.json").write_text(provenance.model_dump_json())
    except (ImportError, MemoryError) as error:
        reason = (
            "codec_runtime_unavailable"
            if isinstance(error, ImportError)
            else "codec_memory_limit"
        )
        (root / "result.json").write_text(
            json.dumps(dict(status="blocked", error=reason))
        )
    except Exception as error:
        safe_reasons = {
            "resolution_limit_exceeded",
            "multi_frame_image_not_supported",
            "codec_security_limits_disabled",
            "dng_signature_missing",
            "heic_signature_missing",
            "raw_geometry_not_supported",
            "raw_active_area_mapping_mismatch",
            "codec_output_limit_exceeded",
        }
        reason = (
            str(error)
            if type(error) is ValueError and str(error) in safe_reasons
            else "malformed_or_unsupported_codec_input"
        )
        # Never echo untrusted metadata, paths, codec diagnostics or source contents.
        (root / "result.json").write_text(
            json.dumps(dict(status="rejected", error=reason))
        )


if __name__ == "__main__" and sys.argv[1:] == ["--decode-worker"]:
    _decode_worker(json.loads(sys.stdin.buffer.read(32_000)))
