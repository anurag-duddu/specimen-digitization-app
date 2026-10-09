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
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, FieldKey, FieldResolution, SpecialistRole, WorkState,
)
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, DurabilityScope, PinnedRuntime, ResearchStore, SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.production_runtime import NativeResearchRuntimeFactory

from test_production_bridge import RESEARCH_SCOPE, TAXON, PublishingRuntime, checkpoint, principal, thread


def roster_index(key):
    """Where the key's specialist stands in the roster (the order a pass offers the roles in)."""
    roles = {field: role for role, fields in ROLE_FIELDS.items() for field in fields}
    return list(SpecialistRole).index(roles[key])


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
        # _job takes the job out of a state already read (no read of its own); job() is a read.
        self.store = SimpleNamespace(job=read_job, _read=read_state, _job=lambda state, scope: job)
        winners, self.probes = winners or {}, []

        async def winning_receipt(principal, specimen_id, *, idempotency_key, request_identity_digest):
            self.probes.append(idempotency_key)
            return winners.get(idempotency_key)
        async def read_current_binding(principal, specimen_id):
            self.reads["binding"] += 1
            return SimpleNamespace(causal_chain=())

        async def publish_progress(principal, specimen_id, *, scope):
            # This recording fixture has no native causal proof. It must hold
            # terminal completion instead of manufacturing a progress receipt.
            raise StaleWork("synthetic_native_progress_unproved")

        self.canonical_service = SimpleNamespace(publish_checkpoint=self._publish, winning_receipt=winning_receipt,
            read_current_binding=read_current_binding, publish_progress=publish_progress)


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


def test_a_publication_pass_reads_the_state_once_not_once_per_checkpoint(monkeypatch):
    typed = (resolved(FieldKey.CITY), resolved(FieldKey.COUNTRY), resolved(FieldKey.COUNTY),
        resolved(FieldKey.HABITAT), TAXON)
    runtime = CountingRuntime(typed)
    outcome = publish(monkeypatch, runtime, thread(*typed))
    # Before: one job read per checkpoint and one more at the end, one outbox read per checkpoint;
    # then one read of each, which were two separate reads of the same document.
    assert runtime.reads == {"state": 1}
    # The specialists in roster order (taxonomy first), not the journal's key order.
    assert [field for field, _ in runtime.prepared] == [FieldKey.TAXON, FieldKey.CITY, FieldKey.COUNTRY,
        FieldKey.COUNTY, FieldKey.HABITAT]
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
    assert outcome.publication_receipt_ids == ("receipt-replayed", "receipt-city")   # roster order: taxonomy first
    assert runtime.reads == {"state": 1}


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


def delivered(key, *, commit=True, flag=True):
    """The outbox entry of a publication: pending, or delivered with the receipt's canonical_commit."""
    entry = {"kind": "canonical_publication_required", "delivered": flag,
        "guard": {"checkpoint_id": f"native-{key}", "idempotency_key": f"idem-{key}"}}
    if flag is None:
        del entry["delivered"]
    if commit:
        entry["canonical_commit"] = {"id": f"receipt-of-{key}"}
    return {f"publish/{key}": entry}


def test_a_pass_over_delivered_checkpoints_reads_no_proof_and_asks_for_no_receipt(monkeypatch):
    """Every later window walks every earlier checkpoint. The state document records each delivered
    publication (the receipt and the flag are written in one SQL transaction): twenty of them cost
    no checkpoint proof read, receipt probe or value publication. Terminal
    completion also requires one current causal-head read; this fixture has no
    such proof and therefore preserves the native progress hold."""
    typed = tuple(resolved(key) for key in FieldKey)
    outbox = {}
    for item in typed:
        outbox.update(delivered(item.field_key))
    runtime = CountingRuntime(typed, outbox=outbox)
    outcome = publish(monkeypatch, runtime, thread(*typed))
    assert runtime.proofs == [] and runtime.probes == [] and runtime.prepared == []
    assert runtime.reads == {"state": 1, "binding": 1}
    # Replay still returns every delivered checkpoint and receipt in roster order.
    in_order = sorted(typed, key=lambda item: roster_index(item.field_key))
    assert outcome.checkpoint_ids == tuple(f"native-{item.field_key}" for item in in_order)
    assert outcome.publication_receipt_ids == tuple(f"receipt-of-{item.field_key}" for item in in_order)
    assert outcome.status == "blocked"
    assert outcome.reason_code == "native_progress_publication_requires_reconciliation"


def test_a_pass_publishes_the_new_checkpoints_and_skips_the_delivered_ones(monkeypatch):
    typed = (resolved(FieldKey.CITY), resolved(FieldKey.COUNTRY), TAXON, resolved(FieldKey.HABITAT))
    outbox = {**delivered(FieldKey.COUNTRY), **delivered(FieldKey.HABITAT)}
    runtime = CountingRuntime(typed, outbox=outbox)
    outcome = publish(monkeypatch, runtime, thread(*typed))
    # Delivered values stay in roster order; the genuine unsent Taxon carrier
    # follows them to record current terminal progress.
    assert [field for field, _ in runtime.prepared] == [FieldKey.CITY, FieldKey.TAXON]
    assert runtime.proofs == ["native-city", "native-taxon"] and runtime.probes == []
    assert outcome.publication_receipt_ids == ("receipt-city", "receipt-of-country",
        "receipt-of-habitat", "receipt-taxon")


@pytest.mark.parametrize("flag", [False, None])
def test_a_publication_not_marked_delivered_is_still_verified(monkeypatch, flag):
    """A pending entry (a crash after the attempt was marked, before the commit) is verified: its
    proof is read and its receipt probed, and a winner found by the probe is reused."""
    typed = (resolved(FieldKey.CITY), TAXON)
    outbox = {**delivered(FieldKey.CITY, commit=False, flag=flag), **delivered(FieldKey.TAXON, commit=False, flag=flag)}
    winner = SimpleNamespace(causal=SimpleNamespace(receipt_id="receipt-found"))
    runtime = CountingRuntime(typed, outbox=outbox, winners={"idem-taxon": winner})
    outcome = publish(monkeypatch, runtime, thread(*typed))
    assert runtime.proofs == ["native-taxon", "native-city"] and runtime.probes == ["idem-taxon", "idem-city"]
    assert [field for field, _ in runtime.prepared] == [FieldKey.CITY]
    assert outcome.publication_receipt_ids == ("receipt-found", "receipt-city")


@pytest.mark.parametrize("commit", [None, {}, {"id": None}, {"id": ""}, {"id": 7}, "receipt"])
def test_a_delivered_flag_without_its_receipt_commit_is_not_trusted(monkeypatch, commit):
    """The code only ever sets ``delivered`` together with ``canonical_commit`` (publication_v2
    .outbox_completion and the connector's exact next-state check), so this entry is not one it
    wrote. It is not skipped: it is verified like a pending one. If the probe finds no receipt, the
    worker prepares the publication, and the real preparation refuses a delivered entry
    (native_publication_already_delivered, tests/test_research_harness_publication.py), so the
    pass ends blocked instead of trusting the flag."""
    typed = (TAXON,)
    entry = delivered(FieldKey.TAXON, commit=False)
    if commit is not None:
        entry["publish/taxon"]["canonical_commit"] = commit
    runtime = CountingRuntime(typed, outbox=entry)
    publish(monkeypatch, runtime, thread(*typed))
    assert runtime.proofs == ["native-taxon"] and runtime.probes == ["idem-taxon"]
    assert [field for field, _ in runtime.prepared] == [FieldKey.TAXON]


def test_two_entries_for_one_checkpoint_are_ambiguous_even_when_one_is_delivered(monkeypatch):
    first = delivered(FieldKey.TAXON)
    second = {"publish/other": dict(first["publish/taxon"], delivered=False)}
    runtime = CountingRuntime((TAXON,), outbox={**first, **second})
    with pytest.raises(StaleWork, match="native_publication_operation_ambiguous"):
        publish(monkeypatch, runtime, thread(TAXON))
    assert runtime.prepared == []
