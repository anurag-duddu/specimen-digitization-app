"""The order a publication pass offers its checkpoints in, and when a blocked window gives its lease back.

Offline stand-ins: test_production_bridge's recording runtime for the pass, a real SQLite store for the lease.
"""
import asyncio
import logging
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness import native_worker
from specimen_digitization.research_harness.contracts import (
    DependencyPin, FieldKey, FieldResolution, WorkState, digest,
)
from specimen_digitization.research_harness.native_worker import NativeResearchWorkerOutcomeV2
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, DurabilityScope, HeldUnknown, PinnedRuntime, ResearchStore, SqliteStateBackend, StaleWork,
)

from test_native_worker_windows import CountingRuntime, publish, resolved, roster_index
from test_production_bridge import RESEARCH_SCOPE, TAXON, checkpoint, principal, thread


def dependent(key, source):
    return checkpoint(FieldResolution(field_key=key, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal="synthetic", evidence_ids=["e-label"],
            evidence_relations={"e-label": "supports"}),
        evidence_ids=("e-label",), reason="synthetic resolved work",
        dependencies=(DependencyPin(field_key=source.field_key, revision=source.revision,
            digest=digest(source.resolution)),)))


def test_a_pass_offers_the_specialists_in_roster_order_then_their_fields_in_key_order(monkeypatch):
    """One role per window offered each role's new fields in turn; a window of two roles must too, so a
    refusal on a later role's field never strands an earlier role's committed fields (a pass ends at the
    first refusal). The journal lists fields in key order across roles; the pass reorders them."""
    typed = (resolved(FieldKey.CITY), resolved(FieldKey.COLLECTORS), resolved(FieldKey.COUNTRY),
        resolved(FieldKey.HABITAT), resolved(FieldKey.PRECISE_LOCATION), TAXON)
    runtime = CountingRuntime(typed)
    publish(monkeypatch, runtime, thread(*typed))
    offered = [field for field, _ in runtime.prepared]
    assert set(offered) == {item.field_key for item in typed}
    assert [roster_index(field) for field in offered] == sorted(roster_index(field) for field in offered)
    assert offered[0] == FieldKey.TAXON
    geography = [field for field in offered if roster_index(field) == roster_index(FieldKey.CITY)]
    assert geography == [FieldKey.CITY, FieldKey.COUNTRY, FieldKey.PRECISE_LOCATION]   # key order within the role


def test_a_derived_value_follows_its_source_within_its_role_before_the_next_role(monkeypatch):
    from_m, to_m = resolved(FieldKey.ELEVATION_FROM_M), resolved(FieldKey.ELEVATION_TO_M)
    from_ft = dependent(FieldKey.ELEVATION_FROM_FT, from_m)
    to_ft = dependent(FieldKey.ELEVATION_TO_FT, to_m)
    typed = (resolved(FieldKey.CITY), from_ft, from_m, to_ft, to_m, resolved(FieldKey.HABITAT), TAXON)
    runtime = CountingRuntime(typed)
    publish(monkeypatch, runtime, thread(*typed))
    offered = [field for field, _ in runtime.prepared]
    measurement = [field for field in offered if roster_index(field) == roster_index(FieldKey.ELEVATION_FROM_M)]
    assert measurement == [FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M,
        FieldKey.ELEVATION_FROM_FT, FieldKey.ELEVATION_TO_FT]
    assert offered.index(FieldKey.ELEVATION_TO_FT) < offered.index(FieldKey.HABITAT)
    assert [roster_index(field) for field in offered] == sorted(roster_index(field) for field in offered)


def test_a_dependency_across_roles_keeps_the_source_first_order(monkeypatch):
    """No role depends on another today. If one ever does, the roster order must not put a derived value
    before its source (the projection refuses it): the pass falls back to the whole-list order."""
    habitat = resolved(FieldKey.HABITAT)                  # collection
    city = dependent(FieldKey.CITY, habitat)              # geography, listed before collection in the roster
    runtime = CountingRuntime((city, habitat))
    publish(monkeypatch, runtime, thread(city, habitat))
    assert [field for field, _ in runtime.prepared] == [FieldKey.HABITAT, FieldKey.CITY]


def store_with_job(tmp_path):
    scope = DurabilityScope("org", "insects", "synthetic", "job", 1, "worker")
    backend = SqliteStateBackend(tmp_path / "state.sqlite")
    backend.grant(scope, can_view_sensitive=True)
    store = ResearchStore(backend, "program")
    store.initialize(scope, BudgetPolicy(1_000_000))
    store.create_job(scope, PinnedRuntime("a" * 64, {"digest": "b" * 64}, {"version": "v1"},
        {"digest": "c" * 64}, {"route": "r"}, {"max_tokens": 128}, "specialist_harness_v2"), ["taxon"])
    return store, scope, store.claim(scope, "worker", ttl_seconds=60)


def publication_entry(store, scope, *, delivered):
    def reduce(state, now):
        state["outbox"]["publish/x"] = {"kind": "canonical_publication_required", "delivered": delivered,
            "guard": {"scope": scope.identity(), "checkpoint_id": "native-taxon", "idempotency_key": "k" * 64}}
    store._mutate(scope, reduce)


@pytest.mark.parametrize("state", ["reserved", "sending", "held_unknown"])
def test_a_blocked_window_keeps_its_lease_while_an_effect_may_have_been_sent(tmp_path, state):
    """After a blocked window the lease is released unless an effect is uncertain. A reserved effect
    (proven unsent) is let go by an ordinary release as before, and kept after a block; a sending or
    held_unknown effect keeps custody either way."""
    store, scope, lease = store_with_job(tmp_path)
    effect = store.reserve_effect(scope, lease, "model:specimen_taxonomy", {"request": 1}, 100,
        field_keys=("taxon",))["effect_id"]
    if state in {"sending", "held_unknown"}:
        store.mark_sending(scope, lease, effect)
    if state == "held_unknown":
        store.hold_unknown(scope, effect, "dispatch_or_capture_interrupted")
    with pytest.raises(HeldUnknown):
        store.release(scope, lease, blocked=True)
    assert store.job(scope)["lease"] is not None
    if state == "reserved":
        store.release(scope, lease)      # an ordinary release is unchanged
        assert store.job(scope)["lease"] is None
    else:
        with pytest.raises(HeldUnknown):
            store.release(scope, lease)
        assert store.job(scope)["lease"] is not None


def test_a_blocked_window_with_no_uncertain_effect_releases_its_lease(tmp_path):
    store, scope, lease = store_with_job(tmp_path)
    store.release(scope, lease, blocked=True)
    assert store.job(scope)["lease"] is None


def test_a_publication_prepared_and_not_delivered_keeps_custody_after_a_block(tmp_path):
    """Its attempt may be marked at the connector with no receipt: the next step has to reconcile it
    (run_registered's receipt probe raises native_publication_receipt_requires_reconciliation, lease or
    not). Custody stays until then; an ordinary release is unchanged."""
    store, scope, lease = store_with_job(tmp_path)
    publication_entry(store, scope, delivered=False)
    with pytest.raises(HeldUnknown):
        store.release(scope, lease, blocked=True)
    assert store.job(scope)["lease"] is not None
    store.release(scope, lease)           # an ordinary release is unchanged
    assert store.job(scope)["lease"] is None


def test_a_delivered_publication_does_not_hold_the_lease(tmp_path):
    store, scope, lease = store_with_job(tmp_path)
    publication_entry(store, scope, delivered=True)
    store.release(scope, lease, blocked=True)
    assert store.job(scope)["lease"] is None


class Window:
    """run_registered over a runtime whose release is scripted: one window that ends with ``outcome``."""

    def __init__(self, monkeypatch, outcome, release):
        self.released = []

        def record(scope, lease, **kwargs):
            self.released.append(kwargs)
            return release()
        runtime = SimpleNamespace(store=SimpleNamespace(release=record), scope="durable", lease="lease")

        class Factory:
            async def retained_publication_locators(self, principal, specimen_id):
                return []

            async def open(self, principal, specimen_id, *, owner):
                return runtime
        self.worker = native_worker.NativeResearchWorker(Factory())

        async def run_runtime(*args, **kwargs):
            return outcome
        monkeypatch.setattr(self.worker, "_run_runtime", run_runtime)

    def run(self):
        return asyncio.run(self.worker.run_registered(principal(), RESEARCH_SCOPE.specimen_id, owner="test"))


def blocked_outcome():
    return NativeResearchWorkerOutcomeV2(scope=RESEARCH_SCOPE, status="blocked",
        reason_code="accepted_output_proof_unavailable")


def raises(error):
    def release():
        raise error
    return release


def test_a_release_that_fails_after_a_blocked_window_keeps_the_blocked_outcome(monkeypatch, caplog):
    """The release is best effort there: the window's blocked outcome is the record's hold and must not
    be replaced by a store error (which the bridge would turn into the drain-ending code). The lease
    stays set, as it did before this PR; the failure is logged by class and place, not by message."""
    window = Window(monkeypatch, blocked_outcome(), raises(RuntimeError("Data Connect said: label text")))
    with caplog.at_level(logging.WARNING, logger="specimen_digitization.research_harness.native_worker"):
        outcome = window.run()
    assert (outcome.status, outcome.reason_code) == ("blocked", "accepted_output_proof_unavailable")
    assert window.released == [{"blocked": True}]
    [line] = [record.getMessage() for record in caplog.records]
    assert line.startswith("lease release after a blocked window failed: RuntimeError at=")
    assert "label text" not in caplog.text


@pytest.mark.parametrize("error", [HeldUnknown("Uncertain effect retains its lease custody"),
                                   StaleWork("Current active generation and lease fence required")])
def test_a_release_the_store_refuses_keeps_the_blocked_outcome_without_a_log(monkeypatch, caplog, error):
    window = Window(monkeypatch, blocked_outcome(), raises(error))
    with caplog.at_level(logging.WARNING):
        outcome = window.run()
    assert outcome.reason_code == "accepted_output_proof_unavailable" and not caplog.records


def test_a_release_that_fails_after_a_window_that_did_not_block_still_raises(monkeypatch):
    """Unchanged: only the release after a BLOCKED window is best effort."""
    completed = NativeResearchWorkerOutcomeV2(scope=RESEARCH_SCOPE, status="completed")
    window = Window(monkeypatch, completed, raises(RuntimeError("store unavailable")))
    with pytest.raises(RuntimeError, match="store unavailable"):
        window.run()
    assert window.released == [{"blocked": False}]
