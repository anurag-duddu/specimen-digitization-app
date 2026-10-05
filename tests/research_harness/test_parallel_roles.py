"""Independent specialists run concurrently in a lease window and publish what they would alone.

One synthetic specimen through the production composer (the e2e rig: every layer
is production code except the in-memory Data Connect, the scripted models and the
recorded sources), with the roles of a window running at once. "Window" is the
set of roles that share one lease and one research phase; K is its size. The
ticks here run K roles per window and compare them with one role per window, the
way production ran before: the same publications, the same field outcomes, the
same finalization, and the same isolation and hold semantics.

Offline rehearsal with scripted models; not a production observation.
"""
from __future__ import annotations

import asyncio
import collections
import contextlib

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

import production_e2e_support as support
from specimen_digitization.application.lane_worker import RECORD_HOLDS
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.research_harness import engine as engine_mod
from specimen_digitization.research_harness import native_worker, production_runtime, provisioning, role_windows
from specimen_digitization.research_harness.committed_pins import (
    build_committed_pins, committed_run_cost_limit_micros,
)
from specimen_digitization.research_harness.agents import SpecialistHarness
from specimen_digitization.research_harness.native_service import SqlConnectNativeCanonicalServiceV2
from specimen_digitization.research_harness.contracts import ROLE_FIELDS, SpecialistRole
from specimen_digitization.research_harness.persistence import BudgetPolicy, ResearchStore, StaleWork
from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow

from test_production_e2e import (  # noqa: F401  (no_network is autouse)
    DATES_AND_ELEVATIONS, SWITCH_ON, build_rig, compose, no_network, supervised, to_plan,
)

TICKS = {}


def committed_reservation():
    """What one model request reserves: the committed pin, derived from the route price and output cap."""
    pins = build_committed_pins(support.published_profile(), organization_id=support.ORG,
        collection_id=support.COLLECTION)
    return pins["model"]["specimen_taxonomy"]["reservation_micro_usd"]


RESERVATION = committed_reservation()


def forced_windows(monkeypatch, k):
    """Run k roles per lease window with k of them at once (the engine's own limits apply)."""
    original = engine_mod.ResearchEngine.run

    async def run(self, **kwargs):
        if kwargs.get("role_limit") is not None:
            self.max_concurrency, kwargs["role_limit"] = k, k
        return await original(self, **kwargs)
    monkeypatch.setattr(engine_mod.ResearchEngine, "run", run)


# Each scripted model response takes this long, so that the first requests of a window's two roles
# are both in flight (and both reserved) before either answers, however busy the machine is.
MODEL_DELAY_SECONDS = 0.4


def scripted_with(rig, *, replace=None, delay=MODEL_DELAY_SECONDS):
    """The e2e's scripted models, each answering after ``delay`` so that roles overlap in time.

    ``replace[role]`` answers in place of the script (a callable (messages, info))."""
    base = support.scripted_model_factory(rig.model_calls)

    def factory(request, binding):
        function = base(request, binding).function
        role = str(request.role)

        async def respond(messages, info):
            await asyncio.sleep(delay)
            if replace and role in replace:
                return replace[role](messages, info)
            return function(messages, info)
        return FunctionModel(respond)
    return factory


def provider_fails(messages, info):
    raise RuntimeError("injected provider failure")


def answers_nothing(messages, info):
    """A valid-looking output that covers none of the requested fields: refused twice, then the role fails."""
    return ModelResponse([ToolCallPart(info.output_tools[0].name, {"role": "specimen_geography", "resolutions": []})])


def refusing_from(number):
    """before_step hook: the connector refuses the ``number``-th publication and every later one."""
    def install(rig):
        publish, calls = rig.fake.op_PublishCanonicalResearchV2, []

        def refusing(variables):
            calls.append(variables["specimenId"])
            if len(calls) >= number:
                raise support.ConnectorRefusal("publication refused")
            return publish(variables)
        rig.fake.op_PublishCanonicalResearchV2 = refusing
    return install


def tick(tmp_path, k, *, replace=None, ceiling=None, spent=0, before_step=None, key=None):
    """One plan tick of the synthetic specimen with k roles per window; the observed facts.

    k None: the production composer as shipped (the window size role_windows.ROLE_CONCURRENCY gives it).
    ceiling: the run's allowance in micro-USD (the published profile's is 500,000).
    spent: micro-USD of that allowance already used before research starts (settled elsewhere).
    before_step: called with the rig after the ordinary steps, before the research tick."""
    if key is not None and key in TICKS:
        return TICKS[key]
    tmp_path.mkdir(parents=True, exist_ok=True)
    timeline, engine_runs, reservations, refusals = [], [], [], []
    with pytest.MonkeyPatch.context() as mp, contextlib.contextmanager(build_rig)(tmp_path) as rig:
        if k is not None:
            forced_windows(mp, k)
        if ceiling is not None:
            def policy(profile, ordinary_spend_micros=0):
                # Same shape as production_runtime.research_budget_policy, whatever the run's
                # ordinary chain has already spent against the limit (zero on the synthetic rig).
                return BudgetPolicy(ceiling, external_settled_micro_usd=ordinary_spend_micros + spent,
                    live_authorized=True, hold_reason=None)
            mp.setattr(production_runtime, "research_budget_policy", policy)
            mp.setattr(provisioning, "research_budget_policy", policy)
        original_engine = engine_mod.ResearchEngine.run

        async def run(self, **kwargs):
            started = len(timeline)
            engine_runs.append({"role_limit": kwargs.get("role_limit"), "max_concurrency": self.max_concurrency})
            try:
                return await original_engine(self, **kwargs)
            finally:
                engine_runs[-1]["roles"] = [item[1] for item in timeline[started:]]
        mp.setattr(engine_mod.ResearchEngine, "run", run)

        original_specialist = SpecialistHarness.run_specialist
        clock = iter(range(10 ** 6))

        async def run_specialist(self, role, **kwargs):
            began = next(clock)
            try:
                return await original_specialist(self, role, **kwargs)
            finally:
                timeline.append(("specialist", str(role), began, next(clock)))
        mp.setattr(SpecialistHarness, "run_specialist", run_specialist)

        # Every release of a lease, on the same logical clock as the specialists' starts and ends.
        release_marks = []
        original_release = ResearchStore.release

        def release(store, *args, **kwargs):
            release_marks.append(next(clock))
            return original_release(store, *args, **kwargs)
        mp.setattr(ResearchStore, "release", release)

        # The publication pass's per-checkpoint verification: the accepted-output proof read and the
        # receipt probe (the probe is also what a restart runs per retained operation; a single
        # tick on a fresh run has none of those).
        proof_reads, receipt_probes = [], []
        original_proof = native_worker.read_accepted_checkpoint_proof

        def read_proof(*args, **kwargs):
            proof_reads.append(args[3])
            return original_proof(*args, **kwargs)
        mp.setattr(native_worker, "read_accepted_checkpoint_proof", read_proof)
        original_probe = SqlConnectNativeCanonicalServiceV2.winning_receipt

        async def probe(self, *args, **kwargs):
            receipt_probes.append(kwargs.get("idempotency_key"))
            return await original_probe(self, *args, **kwargs)
        mp.setattr(SqlConnectNativeCanonicalServiceV2, "winning_receipt", probe)

        original_reserve = ResearchStore.reserve_effect

        def reserve(store, scope, lease, operation_key, request, reservation, **kwargs):
            try:
                result = original_reserve(store, scope, lease, operation_key, request, reservation, **kwargs)
            except Exception as error:
                refusals.append((operation_key, type(error).__name__))
                raise
            if operation_key.startswith("model:"):
                reservations.append(store.budget(scope)["held_micro_usd"])
            return result
        mp.setattr(ResearchStore, "reserve_effect", reserve)

        workflow = compose_production_research_workflow(rig.ordinary, repository=rig.repository,
            environ=SWITCH_ON, actor_uid=support.WORKER, state_backend=rig.backend,
            model_factory=scripted_with(rig, replace=replace),
            source_transport=support.fixture_source_transport(rig.source_urls), blobs=rig.research_blobs)
        to_plan(workflow, rig)
        if before_step is not None:
            before_step(rig)
        outcome = "no OperationalBlock"
        with supervised():
            try:
                workflow.step(rig.principal, rig.specimen_id)
            except OperationalBlock as error:
                outcome = f"OperationalBlock({error})"
        _, state = support.research_state(rig.fake, rig.specimen_id)
        job = list(state["jobs"].values())[0]
        effects = list(state["effects"].values())
        receipts = sorted(rig.fake.receipts.values(), key=lambda row: row["used_canonical_revision"])
        specimen = rig.repository.get(rig.principal.scope, rig.specimen_id)
        spans = [(item[2], item[3]) for item in timeline]
        facts = {
            "stage": specimen.run.stage, "disposition": specimen.run.disposition, "outcome": outcome,
            "reasons": sorted(specimen.run.reasons),
            "publications": [row["causal_proof"]["changed_field"] for row in receipts],
            "published_values": {key: field.normalized for key, field in specimen.run.fields.items()},
            "work_states": {key: field["work_state"] for key, field in job["fields"].items()},
            "effects": dict(collections.Counter(
                (effect["operation_key"].split(":")[0], effect["status"]) for effect in effects)),
            "held_after": sum(effect["held_micro_usd"] for effect in effects),
            "settled": sum(effect.get("actual_micro_usd") or 0 for effect in effects),
            "ceiling": state["budget_policy"]["ceiling_micro_usd"], "halted": state["halted"],
            "peak_held": max(reservations, default=0), "refusals": refusals,
            "model_calls": sorted(collections.Counter(role for role, _ in rig.model_calls).items()),
            "sources": sorted(rig.source_urls), "fence": job["fence"], "lease_left_set": job["lease"] is not None,
            "engine_runs": engine_runs,
            "peak_roles": max((sum(a <= start < b for a, b in spans) for start, _ in spans), default=0),
            "release_marks": release_marks,
            "specialist_ends": [(item[1], item[3]) for item in timeline],
            "final_progress": receipts[-1]["causal_proof"]["progress_receipt"] if receipts else None,
            "specimen_state": rig.fake.specimens[rig.specimen_id]["state"],
            "duplicates": len(rig.fake.duplicates),
            "proof_reads": len(proof_reads), "receipt_probes": len(receipt_probes),
            "connector_calls": collections.Counter(rig.fake.calls),
        }
    if key is not None:
        TICKS[key] = facts
    return facts


def test_two_roles_per_window_publish_what_one_role_per_window_publishes(tmp_path):
    one = tick(tmp_path / "one", 1, key="k1")
    two = tick(tmp_path / "two", None, key="shipped")
    # The synthetic label reaches its final queue either way (needs human review on the
    # held verbatim_dts and the dates and elevations without evidence relations).
    for facts in (one, two):
        assert (facts["stage"], facts["disposition"], facts["outcome"]) == (
            "finalized", "needs_human_review", "no OperationalBlock")
        assert facts["lease_left_set"] is False and facts["duplicates"] == 0
    # The same twelve publications in the same order (a pass offers the specialists in roster order,
    # then each one's fields in key order, as one role per window did), same field outcomes, same
    # record, same reasons, same spend, nothing left held.
    assert two["publications"] == one["publications"] and len(two["publications"]) == 12
    for key in ("work_states", "published_values", "reasons", "effects", "model_calls", "sources", "settled",
                "specimen_state"):
        assert two[key] == one[key], key
    assert one["held_after"] == two["held_after"] == 0 and not one["refusals"] and not two["refusals"]
    # The last publication carries the whole twenty fields' progress in both, and it is a field of
    # the last window's roles: it comes after both of them committed (so it sees every role's work).
    assert two["final_progress"]["human_reason_codes"] == one["final_progress"]["human_reason_codes"]
    assert not two["final_progress"]["operational_reason_codes"]
    last_window = tuple(SpecialistRole)[-role_windows.ROLE_CONCURRENCY:]
    assert two["publications"][-1] in {str(key) for role in last_window for key in ROLE_FIELDS[role]}
    # The final queue is the one the one-role e2e asserts: review on the held D/T/S field and on the
    # dates and elevations without evidence relations, and nothing operational.
    unresolved = {f"mandatory_unresolved:{key}" for key in ("verbatim_dts", *DATES_AND_ELEVATIONS)}
    assert {reason for reason in two["reasons"] if reason.startswith("mandatory_unresolved:")} == unresolved
    # A pass verifies a checkpoint (proof read) and probes its receipt only when it publishes it: a
    # checkpoint an earlier pass delivered is not walked again, however many windows follow.
    for facts in (one, two):
        assert facts["proof_reads"] == 12 and facts["receipt_probes"] == 0
    # Concurrency really happened: two roles at once, in three lease windows instead of six.
    assert (one["peak_roles"], two["peak_roles"]) == (1, 2)
    assert [len(run["roles"]) for run in one["engine_runs"]] == [1] * 6
    assert [len(run["roles"]) for run in two["engine_runs"]] == [2, 2, 2]
    assert (one["fence"], two["fence"]) == (6, 3)
    # The shipped constant drives it: the worker asks the engine for two roles and the engine runs two.
    assert {(run["role_limit"], run["max_concurrency"]) for run in two["engine_runs"]} == {(2, 2)}
    assert [sorted(role.removeprefix("specimen_") for role in run["roles"]) for run in two["engine_runs"]] == [
        ["geography", "taxonomy"], ["measurement", "temporal"], ["collection", "parties"]]


def test_a_window_reserves_two_requests_at_a_time_inside_the_run_allowance(tmp_path):
    two = tick(tmp_path / "two", None, key="shipped")
    # The published profile's run allowance (USD 0.5 today); two reservations are a fraction of it.
    assert two["ceiling"] == committed_run_cost_limit_micros(support.published_profile())
    # Two roles' first requests are in flight together: two reservations held, never more, never refused.
    assert two["peak_held"] == 2 * RESERVATION < two["ceiling"]
    assert not two["refusals"] and not two["halted"] and two["held_after"] == 0
    assert 0 < two["settled"] <= two["ceiling"]


def test_a_role_that_fails_alone_does_not_take_its_window_partner_down(tmp_path):
    """Geography answers nothing valid, twice: its five fields fail (operational_failed), a
    model effect per request is completed and paid, none is held. Taxonomy, its partner in the
    window, publishes its field anyway, and the later windows run."""
    facts = tick(tmp_path, None, replace={"specimen_geography": answers_nothing})
    states = facts["work_states"]
    geography = ("city", "country", "county", "precise_location", "province_state")
    assert {states[key] for key in geography} == {"operational_failed"} and states["taxon"] == "resolved"
    assert "taxon" in facts["publications"] and not set(geography) & set(facts["publications"])
    # The roles after the failed window still published (the windows go on).
    assert {"collectors", "collection_code", "habitat"} <= set(facts["publications"])
    assert facts["effects"].get(("model", "held_unknown"), 0) == 0 and facts["held_after"] == 0
    assert facts["outcome"] == "OperationalBlock(native_research_operational_hold)"
    assert facts["stage"] == "processing_blocked" and facts["disposition"] is None
    assert [len(run["roles"]) for run in facts["engine_runs"]] == [2, 2, 2]


def test_a_held_unknown_model_effect_still_blocks_every_publication_of_the_run(tmp_path):
    """The provider fails in the middle of taxonomy's request: the effect stays held_unknown (it is
    not retried and its reservation stays held). Geography, its partner in the window, finished
    and checkpointed its fields, but no publication of the run is allowed while a held effect
    exists: nothing is published, the lease stays set, the record is held. Unchanged by windows."""
    two = tick(tmp_path / "two", None, replace={"specimen_taxonomy": provider_fails}, key="taxonomy_fails")
    assert two["effects"][("model", "held_unknown")] == 1 and two["held_after"] == RESERVATION
    assert two["publications"] == [] and two["lease_left_set"] is True
    assert two["work_states"]["taxon"] == "operational_failed"
    assert [two["work_states"][key] for key in ("city", "country", "county", "province_state")] == ["resolved"] * 4
    assert two["outcome"] == "OperationalBlock(native_publication_requires_reconciliation)"
    assert two["stage"] == "plan" and two["disposition"] is None
    # With one role per window the same effect holds the run before any other role ran.
    one = tick(tmp_path / "one", 1, replace={"specimen_taxonomy": provider_fails})
    assert one["effects"][("model", "held_unknown")] == 1 and one["publications"] == []
    assert one["outcome"] == "OperationalBlock(research_worker_custody_requires_reconciliation)"
    assert one["work_states"]["city"] == "pending"


def test_a_window_never_runs_more_roles_than_the_run_can_reserve_for(tmp_path):
    """Each running role holds one request's reservation. With an allowance that fits one reservation
    but not two, two concurrent roles would see the second refused (BudgetExceeded, its fields lost
    as operational_failed); the window is narrowed to one role instead, and the run completes."""
    one = tick(tmp_path / "one", 1, key="k1")
    short = tick(tmp_path / "short", None, ceiling=RESERVATION * 19 // 10, key="short")
    assert RESERVATION < short["ceiling"] < 2 * RESERVATION
    assert {(run["role_limit"], run["max_concurrency"]) for run in short["engine_runs"]} == {(1, 1)}
    assert [len(run["roles"]) for run in short["engine_runs"]] == [1] * 6 and short["peak_roles"] == 1
    assert not short["refusals"] and short["held_after"] == 0 and not short["halted"]
    assert (short["stage"], short["disposition"]) == ("finalized", "needs_human_review")
    assert sorted(short["publications"]) == sorted(one["publications"])
    assert short["work_states"] == one["work_states"]


def test_an_allowance_for_two_reservations_keeps_the_two_role_window(tmp_path):
    two = tick(tmp_path / "two", None, ceiling=RESERVATION * 5 // 2, key="enough")
    assert 2 * RESERVATION <= two["ceiling"] < 3 * RESERVATION
    assert [len(run["roles"]) for run in two["engine_runs"]] == [2, 2, 2]
    assert two["peak_held"] == 2 * RESERVATION and not two["refusals"] and two["held_after"] == 0
    assert (two["stage"], two["disposition"]) == ("finalized", "needs_human_review")


def test_the_window_follows_what_is_left_of_the_allowance_not_its_size(tmp_path):
    """An allowance of three reservations with 1.2 of them already spent elsewhere leaves 1.8: one
    request at a time. The window reads the remaining allowance, which counts spend settled outside
    the research state (the ordinary chain's spend, when a run's allowance is seeded with it)."""
    seeded = tick(tmp_path, None, ceiling=3 * RESERVATION, spent=RESERVATION * 6 // 5, key="seeded")
    assert seeded["ceiling"] == 3 * RESERVATION
    assert {(run["role_limit"], run["max_concurrency"]) for run in seeded["engine_runs"]} == {(1, 1)}
    assert not seeded["refusals"] and seeded["held_after"] == 0 and seeded["peak_roles"] == 1
    assert (seeded["stage"], seeded["disposition"]) == ("finalized", "needs_human_review")


def test_a_refused_publication_leaves_the_earlier_roles_committed_fields_published(tmp_path):
    """A pass ends at the first refusal. It offers the roster's first role first, so with two roles in
    a window a refusal on geography's field still finds taxonomy's committed taxon published, as one
    role per window had it. The publication whose outcome is in doubt keeps the lease."""
    one = tick(tmp_path / "one", 1, before_step=refusing_from(2))
    two = tick(tmp_path / "two", None, before_step=refusing_from(2))
    for facts in (one, two):
        assert facts["publications"] == ["taxon"]
        assert facts["outcome"] == "OperationalBlock(native_publication_requires_reconciliation)"
        assert facts["lease_left_set"] is True
    assert [len(run["roles"]) for run in two["engine_runs"]] == [2]


def test_a_blocked_window_with_nothing_in_doubt_releases_its_lease_so_the_record_can_be_stepped_again(
        tmp_path, monkeypatch):
    """The window's publication pass is blocked before any publication was prepared (an accepted-output
    proof is unavailable): no effect is uncertain, so the lease is released. An immediate step claims
    again and meets the same record hold (a code the drain holds), not the drain-ending
    native_research_admission_or_binding_unavailable that "already claimed" gave for up to 900 s."""
    fault = {"on": True}
    original = native_worker.read_accepted_checkpoint_proof

    def proof(*args, **kwargs):
        if fault["on"]:
            raise StaleWork("accepted_output_proof_unavailable")
        return original(*args, **kwargs)
    monkeypatch.setattr(native_worker, "read_accepted_checkpoint_proof", proof)
    with contextlib.contextmanager(build_rig)(tmp_path) as rig:
        workflow = compose(rig)
        to_plan(workflow, rig)
        with supervised(), pytest.raises(OperationalBlock) as first:
            workflow.step(rig.principal, rig.specimen_id)
        assert str(first.value) == "accepted_output_proof_unavailable"
        _, state = support.research_state(rig.fake, rig.specimen_id)
        job = list(state["jobs"].values())[0]
        assert job["lease"] is None and job["fence"] == 1
        assert not [effect for effect in state["effects"].values()
                    if effect["status"] in {"sending", "held_unknown", "reserved"}]
        # Stepped again at once, the fault still there: the record's own hold, again.
        with supervised(), pytest.raises(OperationalBlock) as again:
            workflow.step(rig.principal, rig.specimen_id)
        assert str(again.value) == "accepted_output_proof_unavailable" and str(again.value) in RECORD_HOLDS
        # The fault gone: the run goes on from the same checkpoints and reaches its final queue.
        fault["on"] = False
        with supervised():
            specimen = workflow.step(rig.principal, rig.specimen_id)
        assert (specimen.run.stage, specimen.run.disposition) == ("finalized", "needs_human_review")
        _, state = support.research_state(rig.fake, rig.specimen_id)
        assert list(state["jobs"].values())[0]["lease"] is None


def test_no_lease_is_released_before_both_roles_of_the_window_have_ended(tmp_path):
    """Taxonomy's provider fails at once while geography, its partner, is still in flight (every scripted
    response takes 0.4 s, geography needs two). The window's lease is given back (or kept) only after
    the whole window: the release comes after the failing role's end and after its sibling's."""
    facts = tick(tmp_path, None, replace={"specimen_taxonomy": provider_fails}, key="taxonomy_fails")
    ends = dict(facts["specialist_ends"])
    assert set(ends) == {"specimen_taxonomy", "specimen_geography"}
    assert ends["specimen_taxonomy"] < ends["specimen_geography"]       # the failing role ended first
    assert facts["release_marks"] and min(facts["release_marks"]) > max(ends.values())


def test_a_release_that_fails_on_a_blocked_window_leaves_the_record_its_own_hold(tmp_path, monkeypatch):
    """The accepted-output proof is unavailable (nothing in doubt, so the lease would be released), and
    the release round trip itself fails (Data Connect unavailable). The window's blocked outcome is
    what the bridge sees, not the store error: the record is held with its own code, a code the drain
    holds, and the lease is simply kept."""
    def proof_unavailable(*args, **kwargs):
        raise StaleWork("accepted_output_proof_unavailable")

    def store_unavailable(*args, **kwargs):
        raise OperationalBlock("sql_connect_unavailable_or_connector_not_published")
    monkeypatch.setattr(native_worker, "read_accepted_checkpoint_proof", proof_unavailable)
    with contextlib.contextmanager(build_rig)(tmp_path) as rig:
        workflow = compose(rig)
        to_plan(workflow, rig)
        monkeypatch.setattr(ResearchStore, "release", store_unavailable)
        with supervised(), pytest.raises(OperationalBlock) as held:
            workflow.step(rig.principal, rig.specimen_id)
        assert str(held.value) == "accepted_output_proof_unavailable" and str(held.value) in RECORD_HOLDS
        _, state = support.research_state(rig.fake, rig.specimen_id)
        assert list(state["jobs"].values())[0]["lease"] is not None


def test_a_window_size_the_engine_cannot_run_fails_before_a_lease_is_claimed(tmp_path, monkeypatch):
    """A misconfigured K (the engine accepts one or two) must fail loudly when a window opens, with no
    900 s lease left behind: the check runs before the claim."""
    monkeypatch.setattr(role_windows, "ROLE_CONCURRENCY", 3)
    with contextlib.contextmanager(build_rig)(tmp_path) as rig:
        workflow = compose(rig)
        to_plan(workflow, rig)
        with supervised(), pytest.raises(ValueError, match="research_role_concurrency_unsupported"):
            workflow.step(rig.principal, rig.specimen_id)
        _, state = support.research_state(rig.fake, rig.specimen_id)
        job = list(state["jobs"].values())[0]
        assert job["lease"] is None and job["fence"] == 0 and not state["effects"]
