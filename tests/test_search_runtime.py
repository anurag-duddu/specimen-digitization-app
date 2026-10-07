"""Metadata-only pagination and actual API filter/cursor contracts."""

import json
from uuid import uuid4
from test_application import client, intake, HEADERS, PREFIX, SYNTHETIC_COLLECTION
from specimen_digitization.application.domain import Scope, now
from specimen_digitization.application.storage import SQLiteRepository
from specimen_digitization.application.search import SearchFilters
from specimen_digitization.application.production import SqlConnectRepository, actor_uid


def test_sqlite_search_large_metadata_only_and_keyset(tmp_path, monkeypatch):
    repo = SQLiteRepository(tmp_path / "state.db")
    scope = Scope(organization_id="org", collection_id="collection")
    stamp = "2026-01-01T00:00:00+00:00"
    rows = []
    for i in range(10037):
        ident = str(uuid4())
        payload = {
            "created_at": stamp,
            "asset": {"id": str(uuid4()), "sensitive": i % 2 == 0},
            "run": {
                "id": str(uuid4()),
                "stage": "finalized",
                "disposition": "needs_human_review",
                "reasons": ["review"],
                "profile": {"id": "insects", "version": "1"},
                "review_risk": {"composite": 0} if i % 3 else {},
            },
        }
        rows.append(
            ("org", "collection", ident, 1, json.dumps(payload), stamp, "finalized")
        )
    with repo.connect() as db:
        db.executemany(
            "INSERT INTO records(org,collection,id,revision,payload,created_at,state) VALUES (?,?,?,?,?,?,?)",
            rows,
        )
    monkeypatch.setattr(
        repo,
        "list",
        lambda *_: (_ for _ in ()).throw(AssertionError("No full snapshots")),
    )
    expected = sorted(row[2] for i, row in enumerate(rows) if i % 2 and i % 3)
    actual = []
    after = ""
    created = None
    while True:
        page = repo.search(
            scope,
            SearchFilters(risk_min=0, risk_max=0, reason_code="review"),
            now(),
            created,
            after,
            100,
            False,
        )
        actual.extend(row["specimen_id"] for row in page)
        if len(page) < 100:
            break
        created, after = page[-1]["created_at"], page[-1]["specimen_id"]
    assert actual == expected
    assert repo.search(scope, SearchFilters(risk_min=1), now()) == []


def test_display_reference_is_exact_scoped_and_respects_sensitivity(tmp_path, monkeypatch):
    repo = SQLiteRepository(tmp_path / "display-reference.db")
    scope = Scope(organization_id="org", collection_id="collection")
    stamp = "2026-01-01T00:00:00+00:00"
    rows = []
    expected = None
    sensitive_match = None
    for collection, filename, sensitive in (
        ("collection", "source/subject_105526321.JPG", False),
        ("collection", "subject_1055263210.png", False),
        ("collection", "subject_105526321.png", True),
        ("other-collection", "subject_105526321.png", False),
    ):
        ident = str(uuid4())
        if filename.endswith(".JPG"):
            expected = ident
        elif sensitive:
            sensitive_match = ident
        payload = {
            "created_at": stamp,
            "asset": {"filename": filename, "sensitive": sensitive},
            "run": {"stage": "finalized", "disposition": "cleared"},
        }
        rows.append(
            ("org", collection, ident, 1, json.dumps(payload), stamp, "finalized")
        )
    with repo.connect() as db:
        db.executemany(
            "INSERT INTO records(org,collection,id,revision,payload,created_at,state) VALUES (?,?,?,?,?,?,?)",
            rows,
        )
    monkeypatch.setattr(
        repo,
        "list",
        lambda *_: (_ for _ in ()).throw(AssertionError("No full snapshots")),
    )

    filters = SearchFilters(display_reference="#105526321")
    visible = repo.search(scope, filters, now(), limit=100, include_sensitive=False)
    assert [row["specimen_id"] for row in visible] == [expected]
    all_matching = repo.search(scope, filters, now(), limit=100, include_sensitive=True)
    assert {row["specimen_id"] for row in all_matching} == {expected, sensitive_match}
    uuid_fallback = str(uuid4())
    with repo.connect() as db:
        db.execute(
            "INSERT INTO records(org,collection,id,revision,payload,created_at,state) VALUES (?,?,?,?,?,?,?)",
            (
                "org",
                "collection",
                uuid_fallback,
                1,
                json.dumps({"created_at": stamp, "asset": {"sensitive": False}}),
                stamp,
                "finalized",
            ),
        )
    fallback = repo.search(
        scope,
        SearchFilters(display_reference=uuid_fallback[:8]),
        now(),
        include_sensitive=False,
    )
    assert [row["specimen_id"] for row in fallback] == [uuid_fallback]


def test_named_search_passes_display_reference_to_bounded_query():
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"data": {"SearchSpecimens": {"items": []}}}

    class Session:
        def __init__(self):
            self.request = None

        def post(self, _url, *, json, timeout):
            self.request = json
            return Response()

    session = Session()
    repo = SqlConnectRepository(session=session)
    scope = Scope(organization_id="org", collection_id="collection")
    actor_uid.set("synthetic-reviewer")
    try:
        assert repo.search(
            scope, SearchFilters(display_reference="105526321"), now(), limit=25
        ) == []
    finally:
        actor_uid.set(None)

    assert session.request["operationName"] == "SearchSpecimens"
    assert session.request["variables"]["displayReference"] == "105526321"
    assert session.request["variables"]["limit"] == 25
    assert session.request["variables"]["collectionId"] == "collection"


def test_http_search_filters_cursors_and_exact_routes_do_not_list(
    tmp_path, monkeypatch
):
    with client(tmp_path) as http:
        row = intake(http)
        path = PREFIX + "/specimens"
        repo = http.app.state.workflow.repository
        monkeypatch.setattr(
            repo,
            "list",
            lambda *_: (_ for _ in ()).throw(AssertionError("No full list")),
        )
        params = {
            "collection_id": SYNTHETIC_COLLECTION,
            "limit": 1,
            "specimen_id": row["specimen_id"],
        }
        response = http.get(path, params=params, headers=HEADERS)
        assert response.status_code == 200, response.text
        first = response.json()
        assert len(first["items"]) == 1
        following = http.get(
            path, params={**params, "cursor": first["next_cursor"]}, headers=HEADERS
        )
        assert following.status_code == 200 and following.json()["items"] == []
        reference_params = {
            "collection_id": SYNTHETIC_COLLECTION,
            "limit": 1,
            "display_reference": "#synthetic",
        }
        by_reference = http.get(path, params=reference_params, headers=HEADERS)
        assert by_reference.status_code == 200, by_reference.text
        assert [item["specimen_id"] for item in by_reference.json()["items"]] == [
            row["specimen_id"]
        ]
        assert by_reference.json()["next_cursor"]
        changed_reference_cursor = http.get(
            path,
            params={
                **reference_params,
                "display_reference": "another-record",
                "cursor": by_reference.json()["next_cursor"],
            },
            headers=HEADERS,
        )
        assert changed_reference_cursor.status_code == 422
        uuid_reference = http.get(
            path,
            params={
                "collection_id": SYNTHETIC_COLLECTION,
                "specimen_id": row["specimen_id"],
            },
            headers=HEADERS,
        )
        assert uuid_reference.status_code == 200, uuid_reference.text
        assert [item["specimen_id"] for item in uuid_reference.json()["items"]] == [
            row["specimen_id"]
        ]
        for extra in (
            {"cursor": "12"},
            {"state": "unknown"},
            {"issue_code": "review"},
            {"risk_min": 101},
            {"risk_min": "NaN"},
            {"created_from": "2026-01-01"},
            {"cursor": first["next_cursor"], "risk_min": 0},
        ):
            assert (
                http.get(path, params={**params, **extra}, headers=HEADERS).status_code
                == 422
            )
        item = first["items"][0]
        access_path = PREFIX + "/assets/" + item["asset_id"] + "/access"
        assert http.get(access_path, headers=HEADERS).status_code == 200
        assert (
            http.get(
                PREFIX + "/runs/" + item["active_run_id"] + "/events", headers=HEADERS
            ).status_code
            == 200
        )
        detail = http.get(path + "/" + item["specimen_id"], headers=HEADERS).json()
        assert detail["created_at"] == item["created_at"]
