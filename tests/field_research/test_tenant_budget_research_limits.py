"""A monthly cap comes before the run's model unit limit (TENANT_BUDGETS.md).

test_research_limit_recovery.py's production-like rig: a real
SqlConnectRepository over the in-memory connector, which answers
TenantBudgetCapsV1 with the cap set here. A retry whose model units are spent
is given up on unsent, unless a limit on money would refuse it: a monthly cap
that cannot pay for it, or that cannot be read, keeps the money block, as the
program's allowance does. The cap's ledger is only read here.
"""

from __future__ import annotations

import pytest

from specimen_digitization.application import tenant_budget
from specimen_digitization.application.workflow import FIELD_RESEARCH

from test_field_research_e2e import mount, scripted, supervised
from test_research_limit_recovery import (  # noqa: F401 - the rig fixture
    assert_reviewed_without_a_call, due, first_attempt_fails, given_up, rig,
)

CAP = 5_000_000


def short(self):
    """This month's ledger with one microdollar left: less than one expert request."""
    return {"revision": 1, "reserved_total_micros": CAP - 1, "ordinary_effects": {}}


def plenty(self):
    return {"revision": 1, "reserved_total_micros": 0, "ordinary_effects": {}}


def unreadable(self):
    raise tenant_budget.Conflict("SQL Connect transaction rejected")


@pytest.mark.parametrize(("ledger", "blocker"), [
    (short, tenant_budget.EXHAUSTED),
    (unreadable, tenant_budget.UNAVAILABLE),
    (plenty, None),
], ids=["cap_short", "ledger_unreadable", "cap_plenty"])
def test_a_monthly_cap_comes_before_the_model_unit_limit(rig, monkeypatch, ledger, blocker):
    held, _ = first_attempt_fails(rig)
    rig.fake.tenant_budget_caps["organization"] = (CAP, "administrator", "2026-10-20T00:00:00Z")
    monkeypatch.setattr(tenant_budget.TenantLedger, "read", ledger)

    def no_reservation(*args, **kwargs):
        raise AssertionError("the cap's ledger is never reserved on here")
    monkeypatch.setattr(tenant_budget.TenantLedger, "reserve", no_reservation)
    second = scripted()
    workflow, _, _ = mount(rig, second)
    due(rig, held.run)
    before = len(rig.fake.calls)
    with supervised():
        done = workflow.step(rig.principal, rig.specimen_id)
    assert second.calls == []
    assert "TenantBudgetCapsV1" in rig.fake.calls[before:]
    if blocker is None:
        assert_reviewed_without_a_call(done.run, held, second)
        return
    assert (done.run.stage, done.run.blocker, done.run.disposition) == ("processing_blocked", blocker, None)
    assert given_up(done.run) == [] and done.run.attempts[FIELD_RESEARCH] == 1
    assert not workflow.recover_blocked(rig.principal, rig.specimen_id)
