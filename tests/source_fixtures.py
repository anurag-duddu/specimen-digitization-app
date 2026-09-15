"""Shared local-source fixtures: a registered source over a temporary prefix.

These build a synthetic application whose sources are configuration, exactly as
production supplies them. No test registers a source through the API, because
no such endpoint exists.
"""

import io
import os
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    local_app,
)
from specimen_digitization.application.source_reader import LocalSourceReader
from specimen_digitization.application.source_registry import (
    RegisteredSource,
    SourceRegistry,
)

TOKEN = "test-only-local-token"
PREFIX = f"/v1/organizations/{SYNTHETIC_ORG}"
HEADERS = {"Authorization": "Bearer " + TOKEN, "Idempotency-Key": "source-test"}
BUCKET = "specimen-digitization.firebasestorage.app"
SOURCE_ID = "00000000-0000-4000-8000-0000000000f1"
OBJECT_PREFIX = "microscopic-slides/"

# One minute apart, so the two generations differ on any filesystem resolution.
FIRST_GENERATION = 1726300000_000000000
SECOND_GENERATION = 1726300060_000000000


def jpeg_bytes(colour="white", size=(120, 80)):
    output = io.BytesIO()
    Image.new("RGB", size, colour).save(output, format="JPEG", quality=95)
    return output.getvalue()


def png_bytes(colour="white", size=(120, 80)):
    output = io.BytesIO()
    Image.new("RGB", size, colour).save(output, format="PNG")
    return output.getvalue()


def write_object(objects: Path, name: str, data: bytes, generation: int) -> str:
    """Place one object under the local bucket root at an exact generation."""
    path = objects / BUCKET / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, ns=(generation, generation))
    return str(os.stat(path).st_mtime_ns)


def registered(**overrides) -> RegisteredSource:
    return RegisteredSource(
        **{
            "source_id": SOURCE_ID,
            "collection_id": SYNTHETIC_COLLECTION,
            "bucket": BUCKET,
            "prefix": OBJECT_PREFIX,
            "media_types": ("image/jpeg",),
            "registered_by": "fixture-administrator",
            "registered_at": "2026-09-14T00:00:00+00:00",
            **overrides,
        }
    )


class CountingReader:
    """Wraps a reader so a test can see exactly which objects were read."""

    def __init__(self, inner):
        self.inner = inner
        self.reads = []

    def list_objects(self, bucket, prefix, limit):
        return self.inner.list_objects(bucket, prefix, limit)

    def current_generation(self, bucket, object_name):
        return self.inner.current_generation(bucket, object_name)

    def read(self, bucket, object_name, generation):
        self.reads.append(object_name)
        return self.inner.read(bucket, object_name, generation)


def source_client(root: Path, objects: Path, sources=None, reader=None) -> TestClient:
    app = local_app(
        root / "state",
        TOKEN,
        source_registry=SourceRegistry(
            [registered()] if sources is None else sources
        ),
        source_reader=reader or LocalSourceReader(objects),
    )
    return TestClient(app, raise_server_exceptions=False)


def capture(client, source_id=SOURCE_ID):
    response = client.post(
        PREFIX + f"/sources/{source_id}/inventory", headers=HEADERS
    )
    assert response.status_code == 200, response.text
    return response.json()


def listed(client, source_id=SOURCE_ID, **params):
    response = client.get(
        PREFIX + f"/sources/{source_id}/objects", headers=HEADERS, params=params
    )
    assert response.status_code == 200, response.text
    return response.json()


def open_batch(client, display_name="Source intake", **fields):
    response = client.post(
        PREFIX + "/batches",
        # Each batch is a distinct request, so it carries a distinct key.
        headers=dict(HEADERS, **{"Idempotency-Key": "batch:" + display_name}),
        json={
            "collection_id": SYNTHETIC_COLLECTION,
            "display_name": display_name,
            **fields,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["batch_id"]


def import_objects(client, batch_id, rows, source_id=SOURCE_ID, **fields):
    return client.post(
        PREFIX + f"/batches/{batch_id}/items:from-source",
        headers=HEADERS,
        json={
            "source_id": source_id,
            "objects": [
                {"object_name": r["object_name"], "generation": r["generation"]}
                for r in rows
            ],
            **fields,
        },
    )


def queued(client):
    response = client.get(
        PREFIX + "/specimens",
        headers=HEADERS,
        params={"collection_id": SYNTHETIC_COLLECTION},
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]
