from hashlib import sha256
from io import BytesIO
import os
import sys

from PIL import Image
import pytest

from specimen_digitization.application.image_codecs import (
    CodecPolicy,
    codec_capabilities,
    decode_image,
)
from specimen_digitization.application.image_quality import ImageLimits


def png(size=(24, 16)):
    out = BytesIO()
    Image.new("RGB", size, "green").save(out, format="PNG")
    return out.getvalue()


def local_policy(**kwargs):
    # Explicit test exception: macOS cannot enforce RLIMIT_AS.
    return CodecPolicy(require_memory_limit=False, **kwargs)


def test_raster_child_preserves_original_and_verified_derivative():
    data = png()
    result, derivative = decode_image(data, policy=local_policy())
    assert result.status == "decoded"
    assert result.input_sha256 == sha256(data).hexdigest()
    assert result.provenance.derivative_sha256 == sha256(derivative).hexdigest()
    assert result.provenance.actual_format == "PNG"
    assert result.provenance.cpu_limit_enforced
    with Image.open(BytesIO(derivative)) as view:
        assert view.size == (24, 16) and not view.info


def test_absent_disabled_and_unknown_family():
    assert codec_capabilities(CodecPolicy())[1].status == "disabled"
    assert decode_image(b"fake heic", "HEIC")[0].reason == "codec_disabled"
    assert (
        decode_image(b"fake raw", "NEF", local_policy())[0].reason
        == "raw_family_not_approved"
    )
    caps = codec_capabilities(local_policy(enable_heic=True))
    if caps[1].status == "missing":
        assert (
            decode_image(b"fake heic", "HEIC", local_policy(enable_heic=True))[0].reason
            == "codec_missing"
        )


def test_real_process_timeout_and_limits():
    assert (
        decode_image(png(), policy=local_policy(wall_seconds=0.000001))[0].reason
        == "codec_wall_timeout"
    )
    assert (
        decode_image(png(), policy=local_policy(limits=ImageLimits(max_bytes=10)))[
            0
        ].reason
        == "empty_or_oversize_input"
    )
    assert (
        decode_image(png(), policy=local_policy(limits=ImageLimits(max_pixels=100)))[
            0
        ].status
        == "rejected"
    )
    assert decode_image(b"corrupt", policy=local_policy())[0].status == "rejected"
    out = BytesIO()
    Image.frombytes("RGB", (64, 64), os.urandom(64 * 64 * 3)).save(out, format="PNG")
    assert (
        decode_image(out.getvalue(), policy=local_policy(max_output_bytes=1024))[
            0
        ].reason
        == "codec_output_limit_exceeded"
    )


def test_default_requires_memory_enforcement():
    result, derivative = decode_image(png())
    if sys.platform == "darwin":
        assert result.reason == "memory_limit_unavailable" and derivative is None
    elif result.status == "decoded":
        assert result.provenance.memory_limit_enforced


def heic(orientation=1):
    heif = pytest.importorskip("pillow_heif")
    image = Image.new("RGB", (96, 64), "red")
    exif = Image.Exif()
    exif[274] = orientation
    image.info["exif"] = exif.tobytes()
    buffer = BytesIO()
    heif.from_bytes("RGB", image.size, image.tobytes()).save(
        buffer, quality=90, exif=exif.tobytes()
    )
    return buffer.getvalue()


def dng(orientation=1):
    tifffile = pytest.importorskip("tifffile")
    np = pytest.importorskip("numpy")
    out = BytesIO()
    data = (np.indices((64, 96)).sum(axis=0) * 200).astype("uint16")
    tags = [
        (274, "H", 1, orientation, False),
        (50706, "B", 4, (1, 4, 0, 0), False),
        (50707, "B", 4, (1, 1, 0, 0), False),
        (50708, "s", 0, "Synthetic fixture", False),
        (33421, "H", 2, (2, 2), False),
        (33422, "B", 4, (0, 1, 1, 2), False),
        (50714, "H", 1, 0, False),
        (50717, "I", 1, 65535, False),
        (50721, "2i", 9, (1, 1, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1, 1), False),
        (50728, "2I", 3, (1, 1, 1, 1, 1, 1), False),
        (50778, "H", 1, 21, False),
    ]
    tifffile.imwrite(out, data, photometric=32803, metadata=None, extratags=tags)
    return out.getvalue()


@pytest.mark.parametrize("orientation", [1, 3, 6, 8])
def test_real_synthetic_heic(orientation):
    data = heic(orientation)
    policy = local_policy(enable_heic=True)
    result, derivative = decode_image(data, "HEIC", policy)
    assert result.status == "decoded", result
    assert result.provenance.original_sha256 == sha256(data).hexdigest()
    assert result.provenance.coordinate_space == "decoded_heif_primary_pixel_edges"
    with Image.open(BytesIO(derivative)) as view:
        assert view.size == ((64, 96) if orientation in (6, 8) else (96, 64))
        assert not view.info
    assert decode_image(data[:40], "HEIC", policy)[0].status == "rejected"
    assert (
        decode_image(
            data,
            "HEIC",
            local_policy(enable_heic=True, limits=ImageLimits(max_pixels=100)),
        )[0].reason
        == "resolution_limit_exceeded"
    )


@pytest.mark.parametrize("orientation", [1, 3, 6, 8])
def test_real_synthetic_dng(orientation):
    pytest.importorskip("rawpy")
    data = dng(orientation)
    assert decode_image(data, "TIFF", local_policy())[0].reason == "codec_disabled"
    policy = local_policy(approved_raw_families=("DNG",))
    result, derivative = decode_image(data, "DNG", policy)
    assert result.status == "decoded", result
    assert result.provenance.actual_format == "DNG"
    assert result.provenance.sensor_crop == (0, 0, 96, 64)
    assert result.provenance.transform.orientation == orientation
    with Image.open(BytesIO(derivative)) as view:
        assert view.size == ((64, 96) if orientation in (6, 8) else (96, 64))
        assert not view.info
    assert decode_image(png(), "DNG", policy)[0].reason == "dng_signature_missing"
    assert (
        decode_image(
            data,
            "DNG",
            local_policy(
                approved_raw_families=("DNG",), limits=ImageLimits(max_pixels=100)
            ),
        )[0].reason
        == "resolution_limit_exceeded"
    )


def test_mismatched_codec_version_fails_before_native_decode():
    capability = codec_capabilities(
        local_policy(enable_heic=True, heif_package_version="never-approved")
    )[1]
    result, output = decode_image(
        b"not a real file",
        "HEIC",
        local_policy(enable_heic=True, heif_package_version="never-approved"),
    )
    assert result.reason == "codec_" + capability.status
    assert output is None


def test_cpu_limit_stops_actual_child():
    import subprocess

    code = "from specimen_digitization.application.image_codecs import _limits, CodecPolicy\n_limits(CodecPolicy(cpu_seconds=1, require_memory_limit=False))\nwhile True: pass"
    child = subprocess.run(
        [sys.executable, "-c", code],
        timeout=5,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert child.returncode < 0
