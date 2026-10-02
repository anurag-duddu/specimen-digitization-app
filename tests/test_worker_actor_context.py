"""Worker helpers own actor tokens; offline callbacks prove binding and cleanup."""

import contextvars
from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from specimen_digitization.application import worker
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.production import actor_uid
from specimen_digitization.application.worker_deadline import current_deadline

WORKER = "bounded-worker-fixture"
SCOPE = Scope(organization_id="11111111-1111-4111-8111-111111111111",
              collection_id="22222222-2222-4222-8222-222222222222")
TEN = tuple(SimpleNamespace(specimen_id=f"specimen-{n}") for n in range(321, 331))


def caller_context(earlier_actor, operation):
    # A fresh Context exercises the genuinely unbound default. This is a local
    # regression harness, not an autouse reset of the suite's caller identity.
    def call():
        assert actor_uid.get() is None
        assert actor_uid not in contextvars.copy_context()
        if earlier_actor is None:
            result = operation()
            assert actor_uid not in contextvars.copy_context()
            return result
        token = actor_uid.set(earlier_actor)
        try:
            result = operation()
            assert actor_uid in contextvars.copy_context()
            assert actor_uid.get() == earlier_actor
            return result
        finally:
            actor_uid.reset(token)
    return contextvars.Context().run(call)


@pytest.mark.parametrize("earlier_actor", [None, "earlier-verified-reviewer"])
@pytest.mark.parametrize("outcome", ["success", "membership_failure", "clock_failure"])
def test_polling_tick_restores_caller_and_keeps_callback_principal(earlier_actor, outcome):
    observed = []
    def observe(label):
        observed.append((label, actor_uid.get()))
        assert actor_uid.get() == WORKER
    def clock():
        observe("clock")
        if outcome == "clock_failure":
            raise RuntimeError("offline clock failure")
        return "2026-10-01T00:00:00+00:00"
    def memberships(uid):
        observe("memberships")
        assert uid == WORKER
        if outcome == "membership_failure":
            raise RuntimeError("offline membership failure")
        return [dict(SCOPE.model_dump(), role="reviewer")]
    class Repository:
        def document(self, scope, kind, ident):
            observe("cursor")
            assert scope == SCOPE and kind == "worker_cursor"
            return {"revision": 0, "cutoff": clock(), "after_id": None}
        def due_page(self, scope, cutoff, after, size):
            observe("discovery")
            assert scope == SCOPE and after is None and size == 25
            return SimpleNamespace(items=[SimpleNamespace(
                specimen_id=TEN[0].specimen_id, work_available_at=cutoff)], next_cursor=None)
        def put_document(self, scope, kind, ident, payload, revision):
            observe("cursor_write")
            assert scope == SCOPE and revision == 0 and payload["actor_uid"] == WORKER
    def step(principal, ident):
        observe("step")
        assert principal.user_id == WORKER and principal.scope == SCOPE
        assert principal.role == "reviewer" and ident == TEN[0].specimen_id
    polling = worker.PollingWorker(Repository(), SimpleNamespace(step=step),
                                   WORKER, memberships, clock=clock)
    def operation():
        assert actor_uid.get() == earlier_actor
        if outcome == "clock_failure":
            with pytest.raises(RuntimeError, match="offline clock failure"):
                polling.tick()
        else:
            assert polling.tick() is polling.health
            assert polling.health.attempted == (1 if outcome == "success" else 0)
            assert polling.health.membership_errors == (1 if outcome == "membership_failure" else 0)
        assert actor_uid.get() == earlier_actor
    caller_context(earlier_actor, operation)
    assert observed and all(actor == WORKER for _, actor in observed)
    assert any(label == "step" for label, _ in observed) is (outcome == "success")


@pytest.mark.parametrize("earlier_actor", [None, "earlier-verified-reviewer"])
@pytest.mark.parametrize("outcome", ["success", "step_failure", "stopped"])
def test_pilot_tick_restores_caller_through_dispatch_and_early_return(earlier_actor, outcome):
    observed = []
    def observe(label):
        observed.append(label)
        assert actor_uid.get() == WORKER
    specimen = SimpleNamespace(version=1, run=SimpleNamespace(stage="ingested", blocker=None))
    class Repository:
        def get(self, scope, ident):
            observe("get")
            assert scope == SCOPE and ident == TEN[0].specimen_id
            return specimen
    def memberships(uid):
        observe("memberships")
        assert uid == WORKER
        return [dict(SCOPE.model_dump(), role="reviewer")]
    def step(principal, ident):
        observe("step")
        assert principal.user_id == WORKER and principal.scope == SCOPE
        assert principal.role == "reviewer" and ident == TEN[0].specimen_id
        if outcome == "step_failure":
            raise RuntimeError("offline step failure")
        return specimen
    class Admission:
        launch = SimpleNamespace(scope=SCOPE, specimens=TEN, evidence_only=False)
        def begin_step(self, item):
            observe("begin")
            assert item is specimen
        def note_outcome(self, item, *, completed_dispatch=False):
            observe("ack")
            assert item is specimen and completed_dispatch is True
        def abandon_dispatch(self, ident):
            observe("abandon")
            assert ident == TEN[0].specimen_id
    pilot = worker.PilotWorker(Repository(), SimpleNamespace(step=step), WORKER, memberships, Admission())
    stop = threading.Event()
    if outcome == "stopped":
        stop.set()
    def operation():
        assert actor_uid.get() == earlier_actor
        assert pilot.tick(stop) is pilot.health
        assert actor_uid.get() == earlier_actor
        assert pilot.health.ticks == 1
        assert pilot.health.attempted == (1 if outcome == "success" else 0)
        assert pilot.health.record_errors == (1 if outcome == "step_failure" else 0)
    caller_context(earlier_actor, operation)
    if outcome == "stopped":
        assert observed == []
    else:
        assert "step" in observed and observed[-1] == "abandon"
        assert ("ack" in observed) is (outcome == "success")


@pytest.mark.parametrize("earlier_actor", [None, "earlier-verified-reviewer"])
@pytest.mark.parametrize("outcome", ["success", "save_failure", "membership_exit"])
def test_pilot_summary_restores_caller_after_success_error_and_system_exit(earlier_actor, outcome):
    observed = []
    def observe(label):
        observed.append(label)
        assert actor_uid.get() == WORKER
    specimen = SimpleNamespace(run=SimpleNamespace(stage="finalized"))
    class Repository:
        def get(self, scope, ident):
            observe("get")
            assert scope == SCOPE and ident in {item.specimen_id for item in TEN}
            return specimen
    def memberships(uid):
        observe("memberships")
        assert uid == WORKER
        if outcome == "membership_exit":
            raise SystemExit(7)
        return [dict(SCOPE.model_dump(), role="reviewer")]
    class Admission:
        launch = SimpleNamespace(scope=SCOPE, specimens=TEN, evidence_only=False)
        def binding_matches(self, item):
            observe("binding")
            assert item is specimen
            return True
        def save_summary(self, value):
            observe("save")
            assert value["authorized"] == 10 and value["counts"] == {"finalized": 10}
            if outcome == "save_failure":
                raise RuntimeError("offline summary failure")
            return value
    pilot = worker.PilotWorker(Repository(), object(), WORKER, memberships, Admission())
    def operation():
        assert actor_uid.get() == earlier_actor
        if outcome == "membership_exit":
            with pytest.raises(SystemExit) as caught:
                pilot.result_summary()
            assert caught.value.code == 7
        else:
            result = pilot.result_summary()
            assert result["status"] == ("completed" if outcome == "success" else "blocked")
            assert result["counts"] == {"finalized": 10}
            if outcome == "save_failure":
                assert result["blocker"] == "pilot_summary_persistence_unavailable"
        assert actor_uid.get() == earlier_actor
    caller_context(earlier_actor, operation)
    assert observed[0] == "memberships"
    assert ("save" in observed) is (outcome != "membership_exit")


@pytest.mark.parametrize("earlier_actor", [None, "earlier-verified-reviewer"])
@pytest.mark.parametrize("outcome", ["success", "setup_failure", "worker_exit"])
def test_drain_cli_restores_caller_after_success_early_setup_and_system_exit(
    monkeypatch, earlier_actor, outcome,
):
    from specimen_digitization import observability
    from specimen_digitization.application import lane_worker

    observed, flushes = [], []
    def observe(label):
        observed.append(label)
        assert actor_uid.get() == WORKER
        assert current_deadline() is not None
    class Repository:
        def __init__(self, **endpoint):
            observe("repository")
            assert endpoint == {}
            if outcome == "setup_failure":
                raise RuntimeError("offline repository failure")
        def memberships(self, uid):
            observe("memberships")
            assert uid == WORKER
            return []
    def workflow(repository, blobs, adapters, **registries):
        observe("workflow")
        assert repository.graph_blobs is blobs
        assert registries["profile_registry"].bindings == {}
        assert registries["risk_registry"] is not None
        return "offline-workflow"
    class Drain:
        def __init__(self, repository, flow, uid, memberships, **options):
            observe("drain")
            assert flow == "offline-workflow" and uid == WORKER
            assert memberships.__self__ is repository
            assert 600 < options["deadline_seconds"] <= 601
            assert options["continuation"]().status == "unconfigured"
            assert memberships(uid) == []
        def run(self, stop):
            observe("run")
            assert not stop.is_set()
            if outcome == "worker_exit":
                raise SystemExit(7)
            return {"status": "drained", "processed": []}
    def flush(*, shutdown):
        assert shutdown is True and current_deadline() is not None
        flushes.append(actor_uid.get())
        return {"configured": False, "complete": True}
    monkeypatch.setattr(lane_worker, "drain_settings", lambda env: SimpleNamespace(
        actor_uid=WORKER, bindings={}, worker_job=None))
    monkeypatch.setattr(lane_worker, "DrainWorker", Drain)
    monkeypatch.setattr(worker, "sql_endpoint_from_env", lambda: {})
    monkeypatch.setattr(worker, "SqlConnectRepository", Repository)
    monkeypatch.setattr(worker, "GcsBlobs", object)
    monkeypatch.setattr(worker, "ProductionAdapters", lambda blobs: object())
    monkeypatch.setattr(worker, "Workflow", workflow)
    monkeypatch.setattr("specimen_digitization.application.native_drain.compose_registered_native_drain",
                        lambda ordinary, **kwargs: ordinary)
    monkeypatch.setattr("signal.signal", lambda *args: None)
    monkeypatch.setattr(observability, "configure_production_observability", lambda name: None)
    monkeypatch.setattr(observability, "flush_production_observability", flush)
    def operation():
        assert actor_uid.get() == earlier_actor
        args = SimpleNamespace(max_seconds=601, check_config=False)
        if outcome == "setup_failure":
            with pytest.raises(RuntimeError, match="offline repository failure"):
                worker._run_drain(args)
        elif outcome == "worker_exit":
            with pytest.raises(SystemExit) as caught:
                worker._run_drain(args)
            assert caught.value.code == 7
        else:
            worker._run_drain(args)
        assert actor_uid.get() == earlier_actor
        assert current_deadline() is None
    caller_context(earlier_actor, operation)
    assert observed[0] == "repository"
    assert ("run" in observed) is (outcome != "setup_failure")
    assert flushes == [earlier_actor]


@pytest.mark.parametrize("earlier_actor", [None, "earlier-verified-reviewer"])
@pytest.mark.parametrize("outcome", ["success", "setup_failure", "summary_exit"])
def test_pilot_cli_restores_caller_after_success_early_setup_and_system_exit(
    monkeypatch, earlier_actor, outcome,
):
    from specimen_digitization import observability
    from specimen_digitization.application import worker_launch

    observed = []
    def observe(label):
        observed.append(label)
        assert actor_uid.get() == WORKER
    class Repository:
        def __init__(self, **endpoint):
            observe("repository")
            assert endpoint == {}
            if outcome == "setup_failure":
                raise RuntimeError("offline repository failure")
        def memberships(self, uid):
            observe("memberships")
            assert uid == WORKER
            return []
    class Pilot:
        def __init__(self, repository, flow, uid, memberships, admission):
            observe("pilot")
            assert uid == WORKER and memberships.__self__ is repository
            assert memberships(uid) == []
            self.health = worker.WorkerHealth()
        def tick(self, stop):
            observe("tick")
            assert not stop.is_set()
            self.health.ticks += 1
        def result_summary(self):
            observe("summary")
            return {"status": "incomplete" if outcome == "summary_exit" else "completed"}
    launch = SimpleNamespace(timing=None, evidence_only=False,
                             expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    monkeypatch.setattr(worker, "production_launch", lambda args: launch)
    monkeypatch.setattr(worker, "worker_timing_environment", lambda: None)
    monkeypatch.setenv("SPECIMEN_WORKER_ACTOR_UID", WORKER)
    monkeypatch.setattr(worker, "sql_endpoint_from_env", lambda: {})
    monkeypatch.setattr(worker, "SqlConnectRepository", Repository)
    monkeypatch.setattr(worker, "GcsBlobs", lambda: SimpleNamespace(bucket=SimpleNamespace(name="offline")))
    monkeypatch.setattr(worker, "ProductionAdapters", lambda *args, **kwargs: object())
    monkeypatch.setattr(worker, "Workflow", lambda *args, **kwargs: object())
    monkeypatch.setattr(worker, "PilotWorker", Pilot)
    monkeypatch.setattr(worker_launch, "verify_source_manifest", lambda *args: object())
    monkeypatch.setattr(worker_launch, "sam3_expectations", lambda *args: object())
    monkeypatch.setattr(worker_launch, "PilotAdmission", lambda *args: object())
    monkeypatch.setattr("specimen_digitization.research_harness.workflow_bridge.compose_registered_native_workflow",
                        lambda ordinary, **kwargs: ordinary)
    monkeypatch.setattr("signal.signal", lambda *args: None)
    monkeypatch.setattr(observability, "configure_observability", lambda **kwargs: None)
    def operation():
        assert actor_uid.get() == earlier_actor
        args = SimpleNamespace(mode="production", evidence_only=False, check_config=False,
                               source_manifest=Path("offline-unused"), once=True, max_seconds=601)
        if outcome == "setup_failure":
            with pytest.raises(RuntimeError, match="offline repository failure"):
                worker._run(args)
        elif outcome == "summary_exit":
            with pytest.raises(SystemExit) as caught:
                worker._run(args)
            assert caught.value.code == 2
        else:
            worker._run(args)
        assert actor_uid.get() == earlier_actor
    caller_context(earlier_actor, operation)
    assert observed[0] == "repository"
    assert ("summary" in observed) is (outcome != "setup_failure")
