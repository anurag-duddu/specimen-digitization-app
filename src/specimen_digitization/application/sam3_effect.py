"""Trusted child-only SAM request and strict response-to-admission binding."""

import base64
import hashlib
import json
import math
import re
from uuid import NAMESPACE_URL, uuid5

from ..hub_models import SAM3_MODEL

SAM3_IMPLEMENTATION = "transformers/5.14.0;torch/2.8.0;cpu"
SHA256 = re.compile(r"^[a-f0-9]{64}$")
GENERATION = re.compile(r"^[1-9][0-9]*$")


def canonical_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def canonical_sha256(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _source(value):
    if not isinstance(value, dict):
        raise ValueError("source must be an object")
    required = {"bucket", "object_name", "generation", "sha256", "size_bytes"}
    if not required <= value.keys() or value.keys() - required - {"crc32c", "md5_hash"}:
        raise ValueError("source fields missing or unknown")
    if not all(isinstance(value[key], str) for key in required - {"size_bytes"}):
        raise ValueError("source string type")
    if (
        not 3 <= len(value["bucket"]) <= 222
        or not 1 <= len(value["object_name"]) <= 1024
    ):
        raise ValueError("source location bounds")
    if not GENERATION.fullmatch(value["generation"]) or not SHA256.fullmatch(
        value["sha256"]
    ):
        raise ValueError("source immutable binding")
    if (
        type(value["size_bytes"]) is not int
        or not 0 < value["size_bytes"] <= 25_000_000
    ):
        raise ValueError("source size bounds")
    return dict(value, crc32c=value.get("crc32c"), md5_hash=value.get("md5_hash"))


def validate_expected_binding(payload):
    """Refuse outbound work without the coordinator's frozen source binding."""
    try:
        expected, request = payload["expected"], payload["request"]
        if not SHA256.fullmatch(expected["manifest_sha256"]):
            return False
        files = expected["checkpoint_files"]
        if (
            not isinstance(files, dict)
            or not 1 <= len(files) <= 64
            or not all(isinstance(name, str) for name in files)
            or not any(name.endswith(".safetensors") for name in files)
        ):
            return False
        for name, sha in files.items():
            if (
                not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9._-]{0,200}\.(safetensors|json|txt)", name
                )
                or not isinstance(sha, str)
                or not SHA256.fullmatch(sha)
            ):
                return False
        source = _source(expected["source"])
        if source["sha256"] != request["sha256"]:
            return False
        if (
            not isinstance(expected["output_bucket"], str)
            or not 3 <= len(expected["output_bucket"]) <= 222
        ):
            return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def validate_sam3_response(value, payload):
    """Return a retained validation state; never accept partial provenance."""
    from .domain import Region

    if not validate_expected_binding(payload):
        return "expected_binding_missing_or_invalid"
    try:
        request, expected = payload["request"], payload["expected"]
        if not isinstance(value, dict):
            return "invalid_response_shape"
        if (
            value.get("model_id"),
            value.get("model_revision"),
            value.get("implementation"),
        ) != (SAM3_MODEL.repo_id, SAM3_MODEL.revision, SAM3_IMPLEMENTATION) or request[
            "model_revision"
        ] != SAM3_MODEL.revision:
            return "unpinned_response"
        if value.get("request_sha256") != canonical_sha256(request):
            return "request_binding_mismatch"
        if value.get("manifest_sha256") != expected["manifest_sha256"]:
            return "manifest_binding_mismatch"
        if _source(value.get("source")) != _source(expected["source"]):
            return "source_binding_mismatch"
        files = value.get("checkpoint_files")
        if not isinstance(files, dict) or not 1 <= len(files) <= 64:
            return "invalid_checkpoint_provenance"
        for name, sha in files.items():
            if (
                not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9._-]{0,200}\.(safetensors|json|txt)", name
                )
                or not isinstance(sha, str)
                or not SHA256.fullmatch(sha)
            ):
                return "invalid_checkpoint_provenance"
        if value.get("checkpoint_sha256") != canonical_sha256(files):
            return "checkpoint_digest_mismatch"
        if expected["checkpoint_files"] != files:
            return "checkpoint_binding_mismatch"
        if value.get("threshold") != 0.5 or value.get("mask_threshold") != 0.5:
            return "unpinned_segmentation_thresholds"
        regions, masks = value.get("regions"), value.get("masks")
        if (
            not isinstance(regions, list)
            or not isinstance(masks, list)
            or not 0 < len(regions) <= 64
            or len(regions) != len(masks)
        ):
            return "invalid_region_provenance"
        total_bytes = 0
        for index, (raw_region, mask) in enumerate(zip(regions, masks, strict=True)):
            if not isinstance(raw_region, dict) or not isinstance(mask, dict):
                return "invalid_region_provenance"
            if any(
                type(raw_region.get(key)) is not int
                for key in ("x", "y", "width", "height", "order")
            ):
                return "invalid_region_geometry"
            region = Region.model_validate(raw_region)
            expected_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"sam3/{expected['manifest_sha256']}/{request['specimen_id']}/{index}",
                )
            )
            if (
                region.id != expected_id
                or region.order != index
                or region.method != "sam3"
                or region.version != request["model_revision"]
                or region.asset_id != request["asset_id"]
                or region.x + region.width > request["width"]
                or region.y + region.height > request["height"]
                or region.rotation_quarter_turns != 0
                or region.crop_ref is not None
            ):
                return "invalid_region_provenance"
            sha, generation = mask.get("sha256"), mask.get("generation")
            if (
                not isinstance(sha, str)
                or not SHA256.fullmatch(sha)
                or not isinstance(generation, str)
                or not GENERATION.fullmatch(generation)
            ):
                return "invalid_mask_provenance"
            if (
                mask.get("bucket") != expected["output_bucket"]
                or mask.get("object_name") != "application/sha256/" + sha
                or region.mask_ref != sha + ":" + generation
                or mask.get("encoding") != "binary-png-original-pixels"
            ):
                return "mask_binding_mismatch"
            size, score = mask.get("size_bytes"), mask.get("score")
            if (
                type(size) is not int
                or not 0 < size <= 2_000_000
                or type(score) not in (int, float)
                or not math.isfinite(score)
                or not 0 <= score <= 1
            ):
                return "invalid_mask_provenance"
            total_bytes += size
        return "valid" if total_bytes <= 16_000_000 else "mask_byte_limit"
    except (KeyError, ValueError, TypeError, OverflowError):
        return "invalid_response_provenance"


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate response JSON key")
        value[key] = item
    return value


def sam3_request(payload):
    if not validate_expected_binding(payload):
        raise ValueError("SAM expected binding missing or invalid")
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import fetch_id_token

    bearer = fetch_id_token(Request(), payload["endpoint"])
    return sam3_exchange(payload, bearer)


def sam3_exchange(payload, bearer):
    import httpx

    if not validate_expected_binding(payload):
        raise ValueError("SAM expected binding missing or invalid")
    with httpx.Client(
        timeout=payload["timeout_seconds"], follow_redirects=False
    ) as client:
        with client.stream(
            "POST",
            payload["endpoint"] + "/v1/segment",
            headers={
                "Authorization": "Bearer " + bearer,
                "Idempotency-Key": payload["request"]["run_id"] + ":segment",
            },
            json=payload["request"],
        ) as response:
            raw = bytearray()
            for chunk in response.iter_raw(chunk_size=8192):
                if len(raw) + len(chunk) > payload["max_response_bytes"]:
                    raise ValueError("SAM response byte limit")
                raw.extend(chunk)
            raw = bytes(raw)
            validation = "http_error"
            if response.status_code == 200:
                try:
                    value = json.loads(raw, object_pairs_hook=_unique_object)
                    validation = validate_sam3_response(value, payload)
                except (ValueError, TypeError):
                    validation = "invalid_response_json"
            return json.dumps(
                {
                    "http_status": response.status_code,
                    "validation": validation,
                    "body_base64": base64.b64encode(raw).decode(),
                },
                separators=(",", ":"),
            ).encode()
