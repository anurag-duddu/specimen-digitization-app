"""Provider error bodies and prompts stay private even under global capture."""

import base64
import json

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.instrumented import InstrumentationSettings

from specimen_digitization.provider_privacy import (
    PrivateProviderModel,
    private_instrumentation,
)


def test_private_provider_sanitizes_errors_before_agent_spans(capfire):
    previous = Agent._instrument_default
    try:
        Agent.instrument_all(InstrumentationSettings(include_content=True))
        for failure in (
            ModelHTTPError(401, "fixture", "private_provider_body_canary"),
            RuntimeError("private_provider_body_canary"),
        ):

            def model(messages, info):
                raise failure

            agent = Agent(
                PrivateProviderModel(FunctionModel(model)),
                instructions="private_prompt_canary",
            )
            agent.instrument = private_instrumentation()
            with pytest.raises((ModelHTTPError, RuntimeError)):
                agent.run_sync("private_label_canary")
        trace = json.dumps(capfire.exporter.exported_spans_as_dict(), default=str)
        assert "private_provider_body_canary" not in trace
        assert "private_prompt_canary" not in trace
        assert "private_label_canary" not in trace
    finally:
        Agent.instrument_all(previous)


def configured(monkeypatch, mode):
    """Record the settings configure_observability would, without configuring."""
    from specimen_digitization import observability

    settings = None
    if mode is not None:
        settings = observability.ObservabilitySettings(
            environment="test",
            service_name="specimen-worker",
            capture_mode=observability.CaptureMode(mode),
            head_sample_rate=1.0,
            distributed_tracing=False,
        )
    monkeypatch.setattr(observability, "_configured_settings", settings)


@pytest.mark.parametrize("mode", ["approved-content", "metadata", None])
def test_agent_instrumentation_follows_the_configured_capture_mode(
    capfire, monkeypatch, mode
):
    """G3: prompt, input and output are recorded exactly when the process is
    configured for approved-content; image bytes and provider error bodies never."""
    from pydantic_ai import BinaryContent
    from pydantic_ai.messages import ModelResponse, TextPart

    from specimen_digitization.provider_privacy import agent_instrumentation

    configured(monkeypatch, mode)
    image = b"\x89PNG\r\n\x1a\nimage_bytes_canary"
    previous = Agent._instrument_default
    try:
        # A global content setting does not decide it: the agent's own does.
        Agent.instrument_all(InstrumentationSettings(include_content=True))

        def answer(messages, info):
            return ModelResponse(parts=[TextPart("reader_output_canary")])

        def fail(messages, info):
            raise ModelHTTPError(401, "fixture", "private_provider_body_canary")

        for model in (answer, fail):
            agent = Agent(
                PrivateProviderModel(FunctionModel(model)),
                instructions="reader_prompt_canary",
            )
            agent.instrument = agent_instrumentation()
            prompt = ["reader_label_canary", BinaryContent(image, media_type="image/png")]
            if model is answer:
                agent.run_sync(prompt)
            else:
                with pytest.raises(ModelHTTPError):
                    agent.run_sync(prompt)
        spans = capfire.exporter.exported_spans_as_dict()
        trace = json.dumps(spans, default=str)
        assert any(span["name"].startswith("invoke_agent") for span in spans)
        assert "private_provider_body_canary" not in trace
        assert "image_bytes_canary" not in trace
        assert base64.b64encode(image).decode() not in trace
        shown = mode == "approved-content"
        for canary in (
            "reader_prompt_canary",
            "reader_label_canary",
            "reader_output_canary",
        ):
            assert (canary in trace) is shown
    finally:
        Agent.instrument_all(previous)


@pytest.mark.parametrize("mode", ["metadata", None])
def test_agent_instrumentation_outside_approved_content_is_private(monkeypatch, mode):
    from specimen_digitization.provider_privacy import agent_instrumentation

    configured(monkeypatch, mode)
    fields = (
        "include_content",
        "include_binary_content",
        "include_model_request_parameters",
        "version",
    )
    actual, private = agent_instrumentation(), private_instrumentation()
    assert [getattr(actual, f) for f in fields] == [
        getattr(private, f) for f in fields
    ]
