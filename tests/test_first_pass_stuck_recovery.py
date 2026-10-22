"""Runs stuck at an ordinary first pass reach their disposition with no action.

2026-10-12: DeepInfra refused most first-pass calls (HTTP 429 and 503), the
route moved to Novita (0977e9c0), and camera-intake runs were left at their
first pass. Each test below builds one of the states such a run can be left in,
as the code that ran then saved it, and shows the normal drain carrying it on:
no run action, no admin script, no new service. The first-pass calls that
reach a provider go through the real isolated model child with an offline
fixture provider (test_rate_limit_refusal); no live model request is made.
"""

import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

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
    # lease left set, no unknown-outcome kind. A legacy row: recovered on the
    # bounded path and recorded as such (workflow.unknown_outcome_recoverable).
    workflow, principal, ident, adapter = one_failed_comparison(tmp_path, monkeypatch)
    # That code wrote no unknown-outcome kinds.
    legacy = {
        k: v for k, v in workflow.repository.get(principal.scope, ident).run.dependencies.items()
        if k != "unknown_outcome_kinds"
    }
    before = leave(workflow, principal, ident, stage="processing_blocked",
                   blocker="external_outcome_unknown", next_retry_at=None, dependencies=legacy,
                   lease_until=datetime.now(timezone.utc).isoformat())
    step = comparison_step(before.run)
    later(workflow, 1)

    summary = drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    assert summary["recovered"] == 1
    assert run.dependencies[AUTOMATIC_RECOVERIES][0]["rule"] == "legacy_unknown_recovered"
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


@pytest.mark.parametrize("kind", ["first_pass", "extraction", "field_research"])
@pytest.mark.parametrize("used,allowed", [(2, True), (3, False), (4, False)])
def test_literal_three_recovery_policy_has_no_extra_effects(
    tmp_path, monkeypatch, kind, used, allowed
):
    # These counts are policy expectations, independent of the production cap.
    # Reach each real workflow step with offline adapters before leaving a
    # stalled row. The older child/provider recovery journeys stay above.
    from specimen_digitization.application.storage import LocalBlobs
    from specimen_digitization.application.lane_allowance import ProgramLedger
    from test_rate_limit_refusal import ChildLab, lab, research_state

    adapter = ChildLab(LocalBlobs(tmp_path / "blobs"))
    adapter.extract = Mock(return_value=None)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapter, "http_503")
    target = {"first_pass": "first_pass", "extraction": "parse", "field_research": "plan"}[kind]
    for _ in range(20):
        specimen = workflow.repository.get(principal.scope, ident)
        step = workflow.next_step(specimen.run)
        if step.split(":")[0] == target:
            break
        workflow.step(principal, ident)
    assert step.split(":")[0] == target, f"fixture did not reach {kind}"
    research = Mock()
    research.handles.return_value = True
    workflow.field_research = research if kind == "field_research" else None
    recovery_step = "field_research" if kind == "field_research" else step
    blocker = "token_budget_exhausted" if kind == "field_research" else "lane_run_not_progressing"
    history = [
        {"step": recovery_step, "blocker": blocker, "attempt": 1, "at": "2026-10-01T00:00:00+00:00"}
        for _ in range(used)
    ]
    # Unrelated steps do not spend this step's recovery allowance.
    history.append({"step": "another-step", "blocker": blocker, "attempt": 1, "at": "x"})
    before = leave(
        workflow, principal, ident, stage="processing_blocked", blocker=blocker,
        next_retry_at=None, lease_until=None,
        dependencies={**specimen.run.dependencies, AUTOMATIC_RECOVERIES: history},
    )
    assert before.run.usage.reserved_cost_micros > 0, "fixture must retain an existing liability"
    program_before = research_state(backend, before)
    ledger = ProgramLedger(workflow.repository, principal.scope)
    ledger_before = ledger.read()
    save = Mock(wraps=workflow.repository.save)
    monkeypatch.setattr(workflow.repository, "save", save)
    first_pass = Mock(wraps=adapter.first_pass)
    monkeypatch.setattr(adapter, "first_pass", first_pass)
    adapter.extract.reset_mock()
    settle = Mock(wraps=workflow.settle_retained_cost)
    reserve = Mock(wraps=workflow.reserve_retained_cost)
    monkeypatch.setattr(workflow, "settle_retained_cost", settle)
    monkeypatch.setattr(workflow, "reserve_retained_cost", reserve)

    recovered = workflow.recover_blocked(principal, ident)
    after = workflow.repository.get(principal.scope, ident)

    # Check effects before the boolean so an admitted fourth recovery reports
    # the forbidden durable save, rather than only a return-value mismatch.
    assert save.call_count == int(allowed), f"{kind}: history {used} must allow {int(allowed)} save(s)"
    assert recovered is allowed, f"{kind}: only histories below three may recover"
    first_pass.assert_not_called()
    adapter.extract.assert_not_called()
    research.run.assert_not_called()
    settle.assert_not_called()
    reserve.assert_not_called()
    assert after.run.usage == before.run.usage, "recovery must neither add nor release liability"
    assert after.run.paid_calls == before.run.paid_calls
    assert research_state(backend, after) == program_before, "program liability must stay held"
    assert ledger.read() == ledger_before, "collection liability must stay held"
    if allowed:
        assert after.version == before.version + 1
        assert after.run.stage == "retry_scheduled"
        assert after.run.next_retry_at is not None
        assert after.run.dependencies[AUTOMATIC_RECOVERIES][:-1] == history
        assert after.run.dependencies[AUTOMATIC_RECOVERIES][-1]["step"] == recovery_step
        assert len(after.run.dependencies[AUTOMATIC_RECOVERIES]) == 4
    else:
        assert after == before, "a refused fourth or later recovery must not change the record"


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


def test_sensitive_and_finished_records_are_never_recovered(tmp_path, monkeypatch):
    workflow, principal, ident, _ = one_failed_comparison(tmp_path, monkeypatch)
    blocked = dict(stage="processing_blocked", blocker="external_outcome_unknown", next_retry_at=None)
    leave(workflow, principal, ident, disposition=list(Disposition)[0], **blocked)
    later(workflow, 1)
    assert workflow.recover_blocked(principal, ident) is False

    leave(workflow, principal, ident, disposition=None)
    specimen = workflow.repository.get(principal.scope, ident)
    specimen.asset.sensitive = True
    workflow.repository.save(principal, specimen, specimen.version, "sensitive", digest({"sensitive": True}))
    assert workflow.recover_blocked(principal, ident) is False
    after = workflow.repository.get(principal.scope, ident).run
    assert (after.stage, after.blocker) == ("processing_blocked", "external_outcome_unknown")
    assert AUTOMATIC_RECOVERIES not in after.dependencies


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

    found = [ident for page in repository.blocked_ids(None) for ident in page]

    assert found == ["00000000-0000-0000-0000-000000000099", "00000000-0000-0000-0000-000000000101"]
    assert calls == [
        ("ListSpecimenPage", "", False, 100),
        ("ListSpecimenPage", "00000000-0000-0000-0000-000000000099", False, 100),
    ]


class ScanFixture:
    """A collection of blocked records listed page by page, and a workflow
    that recovers each one it is given."""

    def __init__(self, pages):
        self.pages, self.read, self.recovered = pages, 0, []
        self.now = datetime(2026, 10, 12, tzinfo=timezone.utc)

    def blocked_ids(self, scope):
        for page in self.pages:
            self.read += 1
            yield page

    def recover_blocked(self, principal, ident):
        self.recovered.append(ident)
        self.now += timedelta(seconds=30)
        return True

    def worker(self):
        worker = DrainWorker(
            self, self, "u", lambda user: [],
            execution_id="scan-fixture", clock=lambda: self.now, sleep=lambda s: None,
        )
        worker.close_at = self.now + timedelta(seconds=45)
        return worker


def scan_drain():
    return SimpleNamespace(principal=SimpleNamespace(scope=None), retries={})


def test_the_blocked_scan_ends_at_a_stop_and_reads_no_further_page():
    # A SIGTERM during the scan must leave the drain time to release its fence
    # and hand the rest on, so the scan stops before the next record or page.
    fixture = ScanFixture([["a", "b"], ["c"]])
    worker = fixture.worker()
    worker.close_at = fixture.now + timedelta(hours=1)
    stop = threading.Event()
    original = fixture.recover_blocked

    def recover_then_stop(principal, ident):
        stop.set()
        return original(principal, ident)

    fixture.recover_blocked = recover_then_stop
    assert worker._recover_blocked(scan_drain(), stop) == 1
    assert fixture.recovered == ["a"] and fixture.read == 1


def test_the_blocked_scan_ends_at_the_window_close():
    # Each recovery here takes 30 s and the window closes 45 s in: two are
    # recovered, the rest wait for the next execution, the last page unread.
    fixture = ScanFixture([["a", "b", "c"], ["d"]])
    assert fixture.worker()._recover_blocked(scan_drain()) == 2
    assert fixture.recovered == ["a", "b"] and fixture.read == 1


def test_the_blocked_scan_stops_after_a_page_with_no_blocked_record():
    # A full page of running or finished records lists no candidate; the scan
    # still checks the window between pages, so a collection of such records
    # cannot run it past the close.
    fixture = ScanFixture([[], [], ["a"]])
    worker = fixture.worker()
    worker.close_at = fixture.now
    assert worker._recover_blocked(scan_drain()) == 0
    assert fixture.read == 1

    fixture = ScanFixture([[], [], ["a"]])
    stop = threading.Event()
    stop.set()
    worker = fixture.worker()
    assert worker._recover_blocked(scan_drain(), stop) == 0
    assert fixture.read == 1
