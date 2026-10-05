"""Prior research liabilities must fence the next ordinary paid call."""

import pytest

from specimen_digitization.application import lane_reservations
from specimen_digitization.application.domain import Principal
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.workflow import OperationalBlock, Workflow

from test_lane_costs import SCOPE, priced_run
from test_lane_drain import NonSensitiveMember
from test_lane_profile import USER
from test_lane_trigger import specimen_with


class CountingAdapters:
    calls = 0

    def segment(self, specimen):
        self.calls += 1
        raise OperationalBlock("offline_call_reached")


def make_workflow(tmp_path, monkeypatch, retained):
    repository = NonSensitiveMember(tmp_path / "state.sqlite3")
    principal = Principal(user_id=USER, scope=SCOPE, role="reviewer")
    run = priced_run()
    run.completed_steps = ["pin_dependencies", "classify", "quality_check"]
    run.profile.execution = run.profile.execution.model_copy(update={
        "approved_cost_limit_micros": 1_000_000,
        "program_allowance_micros": None,
    })
    run.usage.reserved_cost_micros = 200_000
    specimen = specimen_with(run)
    repository.create(principal, specimen, "seed", "seed")
    monkeypatch.setattr(lane_reservations, "step_reservation", lambda run, step: 20_000)
    adapters = CountingAdapters()
    workflow = Workflow(repository, LocalBlobs(tmp_path / "blobs"), adapters,
        retained_cost=retained)
    return workflow, principal, specimen, adapters


def test_retained_research_blocks_send_without_double_counting(tmp_path, monkeypatch):
    workflow, principal, specimen, adapters = make_workflow(
        tmp_path, monkeypatch, lambda principal, specimen: 790_000)
    result = workflow.step(principal, specimen.id)
    assert adapters.calls == 0
    assert (result.run.stage, result.run.blocker) == ("processing_blocked", "cost_budget_exhausted")
    assert result.run.usage.reserved_cost_micros == 200_000
    assert result.run.profile.execution.approved_cost_limit_micros == 1_000_000


def test_exact_limit_permits_call(tmp_path, monkeypatch):
    workflow, principal, specimen, adapters = make_workflow(
        tmp_path, monkeypatch, lambda principal, specimen: 780_000)
    result = workflow.step(principal, specimen.id)
    assert adapters.calls == 1
    assert result.run.blocker == "offline_call_reached"
    assert result.run.usage.reserved_cost_micros < 300_000
    assert result.run.profile.execution.approved_cost_limit_micros == 1_000_000


@pytest.mark.parametrize("offset", [-1, None, True, "100"])
def test_invalid_retained_liability_blocks_before_send(tmp_path, monkeypatch, offset):
    workflow, principal, specimen, adapters = make_workflow(
        tmp_path, monkeypatch, lambda principal, specimen: offset)
    result = workflow.step(principal, specimen.id)
    assert adapters.calls == 0
    assert result.run.blocker == "research_budget_state_unavailable"
    assert result.run.usage.reserved_cost_micros == 200_000


def test_unreadable_state_blocks_before_send(tmp_path, monkeypatch):
    def unavailable(principal, specimen):
        raise RuntimeError("offline storage unavailable")

    workflow, principal, specimen, adapters = make_workflow(tmp_path, monkeypatch, unavailable)
    result = workflow.step(principal, specimen.id)
    assert adapters.calls == 0
    assert result.run.blocker == "research_budget_state_unavailable"
