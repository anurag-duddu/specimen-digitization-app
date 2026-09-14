"""Approved installation uses synthetic credentials and no network transport."""

import os
import time
from unittest.mock import Mock

import pytest

from specimen_digitization import observability as M
from specimen_digitization.application import bounded_effect, worker_deadline
from specimen_digitization.bounded_telemetry import Ledger

APPROVAL = "06af8483b7b190a5b0f2549475681a60483f2aff98a714472baad28376703b48"  # pragma: allowlist secret (approval digest)


@pytest.fixture
def approved(tmp_path, monkeypatch):
    tmp_path.chmod(0o700)
    ledger = Ledger.create(tmp_path / "trace-budget.sqlite3", deadline=time.monotonic() + 60, scope="a" * 64)
    values = {
        "SPECIMEN_TRACE_EXPORT_MODE": "bounded-v1",
        "SPECIMEN_TRACE_APPROVAL_SHA256": APPROVAL,
        "SPECIMEN_TRACE_SCOPE_SHA256": "a" * 64,
        "SPECIMEN_TRACE_LEDGER_PATH": str(ledger.path),
        "APP_ENV": "production", "LOGFIRE_CAPTURE_MODE": "metadata",
        "LOGFIRE_SEND_TO_LOGFIRE": "false", "LOGFIRE_HEAD_SAMPLE_RATE": "1.0",
        "LOGFIRE_DISTRIBUTED_TRACING": "false", "LOGFIRE_SERVICE_NAME": "specimen-worker",
        "LOGFIRE_TOKEN": "synthetic-writer",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    for name in ("LOGFIRE_BASE_URL", "LOGFIRE_ENVIRONMENT", "LOGFIRE_SERVICE_VERSION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(M, "_configured_settings", None)
    monkeypatch.setattr(M, "_bounded_runtime", None, raising=False)
    end = time.monotonic() + 60
    monkeypatch.setattr(bounded_effect, "current_effect_deadline", lambda: end)
    monkeypatch.setattr(worker_deadline, "current_deadline", lambda: None)
    configure, instrument = Mock(), Mock()
    monkeypatch.setattr(M.logfire, "configure", configure)
    monkeypatch.setattr(M.logfire, "instrument_pydantic_ai", instrument)
    from specimen_digitization import bounded_trace_transport
    monkeypatch.setattr(bounded_trace_transport, "_open_tls", lambda *a: pytest.fail("native network forbidden"))
    return ledger, configure, instrument


def test_approved_installation_uses_only_custom_processor_and_neutral_sdk_credentials(approved):
    ledger, configure, instrument = approved
    assert M.configure_observability().environment == "production"
    options = configure.call_args.kwargs
    assert options["send_to_logfire"] is False
    assert options["token"] != "synthetic-writer"  # pragma: allowlist secret (synthetic test token)
    assert options["api_key"] != "synthetic-writer"  # pragma: allowlist secret (synthetic test token)
    assert options["console"] is False and options["metrics"] is False
    assert options["variables"] is not None
    assert len(options["additional_span_processors"]) == 1
    assert options["additional_span_processors"][0].ledger.path == ledger.path
    assert instrument.call_args.kwargs["include_content"] is False
    assert instrument.call_args.kwargs["include_binary_content"] is False
    M.configure_observability()
    assert configure.call_count == 1


@pytest.mark.parametrize("name,value", [
    ("SPECIMEN_TRACE_APPROVAL_SHA256", ""),
    ("SPECIMEN_TRACE_APPROVAL_SHA256", "b" * 64),
    ("SPECIMEN_TRACE_EXPORT_MODE", "other"),
    ("SPECIMEN_TRACE_SCOPE_SHA256", "b" * 64),
    ("LOGFIRE_CAPTURE_MODE", "approved-content"),
    ("APP_ENV", "development"),
    ("LOGFIRE_SEND_TO_LOGFIRE", "true"),
    ("LOGFIRE_HEAD_SAMPLE_RATE", "0.5"),
    ("LOGFIRE_DISTRIBUTED_TRACING", "true"),
    ("LOGFIRE_BASE_URL", "https://unreviewed.example"),
    ("LOGFIRE_ENVIRONMENT", "other"),
    ("LOGFIRE_SERVICE_VERSION", "other"),
    ("SSLKEYLOGFILE", "/synthetic/forbidden"),
    ("SSL_CERT_FILE", "/synthetic/forbidden"),
    ("SSL_CERT_DIR", "/synthetic/forbidden"),
    ("SPECIMEN_TRACE_LEDGER_PATH", "/missing/trace-budget.sqlite3"),
])
def test_invalid_installation_fails_before_token_or_sdk_work(approved, monkeypatch, name, value):
    _, configure, _ = approved
    monkeypatch.setenv(name, value)
    getenv = os.getenv
    def checked_getenv(key, *args):
        assert key != "LOGFIRE_TOKEN", "credential accessed before admission"
        return getenv(key, *args)
    monkeypatch.setattr(M.os, "getenv", checked_getenv)
    with pytest.raises(M.ObservabilityConfigurationError):
        M.configure_observability()
    assert configure.call_count == 0


def test_no_original_supervisor_deadline_rejects_installation(approved, monkeypatch):
    _, configure, _ = approved
    monkeypatch.setattr(bounded_effect, "current_effect_deadline", lambda: None)
    with pytest.raises(M.ObservabilityConfigurationError):
        M.configure_observability()
    assert configure.call_count == 0


def test_explicit_send_or_content_override_cannot_enable_sdk_export(approved):
    _, configure, _ = approved
    with pytest.raises(M.ObservabilityConfigurationError):
        M.configure_observability(send_to_logfire=True)
    with pytest.raises(M.ObservabilityConfigurationError):
        M.configure_observability(capture_mode=M.CaptureMode.APPROVED_CONTENT)
    assert configure.call_count == 0


def test_flush_is_synchronous_sticky_and_checks_original_clock(approved, monkeypatch):
    M.configure_observability()
    assert M.flush_bounded_observability() == {"configured": True, "complete": True}
    monkeypatch.setattr(bounded_effect, "current_effect_deadline", lambda: time.monotonic() - 1)
    assert M.flush_bounded_observability() == {"configured": True, "complete": False}


def test_actual_sdk_in_isolated_model_child_drains_linked_metadata_before_return(approved, tmp_path):
    from bounded_trace_fixture import traced_child
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
    ledger, _, _ = approved
    result = bounded_effect.run_isolated(traced_child, {
        "wire": str(tmp_path / "wire.bin"), "model_done": str(tmp_path / "model.txt"),
    }, 10, 1024, trace_required=True)
    assert result.status == "completed" and result.value == b"known model result"
    assert result.trace_export == {"configured": True, "complete": True}
    snapshot = ledger.snapshot()
    assert snapshot["requests"] == snapshot["accepted"] == 1
    assert snapshot["completion"] and snapshot["unknown"] == 0
    wire = (tmp_path / "wire.bin").read_bytes()
    assert b"PRIVATE-LABEL-CANARY" not in wire and b"PRIVATE-PROMPT-CANARY" not in wire
    _, body = wire.split(b"\r\n\r\n", 1)
    batch = ExportTraceServiceRequest.FromString(body)
    spans = [span for resource in batch.resource_spans for scope in resource.scope_spans for span in scope.spans]
    assert len(spans) == snapshot["records"] == 2
    attributes = {item.key: item.value.string_value for span in spans for item in span.attributes}
    assert attributes["specimen.id"] == "synthetic-specimen"
    assert attributes["specimen.region.id"] == "synthetic-region"
    assert attributes["specimen.route.id"] == "reader-a"
