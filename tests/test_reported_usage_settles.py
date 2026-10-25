"""A failed model call settles at the tokens its provider reported (PLAN 4.3).

Production, 2026-10-17, the 11-record batch: 26 of the 32 model calls held at
their full reservation had reported their tokens. Specimen 19f0f1f6's first
pass answered twice, both times with `selected_reader` the string "null"
(2,153 tokens in and 2,202 out, about 1,424 micro-dollars), and was held at
318,670. The answers were billed and their tokens known: a call whose provider
reported every request's tokens now costs what those tokens cost. A call whose
spend is unknown (a timeout, a 5xx, a reply nobody counted) stays reserved in
full, as before.

These drive `reliability.run_agent_bounded` with a real Pydantic AI agent and
a scripted model, as `test_rate_limit_refusal` does.
"""

import asyncio

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage, UsageLimits

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.lane_costs import model_cost, record_step
from specimen_digitization.application.lane_reservations import step_reservation
from specimen_digitization.application.reliability import (
    AdapterFailure,
    checked_usage,
    run_agent_bounded,
    stopped_usage,
)

# The bounds production gives a reading, a first pass and the extraction.
LIMITS = UsageLimits(request_limit=2, total_tokens_limit=16_000)


class Pick(BaseModel):
    selected_reader: int


def scripted(*answers):
    """A model that answers each request with the next of `answers`: a usage
    pair for an answer that fails validation, an exception to raise, or an
    awaitable to wait on (a provider that does not answer)."""
    queue = list(answers)

    async def respond(messages, info):
        answer = queue.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        if answer == "stall":
            await asyncio.sleep(30)
        input_tokens, output_tokens = answer
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"selected_reader": "null"})],
            usage=RequestUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            finish_reason="stop",
        )

    return Agent(FunctionModel(respond, model_name="local"), output_type=Pick), queue


def failure_of(agent, limits=LIMITS, timeout=10):
    with pytest.raises(AdapterFailure) as failure:
        run_agent_bounded(agent, "x", timeout_seconds=timeout, usage_limits=limits)
    return failure.value


def test_a_malformed_answer_carries_the_tokens_its_provider_reported():
    # 19f0f1f6's first pass: two answers, both "null", 2,153 in and 2,202 out.
    agent, queue = scripted((1_076, 1_101), (1_077, 1_101))
    failure = failure_of(agent)
    assert queue == []
    assert failure.code == "model_malformed_response"
    assert failure.usage == {"input_tokens": 2_153, "output_tokens": 2_202}
    prices = published_registry().resolve("insects").profile.processing.price_list
    # At GLM's 0.15 and 0.50 per million: 1,424, against 318,670 held.
    assert model_cost(prices.model_dump(mode="json"), "first-pass-glm", 2_153, 2_202) == 1_424


def test_a_call_that_could_still_send_a_request_stays_unknown():
    # The proof that the queued retry was not sent is the call's request limit,
    # which every production model read sets to 2. A limit the answers did not
    # use up proves nothing, so the call is held: over, never under.
    agent, _ = scripted((1_076, 1_101), (1_077, 1_101))
    limits = UsageLimits(request_limit=3, total_tokens_limit=16_000)
    assert failure_of(agent, limits).usage is None


def answering(*answers):
    """A model whose answers are `(selected_reader, input_tokens, output_tokens)`."""
    queue = list(answers)

    def respond(messages, info):
        reader, input_tokens, output_tokens = queue.pop(0)
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"selected_reader": reader})],
            usage=RequestUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            finish_reason="stop",
        )

    return Agent(FunctionModel(respond, model_name="local"), output_type=Pick), queue


def test_a_completed_call_counts_every_answer_and_not_its_output_tools_return():
    from specimen_digitization.application.reliability import reported_usage

    # 19f0f1f6's parse: one answer, 1,627 in and 1,077 out. After it the agent
    # queues the output tool's return, which nothing sends.
    agent, _ = answering((1, 1_627, 1_077))
    result = run_agent_bounded(agent, "x", timeout_seconds=10, usage_limits=LIMITS)
    messages = result.all_messages()
    assert [m.kind for m in messages] == ["request", "response", "request"]
    assert {p.part_kind for p in messages[-1].parts} == {"tool-return"}
    # Before: counted as a request sent and not answered, so unknown.
    assert reported_usage(messages, result.usage) is None
    assert reported_usage(messages, result.usage, completed=True) == {
        "input_tokens": 1_627,
        "output_tokens": 1_077,
    }
    # A malformed answer, then its retry answered: both were billed.
    agent, queue = answering(("null", 1_076, 1_101), (1, 1_200, 30))
    result = run_agent_bounded(agent, "x", timeout_seconds=10, usage_limits=LIMITS)
    assert queue == []
    assert [m.kind for m in result.all_messages()] == ["request", "response"] * 2 + ["request"]
    assert reported_usage(result.all_messages(), result.usage, completed=True) == {
        "input_tokens": 2_276,
        "output_tokens": 1_131,
    }


def test_a_completed_call_whose_last_request_is_not_a_tool_return_stays_unknown():
    # Only the output tool's return is proof of a request never sent. A retry
    # prompt in its place may have been sent, so the call is held.
    from pydantic_ai.messages import ModelRequest, RetryPromptPart, UserPromptPart
    from pydantic_ai.usage import RunUsage

    from specimen_digitization.application.reliability import reported_usage

    request = ModelRequest(parts=[UserPromptPart("x")])
    answer = ModelResponse(
        parts=[ToolCallPart("final_result", {"selected_reader": "null"})],
        usage=RequestUsage(input_tokens=1_076, output_tokens=1_101),
    )
    retry = ModelRequest(parts=[RetryPromptPart("invalid", tool_name="final_result")])
    usage = RunUsage(requests=1, input_tokens=1_076, output_tokens=1_101)
    assert reported_usage([request, answer, retry], usage, completed=True) is None


def test_an_answer_the_client_could_not_read_leaves_the_spend_unknown():
    # The second request was sent; what came back was not counted, and the
    # provider may have billed it.
    agent, _ = scripted((1_000, 40), UnexpectedModelBehavior("Invalid response"))
    failure = failure_of(agent)
    assert failure.code == "model_malformed_response"
    assert failure.usage is None


def test_answers_that_report_no_tokens_leave_the_spend_unknown():
    # A provider that sends no usage: Pydantic AI records zero tokens for it.
    # (Its FunctionModel would estimate some, so the messages are built here.)
    from pydantic_ai.messages import ModelRequest, TextPart, UserPromptPart
    from pydantic_ai.usage import RunUsage

    from specimen_digitization.application.reliability import reported_usage

    request = ModelRequest(parts=[UserPromptPart("x")])
    silent = ModelResponse(parts=[TextPart("a")], usage=RequestUsage())
    counted = ModelResponse(parts=[TextPart("a")], usage=RequestUsage(input_tokens=900))
    assert reported_usage([request, silent], RunUsage(requests=1)) is None
    assert reported_usage(
        [request, counted, request, silent], RunUsage(requests=2, input_tokens=900)
    ) is None
    assert reported_usage([request, counted], RunUsage(requests=1, input_tokens=900)) == {
        "input_tokens": 900,
        "output_tokens": 0,
    }


def test_a_timeout_after_an_answer_reports_no_usage_and_stays_reserved():
    # The first answer reported its tokens; the retry was sent and not answered
    # in time, so what the call cost in all is unknown.
    agent, _ = scripted((1_000, 40), "stall")
    failure = failure_of(agent, timeout=0.5)
    assert (failure.code, failure.outcome_unknown) == ("provider_deadline_outcome_unknown", True)
    assert failure.usage is None
    run, step = first_pass_run()
    record_step(None, None, specimen_of(run), step, [], 0.5, 0, failure=failure.code,
        usage=failure.usage)
    [call] = run.paid_calls
    assert (call["outcome"], call["cost_basis"], call["usage"]) == ("failed", "reserved", None)
    assert call["cost_micros"] == step_reservation(run, step)


@pytest.mark.parametrize("status", [503, 429])
def test_a_provider_error_after_an_answer_reports_no_usage(status):
    from pydantic_ai.exceptions import ModelHTTPError

    agent, _ = scripted((1_000, 40), ModelHTTPError(status, "local", body="failed"))
    assert failure_of(agent).usage is None


def test_a_call_stopped_after_an_answer_counts_that_answer():
    # Pydantic AI counts an answer's tokens before it checks the limit, and
    # then does not keep the answer it refused: the tokens are still billed.
    agent, _ = scripted((15_000, 2_000))
    with pytest.raises(UsageLimitExceeded) as stop:
        run_agent_bounded(agent, "x", timeout_seconds=10, usage_limits=LIMITS)
    assert [m.kind for m in stop.value.run_messages] == ["request"]
    assert stopped_usage(stop.value) == {"input_tokens": 15_000, "output_tokens": 2_000}


def test_a_call_stopped_before_its_retry_was_sent_counts_its_answer():
    # One request allowed: the retry is stopped before it is sent.
    agent, queue = scripted((1_000, 40), (1_000, 40))
    with pytest.raises(UsageLimitExceeded) as stop:
        run_agent_bounded(
            agent, "x", timeout_seconds=10, usage_limits=UsageLimits(request_limit=1)
        )
    assert len(queue) == 1  # The retry was never asked.
    assert stopped_usage(stop.value) == {"input_tokens": 1_000, "output_tokens": 40}


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"input_tokens": 0, "output_tokens": 5},
        {"input_tokens": -1, "output_tokens": 5},
        {"input_tokens": 1.5, "output_tokens": 5},
        {"input_tokens": True, "output_tokens": 5},
        {"input_tokens": 10, "output_tokens": 5, "requests": 2},
        [10, 5],
    ],
)
def test_usage_that_is_not_two_token_counts_is_unknown(value):
    # What crosses the model child's process boundary is priced only in this shape.
    assert checked_usage(value) is None


def first_pass_run():
    from test_lane_routes import first_pass_run as run_and_step

    run, step = run_and_step()
    run.attempts[step] = 1
    return run, step


def specimen_of(run):
    from test_lane_trigger import specimen_with

    return specimen_with(run)


@pytest.mark.parametrize("kind", ["first_pass", "transcribe"])
def test_a_failed_call_with_reported_usage_is_recorded_at_its_cost(kind):
    run, step = first_pass_run()
    route = run.profile.first_pass_route
    if kind == "transcribe":
        route = "handwriting-qwen"
        step = f"transcribe:{run.regions[0].id}:{route}"
        run.attempts[step] = 1
    usage = {"input_tokens": 2_153, "output_tokens": 2_202}
    record_step(None, None, specimen_of(run), step, [], 9.0, 0,
        failure="model_malformed_response", usage=usage)
    [call] = run.paid_calls
    prices = run.profile.execution.price_list
    assert (call["outcome"], call["cost_basis"], call["route_id"], call["usage"]) == (
        "failed", "computed", route, usage
    )
    assert call["failure_code"] == "model_malformed_response"
    assert call["cost_micros"] == model_cost(prices, route, 2_153, 2_202)
    assert call["cost_micros"] < call["reserved_micros"]
    # A known cost: the run's actual cost is known too.
    assert run.usage.actual_cost_micros == call["cost_micros"]


@pytest.mark.parametrize("kwargs,basis", [
    ({"failure": "model_timeout"}, "reserved"),
    ({}, "reserved"),
    ({"refusal": "model_rate_limited"}, "refused"),
])
def test_a_held_or_refused_parse_names_the_route_it_calls(kwargs, basis):
    # Before 2026-10-25 these named the step ("parse"), which no bill names.
    run, _ = first_pass_run()
    run.attempts["parse"] = 1
    record_step(None, None, specimen_of(run), "parse", [], 4.0, 0, **kwargs)
    [call] = run.paid_calls
    assert (call["route_id"], call["cost_basis"]) == (run.profile.routes[0], basis)
    assert call["route_id"] != "parse"


def test_a_completed_parse_is_priced_at_the_route_it_calls():
    # The extraction (harness.extract_with_agent) calls the profile's first
    # route; before, parse kept its whole reservation (58,164 on the pilot).
    run, _ = first_pass_run()
    run.attempts["parse"] = 1
    run.completed_steps.append("parse")
    usage = {"input_tokens": 1_627, "output_tokens": 1_077}
    record_step(None, None, specimen_of(run), "parse", [], 4.0, 0, usage=usage)
    [call] = run.paid_calls
    route = run.profile.routes[0]
    assert (call["outcome"], call["cost_basis"], call["route_id"]) == ("completed", "computed", route)
    # 19f0f1f6's parse at handwriting-qwen's 0.20 and 0.70 per million: 1,080.
    assert call["cost_micros"] == model_cost(run.profile.execution.price_list, route, 1_627, 1_077)
    assert "failure_code" not in call
