"""Generation limits must reach the provider before initial and retry requests."""

import pytest
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.exceptions import (
    IncompleteToolCall,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage, UsageLimits

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.application.reliability import (
    AdapterFailure,
    run_agent_bounded,
)
from specimen_digitization.provider_privacy import PrivateProviderModel


class Reading(BaseModel):
    text: str = Field(min_length=1)


@pytest.mark.parametrize(
    "total_limit,output_limit,agent_cap,expected_caps",
    [
        (16000, None, None, [4096, 4096]),
        (16000, 64, None, [64, 63]),
        (32, None, None, [32, 30]),
        (16000, None, 128, [128, 128]),
    ],
)
def test_generation_is_capped_before_initial_and_schema_retry_requests(
    total_limit, output_limit, agent_cap, expected_caps
):
    observed_caps = []

    def respond(messages, info):
        observed_caps.append((info.model_settings or {}).get("max_tokens"))
        # Force one genuine Pydantic validation retry, then return a valid result.
        text = "" if len(observed_caps) == 1 else "Exact label text"
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"text": text})],
            usage=RequestUsage(input_tokens=1, output_tokens=1),
        )

    agent = Agent(
        FunctionModel(respond),
        output_type=Reading,
        model_settings={"max_tokens": agent_cap} if agent_cap is not None else None,
    )
    result = run_agent_bounded(
        agent,
        "Read the synthetic label",
        timeout_seconds=5,
        usage_limits=UsageLimits(
            request_limit=2,
            total_tokens_limit=total_limit,
            output_tokens_limit=output_limit,
        ),
    )

    assert result.output.text == "Exact label text"
    assert result.usage.requests == 2
    assert observed_caps == expected_caps


@pytest.mark.parametrize("origin", ["model", "wrapped_model", "callable_agent"])
def test_generation_preserves_resolved_provider_and_dynamic_agent_caps(origin):
    observed_caps = []
    settings_evaluations = []

    def respond(messages, info):
        observed_caps.append(info.model_settings["max_tokens"])
        assert info.model_settings["temperature"] == 0.5
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {
                "text": "" if len(observed_caps) == 1 else "Label",
            })],
            usage=RequestUsage(input_tokens=1, output_tokens=1),
        )

    def dynamic_settings(ctx):
        settings_evaluations.append(ctx.usage.output_tokens)
        return {"max_tokens": 8 - ctx.usage.output_tokens, "temperature": 0.5}

    model = FunctionModel(
        respond,
        settings=None if origin == "callable_agent" else {
            "max_tokens": 8, "temperature": 0.5,
        },
    )
    if origin == "wrapped_model":
        model = PrivateProviderModel(model)
    agent = Agent(
        model,
        output_type=Reading,
        model_settings=dynamic_settings if origin == "callable_agent" else None,
    )
    result = run_agent_bounded(
        agent, "Read the synthetic label", timeout_seconds=5,
        usage_limits=UsageLimits(request_limit=2, total_tokens_limit=16000),
    )
    assert result.output.text == "Label"
    assert observed_caps == ([8, 7] if origin == "callable_agent" else [8, 8])
    assert settings_evaluations == ([0, 1] if origin == "callable_agent" else [])


def test_exhausted_output_allowance_stops_before_another_provider_request():
    calls = []

    def respond(messages, info):
        calls.append(info.model_settings["max_tokens"])
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"text": ""})],
            usage=RequestUsage(input_tokens=1, output_tokens=1),
        )

    with pytest.raises(UsageLimitExceeded, match="No output token allowance"):
        run_agent_bounded(
            Agent(FunctionModel(respond), output_type=Reading),
            "Read the synthetic label", timeout_seconds=5,
            usage_limits=UsageLimits(request_limit=2, output_tokens_limit=1),
        )
    assert calls == [1]


def bounded(*responses):
    """run_agent_bounded against a fake provider whose responses, in turn, are
    functions of the output tool's name."""
    calls = []

    def respond(messages, info):
        calls.append(messages)
        return responses[len(calls) - 1](info.output_tools[0].name)

    return run_agent_bounded(
        Agent(FunctionModel(respond), output_type=Reading),
        "Read the synthetic label",
        timeout_seconds=5,
        usage_limits=UsageLimits(request_limit=2, total_tokens_limit=16000),
    )


@pytest.mark.parametrize(
    "response,cause,requests",
    [
        (
            lambda tool: ModelResponse(
                parts=[ToolCallPart(tool, '{"text": "Exact la')],
                finish_reason="length",
            ),
            IncompleteToolCall,
            2,  # Pydantic AI raises it once the output retry is cut off too.
        ),
        (
            lambda tool: ModelResponse(parts=[], finish_reason="length"),
            UnexpectedModelBehavior,
            1,  # An empty answer at its cap is not retried.
        ),
    ],
    ids=["an incomplete tool call", "an empty answer"],
)
def test_an_answer_cut_off_at_its_output_cap_is_a_cap_hit(response, cause, requests):
    # HARNESS.md 3, agreed with S3 for #153: not a malformed answer but a cap hit,
    # which every caller routes as it routes the run's own limits.
    with pytest.raises(UsageLimitExceeded) as stop:
        bounded(response, response)

    assert type(stop.value.__cause__) is cause
    responses = [m for m in stop.value.run_messages if m.kind == "response"]
    assert [m.finish_reason for m in responses] == ["length"] * requests


def test_any_other_unexpected_behavior_stays_a_known_malformed_response():
    def invalid(tool):
        return ModelResponse(
            parts=[ToolCallPart(tool, {"text": ""})], finish_reason="stop"
        )

    with pytest.raises(AdapterFailure) as failure:
        bounded(invalid, invalid)

    assert failure.value.code == "model_malformed_response"
    assert failure.value.status == LookupStatus.MALFORMED
    assert failure.value.outcome_unknown is False


def test_a_run_stopped_by_its_limits_reports_what_it_used_for_the_callers_record():
    def spent(tool):
        return ModelResponse(
            parts=[ToolCallPart(tool, {"text": "Label"})],
            usage=RequestUsage(input_tokens=15_500, output_tokens=900),
        )

    with pytest.raises(UsageLimitExceeded) as stop:
        bounded(spent)

    usage = stop.value.run_usage
    assert (usage.input_tokens, usage.output_tokens) == (15_500, 900)
    # Pydantic AI counts the response past its total but stops before keeping it.
    assert [m.kind for m in stop.value.run_messages] == ["request"]
