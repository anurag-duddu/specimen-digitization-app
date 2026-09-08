"""Explicit ordinary intake must not grant access to sensitive or legacy evidence."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from specimen_digitization.application.api import (
    BatchInput, ItemInput, create_app, SYNTHETIC_ORG, SYNTHETIC_COLLECTION, SYNTHETIC_TEXT,
)
from specimen_digitization.application.domain import Asset, Principal, Scope
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import SQLiteRepository, LocalBlobs, Conflict, digest
from specimen_digitization.application.workflow import SyntheticAdapters
from test_application import image_bytes, HEADERS, PREFIX


def setup_app(tmp_path, sensitive_permission=False):
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    blobs = LocalBlobs(tmp_path / "blobs")
    members = [{
        "organization_id": SYNTHETIC_ORG, "collection_id": SYNTHETIC_COLLECTION,
        "role": "admin", "can_view_sensitive": sensitive_permission,
    }]
    app = create_app(
        mode="emulator", identity_verifier=lambda *_: "reviewer", repository=repo,
        blobs=blobs, adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        memberships=lambda _: members,
    )
    return app, repo, members


def upload_record(http, sensitive=False):
    batch = http.post(PREFIX + "/batches", headers=HEADERS, json={
        "collection_id": SYNTHETIC_COLLECTION, "display_name": "Declared fixture",
        "sensitive": sensitive,
    })
    assert batch.status_code == 200, batch.text
    raw = image_bytes()
    item = http.post(PREFIX + f"/batches/{batch.json()['batch_id']}/items", headers=HEADERS, json={
        "client_item_id": "one", "filename": "declared.png", "media_type": "image/png",
        "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "sensitive": sensitive,
    })
    assert item.status_code == 200, item.text
    upload = item.json()
    progress = http.put(upload["upload_url"], headers=HEADERS, content=raw)
    assert progress.status_code == 200, progress.text
    done = http.post(PREFIX + f"/uploads/{upload['upload_id']}/complete", headers=HEADERS,
                     json={"expected_revision": progress.json()["revision"]})
    assert done.status_code == 200, done.text
    return done.json(), batch.json(), upload


def test_explicit_non_sensitive_intake_save_reopen_history_and_pixels(tmp_path):
    app, repo, members = setup_app(tmp_path)
    with TestClient(app) as http:
        row, batch, upload = upload_record(http)
        path = PREFIX + f"/specimens/{row['specimen_id']}"
        work = http.get(path + "/workspace", headers=HEADERS)
        assert work.status_code == 200, work.text
        assert work.json()["asset"]["sensitive"] is False
        pause = http.post(PREFIX + f"/runs/{row['active_run_id']}/actions", headers=HEADERS,
                          json={"expected_revision": row["revision"], "action": "pause", "reason": "Review source"})
        assert pause.status_code == 200, pause.text
        assert http.get(path + "/workspace", headers=HEADERS).json()["stage"] == "paused"
        assert http.get(path + "/history", headers=HEADERS).status_code == 200
        prior = http.get(path + "/history/1", headers=HEADERS)
        assert prior.status_code == 200, prior.text
        assert prior.json()["asset"]["sensitive"] is False
        assert http.get(path + "/active-graph?revision=1", headers=HEADERS).status_code == 200
        asset = PREFIX + f"/assets/{row['asset_id']}"
        assert http.get(asset + "/access", headers=HEADERS).status_code == 200
        assert http.get(asset + "/content", headers=HEADERS).content == image_bytes()
        assert http.get(asset + "/content?view=true", headers=HEADERS).status_code == 200
        members.clear()
        for url in (path + "/workspace", path + "/history/1", asset + "/content",
                    PREFIX + f"/batches/{batch['batch_id']}", upload["upload_url"].removesuffix("/content")):
            assert http.get(url, headers=HEADERS).status_code in {403, 404}
    reopened = SQLiteRepository(tmp_path / "state.sqlite3")
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    assert reopened.get(scope, row["specimen_id"]).asset.sensitive is False
    assert reopened.version(scope, row["specimen_id"], 1).asset.sensitive is False


def test_default_and_explicit_sensitive_intake_require_permission(tmp_path):
    app, _, _ = setup_app(tmp_path)
    with TestClient(app) as http:
        body = {"collection_id": SYNTHETIC_COLLECTION, "display_name": "Unknown classification"}
        for extra in ({}, {"sensitive": True}):
            assert http.post(PREFIX + "/batches", headers=HEADERS, json=body | extra).status_code == 403


def test_permission_revocation_denies_current_history_images_and_uploads(tmp_path):
    app, _, members = setup_app(tmp_path, True)
    with TestClient(app) as http:
        row, batch, upload = upload_record(http, True)
        members[0]["can_view_sensitive"] = False
        path = PREFIX + f"/specimens/{row['specimen_id']}"
        for url in (path + "/workspace", path + "/history", path + "/history/1",
                    path + "/active-graph", PREFIX + f"/assets/{row['asset_id']}/content",
                    PREFIX + f"/batches/{batch['batch_id']}", upload["upload_url"].removesuffix("/content")):
            assert http.get(url, headers=HEADERS).status_code in {403, 404}


@pytest.mark.parametrize("bad", [0, 1, "false", "true", None])
def test_intake_sensitivity_never_coerces_untrusted_values(bad):
    with pytest.raises(ValidationError):
        BatchInput(collection_id="c", display_name="x", sensitive=bad)


def test_default_sensitivity_preserves_legacy_payload_and_request_digests(tmp_path):
    batch = {"collection_id": "c", "display_name": "legacy", "acquisition_method": "files"}
    assert BatchInput(**batch).sensitive is True
    assert BatchInput(**batch).model_dump() == batch
    asset = dict(sha256="a" * 64, blob_ref="blob", media_type="image/png", size_bytes=1,
                 width=1, height=1, filename="legacy.png", uploader="reviewer")
    old = Asset(**asset).model_dump(mode="json")
    assert "sensitive" not in old
    assert Asset.model_validate(old).sensitive is True
    assert Asset.model_validate(old).model_dump(mode="json") == old
    item = dict(client_item_id="one", filename="legacy.png", media_type="image/png",
                size_bytes=1, width=None, height=None, sha256="a" * 64)
    assert ItemInput(**item).model_dump() == item


def test_repositories_never_downgrade_sensitive_history(tmp_path):
    app, repo, _ = setup_app(tmp_path, True)
    with TestClient(app) as http:
        row, _, _ = upload_record(http, True)
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    specimen = repo.get(scope, row["specimen_id"])
    specimen.asset.sensitive = False
    principal = Principal(user_id="reviewer", scope=scope, role="admin")
    with pytest.raises(Conflict, match="[Ss]ensitiv"):
        repo.save(principal, specimen, specimen.version, "downgrade", digest("downgrade"))
    sql = object.__new__(SqlConnectRepository)
    sql.graph_blobs = None
    calls = []
    retained = repo.get(scope, specimen.id)
    def execute(operation, variables, mutation=False):
        calls.append(operation)
        if operation == "GetReceipt":
            return {}
        if operation == "GetSnapshot":
            payload = retained.model_dump(mode="json")
            return {"specimenSnapshot": {"snapshot": payload, "sha256": digest(payload)}}
        return {}
    sql.execute = execute
    actor_uid.set("reviewer")
    with pytest.raises(Conflict, match="[Ss]ensitiv"):
        sql.save(principal, specimen, specimen.version, "downgrade", digest("downgrade"))
    assert "SaveSpecimenV3" not in calls


def test_sql_create_uses_declared_asset_sensitivity(tmp_path):
    app, repo, _ = setup_app(tmp_path)
    with TestClient(app) as http:
        row, _, _ = upload_record(http)
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    specimen = repo.get(scope, row["specimen_id"])
    sql = object.__new__(SqlConnectRepository)
    sql.graph_blobs = None
    calls = []
    sql.execute = lambda op, variables, mutation=False: calls.append((op, variables)) or {}
    actor_uid.set("reviewer")
    sql.create(Principal(user_id="reviewer", scope=scope, role="admin"), specimen, "new", digest("new"))
    created = next(v for op, v in calls if op == "CreateSpecimenV3")
    assert created["sensitive"] is False
    assert created["snapshot"]["asset"]["sensitive"] is False


def test_historical_sensitive_snapshot_never_inherits_current_false_access(tmp_path):
    app, repo, _ = setup_app(tmp_path)
    with TestClient(app) as http:
        row, _, _ = upload_record(http)
        changed = http.post(PREFIX + f"/runs/{row['active_run_id']}/actions", headers=HEADERS,
                            json={"expected_revision": row["revision"], "action": "pause", "reason": "New current revision"})
        assert changed.status_code == 200, changed.text
        # Simulate an older retained sensitive/unknown snapshot, independently
        # signed by storage; current false must not grant access to its content.
        with repo.connect() as db:
            raw = json.loads(db.execute("SELECT payload FROM versions WHERE id=? AND revision=1",
                                        (row["specimen_id"],)).fetchone()[0])
            raw["asset"].pop("sensitive")
            db.execute("UPDATE versions SET payload=?,sha256=? WHERE id=? AND revision=1",
                       (json.dumps(raw), digest(raw), row["specimen_id"]))
        path = PREFIX + f"/specimens/{row['specimen_id']}"
        assert http.get(path + "/history/1", headers=HEADERS).status_code == 403
        assert http.get(path + "/active-graph?revision=1", headers=HEADERS).status_code == 403
        assert http.get(path + "/phases/resolve?revision=1", headers=HEADERS).status_code == 403
        assert http.get(path + "/authority-results/parties?revision=1", headers=HEADERS).status_code == 403


def test_batch_item_mismatch_is_rejected_before_upload_creation(tmp_path):
    app, repo, _ = setup_app(tmp_path, True)
    with TestClient(app) as http:
        batch = http.post(PREFIX + "/batches", headers=HEADERS, json={
            "collection_id": SYNTHETIC_COLLECTION, "display_name": "Ordinary", "sensitive": False,
        }).json()
        raw = image_bytes()
        response = http.post(PREFIX + f"/batches/{batch['batch_id']}/items", headers=HEADERS, json={
            "client_item_id": "mismatch", "filename": "sensitive.png", "media_type": "image/png",
            "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        })
        assert response.status_code == 422
        assert repo.documents(Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION), "upload") == []


def test_non_sensitive_pilot_declaration_binds_cohort_and_ledger(tmp_path):
    from specimen_digitization.application.worker_launch import PilotLaunch, PilotAdmission
    from specimen_digitization.application.workflow import OperationalBlock
    from test_worker_launch import fixture

    _, principal, originals, old_launch = fixture(tmp_path)
    old_payload = old_launch.model_dump(mode="json")
    assert "sensitive" not in old_payload
    assert PilotLaunch.model_validate(old_payload).model_dump(mode="json") == old_payload
    launch = PilotLaunch.model_validate(dict(old_payload, sensitive=False))
    repo = SQLiteRepository(tmp_path / "declared-cohort.sqlite3")
    specimens = []
    for original in originals[:10]:
        specimen = original.model_copy(deep=True)
        specimen.asset.sensitive = False
        specimens.append(repo.create(principal, specimen, specimen.id, digest(specimen.id)))
    admission = PilotAdmission(repo, launch)
    for specimen in specimens:
        admission.admit(specimen)
    ledger = repo.document(principal.scope, "pilot_launch", admission.ledger_id)
    assert ledger["sensitive"] is False
    assert len(ledger["runs"]) == 10
    sensitive = originals[0]
    with pytest.raises(OperationalBlock, match="pilot_specimen_binding_mismatch"):
        admission.admit(sensitive)
    assert ledger == repo.document(principal.scope, "pilot_launch", admission.ledger_id)


def test_auxiliary_v2_contract_preserves_scope_and_classification(tmp_path):
    sql = object.__new__(SqlConnectRepository)
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    calls = []
    sql.memberships = lambda actor: [{
        "organization_id": SYNTHETIC_ORG, "collection_id": SYNTHETIC_COLLECTION,
        "can_view_sensitive": False,
    }]
    ident = "00000000-0000-4000-8000-000000000005"
    def execute(op, variables, mutation=False):
        calls.append((op, variables, mutation))
        if op == "GetDocumentV2":
            return {"auxiliaryDocument": {"sensitive": False, "payload": {"sensitive": False, "revision": 1}}}
        if op == "ListDocumentPageV2":
            return {"auxiliaryDocuments": [{"id": ident, "sensitive": False}]}
        return {}
    sql.execute = execute
    actor_uid.set("reviewer")
    assert sql.document(scope, "batch", ident)["sensitive"] is False
    assert len(sql.documents(scope, "batch")) == 1
    sql.put_document(scope, "batch", ident, {"sensitive": False}, 0)
    sql.put_document(scope, "batch", ident, {"sensitive": False}, 1)
    assert [v["includeSensitive"] for op, v, _ in calls if op == "ListDocumentPageV2"] == [False]
    assert all(v["sensitive"] is False for op, v, _ in calls if op in {"CreateDocumentV2", "SaveDocumentV2"})
    assert all(v["actorUid"] == "reviewer" and v["collectionId"] == SYNTHETIC_COLLECTION for _, v, _ in calls)
    sql.execute = lambda *_args, **_kwargs: {"auxiliaryDocument": {"sensitive": False, "payload": {"revision": 1}}}
    with pytest.raises(Conflict, match="sensitivity metadata mismatch"):
        sql.document(scope, "batch", ident)


def test_sql_rejects_disagreement_between_current_column_and_snapshot(tmp_path):
    app, repo, _ = setup_app(tmp_path, True)
    with TestClient(app) as http:
        row, _, _ = upload_record(http, True)
    scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
    payload = repo.get(scope, row["specimen_id"]).model_dump(mode="json")
    sql = object.__new__(SqlConnectRepository)
    sql.graph_blobs = None
    sql.execute = lambda op, *_args, **_kwargs: (
        {"specimen": {"revision": 1, "sensitive": False}, "specimenSnapshots": [{}]}
        if op == "GetSpecimen" else {"specimenSnapshot": {"snapshot": payload, "sha256": digest(payload)}}
    )
    actor_uid.set("reviewer")
    with pytest.raises(Conflict, match="sensitivity metadata mismatch"):
        sql.get(scope, row["specimen_id"])


def test_auxiliary_column_binding_never_coerces_numeric_false():
    sql = object.__new__(SqlConnectRepository)
    sql.execute = lambda *_args, **_kwargs: {"auxiliaryDocument": {
        "sensitive": False, "payload": {"sensitive": 0, "revision": 1},
    }}
    actor_uid.set("reviewer")
    with pytest.raises(Conflict, match="sensitivity metadata mismatch"):
        sql.document(Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION), "batch", "id")


def test_run_event_read_rechecks_membership_after_metadata_lookup(tmp_path):
    app, repo, members = setup_app(tmp_path)
    with TestClient(app) as http:
        row, _, _ = upload_record(http)
        original_get = repo.get
        def revoked_after_get(*args):
            result = original_get(*args)
            members.clear()
            return result
        repo.get = revoked_after_get
        result = http.get(PREFIX + f"/runs/{row['active_run_id']}/events", headers=HEADERS)
        assert result.status_code in {403, 404}


@pytest.mark.parametrize("unknown", [None, 0, "false"])
def test_legacy_malformed_auxiliary_classification_does_not_grant_access(tmp_path, unknown):
    app, repo, _ = setup_app(tmp_path)
    with TestClient(app) as http:
        _, batch, _ = upload_record(http)
        with repo.connect() as db:
            payload = dict(batch, sensitive=unknown)
            db.execute("UPDATE documents SET payload=? WHERE kind='batch' AND id=?",
                       (json.dumps(payload), batch["batch_id"]))
        result = http.get(PREFIX + f"/batches/{batch['batch_id']}", headers=HEADERS)
        assert result.status_code == 403
