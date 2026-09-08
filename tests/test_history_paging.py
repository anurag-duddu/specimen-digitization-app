"""Repeated ordinary reviews stay writable while every prior version remains accessible."""

import os
import time

import pytest
from test_upload_completion_http import tcp_client  # noqa: F401
from fastapi.testclient import TestClient
from test_application import client, intake, HEADERS, PREFIX, TOKEN
from specimen_digitization.application.api import local_app
from specimen_digitization.application.domain import Principal, Scope, AuditEvent
from specimen_digitization.application.storage import digest


def exercise_reviews(http, tmp_path, count=110):
    row = intake(http)
    path = PREFIX + f"/specimens/{row['specimen_id']}"
    current = http.get(path + "/workspace", headers=HEADERS).json()
    for _ in range(200):
        if current["status"] == "completed":
            break
        time.sleep(0.05)
        current = http.get(path + "/workspace", headers=HEADERS).json()
    assert current["disposition"] == "needs_human_review"
    original = current
    ref = current["observations"][0]["raw_ref"]
    blob = tmp_path / "blobs" / ref
    raw = blob.read_bytes()
    first_request = first_response = None
    for index in range(count):
        if index % 2:
            blob.write_bytes(raw)
        else:
            blob.unlink()
        body = {
            "kind": "approve",
            "reason": "Synthetic reviewer checked retained evidence",
            "expected_revision": current["revision"],
            "base_record_version_id": current["record_version_id"],
        }
        headers = dict(HEADERS, **{"Idempotency-Key": f"history-review-{index}"})
        response = http.post(path + "/decisions", headers=headers, json=body)
        assert response.status_code == 200, response.text
        current = response.json()
        assert current["disposition"] == ("cleared" if index % 2 else None)
        if index == 0:
            first_request, first_response = (body, headers), current
    assert current["disposition"] == "cleared"
    replay = http.post(
        path + "/decisions", headers=first_request[1], json=first_request[0]
    )
    assert replay.json() == first_response
    stale = http.post(
        path + "/decisions",
        headers=dict(HEADERS, **{"Idempotency-Key": "stale-new"}),
        json=first_request[0],
    )
    assert stale.status_code == 409
    assert (
        http.get(path + f"/history/{original['revision']}", headers=HEADERS).json()
        == original
    )
    through, after, revisions = current["revision"], 0, []
    while True:
        page = http.get(
            path + "/history",
            headers=HEADERS,
            params={
                "after_revision": after,
                "through_revision": through,
                "limit": 17,
            },
        )
        assert page.status_code == 200, page.text
        page = page.json()
        assert page["through_revision"] == through
        revisions.extend(item["revision"] for item in page["items"])
        if page["next_cursor"] is None:
            break
        after = page["next_cursor"]
    assert revisions == list(range(1, through + 1))
    assert (
        http.get(
            path + "/history", headers=HEADERS, params={"through_revision": through + 1}
        ).status_code
        == 422
    )
    # New audit references resolve the complete prior run and verify its digest.
    audit = current["events"][-1]
    referenced = http.get(audit["before"]["history_url"], headers=HEADERS)
    assert referenced.status_code == 200, referenced.text
    assert digest(referenced.json()["run"]) == audit["before"]["run_sha256"]
    assert (
        http.get(
            path + f"/history/{through}",
            headers=HEADERS,
            params={"run_sha256": "wrong"},
        ).status_code
        == 409
    )
    return row, current


def test_one_hundred_ten_http_reviews_recover_without_losing_history(tmp_path):
    with client(tmp_path) as http:
        row, current = exercise_reviews(http, tmp_path)
    app = local_app(tmp_path, TOKEN)
    scope = Scope(
        organization_id=row["organization_id"], collection_id=row["collection_id"]
    )
    stored = app.state.workflow.repository.get(scope, row["specimen_id"])
    assert len(stored.model_dump_json().encode()) < 128 * 1024


def test_legacy_full_run_audit_compacts_only_previously_retained_content(tmp_path):
    app = local_app(tmp_path, TOKEN)
    with TestClient(app) as http:
        row = intake(http)
        repo = app.state.workflow.repository
        principal = Principal(
            user_id="synthetic-reviewer",
            role="reviewer",
            scope=Scope(
                organization_id=row["organization_id"],
                collection_id=row["collection_id"],
            ),
        )
        specimen = repo.get(principal.scope, row["specimen_id"])
        # Reproduce old shape near the cap; new content is not yet present in prior history.
        for _ in range(10):
            specimen.audit.append(
                AuditEvent(
                    actor=principal.user_id,
                    action="review_approve",
                    reason="Legacy synthetic review",
                    before=specimen.run.model_dump(mode="json"),
                )
            )
        legacy = repo.save(
            principal, specimen, specimen.version, "legacy", digest("legacy")
        )
        original_audit = legacy.audit
        path = PREFIX + f"/specimens/{specimen.id}"
        current = http.get(path + "/workspace", headers=HEADERS).json()
        response = http.post(
            path + "/decisions",
            headers=HEADERS,
            json={
                "kind": "approve",
                "reason": "Restore normal editability",
                "expected_revision": current["revision"],
                "base_record_version_id": current["record_version_id"],
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["disposition"] == "cleared"
        assert response.json()["history_through_revision"] == legacy.version
        recovered = repo.get(principal.scope, specimen.id)
        assert len(recovered.model_dump_json().encode()) < 128 * 1024
        assert (
            repo.version(principal.scope, specimen.id, legacy.version).audit
            == original_audit
        )


@pytest.mark.skipif(
    os.getenv("SPECIMEN_TEST_SQL_EMULATOR") != "true",
    reason="Requires seeded SQL Connect/PostgreSQL",
)
@pytest.mark.parametrize("tcp_client", ["sql-emulator"], indirect=True)
def test_real_sql_tcp_one_hundred_ten_reviews_and_history(
    tcp_client, tmp_path, monkeypatch
):
    import io
    from uuid import uuid4
    from PIL import Image, PngImagePlugin
    import test_application

    original = test_application.image_bytes()
    image = Image.open(io.BytesIO(original))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("synthetic_history_test", str(uuid4()))
    output = io.BytesIO()
    image.save(output, format="PNG", pnginfo=metadata)
    monkeypatch.setattr(test_application, "image_bytes", lambda: output.getvalue())
    monkeypatch.setitem(HEADERS, "Authorization", tcp_client.headers["Authorization"])
    monkeypatch.setitem(HEADERS, "Idempotency-Key", str(uuid4()))
    _, current = exercise_reviews(tcp_client, tmp_path)
    assert current["disposition"] == "cleared"


def test_history_current_authorization_and_stored_snapshot_digest(tmp_path):
    from specimen_digitization.application.api import (
        create_app,
        SYNTHETIC_ORG,
        SYNTHETIC_COLLECTION,
    )
    from specimen_digitization.application.storage import SQLiteRepository, LocalBlobs
    from specimen_digitization.application.workflow import SyntheticAdapters
    from specimen_digitization.application.api import SYNTHETIC_TEXT
    import json

    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    blobs = LocalBlobs(tmp_path / "blobs")
    members = [
        {
            "organization_id": SYNTHETIC_ORG,
            "collection_id": SYNTHETIC_COLLECTION,
            "role": "reviewer",
            "can_view_sensitive": True,
        }
    ]
    app = create_app(
        mode="emulator",
        identity_verifier=lambda bearer, appcheck: "synthetic-reviewer",
        repository=repo,
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        token=TOKEN,
        memberships=lambda user: members,
    )
    with TestClient(app) as http:
        row = intake(http)
        path = PREFIX + f"/specimens/{row['specimen_id']}/history/1"
        assert http.get(path, headers=HEADERS).status_code == 200
        members[0]["can_view_sensitive"] = False
        assert http.get(path, headers=HEADERS).status_code == 403
        members[0]["can_view_sensitive"] = True
        member = members.pop()
        assert http.get(path, headers=HEADERS).status_code in {403, 404}
        members.append(member)
        with repo.connect() as db:
            payload = json.loads(
                db.execute(
                    "SELECT payload FROM versions WHERE id=? AND revision=1",
                    (row["specimen_id"],),
                ).fetchone()[0]
            )
            payload["run"]["human_approved"] = True
            db.execute(
                "UPDATE versions SET payload=? WHERE id=? AND revision=1",
                (json.dumps(payload), row["specimen_id"]),
            )
        assert http.get(path, headers=HEADERS).status_code == 409


def test_history_hash_identifies_retained_snapshot_before_new_defaults(tmp_path):
    import json

    app = local_app(tmp_path, TOKEN)
    with TestClient(app) as http:
        row = intake(http)
        repo = app.state.workflow.repository
        with repo.connect() as db:
            payload = json.loads(
                db.execute(
                    "SELECT payload FROM versions WHERE id=? AND revision=1",
                    (row["specimen_id"],),
                ).fetchone()[0]
            )
            payload.pop("audit_offset")
            payload.pop("history_through_revision")
            retained_sha = digest(payload)
            db.execute(
                "UPDATE versions SET payload=?,sha256=? WHERE id=? AND revision=1",
                (json.dumps(payload), retained_sha, row["specimen_id"]),
            )
        path = PREFIX + f"/specimens/{row['specimen_id']}/history"
        page = http.get(path, headers=HEADERS, params={"limit": 1}).json()
        assert page["items"][0]["sha256"] == retained_sha
        detail = http.get(
            path + "/1",
            headers=HEADERS,
            params={
                "run_sha256": digest(payload["run"]),
                "run_id": payload["run"]["id"],
            },
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["audit_offset"] == 0
        assert detail.json()["history_through_revision"] is None
