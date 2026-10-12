"""Ordinary comparisons recover automatically without replaying a publication.

Only the first-pass calls cross the real isolated child here; providers and
the remaining research work are offline fixtures. Both accounting ledgers use
the same reservation hooks as production. No live model requests are made.
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

import pytest

from specimen_digitization.application import model_runtime
from specimen_digitization.application.api import SYNTHETIC_COLLECTION
from specimen_digitization.application.bounded_effect import IsolatedResult
from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Disposition, Profile, Run
from specimen_digitization.application.lane_reservations import step_reservation
from specimen_digitization.application.lane_worker import DrainWorker
from specimen_digitization.application.reliability import first_pass_failure_is_recoverable
from specimen_digitization.application.storage import LocalBlobs, digest
from specimen_digitization.application.workflow import OperationalBlock

import test_rate_limit_refusal
from test_first_pass_given_up import given_up_findings
from test_lane_reservations import with_models
from test_lane_routes import FIRST_PASS_RESERVATION, SAM_RESERVATION, start
from test_rate_limit_refusal import ChildLab, drains, lab, requests


def stalled_comparison_child(payload):
    """A child that has entered its comparison but never returns before cutoff."""
    root = Path(payload["storage"]["root"]).parent
    with (root / "requests-first_pass").open("a") as sent:
        sent.write(str(os.getpid()) + "\n")
    time.sleep(60)
    (root / "late-comparison-result").write_text("must not be applied")
    raise AssertionError("the parent must terminate this child")


def comparison_lab(tmp_path, monkeypatch, failure, attempts, *, small_prices=False):
    if small_prices:
        # A fixture context price, not an increase of the production budget.
        # Three uncertain calls fit so attempt exhaustion can be tested apart
        # from the real profile's earlier financial stop.
        registry = with_models(
            published_registry({SYNTHETIC_COLLECTION: "insects"}),
            **{"first-pass-glm": {"context_tokens": 32_768}},
        )
        monkeypatch.setattr(
            test_rate_limit_refusal, "start", lambda path, adapter: start(path, adapter, registry)
        )
    adapter = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=attempts)
    if failure == "deadline":
        adapter.model_effect = stalled_comparison_child
        real_isolated = model_runtime.run_isolated

        def shortened(effect, payload, timeout, *args, **kwargs):
            return real_isolated(effect, payload, 3, *args, **kwargs)

        monkeypatch.setattr(model_runtime, "run_isolated", shortened)
    result = lab(tmp_path, monkeypatch, adapter, "http_503")
    return (*result, adapter)


def comparison_step(run):
    return "first_pass:" + run.regions[0].id


def failure_code(failure):
    return "first_pass_deadline_exceeded" if failure == "deadline" else "model_provider_error"


def assert_children_stopped(tmp_path, failure):
    if failure != "deadline":
        return
    assert not (tmp_path / "late-comparison-result").exists()
    for line in (tmp_path / "requests-first_pass").read_text().splitlines():
        with pytest.raises(ProcessLookupError):
            os.kill(int(line), 0)


@pytest.mark.parametrize("failure", ["http_503", "deadline"])
def test_comparison_recovers_on_next_attempt_without_repeating_readings(
    tmp_path, monkeypatch, failure
):
    workflow, principal, ident, backend, _ = comparison_lab(tmp_path, monkeypatch, failure, 1)

    first, last = drains(workflow, principal, ident, backend)

    run, step = last.run, comparison_step(last.run)
    assert (first.run.stage, first.run.blocker) == ("retry_scheduled", failure_code(failure))
    assert first.run.lease_until is None
    assert run.stage == "finalized" and run.blocker is None
    assert run.attempts[step] == 2 and len(run.first_pass_decisions) == 1
    assert run.observations == first.run.observations
    assert len(run.observations) == 2
    assert all(count == 1 for key, count in run.attempts.items() if key == "segment" or key.startswith("transcribe:"))
    assert requests(tmp_path, "first_pass") == 1
    first_call, second_call = [call for call in run.paid_calls if call["step"] == step]
    assert (first_call["outcome"], first_call["cost_basis"], first_call["cost_micros"], first_call["failure_code"]) == (
        "failed", "reserved", FIRST_PASS_RESERVATION, failure_code(failure)
    )
    assert (second_call["outcome"], second_call["cost_basis"]) == ("completed", "computed")
    assert run.usage.actual_cost_micros is None
    for drain in (first, last):
        assert drain.research["ordinary_reservations"][f"{step}:1"] == {
            "reserved_micros": FIRST_PASS_RESERVATION, "settled_micros": None
        }
        assert drain.program >= FIRST_PASS_RESERVATION
    assert_children_stopped(tmp_path, failure)


@pytest.mark.parametrize("failure", ["http_503", "deadline"])
def test_exhausted_transient_comparison_keeps_readings_unresolved_for_review(
    tmp_path, monkeypatch, failure
):
    workflow, principal, ident, backend, _ = comparison_lab(
        tmp_path, monkeypatch, failure, 3, small_prices=True
    )

    first, second, last = drains(workflow, principal, ident, backend)

    run, step = last.run, comparison_step(last.run)
    assert [item.run.stage for item in (first, second)] == ["retry_scheduled"] * 2
    assert run.attempts[step] == 3 and requests(tmp_path, "first_pass") == 3
    assert (run.stage, run.disposition, run.blocker) == ("finalized", Disposition.REVIEW, None)
    assert run.observations == first.run.observations
    assert not run.first_pass_decisions
    transcript = run.transcripts[0]
    assert transcript.text is None and not transcript.resolved
    assert set(transcript.alternatives) == {reading.literal_text for reading in run.observations}
    assert f"unresolved_transcription:{run.regions[0].id}" in run.reasons
    assert given_up_findings(run) == [
        ("first_pass_given_up", "warning", f"first_pass_given_up:{run.regions[0].id}:{failure_code(failure)}")
    ]
    assert {"adjudicate", "parse", "finalize"} <= set(run.completed_steps)
    held = step_reservation(run, step)
    calls = [call for call in run.paid_calls if call["step"] == step]
    assert [(call["attempt"], call["outcome"], call["cost_basis"], call["cost_micros"]) for call in calls] == [
        (attempt, "failed", "reserved", held) for attempt in (1, 2, 3)
    ]
    assert all(call["failure_code"] == failure_code(failure) for call in calls)
    for attempt in (1, 2, 3):
        assert last.research["ordinary_reservations"][f"{step}:{attempt}"] == {
            "reserved_micros": held, "settled_micros": None
        }
    assert last.program >= 3 * held and run.usage.actual_cost_micros is None
    assert_children_stopped(tmp_path, failure)


@pytest.mark.parametrize("failure", ["http_503", "deadline"])
def test_published_budget_stops_before_an_unaffordable_third_comparison(
    tmp_path, monkeypatch, failure
):
    workflow, principal, ident, backend, _ = comparison_lab(tmp_path, monkeypatch, failure, 3)

    *retried, last = drains(workflow, principal, ident, backend)

    run, step = last.run, comparison_step(last.run)
    assert len(retried) == 2
    assert (run.stage, run.blocker, run.disposition) == ("processing_blocked", "cost_budget_exhausted", None)
    assert run.attempts[step] == 2 and requests(tmp_path, "first_pass") == 2
    assert run.usage.reserved_cost_micros == SAM_RESERVATION + 2 * FIRST_PASS_RESERVATION
    assert run.usage.reserved_cost_micros + FIRST_PASS_RESERVATION > run.profile.execution.approved_cost_limit_micros
    assert given_up_findings(run) == []
    assert last.program == run.usage.reserved_cost_micros
    assert all(last.research["ordinary_reservations"][f"{step}:{attempt}"]["settled_micros"] is None for attempt in (1, 2))
    assert_children_stopped(tmp_path, failure)


@pytest.mark.parametrize("operation", ["extract", "parse", "field_research", "finalize", "publish", "segment"])
def test_effectful_operations_are_not_comparison_recovery(operation):
    run = Run(profile=Profile())
    assert not first_pass_failure_is_recoverable(run, operation)
    assert isinstance(model_runtime.child_without_answer(run, operation, "deadline_exceeded"), OperationalBlock)


def test_evidence_pilot_is_not_automatically_repeated():
    run = Run(profile=Profile(), dependencies={"evidence_pilot": {}})
    assert not first_pass_failure_is_recoverable(run, "first_pass:region")
    assert isinstance(model_runtime.child_without_answer(run, "first_pass", "deadline_exceeded"), OperationalBlock)


@pytest.mark.parametrize("reason", ["unrecognized_answer", "output_limit", "cleanup_incomplete", "worker_failed"])
def test_invalid_child_contract_is_not_retried_as_a_provider_failure(reason):
    run = Run(profile=Profile())
    assert isinstance(model_runtime.child_without_answer(run, "first_pass", reason), OperationalBlock)


@pytest.mark.parametrize("reason", [
    "input_limit", "invalid_json_input", "invalid_worker_control",
    "missing_worker_output", "worker_call_failed", "worker_transport_failed",
])
def test_invalid_isolated_result_is_not_retried_via_generic_worker_failed(tmp_path, monkeypatch, reason):
    workflow, principal, ident, _, _ = comparison_lab(tmp_path, monkeypatch, "http_503", 1)
    monkeypatch.setattr(model_runtime, "run_isolated", lambda *args, **kwargs: IsolatedResult(
        status="worker_failed", value=None, elapsed_seconds=1, input_bytes=1,
        result_bytes=0, reason=reason, cleanup_complete=True,
    ))

    run = workflow.drain(principal, ident).run

    assert (run.stage, run.blocker) == ("processing_blocked", "external_outcome_unknown")
    assert run.attempts[comparison_step(run)] == 1
    assert requests(tmp_path, "first_pass") == 0
    assert run.usage.reserved_cost_micros == SAM_RESERVATION + FIRST_PASS_RESERVATION


@pytest.mark.parametrize("stage", ["first_pass", "processing_blocked"])
def test_uncertain_existing_comparison_stays_blocked(tmp_path, monkeypatch, stage):
    workflow, principal, ident, _, _ = comparison_lab(tmp_path, monkeypatch, "http_503", 2)
    specimen = workflow.drain(principal, ident)
    specimen.run.stage = stage
    specimen.run.blocker = "external_outcome_unknown"
    specimen = workflow.repository.save(principal, specimen, specimen.version, "old-unknown", digest({"old": True}))

    after = workflow.drain(principal, ident)

    assert (after.run.stage, after.run.blocker) == ("processing_blocked", "external_outcome_unknown")
    assert after.run.attempts == specimen.run.attempts
    assert after.run.observations == specimen.run.observations
    assert after.run.paid_calls == specimen.run.paid_calls
    assert requests(tmp_path, "first_pass") == 1


def test_child_cleanup_must_be_proven_before_comparison_retry(tmp_path, monkeypatch):
    workflow, principal, ident, _, _ = comparison_lab(tmp_path, monkeypatch, "http_503", 1)
    monkeypatch.setattr(model_runtime, "run_isolated", lambda *args, **kwargs: IsolatedResult(
        status="deadline_exceeded", value=None, elapsed_seconds=1, input_bytes=1,
        result_bytes=0, reason="cleanup incomplete", cleanup_complete=False,
    ))

    run = workflow.drain(principal, ident).run

    assert (run.stage, run.blocker) == ("processing_blocked", "external_outcome_unknown")
    assert run.attempts[comparison_step(run)] == 1
    assert requests(tmp_path, "first_pass") == 0
    assert run.usage.reserved_cost_micros == SAM_RESERVATION + FIRST_PASS_RESERVATION


def test_existing_worker_automatically_waits_and_finishes_comparison_retry(tmp_path, monkeypatch):
    workflow, principal, ident, _, _ = comparison_lab(tmp_path, monkeypatch, "http_503", 1)
    moment = [datetime.now(timezone.utc) + timedelta(seconds=2)]
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        moment[0] += timedelta(seconds=seconds)

    workflow.clock = lambda: moment[0]
    worker = DrainWorker(
        workflow.repository, workflow, principal.user_id,
        lambda user: [{**principal.scope.model_dump(), "role": principal.role}],
        execution_id="comparison-recovery-fixture", clock=workflow.clock, sleep=sleep,
    )

    summary = worker.run()

    run = workflow.repository.get(principal.scope, ident).run
    assert summary["status"] == "drained" and summary["processed"] == [ident]
    assert summary["pending_retries"] == 0
    assert waits and all(seconds > 0 for seconds in waits)
    assert run.stage == "finalized" and run.blocker is None
    assert run.attempts[comparison_step(run)] == 2
    assert len(run.first_pass_decisions) == 1 and len(run.observations) == 2
