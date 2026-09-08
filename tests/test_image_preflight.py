from hashlib import sha256
from io import BytesIO

from PIL import Image

from specimen_digitization.application.image_codecs import CodecPolicy
from specimen_digitization.application.image_preflight import (
    PreflightResult,
    preflight_image,
)


def test_preflight_is_explicit_server_check_without_record_creation():
    out = BytesIO()
    Image.new("RGB", (20, 10), "white").save(out, format="PNG")
    data = out.getvalue()
    result = preflight_image(data, "image/png", CodecPolicy(require_memory_limit=False))
    assert result.status == "review"
    assert result.origin == "server_preflight" and result.source_transmitted
    assert not result.specimen_created and not result.external_provider_used
    assert result.input_sha256 == sha256(data).hexdigest() and result.size_bytes == len(
        data
    )
    assert result.actual_format == "PNG"
    assert result.diagnostics.metrics.bright_fraction == 1
    assert "glare" in result.unmeasured
    assert PreflightResult.model_validate_json(result.model_dump_json()) == result


def test_mime_mismatch_and_missing_codec_are_not_success():
    out = BytesIO()
    Image.new("RGB", (20, 10)).save(out, format="PNG")
    result = preflight_image(
        out.getvalue(), "image/jpeg", CodecPolicy(require_memory_limit=False)
    )
    assert "declared_media_type_mismatch" in result.issues
    result = preflight_image(b"fake-heic", "image/heic")
    assert result.status == "blocked" and result.diagnostics is None
    assert not result.specimen_created


def test_rejected_or_blocked_hint_never_claims_actual_format():
    result = preflight_image(b"fake-heic", "image/heic")
    assert result.actual_format is None
    assert result.decode.family == "HEIC"  # requested decoder family only


def test_memory_enforcement_block_has_runtime_action(monkeypatch):
    from specimen_digitization.application import image_preflight
    from specimen_digitization.application.image_codecs import DecodeResult

    def memory_block(data, format_hint, policy):
        return DecodeResult(
            status="blocked",
            input_sha256=sha256(data).hexdigest(),
            size_bytes=len(data),
            family="RASTER",
            reason="memory_limit_unavailable",
        ), None

    monkeypatch.setattr(image_preflight, "decode_image", memory_block)
    result = preflight_image(b"synthetic-boundary-input", "image/png")
    assert result.status == "blocked"
    assert result.action_hints == ("configure_runtime_memory_enforcement",)
    assert result.issues == ("memory_limit_unavailable",)
    assert result.diagnostics is None and not result.specimen_created
