from __future__ import annotations

import json
from unittest.mock import Mock

import logfire
from logfire.testing import CaptureLogfire

from specimen_digitization import observability
from specimen_digitization.logfire_smoke import run_synthetic_harness


def test_configure_observability_uses_privacy_defaults(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOGFIRE_INCLUDE_CONTENT", "false")
    monkeypatch.setenv("LOGFIRE_INCLUDE_BINARY_CONTENT", "false")
    monkeypatch.setenv("LOGFIRE_INCLUDE_MODEL_REQUEST_PARAMETERS", "false")
    monkeypatch.setattr(observability, "_configured", False)
    configure = Mock()
    instrument = Mock()
    monkeypatch.setattr(logfire, "configure", configure)
    monkeypatch.setattr(logfire, "instrument_pydantic_ai", instrument)

    observability.configure_observability(send_to_logfire=False)

    configure.assert_called_once_with(
        service_name="specimen-digitization",
        service_version="0.1.0",
        environment="development",
        inspect_arguments=False,
        send_to_logfire=False,
    )
    instrument.assert_called_once_with(
        include_content=False,
        include_binary_content=False,
        include_model_request_parameters=False,
    )


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
    assert "invoke_agent agent" in span_names
    assert "chat test" in span_names
    assert "Verify the specimen harness telemetry path." not in serialized_spans
    assert (
        "Return a deterministic result for an observability check."
        not in serialized_spans
    )
