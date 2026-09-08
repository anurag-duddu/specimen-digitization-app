"""Opt-in real TCP API + SQL Connect journey across independent API processes."""

import io
import json
import os
import secrets
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from PIL import Image, PngImagePlugin
from specimen_digitization.application.demo import fixture, journey


@pytest.mark.skipif(
    os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true",
    reason="Requires seeded local SQL Connect/PostgreSQL emulator",
)
def test_sql_http_restart(tmp_path):
    token = secrets.token_urlsafe(32)
    env = dict(os.environ, SPECIMEN_SYNTHETIC_TOKEN=token)
    command = [
        str(Path(".venv/bin/specimen-api").resolve()),
        "--mode",
        "synthetic",
        "--persistence",
        "sql-emulator",
        "--state-dir",
        str(tmp_path),
        "--port",
        "8102",
    ]

    def start():
        process = subprocess.Popen(
            command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        for _ in range(100):
            try:
                response = httpx.get(
                    "http://127.0.0.1:8102/v1/session",
                    headers={"Authorization": "Bearer " + token},
                )
                if response.status_code == 200:
                    return process
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        process.terminate()
        process.wait()
        raise AssertionError("Local API failed to start")

    process = start()
    try:
        # Unique synthetic source bytes preserve text while avoiding previous test duplicates.
        image = Image.open(io.BytesIO(fixture()))
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("synthetic_test_id", str(uuid4()))
        output = io.BytesIO()
        image.save(output, format="PNG", pnginfo=metadata)
        with httpx.Client(
            base_url="http://127.0.0.1:8102",
            headers={
                "Authorization": "Bearer " + token,
                "Idempotency-Key": str(uuid4()),
            },
            timeout=60,
        ) as client:
            before = journey(client, output.getvalue())["decision_response"]
        process.terminate()
        process.wait(timeout=10)
        process = start()
        with httpx.Client(
            base_url="http://127.0.0.1:8102",
            headers={"Authorization": "Bearer " + token},
            timeout=30,
        ) as client:
            prefix = "/v1/organizations/" + before["organization_id"]
            response = client.get(
                prefix + "/specimens/" + before["specimen_id"] + "/workspace"
            )
            assert response.status_code == 200, response.text
            assert response.json() == before
            original = client.get(
                prefix + "/assets/" + before["asset"]["id"] + "/content"
            )
            assert original.content == output.getvalue()
        evidence = {
            "mode": "synthetic",
            "persistence": "SQL Connect emulator + PostgreSQL18",
            "api_process_restart": True,
            "reconstructed_equal": True,
            "specimen_id": before["specimen_id"],
            "revision": before["revision"],
            "disposition": before["disposition"],
            "observations": len(before["observations"]),
            "source_bytes": len(original.content),
        }
        # Optional explicit artifact path: tests otherwise touch only their temporary state.
        if os.getenv("SPECIMEN_TEST_EVIDENCE_PATH"):
            Path(os.environ["SPECIMEN_TEST_EVIDENCE_PATH"]).write_text(
                json.dumps(evidence, indent=2) + "\n"
            )
    finally:
        process.terminate()
        process.wait(timeout=10)
