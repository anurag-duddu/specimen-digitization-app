"""Before-submission server analysis; no upload record or provider effect is created."""

from __future__ import annotations

from typing import Literal

from .collection_profiles import FrozenRecord
from .image_codecs import (
    CodecCapability,
    CodecPolicy,
    DecodeResult,
    codec_capabilities,
    decode_image,
)
from .image_quality import ImageDiagnostics, diagnose_image


class PreflightResult(FrozenRecord):
    contract_version: Literal["image-preflight-v1"] = "image-preflight-v1"
    origin: Literal["server_preflight"] = "server_preflight"
    status: Literal["review", "blocked", "rejected"]
    input_sha256: str
    size_bytes: int
    declared_media_type: str
    actual_format: str | None
    decode: DecodeResult
    diagnostics: ImageDiagnostics | None = None
    capabilities: tuple[CodecCapability, ...]
    issues: tuple[str, ...]
    action_hints: tuple[str, ...]
    unmeasured: tuple[str, ...] = (
        "focus",
        "glare",
        "framing",
        "label_coverage",
        "museum_quality_acceptance",
    )
    source_transmitted: Literal[True] = True
    specimen_created: Literal[False] = False
    original_preserved: Literal[True] = True
    external_provider_used: Literal[False] = False


def preflight_image(
    data: bytes, declared_media_type: str, policy: CodecPolicy = CodecPolicy()
) -> PreflightResult:
    """Invoke only after explicit UI server-check action; intake revalidates originals."""
    hints = {
        "image/heic": "HEIC",
        "image/heif": "HEIC",
        "image/dng": "DNG",
        "image/x-adobe-dng": "DNG",
        "image/x-canon-cr2": "CR2",
        "image/x-nikon-nef": "NEF",
        "image/raw": "RAW",
    }
    decoded, derivative = decode_image(data, hints.get(declared_media_type, ""), policy)
    diagnostics = None
    actual = None  # A decoder hint does not establish actual format.
    issues = [decoded.reason]
    status = decoded.status if decoded.status != "decoded" else "review"
    actions = (
        ("configure_approved_codec_or_choose_supported_format",)
        if status == "blocked"
        else ("choose_valid_image",)
    )
    if derivative is not None:
        derived_limits = policy.limits.model_copy(
            update={"max_bytes": policy.max_output_bytes, "allowed_formats": ("PNG",)}
        )
        diagnostics = diagnose_image(derivative, derived_limits)
        actual = decoded.provenance.actual_format
        issues = list(diagnostics.issues)
        if diagnostics.status == "rejected":
            status = "rejected"
        else:
            actions = (
                "inspect_original_focus_glare_and_framing",
                "confirm_before_creating_specimen",
            )
            if decoded.provenance and not decoded.provenance.memory_limit_enforced:
                issues.append("memory_limit_not_enforced_local_test_only")
            expected = {
                "JPEG": "image/jpeg",
                "PNG": "image/png",
                "TIFF": "image/tiff",
                "HEIC": "image/heic",
                "DNG": "image/dng",
            }.get(actual)
            aliases = {"image/heif": "image/heic", "image/x-adobe-dng": "image/dng"}
            if aliases.get(declared_media_type, declared_media_type) != expected:
                issues.append("declared_media_type_mismatch")
    return PreflightResult(
        status=status,
        input_sha256=decoded.input_sha256,
        size_bytes=decoded.size_bytes,
        declared_media_type=declared_media_type,
        actual_format=actual,
        decode=decoded,
        diagnostics=diagnostics,
        capabilities=codec_capabilities(policy),
        issues=tuple(issues),
        action_hints=actions,
    )
