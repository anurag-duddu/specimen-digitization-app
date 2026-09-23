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
OTHER = "00000000-0000-4000-8000-000000000003"
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


class SlowWorkflow(ScriptedWorkflow):
    """Each step takes 30 s."""

    def step(self, principal, ident):
        self.clock.sleep(30)
        return super().step(principal, ident)


def worker(
    repository,
    workflow,
    clock,
    *,
    execution="exec-a",
    role="operator",
    continuation=None,
    deadline_seconds=3600,
    collections=(COLLECTION,),
):
    return DrainWorker(
        repository,
        workflow,
        WORKER,
        lambda user: [
            {
                "organization_id": ORG,
                "collection_id": collection,
                "role": role,
                "can_view_sensitive": False,
            }
            for collection in collections
        ],
        execution_id=execution,
        clock=clock,
        sleep=clock.sleep,
        continuation=continuation,
        deadline_seconds=deadline_seconds,
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
    slow = SlowWorkflow(lane.repository, lane.clock, lane.workflow.scripts)
    continuation = Continuation()
    summary = worker(
        lane.repository, slow, lane.clock, continuation=continuation
    ).run(stop=None)
    assert "b-next" not in slow.steps
    assert summary["status"] == "window_closed"
    # The rest of the queue is handed to the next execution.
    assert (continuation.calls, summary["continuation"]) == (1, "requested")


def test_a_closed_window_with_nothing_due_starts_no_execution(lane):
    queued(lane.repository, "a-oldest", minutes=30)
    slow = SlowWorkflow(
        lane.repository, lane.clock, {"a-oldest": ["progress"] * 100 + ["finalized"]}
    )
    continuation = Continuation()
    summary = worker(
        lane.repository, slow, lane.clock, continuation=continuation
    ).run(stop=None)
    assert summary["status"] == "window_closed"
    assert (continuation.calls, summary["continuation"]) == (0, None)


def test_requested_work_in_a_collection_not_reached_is_handed_over(lane):
    queued(lane.repository, "a-oldest", minutes=30)
    queued(
        lane.repository,
        "z-other",
        minutes=5,
        scope=Scope(organization_id=ORG, collection_id=OTHER),
    )
    slow = SlowWorkflow(
        lane.repository, lane.clock, {"a-oldest": ["progress"] * 100 + ["finalized"]}
    )
    continuation = Continuation()
    summary = worker(
        lane.repository,
        slow,
        lane.clock,
        continuation=continuation,
        collections=(COLLECTION, OTHER),
    ).run(stop=None)
    assert "z-other" not in slow.steps
    assert summary["status"] == "window_closed"
    assert (continuation.calls, summary["continuation"]) == (1, "requested")


def test_handing_over_stops_after_three_executions_without_progress(lane):
    queued(lane.repository, "a-oldest", minutes=30)
    continuation = Continuation()
    for index in range(3):
        # A window too short to start anything makes no progress.
        summary = worker(
            lane.repository,
            lane.workflow,
            lane.clock,
            execution=f"exec-{index}",
            continuation=continuation,
            deadline_seconds=600,
        ).run(stop=None)
        if index < 2:
            assert fence(lane).read()["handovers_without_progress"] == index + 1
    assert lane.workflow.steps == []
    assert continuation.calls == 2
    assert summary["continuation"] is None
    assert summary["withheld_collections"] == [COLLECTION]
    run = lane.repository.get(SCOPE, "a-oldest").run
    assert (run.stage, run.blocker) == (
        "processing_blocked",
        "lane_handover_without_progress",
    )
    assert fence(lane).read()["handovers_without_progress"] == 0


def test_a_run_whose_step_saves_nothing_is_blocked_and_the_queue_moves_on(lane):
    queued(lane.repository, "a-stuck", minutes=30)
    queued(lane.repository, "b-next", minutes=10)

    class StuckWorkflow(ScriptedWorkflow):
        def step(self, principal, ident):
            if ident == "a-stuck":
                self.steps.append(ident)
                return self.repository.get(principal.scope, ident)  # Saves nothing.
            return super().step(principal, ident)

    stuck = StuckWorkflow(lane.repository, lane.clock)
    continuation = Continuation()
    summary = worker(
        lane.repository, stuck, lane.clock, continuation=continuation
    ).run(stop=None)
    assert stuck.steps == ["a-stuck", "b-next"]
    run = lane.repository.get(SCOPE, "a-stuck").run
    assert (run.stage, run.blocker) == ("processing_blocked", "lane_run_not_progressing")
    assert summary["status"] == "drained"
    assert continuation.calls == 0


def test_a_concurrent_edit_is_read_again_and_the_run_continues(lane):
    queued(lane.repository, "a-oldest", minutes=30)

    class EditedWorkflow(ScriptedWorkflow):
        edited = False

        def step(self, principal, ident):
            if not self.edited:
                # A reviewer saves first, so this step's save conflicts.
                self.edited = True
                specimen = self.repository.get(principal.scope, ident)
                self.repository.save(
                    principal, specimen, specimen.version, "review:edit", "edit"
                )
                raise Conflict("Stale revision")
            return super().step(principal, ident)

    edited = EditedWorkflow(
        lane.repository, lane.clock, {"a-oldest": ["progress", "finalized"]}
    )
    summary = worker(lane.repository, edited, lane.clock).run(stop=None)
    assert edited.steps == ["a-oldest", "a-oldest"]
    assert lane.repository.get(SCOPE, "a-oldest").run.disposition == Disposition.REVIEW
    assert summary["status"] == "drained"


def test_a_dead_holders_run_still_leased_is_waited_for(lane):
    queued(lane.repository, "b-interrupted", minutes=10, stage="transcribe")
    specimen = lane.repository.get(SCOPE, "b-interrupted")
    specimen.run.blocker = "external_outcome_unknown"
    specimen.run.lease_until = (START + timedelta(seconds=400)).isoformat()
    lane.repository.save(principal(), specimen, specimen.version, "intent:1", "intent")
    dead = fence(lane, "exec-dead")
    dead.acquire()
    dead.hold("b-interrupted", "run-b")
    lane.clock.sleep(301)
    worker(lane.repository, lane.workflow, lane.clock).run(stop=None)
    assert lane.workflow.steps == ["b-interrupted"]
    assert lane.clock.now >= START + timedelta(seconds=400)


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
