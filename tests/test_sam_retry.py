"""A SAM 3 timeout retries instead of stranding its record (LANE.md T3a, G6).

The service stores each run's response and answers a repeat from it
(test_lane_sam_server), so a segmentation that ran past its budget is retried
after `SAM3_RETRY_SECONDS`. Any other paid call that ran past its budget still
waits for reconciliation as `external_outcome_unknown`.
"""

import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from specimen_digitization.application import bounded_effect
from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.lane_reservations import step_reservation
from specimen_digitization.application.production import (
    SAM3_RETRY_SECONDS,
    Sam3Service,
)
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.sam3_effect import (
    canonical_sha256,
    validate_sam3_run_response,
)
from specimen_digitization.application.sam3_server import RunSegmenter, SegmentRequest
from specimen_digitization.application.storage import LocalBlobs

from test_lane_routes import RUN_CAP, DisagreeingReaders, start
from test_lane_sam_client import envelope, isolated, lane_specimen
from test_lane_sam_server import RunEngine, RunObjects

ENDPOINT = "https://sam.run.app"


def exchange(segmenter, payload):
    """The effect's envelope (sam3_effect._exchange) for the service's answer."""
    try:
        status = 200
        body = segmenter.segment(SegmentRequest.model_validate(payload["request"]))
    except HTTPException as exc:
        status, body = exc.status_code, {"detail": exc.detail}
    raw = json.dumps(body).encode()
    validation = (
        validate_sam3_run_response(json.loads(raw), payload)
        if status == 200
        else "http_error"
    )
    return json.dumps(
        {
            "http_status": status,
            "validation": validation,
            "body_base64": base64.b64encode(raw).decode(),
        }
    ).encode()


class ServedSam(DisagreeingReaders):
    """SAM 3's per-run client, its bounded call answered by the service's own
    segmenter in process. Each call takes the next outcome: "timeout", the
    service segments and stores its response but the worker's budget runs out
    first; "served", the service's answer arrives; "lab", the readers' fixture
    regions (four quadrants with `regions=4`)."""

    def __init__(self, blobs, outcomes, regions=1):
        super().__init__(blobs, regions=regions)
        self.outcomes = list(outcomes)
        self.engine = RunEngine()
        self.engine.checkpoint_sha256 = canonical_sha256(self.engine.checkpoint_files)
        self.segmenter = None
        self.elapsed = [0.0]  # The workflow's monotonic clock.
        self.service_clock = lambda: 1000.0
        self.before_call = lambda payload: None

    def segment(self, specimen):
        outcome = self.outcomes.pop(0)
        if outcome == "lab":
            return super().segment(specimen)
        if self.segmenter is None:
            raw = self.blobs.get(specimen.asset.blob_ref.split(":")[0])
            self.segmenter = RunSegmenter(
                RunObjects(raw), self.engine, clock=lambda: self.service_clock()
            )

        def run_isolated(effect, payload, timeout_seconds, max_result_bytes):
            self.before_call(payload)
            value = exchange(self.segmenter, payload)
            if outcome == "timeout":
                # run_isolated reports the deadline once its budget is spent.
                self.elapsed[0] += timeout_seconds + 1
                return isolated("deadline_exceeded", "overall_deadline")
            return isolated("completed", "ok", value)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(bounded_effect, "run_isolated", run_isolated)
            service = Sam3Service(ENDPOINT, self.blobs, effect=lambda payload: b"")
            return service.segment_per_run(specimen)


def lane(tmp_path, monkeypatch, adapters):
    monkeypatch.setenv(
        "SPECIMEN_SAM3_CHECKPOINT_SHA256", adapters.engine.checkpoint_sha256
    )
    workflow, principal, ident = start(tmp_path, adapters)
    shift = [timedelta(0)]
    workflow.clock = lambda: datetime.now(timezone.utc) + shift[0]
    workflow.monotonic = lambda: adapters.elapsed[0]
    workflow.random_value = lambda: 0.0  # No jitter: each retry at its minimum.
    adapters.service_clock = lambda: workflow.clock().timestamp()
    return SimpleNamespace(
        workflow=workflow, principal=principal, ident=ident, shift=shift
    )


def at(c, moment):
    """Move the workflow's clock to `moment`."""
    c.shift[0] += moment - c.workflow.clock()


def drain(c):
    return c.workflow.drain(c.principal, c.ident).run


def test_a_sam_timeout_past_its_budget_retries_and_storage_answers_the_repeat(
    tmp_path, monkeypatch
):
    adapters = ServedSam(LocalBlobs(tmp_path / "blobs"), ["timeout", "served"])
    c = lane(tmp_path, monkeypatch, adapters)
    before = c.workflow.clock()
    run = drain(c)
    after = c.workflow.clock()
    # The step ran past the 270 s budget it reserved.
    assert run.usage.active_seconds > run.profile.execution.effect_timeout_for_step(
        "segment"
    )
    assert (run.stage, run.blocker) == ("retry_scheduled", "sam3_timeout"), run.reasons
    assert run.lease_until is None and run.reasons != ["external_stage_deadline_exceeded"]
    retry = datetime.fromisoformat(run.next_retry_at)
    wait = timedelta(seconds=SAM3_RETRY_SECONDS)
    assert before + wait <= retry <= after + wait
    # The service finished after the worker gave up, and stored its response.
    stored = f"application/sha256/sam3-runs/{run.id}/response.json"
    assert stored in adapters.segmenter.objects.data
    inferences = adapters.engine.calls

    at(c, retry - timedelta(seconds=10))
    waiting = c.workflow.step(c.principal, c.ident)
    assert waiting.run.stage == "retry_scheduled" and waiting.run.next_retry_at

    # Due: the repeat is answered from the stored response.
    at(c, retry + timedelta(seconds=5))
    run = drain(c)
    assert "segment" in run.completed_steps, run.blocker
    assert run.attempts["segment"] == 2
    assert adapters.engine.calls == inferences  # Answered from storage.
    response = json.loads(adapters.segmenter.objects.data[stored])
    assert [region.id for region in run.regions] == [
        region["id"] for region in response["regions"]
    ]
    assert run.blocker != "external_outcome_unknown"
    segments = [call for call in run.paid_calls if call["step"] == "segment"]
    assert [(call["attempt"], call["outcome"]) for call in segments] == [
        (1, "failed"),
        (2, "completed"),
    ]


class LateReader(DisagreeingReaders):
    """A paid segmentation, reader or first pass whose provider call ran past
    its budget and then failed, by default as a timeout."""

    def __init__(self, blobs, late, failure=None):
        super().__init__(blobs)
        self.late, self.elapsed = late, [0.0]
        self.failure = failure or AdapterFailure("provider_timeout", LookupStatus.TIMEOUT)

    def overran(self, specimen, step):
        self.elapsed[0] += specimen.run.profile.execution.effect_timeout_for_step(step) + 1
        raise self.failure

    def segment(self, specimen):
        if self.late == "segment":
            self.overran(specimen, "segment")
        return super().segment(specimen)

    def transcribe(self, specimen, region, route):
        if self.late == "transcribe":
            self.overran(specimen, f"transcribe:{region.id}:{route}")
        return super().transcribe(specimen, region, route)

    def first_pass(self, specimen, region, readings):
        if self.late == "first_pass":
            self.overran(specimen, f"first_pass:{region.id}")
        return super().first_pass(specimen, region, readings)


@pytest.mark.parametrize("late", ["transcribe", "first_pass"])
def test_any_other_paid_call_past_its_budget_still_waits_for_reconciliation(
    tmp_path, late
):
    adapters = LateReader(LocalBlobs(tmp_path / "blobs"), late)
    workflow, principal, ident = start(tmp_path, adapters)
    workflow.monotonic = lambda: adapters.elapsed[0]
    run = workflow.drain(principal, ident).run
    before = "transcribe:" if late == "first_pass" else "segment"
    assert run.completed_steps[-1].startswith(before)
    assert (run.stage, run.blocker) == ("processing_blocked", "external_outcome_unknown")
    assert run.reasons == ["external_stage_deadline_exceeded"]
    assert run.next_retry_at is None and run.lease_until is not None


@pytest.mark.parametrize(
    ("late", "failure"),
    [
        # Another failure on the segment step,
        ("segment", AdapterFailure("provider_timeout", LookupStatus.TIMEOUT)),
        # a SAM 3 failure whose outcome is unknown,
        (
            "segment",
            AdapterFailure("sam3_timeout", LookupStatus.TIMEOUT, outcome_unknown=True),
        ),
        # and a SAM 3 code on another paid step.
        (
            "transcribe",
            AdapterFailure(
                "sam3_timeout", LookupStatus.TIMEOUT, retry_after_seconds=SAM3_RETRY_SECONDS
            ),
        ),
    ],
    ids=["segment-other-code", "segment-outcome-unknown", "transcribe-sam3-code"],
)
def test_only_a_known_sam3_failure_on_segment_keeps_its_retry_past_the_budget(
    tmp_path, late, failure
):
    adapters = LateReader(LocalBlobs(tmp_path / "blobs"), late, failure)
    workflow, principal, ident = start(tmp_path, adapters)
    workflow.monotonic = lambda: adapters.elapsed[0]
    run = workflow.drain(principal, ident).run
    assert (run.stage, run.blocker) == ("processing_blocked", "external_outcome_unknown")
    assert run.reasons == ["external_stage_deadline_exceeded"]
    assert run.next_retry_at is None and run.lease_until is not None


@pytest.mark.parametrize(
    ("result", "code"),
    [
        (isolated("deadline_exceeded", "worker_deadline"), "sam3_timeout"),
        (isolated("completed", "ok", envelope(429, {"detail": "sam3_busy"})), "sam3_busy"),
        (isolated("completed", "ok", envelope(409, {"detail": "sam3_busy"})), "sam3_busy"),
    ],
)
def test_a_timeout_or_busy_answer_waits_out_the_services_window(
    monkeypatch, tmp_path, result, code
):
    monkeypatch.setattr(bounded_effect, "run_isolated", lambda *args, **kwargs: result)
    service = Sam3Service(ENDPOINT, LocalBlobs(tmp_path), effect=lambda payload: b"")
    with pytest.raises(AdapterFailure) as failure:
        service.segment_per_run(lane_specimen())
    assert (failure.value.code, failure.value.retry_after_seconds) == (code, 250)


def test_sam_timeouts_past_the_attempt_budget_dead_letter_the_record(
    tmp_path, monkeypatch
):
    adapters = ServedSam(LocalBlobs(tmp_path / "blobs"), ["timeout"] * 3)
    c = lane(tmp_path, monkeypatch, adapters)
    run = drain(c)
    for _ in range(2):
        assert (run.stage, run.blocker) == ("retry_scheduled", "sam3_timeout"), run.reasons
        at(c, datetime.fromisoformat(run.next_retry_at) + timedelta(seconds=5))
        run = drain(c)
    assert run.attempts["segment"] == run.profile.execution.max_attempts == 3
    # Dead-lettered on its own code, never left waiting for reconciliation.
    assert run.dead_letter and run.blocker == "retry_budget_exhausted:sam3_timeout"
    assert run.stage == "processing_blocked" and run.next_retry_at is None
    assert run.lease_until is None and run.reasons != ["external_stage_deadline_exceeded"]
    segments = [call for call in run.paid_calls if call["step"] == "segment"]
    assert [(call["attempt"], call["outcome"]) for call in segments] == [
        (1, "failed"),
        (2, "failed"),
        (3, "failed"),
    ]


def test_a_live_claim_is_waited_out_within_the_attempt_budget(tmp_path, monkeypatch):
    adapters = ServedSam(LocalBlobs(tmp_path / "blobs"), ["served"] * 3)
    c = lane(tmp_path, monkeypatch, adapters)

    def lost(payload):
        # An earlier request the worker lost: the service claimed the run just
        # now and is still running it, so this request is answered busy.
        claim = f"application/sha256/sam3-runs/{payload['request']['run_id']}/claim-1.json"
        adapters.segmenter.objects.data.setdefault(
            claim,
            json.dumps(
                {
                    "request_sha256": canonical_sha256(payload["request"]),
                    "claimed_at": adapters.service_clock(),
                }
            ).encode(),
        )

    adapters.before_call = lost
    run = drain(c)
    assert (run.stage, run.blocker) == ("retry_scheduled", "sam3_busy")
    retry = datetime.fromisoformat(run.next_retry_at)
    at(c, retry + timedelta(seconds=5))
    run = drain(c)
    # The claim is past the service's 240 s, so it is taken over and served.
    assert "segment" in run.completed_steps, run.blocker
    assert run.attempts["segment"] == 2


def test_four_regions_and_a_sam_retry_fit_the_run_cap(tmp_path, monkeypatch):
    adapters = ServedSam(
        LocalBlobs(tmp_path / "blobs"), ["timeout", "lab"], regions=4
    )
    c = lane(tmp_path, monkeypatch, adapters)
    run = drain(c)
    assert run.stage == "retry_scheduled", run.blocker
    at(c, datetime.fromisoformat(run.next_retry_at) + timedelta(seconds=5))
    run = drain(c)
    steps = [f"first_pass:{region.id}" for region in run.regions]
    assert len(steps) == 4 and set(steps) <= set(run.completed_steps), run.blocker
    assert run.stage == "finalized", run.blocker
    reserved = {
        (call["step"], call["attempt"]): call["reserved_micros"] for call in run.paid_calls
    }
    # Every paid attempt's reservation, as if none had settled: 2 x 45,000 for
    # SAM 3, 8 x 20,000 for the readings, 4 x 20,000 for the first passes (this
    # emulator's parse makes no paid call).
    assert [r for (step, _), r in reserved.items() if step == "segment"] == [45_000] * 2
    assert sum(reserved.values()) == 330_000 <= RUN_CAP
    # Settled: the timed-out attempt's 45,000 stays held, the rest is what was spent.
    spent = sum(
        call["cost_micros"] for call in run.paid_calls if call["cost_basis"] == "computed"
    )
    assert run.usage.reserved_cost_micros == 45_000 + spent
    # The worst case on the published reservations: all three SAM 3 attempts,
    # the eight readings, four first passes and one retried, and a paid parse.
    worst = (
        run.profile.execution.max_attempts * step_reservation(run, "segment")
        + sum(r for (step, _), r in reserved.items() if step.startswith("transcribe:"))
        + 5 * step_reservation(run, steps[0])
        + step_reservation(run, "parse")
    )
    assert worst == 3 * 45_000 + 8 * 20_000 + 5 * 20_000 + 20_000 == 415_000 <= RUN_CAP
