"""Field research under a monthly budget cap (docs/execution/golive/TENANT_BUDGETS.md).

FieldResearchStep.reservation reserves the run's whole headroom, capped by what
the program's allowance has left; a monthly cap of the organization or the
collection that applies caps it the same way, by the least its ledgers have
left this month. test_step.py's rig, with caps added to its SQLite store.
"""

from __future__ import annotations

import pytest

from specimen_digitization.application.domain import Disposition, Scope
from specimen_digitization.application.tenant_budget import EXHAUSTED, ORGANIZATION, TenantLedger, month_of

from test_step import COLLECTION, ONE_REQUEST, ORG, Scripted, build_rig, mounted, seed_program


@pytest.fixture
def rig(tmp_path):
    return build_rig(tmp_path)


def cap(rig, micros, key=ORGANIZATION):
    """The organization's (or a collection's) monthly cap, as SqlConnectRepository.tenant_caps returns it."""
    rig.repository.tenant_caps = lambda scope: {"caps": [{"collection_key": key, "monthly_cap_micros": micros}],
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
    [paid] = run.paid_calls
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
