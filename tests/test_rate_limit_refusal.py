"""A provider's HTTP 429 refusal costs nothing; every other failure stays held (G30).

Production, 2026-10-11, specimen 105526327, run 094ec176: after segmentation and
six readings, the first pass (route `first-pass-glm`) was answered HTTP 429
twice. Each refusal was recorded as `cost_basis: reserved` at the step's whole
318,670 micro-dollar reservation, so after the second the run held 822,812 of
its 1,000,000 limit, a third attempt did not fit, and the run blocked as
`cost_budget_exhausted`.

A 429 answering a call's first request is a refusal before any work: nothing
was generated, so nothing is billed. These tests drive the real isolated model
child (`model_runtime.invoke_model`) with a fixture provider that answers 429,
or fails another way, in the lab of `test_lane_routes.py`: the published pilot
profile's prices and pins, readings that differ, and both ledgers wired as
production wires them (the program's, and the run's shared research state).
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from specimen_digitization.application.api import SYNTHETIC_COLLECTION, SYNTHETIC_ORG
from specimen_digitization.application.domain import Disposition
from specimen_digitization.application.lane_allowance import ProgramLedger
from specimen_digitization.application.lane_reservations import step_reservation
from specimen_digitization.application.production import ProductionAdapters
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.research_harness.persistence import (
    DurabilityScope,
    SqliteStateBackend,
)
from specimen_digitization.research_harness.production_runtime import research_program_key
from specimen_digitization.research_harness.program_budget import (
    research_liability_micros,
    reserve_ordinary_liability,
    settle_ordinary_liability,
)

from test_lane_profile import USER
from test_lane_routes import (
    FIRST_PASS_RESERVATION,
    PARSE_RESERVATION,
    SAM_RESERVATION,
    SCOPE,
    DisagreeingReaders,
    start,
)

FAILURE = "SPECIMEN_TEST_PROVIDER_FAILURE"
MUSE = "handwriting-muse"


def refusing_model_child(payload):
    """The isolated model child, with a provider that fails as the env names.

    `http_<status>` answers every request with that HTTP status. `malformed`
    answers, with usage, an output the step refuses, twice (the agent's output
    retry). `answer_then_429` gives that answer once, then answers the output
    retry with HTTP 429. Each request is counted in a file beside the blobs.
    """
    from pydantic_ai.exceptions import ModelHTTPError
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.usage import RequestUsage

    from specimen_digitization.application import first_pass, production
    from specimen_digitization.application.model_runtime import model_child
    from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES

    kind = os.environ[FAILURE]
    sent = Path(payload["storage"]["root"]).parent / f"requests-{payload['operation']}"

    class Gateway:
        def __init__(self, timeout_seconds=None):
            self.routes = dict(HUGGINGFACE_ROUTES)

        def route(self, route_id):
            return self.routes[route_id]

        def model_for(self, route_id):
            def respond(messages, info):
                with sent.open("a") as requests:
                    requests.write(route_id + "\n")
                answered = any(m.kind == "response" for m in messages)
                if kind.startswith("http_"):
                    raise ModelHTTPError(int(kind[5:]), route_id, body="provider_request_failed")
                if kind == "answer_then_429" and answered:
                    raise ModelHTTPError(429, route_id, body="provider_request_failed")
                return ModelResponse(
                    parts=[ToolCallPart(info.output_tools[0].name, {"unexpected": 5})],
                    usage=RequestUsage(input_tokens=1_000, output_tokens=40),
                    finish_reason="stop",
                )

            return FunctionModel(respond, model_name="local-provider")

    production.HuggingFaceModelGateway = Gateway
    first_pass.HuggingFaceModelGateway = Gateway
    return model_child(payload)


class ChildLab(DisagreeingReaders):
    """test_lane_routes' lab, whose first `first_passes` first passes and first
    `readings` handwriting-muse readings go to the real model child.

    With `late`, each of those calls also takes longer than its step's effect
    timeout on the workflow's clock (`elapsed`, as tests/test_sam_retry.py)."""

    def __init__(self, blobs, *, first_passes=0, readings=0, late=False):
        super().__init__(blobs)
        self.model_effect = refusing_model_child
        self.child_first_passes, self.child_readings = first_passes, readings
        self.reader_exposure = []
        self.late, self.elapsed = late, [0.0]

    def overrun(self, specimen, step):
        if self.late:
            self.elapsed[0] += specimen.run.profile.execution.effect_timeout_for_step(step) + 1

    def transcribe(self, specimen, region, route):
        if route == MUSE and self.child_readings:
            self.child_readings -= 1
            self.reader_exposure.append(specimen.run.usage.reserved_cost_micros)
            self.overrun(specimen, f"transcribe:{region.id}:{route}")
            return ProductionAdapters.transcribe(self, specimen, region, route)
        return super().transcribe(specimen, region, route)

    def first_pass(self, specimen, region, readings):
        if self.child_first_passes:
            self.child_first_passes -= 1
            self.exposure.append(specimen.run.usage.reserved_cost_micros)
            self.overrun(specimen, "first_pass:" + region.id)
            return ProductionAdapters.first_pass(self, specimen, region, readings)
        return super().first_pass(specimen, region, readings)


class ChildOrganiser(ChildLab):
    """The lab with production's organiser (the paid `parse`), in the model child."""

    extract = ProductionAdapters.extract


def lab(tmp_path, monkeypatch, adapters, failure):
    """The lab with the research state wired as production wires it (workflow_bridge)."""
    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setenv(FAILURE, failure)
    workflow, principal, ident = start(tmp_path, adapters)
    repository = workflow.repository
    backend = SqliteStateBackend(tmp_path / "research.sqlite3")
    backend.grant(
        DurabilityScope(SYNTHETIC_ORG, SYNTHETIC_COLLECTION, "any", "any", 1, USER, False),
        role="admin",
    )
    workflow.retained_cost = lambda p, specimen: research_liability_micros(
        repository, p, specimen, state_backend=backend
    )
    workflow.reserve_retained_cost = lambda p, specimen, step, cost: reserve_ordinary_liability(
        repository, p, specimen, step, cost, state_backend=backend
    )
    workflow.settle_retained_cost = lambda p, specimen, step: settle_ordinary_liability(
        repository, p, specimen, step, state_backend=backend
    )
    return workflow, principal, ident, backend


def research_state(backend, specimen):
    scope = DurabilityScope(
        SYNTHETIC_ORG, SYNTHETIC_COLLECTION, specimen.id, "ordinary-budget-read", 1, USER, False
    )
    return backend.load(scope, research_program_key(specimen.run.id)).state


def drains(workflow, principal, ident, backend):
    """Each drain of the run, an hour later each time a retry is scheduled, with
    both ledgers as it left them."""
    now, seen = datetime.now(timezone.utc), []
    for hour in range(1, 8):
        specimen = workflow.drain(principal, ident)
        seen.append(
            SimpleNamespace(
                run=specimen.run,
                program=ProgramLedger(workflow.repository, SCOPE).read()["reserved_total_micros"],
                research=research_state(backend, specimen),
            )
        )
        if specimen.run.stage != "retry_scheduled":
            return seen
        workflow.clock = lambda later=now + timedelta(hours=hour): later
    raise AssertionError("the run kept scheduling retries: " + specimen.run.blocker)


def requests(tmp_path, operation):
    """The requests the fixture provider was sent for an operation."""
    sent = tmp_path / f"requests-{operation}"
    return len(sent.read_text().splitlines()) if sent.exists() else 0


def ledger_rows(calls):
    return [
        (c["attempt"], c["outcome"], c["cost_basis"], c["cost_micros"], c["usage"], c.get("failure_code"))
        for c in calls
    ]


@pytest.mark.parametrize(
    ("statuses", "refused"),
    [
        ((429,), True),
        # The agent's output retry answered 429 after a billed answer.
        ((None, 429), False),
        ((503,), False),
        ((402,), False),
        ((401,), False),
    ],
)
def test_only_a_429_to_the_calls_first_request_is_a_refusal(statuses, refused):
    from pydantic import BaseModel
    from pydantic_ai import Agent
    from pydantic_ai.exceptions import ModelHTTPError
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.usage import RequestUsage, UsageLimits

    from specimen_digitization.application.reliability import (
        AdapterFailure,
        run_agent_bounded,
    )

    class Output(BaseModel):
        number: int

    answers = list(statuses)

    def respond(messages, info):
        status = answers.pop(0)
        if status is None:
            # An answer, with usage, that fails validation: the agent asks again.
            return ModelResponse(
                parts=[ToolCallPart(info.output_tools[0].name, {"number": "x"})],
                usage=RequestUsage(input_tokens=1_000, output_tokens=40),
            )
        raise ModelHTTPError(status, "model", body="provider_request_failed")

    agent = Agent(FunctionModel(respond, model_name="local"), output_type=Output)
    with pytest.raises(AdapterFailure) as failure:
        run_agent_bounded(
            agent, "x", timeout_seconds=10, usage_limits=UsageLimits(request_limit=2)
        )
    assert answers == []
    assert failure.value.refused is refused


def test_a_refused_call_is_a_known_zero_in_the_runs_actual_cost():
    # Unlike a reserved call, it never makes the run's actual cost unknown.
    from specimen_digitization.application.lane_costs import (
        record_model_usage,
        record_refused,
    )
    from test_lane_costs import QWEN, priced_run

    run = priced_run()
    run.attempts[QWEN] = 1
    record_refused(
        run, QWEN, "model", route_id="handwriting-qwen", failure_code="model_rate_limited"
    )
    assert run.usage.actual_cost_micros == 0
    run.attempts[QWEN] = 2
    record_model_usage(run, QWEN, "handwriting-qwen", input_tokens=1_000, output_tokens=500)
    assert run.usage.actual_cost_micros == 550
    assert [c["cost_basis"] for c in run.paid_calls] == ["refused", "computed"]


def test_two_first_pass_refusals_cost_nothing_and_the_third_attempt_is_sent(
    tmp_path, monkeypatch
):
    # 105526327: the first pass answered 429 twice, then (here) answers.
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=2)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "http_429")

    first, second, last = drains(workflow, principal, ident, backend)

    run = last.run
    step = "first_pass:" + run.regions[0].id
    # Before this change the third attempt did not fit the 1,000,000 limit.
    assert (run.stage, run.blocker) == ("finalized", None), run.blocker
    # Each refusal is a scheduled retry within max_attempts, as before.
    for refused in (first, second):
        assert (refused.run.stage, refused.run.blocker) == ("retry_scheduled", "model_rate_limited")
    assert requests(tmp_path, "first_pass") == 2
    # Every attempt went out at the same exposure: the segmentation's held
    # liability plus its own reservation. Before this change the second saw the
    # first's 318,670 still held (819,661).
    assert adapters.exposure == [SAM_RESERVATION + FIRST_PASS_RESERVATION] * 3
    assert run.attempts[step] == 3 and step in run.completed_steps
    calls = [c for c in run.paid_calls if c["step"] == step]
    assert ledger_rows(calls) == [
        (1, "failed", "refused", 0, None, "model_rate_limited"),
        (2, "failed", "refused", 0, None, "model_rate_limited"),
        (3, "completed", "computed", 330, {"input_tokens": 1_200, "output_tokens": 300}, None),
    ]
    assert {c["reserved_micros"] for c in calls} == {FIRST_PASS_RESERVATION}
    # After each refusal the run's reservation is back where it was before the
    # first pass, and the program's ledger with it.
    assert [d.run.usage.reserved_cost_micros for d in (first, second)] == [SAM_RESERVATION] * 2
    assert [d.program for d in (first, second, last)] == [
        SAM_RESERVATION,
        SAM_RESERVATION,
        SAM_RESERVATION + 330,
    ]
    assert run.usage.reserved_cost_micros == SAM_RESERVATION + 330
    assert run.program_allowance["reserved_total_micros"] == last.program
    # So is the run's shared research state: each refusal settled at zero.
    for drain in (first, second):
        assert drain.research["ordinary_cost_micros"] == SAM_RESERVATION
    reservations = last.research["ordinary_reservations"]
    assert [reservations[f"{step}:{n}"] for n in (1, 2, 3)] == [
        {"reserved_micros": FIRST_PASS_RESERVATION, "settled_micros": 0},
        {"reserved_micros": FIRST_PASS_RESERVATION, "settled_micros": 0},
        {"reserved_micros": FIRST_PASS_RESERVATION, "settled_micros": 330},
    ]


@pytest.mark.parametrize(
    ("failure", "blocker", "outcome", "sent"),
    [
        # A comparison is safe to retry; its unknown bill remains fully held.
        ("http_503", "model_provider_error", "failed", 1),
        # HTTP 402 is a transient provider failure, not a refusal.
        ("http_402", "model_provider_error", "failed", 1),
        # A 429 to the output retry follows an answer that was billed.
        ("answer_then_429", "model_rate_limited", "failed", 2),
    ],
)
def test_a_first_pass_failure_other_than_a_refusal_holds_its_whole_reservation(
    tmp_path, monkeypatch, failure, blocker, outcome, sent
):
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=1)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, failure)

    specimen = workflow.drain(principal, ident)

    run = specimen.run
    step = "first_pass:" + run.regions[0].id
    assert run.blocker == blocker and requests(tmp_path, "first_pass") == sent
    [call] = [c for c in run.paid_calls if c["step"] == step]
    failure_code = "model_provider_error" if failure == "http_503" else None
    assert ledger_rows([call]) == [(1, outcome, "reserved", FIRST_PASS_RESERVATION, None, failure_code)]
    assert run.usage.reserved_cost_micros == SAM_RESERVATION + FIRST_PASS_RESERVATION
    assert ProgramLedger(workflow.repository, SCOPE).read()["reserved_total_micros"] == (
        run.usage.reserved_cost_micros
    )
    state = research_state(backend, specimen)
    assert state["ordinary_reservations"][f"{step}:1"] == {
        "reserved_micros": FIRST_PASS_RESERVATION,
        "settled_micros": None,
    }


def test_a_malformed_first_pass_is_given_up_at_once_and_the_record_goes_to_review(
    tmp_path, monkeypatch
):
    # 2026-10-12, specimen 19f0f1f6: GLM's answer stayed malformed after its
    # output retry ("Exceeded maximum output retries (1)") and the run blocked as
    # model_malformed_response with no way on. A malformed answer is a known,
    # billed outcome: the first pass is given up on at once, not asked again.
    from test_first_pass_given_up import given_up_findings

    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=1)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "malformed")

    specimen = workflow.drain(principal, ident)

    run = specimen.run
    step = "first_pass:" + run.regions[0].id
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    assert run.attempts[step] == 1 and requests(tmp_path, "first_pass") == 2
    assert given_up_findings(run) == [
        ("first_pass_given_up", "warning", f"first_pass_given_up:{run.regions[0].id}:model_malformed_response")
    ]
    [call] = [c for c in run.paid_calls if c["step"] == step]
    assert ledger_rows([call]) == [
        (1, "failed", "reserved", FIRST_PASS_RESERVATION, None, "model_malformed_response")
    ]
    assert research_state(backend, specimen)["ordinary_reservations"][f"{step}:1"] == {
        "reserved_micros": FIRST_PASS_RESERVATION,
        "settled_micros": None,
    }


def test_a_first_pass_refused_after_its_deadline_keeps_its_known_refusal(tmp_path, monkeypatch):
    # The comparison is repeatable. A known first-request 429 still proves a
    # zero bill past its elapsed deadline, as it does for a reader. A 503 has
    # no such proof and remains fully reserved in the test above.
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), first_passes=1, late=True)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "http_429")
    workflow.monotonic = lambda: adapters.elapsed[0]

    specimen = workflow.drain(principal, ident)

    run = specimen.run
    step = "first_pass:" + run.regions[0].id
    assert requests(tmp_path, "first_pass") == 1
    assert (run.stage, run.blocker) == ("retry_scheduled", "model_rate_limited")
    assert "external_stage_deadline_exceeded" not in run.reasons
    [call] = [c for c in run.paid_calls if c["step"] == step]
    assert ledger_rows([call]) == [(1, "failed", "refused", 0, None, "model_rate_limited")]
    assert run.usage.reserved_cost_micros == SAM_RESERVATION
    assert ProgramLedger(workflow.repository, SCOPE).read()["reserved_total_micros"] == (
        SAM_RESERVATION
    )
    assert research_state(backend, specimen)["ordinary_reservations"][f"{step}:1"] == {
        "reserved_micros": FIRST_PASS_RESERVATION,
        "settled_micros": 0,
    }


def test_a_reading_refused_after_its_deadline_is_still_a_refusal(tmp_path, monkeypatch):
    # A reader has no deadline override (reliability.reader_failure_is_recoverable):
    # it keeps a known failure past its effect timeout, and a 429 is one.
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), readings=1, late=True)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "http_429")
    workflow.monotonic = lambda: adapters.elapsed[0]

    specimen = workflow.drain(principal, ident)

    run = specimen.run
    step = f"transcribe:{run.regions[0].id}:{MUSE}"
    assert requests(tmp_path, "transcribe") == 1
    assert (run.stage, run.blocker) == ("retry_scheduled", "model_rate_limited")
    assert "external_stage_deadline_exceeded" not in run.reasons
    [call] = [c for c in run.paid_calls if c["step"] == step]
    assert ledger_rows([call]) == [(1, "failed", "refused", 0, None, "model_rate_limited")]
    others = sum(c["cost_micros"] for c in run.paid_calls if c["step"] != step)
    assert run.usage.reserved_cost_micros == others
    assert ProgramLedger(workflow.repository, SCOPE).read()["reserved_total_micros"] == others
    assert research_state(backend, specimen)["ordinary_reservations"][f"{step}:1"][
        "settled_micros"
    ] == 0


def test_a_reading_refused_with_429_costs_nothing_on_every_attempt(tmp_path, monkeypatch):
    adapters = ChildLab(LocalBlobs(tmp_path / "blobs"), readings=3)
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "http_429")

    *retried, last = drains(workflow, principal, ident, backend)

    run = last.run
    region = run.regions[0].id
    step = f"transcribe:{region}:{MUSE}"
    assert [d.run.blocker for d in retried] == ["model_rate_limited"] * 2
    assert requests(tmp_path, "transcribe") == 3
    # Given up after max_attempts, as before: the record goes to review.
    assert (run.stage, run.disposition, run.attempts[step]) == ("finalized", Disposition.REVIEW, 3)
    assert f"independent_observations_missing:{region}" in run.reasons
    calls = [c for c in run.paid_calls if c["step"] == step]
    assert ledger_rows(calls) == [
        (n, "failed", "refused", 0, None, "model_rate_limited") for n in (1, 2, 3)
    ]
    reading = step_reservation(run, step)
    assert reading > 0 and {c["reserved_micros"] for c in calls} == {reading}
    # Each attempt went out with only its own reservation added; before this
    # change each refused reading stayed held in full.
    others = sum(
        c["cost_micros"] for c in run.paid_calls if c["step"] not in {step, "segment"}
    )
    assert adapters.reader_exposure == [SAM_RESERVATION + others + reading] * 3
    assert run.usage.reserved_cost_micros == SAM_RESERVATION + others
    assert last.program == run.usage.reserved_cost_micros
    reservations = last.research["ordinary_reservations"]
    assert [reservations[f"{step}:{n}"]["settled_micros"] for n in (1, 2, 3)] == [0, 0, 0]


def test_the_organisers_refused_call_costs_nothing(tmp_path, monkeypatch):
    # `parse` makes one model call (extract_with_agent); a 429 to it is refused
    # on every attempt here. After its last attempt the extraction is given up
    # on and the run goes on to its disposition (2026-10-12; it used to stop as
    # retry_budget_exhausted:model_rate_limited).
    adapters = ChildOrganiser(LocalBlobs(tmp_path / "blobs"))
    workflow, principal, ident, backend = lab(tmp_path, monkeypatch, adapters, "http_429")

    *retried, last = drains(workflow, principal, ident, backend)

    run = last.run
    assert [d.run.blocker for d in retried] == ["model_rate_limited"] * 2
    assert requests(tmp_path, "extract") == 3
    assert not run.dead_letter and run.blocker is None
    assert (run.stage, run.disposition) == ("finalized", Disposition.REVIEW)
    assert [f.reason_code for f in run.findings if f.rule_id == "extraction_given_up"] == [
        "extraction_given_up:model_rate_limited"
    ]
    calls = [c for c in run.paid_calls if c["step"] == "parse"]
    assert ledger_rows(calls) == [
        (n, "failed", "refused", 0, None, "model_rate_limited") for n in (1, 2, 3)
    ]
    assert {c["reserved_micros"] for c in calls} == {PARSE_RESERVATION}
    others = sum(c["cost_micros"] for c in run.paid_calls if c["step"] != "parse")
    assert run.usage.reserved_cost_micros == others == last.program
