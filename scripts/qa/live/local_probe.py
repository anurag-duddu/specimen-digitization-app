"""Independent synthetic HTTP/SQLite recovery probe. No sockets or external providers."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import shutil

from fastapi.testclient import TestClient
from PIL import Image

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
    create_app,
    local_app,
)
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
from specimen_digitization.application.workflow import SyntheticAdapters


def run(root, checks=None):
    # This explicit fixture bearer is never sent beyond TestClient's ASGI transport.
    headers = {
        "Authorization": "Bearer qa-authored-fixture",
        "Idempotency-Key": "qa-intake",
    }
    prefix = f"/v1/organizations/{SYNTHETIC_ORG}"
    if checks is None:
        checks = []

    def check(name, condition, actual):
        checks.append(
            {
                "case": name,
                "status": "passed" if condition else "failed",
                "actual": actual,
            }
        )
        if not condition:
            raise AssertionError(name)

    def client():
        return TestClient(
            local_app(root, "qa-authored-fixture"), raise_server_exceptions=False
        )

    stream = io.BytesIO()
    Image.new("RGB", (120, 80), "white").save(stream, format="PNG")
    data = stream.getvalue()
    image_sha = hashlib.sha256(data).hexdigest()
    with client() as api:
        denied = api.get("/v1/session")
        check("missing-bearer", denied.status_code == 401, denied.status_code)
        batch = api.post(
            prefix + "/batches",
            headers=headers,
            json={
                "collection_id": SYNTHETIC_COLLECTION,
                "display_name": "QA authored fixture",
            },
        )
        check("batch", batch.status_code == 200, batch.status_code)
        item = api.post(
            prefix + f"/batches/{batch.json()['batch_id']}/items",
            headers=headers,
            json={
                "client_item_id": "qa-one",
                "filename": "authored-fixture.png",
                "media_type": "image/png",
                "size_bytes": len(data),
                "width": 120,
                "height": 80,
                "sha256": image_sha,
            },
        )
        check("item", item.status_code == 200, item.status_code)
        upload = prefix + f"/uploads/{item.json()['upload_id']}"
        part = api.put(upload + "/content", headers=headers, content=data[:20])
        check(
            "partial-upload",
            part.status_code == 200 and part.json()["offset"] == 20,
            part.status_code,
        )
    with client() as api:
        progress = api.get(upload, headers=headers)
        check(
            "upload-app-recreation",
            progress.status_code == 200 and progress.json()["offset"] == 20,
            {"status": progress.status_code, "offset": progress.json().get("offset")},
        )
        replay = api.put(upload + "/content", headers=headers, content=data[:20])
        check(
            "upload-replay",
            replay.status_code == 200 and replay.json()["offset"] == 20,
            replay.status_code,
        )
        rest = api.put(
            upload + "/content",
            headers=dict(headers, **{"Upload-Offset": "20"}),
            content=data[20:],
        )
        check("upload-resume", rest.status_code == 200, rest.status_code)
        completed = api.post(
            upload + "/complete",
            headers=headers,
            json={"expected_revision": rest.json()["revision"]},
        )
        check("complete", completed.status_code == 200, completed.status_code)
        ident = completed.json()["specimen_id"]
        path = prefix + f"/specimens/{ident}"
        response = api.get(path + "/workspace", headers=headers)
        check("workspace", response.status_code == 200, response.status_code)
        before = response.json()
        check(
            "synthetic-observations",
            len(before["observations"]) == 2,
            {"count": len(before["observations"]), "mode": "synthetic"},
        )
        decision = {
            "expected_revision": before["revision"],
            "base_record_version_id": before["record_version_id"],
            "kind": "transcription",
            "target_id": before["regions"][0]["region_id"],
            "after": {"state": "unreadable", "text": None},
            "reason": "Authored QA unreadable-span case",
        }
        decision_headers = dict(headers, **{"Idempotency-Key": "qa-correction"})
        corrected = api.post(
            path + "/decisions", headers=decision_headers, json=decision
        )
        check("correction", corrected.status_code == 200, corrected.status_code)
        saved = corrected.json()
        check(
            "readings-retained",
            saved["observations"] == before["observations"],
            {"count": len(saved["observations"])},
        )
        repeated = api.post(
            path + "/decisions", headers=decision_headers, json=decision
        )
        check(
            "decision-replay",
            repeated.status_code == 200
            and repeated.json()["revision"] == saved["revision"],
            repeated.status_code,
        )
        changed = api.post(
            path + "/decisions",
            headers=decision_headers,
            json=dict(decision, reason="Changed payload under same key"),
        )
        check("decision-conflict", changed.status_code == 409, changed.status_code)
        # Correction schedules legitimate downstream revalidation. Capture the
        # settled HTTP workspace, not the earlier decision response snapshot.
        saved = api.get(path + "/workspace", headers=headers).json()
    with client() as api:
        restored = api.get(path + "/workspace", headers=headers).json()
        check(
            "correction-app-recreation",
            restored == saved,
            {"revision": restored["revision"]},
        )
        source_path = prefix + f"/assets/{restored['asset']['id']}/content"
        original = api.get(source_path, headers=headers)
        check(
            "original-hash",
            original.status_code == 200
            and hashlib.sha256(original.content).hexdigest() == image_sha,
            {
                "status": original.status_code,
                "sha256": hashlib.sha256(original.content).hexdigest(),
            },
        )
        history = api.get(path + "/history", headers=headers)
        check("history-reopens", history.status_code == 200, history.status_code)

    # Injected identity/membership exercise API decisions only, never Firebase SDK behavior.
    memberships = [
        {
            "organization_id": SYNTHETIC_ORG,
            "collection_id": SYNTHETIC_COLLECTION,
            "role": "viewer",
            "can_view_sensitive": True,
        }
    ]
    blobs = LocalBlobs(root / "blobs")
    app = create_app(
        mode="emulator",
        repository=SQLiteRepository(root / "state.sqlite3"),
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda token, check_token: "qa-injected-viewer",
        memberships=lambda user: list(memberships),
        origins=["https://fixture.invalid"],
    )
    with TestClient(app, raise_server_exceptions=False) as api:
        viewed = api.get(path + "/workspace", headers=headers)
        check("viewer-positive-control", viewed.status_code == 200, viewed.status_code)
        denied = api.post(path + "/decisions", headers=decision_headers, json=decision)
        check("viewer-write-denied", denied.status_code == 403, denied.status_code)
        wrong = api.get(
            path.replace(SYNTHETIC_ORG, "unassigned-organization") + "/workspace",
            headers=headers,
        )
        check(
            "cross-organization-denied",
            wrong.status_code in {403, 404},
            wrong.status_code,
        )
        cors = api.options(
            "/v1/session",
            headers={
                "Origin": "https://untrusted.invalid",
                "Access-Control-Request-Method": "GET",
            },
        )
        check(
            "cors-untrusted-origin",
            "access-control-allow-origin" not in cors.headers,
            cors.status_code,
        )
        memberships.clear()
        for name, endpoint in (
            ("workspace", path + "/workspace"),
            ("source", source_path),
            ("history", path + "/history"),
        ):
            denied = api.get(endpoint, headers=headers)
            check(
                "membership-revoked-" + name,
                denied.status_code in {403, 404},
                denied.status_code,
            )
    return checks, image_sha


def source_identity():
    candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    changed = subprocess.check_output(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            "src",
            "apps",
            "dataconnect",
            "containers",
            "pyproject.toml",
            "uv.lock",
            "firebase.json",
            ".firebaserc",
        ],
        text=True,
    )
    if changed.strip():
        raise RuntimeError(
            "Product source must be clean before independent evidence capture"
        )
    return {
        "candidate_sha": candidate,
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    checks, image_sha, identity, failure, temporary = [], None, {}, None, None
    # Reserve output before executing: an existing evidence file aborts safely.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        try:
            identity = source_identity()
            temporary = Path(tempfile.mkdtemp(prefix="specimen-independent-qa-"))
            _, image_sha = run(temporary, checks)
            if source_identity() != identity:
                raise RuntimeError(
                    "Product or harness source changed during evidence capture"
                )
        except Exception as exc:
            # Keep synthetic state and completed checks; never echo exception
            # messages that could contain request headers or source contents.
            failure = type(exc).__name__
        result = {
            **identity,
            "started_at_utc": started,
            "ended_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "fixture",
            "transport": "ASGI TestClient / SQLite / LocalBlobs",
            "fixture_sha256": image_sha,
            "checks": checks,
            "cloud_specimens_used": 0,
            "paid_calls": 0,
            "release_accepted": False,
            "probe_status": "failed" if failure else "passed",
            "error_type": failure,
            "failed_state_directory": str(temporary) if failure and temporary else None,
            "limitations": [
                "App recreation in same process, not worker process restart",
                "Injected identity, not Firebase or App Check validation",
                "No real emulator, cloud SQL/Storage, browser, or provider used",
                "One authored blank raster; text supplied by synthetic adapter",
            ],
        }
        stream.write(json.dumps(result, indent=2) + "\n")
    if failure:
        print("Independent probe failed; retained evidence requires review")
        return 1
    if temporary is not None:
        shutil.rmtree(temporary)
    print(f"{len(checks)} independent local checks passed; cloud acceptance pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
