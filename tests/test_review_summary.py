"""Queue/workspace field counts without raw values or per-row snapshot reads."""

import json

import pytest

from specimen_digitization.application.domain import Scope
from specimen_digitization.application.review_summary import (
    project_fields,
    review_summary,
)
from specimen_digitization.application.search import SearchFilters, sql_item
from specimen_digitization.application.storage import SQLiteRepository


FIELDS = {
    "fmnh_ins_number": {"state": "supported", "literal": "105526321"},
    "collection_code": {"state": "not_present"},
    "country": {"state": "supported", "normalized": " ", "literal": "USA"},
    "province_state": {"state": "supported", "literal": " \t\n\u00a0\ufeff"},
    "city": {"state": "supported", "literal": "Chicago"},
    "county": {"state": "not_applicable"},
    "collectors": {"state": "unknown"},
    "taxon": {"state": "ambiguous", "parsed": "Apis"},
}
REASONS = [
    "evidence_missing:city",
    "evidence_missing:city",
    "mandatory_unresolved:city",
    "human_approval_required",
    "unresolved_transcription:label-one",
    "field_research_timeout:country",
    "evidence_missing:nonexistent",
]
EXPECTED = {"review": 4, "missing": 3}


def test_counts_are_unique_and_absence_is_distinct_from_review():
    assert review_summary(project_fields(FIELDS), REASONS) == EXPECTED
    assert review_summary(project_fields({"city": {"state": "not_present"}}), []) == {
        "review": 0,
        "missing": 1,
    }
    assert review_summary(
        project_fields({"city": {"state": "not_present"}}),
        ["mandatory_unresolved:city"],
    ) == {
        "review": 1,
        "missing": 1,
    }


@pytest.mark.parametrize(
    "fields",
    [
        None,
        {},
        [],
        {"city": {"has_value": 1}},
        {"city": {"state": [], "has_value": False}},
    ],
)
def test_unknown_or_malformed_projection_never_claims_zero(fields):
    assert review_summary(fields, []) is None


@pytest.mark.parametrize(
    "reason,field",
    [
        ("identifier_format", "fmnh_ins_number"),
        ("taxonomy_lookup_missing", "taxon"),
        ("identified_by_irn_identity_unproved", "identified_by_irn"),
        ("elevation_range:ft", "elevation_from_ft"),
        ("elevation_invalid:m", "elevation_from_m"),
        ("elevation_units_conflict:to", "elevation_to_m"),
    ],
)
def test_blocking_reason_targets_match_workbench(reason, field):
    fields = {field: {"state": "supported", "has_value": True}}
    assert review_summary(fields, [reason, reason]) == {"review": 1, "missing": 0}


def test_raw_observations_are_not_a_current_settled_value():
    assert review_summary(
        project_fields(
            {
                "city": {
                    "state": "supported",
                    "verbatim_by_observation": {"a": "Chicago"},
                }
            }
        ),
        [],
    ) == {"review": 1, "missing": 1}


def test_sqlite_search_and_named_sql_projection_count_without_snapshot_reads(
    tmp_path, monkeypatch
):
    repo = SQLiteRepository(tmp_path / "counts.db")
    scope = Scope(organization_id="org", collection_id="collection")
    stamp = "2026-01-01T00:00:00+00:00"
    payload = {
        "asset": {"sensitive": False},
        "run": {"fields": FIELDS, "reasons": REASONS},
    }
    with repo.connect() as db:
        db.execute(
            "INSERT INTO records(org,collection,id,revision,payload,created_at,state) VALUES (?,?,?,?,?,?,?)",
            ("org", "collection", "record", 1, json.dumps(payload), stamp, "finalized"),
        )
    monkeypatch.setattr(
        repo, "get", lambda *_: pytest.fail("No per-row snapshot fetch")
    )
    rows = repo.search(scope, SearchFilters(), stamp)
    assert rows[0]["review_summary"] == EXPECTED
    assert "fields" not in rows[0] and "field_review_states" not in rows[0]
    sql = sql_item(
        {"fieldReviewStates": project_fields(FIELDS), "reasonCodes": REASONS}, scope
    )
    assert sql["review_summary"] == rows[0]["review_summary"]
    assert "fieldReviewStates" not in sql
    assert sql_item({}, scope)["review_summary"] is None


@pytest.mark.parametrize(
    "field",
    [
        {"state": "supported", "literal": 123},
        {"state": "supported", "normalized": {"unexpected": "value"}},
        {"state": "supported", "parsed": True},
        "invalid field",
        None,
    ],
)
def test_malformed_persisted_values_do_not_look_settled(tmp_path, field):
    repo = SQLiteRepository(tmp_path / "malformed.db")
    scope = Scope(organization_id="org", collection_id="collection")
    fields = {"city": field}
    payload = {"asset": {"sensitive": False}, "run": {"fields": fields, "reasons": []}}
    stamp = "2026-01-01T00:00:00+00:00"
    with repo.connect() as db:
        db.execute(
            "INSERT INTO records(org,collection,id,revision,payload,created_at,state) VALUES (?,?,?,?,?,?,?)",
            ("org", "collection", "record", 1, json.dumps(payload), stamp, "finalized"),
        )
    actual = repo.search(scope, SearchFilters(), stamp)[0]["review_summary"]
    assert actual == review_summary(project_fields(fields), [])
    assert actual is None or actual == {"review": 1, "missing": 1}


def test_api_workspace_and_queue_count_the_same_current_revision(tmp_path):
    from test_application import client, intake, HEADERS, PREFIX, SYNTHETIC_COLLECTION

    with client(tmp_path) as http:
        created = intake(http)
        detail = http.get(
            f"{PREFIX}/specimens/{created['specimen_id']}", headers=HEADERS
        ).json()
        rows = http.get(
            f"{PREFIX}/specimens",
            params={
                "collection_id": SYNTHETIC_COLLECTION,
                "specimen_id": created["specimen_id"],
            },
            headers=HEADERS,
        ).json()["items"]
        assert len(rows) == 1
        assert rows[0]["revision"] == detail["revision"]
        assert rows[0]["review_summary"] == detail["review_summary"]
