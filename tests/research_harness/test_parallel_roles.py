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
import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

import production_e2e_support as support
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.research_harness import engine as engine_mod
from specimen_digitization.research_harness.agents import SpecialistHarness
from specimen_digitization.research_harness.persistence import ResearchStore
from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow

from test_production_e2e import SWITCH_ON, build_rig, no_network, supervised, to_plan  # noqa: F401

RESERVATION = 107_725
TICKS = {}


def forced_windows(monkeypatch, k):
    """Run k roles per lease window with k of them at once (the engine's own limits apply)."""
    original = engine_mod.ResearchEngine.run

    async def run(self, **kwargs):
        if kwargs.get("role_limit") is not None:
            self.max_concurrency, kwargs["role_limit"] = k, k
        return await original(self, **kwargs)
    monkeypatch.setattr(engine_mod.ResearchEngine, "run", run)


def scripted_with(rig, *, replace=None, delay=0.01):
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


def tick(tmp_path, k, *, replace=None, key=None):
    """One plan tick of the synthetic specimen with k roles per window; the observed facts.

    k None: the production composer as shipped (the window size it picks itself)."""
    if key is not None and key in TICKS:
        return TICKS[key]
    tmp_path.mkdir(parents=True, exist_ok=True)
    timeline, engine_runs, reservations, refusals = [], [], [], []
    with pytest.MonkeyPatch.context() as mp, contextlib.contextmanager(build_rig)(tmp_path) as rig:
        if k is not None:
            forced_windows(mp, k)
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
            "final_progress": receipts[-1]["causal_proof"]["progress_receipt"] if receipts else None,
            "specimen_state": rig.fake.specimens[rig.specimen_id]["state"],
            "duplicates": len(rig.fake.duplicates),
        }
    if key is not None:
        TICKS[key] = facts
    return facts


def test_two_roles_per_window_publish_what_one_role_per_window_publishes(tmp_path):
    one = tick(tmp_path / "one", 1, key="k1")
    two = tick(tmp_path / "two", 2, key="k2")
    # The synthetic label reaches its final queue either way (needs human review on the
    # held verbatim_dts and the dates and elevations without evidence relations).
    for facts in (one, two):
        assert (facts["stage"], facts["disposition"], facts["outcome"]) == (
            "finalized", "needs_human_review", "no OperationalBlock")
        assert facts["lease_left_set"] is False and facts["duplicates"] == 0
    # Same twelve publications (order differs: a window publishes what it committed in key order),
    # same field outcomes, same record, same reasons, same spend, nothing left held.
    assert sorted(two["publications"]) == sorted(one["publications"]) and len(two["publications"]) == 12
    for key in ("work_states", "published_values", "reasons", "effects", "model_calls", "sources", "settled",
                "specimen_state"):
        assert two[key] == one[key], key
    assert one["held_after"] == two["held_after"] == 0 and not one["refusals"] and not two["refusals"]
    # The last publication carries the whole twenty fields' progress in both.
    assert two["final_progress"]["human_reason_codes"] == one["final_progress"]["human_reason_codes"]
    assert not two["final_progress"]["operational_reason_codes"]
    # Concurrency really happened: two roles at once, in three lease windows instead of six.
    assert (one["peak_roles"], two["peak_roles"]) == (1, 2)
    assert [len(run["roles"]) for run in one["engine_runs"]] == [1] * 6
    assert [len(run["roles"]) for run in two["engine_runs"]] == [2, 2, 2]
    assert (one["fence"], two["fence"]) == (6, 3)


def test_a_window_reserves_two_requests_at_a_time_inside_the_half_dollar_ceiling(tmp_path):
    two = tick(tmp_path / "two", 2, key="k2")
    assert two["ceiling"] == 500_000
    # Two roles' first requests are in flight together: two reservations held, never more, never refused.
    assert two["peak_held"] == 2 * RESERVATION < two["ceiling"]
    assert not two["refusals"] and not two["halted"] and two["held_after"] == 0
    assert 0 < two["settled"] <= two["ceiling"]


def test_a_role_that_fails_alone_does_not_take_its_window_partner_down(tmp_path):
    """Geography answers nothing valid, twice: its five fields fail (operational_failed), a
    model effect per request is completed and paid, none is held. Taxonomy, its partner in the
    window, publishes its field anyway, and the later windows run."""
    facts = tick(tmp_path, 2, replace={"specimen_geography": answers_nothing})
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
    two = tick(tmp_path / "two", 2, replace={"specimen_taxonomy": provider_fails})
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
