"""The research harness mount over the ordinary drain, with offline stand-ins.

No live provider, blob, IAM or SQL acceptance is implied.
"""
from types import SimpleNamespace
import time

import pytest

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Principal, Scope
from specimen_digitization.application.native_drain import (
    RegisteredNativeDrainWorkflow, compose_registered_native_drain,
)
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.application.worker_deadline import WorkerDeadline
from specimen_digitization.research_harness.native_worker import NativeResearchWorkerOutcomeV2
from specimen_digitization.research_harness.contracts import ResearchScope
from specimen_digitization.research_harness.persistence import HeldUnknown
from specimen_digitization.research_harness.workflow_bridge import NativeResearchWorkflow

ORG = "00000000-0000-4000-8000-000000000001"
COLLECTION = "00000000-0000-4000-8000-000000000002"
SPECIMEN = "00000000-0000-4000-8000-000000000321"
# The published profile names the harness route; a run pins it as its snapshot.
HARNESS = published_registry().profiles[0].model_dump(mode="json")
assert HARNESS["harness_route"] == "harness-deepseek"
# Construction only: the composer's factory keeps the repository's blob bucket.
REPOSITORY = SimpleNamespace(graph_blobs=SimpleNamespace(bucket=object()))


def test_switch_off_leaves_the_ordinary_workflow_in_place():
    ordinary = SimpleNamespace(repository=object())
    for environ in ({}, {"SPECIMEN_RESEARCH_HARNESS": ""}, {"SPECIMEN_RESEARCH_HARNESS": "off"}):
        assert compose_registered_native_drain(ordinary, repository=object(), environ=environ) is ordinary


@pytest.mark.parametrize("value", ["yes", "On", "1"])
def test_an_unknown_switch_value_names_the_setting_not_the_value(value):
    with pytest.raises(ValueError, match="SPECIMEN_RESEARCH_HARNESS") as caught:
        compose_registered_native_drain(SimpleNamespace(), repository=object(),
            environ={"SPECIMEN_RESEARCH_HARNESS": value})
    assert value not in str(caught.value)


def test_switch_on_mounts_research_over_an_ordinary_workflow_without_admission():
    ordinary = SimpleNamespace(repository=object(), admission=None)
    mounted = compose_registered_native_drain(ordinary, repository=REPOSITORY,
        environ={"SPECIMEN_RESEARCH_HARNESS": "on"})
    assert isinstance(mounted, RegisteredNativeDrainWorkflow)
    assert isinstance(mounted.workflow, NativeResearchWorkflow) and mounted.ordinary is ordinary


def test_an_unsupervised_drain_step_reads_nothing():
    workflow, principal, _, calls = scenario(step="segment")
    with pytest.raises(OperationalBlock, match="worker_supervisor_required"):
        RegisteredNativeDrainWorkflow(workflow).step(principal, SPECIMEN)
    assert calls == []
    with WorkerDeadline(time.monotonic()+30).scope():
        RegisteredNativeDrainWorkflow(workflow).step(principal, SPECIMEN)
    assert calls == ["get", "ordinary_step"]


def scenario(*, step="plan", profile=HARNESS, stage="plan", refusal=None, outcome="completed"):
    calls = []
    principal = Principal(user_id="offline-worker", role="operator",
        scope=Scope(organization_id=ORG, collection_id=COLLECTION))
    specimen = SimpleNamespace(id=SPECIMEN, run=SimpleNamespace(stage=stage, dependencies={},
        profile_snapshot=profile))
    class Repository:
        def get(self, scope, ident):
            calls.append("get")
            return specimen
    ordinary = SimpleNamespace(repository=Repository(), admission=None)
    ordinary.next_step = lambda run: step
    def ordinary_step(caller, ident):
        calls.append("ordinary_step")
        return specimen
    ordinary.step = ordinary_step
    class NativeWorker:
        async def run_registered(self, caller, ident, *, owner):
            assert caller is principal and ident == SPECIMEN
            calls.append("native_run")
            if refusal is not None:
                raise refusal
            scope = ResearchScope(organization_id=ORG, collection_id=COLLECTION, specimen_id=ident,
                job_id="offline-job", generation=1, input_digest="0" * 64, profile_digest="0" * 64)
            return NativeResearchWorkerOutcomeV2(scope=scope, status=outcome,
                reason_code="research_retry_not_completed" if outcome == "blocked" else None)
    async def provision(caller, value):
        assert caller is principal and value is specimen
        calls.append("provision")
    mounted = NativeResearchWorkflow(ordinary, NativeWorker(), provision=provision)
    return mounted, principal, specimen, calls


# The run's own refusal keeps its code, so the drain holds that record; any
# other refusal is one code that ends the drain's execution.
@pytest.mark.parametrize("refusal,code", [
    (PermissionError("research_live_authority_required"), "native_research_admission_or_binding_unavailable"),
    (HeldUnknown("research_committed_pins_changed"), "research_committed_pins_changed")])
def test_a_refused_research_open_stops_before_any_ordinary_step(refusal, code):
    workflow, principal, _, calls = scenario(refusal=refusal)
    with WorkerDeadline(time.monotonic()+30).scope():
        with pytest.raises(OperationalBlock, match=f"^{code}$"):
            workflow.step(principal, SPECIMEN)
    assert calls == ["get", "provision", "native_run"]


def test_a_researched_plan_step_provisions_then_runs_and_rereads_the_record():
    workflow, principal, specimen, calls = scenario()
    with WorkerDeadline(time.monotonic()+30).scope():
        assert workflow.step(principal, SPECIMEN) is specimen
    assert calls == ["get", "provision", "native_run", "get"]


def test_a_blocked_research_outcome_names_its_reason():
    workflow, principal, _, calls = scenario(outcome="blocked")
    with WorkerDeadline(time.monotonic()+30).scope():
        with pytest.raises(OperationalBlock, match="^research_retry_not_completed$"):
            workflow.step(principal, SPECIMEN)
    assert "ordinary_step" not in calls


@pytest.mark.parametrize("step,profile", [("parse", HARNESS), ("segment", HARNESS),
    ("plan", {}), ("plan", {**HARNESS, "harness_route": None}),
    ("plan", {**HARNESS, "harness_route": "handwriting-qwen"})])
def test_other_steps_and_runs_without_a_harness_route_stay_ordinary(step, profile):
    workflow, principal, specimen, calls = scenario(step=step, profile=profile)
    assert workflow.step(principal, SPECIMEN) is specimen
    assert calls == ["get", "ordinary_step"]


@pytest.mark.parametrize("stage", ["finalized", "paused", "cancelled", "processing_blocked"])
def test_a_terminal_run_is_returned_untouched(stage):
    workflow, principal, specimen, calls = scenario(stage=stage)
    assert workflow.step(principal, SPECIMEN) is specimen
    assert calls == ["get"]


def test_unsupervised_research_cannot_provision_or_dispatch():
    workflow, principal, _, calls = scenario()
    with pytest.raises(OperationalBlock, match="worker_supervisor_required"):
        workflow.step(principal, SPECIMEN)
    assert calls == ["get"]


def test_missing_legacy_ledger_is_not_created_or_zeroed():
    from specimen_digitization.application.lane_allowance import ProgramLedger, LegacyLedgerUnavailable
    from specimen_digitization.application.storage import Missing
    calls = []
    class Repository:
        def document(self, *args):
            raise Missing("offline absent")
        def put_document(self, *args):
            calls.append("write")
            raise AssertionError("missing original ledger may not be recreated")
    ledger = ProgramLedger(Repository(), Scope(organization_id=ORG, collection_id=COLLECTION))
    with pytest.raises(LegacyLedgerUnavailable):
        ledger.read()
    result = ledger.reserve(12_000_000, 1, specimen_id=SPECIMEN, run_id="r", step="segment", attempt=1)
    assert result.issue == "program_allowance_ledger_unavailable" and result.position is None
    assert calls == []


def test_cli_deadline_starts_before_configuration(monkeypatch):
    from specimen_digitization import observability
    from specimen_digitization.application import worker
    from specimen_digitization.application.worker_deadline import current_deadline
    seen = []
    owned_deadline = []
    flushed = []
    def execute(args, deadline):
        assert current_deadline() is deadline
        assert 0 < deadline.remaining() <= 601
        owned_deadline.append(deadline)
        seen.append("configured_inside_original_deadline")
    def flush(*, shutdown, maximum_millis):
        assert shutdown is True and maximum_millis == observability.FINAL_FLUSH_MILLIS
        assert current_deadline() is owned_deadline[0]
        flushed.append("same_original_deadline")
        return {"configured": False, "complete": True}
    monkeypatch.setattr(worker, "_execute_drain", execute)
    monkeypatch.setattr(observability, "flush_production_observability", flush)
    worker._run_drain(SimpleNamespace(max_seconds=601, check_config=False))
    assert seen == ["configured_inside_original_deadline"]
    assert flushed == ["same_original_deadline"]
