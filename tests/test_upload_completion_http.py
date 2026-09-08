"""Upload completion replay and malformed-image behavior over real TCP."""

import hashlib
import io
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time

import httpx
from PIL import Image
import pytest

from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG

PREFIX = f"/v1/organizations/{SYNTHETIC_ORG}"


@pytest.fixture
def tcp_client(tmp_path):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    token = secrets.token_urlsafe(32)
    process = subprocess.Popen(
        [
            str(Path(".venv/bin/specimen-api").resolve()),
            "--mode",
            "synthetic",
            "--state-dir",
            str(tmp_path),
            "--port",
            str(port),
        ],
        env=dict(os.environ, SPECIMEN_SYNTHETIC_TOKEN=token),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            headers={
                "Authorization": "Bearer " + token,
                "Idempotency-Key": "completion-test",
            },
            timeout=30,
        ) as client:
            for _ in range(100):
                try:
                    if client.get("/v1/session").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("API did not start")
            yield client
    finally:
        process.terminate()
        process.wait(timeout=10)


def upload(client, truncated=False):
    output = io.BytesIO()
    Image.new("RGB", (120, 80), "white").save(output, format="PNG")
    data = output.getvalue()[:60] if truncated else output.getvalue()
    batch = client.post(
        PREFIX + "/batches",
        json={
            "collection_id": SYNTHETIC_COLLECTION,
            "display_name": "Synthetic TCP",
        },
    ).json()
    item = client.post(
        PREFIX + f"/batches/{batch['batch_id']}/items",
        json={
            "client_item_id": "one",
            "filename": "synthetic.png",
            "media_type": "image/png",
            "size_bytes": len(data),
            "width": 120,
            "height": 80,
            "sha256": hashlib.sha256(data).hexdigest(),
        },
    )
    assert item.status_code == 200, item.text
    document = item.json()
    path = PREFIX + f"/uploads/{document['upload_id']}"
    chunk = client.put(path + "/content", content=data)
    assert chunk.status_code == 200, chunk.text
    return (
        path,
        document,
        {
            "expected_revision": chunk.json()["revision"],
            "reason": "Synthetic completion",
        },
    )


def test_completion_retains_original_response_and_rejects_changed_request(tcp_client):
    client = tcp_client
    path, document, body = upload(client)
    original = client.post(path + "/complete", json=body)
    assert original.status_code == 200, original.text
    # Background processing changes the specimen, never the completion receipt.
    for _ in range(100):
        current = client.get(PREFIX + f"/specimens/{document['specimen_id']}/workspace")
        if current.json()["revision"] > original.json()["revision"]:
            break
        time.sleep(0.05)
    assert current.json()["revision"] > original.json()["revision"]
    assert client.post(path + "/complete", json=body).json() == original.json()
    assert (
        client.post(path + "/complete", json=dict(body, reason="Changed")).status_code
        == 409
    )
    assert (
        client.post(
            path + "/complete", json=body, headers={"Idempotency-Key": "different"}
        ).status_code
        == 409
    )
    assert client.post(path + "/complete", json=body).json() == original.json()


def test_truncated_image_is_stable_input_error_on_same_connection(tcp_client):
    client = tcp_client
    path, document, body = upload(client, truncated=True)
    for _ in range(2):
        response = client.post(path + "/complete", json=body)
        assert response.status_code == 422, response.text
        assert client.get("/v1/session").status_code == 200
        assert (
            client.get(
                PREFIX + f"/specimens/{document['specimen_id']}/workspace"
            ).status_code
            == 404
        )
        assert client.get(path).json()["state"] == "uploading"
