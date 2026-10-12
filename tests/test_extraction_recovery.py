"""The organiser's extraction recovers, or is given up on, by itself.

Production, 2026-10-12 13:00Z-13:34Z, collection 200d7057: the extraction call
of `parse` (agent insects_bounded_extractor, Qwen3-VL-30B-A3B-Instruct on the
handwriting-qwen route) was answered HTTP 504 `provider_request_failed` after
120 s for five of six camera-intake runs (66a72095, b191ed67, 1d842828,
74efda01, 3781e440). A 5xx is an unknown outcome, and before this change any
failure of that call blocked the run as `external_outcome_unknown` with no
retry and no recovery: the run stayed in intake. Specimen 19f0f1f6's first pass
answered malformed twice ("Exceeded maximum output retries (1)") and blocked as
`model_malformed_response`, also with no way on.

These tests drive the real isolated model child (`model_runtime.invoke_model`)
with the offline fixture provider of `test_rate_limit_refusal.py`, in the lab of
`test_lane_routes.py` (the published pilot profile's prices and pins, both
ledgers wired as production wires them). No live model request is made.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from specimen_digitization.application import model_runtime
from specimen_digitization.application.domain import Disposition
from specimen_digitization.application.production import ProductionAdapters
from specimen_digitization.application.storage import LocalBlobs, digest

from test_first_pass_given_up import given_up_findings
from test_first_pass_stuck_recovery import drain_worker, later
from test_first_pass_transient_recovery import comparison_lab, comparison_step
from test_lane_routes import PARSE_RESERVATION
from test_rate_limit_refusal import FAILURE, ChildLab, drains, lab, requests


class ExtractionLab(ChildLab):
    """The lab whose first `extracts` extraction calls go to the real model child
    and its fixture provider; a later call answers with no candidates."""

    def __init__(self, blobs, *, extracts=0):
        super().__init__(blobs)
        self.child_extracts = extracts

    def extract(self, specimen):
        if self.child_extracts:
            self.child_extracts -= 1
            self.overrun(specimen, "parse")
            return ProductionAdapters.extract(self, specimen)
        return None


def stalled_extraction_child(payload):
    """A child that has entered its extraction but never returns before cutoff."""
    root = Path(payload["storage"]["root"]).parent
    with (root / "requests-extract").open("a") as sent:
        sent.write(str(os.getpid()) + "\n")
    time.sleep(60)
    raise AssertionError("the parent must terminate this child")


def extraction_lab(tmp_path, monkeypatch, failure, extracts):
    adapters = ExtractionLab(LocalBlobs(tmp_path / "blobs"), extracts=extracts)
    if failure == "deadline":
        adapters.model_effect = stalled_extraction_child
        real_isolated = model_runtime.run_isolated

        def shortened(effect, payload, timeout, *args, **kwargs):
            return real_isolated(effect, payload, 3, *args, **kwargs)

        monkeypatch.setattr(model_runtime, "run_isolated", shortened)
    workflow, principal, ident, backend = lab(
        tmp_path, monkeypatch, adapters, "http_504" if failure == "deadline" else failure
    )
    return workflow, principal, ident, backend, adapters


def failure_code(failure):
    return "extract_deadline_exceeded" if failure == "deadline" else "model_provider_error"


def sent(tmp_path, failure, calls):
    """Whether the fixture provider was sent `calls` extraction requests. A
    stalled child writes its line before it waits, but under load the parent's
    3 s cutoff can stop it first: the attempts and the cost rows count those."""
    made = requests(tmp_path, "extract")
    return made <= calls if failure == "deadline" else made == calls


def extraction_findings(run):
    return [f.reason_code for f in run.findings if f.rule_id == "extraction_given_up"]


def parse_calls(run):
    return [
        (c["attempt"], c["outcome"], c["cost_basis"], c["cost_micros"], c.get("failure_code"))
        for c in run.paid_calls
        if c["step"] == "parse"
    ]


@pytest.mark.parametrize("failure", ["http_504", "deadline"])
def test_a_failed_extraction_is_retried_and_the_run_reaches_its_disposition(
    tmp_path, monkeypatch, failure
):
    workflow, principal, ident, backend, _ = extraction_lab(tmp_path, monkeypatch, failure, 1)

    first, last = drains(workflow, principal, ident, backend)

    # Before: processing_blocked as external_outcome_unknown, with no retry.
    assert (first.run.stage, first.run.blocker) == ("retry_scheduled", failure_code(failure))
    assert first.run.lease_until is None
    run = last.run
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert run.attempts["parse"] == 2 and sent(tmp_path, failure, 1)
    # Every attempt resolved: no unknown-outcome kind is left behind (#146).
    assert "unknown_outcome_kinds" not in run.dependencies
    assert extraction_findings(run) == []
    # The uncertain first attempt keeps its whole reservation.
    assert parse_calls(run)[0] == (1, "failed", "reserved", PARSE_RESERVATION, failure_code(failure))
    assert last.research["ordinary_reservations"]["parse:1"] == {
        "reserved_micros": PARSE_RESERVATION, "settled_micros": None
    }


@pytest.mark.parametrize("failure", ["http_504", "deadline"])
def test_an_extraction_that_keeps_failing_is_given_up_and_the_record_goes_to_review(
    tmp_path, monkeypatch, failure
):
    workflow, principal, ident, backend, _ = extraction_lab(tmp_path, monkeypatch, failure, 3)

    *retried, last = drains(workflow, principal, ident, backend)

    run = last.run
    assert [d.run.stage for d in retried] == ["retry_scheduled"] * 2
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert run.attempts["parse"] == 3 and sent(tmp_path, failure, 3)
    assert extraction_findings(run) == [f"extraction_given_up:{failure_code(failure)}"]
    assert "parse" in run.completed_steps and "finalize" in run.completed_steps
    assert parse_calls(run) == [
        (n, "failed", "reserved", PARSE_RESERVATION, failure_code(failure)) for n in (1, 2, 3)
    ]
    for attempt in (1, 2, 3):
        assert last.research["ordinary_reservations"][f"parse:{attempt}"]["settled_micros"] is None
    assert run.usage.reserved_cost_micros <= run.profile.execution.approved_cost_limit_micros


def test_a_malformed_extraction_is_given_up_at_once(tmp_path, monkeypatch):
    workflow, principal, ident, backend, _ = extraction_lab(tmp_path, monkeypatch, "malformed", 1)

    specimen = workflow.drain(principal, ident)

    run = specimen.run
    # Before: processing_blocked as model_malformed_response, with no retry.
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert run.attempts["parse"] == 1 and requests(tmp_path, "extract") == 2
    assert extraction_findings(run) == ["extraction_given_up:model_malformed_response"]
    assert parse_calls(run) == [(1, "failed", "reserved", PARSE_RESERVATION, "model_malformed_response")]


def test_an_extraction_stopped_by_its_limits_is_given_up_at_once(tmp_path, monkeypatch):
    from pydantic_ai.exceptions import UsageLimitExceeded

    from specimen_digitization.application import harness

    def stopped(agent, prompt, **_):
        raise UsageLimitExceeded("The answer was cut off at its output cap")

    # The organiser's call, in this process: the child's mapping is shown by
    # test_reader_failures_recoverable for a reader's `stopped` status.
    monkeypatch.setattr(harness, "run_agent_bounded", stopped)
    workflow, principal, ident, backend, adapters = extraction_lab(tmp_path, monkeypatch, "http_504", 0)
    monkeypatch.setattr(
        type(adapters), "extract", lambda self, specimen: ProductionAdapters._extract_direct(self, specimen)
    )
    monkeypatch.setattr(
        "specimen_digitization.application.production.HuggingFaceModelGateway", _NoCallGateway
    )

    run = workflow.drain(principal, ident).run

    # Before: an exception the workflow did not know, so external_outcome_unknown.
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert run.attempts["parse"] == 1
    assert extraction_findings(run) == ["extraction_given_up:extraction_usage_limit"]
    assert parse_calls(run) == [(1, "failed", "reserved", PARSE_RESERVATION, "extraction_usage_limit")]


class _NoCallGateway:
    """The production gateway's pins, with a model that is never asked."""

    def __init__(self, timeout_seconds=None):
        from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES

        self.routes = dict(HUGGINGFACE_ROUTES)

    def route(self, route_id):
        return self.routes[route_id]

    def model_for(self, route_id):
        from pydantic_ai.models.test import TestModel

        return TestModel()


def blocked_at_parse(workflow, principal, ident, **state):
    """Save the run as the code before 2026-10-12 left it after its extraction
    failed: blocked at parse, its lease over."""
    specimen = workflow.repository.get(principal.scope, ident)
    run = specimen.run
    run.stage, run.next_retry_at, run.lease_until, run.disposition = (
        "processing_blocked", None, None, None
    )
    for key, value in state.items():
        setattr(run, key, value)
    return workflow.repository.save(
        principal, specimen, specimen.version, "left-at-parse", digest({"left": sorted(state)})
    )


def as_before_this_change(monkeypatch):
    """The extraction as a6b72f6f ran it: not a recoverable model read, so a
    provider's 5xx is saved as external_outcome_unknown with nothing to say so.
    Returns the undo."""
    from specimen_digitization.application import model_runtime as runtime, workflow as flow

    old = lambda run, step: False  # noqa: E731
    saved = (flow.extraction_failure_is_recoverable, runtime.extraction_failure_is_recoverable)
    reliability = __import__(
        "specimen_digitization.application.reliability", fromlist=["model_read_is_recoverable"]
    )
    read = reliability.model_read_is_recoverable

    def read_before(run, step):
        return step.split(":", 1)[0] not in {"parse", "extract"} and read(run, step)

    monkeypatch.setattr(flow, "extraction_failure_is_recoverable", old)
    monkeypatch.setattr(runtime, "extraction_failure_is_recoverable", old)
    monkeypatch.setattr(flow, "model_read_is_recoverable", read_before)

    def undo():
        flow.extraction_failure_is_recoverable, runtime.extraction_failure_is_recoverable = saved
        flow.model_read_is_recoverable = read

    return undo


def test_a_504_left_unknown_at_the_extraction_by_the_old_code_is_recovered_as_legacy(
    tmp_path, monkeypatch
):
    # 66a72095, b191ed67, 1d842828, 74efda01 and 3781e440: an HTTP 504 at the
    # extraction, saved by a6b72f6f as external_outcome_unknown. That row is what
    # an invalid child result leaves too (compared field by field on a6b72f6f),
    # and it has no unknown-outcome kind: a legacy row. The coordinator's ruling
    # of 2026-10-12: recover it on the bounded path, record the rule, end in
    # review at worst. Here the provider keeps answering 504: the extraction is
    # retried, then given up on.
    workflow, principal, ident, backend, _ = extraction_lab(tmp_path, monkeypatch, "http_504", 3)
    undo = as_before_this_change(monkeypatch)
    first = workflow.drain(principal, ident).run
    undo()
    assert (first.stage, first.blocker, first.reasons) == (
        "processing_blocked", "external_outcome_unknown", []
    )
    [row] = [c for c in first.paid_calls if c["step"] == "parse"]
    assert (row["outcome"], row.get("failure_code")) == ("unknown", None)
    assert "parse:1" not in first.dependencies.get("unknown_outcome_kinds", {})
    later(workflow, 2)

    summary = drain_worker(workflow, principal)
    for hours in (3, 4, 5):
        run = workflow.repository.get(principal.scope, ident).run
        if run.stage == "finalized":
            break
        later(workflow, hours)
        drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    assert summary["recovered"] == 1
    [recovery] = run.dependencies["automatic_recoveries"]
    assert (recovery["step"], recovery["blocker"], recovery["rule"]) == (
        "parse", "external_outcome_unknown", "legacy_unknown_recovered"
    )
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert run.attempts["parse"] == 3 and requests(tmp_path, "extract") == 3
    assert extraction_findings(run) == ["extraction_given_up:model_provider_error"]
    # Every attempt is held in full, and the run stays within its limit.
    assert [(c[0], c[2], c[3]) for c in parse_calls(run)] == [
        (n, "reserved", PARSE_RESERVATION) for n in (1, 2, 3)
    ]
    assert run.usage.reserved_cost_micros <= run.profile.execution.approved_cost_limit_micros


def test_an_extraction_the_old_code_saw_overrun_its_deadline_is_carried_on(tmp_path, monkeypatch):
    # A call that overran the step's effect timeout: a6b72f6f saved the unknown
    # outcome with the reason external_stage_deadline_exceeded, durable
    # evidence of a deadline; the drain makes it due and the run goes on.
    workflow, principal, ident, backend, adapters = extraction_lab(tmp_path, monkeypatch, "http_504", 1)
    adapters.late = True
    workflow.monotonic = lambda: adapters.elapsed[0]
    undo = as_before_this_change(monkeypatch)
    first = workflow.drain(principal, ident).run
    undo()
    adapters.late = False
    assert (first.stage, first.blocker, first.reasons) == (
        "processing_blocked", "external_outcome_unknown", ["external_stage_deadline_exceeded"]
    )
    later(workflow, 2)

    summary = drain_worker(workflow, principal)
    for hours in (3, 4):
        run = workflow.repository.get(principal.scope, ident).run
        if run.stage == "finalized":
            break
        later(workflow, hours)
        drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    assert summary["recovered"] == 1
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    # The lost attempt was recorded once, by the step that saved it.
    assert run.attempts["parse"] == 2 and requests(tmp_path, "extract") == 1
    assert [c[0] for c in parse_calls(run)] == [1, 2]
    assert run.dependencies["automatic_recoveries"][0]["step"] == "parse"


class Stopped(BaseException):
    """The worker process stopping mid-call (a job's time limit, a lost instance)."""


def test_an_extraction_whose_worker_stopped_after_its_intent_is_carried_on(tmp_path, monkeypatch):
    # The intent was saved and the worker stopped before its result: no row for
    # the attempt. a6b72f6f then saved the run blocked as unknown; that missing
    # row is durable evidence that no result, valid or not, was ever seen.
    workflow, principal, ident, backend, adapters = extraction_lab(tmp_path, monkeypatch, "http_504", 0)

    def stop(specimen):
        raise Stopped()

    adapters.extract = stop
    undo = as_before_this_change(monkeypatch)
    with pytest.raises(Stopped):
        workflow.drain(principal, ident)
    later(workflow, 1)  # The lease ends; the old code parks the run.
    parked = workflow.drain(principal, ident).run
    undo()
    del adapters.extract
    assert (parked.stage, parked.blocker) == ("processing_blocked", "external_outcome_unknown")
    assert parked.attempts["parse"] == 1 and parse_calls(parked) == []
    assert "parse:1" not in parked.dependencies.get("unknown_outcome_kinds", {})  # A legacy row.
    later(workflow, 2)

    summary = drain_worker(workflow, principal)
    for hours in (3, 4):
        run = workflow.repository.get(principal.scope, ident).run
        if run.stage == "finalized":
            break
        later(workflow, hours)
        drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    assert summary["recovered"] == 1
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert run.attempts["parse"] == 2
    assert [(c[0], c[1], c[4]) for c in parse_calls(run)][0] == (1, "failed", "extraction_result_lost")


def test_a_lost_last_extraction_is_given_up_by_the_drain(tmp_path, monkeypatch):
    # The worker stopped after the last attempt's intent: settled as lost, then
    # given up on, without another call.
    workflow, principal, ident, backend, _ = extraction_lab(tmp_path, monkeypatch, "http_504", 1)
    first = workflow.drain(principal, ident).run
    attempts = {**first.attempts, "parse": first.profile.execution.max_attempts}
    blocked_at_parse(workflow, principal, ident, blocker="external_outcome_unknown", attempts=attempts)
    later(workflow, 1)

    summary = drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    assert summary["recovered"] == 1
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert extraction_findings(run) == ["extraction_given_up:extraction_result_lost"]
    assert requests(tmp_path, "extract") == 1
    assert parse_calls(run)[-1] == (3, "failed", "reserved", PARSE_RESERVATION, "extraction_result_lost")


@pytest.mark.parametrize(
    "blocker", ["retry_budget_exhausted:model_rate_limited", "model_malformed_response"]
)
def test_a_run_left_dead_at_its_extraction_is_given_up_by_the_drain(tmp_path, monkeypatch, blocker):
    workflow, principal, ident, backend, _ = extraction_lab(tmp_path, monkeypatch, "http_504", 1)
    workflow.drain(principal, ident)
    blocked_at_parse(workflow, principal, ident, blocker=blocker, dead_letter=True)
    later(workflow, 1)

    summary = drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    assert summary["recovered"] == 1
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert not run.dead_letter
    assert extraction_findings(run) == [
        "extraction_given_up:" + blocker.removeprefix("retry_budget_exhausted:")
    ]
    # Given up, not asked again: parse ran without its call.
    assert requests(tmp_path, "extract") == 1 and run.attempts["parse"] == 1
    assert "parse" in run.completed_steps


def test_an_unaffordable_extraction_is_given_up_unsent(tmp_path, monkeypatch):
    workflow, principal, ident, backend, _ = extraction_lab(tmp_path, monkeypatch, "http_504", 1)
    first = workflow.drain(principal, ident).run
    assert first.stage == "retry_scheduled"
    specimen = workflow.repository.get(principal.scope, ident)
    # Leave the run with no room for another extraction under its USD 1 limit.
    specimen.run.usage.reserved_cost_micros = (
        specimen.run.profile.execution.approved_cost_limit_micros - PARSE_RESERVATION + 1
    )
    workflow.repository.save(principal, specimen, specimen.version, "full", digest({"full": 1}))
    later(workflow, 1)

    run = workflow.drain(principal, ident).run

    # Before: processing_blocked as cost_budget_exhausted.
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert extraction_findings(run) == ["extraction_given_up:cost_budget_exhausted"]
    assert run.attempts["parse"] == 1 and requests(tmp_path, "extract") == 1
    assert "parse" in run.completed_steps
    assert [c[0] for c in parse_calls(run)] == [1]


def test_a_run_left_blocked_at_a_malformed_first_pass_is_given_up_by_the_drain(tmp_path, monkeypatch):
    # 19f0f1f6: blocked at its first pass as model_malformed_response.
    workflow, principal, ident, backend, _ = comparison_lab(tmp_path, monkeypatch, "http_503", 1)
    workflow.drain(principal, ident)
    specimen = workflow.repository.get(principal.scope, ident)
    run = specimen.run
    run.stage, run.blocker, run.next_retry_at = "processing_blocked", "model_malformed_response", None
    workflow.repository.save(principal, specimen, specimen.version, "malformed", digest({"m": 1}))
    later(workflow, 1)

    summary = drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    assert summary["recovered"] == 1
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert given_up_findings(run) == [
        ("first_pass_given_up", "warning",
         f"first_pass_given_up:{run.regions[0].id}:model_malformed_response")
    ]
    assert requests(tmp_path, "first_pass") == 1 and run.attempts[comparison_step(run)] == 1


@pytest.mark.parametrize(
    ("failure", "blocker"),
    [
        ("http_401", "model_authentication_error"),
        ("http_403", "model_authorization_error"),
        ("http_400", "model_request_rejected"),
    ],
)
def test_a_failure_asking_again_would_not_mend_still_blocks_with_its_cause(
    tmp_path, monkeypatch, failure, blocker
):
    workflow, principal, ident, backend, _ = extraction_lab(tmp_path, monkeypatch, failure, 1)

    run = workflow.drain(principal, ident).run

    assert (run.stage, run.blocker) == ("processing_blocked", blocker)
    assert extraction_findings(run) == []
    later(workflow, 1)
    assert workflow.recover_blocked(principal, ident) is False


# ---- a result the parent could not accept stays blocked (review of f8e7c73d) --

def invalid_result(kind):
    """What the isolated child hands back when its result is not acceptable:
    an invalid IPC input, or an extraction whose fields do not match the run's."""
    import json

    from specimen_digitization.application.bounded_effect import IsolatedResult

    if kind == "invalid_json_input":
        return IsolatedResult(
            status="worker_failed", value=None, elapsed_seconds=1, input_bytes=1,
            result_bytes=0, reason="invalid_json_input", cleanup_complete=True,
        )
    body = json.dumps({"status": "completed", "value": {"fields": {}, "evidence": [], "tokens": 0}})
    return IsolatedResult(
        status="completed", value=body.encode(), elapsed_seconds=1, input_bytes=1,
        result_bytes=len(body), reason=None, cleanup_complete=True,
    )


@pytest.mark.parametrize("kind", ["invalid_json_input", "mismatched_fields"])
def test_an_extraction_result_the_parent_cannot_accept_stays_blocked_after_its_lease(
    tmp_path, monkeypatch, kind
):
    workflow, principal, ident, backend, _ = extraction_lab(tmp_path, monkeypatch, "http_504", 1)
    monkeypatch.setattr(model_runtime, "run_isolated", lambda *args, **kwargs: invalid_result(kind))

    first = workflow.drain(principal, ident).run
    assert (first.stage, first.blocker) == ("processing_blocked", "external_outcome_unknown")
    assert first.attempts["parse"] == 1
    later(workflow, 2)  # Well past the lease.

    summary = drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    # On f8e7c73d the drain made it due, settled it as lost and asked again.
    assert summary["recovered"] == 0
    assert (run.stage, run.blocker, run.disposition) == (
        "processing_blocked", "external_outcome_unknown", None
    )
    assert run.attempts["parse"] == 1 and extraction_findings(run) == []
    assert run.dependencies["unknown_outcome_kinds"]["parse:1"] == "held"
    assert workflow.recover_blocked(principal, ident) is False


def test_a_first_pass_result_the_parent_cannot_accept_stays_blocked_after_its_lease(
    tmp_path, monkeypatch
):
    workflow, principal, ident, _, _ = comparison_lab(tmp_path, monkeypatch, "http_503", 1)
    monkeypatch.setattr(
        model_runtime, "run_isolated", lambda *args, **kwargs: invalid_result("invalid_json_input")
    )

    first = workflow.drain(principal, ident).run
    step = comparison_step(first)
    assert (first.stage, first.blocker) == ("processing_blocked", "external_outcome_unknown")
    later(workflow, 2)

    summary = drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    assert summary["recovered"] == 0
    assert (run.stage, run.blocker) == ("processing_blocked", "external_outcome_unknown")
    assert run.attempts[step] == 1 and given_up_findings(run) == []
    assert workflow.recover_blocked(principal, ident) is False


# ---- every unknown outcome this code saves says what it is (2026-10-12) -------

def test_a_call_left_unanswered_by_a_stopped_worker_is_marked_and_carried_on(tmp_path, monkeypatch):
    # The new code's recoverable unknown: the intent is saved as unanswered,
    # the worker stops, and the drain carries the run on once the lease ends,
    # even when something left it processing_blocked.
    workflow, principal, ident, backend, adapters = extraction_lab(tmp_path, monkeypatch, "http_504", 0)

    def stop(specimen):
        raise Stopped()

    adapters.extract = stop
    with pytest.raises(Stopped):
        workflow.drain(principal, ident)
    del adapters.extract
    left = workflow.repository.get(principal.scope, ident).run
    assert left.blocker == "external_outcome_unknown"
    assert left.dependencies["unknown_outcome_kinds"]["parse:1"] == "unanswered"
    blocked_at_parse(workflow, principal, ident, blocker="external_outcome_unknown")
    later(workflow, 2)

    summary = drain_worker(workflow, principal)
    for hours in (3, 4):
        run = workflow.repository.get(principal.scope, ident).run
        if run.stage == "finalized":
            break
        later(workflow, hours)
        drain_worker(workflow, principal)

    run = workflow.repository.get(principal.scope, ident).run
    assert summary["recovered"] == 1
    assert "rule" not in run.dependencies["automatic_recoveries"][0]  # Not a legacy row.
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert run.attempts["parse"] == 2


def kind_checking(workflow):
    """Fail on any save of an ordinary first pass's or extraction's unknown
    outcome that does not say what it is."""
    from specimen_digitization.application.workflow import Workflow

    save = workflow.repository.save
    seen = []

    def checked(principal, specimen, *args, **kwargs):
        run = specimen.run
        step = Workflow.next_step(run)
        if run.blocker == "external_outcome_unknown" and (
            step.startswith("first_pass:") or step == "parse"
        ):
            kind = run.dependencies.get("unknown_outcome_kinds", {}).get(
                f"{step}:{run.attempts.get(step, 0)}"
            )
            assert kind in {"unanswered", "held"}, (step, kind)
            seen.append(kind)
        return save(principal, specimen, *args, **kwargs)

    workflow.repository.save = checked
    return seen


def cleanup_incomplete():
    from specimen_digitization.application.bounded_effect import IsolatedResult

    return IsolatedResult(
        status="deadline_exceeded", value=None, elapsed_seconds=1, input_bytes=1,
        result_bytes=0, reason="deadline_exceeded", cleanup_complete=False,
    )


@pytest.mark.parametrize(
    "path", ["invalid_json_input", "mismatched_fields", "cleanup_incomplete", "parent_exception", "stopped"]
)
def test_every_unknown_outcome_this_code_saves_at_the_extraction_has_a_kind(tmp_path, monkeypatch, path):
    workflow, principal, ident, backend, adapters = extraction_lab(tmp_path, monkeypatch, "http_504", 1)
    seen = kind_checking(workflow)
    if path in {"invalid_json_input", "mismatched_fields"}:
        monkeypatch.setattr(model_runtime, "run_isolated", lambda *a, **k: invalid_result(path))
    elif path == "cleanup_incomplete":
        monkeypatch.setattr(model_runtime, "run_isolated", lambda *a, **k: cleanup_incomplete())
    elif path == "parent_exception":
        def broken(specimen):
            raise RuntimeError("a defect in the parent")

        adapters.extract = broken
    else:
        def stop(specimen):
            raise Stopped()

        adapters.extract = stop

    try:
        workflow.drain(principal, ident)
    except Stopped:
        del adapters.extract  # The next worker runs normally.
    later(workflow, 2)
    drain_worker(workflow, principal)  # Saves again: recovery, settlement, or nothing.

    run = workflow.repository.get(principal.scope, ident).run
    kinds = run.dependencies.get("unknown_outcome_kinds", {})
    if path == "stopped":
        # Settled as a lost attempt: known now, so no longer recorded.
        assert "unanswered" in seen and "parse:1" not in kinds
    else:
        assert kinds["parse:1"] == "held"
    assert seen and set(seen) <= {"unanswered", "held"}


@pytest.mark.parametrize("path", ["invalid_json_input", "cleanup_incomplete", "parent_exception"])
def test_every_unknown_outcome_this_code_saves_at_a_first_pass_has_a_kind(tmp_path, monkeypatch, path):

    workflow, principal, ident, _, adapters = comparison_lab(tmp_path, monkeypatch, "http_503", 1)
    seen = kind_checking(workflow)
    if path == "invalid_json_input":
        monkeypatch.setattr(model_runtime, "run_isolated", lambda *a, **k: invalid_result(path))
    elif path == "cleanup_incomplete":
        monkeypatch.setattr(model_runtime, "run_isolated", lambda *a, **k: cleanup_incomplete())
    else:
        def broken(specimen, region, readings):
            raise RuntimeError("a defect in the parent")

        adapters.first_pass = broken

    run = workflow.drain(principal, ident).run
    step = comparison_step(run)

    assert (run.stage, run.blocker) == ("processing_blocked", "external_outcome_unknown")
    assert run.dependencies["unknown_outcome_kinds"][f"{step}:1"] == "held"
    assert "unanswered" in seen and "held" in seen
    later(workflow, 2)
    assert drain_worker(workflow, principal)["recovered"] == 0
