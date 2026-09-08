"""Forged HTTP response tests; all source/model values here are fixtures."""

import base64
import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

import httpx
import pytest

from specimen_digitization.application.sam3_effect import (
    SAM3_IMPLEMENTATION,
    canonical_sha256,
    sam3_exchange,
    validate_sam3_response,
)
from specimen_digitization.hub_models import SAM3_MODEL


def expected_binding(request):
    return {
        "manifest_sha256": "a" * 64,
        "output_bucket": "fixture-evidence",
        "checkpoint_files": {"model.safetensors": "b" * 64, "config.json": "c" * 64},
        "source": {
            "bucket": "fixture-source",
            "object_name": "approved-image.png",
            "generation": "17",
            "sha256": request["sha256"],
            "size_bytes": 128,
        },
    }


def legitimate_body(request, expected):
    mask_sha = hashlib.sha256(b"fixture mask bytes").hexdigest()
    return {
        "model_id": "facebook/sam3",
        "model_revision": SAM3_MODEL.revision,
        "implementation": SAM3_IMPLEMENTATION,
        "request_sha256": canonical_sha256(request),
        "manifest_sha256": expected["manifest_sha256"],
        "source": dict(expected["source"], crc32c=None, md5_hash=None),
        "checkpoint_files": expected["checkpoint_files"].copy(),
        "checkpoint_sha256": canonical_sha256(expected["checkpoint_files"]),
        "threshold": 0.5,
        "mask_threshold": 0.5,
        "regions": [
            {
                "id": str(
                    uuid5(
                        NAMESPACE_URL,
                        f"sam3/{expected['manifest_sha256']}/{request['specimen_id']}/0",
                    )
                ),
                "asset_id": request["asset_id"],
                "x": 0,
                "y": 0,
                "width": request["width"],
                "height": request["height"],
                "order": 0,
                "method": "sam3",
                "version": SAM3_MODEL.revision,
                "mask_ref": mask_sha + ":29",
            }
        ],
        "masks": [
            {
                "bucket": expected["output_bucket"],
                "object_name": "application/sha256/" + mask_sha,
                "generation": "29",
                "sha256": mask_sha,
                "size_bytes": 18,
                "score": 0.8,
                "encoding": "binary-png-original-pixels",
            }
        ],
    }


@pytest.fixture
def payload():
    request = {
        "run_id": "fixture-run",
        "asset_id": "fixture-asset",
        "specimen_id": "fixture-specimen",
        "sha256": "d" * 64,
        "model_id": SAM3_MODEL.repo_id,
        "model_revision": SAM3_MODEL.revision,
        "width": 120,
        "height": 80,
        "prompt": "label",
        "parameters": {},
        "adapter_version": "sam3-http-v1",
        "settings_version": "sam3-settings-v1",
        "blob_ref": "d" * 64 + ":18",
        "organization_id": "fixture-org",
        "collection_id": "fixture-collection",
    }
    return {
        "request": request,
        "expected": expected_binding(request),
        "endpoint": "https://fixture.run.app",
        "timeout_seconds": 2,
        "max_response_bytes": 1024 * 1024,
    }


def test_complete_response_binds_to_exact_admission(payload):
    value = legitimate_body(payload["request"], payload["expected"])
    assert validate_sam3_response(value, payload) == "valid"
    # Server and client canonicalization must remain byte-identical.
    from specimen_digitization.application.sam3_server import encoded

    assert (
        canonical_sha256(payload["request"])
        == hashlib.sha256(encoded(payload["request"])).hexdigest()
    )


@pytest.mark.parametrize(
    "field",
    [
        "request_sha256",
        "manifest_sha256",
        "source",
        "checkpoint_files",
        "checkpoint_sha256",
        "implementation",
        "masks",
        "regions",
    ],
)
def test_missing_binding_fields_never_accepted(payload, field):
    value = legitimate_body(payload["request"], payload["expected"])
    del value[field]
    assert validate_sam3_response(value, payload) != "valid"


@pytest.mark.parametrize(
    "path,replacement",
    [
        (("request_sha256",), "0" * 64),
        (("manifest_sha256",), "0" * 64),
        (("implementation",), "unreviewed/model"),
        (("model_revision",), "main"),
        (("source", "bucket"), "other-source"),
        (("source", "object_name"), "different.png"),
        (("source", "generation"), "18"),
        (("source", "sha256"), "0" * 64),
        (("source", "size_bytes"), 129),
        (("checkpoint_sha256",), "0" * 64),
        (("threshold",), 0.1),
        (("mask_threshold",), 0.1),
        (("regions", 0, "mask_ref"), "anything"),
        (("regions", 0, "mask_ref"), "e" * 64 + ":29"),
        (("regions", 0, "mask_ref"), "f" * 64 + ":0"),
        (("regions", 0, "width"), 121),
        (("regions", 0, "x"), -1),
        (("regions", 0, "height"), True),
        (("regions", 0, "order"), 1),
        (("regions", 0, "asset_id"), "different-asset"),
        (("masks", 0, "bucket"), "other-evidence"),
        (("masks", 0, "generation"), "30"),
        (("masks", 0, "object_name"), "arbitrary/key"),
        (("masks", 0, "size_bytes"), 2_000_001),
        (("masks", 0, "score"), float("nan")),
        (("masks", 0, "encoding"), "unreviewed"),
    ],
)
def test_forged_metadata_and_geometry_are_rejected(payload, path, replacement):
    value = legitimate_body(payload["request"], payload["expected"])
    location = value
    for key in path[:-1]:
        location = location[key]
    location[path[-1]] = replacement
    assert validate_sam3_response(value, payload) != "valid"


def test_self_consistent_forged_checkpoint_requires_trusted_pin(payload):
    value = legitimate_body(payload["request"], payload["expected"])
    value["checkpoint_files"]["model.safetensors"] = "0" * 64
    value["checkpoint_sha256"] = canonical_sha256(value["checkpoint_files"])
    assert validate_sam3_response(value, payload) == "checkpoint_binding_mismatch"


@pytest.mark.parametrize(
    "missing", ["manifest_sha256", "source", "output_bucket", "checkpoint_files"]
)
def test_missing_expected_binding_prevents_http(payload, monkeypatch, missing):
    del payload["expected"][missing]

    def unexpected(*args, **kwargs):
        pytest.fail("HTTP must not start without complete admission")

    monkeypatch.setattr(httpx, "Client", unexpected)
    with pytest.raises(ValueError, match="expected binding"):
        sam3_exchange(payload, "fixture")


@pytest.mark.parametrize("forged", [False, True])
def test_transport_retains_full_body_and_never_labels_forgery_valid(
    payload, monkeypatch, forged
):
    value = legitimate_body(payload["request"], payload["expected"])
    if forged:
        value["request_sha256"] = "0" * 64
    raw = json.dumps(value).encode()
    client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, stream=httpx.ByteStream(raw))
            ),
            **kwargs,
        ),
    )
    envelope = json.loads(sam3_exchange(payload, "fixture"))
    assert base64.b64decode(envelope["body_base64"]) == raw
    assert (envelope["validation"] == "valid") is (not forged)
