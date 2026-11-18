"""`cleared_by` on the specimen list and detail: who cleared a cleared record.

The owner's words, typed 2026-11-17 in session f9614090, to the coordinator's plan he answered
"Yes, go ahead": "'Cleared by the system' in the app. The design says 'Green means a human
affirmed it.'" The field is derived from the stored `run.human_approved` (lane.cleared_by) on
both list paths (SQLite and SQL Connect) and on the summary the detail returns.
"""

import json
from uuid import uuid4

import pytest

from test_application import HEADERS, PREFIX, SYNTHETIC_COLLECTION, client, intake
from specimen_digitization.application.api import SYNTHETIC_ORG, summary
from specimen_digitization.application.domain import (
    Asset,
    Disposition,
    Principal,
    Run,
    Scope,
    Specimen,
    now,
)
from specimen_digitization.application.lane import cleared_by
from specimen_digitization.application.search import SearchFilters, sql_item
from specimen_digitization.application.storage import SQLiteRepository, digest


@pytest.mark.parametrize(
    ("disposition", "approved", "expected"),
    [
        ("cleared", True, "person"),
        ("cleared", False, "system"),
        (Disposition.CLEARED, False, "system"),
        ("cleared", None, None),
        ("cleared", "true", None),
        ("cleared", 1, None),
        ("needs_human_review", True, None),
        ("needs_human_review", False, None),
        ("deferred", True, None),
        (None, True, None),
        (None, None, None),
    ],
)
def test_cleared_by_names_a_person_or_the_system_only_for_a_cleared_record(disposition, approved, expected):
    assert cleared_by(disposition, approved) == expected


def specimen_for(run):
    return Specimen(scope=Scope(organization_id="org", collection_id="collection"), run=run,
        asset=Asset(sha256="a" * 64, blob_ref="photo", media_type="image/png", size_bytes=1,
                    width=1, height=1, filename="photo.png", uploader="operator"))


@pytest.mark.parametrize(
    ("disposition", "approved", "expected"),
    [
        (Disposition.CLEARED, True, "person"),
        (Disposition.CLEARED, False, "system"),
        (Disposition.REVIEW, False, None),
        (Disposition.REVIEW, True, None),
        (Disposition.DEFERRED, False, None),
        (None, False, None),
    ],
)
def test_the_summary_says_who_cleared_the_record(disposition, approved, expected):
    run = Run(stage="finalized" if disposition else "transcribe", disposition=disposition,
              human_approved=approved)
    result = summary(specimen_for(run), "reviewer")
    assert result["cleared_by"] == expected
    # Additive: the fields an older client reads are unchanged.
    assert result["disposition"] == disposition
    assert result["status"] == ("completed" if disposition else "running")


def insert(repo, scope, run):
    ident = str(uuid4())
    stamp = "2026-01-01T00:00:00+00:00"
    payload = {"created_at": stamp, "asset": {"sensitive": False, "filename": ident + ".png"}, "run": run}
    with repo.connect() as db:
        db.execute(
            "INSERT INTO records(org,collection,id,revision,payload,created_at,state) VALUES (?,?,?,?,?,?,?)",
            (scope.organization_id, scope.collection_id, ident, 1, json.dumps(payload), stamp, "finalized"),
        )
    return ident


def test_the_sqlite_list_says_who_cleared_each_record_and_null_for_an_old_record(tmp_path):
    repo = SQLiteRepository(tmp_path / "state.db")
    scope = Scope(organization_id="org", collection_id="collection")
    expected = {
        insert(repo, scope, {"stage": "finalized", "disposition": "cleared", "human_approved": True}): "person",
        insert(repo, scope, {"stage": "finalized", "disposition": "cleared", "human_approved": False}): "system",
        insert(repo, scope, {"stage": "finalized", "disposition": "needs_human_review",
                             "human_approved": False}): None,
        insert(repo, scope, {"stage": "finalized", "disposition": "deferred", "human_approved": True}): None,
        # A stored run without the value, or with one that is not a boolean, does not say.
        insert(repo, scope, {"stage": "finalized", "disposition": "cleared"}): None,
        insert(repo, scope, {"stage": "finalized", "disposition": "cleared", "human_approved": 1}): None,
        insert(repo, scope, {"stage": "finalized", "disposition": "cleared", "human_approved": "true"}): None,
    }
    rows = repo.search(scope, SearchFilters(), now(), limit=100, include_sensitive=True)
    assert {row["specimen_id"]: row["cleared_by"] for row in rows} == expected
    assert all("human_approved" not in row for row in rows)
    cleared = repo.search(scope, SearchFilters(disposition="cleared"), now(), limit=100, include_sensitive=True)
    assert sorted(row["cleared_by"] or "" for row in cleared) == ["", "", "", "person", "system"]


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"disposition": "cleared", "humanApproved": True}, "person"),
        ({"disposition": "cleared", "humanApproved": False}, "system"),
        ({"disposition": "cleared", "humanApproved": None}, None),
        ({"disposition": "cleared"}, None),
        ({"disposition": "needs_human_review", "humanApproved": False}, None),
        ({"disposition": None, "humanApproved": True}, None),
    ],
)
def test_the_sql_connect_list_row_says_who_cleared_it(row, expected):
    scope = Scope(organization_id=str(uuid4()), collection_id=str(uuid4()))
    item = sql_item({"id": str(uuid4()), "revision": 3, "activeRunId": str(uuid4()), "reasonCodes": [], **row}, scope)
    assert item["cleared_by"] == expected
    assert "humanApproved" not in item and "human_approved" not in item


def test_the_api_list_and_detail_follow_a_person_approval_and_a_system_clearance(tmp_path):
    with client(tmp_path) as http:
        ident = intake(http)["specimen_id"]
        processed = http.post(PREFIX + f"/specimens/{ident}/process", headers=HEADERS)
        assert processed.status_code == 200, processed.text
        work = processed.json()
        assert work["disposition"] == "needs_human_review"

        def read():
            listed = http.get(PREFIX + "/specimens", headers=HEADERS,
                              params={"collection_id": SYNTHETIC_COLLECTION, "specimen_id": ident})
            assert listed.status_code == 200, listed.text
            detail = http.get(PREFIX + f"/specimens/{ident}", headers=HEADERS)
            assert detail.status_code == 200, detail.text
            [item] = listed.json()["items"]
            return item["disposition"], item["cleared_by"], detail.json()["cleared_by"]

        assert read() == ("needs_human_review", None, None)
        approved = http.post(PREFIX + f"/specimens/{ident}/decisions", headers=HEADERS, json={
            "expected_revision": work["revision"],
            "base_record_version_id": work["record_version_id"],
            "kind": "approve",
            "reason": "Synthetic fixture reviewed",
        })
        assert approved.status_code == 200, approved.text
        assert approved.json()["disposition"] == "cleared"
        assert approved.json()["cleared_by"] == "person"
        assert read() == ("cleared", "person", "person")

        # The clearance rules clear a record with no person (field_research.step.finalize_fields):
        # the same stored record, cleared, with no approval standing.
        scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
        repo = SQLiteRepository(tmp_path / "state.sqlite3")
        stored = repo.get(scope, ident)
        stored.run.human_approved = False
        stored.run.disposition = Disposition.CLEARED
        principal = Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer")
        repo.save(principal, stored, stored.version, "system-clearance", digest({"system": ident}))
        assert read() == ("cleared", "system", "system")
