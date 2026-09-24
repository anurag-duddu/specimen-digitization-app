"""Content in the run's trace (docs/execution/golive/LANE.md, T5b; PLAN 4.5, G3)."""

import json

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from specimen_digitization import observability
from specimen_digitization.observability import CaptureMode, ObservabilitySettings
from specimen_digitization.provider_privacy import (
    PrivateProviderModel,
    agent_instrumentation,
)


def configured(monkeypatch, mode):
    settings = ObservabilitySettings(
        environment="lab",
        service_name="specimen-worker",
        capture_mode=mode,
        head_sample_rate=1.0,
        distributed_tracing=False,
    )
    monkeypatch.setattr(observability, "_configured_settings", settings)


def test_agents_show_content_only_in_the_approved_content_mode(monkeypatch):
    assert agent_instrumentation().include_content is False  # Nothing configured.
    configured(monkeypatch, CaptureMode.METADATA)
    assert agent_instrumentation().include_content is False
    configured(monkeypatch, CaptureMode.APPROVED_CONTENT)
    settings = agent_instrumentation()
    assert settings.include_content is True
    assert settings.include_binary_content is False


def test_approved_content_shows_prompts_but_never_provider_error_bodies(
    monkeypatch, capfire
):
    configured(monkeypatch, CaptureMode.APPROVED_CONTENT)

    def answer(messages, info):
        return ModelResponse(parts=[TextPart("reading_canary")])

    agent = Agent(PrivateProviderModel(FunctionModel(answer)), instructions="prompt_canary")
    agent.instrument = agent_instrumentation()
    agent.run_sync("label_canary")

    def fail(messages, info):
        raise ModelHTTPError(401, "fixture", "provider_body_canary")

    failing = Agent(PrivateProviderModel(FunctionModel(fail)), instructions="prompt_canary")
    failing.instrument = agent_instrumentation()
    with pytest.raises(ModelHTTPError):
        failing.run_sync("label_canary")
    trace = json.dumps(capfire.exporter.exported_spans_as_dict(), default=str)
    for visible in ("prompt_canary", "label_canary", "reading_canary"):
        assert visible in trace
    assert "provider_body_canary" not in trace


def test_model_children_configure_the_parents_mode(monkeypatch):
    configured(monkeypatch, CaptureMode.APPROVED_CONTENT)
    context = observability.model_trace_context("specimen-1", "run-1")
    assert context["capture_mode"] == "approved-content"
    seen = []
    monkeypatch.setattr(
        observability,
        "configure_observability",
        lambda **options: seen.append(options["capture_mode"]),
    )
    monkeypatch.setattr(observability.logfire, "shutdown", lambda **_: None)
    for carrier, expected in (
        (context, CaptureMode.APPROVED_CONTENT),
        ({"specimen_id": "specimen-1", "run_id": "run-1"}, CaptureMode.METADATA),
        (dict(context, capture_mode="everything"), CaptureMode.METADATA),
    ):
        with observability.isolated_model_span(carrier, operation="transcribe"):
            pass
        assert seen[-1] == expected
