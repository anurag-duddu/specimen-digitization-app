"""`cleared_by` on the specimen list and detail: who cleared a cleared record.

The coordinator put the change to the owner as "'Cleared by the system' in the app. The design
says 'Green means a human affirmed it.'", and to "Go ahead with the plan, including the three
rule changes?" the owner typed "Yes, go ahead" (2026-11-17, session f9614090). The field is
derived from the stored `run.human_approved` (lane.cleared_by) on both list paths (SQLite and
SQL Connect) and on the summary the detail returns. Every writer dumps the run model, so the
stored value is always a JSON boolean; for one that is not, which no writer produces, the list
answers null and the detail follows the run model's coercion (pinned below).
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


MISSING = object()


def approved_synthetic_record(http):
    """The synthetic fixture processed and approved through the API: cleared, a person's."""
    ident = intake(http)["specimen_id"]
    work = http.post(PREFIX + f"/specimens/{ident}/process", headers=HEADERS).json()
    approved = http.post(PREFIX + f"/specimens/{ident}/decisions", headers=HEADERS, json={
        "expected_revision": work["revision"], "base_record_version_id": work["record_version_id"],
        "kind": "approve", "reason": "Synthetic fixture reviewed"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["cleared_by"] == "person"
    return ident


def read_both(http, ident):
    listed = http.get(PREFIX + "/specimens", headers=HEADERS,
                      params={"collection_id": SYNTHETIC_COLLECTION, "specimen_id": ident})
    assert listed.status_code == 200, listed.text
    [item] = listed.json()["items"]
    return item, http.get(PREFIX + f"/specimens/{ident}", headers=HEADERS)


# The detail's answer for each stored value no writer produces: the run model's coercion.
COERCED = {"missing": "system", "string": "person", "number": "person"}


@pytest.mark.parametrize("stored", [MISSING, "true", 1, None], ids=["missing", "string", "number", "null"])
def test_a_stored_value_that_is_not_a_boolean_is_null_on_the_list_and_coerced_on_the_detail(tmp_path, stored):
    """Pins the residual risk the contract states: only the list reads the stored JSON. The
    detail reads the validated run, whose lax boolean turns a missing key into False and "true"
    or 1 into True; a stored null makes the record unreadable. No writer stores these shapes."""
    with client(tmp_path) as http:
        ident = approved_synthetic_record(http)
        repo = SQLiteRepository(tmp_path / "state.sqlite3")
        scope = (SYNTHETIC_ORG, SYNTHETIC_COLLECTION, ident)
        # Rewrite the current stored snapshot in a shape no writer produces, with its digest,
        # so the reader accepts it as the stored record.
        with repo.connect() as db:
            revision, payload = db.execute(
                "SELECT revision,payload FROM records WHERE org=? AND collection=? AND id=?", scope).fetchone()
            payload = json.loads(payload)
            if stored is MISSING:
                del payload["run"]["human_approved"]
            else:
                payload["run"]["human_approved"] = stored
            text = json.dumps(payload)
            db.execute("UPDATE records SET payload=? WHERE org=? AND collection=? AND id=?", (text, *scope))
            db.execute("UPDATE versions SET payload=?,sha256=? WHERE org=? AND collection=? AND id=? AND revision=?",
                (text, digest(payload), *scope, revision))
        item, detail = read_both(http, ident)
        assert (item["disposition"], item["cleared_by"]) == ("cleared", None)
        if stored is None:
            assert detail.status_code >= 400 and "cleared_by" not in detail.json()
        else:
            name = "missing" if stored is MISSING else "string" if stored == "true" else "number"
            assert detail.status_code == 200, detail.text
            assert detail.json()["cleared_by"] == COERCED[name]


def test_a_rules_only_retry_of_an_approved_record_keeps_the_persons_approval(tmp_path, monkeypatch):
    """Codex's round 2 case: every ordinary step is complete, so a retry's only step is finalize,
    which applies the rules to the values the person approved. The approval stands."""
    from specimen_digitization.application import api as app_api
    from specimen_digitization.application.workflow import Workflow

    with client(tmp_path) as http:
        ident = approved_synthetic_record(http)
        repo = SQLiteRepository(tmp_path / "state.sqlite3")
        scope = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)
        stored = repo.get(scope, ident)
        assert Workflow.next_step(stored.run) == "finalize"
        response = http.post(PREFIX + f"/runs/{stored.run.id}/actions",
            headers={**HEADERS, "Idempotency-Key": "rules-only-retry"},
            json={"expected_revision": stored.version, "action": "retry", "reason": "Apply the rules again."})
        assert response.status_code == 200, response.text
        for _ in range(4):
            current = repo.get(scope, ident)
            if current.run.stage == "finalized":
                break
            http.app.state.workflow.step(
                Principal(user_id="synthetic-reviewer", scope=scope, role="reviewer"), ident)
        current = repo.get(scope, ident)
        assert (current.run.stage, current.run.disposition, current.run.human_approved) == (
            "finalized", Disposition.CLEARED, True)
        item, detail = read_both(http, ident)
        assert item["cleared_by"] == detail.json()["cleared_by"] == "person"
