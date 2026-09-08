"""Provider error bodies and prompts stay private even under global capture."""

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
