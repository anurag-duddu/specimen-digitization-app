"""Offline tests for workflow-only publication of pinned georeferencing assets."""
from __future__ import annotations

import hashlib
from dataclasses import replace
import os
from pathlib import Path
import sys

import pytest

# This branch does not yet carry the georeferencing manifest. In an integrated
# checkout it is imported locally; for this bounded worktree test, read the
# owning Geo branch's committed manifest without changing that worktree.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
GEO_SOURCE = os.environ.get("GEOGRAPHIC_MANIFEST_SRC")
if not (ROOT / "src/specimen_digitization/application/georef_datasets.py").is_file() and GEO_SOURCE:
    if not (Path(GEO_SOURCE) / "specimen_digitization/application/georef_datasets.py").is_file():
        raise RuntimeError("GEOGRAPHIC_MANIFEST_SRC must point to the manifest source root")
    sys.path.insert(0, GEO_SOURCE)

from specimen_digitization.application.georef_datasets import Dataset, MANIFEST
from scripts.release import georef_datasets as release


class Response:
    def __init__(self, payload: bytes, *, status: int = 200, chunk_size: int = 11):
        self.payload = payload
        self.status_code = status
        self.chunk_size = chunk_size
        self.headers = {"Content-Length": str(len(payload))}
        self.closed = False
        self.chunks_yielded = 0

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int):
        assert chunk_size == release.CHUNK_SIZE
        for start in range(0, len(self.payload), self.chunk_size):
            self.chunks_yielded += 1
            yield self.payload[start : start + self.chunk_size]

    def close(self):
        self.closed = True


class FakeHttp:
    def __init__(self, payloads: dict[str, bytes]):
        self.payloads = payloads
        self.urls: list[str] = []
        self.responses: list[Response] = []

    def get(self, url: str, **kwargs):
        assert kwargs == {"stream": True, "timeout": release.HTTP_TIMEOUT}
        self.urls.append(url)
        response = Response(self.payloads[url])
        self.responses.append(response)
        return response


class FakeStorage:
    """Models create-only writes and lets tests seed pre-existing objects."""

    def __init__(self, objects: dict[str, bytes] | None = None):
        self.objects = dict(objects or {})
        self.reads: list[str] = []
        self.creates: list[tuple[str, str, bytes]] = []

    def read_object(self, name: str, expected_size: int) -> bytes | None:
        self.reads.append(name)
        return self.objects.get(name)

    def create_if_absent(self, name: str, content_type: str, data: bytes) -> bool:
        self.creates.append((name, content_type, data))
        if name in self.objects:
            return False
        self.objects[name] = data
        return True


def tiny_manifest() -> tuple[tuple[Dataset, ...], dict[str, bytes]]:
    payloads: dict[str, bytes] = {}
    entries = []
    for index, entry in enumerate(MANIFEST):
        data = f"synthetic dataset {index}".encode()
        digest = hashlib.sha256(data).hexdigest()
        pinned = replace(entry, size=len(data), sha256=digest)
        entries.append(pinned)
        payloads[release.asset_url(pinned)] = data
    return tuple(entries), payloads


def test_publish_fetches_and_create_only_stores_the_ten_reviewed_bytes():
    manifest, payloads = tiny_manifest()
    http, storage, emitted = FakeHttp(payloads), FakeStorage(), []

    release.publish(http, storage, manifest, emitted.append)

    assert len(manifest) == len(http.urls) == len(storage.creates) == 10
    assert all(url.startswith(release.ASSET_ROOT + "/") and url.endswith(".bin") for url in http.urls)
    assert set(storage.objects) == {entry.object_name for entry in manifest}
    for entry in manifest:
        expected = payloads[release.asset_url(entry)]
        assert storage.objects[entry.object_name] == expected
        assert hashlib.sha256(storage.objects[entry.object_name]).hexdigest() == entry.sha256
    assert all(response.closed for response in http.responses)
    assert len(emitted) == 10


def test_existing_exact_object_is_verified_and_never_written_again():
    manifest, payloads = tiny_manifest()
    storage = FakeStorage(
        {entry.object_name: payloads[release.asset_url(entry)] for entry in manifest}
    )

    release.publish(FakeHttp(payloads), storage, manifest, lambda _: None)

    assert storage.creates == []
    assert len(storage.reads) == 10


def test_bad_release_asset_digest_fails_before_any_storage_read_or_write():
    manifest, payloads = tiny_manifest()
    first = manifest[0]
    payloads[release.asset_url(first)] += b" altered"
    storage = FakeStorage()
    http = FakeHttp(payloads)
    original_get = http.get

    def response_with_manifest_length(url: str, **kwargs):
        response = original_get(url, **kwargs)
        response.headers["Content-Length"] = str(manifest[0].size)
        return response

    http.get = response_with_manifest_length
    with pytest.raises(release.PublicationFailure, match="does not match its manifest"):
        release.publish(http, storage, manifest, lambda _: None)

    assert storage.reads == []
    assert storage.creates == []


@pytest.mark.parametrize("existing", [b"partial bytes", b"x" * 20])
def test_partial_or_wrong_existing_object_is_refused_without_overwrite(existing: bytes):
    manifest, payloads = tiny_manifest()
    first = manifest[0]
    storage = FakeStorage({first.object_name: existing})

    with pytest.raises(release.PublicationFailure, match="existing object .* does not match"):
        release.publish(FakeHttp(payloads), storage, manifest, lambda _: None)

    assert storage.objects[first.object_name] == existing
    assert storage.creates == []


def test_download_is_bounded_to_expected_size_plus_one():
    entry = replace(MANIFEST[0], size=8)
    response = Response(b"x" * 10_000, chunk_size=10_000)
    response.headers = {}
    class Http:
        def get(self, url, **kwargs):
            return response

    with pytest.raises(release.PublicationFailure, match="does not match its manifest"):
        release.download_dataset(Http(), entry)

    assert response.chunks_yielded == 1
    assert response.closed


@pytest.mark.parametrize(
    "changes",
    [
        {"GITHUB_ACTIONS": "false"},
        {"GITHUB_REF": "refs/heads/feature"},
        {"GITHUB_WORKFLOW": "Runtime release"},
        {"GITHUB_SHA": "b" * 40},
        {"GITHUB_SHA": "not-a-commit"},
    ],
)
def test_workflow_guard_rejects_any_non_data_main_identity(changes: dict[str, str]):
    env = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW": "Data release",
        "GITHUB_SHA": "a" * 40,
        **changes,
    }

    with pytest.raises(release.PublicationFailure):
        release.require_data_release(env, "a" * 40)


def test_workflow_guard_accepts_only_matching_data_release_main_sha():
    env = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_WORKFLOW": "Data release",
        "GITHUB_SHA": "a" * 40,
    }
    release.require_data_release(env, "a" * 40)
    with pytest.raises(release.PublicationFailure, match="checked-out commit"):
        release.require_data_release(env, "b" * 40)


def test_gcs_existing_object_checks_metadata_and_reads_bounded_exact_bytes():
    class GcsResponse(Response):
        def __init__(self, payload: bytes, *, metadata_size: int | None = None):
            super().__init__(payload)
            self.metadata_size = metadata_size

        def json(self):
            return {"size": self.metadata_size}

    class Session:
        def __init__(self, responses):
            self.responses = iter(responses)
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return next(self.responses)

    payload = b"verified"
    metadata = GcsResponse(b"", metadata_size=len(payload))
    body = GcsResponse(payload)
    session = Session([metadata, body])
    storage = release.GoogleStorage(session)

    assert storage.read_object("application/sha256/test", len(payload)) == payload
    assert session.calls[1][1]["headers"] == {"Range": f"bytes=0-{len(payload)}"}
    assert session.calls[1][1]["stream"] is True
    assert body.closed


def test_gcs_existing_object_with_wrong_metadata_size_is_rejected_before_download():
    class MetadataResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"size": 3}

    class Session:
        def __init__(self):
            self.calls = 0

        def get(self, url, **kwargs):
            self.calls += 1
            return MetadataResponse()

    session = Session()
    with pytest.raises(release.PublicationFailure, match="expected 8"):
        release.GoogleStorage(session).read_object("application/sha256/test", 8)
    assert session.calls == 1


def test_gcs_create_request_uses_generation_zero_precondition():
    class Session:
        def __init__(self):
            self.call = None

        def post(self, url, **kwargs):
            self.call = (url, kwargs)
            return Response(b"{}")

    session = Session()
    storage = release.GoogleStorage(session)
    created = storage.create_if_absent("application/sha256/test", "application/zip", b"verified")

    assert created is True
    url, kwargs = session.call
    assert url == f"{release.GCS_ROOT}/upload/storage/v1/b/{release.BUCKET}/o"
    assert kwargs["params"] == {
        "uploadType": "media",
        "name": "application/sha256/test",
        "ifGenerationMatch": "0",
    }
    assert kwargs["data"] == b"verified"


def test_data_release_workflow_calls_publisher_without_an_additional_secret():
    workflow = (ROOT / ".github/workflows/data-release.yml").read_text()
    release_step = "run: uv run python scripts/release/data_release.py"
    publisher_step = (
        "- name: Publish the ten pinned georeferencing datasets\n"
        "        run: uv run python scripts/release/georef_datasets.py"
    )
    assert "permissions:\n  contents: read" in workflow
    assert workflow.index(release_step) < workflow.index(publisher_step)
    section = workflow[workflow.index(publisher_step) :]
    assert "${{ secrets." not in section
