"""A first pass whose last attempt fails with a retried failure is given up on (G6).

Production, 2026-10-11, specimen 105526323, run 33e6f0fc: after segmentation and
four readings, the first pass (route `first-pass-glm`) was answered HTTP 429 on
all three attempts. Each refusal cost nothing (#311), but the third used up
`max_attempts`, so the run ended `processing_blocked` as
`retry_budget_exhausted:model_rate_limited`, dead-lettered with no disposition:
in no review queue, and field research never ran.

A first pass given up on now ends as a reader given up on does
(tests/test_reader_failures_recoverable.py): its step completes with no
decision, the label's transcript stays unresolved with both readings, a warning
finding names the failure, and the run goes on to its queue decision, which
sends the record to review. A failure that is not retried, or whose outcome is
unknown, still blocks and names its cause.

The lab is tests/test_rate_limit_refusal.py's: the real isolated model child
with a fixture provider, the published pilot profile's prices and pins, and
both ledgers wired as production wires them.
"""

from datetime import datetime, timedelta, timezone

import pytest

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_TEXT,
    summary,
)
from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import (
    Disposition,
    LookupStatus,
    Profile,
    Run,
)
from specimen_digitization.application.lane_reservations import step_reservation
from specimen_digitization.application.reliability import AdapterFailure, retry_delay
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.workflow import Workflow

import test_rate_limit_refusal
from test_lane_reservations import with_models
from test_lane_routes import FIRST_PASS_RESERVATION, start
from test_rate_limit_refusal import (
    FAILURE,
    ChildLab,
    drains,
    lab,
    ledger_rows,
    requests,
    research_state,
)

GIVEN_UP = "first_pass_given_up"


def given_up_findings(run):
    return [
        (f.rule_id, f.severity, f.reason_code) for f in run.findings if f.rule_id == GIVEN_UP
    ]


def first_pass_step(run):
    return "first_pass:" + run.regions[0].id


def test_three_first_pass_refusals_give_up_and_the_record_goes_to_review(
    tmp_path, monkeypatch
):
    # 105526323: the first pass answered 429 on every attempt.
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=3)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "http_429")

    *retried, last = drains(workflow, principal, ident, backend)

    run = last.run
    region = run.regions[0].id
    step = first_pass_step(run)
    for drain in retried:
        assert (drain.run.stage, drain.run.blocker) == ("retry_scheduled", "model_rate_limited")
    assert requests(tmp_path, "first_pass") == 3
    # Before this change: processing_blocked, dead-lettered with no disposition.
    assert not run.dead_letter and run.blocker is None, run.blocker
    assert (run.stage, run.disposition) == ("finalized", Disposition.REVIEW)
    assert run.attempts[step] == 3
    steps = run.completed_steps
    assert step in steps
    assert steps.index(step) < steps.index("adjudicate") < steps.index("parse")
    assert {"plan", "lookup", "finalize"} <= set(steps)
    # No decision: the label keeps both readings, unresolved, as the first pass
    # leaves a label it cannot decide.
    assert run.first_pass_decisions == []
    [transcript] = run.transcripts
    readings = [o for o in run.observations if o.region_id == region]
    assert len(readings) == 2
    assert (transcript.text, transcript.resolved, transcript.decision_kind) == (None, False, None)
    assert transcript.observation_ids == [o.id for o in readings]
    assert transcript.alternatives == [SYNTHETIC_TEXT, SYNTHETIC_TEXT + " 1946"]
    # Why, beside the record; and the reason that sends it to review.
    assert given_up_findings(run) == [
        (GIVEN_UP, "warning", f"{GIVEN_UP}:{region}:model_rate_limited")
    ]
    assert f"unresolved_transcription:{region}" in run.reasons
    # Every refusal, the last one too, cost nothing (#311).
    calls = [c for c in run.paid_calls if c["step"] == step]
    assert ledger_rows(calls) == [
        (n, "failed", "refused", 0, None, "model_rate_limited") for n in (1, 2, 3)
    ]
    reservations = last.research["ordinary_reservations"]
    assert [reservations[f"{step}:{n}"]["settled_micros"] for n in (1, 2, 3)] == [0, 0, 0]
    # The record's summary: a completed run waiting for a person.
    record = summary(workflow.repository.get(principal.scope, ident))
    assert (record["status"], record["disposition"]) == ("completed", "needs_human_review")
    assert f"unresolved_transcription:{region}" in record["reason_codes"]


def test_a_first_pass_refused_once_then_answered_is_decided_as_before(tmp_path, monkeypatch):
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=1)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "http_429")

    first, last = drains(workflow, principal, ident, backend)

    run = last.run
    step = first_pass_step(run)
    assert (first.run.stage, first.run.blocker) == ("retry_scheduled", "model_rate_limited")
    assert (run.stage, run.blocker) == ("finalized", None)
    assert run.attempts[step] == 2 and requests(tmp_path, "first_pass") == 1
    [decision] = run.first_pass_decisions
    [transcript] = run.transcripts
    assert transcript.decision_kind == "first_pass"
    assert transcript.first_pass_call == decision.call
    assert given_up_findings(run) == []
    calls = [c for c in run.paid_calls if c["step"] == step]
    assert [(c["attempt"], c["outcome"], c["cost_basis"]) for c in calls] == [
        (1, "failed", "refused"),
        (2, "completed", "computed"),
    ]


def until_the_last_attempt(tmp_path, monkeypatch, *, late=False):
    """The lab, its first pass refused twice; its third attempt fails as the env
    then names (and with `late`, past its effect timeout)."""
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=3)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "http_429")
    workflow.monotonic = lambda: adapters.elapsed[0]
    now = datetime.now(timezone.utc)
    for hour in (1, 2):
        run = workflow.drain(principal, ident).run
        assert (run.stage, run.blocker) == ("retry_scheduled", "model_rate_limited")
        workflow.clock = lambda later=now + timedelta(hours=hour): later
    adapters.late = late
    return workflow, principal, ident, backend


@pytest.mark.parametrize(
    ("failure", "blocker"),
    [
        ("http_401", "model_authentication_error"),
        ("http_403", "model_authorization_error"),
        # A request the provider refuses as invalid is refused every time.
        ("http_400", "model_request_rejected"),
        ("malformed", "model_malformed_response"),
        # A server error may follow a billed answer: its outcome is unknown.
        ("http_503", "external_outcome_unknown"),
    ],
)
def test_a_last_attempt_that_asking_again_would_not_mend_still_blocks_with_its_cause(
    tmp_path, monkeypatch, failure, blocker
):
    workflow, principal, ident, _ = until_the_last_attempt(tmp_path, monkeypatch)
    monkeypatch.setenv(FAILURE, failure)

    run = workflow.drain(principal, ident).run

    step = first_pass_step(run)
    assert run.attempts[step] == 3
    assert (run.stage, run.blocker, run.disposition) == ("processing_blocked", blocker, None)
    assert step not in run.completed_steps and not run.transcripts
    assert given_up_findings(run) == []


def test_a_last_attempt_refused_after_its_deadline_still_blocks_as_unknown(
    tmp_path, monkeypatch
):
    workflow, principal, ident, _ = until_the_last_attempt(tmp_path, monkeypatch, late=True)

    run = workflow.drain(principal, ident).run

    step = first_pass_step(run)
    assert run.attempts[step] == 3
    assert (run.stage, run.blocker) == ("processing_blocked", "external_outcome_unknown")
    assert run.reasons == ["external_stage_deadline_exceeded"]
    assert step not in run.completed_steps and not run.transcripts
    assert given_up_findings(run) == []


def test_a_first_pass_given_up_on_a_provider_error_stays_reserved_and_names_its_code(
    tmp_path, monkeypatch
):
    # HTTP 402 is a transient provider failure (HARNESS.md section 3), retried
    # and given up on as a 429 is. It is no refusal: each attempt stays held in
    # full, so the first-pass route's context is made small enough here for
    # three held attempts to fit the run's limit.
    registry = with_models(
        published_registry({SYNTHETIC_COLLECTION: "insects"}),
        **{"first-pass-glm": {"context_tokens": 32_768}},
    )
    monkeypatch.setattr(
        test_rate_limit_refusal, "start", lambda path, kept: start(path, kept, registry)
    )
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=3)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "http_402")

    *retried, last = drains(workflow, principal, ident, backend)

    run = last.run
    region = run.regions[0].id
    step = first_pass_step(run)
    assert [d.run.blocker for d in retried] == ["model_provider_error"] * 2
    assert (run.stage, run.disposition, run.blocker) == ("finalized", Disposition.REVIEW, None)
    assert given_up_findings(run) == [
        (GIVEN_UP, "warning", f"{GIVEN_UP}:{region}:model_provider_error")
    ]
    assert f"unresolved_transcription:{region}" in run.reasons
    calls = [c for c in run.paid_calls if c["step"] == step]
    reserved = step_reservation(run, step)
    assert 0 < reserved < FIRST_PASS_RESERVATION
    # The given-up attempt is a failed call with its code, never "completed".
    assert ledger_rows(calls) == [
        (1, "failed", "reserved", reserved, None, None),
        (2, "failed", "reserved", reserved, None, None),
        (3, "failed", "reserved", reserved, None, "model_provider_error"),
    ]
    assert research_state(backend, last_specimen(workflow, principal, ident))[
        "ordinary_reservations"
    ][f"{step}:3"] == {"reserved_micros": reserved, "settled_micros": None}


def test_two_held_first_pass_failures_leave_no_room_for_a_third_under_the_run_cap(
    tmp_path, monkeypatch
):
    # Not changed here: with the published first-pass reservation, two failures
    # that stay held (a 402 is no refusal) and SAM's liability leave no room
    # under the run's USD 1 for a third attempt, so the first pass blocks before
    # it could be given up on. A refused 429 holds nothing (the test above).
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=3)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "http_402")

    *retried, last = drains(workflow, principal, ident, backend)

    run = last.run
    step = first_pass_step(run)
    assert [d.run.blocker for d in retried] == ["model_provider_error"] * 2
    assert (run.stage, run.blocker) == ("processing_blocked", "cost_budget_exhausted")
    assert run.attempts[step] == 2 and requests(tmp_path, "first_pass") == 2
    assert run.usage.reserved_cost_micros + FIRST_PASS_RESERVATION > (
        run.profile.execution.approved_cost_limit_micros
    )


def last_specimen(workflow, principal, ident):
    return workflow.repository.get(principal.scope, ident)


@pytest.mark.parametrize(
    ("failure", "given_up"),
    [
        (AdapterFailure("model_rate_limited", LookupStatus.RATE_LIMITED, refused=True), True),
        (AdapterFailure("model_rate_limited", LookupStatus.RATE_LIMITED), True),
        (AdapterFailure("model_provider_error", LookupStatus.PROVIDER), True),
        (AdapterFailure("provider_timeout", LookupStatus.TIMEOUT), True),
        (
            AdapterFailure(
                "provider_deadline_outcome_unknown",
                LookupStatus.TIMEOUT,
                outcome_unknown=True,
            ),
            False,
        ),
        (
            AdapterFailure(
                "model_provider_error", LookupStatus.PROVIDER, outcome_unknown=True
            ),
            False,
        ),
        (AdapterFailure("model_authentication_error", LookupStatus.AUTHENTICATION), False),
        (AdapterFailure("model_authorization_error", LookupStatus.AUTHORIZATION), False),
        (AdapterFailure("model_request_rejected", LookupStatus.POLICY), False),
        (AdapterFailure("model_malformed_response", LookupStatus.MALFORMED), False),
    ],
)
def test_which_last_attempts_are_given_up_on(failure, given_up):
    run = Run(profile=Profile())
    step = "first_pass:region"
    run.attempts[step] = run.profile.execution.max_attempts
    assert Workflow.first_pass_has_no_attempt_left(run, step, failure) is given_up
    # An earlier attempt is retried, never given up on.
    run.attempts[step] -= 1
    assert Workflow.first_pass_has_no_attempt_left(run, step, failure) is False
    # Nor is the evidence pilot's, whose readers are never given up on either.
    run.attempts[step] += 1
    run.dependencies["evidence_pilot"] = {}
    assert Workflow.first_pass_has_no_attempt_left(run, step, failure) is False
    # Only a first pass: a reader has its own rule (reading_has_no_attempt_left).
    run.dependencies = {}
    reader = "transcribe:region:route"
    run.attempts[reader] = run.profile.execution.max_attempts
    assert Workflow.first_pass_has_no_attempt_left(run, reader, failure) is False


# Longer waits after a rate limit ---------------------------------------------


@pytest.mark.parametrize("jitter", [0.0, 0.999])
def test_a_rate_limit_waits_at_least_its_floor_and_other_failures_as_before(jitter):
    from specimen_digitization.application.reliability import RATE_LIMIT_FLOORS

    assert RATE_LIMIT_FLOORS == (30, 90)
    draw = lambda: jitter  # noqa: E731
    first, second, third = (retry_delay(n, None, draw, rate_limited=True) for n in (1, 2, 3))
    assert 30 <= first < 60 and 90 <= second < 180 and 90 <= third < 180
    # A provider's Retry-After above the floor is still honoured.
    assert retry_delay(1, 120, draw, rate_limited=True) >= 120
    # Every other failure keeps the backoff it had: 2 to 4 s, then 4 to 8 s.
    assert [retry_delay(n, None, draw) for n in (1, 2)] == [2 + jitter * 2, 4 + jitter * 4]


def test_a_rate_limited_first_pass_waits_holding_no_lease_and_is_not_sent_early(
    tmp_path, monkeypatch
):
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=2)
    workflow, principal, ident, _ = lab(tmp_path, monkeypatch, adapters, "http_429")
    start = datetime.now(timezone.utc)
    workflow.clock, workflow.random_value = (lambda: start), (lambda: 0.0)

    run = workflow.drain(principal, ident).run

    assert (run.stage, run.blocker, run.lease_until) == (
        "retry_scheduled",
        "model_rate_limited",
        None,
    )
    # Before this change the retry was 2 s away (2 to 4 s with jitter).
    retry = datetime.fromisoformat(run.next_retry_at)
    assert retry == start + timedelta(seconds=30)
    # A step before then sends nothing and saves nothing.
    revision = last_specimen(workflow, principal, ident).version
    workflow.clock = lambda: retry - timedelta(seconds=1)
    assert workflow.step(principal, ident).version == revision
    assert requests(tmp_path, "first_pass") == 1
    # At its time the second attempt goes out; refused again, it waits 90 s.
    workflow.clock = lambda: retry
    run = workflow.drain(principal, ident).run
    assert requests(tmp_path, "first_pass") == 2
    assert run.stage == "retry_scheduled" and run.lease_until is None
    assert datetime.fromisoformat(run.next_retry_at) == retry + timedelta(seconds=90)


def test_a_provider_error_keeps_its_short_wait(tmp_path, monkeypatch):
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=1)
    workflow, principal, ident, _ = lab(tmp_path, monkeypatch, adapters, "http_402")
    start = datetime.now(timezone.utc)
    workflow.clock, workflow.random_value = (lambda: start), (lambda: 0.0)

    run = workflow.drain(principal, ident).run

    assert (run.stage, run.blocker) == ("retry_scheduled", "model_provider_error")
    assert datetime.fromisoformat(run.next_retry_at) == start + timedelta(seconds=2)
