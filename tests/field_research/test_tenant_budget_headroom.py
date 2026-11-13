"""Field research under a monthly budget cap (docs/execution/golive/TENANT_BUDGETS.md).

FieldResearchStep.reservation reserves the run's whole headroom, capped by what
the program's allowance has left; a monthly cap of the organization or the
collection that applies caps it the same way, by the least its ledgers have
left this month. test_step.py's rig, with caps added to its SQLite store.
"""

from __future__ import annotations

import pytest

from specimen_digitization.application.domain import Disposition, Scope
from specimen_digitization.application import lane_allowance, tenant_budget
from specimen_digitization.application.tenant_budget import (
    EXHAUSTED, ORGANIZATION, RECORD, Reservation, TenantLedger, month_of,
)
from specimen_digitization.application.workflow import FIELD_RESEARCH, requeue_completed_field_research

from test_step import COLLECTION, ONE_REQUEST, ORG, Scripted, build_rig, mounted, research_paid, seed_program


@pytest.fixture
def rig(tmp_path):
    return build_rig(tmp_path)


def cap(rig, micros, key=ORGANIZATION, **more):
    """The organization's (or a collection's) monthly cap, as SqlConnectRepository.tenant_caps
    returns it; ``more`` adds {key: micros}."""
    rows = [{"collection_key": key, "monthly_cap_micros": micros}] + [
        {"collection_key": name, "monthly_cap_micros": value} for name, value in more.items()]
    rig.repository.tenant_caps = lambda scope: {"caps": rows,
        "collections": [{"id": COLLECTION, "parent_id": None}]}


def month_ledger(rig, key=ORGANIZATION):
    return TenantLedger(rig.repository, Scope(organization_id=ORG, collection_id=COLLECTION), key,
        month_of(rig.clock.now))


def test_a_low_monthly_cap_caps_the_step_and_sends_what_does_not_fit_to_review(rig):
    cap(rig, 25_000)
    resolver = Scripted(tokens=(48_000, 2048))  # Each field's call settles at its worst case.
    state = mounted(rig, resolver)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    [meter] = state.meters
    assert meter.cap_micros == 25_000 and ONE_REQUEST < 25_000
    [paid] = research_paid(run)
    assert paid["reserved_micros"] == 25_000 and paid["cost_micros"] == meter.spent_micros <= 25_000
    assert (run.stage, run.disposition, run.blocker) == ("finalized", Disposition.REVIEW, None)
    # The cap's ledger reserved the headroom and settled to what the experts spent.
    assert month_ledger(rig).read()["reserved_total_micros"] == meter.spent_micros


def test_the_least_left_of_the_cap_and_the_program_allowance_caps_the_step(rig):
    seed_program(rig, 5_000_000 - 40_000)  # The allowance has 40,000 left.
    cap(rig, 30_000, key=COLLECTION)  # The collection's cap has less.
    resolver = Scripted(tokens=(48_000, 2048))
    state = mounted(rig, resolver)
    rig.workflow.step(rig.principal, rig.specimen.id)
    [meter] = state.meters
    assert meter.cap_micros == 30_000


def test_a_monthly_cap_below_one_request_blocks_the_record(rig):
    cap(rig, ONE_REQUEST - 1)
    resolver = Scripted()
    state = mounted(rig, resolver)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (run.stage, run.blocker) == ("processing_blocked", EXHAUSTED)
    assert resolver.calls == [] and state.meters == []
    assert month_ledger(rig).read()["reserved_total_micros"] == 0


def test_unreadable_caps_keep_the_headroom_and_block_at_the_reservation(rig):
    def refused(scope):
        raise ValueError("malformed answer")

    rig.repository.tenant_caps = refused
    resolver = Scripted()
    state = mounted(rig, resolver)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (run.stage, run.blocker) == ("processing_blocked", "tenant_budget_unavailable")
    assert resolver.calls == [] and state.meters == []


# ---- an attempt refused after its hold is retried with that hold -----------------

def retry(rig, steps=None):
    """What a person's retry does to a blocked run (api.py, action "retry").
    ``steps`` sets the run's steps used, so the run's own step limit (a limit
    other than money, workflow.RESEARCH_LIMITS) can leave the retry no room."""
    specimen = rig.repository.get(rig.principal.scope, rig.specimen.id)
    specimen.run.blocker, specimen.run.disposition, specimen.run.stage = None, None, "plan"
    if steps is not None:
        specimen.run.usage.steps = steps
    rig.repository.save(rig.principal, specimen, specimen.version, "retry", "retry")


def refused_once(monkeypatch, owner, name, refuse):
    """``owner.name`` refuses its first call with ``refuse()``, then works."""
    real, calls = getattr(owner, name), []

    def once(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1 and refuse(*args):
            return refuse(*args)
        return real(*args, **kwargs)
    monkeypatch.setattr(owner, name, once)
    return calls


def test_an_attempt_the_allowance_refuses_after_its_hold_runs_on_retry(rig, monkeypatch):
    # The race the read-only check cannot exclude: another worker takes the
    # allowance's room between this attempt's check and its reservation, once.
    program = seed_program(rig, 5_000_000 - 40_000)
    cap(rig, 60_000)
    refused_once(monkeypatch, lane_allowance, "reserve_step", lambda *args: lane_allowance.EXHAUSTED)
    resolver = Scripted()
    state = mounted(rig, resolver)
    blocked = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (blocked.stage, blocked.blocker) == ("processing_blocked", "program_allowance_exhausted")
    assert blocked.dependencies[RECORD][f"{FIELD_RESEARCH}:1"]["keys"] == [ORGANIZATION]
    assert month_ledger(rig).read()["reserved_total_micros"] == 40_000 and resolver.calls == []
    retry(rig)
    # The cap's room is now 20,000, smaller by the attempt's own hold: the
    # attempt reserves its recorded 40,000 again, and its hold replays.
    done = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (done.stage, done.blocker) == ("finalized", None) and done.attempts[FIELD_RESEARCH] == 1
    [meter] = state.meters
    assert meter.cap_micros == 40_000 and resolver.calls
    assert done.dependencies[RECORD][f"{FIELD_RESEARCH}:1"]["micros"] == 40_000
    assert month_ledger(rig).read()["reserved_total_micros"] == meter.spent_micros
    assert program.read()["reserved_total_micros"] == 5_000_000 - 40_000 + meter.spent_micros


def test_an_attempt_a_second_cap_refuses_after_its_first_hold_runs_on_retry(rig, monkeypatch):
    # No program ledger: the collection's ledger refuses once after the check
    # (another worker filled it meanwhile), the organization's already holds.
    cap(rig, 60_000, **{COLLECTION: 40_000})

    real = TenantLedger.reserve
    refused = []

    def reserve(ledger, *args, **kwargs):
        if ledger.key == COLLECTION and not refused:
            refused.append(True)
            return Reservation(EXHAUSTED, None, False)
        return real(ledger, *args, **kwargs)
    monkeypatch.setattr(TenantLedger, "reserve", reserve)
    resolver = Scripted()
    state = mounted(rig, resolver)
    blocked = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (blocked.stage, blocked.blocker) == ("processing_blocked", EXHAUSTED)
    assert blocked.dependencies[RECORD][f"{FIELD_RESEARCH}:1"]["keys"] == [ORGANIZATION]
    assert month_ledger(rig).read()["reserved_total_micros"] == 40_000
    retry(rig)
    done = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (done.stage, done.blocker) == ("finalized", None)
    [meter] = state.meters
    assert meter.cap_micros == 40_000
    for key in (ORGANIZATION, COLLECTION):
        assert month_ledger(rig, key).read()["reserved_total_micros"] == meter.spent_micros


def test_a_held_attempt_given_up_unsent_on_retry_settles_its_hold_at_zero(rig, monkeypatch):
    # The attempt held 40,000 of a 60,000 cap and the program's allowance
    # refused it once (the race). By the person's retry the run's own step
    # limit leaves it no room. Its own hold is not counted twice, so the retry
    # is given up unsent rather than blocked over the cap; never sent, the
    # hold settles at zero.
    program = seed_program(rig, 5_000_000 - 40_000)
    cap(rig, 60_000)
    refused_once(monkeypatch, lane_allowance, "reserve_step", lambda *args: lane_allowance.EXHAUSTED)
    resolver = Scripted()
    state = mounted(rig, resolver)
    blocked = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (blocked.stage, blocked.blocker) == ("processing_blocked", "program_allowance_exhausted")
    assert month_ledger(rig).read()["reserved_total_micros"] == 40_000
    used = blocked.usage.steps
    retry(rig, steps=blocked.profile.execution.max_steps)
    done = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (done.stage, done.blocker, done.disposition) == ("finalized", None, Disposition.REVIEW)
    assert resolver.calls == [] and state.meters == [] and done.attempts.get(FIELD_RESEARCH, 0) == 0
    assert done.dependencies[RECORD][f"{FIELD_RESEARCH}:1"]["released"] is True
    current = month_ledger(rig).read()
    assert current["reserved_total_micros"] == 0
    assert [entry["settled_micros"] for entry in current["ordinary_effects"].values()] == [0]
    assert program.read()["reserved_total_micros"] == 5_000_000 - 40_000  # It never held there.

    # Queued again on the same run (a person's retry of the reviewed run, as
    # api.py's "retry" action does it), with room under its limits: the same
    # attempt number holds afresh, under the next generation's entry, and its
    # spend counts.
    specimen = rig.repository.get(rig.principal.scope, rig.specimen.id)
    assert requeue_completed_field_research(specimen.run)
    specimen.run.blocker, specimen.run.disposition, specimen.run.stage = None, None, "plan"
    specimen.run.usage.steps = used
    rig.repository.save(rig.principal, specimen, specimen.version, "queued-again", "queued-again")
    again = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert again.blocker is None and again.attempts[FIELD_RESEARCH] == 1 and resolver.calls
    [meter] = state.meters
    assert again.dependencies[RECORD][f"{FIELD_RESEARCH}:1"]["generation"] == 1
    current = month_ledger(rig).read()
    assert current["reserved_total_micros"] == meter.spent_micros > 0
    assert sorted(entry["settled_micros"] for entry in current["ordinary_effects"].values()) == [
        0, meter.spent_micros]


def test_a_hold_whose_run_was_never_saved_is_found_on_the_ledger_and_replays(rig):
    # A worker reserved field research's headroom and stopped before saving the
    # run: no record, but this month's ledger holds the attempt.
    cap(rig, 25_000)
    stopped = rig.repository.get(rig.principal.scope, rig.specimen.id)
    assert tenant_budget.reserve_step(rig.repository, rig.principal, stopped, FIELD_RESEARCH, 25_000,
        rig.workflow.clock) is None
    assert RECORD not in rig.repository.get(rig.principal.scope, rig.specimen.id).run.dependencies
    resolver = Scripted()
    state = mounted(rig, resolver)
    done = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (done.stage, done.blocker) == ("finalized", None)
    [meter] = state.meters
    assert meter.cap_micros == 25_000
    assert month_ledger(rig).read()["reserved_total_micros"] == meter.spent_micros
