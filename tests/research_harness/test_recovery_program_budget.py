"""Recovery composition with real local research/ProgramLedger CAS stores.

Historical providers and binding discovery are offline fixtures. No paid call,
native SQL proof or production access is claimed.
"""
import asyncio
import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import Scope
from specimen_digitization.application.lane_allowance import LEDGER_KIND, ProgramLedger
from specimen_digitization.application.storage import Missing, SQLiteRepository
from specimen_digitization.research_harness import production_runtime as module
from specimen_digitization.research_harness import canonical_evidence_provider_v2 as captures
from specimen_digitization.research_harness.contracts import FieldKey
from specimen_digitization.research_harness.persistence import (
    CapturedResult, DurableEffectBroker, HeldUnknown, ImmutableFileBlobs, PinnedRuntime,
)
from specimen_digitization.research_harness.program_budget import ProgramEffectBroker

from test_production_bridge import opened, ordinary_spend, worker_context  # noqa: F401


@pytest.fixture
def recovery(opened, tmp_path, monkeypatch):
    repository = SQLiteRepository(tmp_path / "program.sqlite")
    collection = opened.specimen.scope.collection_id
    execution = opened.specimen.run.profile.execution
    execution.program_allowance_micros = 5_000_000
    execution.program_ledger_collection = collection
    # Canonical/binding discovery stays the existing offline fixture; budget
    # reads/writes use the actual ordinary repository and its optimistic CAS.
    opened.repository.document = repository.document
    opened.repository.put_document = repository.put_document
    ledger = ProgramLedger(repository, Scope(
        organization_id=opened.scope.organization_id, collection_id=collection))
    built = opened.factory()
    def forbidden(*args, **kwargs):
        pytest.fail("publication-only reconciliation constructed or invoked a sender")
    for name in ("_gateway_models", "_georeferencing_adapter", "build_research_engine", "BoundedHTTPTransport"):
        monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(captures, "build_captured_research_services_v2", forbidden)
    monkeypatch.setattr(ProgramEffectBroker, "execute", forbidden)
    monkeypatch.setattr(ProgramEffectBroker, "before_send", forbidden)
    recovered, snapshots = object(), []
    async def publication_only(*args, **kwargs):
        snapshots.append(ledger.read())
        return recovered
    monkeypatch.setattr(built, "_publication_runtime", publication_only)
    return SimpleNamespace(opened=opened, built=built, ledger=ledger, repository=repository,
        blobs=ImmutableFileBlobs(tmp_path / "captures"), recovered=recovered, snapshots=snapshots)


def seed(rig, total=4_900_000):
    rig.repository.put_document(rig.ledger.scope, LEDGER_KIND, rig.ledger.ident,
        {"sensitive": False, "reserved_total_micros": total, "prior_unknown": "preserved"}, 0)


def historical(rig, scope, lease, key, reservation, actual, *, no_effect=False, lost=False):
    store = rig.opened.store
    async def dispatch(*_):
        if lost:
            raise OSError("offline historical reply lost")
        return CapturedResult({"offline": True}, actual,
            outcome="failed_no_effect" if no_effect else "completed")
    broker = DurableEffectBroker(store, rig.blobs)
    try:
        receipt = asyncio.run(broker.execute(scope, lease, key, {"key": key}, reservation,
            dispatch, field_keys=(str(FieldKey.COUNTRY),)))
        return receipt.effect_id
    except OSError:
        assert lost
        return next(effect["effect_id"] for effect in store._read(scope).state["effects"].values()
            if effect["operation_key"] == key)


def attempt_key(rig, effect_id, number=1):
    return f"research:{rig.opened.store.program_key}:{effect_id}:{number}"


@pytest.mark.parametrize("mode", ["exhausted", "halted"])
@pytest.mark.parametrize("unknown", ["unbilled_receipt", "lost_response"])
def test_recovery_imports_all_jobs_attempts_and_unknowns_before_publication(recovery, mode, unknown):
    rig = recovery
    seed(rig)
    opened = rig.opened
    store, scope = opened.store, opened.scope
    lease = store.claim(scope, "offline-history")
    paid = historical(rig, scope, lease, "paid-before-upgrade", 40_000, 25_000)
    held = historical(rig, scope, lease, "unknown-before-upgrade", 100_000, None,
        lost=unknown == "lost_response")
    old_scope = replace(scope, job_id="historical-job")
    pins = PinnedRuntime(**store.job(scope)["pins"])
    old_pins = replace(pins, settings={**pins.settings,
        "retry_failed_no_effect": True, "safe_retry_attempt_limit": 2})
    store.create_job(old_scope, old_pins, [str(FieldKey.COUNTRY)])
    old_lease = store.claim(old_scope, "offline-old-job")
    retried = historical(rig, old_scope, old_lease, "old-retry", 50_000, 10_000, no_effect=True)
    store.retry_effect(old_scope, old_lease, retried)
    assert historical(rig, old_scope, old_lease, "old-retry", 50_000, None) == retried
    if mode == "exhausted":
        opened.specimen.run.usage.reserved_cost_micros = 1_000_000
    else:
        store._mutate(scope, lambda state, _: state.update(halted=True))
    before = copy.deepcopy(store._read(scope).state["effects"])
    assert opened.open(rig.built) is rig.recovered
    expected = {
        attempt_key(rig, paid): {"micros": 25_000, "status": "settled"},
        attempt_key(rig, held): {"micros": 100_000, "status": "held"},
        attempt_key(rig, retried): {"micros": 10_000, "status": "settled"},
        attempt_key(rig, retried, 2): {"micros": 50_000, "status": "held"},
    }
    snapshot = rig.ledger.read()
    assert snapshot["research_effects"] == expected
    assert snapshot["reserved_total_micros"] == 5_085_000
    assert snapshot["prior_unknown"] == "preserved"
    assert rig.snapshots == [snapshot]  # Ledger is reconciled before recovery is exposed.
    assert store._read(scope).state["effects"] == before
    assert opened.open(rig.built) is rig.recovered
    assert rig.ledger.read() == snapshot  # No second charge or CAS revision on replay.
    other = rig.ledger.reserve(5_000_000, 1, specimen_id="another-specimen",
        run_id="another-run", step="parse", attempt=1)
    assert other.issue == "program_allowance_exhausted"


@pytest.mark.parametrize("settlement_ack", ["lost", "already_committed"])
def test_halted_provider_overrun_repairs_global_settlement_without_double_charge(recovery, settlement_ack):
    rig = recovery
    seed(rig, total=4_990_000)
    opened, store = rig.opened, rig.opened.store
    lease = store.claim(opened.scope, "offline-history")
    effect_id = historical(rig, opened.scope, lease, "provider-contract-violation", 5_000, 12_000)
    key = attempt_key(rig, effect_id)
    rig.ledger.research_effect(5_000_000, key, 5_000)  # The known pre-send global reservation.
    if settlement_ack == "already_committed":
        rig.ledger.research_effect(5_000_000, key, 12_000, settle=True, historical=True)
    assert store.budget(opened.scope)["halted"] is True
    assert store.budget(opened.scope)["remaining_micro_usd"] > 0
    assert opened.open(rig.built) is rig.recovered
    first = rig.ledger.read()
    assert first["reserved_total_micros"] == 5_002_000
    assert first["research_effects"][key] == {"micros": 12_000, "status": "settled"}
    assert opened.open(rig.built) is rig.recovered
    assert rig.ledger.read() == first
    assert store.budget(opened.scope)["halted"] is True


@pytest.mark.parametrize("missing", [True, False])
def test_unavailable_program_ledger_holds_recovery_and_preserves_research_liability(recovery, monkeypatch, missing):
    rig = recovery
    opened, store = rig.opened, rig.opened.store
    lease = store.claim(opened.scope, "offline-history")
    historical(rig, opened.scope, lease, "retained-unknown", 50_000, None)
    opened.specimen.run.usage.reserved_cost_micros = 1_000_000
    before = copy.deepcopy(store._read(opened.scope).state["effects"])
    if not missing:
        seed(rig)
        from specimen_digitization.application.lane_allowance import LegacyLedgerUnavailable
        def unavailable(*args, **kwargs):
            raise LegacyLedgerUnavailable("program_allowance_ledger_unavailable")
        monkeypatch.setattr(opened.repository, "document", unavailable)
    with pytest.raises(HeldUnknown, match="program_allowance_ledger_unavailable"):
        opened.open(rig.built)
    assert rig.snapshots == []
    assert store._read(opened.scope).state["effects"] == before
    if missing:
        with pytest.raises(Missing):
            rig.repository.document(rig.ledger.scope, LEDGER_KIND, rig.ledger.ident)
