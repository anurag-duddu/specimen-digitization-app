"""Runs stuck at an ordinary first pass reach their disposition with no action.

2026-10-12: DeepInfra refused most first-pass calls (HTTP 429 and 503), the
route moved to Novita (0977e9c0), and camera-intake runs were left at their
first pass. Each test below builds one of the states such a run can be left in,
as the code that ran then saved it, and shows the normal drain carrying it on:
no run action, no admin script, no new service. The first-pass calls that
reach a provider go through the real isolated model child with an offline
fixture provider (test_rate_limit_refusal); no live model request is made.
"""

from datetime import datetime, timedelta, timezone

from specimen_digitization.application.domain import Disposition
from specimen_digitization.application.lane_worker import DrainWorker
from specimen_digitization.application.production import SqlConnectRepository
from specimen_digitization.application.storage import digest
from specimen_digitization.application.workflow import (
    AUTOMATIC_RECOVERIES,
    LOST_FIRST_PASS,
    MAX_AUTOMATIC_RECOVERIES,
)
from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES

from test_first_pass_given_up import given_up_findings
from test_first_pass_transient_recovery import comparison_lab, comparison_step
from test_lane_routes import FIRST_PASS_RESERVATION, SAM_RESERVATION
from test_rate_limit_refusal import requests

ROUTE = "first-pass-glm"
NOVITA = {"model_id": HUGGINGFACE_ROUTES[ROUTE].model_id, "provider": "novita"}
DEEPINFRA = {**NOVITA, "provider": "deepinfra"}


def later(workflow, hours):
    workflow.clock = lambda: datetime.now(timezone.utc) + timedelta(hours=hours)


def leave(workflow, principal, ident, **state):
    """Save the run as an older worker left it."""
    specimen = workflow.repository.get(principal.scope, ident)
    run = specimen.run
    for key, value in state.items():
        if key == "pin":
            run.dependencies["routes"][ROUTE] = dict(value)
        else:
            setattr(run, key, value)
    return workflow.repository.save(
        principal, specimen, specimen.version, "left-" + digest(sorted(state)), digest({"left": sorted(state)})
    )


def drain_worker(workflow, principal):
    """One drain execution, whose waits move the workflow's clock on."""
    moment = [workflow.clock()]

    def sleep(seconds):
        moment[0] += timedelta(seconds=seconds)

    workflow.clock = lambda: moment[0]
    worker = DrainWorker(
        workflow.repository, workflow, principal.user_id,
        lambda user: [{**principal.scope.model_dump(), "role": principal.role}],
        execution_id="stuck-recovery-fixture", clock=workflow.clock, sleep=sleep,
    )
    return worker.run()


def one_failed_comparison(tmp_path, monkeypatch, attempts=1, **lab):
    """A run whose first comparison failed (HTTP 503) and waits for its retry."""
    workflow, principal, ident, backend, adapter = comparison_lab(
        tmp_path, monkeypatch, "http_503", attempts, **lab
    )
    run = workflow.drain(principal, ident).run
    assert (run.stage, run.attempts[comparison_step(run)]) == ("retry_scheduled", 1)
    return workflow, principal, ident, adapter


def assert_compared(run, adapter, step):
    assert (run.stage, run.blocker) == ("finalized", None)
    assert len(run.first_pass_decisions) == 1 and not given_up_findings(run)
    assert run.dependencies["routes"][ROUTE] == NOVITA
    assert adapter.pins[-1] == NOVITA


def test_a_waiting_retry_pinned_to_the_old_provider_is_repinned_and_sent(tmp_path, monkeypatch):
    # (a) retry_scheduled with a DeepInfra pin. Before: the child refused the pin,
    # so the retry blocked as pinned_model_route_unavailable.
    workflow, principal, ident, adapter = one_failed_comparison(
        tmp_path, monkeypatch, attempts=2, small_prices=True
    )
    leave(workflow, principal, ident, pin=DEEPINFRA)
    later(workflow, 1)

    retried = workflow.drain(principal, ident).run
    step = comparison_step(retried)

    # The re-pinned retry reached the provider (still failing here), not a block.
    assert (retried.stage, retried.blocker) == ("retry_scheduled", "model_provider_error")
    assert requests(tmp_path, "first_pass") == 2
    assert retried.dependencies["routes"][ROUTE] == NOVITA
    (repin,) = retried.dependencies["route_repins"]
    assert {k: repin[k] for k in ("route_id", "model_id", "from_provider", "to_provider")} == {
        "route_id": ROUTE, "model_id": NOVITA["model_id"],
        "from_provider": "deepinfra", "to_provider": "novita",
    }
    assert datetime.fromisoformat(repin["at"])
    later(workflow, 2)
    run = workflow.drain(principal, ident).run
    assert_compared(run, adapter, step)
    assert run.attempts[step] == 3


def test_a_pin_of_another_model_is_never_moved(tmp_path, monkeypatch):
    workflow, principal, ident, _ = one_failed_comparison(tmp_path, monkeypatch, attempts=2)
    other = {"model_id": "other/model", "provider": "deepinfra"}
    leave(workflow, principal, ident, pin=other)
    later(workflow, 1)

    run = workflow.drain(principal, ident).run

    assert (run.stage, run.blocker) == ("processing_blocked", "pinned_model_route_unavailable")
    assert run.dependencies["routes"][ROUTE] == other and "route_repins" not in run.dependencies
    assert requests(tmp_path, "first_pass") == 1
    later(workflow, 2)
    summary = drain_worker(workflow, principal)
    after = workflow.repository.get(principal.scope, ident).run
    assert summary["recovered"] == 0
    assert (after.stage, after.blocker) == ("processing_blocked", "pinned_model_route_unavailable")


def test_a_blocked_old_provider_pin_is_recovered_by_the_drain(tmp_path, monkeypatch):
    # (c) processing_blocked as pinned_model_route_unavailable, DeepInfra pin.
    workflow, principal, ident, adapter = one_failed_comparison(tmp_path, monkeypatch)
    leave(workflow, principal, ident, pin=DEEPINFRA, stage="processing_blocked",
          blocker="pinned_model_route_unavailable", next_retry_at=None)
    later(workflow, 1)

    summary = drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    step = comparison_step(run)
    assert summary["recovered"] == 1 and summary["processed"] == [ident]
    assert_compared(run, adapter, step)
    assert run.attempts[step] == 2
    assert run.dependencies[AUTOMATIC_RECOVERIES][0]["blocker"] == "pinned_model_route_unavailable"


def test_a_blocked_unknown_comparison_is_retried_by_the_drain(tmp_path, monkeypatch):
    # (b) processing_blocked as external_outcome_unknown, as the code before
    # e52503c5 saved a first-pass HTTP 503: the attempt recorded and held, its
    # lease left set.
    workflow, principal, ident, adapter = one_failed_comparison(tmp_path, monkeypatch)
    before = leave(workflow, principal, ident, stage="processing_blocked",
                   blocker="external_outcome_unknown", next_retry_at=None,
                   lease_until=datetime.now(timezone.utc).isoformat())
    step = comparison_step(before.run)
    later(workflow, 1)

    summary = drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    assert summary["recovered"] == 1
    assert_compared(run, adapter, step)
    assert run.attempts[step] == 2 and requests(tmp_path, "first_pass") == 1
    calls = [(c["attempt"], c["outcome"], c["cost_basis"]) for c in run.paid_calls if c["step"] == step]
    # The unknown attempt is recorded once, and stays held in full.
    assert calls == [(1, "failed", "reserved"), (2, "completed", "computed")]


def test_a_lost_comparison_is_a_failed_attempt_with_its_reservation_held(tmp_path, monkeypatch):
    # (f) A worker stopped mid-comparison: intent saved (unknown, lease), no
    # result, nothing recorded. Before: blocked as external_outcome_unknown.
    workflow, principal, ident, _ = one_failed_comparison(tmp_path, monkeypatch, attempts=2)
    specimen = workflow.repository.get(principal.scope, ident)
    step = comparison_step(specimen.run)
    run = specimen.run
    run.attempts[step] += 1
    run.usage.reserved_cost_micros += FIRST_PASS_RESERVATION
    leave(workflow, principal, ident, stage="first_pass", blocker="external_outcome_unknown",
          next_retry_at=None, attempts=run.attempts, usage=run.usage,
          lease_until=datetime.now(timezone.utc).isoformat())
    later(workflow, 1)

    lost = workflow.drain(principal, ident).run

    assert (lost.stage, lost.blocker) == ("retry_scheduled", LOST_FIRST_PASS)
    calls = [(c["attempt"], c["outcome"], c["cost_basis"], c.get("failure_code"))
             for c in lost.paid_calls if c["step"] == step]
    assert calls[-1] == (2, "failed", "reserved", LOST_FIRST_PASS)
    assert lost.usage.reserved_cost_micros == SAM_RESERVATION + 2 * FIRST_PASS_RESERVATION
    assert requests(tmp_path, "first_pass") == 1


def test_a_comparison_lost_on_its_last_attempt_is_given_up(tmp_path, monkeypatch):
    workflow, principal, ident, _ = one_failed_comparison(tmp_path, monkeypatch)
    specimen = workflow.repository.get(principal.scope, ident)
    step = comparison_step(specimen.run)
    attempts = {**specimen.run.attempts, step: specimen.run.profile.execution.max_attempts}
    leave(workflow, principal, ident, stage="first_pass", blocker="external_outcome_unknown",
          next_retry_at=None, attempts=attempts, lease_until=datetime.now(timezone.utc).isoformat())
    later(workflow, 1)

    run = workflow.drain(principal, ident).run

    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert given_up_findings(run) == [
        ("first_pass_given_up", "warning", f"first_pass_given_up:{run.regions[0].id}:{LOST_FIRST_PASS}")
    ]


def test_a_run_blocked_by_its_cost_limit_gives_the_comparison_up(tmp_path, monkeypatch):
    # The production state of 2026-10-11 (test_rate_limit_refusal's docstring):
    # two held failures, then cost_budget_exhausted at the first pass.
    workflow, principal, ident, _ = one_failed_comparison(tmp_path, monkeypatch, attempts=2)
    later(workflow, 1)
    assert workflow.drain(principal, ident).run.stage == "retry_scheduled"
    leave(workflow, principal, ident, stage="processing_blocked",
          blocker="cost_budget_exhausted", next_retry_at=None)
    later(workflow, 2)

    summary = drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    assert summary["recovered"] == 1
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert requests(tmp_path, "first_pass") == 2
    assert given_up_findings(run) == [
        ("first_pass_given_up", "warning", f"first_pass_given_up:{run.regions[0].id}:cost_budget_exhausted")
    ]
    assert run.usage.reserved_cost_micros <= run.profile.execution.approved_cost_limit_micros


def test_a_dead_lettered_comparison_is_given_up_by_the_drain(tmp_path, monkeypatch):
    workflow, principal, ident, _ = one_failed_comparison(tmp_path, monkeypatch)
    leave(workflow, principal, ident, stage="processing_blocked", dead_letter=True,
          blocker="retry_budget_exhausted:model_rate_limited", next_retry_at=None)
    later(workflow, 1)

    summary = drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    assert summary["recovered"] == 1
    assert (run.stage, run.disposition, run.dead_letter) == ("finalized", Disposition.REVIEW, False)
    assert given_up_findings(run) == [
        ("first_pass_given_up", "warning", f"first_pass_given_up:{run.regions[0].id}:model_rate_limited")
    ]
    assert requests(tmp_path, "first_pass") == 1


def test_a_lane_stall_at_a_comparison_is_recovered_at_most_three_times(tmp_path, monkeypatch):
    # (d) lane_run_not_progressing: due again, a bounded number of times.
    workflow, principal, ident, adapter = one_failed_comparison(tmp_path, monkeypatch)
    step = comparison_step(workflow.repository.get(principal.scope, ident).run)
    used = [{"step": step, "blocker": "lane_run_not_progressing", "attempt": 1, "at": "x"}]
    leave(workflow, principal, ident, stage="processing_blocked",
          blocker="lane_run_not_progressing", next_retry_at=None)
    later(workflow, 1)
    assert drain_worker(workflow, principal)["recovered"] == 1
    assert_compared(workflow.repository.get(principal.scope, ident).run, adapter, step)

    specimen = workflow.repository.get(principal.scope, ident)
    capped = specimen.model_copy(deep=True)
    capped.run.dependencies[AUTOMATIC_RECOVERIES] = used * MAX_AUTOMATIC_RECOVERIES
    capped.run.stage, capped.run.blocker, capped.run.disposition = (
        "processing_blocked", "lane_run_not_progressing", None
    )
    capped.run.completed_steps = [s for s in capped.run.completed_steps if s.split(":")[0] in {
        "pin_dependencies", "classify", "quality_check", "segment", "transcribe"}]
    workflow.repository.save(principal, capped, specimen.version, "capped", digest({"capped": 1}))
    assert workflow.recover_blocked(principal, ident) is False


def test_evidence_pilot_and_other_steps_are_never_recovered(tmp_path, monkeypatch):
    workflow, principal, ident, _ = one_failed_comparison(tmp_path, monkeypatch)
    specimen = workflow.repository.get(principal.scope, ident)
    pilot = {**specimen.run.dependencies, "evidence_pilot": {}}
    leave(workflow, principal, ident, stage="processing_blocked",
          blocker="external_outcome_unknown", next_retry_at=None, dependencies=pilot)
    later(workflow, 1)
    assert workflow.recover_blocked(principal, ident) is False

    leave(workflow, principal, ident, dependencies=specimen.run.dependencies,
          blocker="model_authentication_error")
    assert workflow.recover_blocked(principal, ident) is False
    after = workflow.repository.get(principal.scope, ident).run
    assert (after.stage, after.blocker) == ("processing_blocked", "model_authentication_error")


def test_the_connector_listing_names_only_blocked_unfinished_records():
    pages = [
        [{"id": f"00000000-0000-0000-0000-{n:012d}", "state": "running", "disposition": None,
          "sensitive": False} for n in range(99)]
        + [{"id": "00000000-0000-0000-0000-000000000099", "state": "processing_blocked",
            "disposition": None, "sensitive": False}],
        [
            {"id": "00000000-0000-0000-0000-000000000100", "state": "processing_blocked",
             "disposition": "human_review", "sensitive": False},
            {"id": "00000000-0000-0000-0000-000000000101", "state": "processing_blocked",
             "disposition": None, "sensitive": False},
        ],
    ]
    calls = []
    repository = object.__new__(SqlConnectRepository)
    repository.variables = lambda scope: {"organizationId": "o", "collectionId": "c", "actorUid": "u"}

    def execute(operation, variables, **_):
        calls.append((operation, variables["afterId"], variables["includeSensitive"], variables["limit"]))
        return {"specimens": pages[len(calls) - 1]}

    repository.execute = execute

    found = repository.blocked_ids(None)

    assert found == ["00000000-0000-0000-0000-000000000099", "00000000-0000-0000-0000-000000000101"]
    assert calls == [
        ("ListSpecimenPage", "", False, 100),
        ("ListSpecimenPage", "00000000-0000-0000-0000-000000000099", False, 100),
    ]
