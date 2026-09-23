"""SAM 3 serving per run and in the lab (docs/execution/golive/LANE.md, T3a)."""

import hashlib
import io
import json
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from specimen_digitization.application.sam3_effect import canonical_sha256
from specimen_digitization.application.sam3_server import (
    LocalObjects,
    RunSegmenter,
    checkpoint_files_digest,
    create_app,
    lab_authenticator,
    serving_mode,
)
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.hub_models import SAM3_MODEL

from test_sam3_server import FixtureEngine, MemoryObjects

TOKEN = "fixture-lab-token-" + "x" * 20


class RunEngine(FixtureEngine):
    """The pilot fixture engine, answering the per-run detect call (LANE.md T3b)."""

    def detect(self, image, prompt, *, threshold, mask_threshold, limit):
        found = [pair for pair in self.predict(image, prompt) if pair[1] >= threshold]
        return found[:limit]


class RunObjects(MemoryObjects):
    """The pilot fixture store plus the per-run source read and mask reference."""

    def application_source(self, request):
        self.reads += 1
        return self.raw

    def put_mask(self, raw):
        stored = super().put_mask(raw)
        return dict(stored, ref=stored["sha256"] + ":" + stored["generation"])


def image_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (4, 4)).save(stream, "PNG")
    return stream.getvalue()


def run_request(raw, run_id="run-a", **changes):
    sha = hashlib.sha256(raw).hexdigest()
    return {
        "run_id": run_id,
        "asset_id": "asset-a",
        "specimen_id": "00000000-0000-4000-8000-00000000000a",
        "organization_id": "00000000-0000-4000-8000-00000000000b",
        "collection_id": "00000000-0000-4000-8000-00000000000c",
        "blob_ref": sha + ":7",
        "sha256": sha,
        "width": 4,
        "height": 4,
        "model_id": SAM3_MODEL.repo_id,
        "model_revision": SAM3_MODEL.revision,
        "prompt": "label",
        "parameters": {},
        "adapter_version": "sam3-http-v1",
        "settings_version": "sam3-settings-v1",
        **changes,
    }


@pytest.fixture
def served():
    raw = image_bytes()
    objects, engine = RunObjects(raw), RunEngine()
    engine.checkpoint_sha256 = canonical_sha256(engine.checkpoint_files)
    clock = SimpleNamespace(now=1000.0)
    segmenter = RunSegmenter(objects, engine, clock=lambda: clock.now)

    def auth(header):
        if header != "Bearer fixture":
            raise ValueError("denied")

    client = TestClient(create_app(segmenter, auth))
    return SimpleNamespace(
        raw=raw, objects=objects, engine=engine, clock=clock, client=client
    )


def post(client, request, bearer="fixture"):
    return client.post(
        "/v1/segment", json=request, headers={"Authorization": "Bearer " + bearer}
    )


def test_any_authenticated_run_is_served_without_a_manifest(served):
    request = run_request(served.raw)
    response = post(served.client, request)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"] == "run-a"
    assert body["request_sha256"] == canonical_sha256(request)
    assert body["source"] == {
        "blob_ref": request["blob_ref"],
        "sha256": request["sha256"],
        "size_bytes": len(served.raw),
    }
    assert [region["id"] for region in body["regions"]] == [
        str(uuid5(NAMESPACE_URL, "sam3-run/run-a/0"))
    ]
    assert body["regions"][0]["mask_ref"] == body["masks"][0]["ref"]
    assert "application/sha256/sam3-runs/run-a/claim-1.json" in served.objects.data
    assert "application/sha256/sam3-runs/run-a/response.json" in served.objects.data


def test_a_repeated_run_returns_its_stored_result_without_inference(served):
    request = run_request(served.raw)
    first = post(served.client, request)
    second = post(served.client, request)
    assert first.json() == second.json()
    assert served.engine.calls == 1


def test_a_different_request_for_the_same_run_is_refused(served):
    assert post(served.client, run_request(served.raw)).status_code == 200
    changed = post(served.client, run_request(served.raw, prompt="labels"))
    assert changed.status_code == 409
    assert changed.json()["detail"] == "sam3_run_request_mismatch"


def test_an_attempt_that_died_is_taken_over_and_a_live_one_is_busy(served):
    request = run_request(served.raw)
    claim = "application/sha256/sam3-runs/run-a/claim-1.json"
    served.objects.data[claim] = json.dumps(
        {"request_sha256": canonical_sha256(request), "claimed_at": 990.0}
    ).encode()
    busy = post(served.client, request)
    assert busy.status_code == 409
    assert busy.json()["detail"] == "sam3_busy"
    assert served.engine.calls == 0
    served.clock.now = 990.0 + 241
    taken = post(served.client, request)
    assert taken.status_code == 200, taken.text
    assert "application/sha256/sam3-runs/run-a/claim-2.json" in served.objects.data
    assert served.engine.calls == 1


@pytest.mark.parametrize("run_id", ["../escape", "a/b", ".hidden", "run a"])
def test_run_ids_that_could_name_a_path_are_refused(served, run_id):
    response = post(served.client, run_request(served.raw, run_id=run_id))
    assert response.status_code == 422
    assert served.engine.calls == 0
    assert not any("escape" in name for name in served.objects.data)


def test_source_bytes_must_match_the_requested_digest(served):
    served.objects.raw = image_bytes() + b"tampered"
    response = post(served.client, run_request(image_bytes()))
    assert response.status_code == 409
    assert response.json()["detail"] == "source_integrity_mismatch"
    assert served.engine.calls == 0


def test_lab_objects_use_the_application_local_blob_layout(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    raw = image_bytes()
    ref = blobs.put(raw)
    objects = LocalObjects(tmp_path / "blobs")
    request = SimpleNamespace(blob_ref=ref, sha256=ref)
    assert objects.application_source(request) == raw
    mask = b"fixture mask"
    stored = objects.put_mask(mask)
    assert stored["ref"] == hashlib.sha256(mask).hexdigest()
    assert blobs.get(stored["ref"]) == mask
    assert objects.create("sam3-runs/run-a/claim-1.json", b"{}") is not None
    assert objects.create("sam3-runs/run-a/claim-1.json", b"{}") is None
    assert objects.read("sam3-runs/run-a/claim-1.json") == b"{}"
    assert objects.read("sam3-runs/run-a/response.json") is None


def test_lab_mode_serves_a_run_end_to_end_over_local_blobs(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    raw = image_bytes()
    ref = blobs.put(raw)
    engine = RunEngine()
    engine.checkpoint_sha256 = canonical_sha256(engine.checkpoint_files)
    segmenter = RunSegmenter(LocalObjects(tmp_path / "blobs"), engine)
    client = TestClient(create_app(segmenter, lab_authenticator(TOKEN)))
    request = run_request(raw, blob_ref=ref)
    assert post(client, request, bearer="wrong-token").status_code == 403
    response = post(client, request, bearer=TOKEN)
    assert response.status_code == 200, response.text
    mask_ref = response.json()["regions"][0]["mask_ref"]
    assert blobs.get(mask_ref)


@pytest.mark.parametrize("token", ["", "short"])
def test_lab_secrets_must_be_long(token):
    with pytest.raises(ValueError):
        lab_authenticator(token)


@pytest.mark.parametrize(
    ("env", "mode"),
    [
        ({"SPECIMEN_SAM3_ENABLE": "authorized-run", "K_SERVICE": "specimen-sam"}, "authorized-run"),
        ({"SPECIMEN_SAM3_ENABLE": "authorized-pilot", "K_SERVICE": "specimen-sam"}, "authorized-pilot"),
        ({"SPECIMEN_SAM3_ENABLE": "lab", "APP_ENV": "lab"}, "lab"),
    ],
)
def test_serving_modes(env, mode):
    assert serving_mode(env) == mode


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"SPECIMEN_SAM3_ENABLE": "authorized-run"},
        {"SPECIMEN_SAM3_ENABLE": "lab", "K_SERVICE": "specimen-sam"},
        {"SPECIMEN_SAM3_ENABLE": "lab", "APP_ENV": "production"},
        {"SPECIMEN_SAM3_ENABLE": "anything", "K_SERVICE": "specimen-sam"},
    ],
)
def test_serving_mode_refusals(env):
    with pytest.raises(RuntimeError):
        serving_mode(env)


def test_the_checkpoint_digest_is_the_digest_of_its_file_digests(tmp_path):
    (tmp_path / "model.safetensors").write_bytes(b"weights")
    (tmp_path / "config.json").write_bytes(b"{}")
    (tmp_path / "ignored.bin").write_bytes(b"not an artifact")
    files, value = checkpoint_files_digest(tmp_path)
    assert files == {
        "config.json": hashlib.sha256(b"{}").hexdigest(),
        "model.safetensors": hashlib.sha256(b"weights").hexdigest(),
    }
    assert value == canonical_sha256(files)
