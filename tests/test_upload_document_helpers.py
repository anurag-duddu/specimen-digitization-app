"""Batch upload helpers avoid full-document scans and SqlConnect N+1 fetches."""

from __future__ import annotations

from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import SQLiteRepository, digest


SCOPE = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)


def _upload(batch_id, key, *, sensitive=False, digest_seed="body"):
    return {
        "batch_id": batch_id,
        "idempotency_key": key,
        "sensitive": sensitive,
        "request_digest": digest(digest_seed),
        "upload_id": f"upload-{key}",
        "revision": 1,
    }


def test_sqlite_uploads_for_batch_filters_by_batch_and_sensitivity(tmp_path):
    repo = SQLiteRepository(tmp_path / "uploads.sqlite3")
    kept = _upload("batch-a", "a1", sensitive=False)
    other_batch = _upload("batch-b", "b1", sensitive=False)
    hidden = _upload("batch-a", "a2", sensitive=True)
    repo.put_document(SCOPE, "upload", kept["upload_id"], kept, 0)
    repo.put_document(SCOPE, "upload", other_batch["upload_id"], other_batch, 0)
    repo.put_document(SCOPE, "upload", hidden["upload_id"], hidden, 0)

    ordinary = repo.uploads_for_batch(SCOPE, "batch-a", include_sensitive=False)
    assert [row["upload_id"] for row in ordinary] == [kept["upload_id"]]

    privileged = repo.uploads_for_batch(SCOPE, "batch-a", include_sensitive=True)
    assert {row["upload_id"] for row in privileged} == {
        kept["upload_id"],
        hidden["upload_id"],
    }


def test_sqlite_upload_by_idempotency_returns_matching_row(tmp_path):
    repo = SQLiteRepository(tmp_path / "idem.sqlite3")
    first = _upload("batch-a", "same-key", digest_seed="one")
    second = _upload("batch-a", "other-key", digest_seed="two")
    repo.put_document(SCOPE, "upload", first["upload_id"], first, 0)
    repo.put_document(SCOPE, "upload", second["upload_id"], second, 0)

    found = repo.upload_by_idempotency(SCOPE, "batch-a", "same-key")
    assert found["request_digest"] == first["request_digest"]
    assert repo.upload_by_idempotency(SCOPE, "batch-a", "missing") is None
    assert repo.upload_by_idempotency(SCOPE, "batch-b", "same-key") is None


def test_sqlconnect_documents_uses_payload_list_without_per_row_get():
    sql = object.__new__(SqlConnectRepository)
    calls = []
    ident = "00000000-0000-4000-8000-000000000011"
    payload = {"sensitive": False, "revision": 1, "batch_id": "batch-a"}

    def execute(op, variables, mutation=False):
        calls.append((op, variables, mutation))
        if op == "ListDocumentsV2":
            return {
                "auxiliaryDocuments": [
                    {"id": ident, "sensitive": False, "payload": payload}
                ]
            }
        raise AssertionError(f"unexpected operation {op}")

    sql.execute = execute
    sql.memberships = lambda _actor: [
        {
            "organization_id": SYNTHETIC_ORG,
            "collection_id": SYNTHETIC_COLLECTION,
            "can_view_sensitive": False,
        }
    ]
    actor_uid.set("operator")
    assert sql.documents(SCOPE, "upload") == [payload]
    assert [op for op, _, _ in calls] == ["ListDocumentsV2"]
    assert calls[0][1]["includeSensitive"] is False
    assert "GetDocumentV2" not in {op for op, _, _ in calls}


def test_sqlconnect_upload_by_idempotency_stops_after_match():
    sql = object.__new__(SqlConnectRepository)
    calls = []
    miss_page = [
        {
            "id": f"00000000-0000-4000-8000-{index:012x}",
            "sensitive": False,
            "payload": _upload("batch-a", f"miss-{index}"),
        }
        for index in range(100)
    ]
    hit_page = [
        {
            "id": "00000000-0000-4000-8000-0000000000bb",
            "sensitive": False,
            "payload": _upload("batch-a", "wanted"),
        },
        {
            "id": "00000000-0000-4000-8000-0000000000cc",
            "sensitive": False,
            "payload": _upload("batch-a", "later"),
        },
    ]
    pages = {0: miss_page, 100: hit_page}

    def execute(op, variables, mutation=False):
        calls.append((op, variables, mutation))
        if op == "ListDocumentsV2":
            return {"auxiliaryDocuments": pages[variables["offset"]]}
        raise AssertionError(f"unexpected operation {op}")

    sql.execute = execute
    sql.memberships = lambda _actor: [
        {
            "organization_id": SYNTHETIC_ORG,
            "collection_id": SYNTHETIC_COLLECTION,
            "can_view_sensitive": True,
        }
    ]
    actor_uid.set("operator")
    found = sql.upload_by_idempotency(SCOPE, "batch-a", "wanted")
    assert found["idempotency_key"] == "wanted"
    list_calls = [v for op, v, _ in calls if op == "ListDocumentsV2"]
    assert len(list_calls) == 2
    assert list_calls[0]["offset"] == 0
    assert list_calls[1]["offset"] == 100
