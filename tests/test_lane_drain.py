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
from specimen_digitization.application.lane_dispatch import DispatchOutcome
from specimen_digitization.application.lane_worker import (
    CollectionFence,
    DrainWorker,
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


class Continuation:
    """Records each start of the next execution."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return DispatchOutcome(status="requested")


class NonSensitiveMember(SQLiteRepository):
    """The release membership cannot view sensitive records, so it may only
    write documents marked not sensitive (S5's SaveDocumentV2 check)."""

    def put_document(self, scope, kind, ident, payload, expected):
        if payload.get("sensitive", True) is not False:
            raise Conflict("SQL Connect transaction rejected")
        return super().put_document(scope, kind, ident, payload, expected)


def principal():
    return Principal(user_id=WORKER, scope=SCOPE, role="operator")


def queued(repository, ident, minutes, *, sensitive=False, stage="pending"):
    run = Run(profile=Profile(synthetic=False), stage=stage)
    run.queued_at = (START - timedelta(minutes=minutes)).isoformat()
    specimen = Specimen(
        id=ident,
        scope=SCOPE,
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
    repository.create(principal(), specimen, "queue:" + ident, ident)


class ScriptedWorkflow:
    """Steps each run through a script of outcomes and records the order."""

    def __init__(self, repository, clock, scripts=None):
        self.repository, self.clock = repository, clock
        self.scripts = scripts or {}
        self.steps = []

    def step(self, principal, ident):
        self.steps.append(ident)
        specimen = self.repository.get(principal.scope, ident)
        script = self.scripts.setdefault(ident, ["finalized"])
        outcome = script.pop(0) if len(script) > 1 else script[0]
        run = specimen.run
        if outcome == "finalized":
            run.stage, run.disposition = "finalized", Disposition.REVIEW
        elif outcome == "progress":
            run.stage = "transcribe"
        elif outcome.startswith("retry:"):
            run.stage = "retry_scheduled"
            run.next_retry_at = (
                self.clock() + timedelta(seconds=int(outcome.split(":")[1]))
            ).isoformat()
        # Keyed by revision, like the workflow's intents, so a later execution's
        # step is not mistaken for a replay of an earlier one.
        return self.repository.save(
            principal, specimen, specimen.version, f"step:{ident}:{specimen.version}", ident
        )


def worker(
    repository, workflow, clock, *, execution="exec-a", role="operator", continuation=None
):
    return DrainWorker(
        repository,
        workflow,
        WORKER,
        lambda user: [
            {
                "organization_id": ORG,
                "collection_id": COLLECTION,
                "role": role,
                "can_view_sensitive": False,
            }
        ],
        execution_id=execution,
        clock=clock,
        sleep=clock.sleep,
        continuation=continuation,
    )


@pytest.fixture
def lane(tmp_path):
    repository = NonSensitiveMember(tmp_path / "state.sqlite3")
    clock = Clock()
    return SimpleNamespace(
        repository=repository,
        clock=clock,
        workflow=ScriptedWorkflow(repository, clock),
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


def test_the_worker_drains_one_run_at_a_time_in_request_order(lane):
    queued(lane.repository, "c-newest", minutes=1)
    queued(lane.repository, "a-oldest", minutes=30)
    lane.workflow.scripts = {"a-oldest": ["progress", "progress", "finalized"]}
    continuation = Continuation()
    summary = worker(
        lane.repository, lane.workflow, lane.clock, continuation=continuation
    ).run(stop=None)
    assert lane.workflow.steps == ["a-oldest", "a-oldest", "a-oldest", "c-newest"]
    assert summary["status"] == "drained"
    assert summary["processed"] == ["a-oldest", "c-newest"]
    assert fence(lane).read()["holder"] is None
    # An empty queue starts no further execution.
    assert (continuation.calls, summary["continuation"]) == (0, None)


def test_the_fence_is_written_as_not_sensitive(lane):
    assert fence(lane).acquire() == {"revision": 0, "holder": None}
    stored = fence(lane).read()
    assert stored["sensitive"] is False
    assert stored["holder"] == "exec-b"


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


def test_a_collection_another_execution_is_draining_is_left_to_it(lane):
    queued(lane.repository, "a-oldest", minutes=30)
    assert fence(lane, "exec-other").acquire() is not None
    summary = worker(lane.repository, lane.workflow, lane.clock).run(stop=None)
    assert lane.workflow.steps == []
    assert summary["skipped_collections"] == [COLLECTION]


def test_an_expired_fence_is_taken_over_and_its_run_finished_first(lane):
    queued(lane.repository, "a-oldest", minutes=30)
    queued(lane.repository, "b-interrupted", minutes=10, stage="transcribe")
    dead = fence(lane, "exec-dead")
    dead.acquire()
    dead.hold("b-interrupted", "run-b")
    lane.clock.sleep(301)
    worker(lane.repository, lane.workflow, lane.clock).run(stop=None)
    assert lane.workflow.steps == ["b-interrupted", "a-oldest"]


def test_a_worker_that_loses_its_fence_leaves_the_collection(lane):
    queued(lane.repository, "a-oldest", minutes=30)

    class StallingWorkflow(ScriptedWorkflow):
        def step(self, principal, ident):
            specimen = super().step(principal, ident)
            self.clock.sleep(301)  # Stalled past the lease; another execution takes over.
            assert fence(lane, "exec-other").acquire() is not None
            return specimen

    stalling = StallingWorkflow(lane.repository, lane.clock, {"a-oldest": ["progress"]})
    summary = worker(lane.repository, stalling, lane.clock).run(stop=None)
    assert stalling.steps == ["a-oldest"]
    assert summary["skipped_collections"] == [COLLECTION]
    assert fence(lane).read()["holder"] == "exec-other"


def test_a_short_retry_is_waited_for_before_the_worker_exits(lane):
    queued(lane.repository, "a-oldest", minutes=30)
    lane.workflow.scripts = {"a-oldest": ["retry:12", "finalized"]}
    summary = worker(lane.repository, lane.workflow, lane.clock).run(stop=None)
    assert lane.workflow.steps == ["a-oldest", "a-oldest"]
    assert summary["status"] == "drained"
    assert lane.clock.now >= START + timedelta(seconds=12)


def test_a_retry_after_the_window_is_handed_to_the_next_execution(lane):
    queued(lane.repository, "a-oldest", minutes=30)

    class LateWorkflow(ScriptedWorkflow):
        def step(self, principal, ident):
            self.clock.sleep(2900)
            return super().step(principal, ident)

    late = LateWorkflow(lane.repository, lane.clock, {"a-oldest": ["retry:200"]})
    continuation = Continuation()
    summary = worker(
        lane.repository, late, lane.clock, continuation=continuation
    ).run(stop=None)
    assert late.steps == ["a-oldest"]
    assert summary["pending_retries"] == 1
    assert (continuation.calls, summary["continuation"]) == (1, "requested")
    left = fence(lane).read()
    assert (left["holder"], left["specimen_id"]) == (None, "a-oldest")
    assert left["retry_at"] == (START + timedelta(seconds=3100)).isoformat()

    # The next execution waits for the handed-over retry, then finishes the run.
    lane.clock.sleep(10)
    lane.workflow.scripts = {"a-oldest": ["finalized"]}
    summary = worker(
        lane.repository, lane.workflow, lane.clock, execution="exec-b"
    ).run(stop=None)
    assert lane.workflow.steps == ["a-oldest"]
    assert summary["processed"] == ["a-oldest"]
    assert lane.clock.now >= START + timedelta(seconds=3100)


def test_a_retry_no_execution_could_reach_waits_for_a_later_request(lane):
    queued(lane.repository, "a-oldest", minutes=30)
    lane.workflow.scripts = {"a-oldest": ["retry:7000", "finalized"]}
    continuation = Continuation()
    summary = worker(
        lane.repository, lane.workflow, lane.clock, continuation=continuation
    ).run(stop=None)
    assert lane.workflow.steps == ["a-oldest"]
    assert summary["pending_retries"] == 1
    assert (continuation.calls, summary["continuation"]) == (0, None)


def test_no_new_run_starts_in_the_last_ten_minutes(lane):
    queued(lane.repository, "a-oldest", minutes=30)
    queued(lane.repository, "b-next", minutes=10)
    lane.workflow.scripts = {"a-oldest": ["progress"] * 100 + ["finalized"]}

    class SlowWorkflow(ScriptedWorkflow):
        def step(self, principal, ident):
            self.clock.sleep(30)
            return super().step(principal, ident)

    slow = SlowWorkflow(lane.repository, lane.clock, lane.workflow.scripts)
    continuation = Continuation()
    summary = worker(
        lane.repository, slow, lane.clock, continuation=continuation
    ).run(stop=None)
    assert "b-next" not in slow.steps
    assert summary["status"] == "window_closed"
    # The rest of the queue is handed to the next execution.
    assert (continuation.calls, summary["continuation"]) == (1, "requested")


def test_a_stop_signal_ends_the_drain_and_releases_the_fence(lane):
    import threading

    queued(lane.repository, "a-oldest", minutes=30)
    queued(lane.repository, "b-next", minutes=10)
    stop = threading.Event()

    class StoppingWorkflow(ScriptedWorkflow):
        def step(self, principal, ident):
            stop.set()
            return super().step(principal, ident)

    stopping = StoppingWorkflow(lane.repository, lane.clock)
    continuation = Continuation()
    summary = worker(
        lane.repository, stopping, lane.clock, continuation=continuation
    ).run(stop=stop)
    assert stopping.steps == ["a-oldest"]
    assert summary["status"] == "stopped"
    assert fence(lane).read()["holder"] is None
    assert continuation.calls == 0


def test_viewer_memberships_are_not_drained(lane):
    queued(lane.repository, "a-oldest", minutes=30)
    worker(lane.repository, lane.workflow, lane.clock, role="viewer").run(stop=None)
    assert lane.workflow.steps == []


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
