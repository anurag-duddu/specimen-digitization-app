"""Real local CAS ledgers plus a scripted provider; no network or paid calls."""
import asyncio
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import Scope
from specimen_digitization.application.lane_allowance import LEDGER_KIND, ProgramLedger
from specimen_digitization.application.storage import SQLiteRepository
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, CapturedResult, DurabilityScope, HeldUnknown, ImmutableFileBlobs,
    PinnedRuntime, ResearchStore, SqliteStateBackend,
)
from specimen_digitization.research_harness.program_budget import ProgramEffectBroker


@pytest.fixture
def rig(tmp_path):
    scope = DurabilityScope("org", "collection", "specimen", "job", 1, "actor", False)
    repository = SQLiteRepository(tmp_path / "ordinary.sqlite")
    ordinary_scope = Scope(organization_id="org", collection_id="collection")
    ledger = ProgramLedger(repository, ordinary_scope)
    repository.put_document(ordinary_scope, LEDGER_KIND, ledger.ident,
        {"sensitive": False, "reserved_total_micros": 4_800_000, "prior_unknown": "retained"}, 0)
    backend = SqliteStateBackend(tmp_path / "research.sqlite")
    backend.grant(scope)
    store = ResearchStore(backend, "research-run:00000000-0000-4000-8000-000000000111")
    store.initialize(scope, BudgetPolicy(1_000_000, external_settled_micro_usd=100_000))
    store.create_job(scope, PinnedRuntime("input", {}, {}, {}, {}, {}, "fixture"), ["taxon"])
    lease = store.claim(scope, "worker", ttl_seconds=300)
    run = SimpleNamespace(profile=SimpleNamespace(execution=SimpleNamespace(
        program_allowance_micros=5_000_000, program_ledger_collection="collection")))
    broker = ProgramEffectBroker(store, ImmutableFileBlobs(tmp_path / "blobs"),
        repository=repository, scope=scope, run=run)
    return SimpleNamespace(scope=scope, repository=repository, ledger=ledger, store=store, lease=lease, broker=broker)


def request(rig, number=1, reservation=150_000, actual=10_000, calls=None, fail=False):
    async def dispatch(attempt, key):
        if calls is not None:
            calls.append(key)
        if fail:
            raise OSError("lost provider response")
        return CapturedResult({}, actual)
    return asyncio.run(rig.broker.execute(rig.scope, rig.lease, "model:role", {"request": number},
        reservation, dispatch, field_keys=("taxon",)))


@pytest.mark.parametrize("allowance, refused", [
    (15_000_000, False),  # The pilot profile's allowance (G30).
    (25_000_000, False),  # G9's USD 25 ceiling is the largest the code admits.
    (25_000_001, True)])
def test_the_code_refuses_an_allowance_above_the_g9_ceiling(rig, tmp_path, allowance, refused):
    run = SimpleNamespace(profile=SimpleNamespace(execution=SimpleNamespace(
        program_allowance_micros=allowance, program_ledger_collection="collection")))
    def build():
        return ProgramEffectBroker(rig.store, ImmutableFileBlobs(tmp_path / "cap-blobs"),
            repository=rig.repository, scope=rig.scope, run=run)
    if refused:
        with pytest.raises(HeldUnknown, match="program_allowance_ledger_unavailable"):
            build()
    else:
        assert build().allowance == allowance


def test_global_allowance_refuses_before_a_send_is_marked_or_provider_called(rig):
    calls = []
    with pytest.raises(HeldUnknown, match="program_allowance_exhausted"):
        request(rig, reservation=200_001, calls=calls)
    assert calls == []
    effect = next(iter(rig.store._read(rig.scope).state["effects"].values()))
    assert effect["status"] == "reserved" and effect["attempts"] == []
    assert rig.ledger.read()["reserved_total_micros"] == 4_800_000


def test_settlement_and_replay_count_once_preserving_prior_liabilities(rig):
    calls = []
    request(rig, calls=calls)
    request(rig, calls=calls)
    rig.broker.reconcile(rig.scope)
    assert len(calls) == 1
    assert rig.ledger.read()["reserved_total_micros"] == 4_810_000
    assert rig.ledger.read()["prior_unknown"] == "retained"
    assert rig.store.budget(rig.scope)["settled_micro_usd"] == 110_000
    # Ordinary calls must retain research idempotency records when they update
    # the shared document; otherwise a later replay could settle twice.
    rig.ledger.reserve(5_000_000, 20_000, specimen_id="s", run_id="r", step="parse", attempt=1)
    rig.ledger.settle(5_000_000, 20_000, 1_000, specimen_id="s", run_id="r", step="parse", attempt=1)
    rig.broker.reconcile(rig.scope)
    assert rig.ledger.read()["reserved_total_micros"] == 4_811_000


def test_unknown_response_keeps_both_full_holds_across_restart(rig):
    with pytest.raises(OSError):
        request(rig, fail=True)
    rig.broker.reconcile(rig.scope)
    assert rig.ledger.read()["reserved_total_micros"] == 4_950_000
    assert rig.store.budget(rig.scope)["held_micro_usd"] == 150_000
    with pytest.raises(HeldUnknown, match="program_allowance_exhausted"):
        request(rig, number=2, reservation=50_001)


def test_historical_cost_is_carried_even_when_it_exhausts_the_allowance(rig):
    # Old research state may predate program accounting. Never erase it or
    # pretend the original aggregate covered it without evidence.
    rig.ledger.research_effect(5_000_000, "historical", 300_000, settle=True, historical=True)
    rig.ledger.research_effect(5_000_000, "historical", 300_000, settle=True, historical=True)
    assert rig.ledger.read()["reserved_total_micros"] == 5_100_000
    with pytest.raises(HeldUnknown, match="program_allowance_exhausted"):
        request(rig)


def test_repeated_ordinary_corrections_never_reset_the_research_remainder(rig):
    request(rig)
    for total in (120_000, 120_000, 100_000, 160_000):
        rig.store.reconcile_ordinary_spend(rig.scope, total)
    budget = rig.store.budget(rig.scope)
    assert budget["settled_micro_usd"] == 170_000
    assert rig.store._read(rig.scope).state["budget_policy"]["external_settled_micro_usd"] == 100_000


def test_two_specimens_share_one_atomic_program_allowance(rig):
    from concurrent.futures import ThreadPoolExecutor
    from specimen_digitization.application.lane_allowance import LegacyLedgerUnavailable
    def reserve(key):
        try:
            rig.ledger.research_effect(5_000_000, key, 150_000)
            return "reserved"
        except LegacyLedgerUnavailable as error:
            return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, ["run-one", "run-two"]))
    assert sorted(outcomes) == ["program_allowance_exhausted", "reserved"]
    assert rig.ledger.read()["reserved_total_micros"] == 4_950_000


def liability_input(rig):
    specimen = SimpleNamespace(id="specimen", asset=SimpleNamespace(sensitive=False),
        run=SimpleNamespace(id="00000000-0000-4000-8000-000000000111", usage=SimpleNamespace(reserved_cost_micros=90_000)))
    principal = SimpleNamespace(scope=Scope(organization_id="org", collection_id="collection"), user_id="actor")
    # Scope is run-wide: the ordinary pre-call reader does not have a research job ID.
    class Backend:
        def load(self, scope, key):
            assert scope.job_id == "ordinary-budget-read" and key == "research-run:00000000-0000-4000-8000-000000000111"
            return rig.store._read(rig.scope)
    return principal, specimen, Backend()


def test_ordinary_pre_call_offset_counts_all_jobs_unknowns_and_highwater(rig):
    from specimen_digitization.research_harness.program_budget import research_liability_micros
    request(rig, actual=10_000)
    with pytest.raises(OSError):
        request(rig, number=2, reservation=100_000, fail=True)
    rig.store.reconcile_ordinary_spend(rig.scope, 120_000)
    principal, specimen, backend = liability_input(rig)
    assert research_liability_micros(None, principal, specimen, state_backend=backend) == 140_000


@pytest.mark.parametrize("mutation", ["absent", "unreadable", "contract", "program", "negative", "boolean"])
def test_only_absent_research_state_means_zero_liability(rig, mutation):
    from specimen_digitization.research_harness.program_budget import research_liability_micros
    principal, specimen, backend = liability_input(rig)
    document = backend.load(SimpleNamespace(job_id="ordinary-budget-read"), "research-run:00000000-0000-4000-8000-000000000111")
    state = document.state
    if mutation == "contract": state["contract_version"] = "unknown"
    if mutation == "program": state["program_key"] = "another-run"
    if mutation == "negative": state["budget_policy"]["external_held_micro_usd"] = -1
    if mutation == "boolean": state["budget_policy"]["external_held_micro_usd"] = False
    def load(scope, key):
        if mutation == "unreadable": raise OSError("offline state read failed")
        return None if mutation == "absent" else document
    backend.load = load
    if mutation == "absent":
        assert research_liability_micros(None, principal, specimen, state_backend=backend) == 0
    else:
        with pytest.raises(HeldUnknown, match="research_budget_state_unavailable"):
            research_liability_micros(None, principal, specimen, state_backend=backend)


def test_ordinary_and_research_race_on_the_same_run_ceiling(rig):
    from concurrent.futures import ThreadPoolExecutor
    from specimen_digitization.research_harness.persistence import BudgetExceeded
    rig.store.reconcile_ordinary_spend(rig.scope, 700_000)
    def ordinary():
        try:
            rig.store.reserve_ordinary(rig.scope, "parse:2", 200_000, 700_000)
            return "reserved"
        except BudgetExceeded:
            return "blocked"
    def research():
        try:
            rig.store.reserve_effect(rig.scope, rig.lease, "model:role", {"request": 1}, 200_000)
            return "reserved"
        except BudgetExceeded:
            return "blocked"
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(ordinary), pool.submit(research)]
        assert sorted(future.result() for future in futures) == ["blocked", "reserved"]
    totals = rig.store.budget(rig.scope)
    assert totals["settled_micro_usd"] + totals["held_micro_usd"] == 900_000


def test_ordinary_reservation_survives_failed_canonical_save_and_replay(rig):
    rig.store.reserve_ordinary(rig.scope, "parse:2", 200_000, 700_000)
    rig.store.reserve_ordinary(rig.scope, "parse:2", 200_000, 700_000)
    assert rig.store.budget(rig.scope)["settled_micro_usd"] == 900_000
    with pytest.raises(HeldUnknown, match="ordinary_reservation_changed"):
        rig.store.reserve_ordinary(rig.scope, "parse:2", 1, 700_000)


def test_stale_canonical_binding_refuses_before_provider_send(rig):
    from specimen_digitization.research_harness.persistence import StaleWork
    async def stale():
        raise StaleWork("research_canonical_changed_before_dispatch")
    rig.broker.binding_guard = stale
    calls = []
    with pytest.raises(StaleWork):
        request(rig, calls=calls)
    assert calls == []
    effect = next(iter(rig.store._read(rig.scope).state["effects"].values()))
    assert effect["attempts"] == []


def test_binding_changed_after_reservation_still_refuses_at_dispatch(rig):
    from specimen_digitization.research_harness.persistence import StaleWork
    count = 0
    async def guard():
        nonlocal count
        count += 1
        if count == 2:
            raise StaleWork("research_canonical_changed_before_dispatch")
    rig.broker.binding_guard = guard
    calls = []
    with pytest.raises(StaleWork):
        request(rig, calls=calls)
    assert calls == [] and count == 2
    assert rig.ledger.read()["reserved_total_micros"] == 4_950_000


def test_public_ordinary_hook_creates_shared_run_state_before_first_call(rig):
    from specimen_digitization.application.collection_profiles import published_registry
    from specimen_digitization.research_harness.program_budget import reserve_ordinary_liability
    principal, specimen, _ = liability_input(rig)
    specimen.run.id = "00000000-0000-4000-8000-000000000222"
    specimen.run.profile_snapshot = published_registry().profiles[0].model_dump(mode="json")
    specimen.run.attempts = {}
    specimen.run.usage.reserved_cost_micros = 700_000
    reserve_ordinary_liability(None, principal, specimen, "parse", 200_000,
        state_backend=rig.store.backend)
    reserve_ordinary_liability(None, principal, specimen, "parse", 200_000,
        state_backend=rig.store.backend)
    key = "research-run:" + specimen.run.id
    state = rig.store.backend.load(rig.scope, key).state
    assert state["jobs"] == {}
    assert state["ordinary_reservations"] == {"parse:1": {"reserved_micros": 200_000, "settled_micros": None}}
    assert state["budget_totals"]["settled_micro_usd"] == 900_000
    from specimen_digitization.research_harness.persistence import BudgetExceeded
    with pytest.raises(BudgetExceeded, match="run_cost_allowance_exhausted"):
        reserve_ordinary_liability(None, principal, specimen, "parse", 200_000,
            attempt=2, state_backend=rig.store.backend)


def test_known_ordinary_settlement_releases_only_its_unused_hold(rig):
    from specimen_digitization.research_harness.program_budget import settle_ordinary_liability
    principal, specimen, _ = liability_input(rig)
    specimen.run.attempts = {"parse": 2}
    specimen.run.paid_calls = [{"step": "parse", "attempt": 2, "cost_basis": "computed", "cost_micros": 1_000}]
    rig.store.reserve_ordinary(rig.scope, "parse:2", 200_000, 100_000)
    rig.store.reserve_ordinary(rig.scope, "segment:1", 182_321, 100_000)
    for _ in range(2):
        settle_ordinary_liability(None, principal, specimen, "parse", state_backend=rig.store.backend)
    assert rig.store.budget(rig.scope)["settled_micro_usd"] == 100_000 + 1_000 + 182_321
    specimen.run.paid_calls.append({"step": "segment", "attempt": 1, "cost_basis": "reserved", "cost_micros": 182_321})
    settle_ordinary_liability(None, principal, specimen, "segment", state_backend=rig.store.backend)
    assert rig.store.budget(rig.scope)["settled_micro_usd"] == 283_321


def test_production_context_bounds_settle_then_leave_two_role_headroom(rig):
    from specimen_digitization.application.collection_profiles import published_registry
    from specimen_digitization.application.lane_reservations import call_micros
    from specimen_digitization.research_harness.role_windows import window_size
    profile = published_registry().profiles[0]
    prices = profile.processing.price_list.model_dump(mode="json")["models"]
    # Keep the existing 100k unknown seed and full SAM liability. Each model
    # uses the production route's full context bound for both allowed calls.
    rig.store.reserve_ordinary(rig.scope, "segment:1", 182_321, 100_000)
    for step, route in [("first_pass:region:1", profile.first_pass_route), ("parse:1", profile.model_routes[0])]:
        price = prices[route]
        reservation = call_micros({**price, "max_input_tokens": None}, None)
        rig.store.reserve_ordinary(rig.scope, step, reservation, 100_000)
        rig.store.settle_ordinary(rig.scope, step, 2_000)
    remaining = rig.store.budget(rig.scope)["remaining_micro_usd"]
    assert remaining == 713_679
    assert window_size(remaining, 212_173) == 2


def test_ordinary_program_replay_cannot_refund_another_research_hold(rig):
    identity = dict(specimen_id="specimen", run_id="run", step="parse", attempt=1)
    rig.ledger.research_effect(5_000_000, "other-unknown", 100_000)
    for _ in range(2):
        assert rig.ledger.reserve(5_000_000, 50_000, **identity).issue is None
    assert rig.ledger.read()["reserved_total_micros"] == 4_950_000
    for _ in range(2):
        assert rig.ledger.settle(5_000_000, 50_000, 1_000, **identity) is not None
    assert rig.ledger.read()["reserved_total_micros"] == 4_901_000
    assert rig.ledger.reserve(5_000_000, 50_001, **identity).issue == "program_allowance_ledger_unavailable"
    assert rig.ledger.settle(5_000_000, 50_000, 999, **identity) is None
    assert rig.ledger.settle(5_000_000, 100_000, 0, **{**identity, "run_id": "unproved-legacy"}) is None
    assert rig.ledger.read()["reserved_total_micros"] == 4_901_000
    assert rig.ledger.read()["research_effects"]["other-unknown"] == {"micros": 100_000, "status": "held"}


def test_sql_backend_serializes_send_authority_only_for_send_cas():
    from specimen_digitization.research_harness.persistence import SqlConnectStateBackend
    import json
    seen = []
    class Repository:
        def variables(self, scope):
            return {"actorUid": scope.actor_uid}
        def execute(self, operation, variables, mutation=False):
            seen.append((operation, variables))
    scope = DurabilityScope("org", "collection", "specimen", "job", 1, "actor", False)
    backend = SqlConnectStateBackend(Repository())
    authority = {"canonical_revision": 7, "canonical_run_id": "run", "binding_id": "binding",
        "job_key": "job-key", "generation": 1, "record_version_id": "record", "snapshot_sha256": "a" * 64}
    backend.cas(scope, "program", 1, {}, send_authorization=authority)
    backend.cas(scope, "program", 2, {})
    assert json.loads(seen[0][1]["sendAuthorizationJson"]) == authority
    assert "sendAuthorizationJson" not in seen[1][1]
