"""Field research that a run's own limit leaves no room for ends in review.

Production, 2026-10-12 about 22:24Z: a camera photo (asset c7e52321bd4b...)
reached field research, whose first attempt failed (experts answered
`UnexpectedModelBehavior`, the taxon's expert stopped at its own usage limit)
and was scheduled for a retry. The retry's budget check in `Workflow._step`
found no room for another 16,000 reserved model units under the run's
`max_tokens` and saved the run `processing_blocked` as
`token_budget_exhausted`, which the app reads "The run reached its limit on
model units. An administrator must review the approved limit." Nothing carried
it on. The owner: photos stuck in intake "should all successfuly end up in the
main specimen queue based on how the pipeline+harness resolve them".

The production-like rig of test_field_research_e2e.py: a real
SqlConnectRepository over the in-memory connector, the published profile's
cost ceiling and prices, the field experts and sources stand-ins. Its run's
`max_tokens` is one field research reservation, so the first attempt fits and
a retry does not.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import partial

import pytest

from specimen_digitization.application.domain import Disposition, ExecutionPolicy
from specimen_digitization.application.storage import digest
from specimen_digitization.application.workflow import FIELD_RESEARCH

import test_field_research_e2e as e2e
from test_field_research_e2e import CAP, mount, no_network, scripted, supervised  # noqa: F401
from test_step import failing

# One field research reservation (workflow.py: 16,000 reserved model units per
# billable external step that is not synthetic).
ONE_RESERVATION = 16000
GIVEN_UP = "field_research_given_up"


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(e2e, "ExecutionPolicy", partial(ExecutionPolicy, max_tokens=ONE_RESERVATION))
    yield from e2e.make_rig(tmp_path)


def given_up(run):
    return [f.reason_code for f in run.findings if f.rule_id == GIVEN_UP]


def first_attempt_fails(rig):
    """Adjudicate, parse, then field research whose taxon expert fails as a model
    error: the run waits for its retry, with its one reservation spent."""
    first = scripted()
    first.scripts["taxon"] = failing("model_error")
    workflow, _, state = mount(rig, first)
    with supervised():
        workflow.step(rig.principal, rig.specimen_id)
        workflow.step(rig.principal, rig.specimen_id)
        held = workflow.step(rig.principal, rig.specimen_id)
    run = held.run
    assert (run.stage, run.blocker) == ("retry_scheduled", "field_research_model_error")
    assert run.attempts[FIELD_RESEARCH] == 1
    assert run.usage.reserved_tokens == ONE_RESERVATION == run.profile.execution.max_tokens
    return held, state


def due(rig, run):
    moment = datetime.fromisoformat(run.next_retry_at) + timedelta(seconds=1)
    rig.ordinary.clock = lambda: moment.astimezone(timezone.utc)


def leave(rig, **state):
    """Save the run as the code before this change left it."""
    specimen = rig.repository.get(rig.principal.scope, rig.specimen_id)
    for key, value in state.items():
        setattr(specimen.run, key, value)
    return rig.repository.save(rig.principal, specimen, specimen.version, "left-" + digest(sorted(state)),
        digest({"left": sorted(state)}))


def assert_reviewed_without_a_call(run, held, resolver):
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW), run.blocker
    assert resolver.calls == []  # No expert, so no model request, ran again.
    assert given_up(run) == ["field_research_given_up:token_budget_exhausted"]
    assert FIELD_RESEARCH in run.completed_steps
    # Nothing new reserved, attempted or paid: the first attempt's spend stands.
    assert run.attempts[FIELD_RESEARCH] == 1
    assert run.paid_calls == held.run.paid_calls
    assert run.usage.reserved_tokens == ONE_RESERVATION
    assert run.usage.reserved_cost_micros == held.run.usage.reserved_cost_micros <= CAP
    assert run.usage.reserved_cost_micros <= run.profile.execution.approved_cost_limit_micros
    # The field the harness could not check stays unchecked, for the reviewer.
    taxon = run.fields["taxon"]
    assert taxon.state == "unresolved" and "limit" in taxon.reason
    assert "mandatory_unresolved:taxon" in run.reasons
    # A field the first attempt settled is kept.
    assert run.fields["country"].state == "supported"


def test_a_retry_the_model_unit_limit_leaves_no_room_for_goes_to_review_unsent(rig):
    held, _ = first_attempt_fails(rig)
    second = scripted()
    workflow, _, state = mount(rig, second)
    due(rig, held.run)
    with supervised():
        done = workflow.step(rig.principal, rig.specimen_id)

    # Before: processing_blocked as token_budget_exhausted, for an administrator.
    assert_reviewed_without_a_call(done.run, held, second)
    assert state.meters == []  # Not even a meter: the step never started.
    saved = rig.repository.get(rig.principal.scope, rig.specimen_id)
    assert saved.run == done.run
    queued = [row for row in rig.fake.tables["record_version"].values() if row["disposition"] == Disposition.REVIEW]
    assert [row["runId"] for row in queued] == [done.run.id]


def test_a_run_left_blocked_at_the_model_unit_limit_is_recovered_by_the_drain(rig):
    held, _ = first_attempt_fails(rig)
    left = leave(rig, stage="processing_blocked", blocker="token_budget_exhausted", next_retry_at=None,
        disposition=None)
    second = scripted()
    workflow, _, _ = mount(rig, second)
    due(rig, held.run)
    with supervised():
        # As the drain left it, nothing carries it on.
        assert workflow.step(rig.principal, rig.specimen_id).version == left.version
        assert workflow.recover_blocked(rig.principal, rig.specimen_id)
        recovered = rig.repository.get(rig.principal.scope, rig.specimen_id).run
        assert recovered.stage == "retry_scheduled"
        assert recovered.dependencies["automatic_recoveries"][-1]["blocker"] == "token_budget_exhausted"
        done = workflow.drain(rig.principal, rig.specimen_id)

    assert_reviewed_without_a_call(done.run, held, second)


@pytest.mark.parametrize("left", [
    {"disposition": Disposition.REVIEW},
    {"sensitive": True},
    {"blocker": "cost_budget_exhausted"},
    {"blocker": "program_allowance_exhausted"},
    {"lease_until": "2099-01-01T00:00:00+00:00"},
])
def test_sensitive_finished_leased_and_money_blocks_are_never_recovered(rig, left):
    held, _ = first_attempt_fails(rig)
    state = {"stage": "processing_blocked", "blocker": "token_budget_exhausted", "next_retry_at": None,
        "disposition": None, **{key: value for key, value in left.items() if key != "sensitive"}}
    leave(rig, **state)
    if left.get("sensitive"):
        specimen = rig.repository.get(rig.principal.scope, rig.specimen_id)
        specimen.asset.sensitive = True
        rig.repository.save(rig.principal, specimen, specimen.version, "sensitive", digest({"sensitive": True}))
    second = scripted()
    workflow, _, _ = mount(rig, second)
    due(rig, held.run)
    before = rig.repository.get(rig.principal.scope, rig.specimen_id)
    assert not workflow.recover_blocked(rig.principal, rig.specimen_id)
    after = rig.repository.get(rig.principal.scope, rig.specimen_id)
    assert after.version == before.version and after.run.blocker == state["blocker"]
    assert second.calls == [] and given_up(after.run) == []


def test_a_retry_over_the_money_ceiling_still_blocks(rig):
    """The run's cost ceiling is a limit on money (FIELD_RESEARCH.md 8): a run
    whose reservations already exceed it is not given up on here."""
    held, _ = first_attempt_fails(rig)
    run = held.run
    usage = run.usage.model_copy(update={"reserved_tokens": 0,
        "reserved_cost_micros": run.profile.execution.approved_cost_limit_micros + 1})
    leave(rig, usage=usage)
    second = scripted()
    workflow, _, _ = mount(rig, second)
    due(rig, held.run)
    with supervised():
        done = workflow.step(rig.principal, rig.specimen_id)
    assert (done.run.stage, done.run.blocker) == ("processing_blocked", "cost_budget_exhausted")
    assert second.calls == [] and given_up(done.run) == []
    assert not workflow.recover_blocked(rig.principal, rig.specimen_id)
