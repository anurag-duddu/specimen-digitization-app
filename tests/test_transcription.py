from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from specimen_digitization.prompts import PromptName, ResolvedPrompt
from specimen_digitization.transcription import (
    LiteralTranscription,
    build_literal_transcription_agent,
)


class FakeGateway:
    def model_for(self, route_id: str) -> TestModel:
        assert route_id == "handwriting-qwen"
        return TestModel()


def test_literal_transcription_requires_lines_to_reconstruct_text() -> None:
    with pytest.raises(ValidationError, match="reconstruct"):
        LiteralTranscription(
            verbatim_text="line one\nline two",
            lines=["line one"],
        )


def test_transcription_agent_has_a_stable_logfire_name() -> None:
    prompt = ResolvedPrompt(
        name=PromptName.LITERAL_TRANSCRIPTION,
        text="Transcribe literally.",
        requested_label="candidate",
        served_label="candidate",
        version=2,
        resolution_reason="remote",
    )

    agent = build_literal_transcription_agent(
        FakeGateway(),
        route_id="handwriting-qwen",
        prompt=prompt,
    )

    assert agent.name == "literal_transcriber_handwriting_qwen"


@pytest.mark.parametrize(
    ("mode", "content"),
    [("approved-content", True), ("metadata", False), (None, False)],
)
def test_reader_agent_records_content_only_under_approved_content(
    monkeypatch, mode, content
) -> None:
    from specimen_digitization import observability

    monkeypatch.setattr(
        observability,
        "_configured_settings",
        None
        if mode is None
        else observability.ObservabilitySettings(
            environment="test",
            service_name="specimen-worker",
            capture_mode=observability.CaptureMode(mode),
            head_sample_rate=1.0,
            distributed_tracing=False,
        ),
    )
    prompt = ResolvedPrompt(
        name=PromptName.LITERAL_TRANSCRIPTION,
        text="Transcribe literally.",
        requested_label="candidate",
        served_label="candidate",
        version=2,
        resolution_reason="remote",
    )

    agent = build_literal_transcription_agent(
        FakeGateway(), route_id="handwriting-qwen", prompt=prompt
    )

    assert agent.instrument.include_content is content
    assert agent.instrument.include_model_request_parameters is content
    assert agent.instrument.include_binary_content is False
