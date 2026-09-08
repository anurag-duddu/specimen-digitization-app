"""Optional real codecs through upload, worker, retained pixels and restart."""

import hashlib
import io
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_application import HEADERS, PREFIX, TOKEN, SYNTHETIC_COLLECTION
from test_image_codecs import heic, dng
from specimen_digitization.application.api import create_app, SYNTHETIC_TEXT
from specimen_digitization.application.image_codecs import CodecPolicy
from specimen_digitization.application.collection_runtime import application_registry
from specimen_digitization.application.storage import SQLiteRepository, LocalBlobs
from specimen_digitization.application.workflow import SyntheticAdapters, crop_bytes
from specimen_digitization.application.domain import Scope


def codec_app(root, enable=True):
    registry = application_registry(True)
    registry = registry.model_copy(
        update={
            "profiles": tuple(
                profile.model_copy(
                    update={
                        "allowed_input_formats": ("JPEG", "PNG", "TIFF", "HEIC", "DNG")
                    }
                )
                for profile in registry.profiles
            )
        }
    )
    blobs = LocalBlobs(root / "blobs")
    repo = SQLiteRepository(root / "state.db")
    return create_app(
        mode="synthetic",
        repository=repo,
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        token=TOKEN,
        profile_registry=registry,
        codec_policy=CodecPolicy(
            enable_heic=enable,
            approved_raw_families=("DNG",) if enable else (),
            require_memory_limit=False,
        ),
    )


def upload_codec(http, data, media, **dimensions):
    batch = http.post(
        PREFIX + "/batches",
        headers={**HEADERS, "Idempotency-Key": str(uuid4())},
        json={"collection_id": SYNTHETIC_COLLECTION, "display_name": "Synthetic codec"},
    ).json()
    response = http.post(
        PREFIX + "/batches/" + batch["batch_id"] + "/items",
        headers={**HEADERS, "Idempotency-Key": str(uuid4())},
        json={
            "client_item_id": str(uuid4()),
            "filename": "synthetic-codec",
            "media_type": media,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            **dimensions,
        },
    )
    assert response.status_code == 200, response.text
    item = response.json()
    chunk = http.put(item["upload_url"], headers=HEADERS, content=data).json()
    return http.post(
        PREFIX + "/uploads/" + item["upload_id"] + "/complete",
        headers={**HEADERS, "Idempotency-Key": str(uuid4())},
        json={"expected_revision": chunk["revision"]},
    )


@pytest.mark.parametrize("family", ["HEIC", "DNG"])
@pytest.mark.parametrize("orientation", [1, 3, 6, 8])
def test_real_optional_codec_intake_worker_crop_and_restart(
    tmp_path, family, orientation
):
    data = heic(orientation) if family == "HEIC" else dng(orientation)
    if family == "DNG":
        pytest.importorskip("rawpy")
    app = codec_app(tmp_path)
    with TestClient(app) as http:
        response = upload_codec(
            http, data, "image/heic" if family == "HEIC" else "image/dng"
        )
        assert response.status_code == 200, response.text
        row = response.json()
        path = PREFIX + "/specimens/" + row["specimen_id"]
        work = http.get(path + "/workspace", headers=HEADERS).json()
        assert work["disposition"] == "needs_human_review", work["blocker"]
        assert work["asset"]["sha256"] == hashlib.sha256(data).hexdigest()
        assert work["asset"]["pixel_basis"] == (
            "decoded_heif_primary_pixel_edges"
            if family == "HEIC"
            else "raw_active_area_pixel_edges"
        )
        access_path = PREFIX + "/assets/" + work["asset"]["id"] + "/access"
        access = http.get(access_path, headers=HEADERS).json()
        assert http.get(access["url"], headers=HEADERS).content == data
        view = http.get(access["view_url"], headers=HEADERS).content
        assert (
            hashlib.sha256(view).hexdigest()
            == work["asset"]["view_derivative"]["derivative_sha256"]
        )
        scope = Scope(
            organization_id=row["organization_id"], collection_id=row["collection_id"]
        )
        specimen = app.state.workflow.repository.get(scope, row["specimen_id"])
        pixels = crop_bytes(app.state.workflow.blobs, specimen, specimen.run.regions[0])
        assert Image.open(io.BytesIO(pixels)).size == (
            specimen.asset.width,
            specimen.asset.height,
        )
    restarted = codec_app(tmp_path)
    with TestClient(restarted) as http:
        restored = http.get(path + "/workspace", headers=HEADERS).json()
        assert restored["asset"] == work["asset"]
        approved = http.post(
            path + "/decisions",
            headers=HEADERS,
            json={
                "kind": "approve",
                "reason": "Synthetic codec evidence inspected",
                "expected_revision": restored["revision"],
                "base_record_version_id": restored["record_version_id"],
            },
        )
        assert (
            approved.status_code == 200 and approved.json()["disposition"] == "cleared"
        ), approved.text


def test_disabled_codec_retains_upload_without_specimen(tmp_path):
    app = codec_app(tmp_path, False)
    with TestClient(app) as http:
        result = upload_codec(http, b"fake heic", "image/heic")
        assert (
            result.status_code == 503
            and result.json()["error"]["message"] == "image_codec_codec_disabled"
        )
        with app.state.workflow.repository.connect() as db:
            assert db.execute("SELECT count(*) FROM records").fetchone()[0] == 0
