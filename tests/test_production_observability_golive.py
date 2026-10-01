"""Standing G3 SDK configuration and actual offline span privacy/lineage. No network."""
import json
from types import SimpleNamespace
from unittest.mock import Mock
import logfire
import pytest
from specimen_digitization import observability as O

SHA = "a" * 40

@pytest.fixture
def production(monkeypatch, tmp_path):
    for key in list(O.os.environ):
        if key.startswith(("OTEL_", "SPECIMEN_TRACE_")) or key in {"LOGFIRE_BASE_URL", "LOGFIRE_ENVIRONMENT", "LOGFIRE_SERVICE_VERSION"}:
            monkeypatch.delenv(key, raising=False)
    package = tmp_path / "package"
    package.mkdir()
    (package / "_build.json").write_text(json.dumps({"source_sha": SHA}))
    monkeypatch.setattr(O, "__file__", str(package / "observability.py"))
    for key, value in {"APP_ENV": "production", "LOGFIRE_CAPTURE_MODE": "approved-content",
        "LOGFIRE_SEND_TO_LOGFIRE": "true", "LOGFIRE_SERVICE_NAME": "specimen-worker",
        "LOGFIRE_HEAD_SAMPLE_RATE": "1.0", "LOGFIRE_DISTRIBUTED_TRACING": "true",
        "LOGFIRE_TOKEN": "SYNTHETIC-WRITER-CANARY"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(O, "_configured_settings", None)
    monkeypatch.setattr(O, "_bounded_runtime", None)
    return package


@pytest.mark.parametrize("role", ["api", "worker", "sam"])
def test_actual_standing_sdk_configuration_uses_source_production_and_approved_content(production, monkeypatch, role):
    configure, instrument = Mock(), Mock()
    monkeypatch.setattr(logfire, "configure", configure)
    monkeypatch.setattr(logfire, "instrument_pydantic_ai", instrument)
    service = "specimen-" + role
    monkeypatch.setenv("LOGFIRE_SERVICE_NAME", service)
    settings = O.configure_production_observability(service, instrument_agents=role != "sam")
    assert settings.environment == "production" and settings.include_content and not settings.include_binary_content
    options = configure.call_args.kwargs
    assert options["send_to_logfire"] is True
    assert options["environment"] == "production" and options["service_version"] == SHA
    assert options["service_name"] == service and options["distributed_tracing"] is True
    assert options["advanced"].base_url == "https://logfire-us.pydantic.dev"
    assert options["advanced"].exception_callback is O._private_exception_callback
    assert options["inspect_arguments"] is False and options["add_baggage_to_attributes"] is False
    assert options["console"] is False and options["metrics"] is False
    if role == "sam":
        instrument.assert_not_called()  # SAM has no Pydantic-AI dependency or agents.
    else:
        instrument.assert_called_once_with(include_content=True, include_binary_content=False,
            include_model_request_parameters=True, version=5)


@pytest.mark.parametrize("name,value", [("LOGFIRE_BASE_URL", "https://foreign.invalid"),
    ("OTEL_EXPORTER_OTLP_ENDPOINT", "https://foreign.invalid"),
    ("SPECIMEN_TRACE_EXPORT_MODE", "bounded-v1"), ("APP_ENV", "development")])
def test_unqualified_or_retired_export_configuration_refuses_before_sdk(production, monkeypatch, name, value):
    configure = Mock()
    monkeypatch.setattr(logfire, "configure", configure)
    monkeypatch.setenv(name, value)
    with pytest.raises(O.ObservabilityConfigurationError):
        O.configure_production_observability("specimen-worker")
    configure.assert_not_called()


def test_missing_writer_and_conflicting_embedded_source_refuse_before_sdk(production, monkeypatch):
    configure = Mock()
    monkeypatch.setattr(logfire, "configure", configure)
    monkeypatch.delenv("LOGFIRE_TOKEN")
    with pytest.raises(O.ObservabilityConfigurationError, match="writer_required"):
        O.configure_production_observability("specimen-worker")
    (production / "application").mkdir()
    (production / "application/_build.json").write_text(json.dumps({"source_sha": "b" * 40}))
    with pytest.raises(O.ObservabilityConfigurationError, match="build_provenance_invalid"):
        O.configure_production_observability("specimen-worker")
    configure.assert_not_called()


def test_exception_backstop_removes_body_and_status_description():
    helper = SimpleNamespace(no_record_exception=Mock(), span=SimpleNamespace(set_status=Mock()))
    O._private_exception_callback(helper)
    helper.no_record_exception.assert_called_once_with()
    status = helper.span.set_status.call_args.args[0]
    assert status.description is None


def test_flush_uses_remaining_original_task_deadline(production, monkeypatch):
    from specimen_digitization.application.worker_deadline import WorkerDeadline
    monkeypatch.setattr(O, "_configured_settings", O.ObservabilitySettings.from_environment())
    monkeypatch.setattr(O.time, "monotonic", lambda: 10)
    flush = Mock(return_value=True)
    monkeypatch.setattr(logfire, "force_flush", flush)
    with WorkerDeadline(10.25, monotonic=lambda: 10).scope():
        assert O.flush_production_observability()["complete"]
    flush.assert_called_once_with(timeout_millis=250)
    flush.reset_mock()
    with WorkerDeadline(10.25, monotonic=lambda: 10).scope():
        monkeypatch.setattr(O.time, "monotonic", lambda: 10.30)
        assert not O.flush_production_observability()["complete"]
    flush.assert_not_called()


@pytest.mark.asyncio
async def test_actual_agent_content_spans_keep_text_but_exclude_binary(production, monkeypatch, capfire):
    from pydantic_ai import Agent, BinaryContent
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.messages import ModelResponse, TextPart
    # Keep the installed local CaptureLogfire exporter; replace only export configuration.
    monkeypatch.setattr(logfire, "configure", Mock())
    O.configure_production_observability("specimen-worker")
    def answer(messages, info):
        return ModelResponse(parts=[TextPart("OUTPUT-CANARY")])
    agent = Agent(FunctionModel(answer), system_prompt="SYSTEM-CANARY")
    await agent.run(["INPUT-CANARY", BinaryContent(data=b"BINARY-CANARY", media_type="image/png")])
    spans = json.dumps(capfire.exporter.exported_spans_as_dict())
    assert all(text in spans for text in ("SYSTEM-CANARY", "INPUT-CANARY", "OUTPUT-CANARY"))
    assert "BINARY-CANARY" not in spans and "QklOQVJZLUNBTkFSWQ==" not in spans
    assert "SYNTHETIC-WRITER-CANARY" not in spans


def test_actual_sam_route_carries_parent_and_parameters_without_credential_body(capfire, monkeypatch):
    from fastapi.testclient import TestClient
    from specimen_digitization.application.sam3_server import create_app
    from test_lane_sam_server import run_request, image_bytes
    segmenter = SimpleNamespace(segment=lambda request: {"status": "completed"})
    app = create_app(segmenter, lambda header: None)
    client = TestClient(app)
    with logfire.span("worker parent"):
        carrier = logfire.get_context()
        response = client.post("/v1/segment", json=run_request(image_bytes()),
            headers={**carrier, "authorization": "Bearer PRIVATE-CALLER-CANARY", "baggage": "uid=PRIVATE-USER-CANARY"})
    assert response.status_code == 200
    records = capfire.exporter.exported_spans_as_dict()
    parent = next(item for item in records if item["name"] == "worker parent")
    sam = next(item for item in records if item["name"] == "SAM 3 segmentation")
    assert sam["parent"]["span_id"] == parent["context"]["span_id"]
    assert sam["context"]["trace_id"] == parent["context"]["trace_id"]
    text = json.dumps(records)
    assert "sam3.parameters" in text and "sam3.prompt" in text
    assert "PRIVATE-CALLER-CANARY" not in text and "PRIVATE-USER-CANARY" not in text


def test_actual_api_middleware_never_exports_auth_identity_or_body(capfire):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    O.install_api_trace_spans(app)
    @app.post("/private")
    def endpoint():
        return {"status": "ok"}
    response = TestClient(app).post("/private", json={"email": "PRIVATE-USER-CANARY"},
        headers={"authorization": "Bearer PRIVATE-AUTH-CANARY"})
    assert response.status_code == 200
    records = capfire.exporter.exported_spans_as_dict()
    assert any(item["name"] == "Specimen API request" for item in records)
    assert "PRIVATE-" not in json.dumps(records)
