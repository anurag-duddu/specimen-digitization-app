"""A reader failure is retried, then ends its reading; it never blocks the run (G6).

Production, 2026-10-09: a new run on specimen 105526322 blocked at its
`handwriting-muse` reader as `external_outcome_unknown`, and nothing in the
product clears that. A reading is a pure read, so a failed one is a known
failure that is asked again, and one that stays failed ends its reading with no
observation: the record goes to review (`independent_observations_missing`).
Every other step's unknown outcome still blocks.

These tests drive the real isolated model child (research_harness/workflow_bridge.py
runs readers as the ordinary `transcribe:` steps) with a fixture model whose
reader fails in each way the child can end. `test_reader_usage_limit.py` covers
a reading stopped by its token limits (#232).
"""

import os
import signal
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application.api import (
    SYNTHETIC_COLLECTION,
    SYNTHETIC_ORG,
    SYNTHETIC_TEXT,
    create_app,
)
from specimen_digitization.application.domain import (
    Disposition,
    ExecutionPolicy,
    Principal,
    Scope,
)
from specimen_digitization.application.production import (
    ProductionAdapters,
    actor_uid,
)
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.workflow import SyntheticAdapters
from test_application import HEADERS, PREFIX, TOKEN, intake
from test_hardening_concurrency import repository

PRINCIPAL = Principal(
    user_id="synthetic-reviewer",
    role="reviewer",
    scope=Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION),
)
# The reader that fails is the second route's (`handwriting-muse` in production).
FAILING = "1"


def failing_reader_child(payload):
    """The model child, with the named routes' readers failing the way the env names.

    Each fails its first `SPECIMEN_TEST_READER_FAILS` calls (counted in a file,
    because every call is a new process) and answers after that.
    """
    from pydantic_ai.exceptions import ModelHTTPError
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.usage import RequestUsage

    from specimen_digitization.application import production
    from specimen_digitization.application.model_runtime import model_child
    from specimen_digitization.model_gateway import INITIAL_HUGGINGFACE_ROUTES

    kind = os.environ["SPECIMEN_TEST_READER_FAILURE"]
    fails = int(os.environ["SPECIMEN_TEST_READER_FAILS"])
    routes = payload["profile"]["routes"]
    failing = {routes[int(index)] for index in os.environ["SPECIMEN_TEST_READER_FAILING"]}
    root = Path(payload["storage"]["root"]).parent

    class Gateway:
        def __init__(self, timeout_seconds=None):
            pass

        def route(self, route):
            return INITIAL_HUGGINGFACE_ROUTES[route]

        def model_for(self, route):
            def respond(messages, info):
                if route in failing:
                    counter = root / f"calls-{route}"
                    with counter.open("a") as calls:
                        calls.write("call\n")
                    if len(counter.read_text().splitlines()) <= fails:
                        if kind == "malformed":
                            # An answer that fails validation, again after the
                            # agent's own output retry (model_malformed_response).
                            return ModelResponse(
                                parts=[
                                    ToolCallPart(
                                        info.output_tools[0].name, {"verbatim_text": 5}
                                    )
                                ],
                                finish_reason="stop",
                            )
                        fail(kind)
                answer = {
                    "verbatim_text": SYNTHETIC_TEXT,
                    "lines": SYNTHETIC_TEXT.splitlines(),
                    "unreadable_spans": [],
                }
                return ModelResponse(
                    parts=[ToolCallPart(info.output_tools[0].name, answer)],
                    usage=RequestUsage(input_tokens=1_000, output_tokens=40),
                    finish_reason="stop",
                )

            def fail(kind):
                if kind == "http_429":
                    raise ModelHTTPError(429, "reader", body="rate limited")
                if kind == "http_503":
                    raise ModelHTTPError(503, "reader", body="bad gateway")
                if kind == "http_401":
                    raise ModelHTTPError(401, "reader", body="unauthorized")
                if kind == "provider_timeout":
                    raise TimeoutError
                if kind == "transport":
                    raise httpx.ConnectError("connection reset by peer")
                if kind == "unmapped":
                    raise RuntimeError("an exception the child does not map")
                if kind == "killed":
                    os.kill(os.getpid(), signal.SIGKILL)
                if kind == "hangs":
                    import time

                    time.sleep(60)

            return FunctionModel(respond, model_name="local-reader-failure")

    production.HuggingFaceModelGateway = Gateway
    return model_child(payload)


class FailingReaders(SyntheticAdapters):
    """Production readers in the real isolated child; the rest synthetic."""

    pin_dependencies = ProductionAdapters.pin_dependencies
    transcribe = ProductionAdapters.transcribe

    def __init__(self, blobs, reader_timeout=None):
        super().__init__(blobs, SYNTHETIC_TEXT)
        self.classifier = None
        self.model_effect = failing_reader_child
        self.reader_timeout = reader_timeout

    def pin_dependencies(self, run):
        if self.reader_timeout:
            run.profile.execution = ExecutionPolicy.model_validate(
                dict(
                    run.profile.execution.model_dump(),
                    reader_timeout_seconds=self.reader_timeout,
                )
            )
        return ProductionAdapters.pin_dependencies(self, run)


def start(tmp_path, monkeypatch, failure, fails, reader_timeout=None, failing=FAILING):
    """A synthetic app whose first drain has run; the specimen's id and the app."""
    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setenv("SPECIMEN_TEST_READER_FAILURE", failure)
    monkeypatch.setenv("SPECIMEN_TEST_READER_FAILS", str(fails))
    monkeypatch.setenv("SPECIMEN_TEST_READER_FAILING", failing)
    blobs = LocalBlobs(tmp_path / "blobs")
    app = create_app(
        mode="synthetic",
        repository=repository(tmp_path, "sqlite"),
        blobs=blobs,
        adapters=FailingReaders(blobs, reader_timeout),
        token=TOKEN,
    )
    with TestClient(app) as http:
        row = intake(http)
        work = http.get(
            PREFIX + "/specimens/" + row["specimen_id"] + "/workspace",
            headers=HEADERS,
        ).json()
    return app, row["specimen_id"], work["run"]


def drain_through_retries(app, specimen_id):
    """Step the run to its end, a day later each time a retry is scheduled."""
    actor_uid.set(PRINCIPAL.user_id)
    workflow = app.state.workflow
    now = datetime.now(timezone.utc)
    for day in range(1, 8):
        run = workflow.drain(PRINCIPAL, specimen_id).run
        if run.stage != "retry_scheduled":
            return run
        workflow.clock = lambda later=now + timedelta(days=day): later
    raise AssertionError("the run kept scheduling retries: " + run.blocker)


def step_of(run, index=int(FAILING)):
    return f"transcribe:{run.regions[0].id}:{run.profile.routes[index]}"


def calls(tmp_path, run, index=int(FAILING)):
    counter = tmp_path / f"calls-{run.profile.routes[index]}"
    return len(counter.read_text().splitlines())


def stored_specimen(app, specimen_id):
    actor_uid.set(PRINCIPAL.user_id)
    return app.state.workflow.repository.get(PRINCIPAL.scope, specimen_id)


def stored(app, specimen_id):
    return stored_specimen(app, specimen_id).run


def ended_without_its_reading(run, tmp_path, attempts, requests=1):
    """The run finished: the failing reader was asked `attempts` times, in vain.

    `requests` are the model requests of one attempt (an answer that fails
    validation is asked again once inside the attempt).
    """
    step = step_of(run)
    assert run.blocker is None, run.blocker
    assert not run.dead_letter
    assert run.stage == "finalized" and run.disposition == Disposition.REVIEW
    assert step in run.completed_steps and run.attempts[step] == attempts
    assert calls(tmp_path, run) == attempts * requests
    # Only the other reader's observation exists, once; never a duplicate.
    assert [o.route_id for o in run.observations] == [run.profile.routes[0]]
    assert f"independent_observations_missing:{run.regions[0].id}" in run.reasons


# Each way a reader can end other than with an answer. A 429, a 5xx, a provider
# timeout, a transport error, an exception the child does not map, a kill and an
# answer that never validates are all asked again (twice: three attempts), then
# the reading ends.
@pytest.mark.parametrize(
    "failure",
    [
        "http_429",
        "http_503",
        "provider_timeout",
        "transport",
        "unmapped",
        "killed",
        "malformed",
    ],
)
def test_a_reader_that_keeps_failing_is_retried_then_ends_its_reading(
    tmp_path, monkeypatch, failure
):
    app, specimen_id, first = start(tmp_path, monkeypatch, failure, fails=99)
    step = step_of(stored(app, specimen_id))
    # The first failure is a scheduled retry: before this change it parked the
    # run here as external_outcome_unknown, and nothing could clear that.
    assert first["blocker"] != "external_outcome_unknown", first["blocker"]
    assert first["stage"] == "retry_scheduled" and first["attempts"][step] == 1
    assert first["lease_until"] is None
    run = drain_through_retries(app, specimen_id)
    ended_without_its_reading(
        run, tmp_path, attempts=3, requests=2 if failure == "malformed" else 1
    )


def test_a_reader_that_fails_once_is_asked_again_and_reads(tmp_path, monkeypatch):
    app, specimen_id, first = start(tmp_path, monkeypatch, "http_503", fails=1)
    assert first["stage"] == "retry_scheduled"
    run = drain_through_retries(app, specimen_id)
    step = step_of(run)
    assert run.blocker is None and run.stage == "finalized"
    assert run.attempts[step] == 2 and calls(tmp_path, run) == 2
    # One observation per reader: the failed attempt left none behind.
    assert sorted(o.route_id for o in run.observations) == sorted(run.profile.routes)
    assert len({o.id for o in run.observations}) == 2
    assert "independent_observations_missing" not in " ".join(run.reasons)


def test_a_reader_whose_deadline_passes_is_retried_not_blocked(tmp_path, monkeypatch):
    app, specimen_id, first = start(
        tmp_path, monkeypatch, "hangs", fails=99, reader_timeout=3
    )
    step = step_of(stored(app, specimen_id))
    assert first["blocker"] == "reader_deadline_exceeded"
    assert first["stage"] == "retry_scheduled" and first["lease_until"] is None
    assert first["attempts"][step] == 1
    run = drain_through_retries(app, specimen_id)
    ended_without_its_reading(run, tmp_path, attempts=3)


def test_a_credential_failure_still_blocks_and_names_its_cause(tmp_path, monkeypatch):
    # Asking again repeats a 401, so it is not retried and the run is not sent
    # to review as though the reader had found nothing.
    app, specimen_id, first = start(tmp_path, monkeypatch, "http_401", fails=99)
    assert first["stage"] == "processing_blocked"
    assert first["blocker"] == "model_authentication_error"
    assert calls(tmp_path, stored(app, specimen_id)) == 1


def test_both_readers_failing_still_ends_in_review(tmp_path, monkeypatch):
    # Nothing is read for the region. Its transcript has no text and no
    # readings, which evidence verification used to refuse as
    # `evidence_integrity_failure`; the record now goes to review.
    app, specimen_id, _ = start(
        tmp_path, monkeypatch, "unmapped", fails=99, failing="01"
    )
    run = drain_through_retries(app, specimen_id)
    assert run.blocker is None, run.blocker
    assert run.stage == "finalized" and run.disposition == Disposition.REVIEW
    assert run.observations == []
    assert [run.attempts[step_of(run, i)] for i in (0, 1)] == [3, 3]
    region = run.regions[0].id
    assert f"independent_observations_missing:{region}" in run.reasons
    assert f"unresolved_transcription:{region}" in run.reasons
    [transcript] = run.transcripts
    assert (transcript.text, transcript.resolved, transcript.observation_ids) == (
        None,
        False,
        [],
    )


def test_a_transcript_with_text_must_still_trace_to_a_reading(tmp_path, monkeypatch):
    # The integrity rule only gives way for a region nothing was read for.
    from specimen_digitization.application.integrity import (
        EvidenceIntegrityError,
        verify_evidence,
    )

    app, specimen_id, _ = start(tmp_path, monkeypatch, "http_503", fails=0)
    specimen = stored_specimen(app, specimen_id)
    verify_evidence(specimen, app.state.workflow.blobs)
    [transcript] = specimen.run.transcripts
    transcript.observation_ids = []
    with pytest.raises(EvidenceIntegrityError):
        verify_evidence(specimen, app.state.workflow.blobs)


def dying_child(payload):
    """A model child that is killed on the operation the env names."""
    if payload["operation"] == os.environ["SPECIMEN_TEST_DYING_OPERATION"]:
        os.kill(os.getpid(), signal.SIGKILL)
    return failing_reader_child(payload)


@pytest.mark.parametrize(
    "operation", ["transcribe", "first_pass", "extract"]
)
def test_only_a_reader_child_that_dies_is_a_known_failure(
    tmp_path, monkeypatch, operation
):
    # The same killed child. A reader's is asked again; a first pass's and the
    # organiser's may have changed something, and still block as unknown.
    from specimen_digitization.application.model_runtime import invoke_model
    from specimen_digitization.application.reliability import AdapterFailure
    from specimen_digitization.application.workflow import OperationalBlock

    app, specimen_id, _ = start(tmp_path, monkeypatch, "http_503", fails=0)
    specimen = stored_specimen(app, specimen_id)
    run = specimen.run
    region = run.regions[0]
    adapters = app.state.workflow.adapters
    adapters.model_effect = dying_child
    monkeypatch.setenv("SPECIMEN_TEST_DYING_OPERATION", operation)
    arguments = {
        "transcribe": dict(region=region, route=run.profile.routes[0]),
        "first_pass": dict(region=region, readings=[]),
        "extract": {},
    }[operation]

    if operation == "transcribe":
        with pytest.raises(AdapterFailure) as known:
            invoke_model(adapters, specimen, operation, **arguments)
        assert known.value.code == "reader_worker_failed"
        assert known.value.outcome_unknown is False
    else:
        with pytest.raises(OperationalBlock, match="external_outcome_unknown"):
            invoke_model(adapters, specimen, operation, **arguments)


def test_each_retry_of_a_reader_reserves_again_and_an_unknown_spend_stays_held(
    tmp_path, monkeypatch
):
    # A priced run (PLAN 4.3, G30): every attempt reserves its worst case
    # before the call, and nothing is given back for an attempt whose outcome
    # is unknown. The failure is the shape run_agent_bounded gives a provider
    # timeout: the provider may have billed.
    from specimen_digitization.application.lane_reservations import step_reservation
    from specimen_digitization.application.reliability import AdapterFailure
    from test_lane_costs import TokenAdapters, lab, ledger_total

    kept = TokenAdapters.transcribe

    def transcribe(self, specimen, region, route):
        if route == "handwriting-muse":
            raise AdapterFailure(
                "provider_deadline_outcome_unknown", outcome_unknown=True
            )
        return kept(self, specimen, region, route)

    monkeypatch.setattr(TokenAdapters, "transcribe", transcribe)
    app, principal, row = lab(tmp_path)
    workflow = app.state.workflow
    now = datetime.now(timezone.utc)
    for day in range(1, 8):
        run = workflow.drain(principal, row["specimen_id"]).run
        if run.stage != "retry_scheduled":
            break
        assert run.blocker == "provider_deadline_outcome_unknown"
        workflow.clock = lambda later=now + timedelta(days=day): later
    step = step_of(run, 1)
    assert run.blocker is None and run.stage == "finalized", run.blocker
    assert run.attempts[step] == 3 and step in run.completed_steps
    assert [o.route_id for o in run.observations] == ["handwriting-qwen"]

    failed = [c for c in run.paid_calls if c["step"] == step]
    reserved = step_reservation(run, step)
    assert [(c["attempt"], c["cost_basis"], c["usage"]) for c in failed] == [
        (1, "reserved", None),
        (2, "reserved", None),
        (3, "reserved", None),
    ]
    assert all(c["cost_micros"] == c["reserved_micros"] == reserved for c in failed)
    # The run's budget and the program's ledger both hold all three, in full,
    # beside the segmentation and the reading that answered (settled to 550).
    assert run.usage.reserved_cost_micros == 164_121 + 550 + 3 * reserved
    assert ledger_total(app) == run.usage.reserved_cost_micros
    assert run.usage.actual_cost_micros is None
