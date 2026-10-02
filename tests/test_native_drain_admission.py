"""Actual native drain adapter over offline authority/native-read boundaries.

No live authority installation, provider, blob, IAM or SQL acceptance is implied.
"""
from types import SimpleNamespace
import time

import pytest

from specimen_digitization.application.domain import Principal, Scope
from specimen_digitization.application.native_drain import (
    RegisteredNativeDrainWorkflow, compose_registered_native_drain,
)
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.application.worker_deadline import WorkerDeadline
from specimen_digitization.research_harness.persistence import DurabilityScope, HeldUnknown
from specimen_digitization.research_harness.workflow_bridge import NativeResearchWorkflow

ORG = "00000000-0000-4000-8000-000000000001"
COLLECTION = "00000000-0000-4000-8000-000000000002"
TEN = tuple(f"specimen-{n}" for n in range(321, 331))


def test_direct_cli_missing_installed_admission_refuses_before_factory_or_work():
    ordinary = SimpleNamespace(admission=None)
    with pytest.raises(OperationalBlock, match="legacy_import_protected_authority_origin_unavailable"):
        compose_registered_native_drain(ordinary, repository=object())


@pytest.mark.parametrize("ids,evidence", [(TEN[:-1], False), (TEN, True)])
def test_no_expanded_or_draft_cohort_can_mount_native_drain(ids, evidence):
    ordinary = SimpleNamespace(admission=SimpleNamespace(
        bindings={i:object() for i in ids}, launch=SimpleNamespace(evidence_only=evidence)))
    with pytest.raises(OperationalBlock, match="native_drain_original_ten_admission_required"):
        compose_registered_native_drain(ordinary, repository=object())


def scenario(*, authority=False, remaining=1):
    calls = []
    principal = Principal(user_id="offline-reviewer", role="reviewer",
        scope=Scope(organization_id=ORG, collection_id=COLLECTION))
    specimen = SimpleNamespace(run=SimpleNamespace(stage="parse", dependencies={}))
    class Repository:
        def get(self, scope, ident):
            calls.append("get")
            return specimen
    class Admission:
        def admit(self, value):
            assert value is specimen
            calls.append("original_ten_admit")
    class Store:
        def require_live_authority(self, scope):
            calls.append("protected_authority")
            if not authority:
                raise HeldUnknown("synthetic_missing_protected_origin")
        def budget(self, scope):
            calls.append("budget")
            return {"remaining_micro_usd":remaining}
    bound = DurabilityScope(ORG, COLLECTION, TEN[0], "offline-job", 1, principal.user_id, False)
    class Binding:
        def durability_scope(self, caller):
            assert caller is principal
            return bound
    class Discovery:
        async def binding(self, caller, ident):
            calls.append("native_binding")
            return Binding()
        def mutable_store(self, binding):
            return Store()
    ordinary = SimpleNamespace(repository=Repository(), admission=Admission())
    ordinary.next_step = lambda run: "parse"
    def step(caller, ident):
        calls.append("ordinary_step")
        return specimen
    ordinary.step = step
    native_worker = SimpleNamespace(runtime_factory=SimpleNamespace(discovery=Discovery()))
    mounted = RegisteredNativeDrainWorkflow(NativeResearchWorkflow(
        ordinary, native_worker, approved_specimen_ids=TEN))
    return mounted, principal, specimen, calls


def test_native_missing_authority_stops_before_ordinary_paid_step():
    workflow, principal, _, calls = scenario()
    with WorkerDeadline(time.monotonic()+30).scope():
        with pytest.raises(OperationalBlock, match="native_drain_protected_admission_unavailable"):
            workflow.step(principal, TEN[0])
    assert calls == ["get", "original_ten_admit", "native_binding", "protected_authority"]


@pytest.mark.parametrize("remaining", [None, True, 0, -1, 0.5])
def test_unknown_or_exhausted_native_headroom_never_calls_ordinary_step(remaining):
    workflow, principal, _, calls = scenario(authority=True, remaining=remaining)
    with WorkerDeadline(time.monotonic()+30).scope():
        with pytest.raises(OperationalBlock, match="native_drain_protected_admission_unavailable"):
            workflow.step(principal, TEN[0])
    assert "ordinary_step" not in calls


def test_proved_offline_transport_path_retains_the_original_parse_boundary():
    workflow, principal, specimen, calls = scenario(authority=True)
    with WorkerDeadline(time.monotonic()+30).scope():
        assert workflow.step(principal, TEN[0]) is specimen
    assert calls.index("protected_authority") < calls.index("budget") < calls.index("ordinary_step")
    # The transport fixture does not supply a real installed ledger authority.


def test_outside_original_cohort_never_reads_native_or_ordinary_record():
    workflow, principal, _, calls = scenario(authority=True)
    with WorkerDeadline(time.monotonic()+30).scope():
        with pytest.raises(PermissionError, match="outside_approved_cohort"):
            workflow.step(principal, "specimen-331")
    assert calls == []


def test_unsupervised_drain_cannot_read_or_dispatch():
    workflow, principal, _, calls = scenario(authority=True)
    with pytest.raises(OperationalBlock, match="worker_supervisor_required"):
        workflow.step(principal, TEN[0])
    assert calls == []


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
    result = ledger.reserve(12_000_000, 1, specimen_id=TEN[0], run_id="r", step="segment", attempt=1)
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
    def flush(*, shutdown):
        assert shutdown is True
        assert current_deadline() is owned_deadline[0]
        flushed.append("same_original_deadline")
        return {"configured": False, "complete": True}
    monkeypatch.setattr(worker, "_execute_drain", execute)
    monkeypatch.setattr(observability, "flush_production_observability", flush)
    worker._run_drain(SimpleNamespace(max_seconds=601, check_config=False))
    assert seen == ["configured_inside_original_deadline"]
    assert flushed == ["same_original_deadline"]
