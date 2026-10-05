"""Offline composition contracts; fake SQL responses are not production proof."""
import asyncio
import time
from dataclasses import replace
from types import ModuleType, SimpleNamespace
import sys

import pytest

from specimen_digitization.application.domain import AuditEvent
from specimen_digitization.application.lane_worker import DrainWorker
from specimen_digitization.application.native_drain import RegisteredNativeDrainWorkflow
from specimen_digitization.application.storage import ReviewDecisionProof
from specimen_digitization.application.worker_deadline import WorkerDeadline
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.research_harness.persistence import HeldUnknown, StaleWork
from specimen_digitization.research_harness.workflow_bridge import NativeResearchWorkflow

from test_derivation_provisioning import queued  # noqa: F401
from test_provisioning import rig, job_scope  # noqa: F401

queue = pytest.importorskip("specimen_digitization.research_harness.derivation_work_queue")


@pytest.fixture
def composed(queued, monkeypatch):
    rig = queued
    repository, specimen, command = rig.repository, rig.specimen, rig.command
    rig.calls, rig.finished = [], False
    rig.error, rig.finish_error, rig.finish_count, rig.finish_due = None, None, 1, None
    rig.verify_error, rig.mismatch_result = None, False
    event = AuditEvent(actor=command.actor_uid, action="review_derive_rest", reason=command.reason,
        before={"revision": command.source_revision, "run_id": command.canonical_run_id},
        after={"request_id": command.id, "input_digest": command.input_digest,
            "requested_fields": [str(key) for key in command.requested_fields]},
        base_revision=command.source_revision, resulting_revision=command.queued_revision)
    specimen.audit.append(event)
    proof = ReviewDecisionProof(specimen.id, event, command.source_revision, command.queued_revision,
        command.source_snapshot_sha256, "f" * 64, "offline-server-save-audit")
    rig.proofs = [proof]
    repository._review_proofs = lambda scope, current: (rig.proofs, None)
    repository.version_info = lambda scope, ident, revision: {"revision": revision,
        "run_id": specimen.run.id, "sha256": "f" * 64 if revision == command.queued_revision else "b" * 64}
    repository.get = lambda scope, ident: specimen.model_copy(deep=True)
    def execute(operation, variables, mutation=False):
        rig.calls.append(operation)
        assert operation == "FinishResearchDerivationV1" and mutation is True
        assert variables["requestId"] == command.id and variables["queuedRevision"] == specimen.version
        if rig.finish_error:
            raise rig.finish_error
        rig.finished = type(rig.finish_count) is int and rig.finish_count == 1 and rig.finish_due is None
        return {"finished": rig.finish_count, "read": {"specimen": {
            "revision": specimen.version, "activeRunId": specimen.run.id,
            "state": "completed", "workAvailableAt": rig.finish_due}}}
    repository.execute = execute
    def forbidden(*args, **kwargs):
        pytest.fail("derivation side work attempted ordinary/model/publication work")
    class Outcome:
        request_id, status, checkpoint_ids, blocked_reason = command.id, "completed", (), None
        def model_dump(self, **kwargs):
            return {"request_id": self.request_id, "status": self.status,
                "checkpoint_ids": list(self.checkpoint_ids), "blocked_reason": self.blocked_reason}
    rig.outcome = Outcome()
    scope = job_scope(rig)
    async def bound_state(principal, ident):
        rig.calls.append("bound_state")
        result = rig.outcome.model_dump()
        if rig.mismatch_result:
            result["status"] = "running"
        return (SimpleNamespace(canonical=SimpleNamespace(record_revision=specimen.version,
                    canonical_run_id=specimen.run.id)),
            SimpleNamespace(program_key="research-run:" + specimen.run.id), scope, None,
            {"dependencies": {"derivation_request_id": command.id, "derivation_result": result}})
    factory = SimpleNamespace(repository=repository, discovery=SimpleNamespace(bound_state=bound_state))
    worker_module = ModuleType("specimen_digitization.research_harness.derivation_worker")
    class DerivationWorker:
        def __init__(self, runtime_factory, *, input_blobs):
            assert runtime_factory is factory and input_blobs is repository.graph_blobs
        def _verify(self, principal, ident):
            rig.calls.append("verify")
            if rig.verify_error:
                raise rig.verify_error
            return SimpleNamespace(command=command, specimen=repository.get(principal.scope, ident))
        async def run_registered(self, principal, ident, *, owner, command):
            rig.calls.append("derive")
            if rig.error:
                raise rig.error
            return rig.outcome
    worker_module.ResearchDerivationWorker = DerivationWorker
    monkeypatch.setitem(sys.modules, worker_module.__name__, worker_module)
    async def provision(principal, current):
        rig.calls.append("provision")
        assert current.version == command.queued_revision
    rig.ordinary = SimpleNamespace(repository=repository, step=forbidden, next_step=lambda run: "plan")
    native = SimpleNamespace(runtime_factory=factory, run_registered=forbidden)
    rig.workflow = NativeResearchWorkflow(rig.ordinary, native, provision=provision)
    rig.step = lambda: rig.workflow.step(rig.principal, specimen.id)
    return rig


def supervised():
    return WorkerDeadline(time.monotonic() + 60).scope()


@pytest.mark.parametrize("stage", ["finalized", "waiting_for_review", "plan"])
@pytest.mark.parametrize("status", ["completed", "blocked"])
def test_terminal_side_work_retires_only_metadata_and_preserves_science(composed, stage, status):
    rig = composed
    rig.specimen.run.stage = stage
    rig.outcome.status = status
    rig.outcome.blocked_reason = "derivation_geolocate_not_successful" if status == "blocked" else None
    before = rig.specimen.model_dump(mode="json")
    with supervised():
        result = rig.step()
    assert result.model_dump(mode="json") == before and rig.finished
    assert rig.workflow.completed_side_work(result) is True
    assert rig.calls == ["verify", "provision", "derive", "bound_state", "FinishResearchDerivationV1"]
    changed = result.model_copy(deep=True)
    changed.version += 1
    assert rig.workflow.completed_side_work(changed) is False
    changed = result.model_copy(deep=True)
    changed.run.blocker = "another_value"
    assert rig.workflow.completed_side_work(changed) is False


@pytest.mark.parametrize("failure", ["proof_missing", "proof_duplicate", "proof_plain_audit", "proof_actor", "proof_reason",
    "proof_revision", "proof_snapshot", "proof_source", "verify", "worker", "running", "wrong_request",
    "journal_mismatch", "finish_count", "finish_bool_count", "finish_due", "finish_transport"])
def test_unknown_or_unproved_work_never_finishes_or_mutates_canonical(composed, failure):
    rig = composed
    if failure == "proof_missing":
        rig.proofs = []
    elif failure == "proof_duplicate":
        rig.proofs *= 2
    elif failure == "proof_plain_audit":
        rig.proofs = [rig.proofs[0].event]
    elif failure in {"proof_actor", "proof_reason"}:
        field = failure.removeprefix("proof_")
        rig.proofs = [replace(rig.proofs[0], event=rig.proofs[0].event.model_copy(update={field: "changed"}))]
    elif failure == "proof_revision":
        rig.proofs = [replace(rig.proofs[0], resulting_revision=999)]
    elif failure == "proof_snapshot":
        rig.proofs = [replace(rig.proofs[0], snapshot_sha256="0" * 64)]
    elif failure == "proof_source":
        rig.proofs = [replace(rig.proofs[0], prior_sha256="0" * 64)]
    elif failure == "verify":
        rig.verify_error = StaleWork("changed during request")
    elif failure == "worker":
        rig.error = HeldUnknown("unknown source send")
    elif failure == "running":
        rig.outcome.status = "running"
    elif failure == "wrong_request":
        rig.outcome.request_id = "0" * 64
    elif failure == "journal_mismatch":
        rig.mismatch_result = True
    elif failure == "finish_count":
        rig.finish_count = 0
    elif failure == "finish_bool_count":
        rig.finish_count = True
    elif failure == "finish_due":
        rig.finish_due = "still due"
    else:
        rig.finish_error = TimeoutError("outcome unknown")
    before = rig.specimen.model_dump(mode="json")
    with supervised(), pytest.raises(OperationalBlock, match="^research_derivation_requires_reconciliation$"):
        rig.step()
    assert rig.specimen.model_dump(mode="json") == before
    assert rig.workflow.completed_side_work(rig.specimen) is False and not rig.finished
    if failure.startswith("proof_") or failure == "verify":
        assert "provision" not in rig.calls and "derive" not in rig.calls


def test_successful_prior_step_cannot_mask_later_unconfirmed_finish(composed):
    with supervised():
        completed = composed.step()
    assert composed.workflow.completed_side_work(completed)
    composed.finish_count = 0
    with supervised(), pytest.raises(OperationalBlock):
        composed.step()
    assert not composed.workflow.completed_side_work(completed)


@pytest.mark.parametrize("change", ["revision", "run"])
def test_historical_command_does_not_intercept_later_ordinary_work(composed, change):
    rig = composed
    rig.specimen.run.stage = "parse"
    if change == "revision":
        rig.specimen.version += 1
    else:
        rig.specimen.run.id = "00000000-0000-4000-8000-000000000055"
    rig.ordinary.next_step = lambda run: "parse"
    rig.ordinary.step = lambda principal, ident: rig.calls.append("ordinary") or rig.specimen
    result = rig.step()
    assert result is rig.specimen and rig.calls == ["ordinary"]
    assert rig.workflow.completed_side_work(result) is False


@pytest.mark.parametrize("stage", ["paused", "cancelled", "processing_blocked"])
def test_command_does_not_bypass_an_existing_lifecycle_hold(composed, stage):
    composed.specimen.run.stage = stage
    with supervised(), pytest.raises(OperationalBlock, match="research_derivation_requires_reconciliation"):
        composed.step()
    assert composed.calls == []


def test_drain_counts_verified_side_work_without_a_canonical_version_increment(composed):
    rig = composed
    drain = DrainWorker(rig.repository, RegisteredNativeDrainWorkflow(rig.workflow),
        rig.principal.user_id, lambda user: [], execution_id="offline-side-work")
    fence = SimpleNamespace(hold=lambda *args: None)
    with supervised():
        result, progressed = drain._step_until_stopped(rig.principal, fence, rig.specimen.id, None)
    assert progressed is True and result == rig.specimen.run and rig.finished


def test_drain_does_not_write_a_block_for_unknown_side_work(composed):
    rig = composed
    rig.finish_error = TimeoutError("unknown finish")
    drain = DrainWorker(rig.repository, rig.workflow, rig.principal.user_id, lambda user: [],
        execution_id="offline-side-work")
    drain._block = lambda *args, **kwargs: pytest.fail("side work must not save canonical block state")
    with supervised(), pytest.raises(OperationalBlock, match="research_derivation_requires_reconciliation"):
        drain._step_until_stopped(rig.principal, SimpleNamespace(hold=lambda *args: None), rig.specimen.id, None)


def test_cancellation_does_not_finish_or_acknowledge_side_work(composed):
    composed.error = asyncio.CancelledError()
    with supervised(), pytest.raises(asyncio.CancelledError):
        composed.step()
    assert "FinishResearchDerivationV1" not in composed.calls
    assert not composed.workflow.completed_side_work(composed.specimen)


def test_unsupervised_command_never_reaches_provisioning_or_worker(composed):
    with pytest.raises(OperationalBlock, match="native_research_worker_supervisor_required"):
        composed.step()
    assert composed.calls == [] and not composed.workflow.completed_side_work(composed.specimen)
