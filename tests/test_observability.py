from __future__ import annotations

import json
from unittest.mock import Mock

import logfire
import pytest
from logfire.testing import CaptureLogfire

from specimen_digitization import observability
from specimen_digitization.logfire_smoke import run_synthetic_harness
from specimen_digitization.observability import (
    CaptureMode,
    ObservabilityConfigurationError,
    ObservabilitySettings,
)


def test_configure_observability_uses_metadata_policy_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("LOGFIRE_CAPTURE_MODE", "metadata")
    monkeypatch.setenv("LOGFIRE_HEAD_SAMPLE_RATE", "1.0")
    monkeypatch.setenv("LOGFIRE_DISTRIBUTED_TRACING", "false")
    monkeypatch.setattr(observability, "_configured_settings", None)
    configure = Mock()
    instrument = Mock()
    sampling = object()
    monkeypatch.setattr(logfire, "configure", configure)
    monkeypatch.setattr(logfire, "instrument_pydantic_ai", instrument)
    monkeypatch.setattr(logfire, "SamplingOptions", Mock(return_value=sampling))

    settings = observability.configure_observability(send_to_logfire=False)

    assert settings.capture_mode is CaptureMode.METADATA
    configure.assert_called_once_with(
        service_name="specimen-digitization",
        service_version="0.1.0",
        environment="development",
        inspect_arguments=False,
        distributed_tracing=False,
        sampling=sampling,
        resource_attributes={
            "specimen.telemetry.capture_mode": "metadata",
        },
        send_to_logfire=False,
    )
    instrument.assert_called_once_with(
        include_content=False,
        include_binary_content=False,
        include_model_request_parameters=True,
        version=5,
    )


def test_approved_content_still_excludes_binary_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOGFIRE_HEAD_SAMPLE_RATE", "1")

    settings = ObservabilitySettings.from_environment(
        capture_mode=CaptureMode.APPROVED_CONTENT
    )

    assert settings.include_content is True
    assert settings.include_binary_content is False
    assert settings.include_model_request_parameters is True


@pytest.mark.parametrize("sample_rate", ["0", "1.1", "not-a-number"])
def test_invalid_sample_rate_fails_closed(
    monkeypatch: pytest.MonkeyPatch, sample_rate: str
) -> None:
    monkeypatch.setenv("LOGFIRE_HEAD_SAMPLE_RATE", sample_rate)

    with pytest.raises(ObservabilityConfigurationError, match="SAMPLE_RATE"):
        ObservabilitySettings.from_environment()


def test_synthetic_harness_emits_nested_metadata_only_spans(
    capfire: CaptureLogfire,
) -> None:
    logfire.instrument_pydantic_ai(
        include_content=False,
        include_binary_content=False,
        include_model_request_parameters=False,
    )

    run_synthetic_harness()

    spans = capfire.exporter.exported_spans_as_dict()
    span_names = {span["name"] for span in spans}
    serialized_spans = json.dumps(spans)

    assert "Run synthetic specimen harness smoke" in span_names
    assert "invoke_agent synthetic_observability_smoke" in span_names
    assert "chat test" in span_names
    assert "Verify the specimen harness telemetry path." not in serialized_spans
    assert (
        "Return a deterministic result for an observability check."
        not in serialized_spans
    )
