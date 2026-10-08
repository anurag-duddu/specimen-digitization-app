"""The production worker drains the queue (docs/execution/golive/LANE.md, T2)."""

import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import (
    Asset,
    Disposition,
    Observation,
    Principal,
    Profile,
    ReaderHandoff,
    Region,
    Run,
    Scope,
    Specimen,
    Transcript,
)
from specimen_digitization.application.lane_dispatch import DispatchOutcome
from specimen_digitization.application.lane_worker import (
    CollectionFence,
    DrainWorker,
    FenceLost,
    drain_settings,
)
from specimen_digitization.application.native_drain import RegisteredNativeDrainWorkflow
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.projection import Blob
from specimen_digitization.application.storage import Conflict, SQLiteRepository
from specimen_digitization.application.storage import digest as canonical_digest
from specimen_digitization.application.worker_deadline import WorkerDeadline
from specimen_digitization.application.workflow import OperationalBlock, Workflow
from specimen_digitization.hub_models import SAM3_MODEL
from specimen_digitization.research_harness import provisioning
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import ResearchScope
from specimen_digitization.research_harness.native_worker import (
    NativeResearchWorkerOutcomeV2,
)
from specimen_digitization.research_harness.persistence import (
    DurabilityScope,
    HeldUnknown,
    SqliteStateBackend,
    StaleWork,
)
from specimen_digitization.research_harness.native_canonical_v2 import SqlConnectCanonicalResearchWriterV2
from specimen_digitization.research_harness.workflow_bridge import NativeResearchWorkflow

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


def queued(repository, ident, minutes, *, sensitive=False, stage="pending", scope=SCOPE,
           profile_snapshot=None):
    run = Run(profile=Profile(synthetic=False), stage=stage,
              profile_snapshot=profile_snapshot or {})
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


def test_collection_fence_outlives_a_long_native_research_step(lane):
    class NativeLengthWorkflow(ScriptedWorkflow):
        def step(self, principal, ident):
            self.clock.sleep(901)
            # A second job cannot take another specimen after the old 300 s
            # fence would have expired, while a valid native step continues.
            assert fence(lane, holder="exec-b").acquire() is None
            return super().step(principal, ident)

    queued(lane.repository, "native-long", minutes=30)
    workflow = NativeLengthWorkflow(lane.repository, lane.clock)
    summary = worker(lane.repository, workflow, lane.clock).run()
    assert summary["processed"] == ["native-long"]
    assert fence(lane, holder="exec-b").acquire() is not None


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
            self.clock.sleep(3661)  # Past the task-covering fence; another execution takes over.
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
        # A secret stored with a trailing newline reaches the job as-is.
        ({"SPECIMEN_WORKER_ACTOR_UID": "worker\n"}, "SPECIMEN_WORKER_ACTOR_UID"),
        ({"SPECIMEN_WORKER_ACTOR_UID": " worker"}, "SPECIMEN_WORKER_ACTOR_UID"),
        ({"SPECIMEN_WORKER_ACTOR_UID": "wor\x00ker"}, "SPECIMEN_WORKER_ACTOR_UID"),
        ({"SPECIMEN_WORKER_ACTOR_UID": "w" * 129}, "SPECIMEN_WORKER_ACTOR_UID"),
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


@pytest.mark.parametrize(
    "blocker", ["lane_run_not_progressing", "lane_handover_without_progress"]
)
def test_the_drains_blocks_are_retried_by_the_operator_action(tmp_path, blocker):
    import test_lane_trigger as trigger

    dispatcher = trigger.RecordingDispatcher()
    client = trigger.lane_client(tmp_path, dispatcher=dispatcher)
    specimen_id = trigger.intake(client)["specimen_id"]
    reviewer = Principal(user_id=trigger.USER, scope=trigger.SCOPE, role="reviewer")
    repository = SQLiteRepository(tmp_path / "state.sqlite3")
    DrainWorker(
        repository, None, trigger.USER, lambda user: [], execution_id="exec-a"
    )._block(reviewer, specimen_id, blocker)
    run = trigger.stored(tmp_path, specimen_id).run
    assert (run.stage, run.blocker) == ("processing_blocked", blocker)
    response = trigger.action(client, specimen_id, "retry", "retry-" + blocker)
    assert response.status_code == 200, response.text
    run = trigger.stored(tmp_path, specimen_id).run
    assert (run.stage, run.blocker) == ("pending", None)
    assert dispatcher.calls == 2


# The production drain composition (worker.py 737-744) over offline stand-ins:
# the actual RegisteredNativeDrainWorkflow and NativeResearchWorkflow, the
# ordinary path up to the plan boundary, and the native worker's outcome. Each run pins the published profile, which
# names the harness route.
TEN = tuple(f"subject_{n}" for n in range(105526321, 105526331))


def harness_profile():
    from specimen_digitization.application.collection_profiles import published_registry

    return published_registry().profiles[0].model_dump(mode="json")


class Admission:
    def __init__(self):
        self.admitted = []

    def admit(self, specimen):
        self.admitted.append(specimen.id)


class Ordinary:
    """The ordinary producer path, which hands over at the plan boundary."""

    def __init__(self, repository, *, at_plan=False):
        self.repository, self.admission = repository, Admission()
        self.at_plan = at_plan  # The ordinary stages are already complete.

    def next_step(self, run):
        return "plan" if self.at_plan or run.stage == "plan" else "segment"

    def step(self, principal, ident):
        specimen = self.repository.get(principal.scope, ident)
        specimen.run.stage = "plan"
        return self.repository.save(
            principal, specimen, specimen.version, f"ordinary:{ident}", ident
        )


class NativeLane:
    """The native research worker, offline."""

    def __init__(self, repository, holds=None, *, failure=None, refusals=None):
        self.repository, self.holds, self.failure = repository, holds or {}, failure
        self.refusals = refusals or {}  # One record's own open() refusal.
        self.runs = []

    async def run_registered(self, principal, ident, *, owner):
        self.runs.append(ident)
        if self.failure is not None:
            raise self.failure
        if ident in self.refusals:
            raise self.refusals[ident]
        scope = ResearchScope(
            organization_id=ORG,
            collection_id=COLLECTION,
            specimen_id=ident,
            job_id="offline-job",
            generation=0,
            input_digest="0" * 64,
            profile_digest="0" * 64,
        )
        if ident in self.holds:
            return NativeResearchWorkerOutcomeV2(
                scope=scope, status="blocked", reason_code=self.holds[ident]
            )
        # Stands in for the canonical publication's own save.
        specimen = self.repository.get(principal.scope, ident)
        specimen.run.stage, specimen.run.disposition = "finalized", Disposition.REVIEW
        self.repository.save(
            principal, specimen, specimen.version, f"publish:{ident}", ident
        )
        return NativeResearchWorkerOutcomeV2(scope=scope, status="completed")


def drain_the_ten(lane, native, *, supervised=True, at_plan=False, provision=None):
    profile = harness_profile()
    for minutes, ident in zip(range(50, 40, -1), TEN):
        queued(lane.repository, ident, minutes=minutes, profile_snapshot=profile)
    workflow = RegisteredNativeDrainWorkflow(
        NativeResearchWorkflow(
            Ordinary(lane.repository, at_plan=at_plan), native, provision=provision
        )
    )
    drain = worker(lane.repository, workflow, lane.clock)
    if not supervised:
        return drain.run(stop=None)
    with WorkerDeadline(time.monotonic() + 600).scope():
        return drain.run(stop=None)


@pytest.mark.parametrize(
    ("reason_code", "blocker"),
    [
        ("accepted_output_proof_unavailable", "accepted_output_proof_unavailable"),
        ("research_retry_not_completed", "research_retry_not_completed"),
        (
            "research_worker_custody_requires_reconciliation",
            "research_worker_custody_requires_reconciliation",
        ),
        (None, "native_research_operational_hold"),
    ],
)
def test_a_held_record_is_blocked_and_the_later_records_are_drained(
    lane, reason_code, blocker
):
    native = NativeLane(lane.repository, {TEN[0]: reason_code})
    summary = drain_the_ten(lane, native)
    assert summary["status"] == "drained"
    assert summary["processed"] == list(TEN)
    assert native.runs == list(TEN)
    held = lane.repository.get(SCOPE, TEN[0])
    assert (held.run.stage, held.run.blocker, held.run.disposition) == (
        "processing_blocked",
        blocker,
        None,
    )
    assert (held.audit[-1].action, held.audit[-1].reason) == ("lane_block", blocker)
    for ident in TEN[1:]:
        run = lane.repository.get(SCOPE, ident).run
        assert (run.stage, run.disposition) == ("finalized", Disposition.REVIEW)
    # Nothing is left due, so a later execution does not step the held record
    # again. A started run's due time is its last save, on the real clock.
    later = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert lane.repository.oldest_due(SCOPE, later, limit=10) == []
    assert fence(lane).read()["holder"] is None


class PublishesThenHolds(NativeLane):
    """A save leaves the record stopped, then the worker's blocked outcome follows.

    The default is a publication's own save: canonical_materialization_v2 saves a
    run whose fields still wait on a source as processing_blocked, with no blocker."""

    def __init__(self, repository, holds, *, blocker=None, stage="processing_blocked"):
        super().__init__(repository, holds)
        self.blocker, self.stage = blocker, stage

    async def run_registered(self, principal, ident, *, owner):
        if ident in self.holds:
            specimen = self.repository.get(principal.scope, ident)
            specimen.run.stage, specimen.run.blocker = self.stage, self.blocker
            self.repository.save(principal, specimen, specimen.version, f"publish:{ident}", ident)
        return await super().run_registered(principal, ident, owner=owner)


def test_a_hold_after_a_publication_blocked_the_record_is_recorded_and_logged(lane, caplog):
    code = "accepted_output_proof_unavailable"
    native = PublishesThenHolds(lane.repository, {TEN[2]: code})
    with caplog.at_level(logging.WARNING, logger="specimen_digitization.application.lane_worker"):
        summary = drain_the_ten(lane, native)
    assert summary["status"] == "drained"
    assert summary["processed"] == list(TEN)
    held = lane.repository.get(SCOPE, TEN[2])
    # The publication's save blocked the record; the hold's code reaches it too.
    assert (held.run.stage, held.run.blocker, held.run.disposition) == ("processing_blocked", code, None)
    assert (held.audit[-1].action, held.audit[-1].reason) == ("lane_block", code)
    # The drain's own not-progressing block does not replace it.
    assert [event.reason for event in held.audit if event.action == "lane_block"] == [code]
    # The log names the code and the record's last six characters, nothing else.
    lines = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert lines == [f"record held by the drain: {code} (record ...{TEN[2][-6:]})"]
    assert TEN[2] not in caplog.text
    for ident in TEN[:2] + TEN[3:]:
        run = lane.repository.get(SCOPE, ident).run
        assert (run.stage, run.disposition) == ("finalized", Disposition.REVIEW)


@pytest.mark.parametrize("blocker", ["external_outcome_unknown", "pilot_evidence_review_required"])
def test_a_hold_keeps_the_blocker_an_already_blocked_record_names(lane, blocker):
    native = PublishesThenHolds(
        lane.repository, {TEN[0]: "accepted_output_proof_unavailable"}, blocker=blocker
    )
    drain_the_ten(lane, native)
    held = lane.repository.get(SCOPE, TEN[0])
    assert (held.run.stage, held.run.blocker) == ("processing_blocked", blocker)
    assert "lane_block" not in [event.action for event in held.audit]


@pytest.mark.parametrize("stage", ["finalized", "paused", "cancelled"])
def test_a_hold_does_not_touch_a_run_that_has_stopped_another_way(lane, stage):
    native = PublishesThenHolds(
        lane.repository, {TEN[0]: "accepted_output_proof_unavailable"}, stage=stage
    )
    drain_the_ten(lane, native)
    held = lane.repository.get(SCOPE, TEN[0])
    assert (held.run.stage, held.run.blocker) == (stage, None)
    assert "lane_block" not in [event.action for event in held.audit]


@pytest.mark.parametrize("published_stage", [None, "processing_blocked", "finalized"])
def test_unknown_native_publication_preserves_the_original_canonical_snapshot(
    lane, published_stage
):
    class PublicationTimeout(NativeLane):
        async def run_registered(self, principal, ident, *, owner):
            if ident == TEN[0]:
                current = self.repository.get(principal.scope, ident)
                if published_stage is not None:
                    current.run.stage = published_stage
                    current = self.repository.save(
                        principal, current, current.version, "native-partial-save", ident
                    )
                self.retained = current.model_dump(mode="json")
            return await super().run_registered(principal, ident, owner=owner)

    code = "native_publication_requires_reconciliation"
    native = PublicationTimeout(lane.repository, {TEN[0]: code})
    with pytest.raises(OperationalBlock, match=f"^{code}$"):
        drain_the_ten(lane, native, at_plan=True)

    # Keep the exact last authoritative snapshot, whether the native request
    # committed before its response was lost or failed before changing Q.
    retained = lane.repository.get(SCOPE, TEN[0])
    assert retained.model_dump(mode="json") == native.retained
    assert "lane_block" not in [event.action for event in retained.audit]
    assert native.runs == [TEN[0]]
    assert all(lane.repository.get(SCOPE, ident).run.stage == "pending" for ident in TEN[1:])
    assert fence(lane).read()["holder"] is None


def test_the_drains_stall_blocks_leave_a_blocked_record_as_it_is(lane):
    # Only a record's own hold is recorded on a run that is already blocked.
    queued(lane.repository, TEN[0], minutes=5, stage="processing_blocked")
    drain = worker(lane.repository, None, lane.clock)
    for reason in ("lane_run_not_progressing", "lane_handover_without_progress"):
        drain._block(principal(), TEN[0], reason)
    held = lane.repository.get(SCOPE, TEN[0])
    assert (held.run.stage, held.run.blocker) == ("processing_blocked", None)
    assert "lane_block" not in [event.action for event in held.audit]


@pytest.mark.parametrize(
    ("site", "refusal"),
    [
        # open(): the run's job was pinned before the committed pins changed,
        # and a job is never re-pinned (production_runtime.py).
        ("open", HeldUnknown("research_committed_pins_changed")),
        # provision(): the run is not one provisioning accepts (provisioning.py).
        ("provision", StaleWork("research_provision_run_unavailable")),
        # provision(): the run's research state or job exists with other pins
        # or allowance (provisioning.py).
        ("provision", HeldUnknown("research_provision_state_conflict")),
        # provision(): the connector refused this specimen's binding row.
        ("provision", HeldUnknown("research_provision_registration_refused")),
        # open(): the run's own research allowance (one state document per run)
        # is halted, or has no headroom left (production_runtime.py).
        ("open", HeldUnknown("research_live_admission_unqualified")),
        ("open", HeldUnknown("research_program_headroom_unavailable")),
    ],
)
def test_a_runs_own_refusal_holds_that_record_and_the_drain_goes_on(
    lane, site, refusal
):
    code = str(refusal)
    refusals = {TEN[0]: refusal} if site == "open" else None
    native = NativeLane(lane.repository, refusals=refusals)
    provisioned = []

    async def provision(principal, specimen):
        provisioned.append(specimen.id)
        if site == "provision" and specimen.id == TEN[0]:
            raise refusal

    summary = drain_the_ten(lane, native, provision=provision)
    assert summary["status"] == "drained"
    assert summary["processed"] == list(TEN)
    assert provisioned == list(TEN)
    assert native.runs == (list(TEN) if site == "open" else list(TEN[1:]))
    held = lane.repository.get(SCOPE, TEN[0])
    assert (held.run.stage, held.run.blocker, held.run.disposition) == (
        "processing_blocked",
        code,
        None,
    )
    assert (held.audit[-1].action, held.audit[-1].reason) == ("lane_block", code)
    for ident in TEN[1:]:
        run = lane.repository.get(SCOPE, ident).run
        assert (run.stage, run.disposition) == ("finalized", Disposition.REVIEW)
    later = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert lane.repository.oldest_due(SCOPE, later, limit=10) == []
    assert fence(lane).read()["holder"] is None


REFUSED = "00000000-0000-4000-8000-0000000000aa"


def parsed_request(ident, minutes):
    """A requested harness-routed run whose label reading is parsed, so
    provisioning accepts it once the ordinary chain hands it over at plan."""
    asset = Asset(sha256="a" * 64, blob_ref="a" * 64 + ":1", media_type="image/jpeg",
        size_bytes=10, width=100, height=100, filename="fixture.jpeg", uploader="fixture",
        sensitive=False)
    region = Region(asset_id=asset.id, x=0, y=0, width=100, height=100, order=0,
        method="fixture", version="fixture")
    reading = Observation(region_id=region.id, route_id="handwriting-qwen",
        model_id="fixture-model", provider="fixture", prompt_version="b" * 64,
        input_sha256="c" * 64, input_asset_id=asset.id, literal_text="country: Kenya",
        raw_ref="d" * 64 + ":2", raw_sha256="d" * 64)
    transcript = Transcript(region_id=region.id, text=reading.literal_text,
        observation_ids=[reading.id], alternatives=[reading.literal_text], resolved=True,
        decision_kind="identical_readings", selected_observation_id=reading.id,
        handoffs=[ReaderHandoff(observation_id=reading.id, role="decided_transcript",
            handed_text=reading.literal_text)])
    from specimen_digitization.application.collection_profiles import published_registry

    profile = published_registry().profiles[0]
    run = Run(profile=Profile(id=profile.id, version=profile.version,
        routes=tuple(profile.model_routes)), regions=[region], observations=[reading],
        transcripts=[transcript], profile_snapshot=profile.model_dump(mode="json"),
        profile_registry_version="registry-1")
    Workflow.parse(run, asset.id)
    run.dependencies = {"profile_snapshot_sha256": canonical_digest(run.profile_snapshot),
        "profile_registry_version": "registry-1"}
    run.stage, run.queued_at = "pending", (START - timedelta(minutes=minutes)).isoformat()
    return Specimen(id=ident, scope=SCOPE, run=run, asset=asset,
        created_at=(START - timedelta(hours=1)).isoformat())


class ConnectorResponse:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class RefusingConnector:
    """The Data Connect calls provisioning makes, offline.

    The snapshot read and the base record rows are local. The binding writer
    posts through ``session``: no binding is current, and
    RegisterCanonicalResearchBindingV2 answers with the GraphQL errors of a
    registration the connector does not admit (its count check fails).
    """

    variables = staticmethod(SqlConnectRepository.variables)
    url = "https://dataconnect.invalid/v1/projects/p/locations/l/services/s/connectors/c"

    def __init__(self, repository):
        self.repository, self.session, self.posts = repository, self, []

    def execute(self, operation, variables, mutation=False):
        assert operation == "GetSnapshot"
        specimen = self.repository.get(SCOPE, variables["id"])
        assert specimen.version == variables["revision"]
        snapshot = specimen.model_dump(mode="json")
        return {"specimenSnapshot": {"revision": specimen.version, "snapshot": snapshot,
            "sha256": canonical_digest(snapshot), "contractVersion": "fixture"}}

    def locate(self, ref):
        sha, _, generation = ref.partition(":")
        return Blob("offline", sha, generation)

    def _sized(self, ref):
        return 64

    def _insert(self, operation, variables):
        pass

    def post(self, url, json=None, timeout=None):
        operation = json["operationName"]
        self.posts.append(operation)
        if operation == "GetCanonicalResearchBindingV2":
            return ConnectorResponse({"data": {"organizationMember": {"active": True},
                "collectionMember": {"active": True, "role": "manager",
                    "canViewSensitive": False},
                "specimen": {"sensitive": False}, "binding": None}})
        assert operation == "RegisterCanonicalResearchBindingV2"
        return ConnectorResponse({"errors": [{"message": "research registration unavailable",
            "extensions": {"code": "FAILED_PRECONDITION"}}]})


def test_a_registration_the_connector_refuses_holds_that_record_and_the_drain_goes_on(
    lane, tmp_path
):
    # The first request goes through the production provisioning and binding
    # writer. The worker is a manager, a role the connector registers for, so
    # the registration reaches the connector, whose refusal arrives as GraphQL
    # errors. The ten requests after it proceed.
    lane.repository.create(principal(), parsed_request(REFUSED, 51), "queue:refused", REFUSED)
    profile = harness_profile()
    for minutes, ident in zip(range(50, 40, -1), TEN):
        queued(lane.repository, ident, minutes=minutes, profile_snapshot=profile)
    connector = RefusingConnector(lane.repository)
    backend = SqliteStateBackend(tmp_path / "research-state.sqlite")
    backend.grant(DurabilityScope(ORG, COLLECTION, REFUSED, "membership", 1, WORKER, False),
        role="manager")
    provisioned = []

    async def fresh_member(principal, sensitive):
        assert principal.role == "manager" and sensitive is False

    async def provision(principal, specimen):
        provisioned.append(specimen.id)
        if specimen.id == REFUSED:
            await provisioning.provision(connector, principal, specimen, actor_uid=WORKER,
                verify_access=fresh_member, state_backend=backend)

    native = NativeLane(lane.repository)
    workflow = RegisteredNativeDrainWorkflow(
        NativeResearchWorkflow(Ordinary(lane.repository), native, provision=provision)
    )
    drain = worker(lane.repository, workflow, lane.clock, role="manager")
    token = actor_uid.set(WORKER)
    try:
        with WorkerDeadline(time.monotonic() + 600).scope():
            summary = drain.run(stop=None)
    finally:
        actor_uid.reset(token)
    code = "research_provision_registration_refused"
    assert summary["status"] == "drained"
    assert summary["processed"] == [REFUSED, *TEN]
    assert provisioned == [REFUSED, *TEN] and native.runs == list(TEN)
    assert connector.posts == ["GetCanonicalResearchBindingV2",
        "RegisterCanonicalResearchBindingV2"]
    held = lane.repository.get(SCOPE, REFUSED)
    assert (held.run.stage, held.run.blocker, held.run.disposition) == (
        "processing_blocked",
        code,
        None,
    )
    assert (held.audit[-1].action, held.audit[-1].reason) == ("lane_block", code)
    for ident in TEN:
        run = lane.repository.get(SCOPE, ident).run
        assert (run.stage, run.disposition) == ("finalized", Disposition.REVIEW)
    later = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert lane.repository.oldest_due(SCOPE, later, limit=11) == []
    assert fence(lane).read()["holder"] is None


def test_an_unrelated_registration_error_still_ends_the_drain(lane, tmp_path, monkeypatch):
    # Only the connector's refusal codes are this record's hold. Any other code
    # from the registration call is the drain's systemic stop, as before.
    lane.repository.create(principal(), parsed_request(REFUSED, 51), "queue:refused", REFUSED)
    profile = harness_profile()
    for minutes, ident in zip(range(50, 40, -1), TEN):
        queued(lane.repository, ident, minutes=minutes, profile_snapshot=profile)
    connector = RefusingConnector(lane.repository)
    backend = SqliteStateBackend(tmp_path / "research-state.sqlite")
    backend.grant(DurabilityScope(ORG, COLLECTION, REFUSED, "membership", 1, WORKER, False),
        role="manager")

    async def unrelated(self, *args, **kwargs):
        raise PublicationUnavailable("native_v2_owner_policy_pin_unproved")

    monkeypatch.setattr(SqlConnectCanonicalResearchWriterV2, "register_current_binding", unrelated)

    async def fresh_member(principal, sensitive):
        assert principal.role == "manager" and sensitive is False

    async def provision(principal, specimen):
        await provisioning.provision(connector, principal, specimen, actor_uid=WORKER,
            verify_access=fresh_member, state_backend=backend)

    native = NativeLane(lane.repository)
    workflow = RegisteredNativeDrainWorkflow(
        NativeResearchWorkflow(Ordinary(lane.repository), native, provision=provision)
    )
    drain = worker(lane.repository, workflow, lane.clock, role="manager")
    token = actor_uid.set(WORKER)
    try:
        with WorkerDeadline(time.monotonic() + 600).scope():
            with pytest.raises(OperationalBlock, match="^native_research_admission_or_binding_unavailable$"):
                drain.run(stop=None)
    finally:
        actor_uid.reset(token)
    assert native.runs == []
    assert lane.repository.get(SCOPE, REFUSED).run.blocker != "research_provision_registration_refused"


def test_a_hold_on_a_runs_first_step_keeps_its_own_blocker(lane):
    # No step saved before the hold, so the drain also takes the run as not
    # progressing; the hold's blocker stays the one recorded.
    held = TEN[4]
    native = NativeLane(lane.repository, {held: "research_worker_custody_requires_reconciliation"})
    summary = drain_the_ten(lane, native, at_plan=True)
    assert summary["status"] == "drained"
    assert native.runs == list(TEN)
    run = lane.repository.get(SCOPE, held).run
    assert (run.stage, run.blocker) == (
        "processing_blocked",
        "research_worker_custody_requires_reconciliation",
    )
    actions = [event.action for event in lane.repository.get(SCOPE, held).audit]
    assert actions.count("lane_block") == 1
    assert [
        lane.repository.get(SCOPE, ident).run.disposition for ident in TEN if ident != held
    ] == [Disposition.REVIEW] * 9


@pytest.mark.parametrize(
    ("change", "error", "message"),
    [
        # Configuration: the research harness switch is off.
        (
            {"failure": PermissionError("research_harness_switch_off")},
            OperationalBlock,
            "native_research_admission_or_binding_unavailable",
        ),
        # Authorization: the run's live research authority is refused.
        (
            {"failure": PermissionError("research_live_authority_required")},
            OperationalBlock,
            "native_research_admission_or_binding_unavailable",
        ),
        # Authorization: the native run's access check refuses.
        (
            {"failure": PermissionError("research_worker_access_denied")},
            OperationalBlock,
            "native_research_admission_or_binding_unavailable",
        ),
        # Storage: the research store's outcome is unknown.
        (
            {"failure": HeldUnknown("research_store_unavailable")},
            OperationalBlock,
            "native_research_admission_or_binding_unavailable",
        ),
        # Storage: the connection fails.
        ({"failure": ConnectionError("sql_unavailable")}, ConnectionError, "sql_unavailable"),
    ],
)
def test_a_systemic_failure_still_ends_the_execution(lane, change, error, message):
    native = NativeLane(lane.repository, **change)
    with pytest.raises(error, match=f"^{message}$"):
        drain_the_ten(lane, native)
    first = lane.repository.get(SCOPE, TEN[0]).run
    assert first.stage != "processing_blocked" and first.blocker is None
    assert native.runs in ([], [TEN[0]])
    assert [lane.repository.get(SCOPE, ident).run.stage for ident in TEN[1:]] == [
        "pending"
    ] * 9
    assert fence(lane).read()["holder"] is None


def test_an_unsupervised_drain_still_ends_the_execution(lane):
    native = NativeLane(lane.repository)
    with pytest.raises(OperationalBlock, match="^native_research_worker_supervisor_required$"):
        drain_the_ten(lane, native, supervised=False)
    assert native.runs == []
    assert [lane.repository.get(SCOPE, ident).run.stage for ident in TEN] == [
        "pending"
    ] * 10
    assert fence(lane).read()["holder"] is None
