"""CPU contract fixtures only: no SAM checkpoint/inference/cloud calls."""

import hashlib
import io
import json
from uuid import UUID

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from specimen_digitization.application.sam3_server import (
    PilotManifest,
    SegmentRequest,
    Segmenter,
    create_app,
    read_manifest,
)
from specimen_digitization.hub_models import SAM3_MODEL


class MemoryObjects:
    def __init__(self, raw):
        self.raw, self.data, self.reads = raw, {}, 0

    def source(self, source):
        self.reads += 1
        return self.raw

    def create(self, name, raw):
        if name in self.data:
            return None
        self.data[name] = raw
        return {
            "bucket": "test-output",
            "object_name": name,
            "generation": "1",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }

    def put_mask(self, raw):
        name = "application/sha256/" + hashlib.sha256(raw).hexdigest()
        result = self.create(name, raw)
        if result is not None:
            return result
        assert self.data[name] == raw
        return {
            "bucket": "test-output",
            "object_name": name,
            "generation": "1",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        }

    def read(self, name):
        return self.data.get(name)


class FixtureEngine:
    checkpoint_files = {"fixture-not-real.safetensors": "e" * 64}
    checkpoint_sha256 = "e" * 64

    def __init__(self):
        self.calls = 0
        self.invalid = None

    def predict(self, image, prompt):
        self.calls += 1
        if self.invalid == "failure":
            raise RuntimeError("private error")
        if self.invalid == "empty":
            return []
        mask = Image.new("L", image.size)
        mask.paste(255, (1, 1, 3, 3))
        if self.invalid == "dimensions":
            mask = Image.new("L", (1, 1), 255)
        if self.invalid == "nonbinary":
            mask.putpixel((0, 0), 42)
        return [(mask, float("nan") if self.invalid == "score" else 0.8)]


@pytest.fixture
def setup():
    stream = io.BytesIO()
    Image.new("RGB", (4, 4)).save(stream, "PNG")
    raw = stream.getvalue()
    sha = hashlib.sha256(raw).hexdigest()
    specimens = []
    for index in range(1, 11):
        specimens.append(
            {
                "ordinal": index,
                "specimen_id": str(UUID(int=index)),
                "organization_id": str(UUID(int=100)),
                "collection_id": str(UUID(int=101)),
                "source_objects": [
                    {
                        "bucket": "authorized-source",
                        "object_name": str(index),
                        "generation": str(index),
                        "sha256": sha,
                        "size_bytes": len(raw),
                    }
                ],
                "application_source": {
                    "blob_ref": f"{sha}:{index}",
                    "sha256": sha,
                    "size_bytes": len(raw),
                    "source_object_index": 0,
                },
            }
        )
    manifest = PilotManifest.model_validate(
        {
            "schema_version": "specimen-pilot/v1",
            "status": "ready",
            "project_id": "specimen-digitization",
            "authorization_reference": "fixture-only",
            "selection": {
                "order": "explicit_source_order",
                "source_inventory_sha256": "a" * 64,
            },
            "specimens": specimens,
        }
    )
    request = {
        "run_id": "fixture-run",
        "asset_id": "fixture-asset",
        "specimen_id": str(UUID(int=1)),
        "organization_id": str(UUID(int=100)),
        "collection_id": str(UUID(int=101)),
        "blob_ref": f"{sha}:1",
        "sha256": sha,
        "width": 4,
        "height": 4,
        "model_id": SAM3_MODEL.repo_id,
        "model_revision": SAM3_MODEL.revision,
        "prompt": "label",
        "parameters": {},
        "adapter_version": "sam3-http-v1",
        "settings_version": "sam3-settings-v1",
    }
    objects, engine = MemoryObjects(raw), FixtureEngine()
    service = Segmenter(manifest, "a" * 64, objects, engine, 1000, clock=lambda: 0)

    def auth(header):
        if header != "Bearer fixture":
            raise ValueError("denied")

    client = TestClient(create_app(service, auth))
    return service, client, request, objects, engine


def post(client, request):
    return client.post(
        "/v1/segment", json=request, headers={"Authorization": "Bearer fixture"}
    )


def test_mask_provenance_and_restart_reuses_retained_result(setup):
    service, client, request, objects, engine = setup
    response = post(client, request)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["regions"][0]["x"] == 1
    assert result["regions"][0]["width"] == 2
    mask = result["masks"][0]
    assert result["regions"][0]["mask_ref"] == mask["sha256"] + ":1"
    assert mask["object_name"] == "application/sha256/" + mask["sha256"]
    assert (
        hashlib.sha256(objects.data[mask["object_name"]]).hexdigest() == mask["sha256"]
    )
    restarted = Segmenter(
        service.manifest,
        service.manifest_sha256,
        objects,
        engine,
        1000,
        clock=lambda: 0,
    )
    assert restarted.segment(SegmentRequest.model_validate(request)) == result
    assert engine.calls == objects.reads == 1
    request["run_id"] = "new-run"
    assert post(client, request).status_code == 409
    assert engine.calls == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("blob_ref", "b" * 64 + ":1"),
        ("sha256", "b" * 64),
        ("specimen_id", str(UUID(int=11))),
        ("collection_id", str(UUID(int=102))),
    ],
)
def test_allowlist_denials_precede_storage_and_model(setup, field, value):
    _, client, request, objects, engine = setup
    request[field] = value
    assert post(client, request).status_code == 403
    assert not objects.data and engine.calls == objects.reads == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_revision", "main"),
        ("width", 20001),
        ("parameters", {"threshold": 0}),
        ("height", True),
    ],
)
def test_invalid_request_is_bounded_and_redacted(setup, field, value):
    _, client, request, objects, engine = setup
    request[field] = value
    response = post(client, request)
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_segmentation_request"}
    assert not objects.data and not engine.calls


@pytest.mark.parametrize(
    "invalid", ["failure", "empty", "dimensions", "nonbinary", "score"]
)
def test_invalid_output_and_unknown_effect_never_replay(setup, invalid):
    _, client, request, _, engine = setup
    engine.invalid = invalid
    assert post(client, request).status_code in (422, 503)
    assert post(client, request).status_code == 409
    assert engine.calls == 1


def test_source_hash_and_dimensions_checked_before_model(setup):
    _, client, request, objects, engine = setup
    objects.raw += b"changed"
    assert post(client, request).status_code == 409
    assert engine.calls == 0


def test_auth_request_size_and_expiry(setup):
    service, client, request, objects, engine = setup
    assert client.post("/v1/segment", json=request).status_code == 403
    assert (
        client.post(
            "/v1/segment",
            content=b"x" * 16385,
            headers={"Authorization": "Bearer fixture"},
        ).status_code
        == 413
    )
    service.expires_at = 120
    assert post(client, request).status_code == 403
    assert not objects.data and not engine.calls


def test_manifest_requires_exact_ten_ready_bound_hash(setup, tmp_path):
    service, _, _, _, _ = setup
    value = service.manifest.model_dump()
    path = tmp_path / "manifest.json"
    raw = json.dumps(value).encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    assert len(read_manifest(path, hashlib.sha256(raw).hexdigest()).specimens) == 10
    with pytest.raises(ValueError):
        read_manifest(path, "0" * 64)
    for bad in [
        dict(value, status="metadata_frozen"),
        dict(value, specimens=value["specimens"][:9]),
    ]:
        with pytest.raises(ValueError):
            PilotManifest.model_validate(bad)


def test_pending_claim_blocks_independent_server_instance(setup):
    service, _, request, objects, engine = setup
    prefix = f"sam3/{service.manifest_sha256}/{request['specimen_id']}"
    objects.create(prefix + "/claim.json", b"{}")
    restarted = Segmenter(
        service.manifest,
        service.manifest_sha256,
        objects,
        engine,
        1000,
        clock=lambda: 0,
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as failure:
        restarted.segment(SegmentRequest.model_validate(request))
    assert failure.value.status_code == 409
    assert engine.calls == objects.reads == 0


def test_busy_refuses_before_claim(setup):
    service, client, request, objects, engine = setup
    with service.lock:
        assert post(client, request).status_code == 429
    assert not objects.data and not engine.calls


@pytest.mark.parametrize("offline", [False, True])
def test_engine_pins_checkpoint_and_uses_only_local_model_files(
    monkeypatch, tmp_path, offline
):
    import sys
    from types import SimpleNamespace
    from specimen_digitization.application.sam3_server import Sam3Engine

    calls = {}
    (tmp_path / "model.safetensors").write_bytes(b"fixture-not-model-weights")

    def download(**kwargs):
        calls["download"] = kwargs
        return str(tmp_path)

    class Model:
        @classmethod
        def from_pretrained(cls, path, **kwargs):
            calls["model"] = kwargs
            return cls()

        def eval(self):
            return self

    class Processor:
        @classmethod
        def from_pretrained(cls, path, **kwargs):
            calls["processor"] = kwargs
            return cls()

    monkeypatch.setenv("HF_TOKEN", "fixture-only")
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(set_num_threads=lambda _: None)
    )
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(
            snapshot_download=download,
            constants=SimpleNamespace(HF_HUB_OFFLINE=offline),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(Sam3Model=Model, Sam3Processor=Processor),
    )
    engine = Sam3Engine()
    assert calls["download"]["revision"] == SAM3_MODEL.revision
    assert calls["download"]["repo_id"] == "facebook/sam3"
    assert calls["download"]["local_files_only"] is offline
    for key in ("model", "processor"):
        assert calls[key] == {"local_files_only": True, "trust_remote_code": False}
    assert (
        engine.checkpoint_files["model.safetensors"]
        == hashlib.sha256(b"fixture-not-model-weights").hexdigest()
    )


def test_manifest_rejects_symlink_fifo_and_public_permissions(tmp_path):
    import os

    path = tmp_path / "private.json"
    path.write_text("{}")
    path.chmod(0o644)
    with pytest.raises(ValueError, match="private regular file"):
        read_manifest(path, "a" * 64)
    path.chmod(0o600)
    alias = tmp_path / "alias"
    alias.symlink_to(path)
    with pytest.raises(OSError):
        read_manifest(alias, "a" * 64)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo, mode=0o600)
    with pytest.raises(ValueError, match="private regular file"):
        read_manifest(fifo, "a" * 64)


def test_canonical_mask_reference_is_readable_by_worker_gcs_adapter(setup):
    from types import SimpleNamespace
    from specimen_digitization.application.production import GcsBlobs

    _, client, request, objects, _ = setup
    result = post(client, request).json()
    mask = result["masks"][0]
    raw = objects.data[mask["object_name"]]

    class Response:
        status_code, headers = 200, {}

        def __enter__(self):
            self.raw = SimpleNamespace(read=lambda count, **kwargs: stream.read(count))
            return self

        def __exit__(self, *args):
            pass

    stream = io.BytesIO(raw)

    def get(url, **kwargs):
        assert kwargs["params"]["generation"] == "1"
        assert mask["sha256"] in url
        return Response()

    adapter = GcsBlobs.__new__(GcsBlobs)
    adapter.bucket = SimpleNamespace(
        name="test-output", client=SimpleNamespace(_http=SimpleNamespace(get=get))
    )
    assert adapter.get(result["regions"][0]["mask_ref"]) == raw


@pytest.mark.parametrize("existing", [b"mask", b"fake"])
def test_mask_content_address_collision_is_verified(monkeypatch, existing):
    from types import SimpleNamespace
    from specimen_digitization.application.sam3_server import GCSObjects

    blob = SimpleNamespace(size=4, generation=55, reload=lambda **kwargs: None)
    client = SimpleNamespace(bucket=lambda name: SimpleNamespace(blob=lambda key: blob))
    store = GCSObjects(client, "test-output")
    monkeypatch.setattr(store, "create", lambda name, raw: None)
    monkeypatch.setattr(store, "_media", lambda *args: existing)
    if existing == b"mask":
        result = store.put_mask(b"mask")
        assert result["generation"] == "55"
        assert (
            result["object_name"]
            == "application/sha256/" + hashlib.sha256(existing).hexdigest()
        )
    else:
        with pytest.raises(ValueError, match="immutable_mask_mismatch"):
            store.put_mask(b"mask")


def test_actual_server_response_passes_client_binding_validator(setup):
    from specimen_digitization.application.sam3_effect import (
        canonical_sha256,
        validate_sam3_response,
    )

    service, client, request, _, engine = setup
    engine.checkpoint_sha256 = canonical_sha256(engine.checkpoint_files)
    response = post(client, request)
    assert response.status_code == 200
    expected = {
        "manifest_sha256": service.manifest_sha256,
        "source": service.manifest.specimens[0].source_objects[0].model_dump(),
        "output_bucket": "test-output",
        "checkpoint_files": engine.checkpoint_files,
    }
    assert (
        validate_sam3_response(
            response.json(), {"request": request, "expected": expected}
        )
        == "valid"
    )
