"""The thread route (docs/execution/golive/DATA_CONTRACT.md 8, S5 T3).

It admits whom the workspace route admits, reads the active run unless `run_id` names another
run of the same specimen, and answers not found, the same way, for an unknown run and another
specimen's. The local SQLite runtime writes no normalized rows, so it has no thread. These run
in emulator mode with explicit memberships, which is how the role and sensitivity rules are
reachable; synthetic mode's one member may see everything.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
    create_app,
)
from specimen_digitization.application.domain import (
    Asset,
    FieldValue,
    Lookup,
    LookupStatus,
    Observation,
    Principal,
    Profile,
    Region,
    Run,
    Scope,
    Specimen,
    Transcript,
    ValueState,
)
from specimen_digitization.application.projection import RefusedContent, Write, writes
from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository, digest
from specimen_digitization.application.thread import TRACE_URL_SETTING
from specimen_digitization.application.workflow import SyntheticAdapters

from test_projection import PROFILE, locate, size
from thread_fixtures import TRACE, rows

USER = "member-fixture"
HEADERS = {"Authorization": "Bearer emulator-fixture"}
PREFIX = f"/v1/organizations/{SYNTHETIC_ORG}"
SCOPE = Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION)


class ProjectedSQLite(SQLiteRepository):
    """SQLite plus the writer's rows kept in memory, answering GetRunThreadV1 as SQL does."""

    def __init__(self, path):
        super().__init__(path)
        self.projected: list[Write] = []
        self.asked: list[str] = []

    def _commit(self, principal, specimen, expected, key, request_digest):
        saved = super()._commit(principal, specimen, expected, key, request_digest)
        try:
            self.projected += writes(saved, locate, size, principal.user_id, reviewer=True)
        except RefusedContent:
            # As in production: the snapshot is committed, and the projection writes nothing.
            pass
        return saved

    def record_trace(self, run_id, trace_id):
        self.projected.append(Write("RecordRunTraceV1", {"id": run_id, "traceId": trace_id}, run_id))

    def run_thread(self, scope, specimen_id, run_id, keys):
        self.asked.append(run_id)
        return rows(self.projected, specimen_id, run_id, keys)


def read_run(asset: Asset, texts=("Chicago, Ill.", "Chicago, Il1.")) -> Run:
    """A pinned run with one region read by both routes, in today's domain."""
    run = Run(
        profile=Profile(id="zoology_insects_slides", version="1.0.0", routes=("handwriting-qwen", "handwriting-muse")),
        profile_snapshot=PROFILE,
        dependencies={"profile_snapshot_sha256": digest(PROFILE)},
        stage="transcribe",
    )
    region = Region(id=str(uuid4()), asset_id=asset.id, x=10, y=20, width=390, height=160, order=0, method="sam3", version="rev-1")
    run.regions = [region]
    run.observations = [
        Observation(
            region_id=region.id,
            route_id=route,
            model_id=f"model/{route}",
            provider="fixture-provider",
            prompt_version="p" * 64,
            input_sha256="b" * 64,
            literal_text=text,
            raw_ref=f"{label * 64}:7",
            raw_sha256=label * 64,
        )
        for route, text, label in zip(run.profile.routes, texts, "cd")
    ]
    run.transcripts = [
        Transcript(
            region_id=region.id,
            observation_ids=[o.id for o in run.observations],
            alternatives=list(texts),
            resolved=False,
            disagreement_ratio=1 / 13,
            alignment_status="difference",
            alignment_algorithm="bounded-levenshtein-fraction-v1",
        )
    ]
    return run


def recorded(repo, sensitive=False) -> Specimen:
    sha = uuid4().hex * 2
    asset = Asset(
        sensitive=sensitive,
        sha256=sha,
        blob_ref=f"{sha}:1",
        media_type="image/jpeg",
        size_bytes=2048,
        width=4000,
        height=3000,
        filename="synthetic-slide.jpg",
        uploader=USER,
    )
    specimen = Specimen(scope=SCOPE, asset=asset, run=read_run(asset))
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    return repo.create(principal, specimen, "ingest:" + specimen.id, digest({"create": specimen.id}))


def reprocessed(repo, specimen) -> Specimen:
    """A new run that reads the same region again; the first becomes a previous run."""
    specimen.previous_runs.append(specimen.run)
    run = read_run(specimen.asset, ("Chicago, Ill.", "Chicago, Ill."))
    run.regions = specimen.run.regions
    for observation in run.observations:
        observation.region_id = run.regions[0].id
    run.transcripts[0].region_id = run.regions[0].id
    specimen.run = run
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    return repo.save(principal, specimen, specimen.version, "reprocess:" + specimen.id, digest({"run": run.id}))


def membership(role="reviewer", can_view_sensitive=True, organization=SYNTHETIC_ORG):
    return {
        "organization_id": organization,
        "collection_id": SYNTHETIC_COLLECTION,
        "role": role,
        "can_view_sensitive": can_view_sensitive,
    }


def client(tmp_path, repo, members):
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="emulator",
        repository=repo,
        blobs=blobs,
        adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
        identity_verifier=lambda bearer, appcheck: USER,
        memberships=lambda user: members,
    )
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def repo(tmp_path):
    return ProjectedSQLite(tmp_path / "state.sqlite3")


def thread(http, specimen_id, **params):
    return http.get(PREFIX + f"/specimens/{specimen_id}/thread", headers=HEADERS, params=params)


@pytest.mark.parametrize(
    ("members", "sensitive", "status"),
    [
        ([membership()], False, 200),
        ([membership("viewer")], False, 200),
        ([membership("operator", can_view_sensitive=False)], False, 200),
        ([membership()], True, 200),
        ([membership(can_view_sensitive=False)], True, 403),
        ([membership("viewer", can_view_sensitive=False)], True, 403),
        ([], False, 404),
        ([membership(organization=str(uuid4()))], False, 404),
    ],
)
def test_the_thread_admits_exactly_whom_the_workspace_route_admits(tmp_path, repo, members, sensitive, status):
    s = recorded(repo, sensitive=sensitive)
    http = client(tmp_path, repo, members)
    workspace = http.get(PREFIX + f"/specimens/{s.id}/workspace", headers=HEADERS)
    response = thread(http, s.id)
    assert (workspace.status_code, response.status_code) == (status, status), response.text
    if status != 200:
        assert response.json()["error"]["code"] == workspace.json()["error"]["code"]


def test_a_sensitive_specimen_is_refused_to_a_member_without_sensitive_access(tmp_path, repo):
    kept, open_ = recorded(repo, sensitive=True), recorded(repo)
    http = client(tmp_path, repo, [membership(can_view_sensitive=False)])
    refused = thread(http, kept.id)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "access_denied"
    # Its run is never read, and the same member reads a non-sensitive specimen's thread.
    assert kept.run.id not in repo.asked
    assert thread(http, open_.id).status_code == 200


def test_another_specimens_run_and_an_unknown_run_are_both_not_found(tmp_path, repo):
    mine, theirs = recorded(repo), recorded(repo)
    http = client(tmp_path, repo, [membership()])
    other = thread(http, mine.id, run_id=theirs.run.id)
    unknown = thread(http, mine.id, run_id=str(uuid4()))
    assert (other.status_code, unknown.status_code) == (404, 404)
    same = [{k: v for k, v in r.json()["error"].items() if k != "request_id"} for r in (other, unknown)]
    assert same[0] == same[1] == {
        "code": "not_found",
        "category": "input",
        "message": "Resource not found",
        "retryable": False,
        "details": {},
    }
    # Neither run is read: the specimen's own snapshot does not hold it.
    assert theirs.run.id not in repo.asked


def test_without_a_run_id_the_active_run_is_read_and_a_previous_run_by_its_id(tmp_path, repo):
    s = recorded(repo)
    first = s.run
    s = reprocessed(repo, s)
    http = client(tmp_path, repo, [membership()])
    active = thread(http, s.id)
    assert active.status_code == 200, active.text
    body = active.json()
    assert (body["specimen_id"], body["revision"], body["run"]["run_id"]) == (s.id, 2, s.run.id)
    readings = [r["observation_id"] for r in body["regions"][0]["readings"]]
    assert readings == [o.id for o in s.run.observations]
    previous = thread(http, s.id, run_id=first.id).json()
    assert previous["run"]["run_id"] == first.id
    assert previous["regions"][0]["region_id"] == body["regions"][0]["region_id"]
    assert [r["observation_id"] for r in previous["regions"][0]["readings"]] == [o.id for o in first.observations]
    assert thread(http, s.id, run_id=s.run.id).json() == body


def test_a_run_holding_a_credential_has_no_thread_and_the_answer_never_holds_it(tmp_path, repo):
    s = recorded(repo)
    # Built at run time, so no key-shaped literal is in the repository.
    credential = "AIza" + "0" * 35
    s.run.lookups.append(
        Lookup(
            provider="google-maps-geocoding",
            adapter_version="geocode-1",
            query={"address": "Chicago, Ill.", "key": credential},
            status=LookupStatus.SUCCESS,
            metadata={"locator": "place/fixture-place"},
            raw_ref=f"{'b' * 64}:7",
            digest="b" * 64,
        )
    )
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    s = repo.save(principal, s, s.version, "lookup:" + s.id, digest({"lookup": s.id}))
    response = thread(client(tmp_path, repo, [membership()]), s.id)
    # The writer refuses the run (rule 1.6), so the thread answers as for failed stored evidence.
    assert response.status_code == 503, response.text
    error = response.json()["error"]
    assert (error["code"], error["message"]) == (
        "runtime_unavailable",
        "lookup 0 (google-maps-geocoding) holds a credential in its query (rule 1.6)",
    )
    assert credential not in response.text
    # Refused before SQL is read.
    assert s.run.id not in repo.asked


def test_a_run_keeping_a_google_name_has_no_thread_and_the_answer_never_holds_it(tmp_path, repo):
    s = recorded(repo)
    # G26: a Google-confirmed value's identity keeps its place id and no name (T2c).
    s.run.fields["city"] = FieldValue(
        state=ValueState.SUPPORTED,
        literal="Chicago",
        authority_id="fixture-place",
        authority_identity={
            "source": "google-maps-geocoding",
            "source_record_id": "fixture-place",
            "name": "fixture-google-name",
        },
    )
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    s = repo.save(principal, s, s.version, "field:" + s.id, digest({"field": s.id}))
    response = thread(client(tmp_path, repo, [membership()]), s.id)
    assert response.status_code == 503, response.text
    error = response.json()["error"]
    assert (error["code"], error["message"]) == ("runtime_unavailable", "field city keeps a Google name (G26)")
    assert "fixture-google-name" not in response.text
    assert s.run.id not in repo.asked


def test_the_trace_link_uses_the_configured_template(tmp_path, repo, monkeypatch):
    s = recorded(repo)
    repo.record_trace(s.run.id, TRACE)
    assert thread(client(tmp_path, repo, [membership()]), s.id).json()["trace"] == {"trace_id": TRACE, "url": None}
    monkeypatch.setenv(TRACE_URL_SETTING, "https://logfire.example.test/trace/{trace_id}")
    linked = thread(client(tmp_path, repo, [membership()]), s.id).json()["trace"]
    assert linked == {"trace_id": TRACE, "url": f"https://logfire.example.test/trace/{TRACE}"}
    # A malformed template stops the API from starting.
    monkeypatch.setenv(TRACE_URL_SETTING, "http://logfire.example.test/trace/{trace_id}")
    with pytest.raises(ValueError):
        client(tmp_path, repo, [membership()])


def test_the_local_sqlite_runtime_has_no_thread(tmp_path):
    # SQLiteRepository writes no normalized rows (DATA_CONTRACT.md 11), as a runtime without
    # source configuration has no sources.
    repo = SQLiteRepository(tmp_path / "state.sqlite3")
    s = recorded(repo)
    http = client(tmp_path, repo, [membership()])
    assert http.get(PREFIX + f"/specimens/{s.id}/workspace", headers=HEADERS).status_code == 200
    response = thread(http, s.id)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
