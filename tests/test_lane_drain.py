"""The production worker drains the queue (docs/execution/golive/LANE.md, T2)."""

import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import (
    Asset,
    Disposition,
    Principal,
    Profile,
    Run,
    Scope,
    Specimen,
)
from specimen_digitization.application.lane_worker import (
    CollectionFence,
    FenceLost,
    drain_settings,
)
from specimen_digitization.application.storage import Conflict, SQLiteRepository
from specimen_digitization.hub_models import SAM3_MODEL

ORG = "00000000-0000-4000-8000-000000000001"
COLLECTION = "00000000-0000-4000-8000-000000000002"
SCOPE = Scope(organization_id=ORG, collection_id=COLLECTION)
WORKER = "worker-actor"
START = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)
DRAIN_ENV = {
    "SPECIMEN_WORKER_ACTOR_UID": "worker",
    "SPECIMEN_APPROVED_INFERENCE": "true",
    "SPECIMEN_SAM3_ENDPOINT": "https://sam.run.app",
    "SPECIMEN_SAM3_REVISION": SAM3_MODEL.revision,
    "HF_TOKEN": "fixture-not-a-credential",
}


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)


class NonSensitiveMember(SQLiteRepository):
    """The release membership cannot view sensitive records, so it may only
    write documents marked not sensitive (S5's SaveDocumentV2 check)."""

    def put_document(self, scope, kind, ident, payload, expected):
        if payload.get("sensitive", True) is not False:
            raise Conflict("SQL Connect transaction rejected")
        return super().put_document(scope, kind, ident, payload, expected)


def principal(scope=SCOPE):
    return Principal(user_id=WORKER, scope=scope, role="operator")


def queued(repository, ident, minutes, *, sensitive=False, stage="pending", scope=SCOPE):
    run = Run(profile=Profile(synthetic=False), stage=stage)
    run.queued_at = (START - timedelta(minutes=minutes)).isoformat()
    specimen = Specimen(
        id=ident,
        scope=scope,
        run=run,
        asset=Asset(
            sensitive=sensitive,
            sha256=hashlib.sha256(ident.encode()).hexdigest(),
            blob_ref="0" * 64,
            media_type="image/png",
            size_bytes=1,
            width=1,
            height=1,
            filename=ident + ".png",
            uploader="uploader",
        ),
        created_at=(START - timedelta(hours=1)).isoformat(),
    )
    repository.create(principal(scope), specimen, "queue:" + ident, ident)


@pytest.fixture
def lane(tmp_path):
    repository = NonSensitiveMember(tmp_path / "state.sqlite3")
    clock = Clock()
    return SimpleNamespace(
        repository=repository,
        clock=clock,
    )


def fence(lane, holder="exec-b"):
    return CollectionFence(lane.repository, SCOPE, WORKER, holder, clock=lane.clock)


def test_due_work_comes_oldest_request_first_and_never_sensitive(lane):
    queued(lane.repository, "c-newest", minutes=1)
    queued(lane.repository, "a-oldest", minutes=30)
    queued(lane.repository, "b-middle", minutes=10)
    queued(lane.repository, "d-sensitive", minutes=60, sensitive=True)
    cutoff = START.isoformat()
    due = lane.repository.oldest_due(SCOPE, cutoff, limit=10)
    assert [item.specimen_id for item in due] == ["a-oldest", "b-middle", "c-newest"]


def test_due_work_lists_only_the_states_production_lists(lane):
    queued(lane.repository, "a-blocked", minutes=30)
    queued(lane.repository, "b-done", minutes=20)
    queued(lane.repository, "c-due", minutes=10)
    for ident, stage, disposition in (
        ("a-blocked", "processing_blocked", None),
        ("b-done", "finalized", Disposition.REVIEW),
    ):
        specimen = lane.repository.get(SCOPE, ident)
        specimen.run.stage, specimen.run.disposition = stage, disposition
        lane.repository.save(principal(), specimen, specimen.version, "end:" + ident, ident)
    # An older write path left their due times behind.
    with lane.repository.connect() as db:
        db.execute(
            "UPDATE records SET work_available_at=? WHERE id IN ('a-blocked','b-done')",
            ((START - timedelta(hours=1)).isoformat(),),
        )
    due = lane.repository.oldest_due(SCOPE, START.isoformat(), limit=10)
    assert [item.specimen_id for item in due] == ["c-due"]


def test_the_fence_is_written_as_not_sensitive(lane):
    assert fence(lane).acquire() == {"revision": 0, "holder": None}
    stored = fence(lane).read()
    assert stored["sensitive"] is False
    assert stored["holder"] == "exec-b"


def test_the_fence_admits_one_holder_at_a_time(lane):
    first, second = fence(lane, "exec-a"), fence(lane, "exec-b")
    assert first.acquire() == {"revision": 0, "holder": None}
    assert second.acquire() is None  # Live, so left to its holder.
    first.hold("specimen-1", "run-1")
    lane.clock.sleep(301)
    taken = second.acquire()  # Expired, so taken over.
    assert (taken["holder"], taken["specimen_id"]) == ("exec-a", "specimen-1")
    with pytest.raises(FenceLost):
        first.hold("specimen-1", "run-1")
    first.release()  # Too late to matter.
    assert fence(lane).read()["holder"] == "exec-b"
    second.release()
    assert fence(lane).read()["holder"] is None


def test_the_provider_circuit_state_is_written_as_not_sensitive(lane):
    from specimen_digitization.application.circuit_runtime import RepositoryCircuitStore
    from specimen_digitization.application.provider_circuit import (
        CircuitKey,
        ProviderCircuit,
    )

    key = CircuitKey(
        organization_id=ORG,
        collection_id=COLLECTION,
        provider="fixture",
        config_sha256="1" * 64,
    )
    circuit = ProviderCircuit(RepositoryCircuitStore(lane.repository, SCOPE), lane.clock)
    admission = circuit.admit(key, 20)
    assert admission.status == "permitted"
    assert circuit.record_success(admission.token).status == "recorded"
    [stored] = lane.repository.documents(SCOPE, "worker_cursor")
    assert stored["sensitive"] is False


def test_the_fence_reads_numbers_sql_connect_returns_as_doubles(lane):
    fence(lane, "exec-a").acquire()
    document = lane.repository.document

    def transported(scope, kind, ident):
        # SQL Connect's Struct transport returns every JSON number as a double.
        stored = document(scope, kind, ident)
        return {k: float(v) if type(v) is int else v for k, v in stored.items()}

    lane.repository.document = transported
    current = fence(lane).read()
    assert (current["revision"], type(current["revision"])) == (1, int)
    lane.clock.sleep(301)
    assert fence(lane).acquire()["revision"] == 1
    assert fence(lane).read()["revision"] == 2


def test_production_due_work_uses_the_ordered_non_sensitive_query(monkeypatch):
    from specimen_digitization.application.production import (
        SqlConnectRepository,
        actor_uid,
    )

    monkeypatch.delenv("SPECIMEN_SQL_EMULATOR_HOST", raising=False)
    calls = []

    class Session:
        def post(self, url, **kwargs):
            calls.append(kwargs["json"])
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "data": {
                        "items": [
                            {
                                "id": "00000000-0000-4000-8000-00000000000a",
                                "revision": 3,
                                "state": "pending",
                                "workAvailableAt": "2026-09-23T11:00:00Z",
                                "createdAt": "2026-09-23T10:00:00Z",
                            }
                        ]
                    }
                },
            )

    token = actor_uid.set(WORKER)
    try:
        due = SqlConnectRepository(session=Session()).oldest_due(
            SCOPE, "2026-09-23T12:00:00Z", limit=5
        )
    finally:
        actor_uid.reset(token)
    assert calls[0]["operationName"] == "ListDueWorkV2"
    variables = calls[0]["variables"]
    assert variables["includeSensitive"] is False
    assert (variables["afterAt"], variables["afterId"], variables["limit"]) == (
        "1970-01-01T00:00:00Z",
        "",
        5,
    )
    assert [item.specimen_id for item in due] == ["00000000-0000-4000-8000-00000000000a"]


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"SPECIMEN_WORKER_ACTOR_UID": None}, "SPECIMEN_WORKER_ACTOR_UID"),
        ({"SPECIMEN_APPROVED_INFERENCE": None}, "SPECIMEN_APPROVED_INFERENCE"),
        ({"SPECIMEN_SQL_EMULATOR_HOST": "127.0.0.1:9499"}, "emulator"),
        ({"DATA_CONNECT_EMULATOR_HOST": "127.0.0.1:9399"}, "emulator"),
        ({"SPECIMEN_SAM3_LAB": "true"}, "lab mode"),
        ({"SPECIMEN_SAM3_ENDPOINT": None}, "SPECIMEN_SAM3_ENDPOINT"),
        ({"SPECIMEN_SAM3_ENDPOINT": "http://127.0.0.1:8080"}, "SPECIMEN_SAM3_ENDPOINT"),
        ({"SPECIMEN_SAM3_REVISION": "main"}, "SPECIMEN_SAM3_REVISION"),
        ({"HF_TOKEN": None}, "HF_TOKEN"),
        ({"SPECIMEN_WORKER_JOB": "specimen-worker"}, "SPECIMEN_WORKER_JOB"),
    ],
)
def test_drain_settings_fail_closed(change, problem):
    env = {**DRAIN_ENV, **change}
    with pytest.raises(ValueError, match=problem):
        drain_settings({key: value for key, value in env.items() if value is not None})


def test_drain_settings_carry_the_actor_job_and_bindings():
    job = "projects/example-project/locations/us-central1/jobs/specimen-worker"
    settings = drain_settings(
        {
            **DRAIN_ENV,
            "SPECIMEN_WORKER_JOB": job,
            "SPECIMEN_COLLECTION_BINDINGS_JSON": '{"' + COLLECTION + '": "insects"}',
        }
    )
    assert settings.actor_uid == "worker"
    assert settings.worker_job == job
    assert settings.bindings == {COLLECTION: "insects"}
