"""What a lease window costs: the lease's length and the worker's reads per publication pass.

Offline stand-ins: test_production_bridge's recording runtime (the worker's own
publication loop) and a real SQLite research store for the lease.
"""
import asyncio
import collections
import inspect
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness import native_worker
from specimen_digitization.research_harness.contracts import FieldKey, FieldResolution, WorkState
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, DurabilityScope, PinnedRuntime, ResearchStore, SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.production_runtime import NativeResearchRuntimeFactory

from test_production_bridge import RESEARCH_SCOPE, TAXON, PublishingRuntime, checkpoint, principal, thread


def resolved(key):
    return checkpoint(FieldResolution(field_key=key, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal="synthetic", evidence_ids=["e-label"],
            evidence_relations={"e-label": "supports"}),
        evidence_ids=("e-label",), reason="synthetic resolved work"))


class CountingRuntime(PublishingRuntime):
    """The publication loop's runtime, counting each state read the worker makes itself."""

    def __init__(self, typed, outbox=None, winners=None):
        super().__init__(typed)
        job, self.reads = self.store.job(None), collections.Counter()
        outbox = {} if outbox is None else outbox

        def read_job(scope):
            self.reads["job"] += 1
            return job

        def read_state(scope):
            self.reads["state"] += 1
            return SimpleNamespace(state={"outbox": outbox})
        self.store = SimpleNamespace(job=read_job, _read=read_state)
        winners = winners or {}

        async def winning_receipt(principal, specimen_id, *, idempotency_key, request_identity_digest):
            return winners.get(idempotency_key)
        self.canonical_service = SimpleNamespace(publish_checkpoint=self._publish, winning_receipt=winning_receipt)


def publish(monkeypatch, runtime, view):
    monkeypatch.setattr(native_worker, "read_accepted_checkpoint_proof",
        lambda store, scope, blobs, checkpoint_id: runtime.proofs.append(checkpoint_id))

    async def prepare(journal, scope, field_key, *, principal, expected_record_revision, blobs):
        runtime.prepared.append((field_key, expected_record_revision))
        return str(field_key)

    async def read_thread(_runtime):
        return view
    monkeypatch.setattr(native_worker, "prepare_native_publication", prepare)
    monkeypatch.setattr(native_worker.NativeResearchWorker, "_thread", staticmethod(read_thread))
    return asyncio.run(native_worker.NativeResearchWorker(None)._publish_committed(
        runtime, principal(), RESEARCH_SCOPE.specimen_id))


def test_a_publication_pass_reads_the_job_and_the_outbox_once_not_once_per_checkpoint(monkeypatch):
    typed = (resolved(FieldKey.CITY), resolved(FieldKey.COUNTRY), resolved(FieldKey.COUNTY),
        resolved(FieldKey.HABITAT), TAXON)
    runtime = CountingRuntime(typed)
    outcome = publish(monkeypatch, runtime, thread(*typed))
    # Before: one job read per checkpoint and one more at the end, one outbox read per checkpoint.
    assert runtime.reads == {"job": 1, "state": 1}
    assert [field for field, _ in runtime.prepared] == [item.field_key for item in typed]
    assert len(outcome.publication_receipt_ids) == 5 and outcome.reason_code is None
    # The record revision every preparation expects is the job's immutable one.
    assert {revision for _, revision in runtime.prepared} == {4}


def test_a_checkpoint_already_published_is_replayed_from_its_pending_guard_not_prepared_again(monkeypatch):
    """The outbox read at the start of the pass still names a retained operation: its winning receipt
    is reused (a restarted or later window walks every earlier checkpoint again)."""
    typed = (resolved(FieldKey.CITY), TAXON)
    guard = {"checkpoint_id": f"native-{FieldKey.TAXON}", "idempotency_key": "a" * 64}
    other = {"checkpoint_id": "native-someone-else", "idempotency_key": "b" * 64}
    outbox = {"publication/1": {"kind": "canonical_publication_required", "guard": guard},
              "publication/2": {"kind": "canonical_publication_required", "guard": other},
              "checkpoint/x": {"kind": "research_field_retry", "guard": guard}}
    winner = SimpleNamespace(causal=SimpleNamespace(receipt_id="receipt-replayed"))
    runtime = CountingRuntime(typed, outbox=outbox, winners={guard["idempotency_key"]: winner})
    outcome = publish(monkeypatch, runtime, thread(*typed))
    assert [field for field, _ in runtime.prepared] == [FieldKey.CITY]
    assert outcome.publication_receipt_ids == ("receipt-city", "receipt-replayed")
    assert runtime.reads == {"job": 1, "state": 1}


def test_two_pending_operations_for_one_checkpoint_are_still_refused(monkeypatch):
    guard = {"checkpoint_id": f"native-{FieldKey.TAXON}", "idempotency_key": "a" * 64}
    outbox = {"publication/1": {"kind": "canonical_publication_required", "guard": guard},
              "publication/2": {"kind": "canonical_publication_required", "guard": dict(guard)}}
    runtime = CountingRuntime((TAXON,), outbox=outbox)
    with pytest.raises(StaleWork, match="native_publication_operation_ambiguous"):
        publish(monkeypatch, runtime, thread(TAXON))
    assert runtime.prepared == []


def test_a_lease_may_be_claimed_for_fifteen_minutes_and_no_longer(tmp_path):
    scope = DurabilityScope("org", "insects", "synthetic", "job", 1, "worker")
    backend = SqliteStateBackend(tmp_path / "state.sqlite")
    backend.grant(scope, can_view_sensitive=True)
    store = ResearchStore(backend, "program")
    store.initialize(scope, BudgetPolicy(10_000))
    store.create_job(scope, PinnedRuntime("a" * 64, {"digest": "b" * 64}, {"version": "v1"},
        {"digest": "c" * 64}, {"route": "r"}, {"max_tokens": 128}, "specialist_harness_v2"), ["taxon"])
    for ttl in (0, 901, 3600):
        with pytest.raises(ValueError, match="Lease TTL must be 1..900 seconds"):
            store.claim(scope, "worker", ttl_seconds=ttl)
    lease = store.claim(scope, "worker", ttl_seconds=900)
    assert lease.expires_at - backend.load(scope, "program").server_time == pytest.approx(900, abs=5)
    with pytest.raises(ValueError, match="Lease TTL must be 1..900 seconds"):
        store.heartbeat(scope, lease, ttl_seconds=901)
    assert store.heartbeat(scope, lease, ttl_seconds=900).fence == lease.fence


def test_the_runtime_opens_each_window_with_the_longest_lease():
    """A window runs several specialists and then publishes everything they committed, with no
    heartbeat: it claims the longest lease the store allows."""
    default = inspect.signature(NativeResearchRuntimeFactory.open).parameters["ttl_seconds"].default
    assert default == 900
