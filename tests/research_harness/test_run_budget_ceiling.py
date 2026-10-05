"""USD 1 bounds the whole specimen run: the ordinary chain's spend plus the research harness's.

The per-run limit is the collection profile's ``processing.run_cost_limit_micros``
(USD 1 in the published profile). The research run's allowance is seeded at
provisioning with what the run's ordinary chain had already spent against that
same limit, so the research ceiling leaves only the remainder. Everything here
is offline: a real SQLite research state, the committed pins, scripted models
and recorded source responses. Nothing calls a model or the network.
"""
import threading

import pytest

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.storage import digest as canonical_digest
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.research_harness import production_runtime
from specimen_digitization.research_harness.committed_pins import build_committed_pins
from specimen_digitization.research_harness.contracts import digest
from specimen_digitization.research_harness.persistence import (
    BlobRef, BudgetExceeded, CapturedResult, DurabilityScope, HeldUnknown, PinnedRuntime, ResearchStore,
    SqliteStateBackend,
)
from specimen_digitization.research_harness.production_runtime import research_budget_policy

import test_production_e2e as e2e
from test_production_bridge import Stop, opened, ordinary_spend, worker_context  # noqa: F401 (fixtures)
from test_production_e2e import no_network  # noqa: F401 (autouse fixture: the e2e tests make no HTTP)

CEILING = 1_000_000


def profile_snapshot():
    return published_registry().profiles[0].model_dump(mode="json")


def request_reservation():
    """What one research model request reserves under the committed pins."""
    pins = build_committed_pins(profile_snapshot(), organization_id="org-c1", collection_id="col-c1")
    return pins["model"]["specimen_geography"]["reservation_micro_usd"]


def seeded_store(tmp_path, spend):
    """A research state seeded with the ordinary spend, and a job whose lease is held."""
    scope = DurabilityScope("org-c1", "col-c1", "spec-c1", "job-c1", 1, "actor-c1", False)
    backend = SqliteStateBackend(tmp_path / "state.sqlite3")
    backend.grant(scope)
    store = ResearchStore(backend, "research-run:c1")
    store.initialize(scope, research_budget_policy(profile_snapshot(), spend))
    store.create_job(scope, PinnedRuntime(input_digest="a" * 64, profile={}, prompts={}, sources={},
        model={}, settings={"max_tokens": 2048}, engine_version="c1"), ["taxon"])
    return store, scope, store.claim(scope, "owner-c1", ttl_seconds=300)


def settle(store, scope, lease, effect_id, actual):
    attempt = store.mark_sending(scope, lease, effect_id)
    store.finalize_effect(scope, effect_id, attempt["attempt_id"],
        BlobRef(attempt["capture_locator"], "1", "0" * 64, 2),
        CapturedResult(typed_payload={}, actual_micro_usd=actual))


def test_the_policy_carries_the_profiles_limit_and_the_ordinary_spend():
    policy = research_budget_policy(profile_snapshot(), 123_456)
    assert (policy.ceiling_micro_usd, policy.external_settled_micro_usd,
        policy.external_held_micro_usd) == (CEILING, 123_456, 0)
    assert policy.live_authorized is True and policy.hold_reason is None
    # Without an ordinary spend nothing is carried.
    assert research_budget_policy(profile_snapshot()) == research_budget_policy(profile_snapshot(), 0)


def test_a_run_classified_under_the_former_limit_keeps_it():
    # The limit is read from each run's own profile snapshot, so a run that the
    # previous image classified (500,000) keeps its ceiling, and its pins and
    # policy still build and agree with themselves under this code.
    snapshot = profile_snapshot()
    snapshot["processing"]["run_cost_limit_micros"] = 500_000
    pins = build_committed_pins(snapshot, organization_id="org-c1", collection_id="col-c1")
    assert pins == build_committed_pins(snapshot, organization_id="org-c1", collection_id="col-c1")
    assert research_budget_policy(snapshot, 30_000).ceiling_micro_usd == 500_000
    current = build_committed_pins(profile_snapshot(), organization_id="org-c1", collection_id="col-c1")
    assert digest(pins) != digest(current)


@pytest.mark.parametrize("spend", [0, 150_000, 480_000])
@pytest.mark.parametrize("workers", [6, 12])
def test_concurrent_reservations_never_cross_the_ceiling_with_the_ordinary_spend(tmp_path, workers, spend):
    # Several specialists reserving at once: each reservation is a compare-and-set
    # on the run's one state document, so a reservation is admitted only while the
    # ordinary spend, what is held and what is settled still leave room for it.
    reservation = request_reservation()
    store, scope, lease = seeded_store(tmp_path, spend)
    barrier, outcomes = threading.Barrier(workers), []

    def specialist(index):
        barrier.wait()
        try:
            effect = store.reserve_effect(scope, lease, f"model:role{index}", {"role": index}, reservation)
            outcomes.append(("admitted", effect["effect_id"]))
        except BudgetExceeded:
            outcomes.append(("refused", None))
        except Exception as error:  # a CAS conflict that exhausted its retries would show here
            outcomes.append((type(error).__name__, None))

    threads = [threading.Thread(target=specialist, args=(index,)) for index in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    admitted = [effect_id for kind, effect_id in outcomes if kind == "admitted"]
    assert {kind for kind, _ in outcomes} <= {"admitted", "refused"}, outcomes
    assert len(admitted) == min(workers, (CEILING - spend) // reservation)
    budget, stored = store.budget(scope), store._read(scope).state["budget_totals"]
    assert budget["held_micro_usd"] == len(admitted) * reservation and budget["settled_micro_usd"] == spend
    assert budget["held_micro_usd"] + budget["settled_micro_usd"] <= CEILING
    assert stored["held_micro_usd"] == budget["held_micro_usd"] and stored["settled_micro_usd"] == spend
    # Settling releases each hold and keeps only the actual: the run can then admit
    # a request again, still inside the ceiling.
    for effect_id in admitted:
        settle(store, scope, lease, effect_id, 5_000)
    budget = store.budget(scope)
    assert budget["held_micro_usd"] == 0 and budget["settled_micro_usd"] == spend + 5_000 * len(admitted)
    store.reserve_effect(scope, lease, "model:later", {"role": "later"}, reservation)
    budget = store.budget(scope)
    assert budget["held_micro_usd"] + budget["settled_micro_usd"] <= CEILING


def test_an_ordinary_run_near_the_ceiling_leaves_research_no_request(tmp_path):
    reservation = request_reservation()
    spend = CEILING - reservation + 1
    store, scope, lease = seeded_store(tmp_path, spend)
    with pytest.raises(BudgetExceeded):
        store.reserve_effect(scope, lease, "model:role", {"role": 0}, reservation)
    budget = store.budget(scope)
    assert (budget["held_micro_usd"], budget["settled_micro_usd"], budget["remaining_micro_usd"]) == (
        0, spend, reservation - 1)
    assert store._read(scope).state["effects"] == {}


def test_research_settlement_halts_the_run_at_the_whole_specimen_ceiling(tmp_path):
    # 900,000 spent by the ordinary chain; one research request settles 100,000:
    # together they are the ceiling, so the run halts and admits nothing more.
    store, scope, lease = seeded_store(tmp_path, 900_000)
    effect = store.reserve_effect(scope, lease, "model:role", {"request": 1}, 100_000)
    settle(store, scope, lease, effect["effect_id"], 100_000)
    budget = store.budget(scope)
    assert budget["settled_micro_usd"] == CEILING and budget["remaining_micro_usd"] == 0
    assert budget["halted"] is True
    with pytest.raises(BudgetExceeded):
        store.reserve_effect(scope, lease, "model:role", {"request": 2}, 1)


def test_a_request_cannot_send_when_its_context_and_output_bound_would_cross_one_dollar(tmp_path):
    reservation = request_reservation()
    store, scope, lease = seeded_store(tmp_path, CEILING - reservation + 1)
    # No paid effect exists: the financial bound is enforced before dispatch.
    with pytest.raises(BudgetExceeded):
        store.reserve_effect(scope, lease, "model:role", {"request": 1}, reservation)
    assert store._read(scope).state["effects"] == {}
    assert store.budget(scope)["settled_micro_usd"] == CEILING - reservation + 1


def test_provider_contract_violation_is_recorded_in_full_and_halts_for_reconciliation(tmp_path):
    # Defensive accounting is not permission to overspend: this injected
    # provider-contract violation is impossible under the admitted token bounds.
    store, scope, lease = seeded_store(tmp_path, 0)
    effect = store.reserve_effect(scope, lease, "model:broken-provider", {}, 10_000)
    settle(store, scope, lease, effect["effect_id"], 10_001)
    assert store.budget(scope)["settled_micro_usd"] == 10_001
    assert store.budget(scope)["halted"] is True


@pytest.mark.parametrize("ordinary_spend", [250_000])
def test_open_adopts_the_ordinary_spend_the_state_was_seeded_with(opened, ordinary_spend):
    with pytest.raises(Stop):  # every check passed; the request factory was reached
        opened.open(opened.factory())
    document = opened.store._read(opened.scope)
    assert document.state["budget_policy"]["external_settled_micro_usd"] == 250_000
    assert opened.store.budget(opened.scope)["remaining_micro_usd"] == CEILING - 250_000


@pytest.mark.parametrize("ordinary_spend", [250_000])
def test_open_still_holds_a_seeded_allowance_that_differs_in_another_field(opened, ordinary_spend,
                                                                           monkeypatch):
    from dataclasses import replace
    committed = research_budget_policy(opened.specimen.run.profile_snapshot)
    for change in ({"external_held_micro_usd": 1}, {"ceiling_micro_usd": CEILING - 1},
                   {"external_ledger_digest": "another-ledger"}):
        monkeypatch.setattr(production_runtime, "research_budget_policy",
            lambda profile, change=change: replace(committed, **change))
        with pytest.raises(HeldUnknown, match="research_live_admission_unqualified"):
            opened.open(opened.factory())


@pytest.mark.parametrize("ordinary_spend", [CEILING, CEILING + 250_000])
def test_open_holds_a_run_whose_ordinary_spend_left_no_headroom(opened, ordinary_spend):
    # The second value is a run whose ordinary limit was larger than this ceiling
    # (an API image newer than the worker's): it holds the same way.
    with pytest.raises(HeldUnknown, match="^research_program_headroom_unavailable$"):
        opened.open(opened.factory())


def rig_with_ordinary_spend(tmp_path, monkeypatch, spend):
    """The e2e rig whose specimen's ordinary chain had spent ``spend`` before adjudication."""
    real = e2e.specimen_before_adjudication

    def spent(blobs, **kwargs):
        specimen = real(blobs, **kwargs)
        specimen.run.usage.reserved_cost_micros = spend
        return specimen
    monkeypatch.setattr(e2e, "specimen_before_adjudication", spent)
    yield from e2e.build_rig(tmp_path)


@pytest.fixture
def rig_after_250k(tmp_path, monkeypatch):
    yield from rig_with_ordinary_spend(tmp_path, monkeypatch, 250_000)


@pytest.fixture
def rig_after_the_whole_limit(tmp_path, monkeypatch):
    yield from rig_with_ordinary_spend(tmp_path, monkeypatch, CEILING)


@pytest.fixture
def rig_after_980k(tmp_path, monkeypatch):
    yield from rig_with_ordinary_spend(tmp_path, monkeypatch, 980_000)


def test_the_production_entry_point_counts_the_ordinary_spend_against_the_ceiling(rig_after_250k):
    rig = rig_after_250k
    workflow = e2e.compose(rig, geolocate=False)
    parsed = e2e.to_plan(workflow, rig)
    assert parsed.run.usage.reserved_cost_micros == 250_000
    with e2e.supervised(), pytest.raises(OperationalBlock, match="native_research_operational_hold"):
        workflow.step(rig.principal, rig.specimen_id)
    (_, state), binding = e2e.jobs_and_bindings(rig)
    policy, totals = state["budget_policy"], state["budget_totals"]
    assert (policy["ceiling_micro_usd"], policy["external_settled_micro_usd"]) == (CEILING, 250_000)
    research = sum(effect.get("actual_micro_usd") or 0 for effect in state["effects"].values())
    assert research > 0 and rig.model_calls
    assert totals["settled_micro_usd"] == 250_000 + research and totals["held_micro_usd"] == 0
    assert totals["settled_micro_usd"] + totals["held_micro_usd"] <= CEILING
    assert binding["semantic_mapping"]["journal_budget_policy_digest"] == digest(policy)


def test_an_ordinary_chain_that_spent_the_whole_limit_leaves_the_harness_no_headroom(
        rig_after_the_whole_limit):
    rig = rig_after_the_whole_limit
    workflow = e2e.compose(rig, geolocate=False)
    e2e.to_plan(workflow, rig)
    with e2e.supervised(), pytest.raises(OperationalBlock, match="^research_program_headroom_unavailable$"):
        workflow.step(rig.principal, rig.specimen_id)
    # No model request and no source lookup was made, and nothing more was spent.
    assert rig.model_calls == [] and rig.source_urls == []
    (_, state), _ = e2e.jobs_and_bindings(rig)
    assert state["budget_policy"]["external_settled_micro_usd"] == CEILING
    assert state["effects"] == {} and state["budget_totals"]["remaining_micro_usd"] == 0


@pytest.fixture
def rig_after_40k(tmp_path, monkeypatch):
    yield from rig_with_ordinary_spend(tmp_path, monkeypatch, 40_000)


def test_a_transcription_correction_after_research_researches_again_on_the_stored_seed(rig_after_40k):
    # A person's transcription decision (api.py, kind "transcription") takes the
    # same run's parse, plan and lookup out of completed_steps and sets its stage
    # back to parse; parse is billed again. The research allowance is immutable, so
    # provisioning for the new revision must keep its stored seed (40,000) rather
    # than hold the run with research_provision_state_conflict.
    rig = rig_after_40k
    workflow = e2e.compose(rig, geolocate=False)
    e2e.to_plan(workflow, rig)
    with e2e.supervised(), pytest.raises(OperationalBlock, match="native_research_operational_hold"):
        workflow.step(rig.principal, rig.specimen_id)
    specimen = rig.repository.get(rig.principal.scope, rig.specimen_id)
    first_revision, run = specimen.version, specimen.run
    run.completed_steps = [step for step in run.completed_steps if step not in {
        "parse", "plan", "lookup", "resolve", "normalize", "validate", "finalize"}]
    run.stage, run.disposition, run.blocker = "parse", None, None
    run.usage.reserved_cost_micros += 20_000  # the re-billed parse, a full reservation
    corrected = rig.repository.save(rig.principal, specimen, first_revision, "reviewer-correction",
        canonical_digest({"correction": 1}))
    assert rig.ordinary.next_step(corrected.run) == "parse"
    workflow = e2e.compose(rig, geolocate=False)
    outcome = None
    for _ in range(3):  # parse, then provisioning and research for the new revision
        with e2e.supervised():
            try:
                stepped = workflow.step(rig.principal, rig.specimen_id)
                outcome = ("ok", rig.ordinary.next_step(stepped.run))
            except OperationalBlock as error:
                outcome = ("block", str(error))
                break
    assert outcome != ("block", "research_provision_state_conflict"), outcome
    assert outcome == ("block", "native_research_operational_hold"), outcome
    (_, state), binding = e2e.jobs_and_bindings(rig)
    assert len(state["jobs"]) == 2 and binding["job_id"].endswith(f"-r{corrected.version + 1}")
    assert state["budget_policy"]["external_settled_micro_usd"] == 40_000
    assert state["ordinary_cost_micros"] == 60_000
    totals = state["budget_totals"]
    assert totals["held_micro_usd"] == 0 and totals["settled_micro_usd"] <= CEILING


@pytest.mark.parametrize("ordinary_spend", [250_000])
def test_open_refuses_a_stored_seed_that_is_not_the_registered_policy(opened, ordinary_spend):
    # The registered binding names the digest of the policy it was registered with.
    # A seed rewritten in the stored state (to 0, say) no longer matches it.
    def lower(state, _now):
        state["budget_policy"]["external_settled_micro_usd"] = 0
    opened.store._mutate(opened.scope, lower, force_cas=True)
    assert opened.store.budget(opened.scope)["settled_micro_usd"] == 0
    with pytest.raises(HeldUnknown, match="research_live_admission_unqualified"):
        opened.open(opened.factory())


@pytest.mark.parametrize("ordinary_spend", [250_000])
@pytest.mark.parametrize("seed", [-1, 2.5, True])
def test_open_refuses_a_malformed_stored_seed_even_when_its_digest_matches(opened, ordinary_spend, seed):
    # With the registered digest made to match, only the seed's own check refuses.
    # Simulate externally malformed persistence; the normal reducer now rejects
    # this before CAS, so corrupt the offline backend directly.
    document = opened.store._read(opened.scope)
    document.state["budget_policy"]["external_settled_micro_usd"] = seed
    opened.backend.cas(opened.scope, opened.store.program_key, document.revision, document.state)
    opened.binding.journal_budget_policy_digest = digest(opened.store._read(opened.scope).state["budget_policy"])
    with pytest.raises(HeldUnknown, match="^research_live_admission_unqualified$"):
        opened.open(opened.factory())


def test_an_ordinary_chain_near_the_limit_leaves_no_room_for_one_request(rig_after_980k):
    # 20,000 remain, less than one request's reservation: the roles are refused
    # before any call, so nothing is sent and nothing more is spent.
    rig = rig_after_980k
    workflow = e2e.compose(rig, geolocate=False)
    e2e.to_plan(workflow, rig)
    with e2e.supervised(), pytest.raises(OperationalBlock, match="native_research_operational_hold"):
        workflow.step(rig.principal, rig.specimen_id)
    assert rig.model_calls == []
    (_, state), _ = e2e.jobs_and_bindings(rig)
    totals = state["budget_totals"]
    assert totals["settled_micro_usd"] == 980_000 and totals["held_micro_usd"] == 0
    job = list(state["jobs"].values())[0]
    assert {field["work_state"] for field in job["fields"].values()} == {"operational_failed"}
    assert state["effects"] == {} and rig.source_urls == []
