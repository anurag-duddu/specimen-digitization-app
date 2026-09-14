"""Synthetic export budgeting: no cloud, credentials, or native telemetry."""

import json
import time
from concurrent.futures import ThreadPoolExecutor

import logfire
import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

from specimen_digitization.bounded_telemetry import (
    HEADER_ALLOWANCE,
    BatchPreparer,
    Ledger,
    Limits,
    TraceBudgetError,
    encode_metadata_spans,
)


def ledger_at(tmp_path, **limits):
    return Ledger.create(
        tmp_path / "budget.sqlite3", deadline=time.monotonic() + 60,
        scope="a" * 64, limits=Limits(**limits),
    )


def fixture_spans(capfire):
    with logfire.span(
        "Run isolated specimen model",
        **{"specimen.id": "specimen-001", "specimen.observation.id": "reading-001",
           "specimen.model.operation": "transcribe", "private": "CONTENT-CANARY"},
    ):
        pass
    return capfire.exporter.exported_spans


def test_claim_is_durable_before_dispatch_and_abandonment_never_refunds(
    tmp_path, capfire
):
    ledger = ledger_at(tmp_path)
    calls = []

    def fail(body):
        snapshot = Ledger(ledger.path).snapshot()
        assert snapshot["requests"] == 1
        assert snapshot["records"] == 1
        assert snapshot["request_bytes"] == len(body) + HEADER_ALLOWANCE
        assert snapshot["unknown"] == 1
        calls.append(body)
        raise RuntimeError("PRIVATE-TRANSPORT-ERROR")

    batch = BatchPreparer(ledger).prepare(fixture_spans(capfire))
    assert batch is not None
    assert ledger.authorize_dispatch(batch)
    with pytest.raises(RuntimeError):
        fail(batch.body)
    assert len(calls) == 1
    snapshot = Ledger(ledger.path).snapshot()
    assert snapshot["requests"] == 1 and snapshot["unknown"] == 1
    assert "PRIVATE" not in json.dumps(snapshot)
    with pytest.raises(TraceBudgetError):
        Ledger.create(ledger.path, deadline=time.monotonic() + 60, scope="a" * 64)


@pytest.mark.parametrize("limit", ["records", "requests", "request_bytes"])
def test_exhaustion_blocks_before_transport(tmp_path, capfire, limit):
    spans = fixture_spans(capfire)
    size = len(encode_metadata_spans(spans)) + HEADER_ALLOWANCE
    maximum = size if limit == "request_bytes" else 1
    ledger = ledger_at(tmp_path, **{limit: maximum})
    calls = []
    preparer = BatchPreparer(ledger)
    batch = preparer.prepare(spans)
    assert batch is not None
    assert ledger.authorize_dispatch(batch)
    calls.append(batch.body)
    ledger.finish(batch.attempt, 200)
    assert preparer.prepare(spans) is None
    assert len(calls) == 1
    assert Ledger(ledger.path).snapshot()["requests"] == 1


def test_concurrent_claims_share_one_cap_and_reopen_does_not_reset(tmp_path):
    ledger = ledger_at(tmp_path, requests=7)

    def claim(_):
        return Ledger(ledger.path).reserve(records=1, body=b"synthetic-protobuf")

    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(claim, range(32)))
    assert len([c for c in claims if c is not None]) == 7
    snapshot = Ledger(ledger.path).snapshot()
    assert snapshot["requests"] == snapshot["records"] == snapshot["unknown"] == 7


def test_expired_or_missing_ledger_never_dispatches(tmp_path, capfire):
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(TraceBudgetError):
        Ledger(path).snapshot()
    assert not path.exists()
    ledger = Ledger.create(path, deadline=time.monotonic() - 1, scope="a" * 64)
    calls = []
    assert BatchPreparer(ledger).prepare(fixture_spans(capfire)) is None
    assert not calls


def test_encoder_preserves_lineage_and_safe_ids_but_drops_content_and_events(capfire):
    with logfire.span("Private span name CANARY", private="PRIVATE-CANARY"):
        with logfire.span(
            "Run isolated specimen model",
            **{"specimen.observation.id": "reading-001", "gen_ai.usage.input_tokens": 42,
               "gen_ai.input.messages": "PROMPT-CANARY"},
        ):
            try:
                raise ValueError("ERROR-CANARY")
            except ValueError:
                logfire.exception("LOG-CANARY")
    body = encode_metadata_spans(capfire.exporter.exported_spans)
    assert b"CANARY" not in body
    request = ExportTraceServiceRequest.FromString(body)
    spans = [s for r in request.resource_spans for scope in r.scope_spans for s in scope.spans]
    assert len(spans) == 2
    child = next(s for s in spans if s.name == "Run isolated specimen model")
    parent = next(s for s in spans if s.span_id == child.parent_span_id)
    assert child.trace_id == parent.trace_id
    assert not child.events and not child.links and not child.status.message
    attrs = {a.key: a.value for a in child.attributes}
    assert attrs["specimen.observation.id"].string_value == "reading-001"
    assert attrs["gen_ai.usage.input_tokens"].int_value == 42


@pytest.mark.parametrize("kwargs", [
    {"records": 10001}, {"requests": 501}, {"request_bytes": 64 * 1024**2 + 1},
    {"per_request_bytes": 2 * 1024**2 + 1}, {"records": True},
])
def test_limits_cannot_expand_source_ceiling(kwargs):
    with pytest.raises(TraceBudgetError):
        Limits(**kwargs)


def test_prepared_batch_is_single_use_and_binding_cannot_change(tmp_path, capfire):
    from dataclasses import replace

    ledger = ledger_at(tmp_path)
    batch = BatchPreparer(ledger).prepare(fixture_spans(capfire))
    assert not ledger.authorize_dispatch(replace(batch, body=b"wrong-body"))
    assert ledger.authorize_dispatch(batch)
    assert not Ledger(ledger.path).authorize_dispatch(batch)
    assert Ledger(ledger.path).snapshot()["unknown"] == 1


def test_processor_flushes_once_without_retry_and_never_configures_network(
    tmp_path, capfire
):
    from specimen_digitization.bounded_telemetry import MetadataBatchProcessor

    ledger = ledger_at(tmp_path)
    calls = []

    def record_failure(body, timeout):
        calls.append(body)
        assert Ledger(ledger.path).snapshot()["unknown"] == 1
        assert 0 < timeout <= 1
        raise RuntimeError("PRIVATE-CANARY")

    processor = MetadataBatchProcessor(ledger, record_failure)
    for span in fixture_spans(capfire):
        processor.on_end(span)
    assert not calls
    assert processor.force_flush() is False
    processor.shutdown()
    assert len(calls) == 1
    assert Ledger(ledger.path).snapshot()["requests"] == 1


@pytest.mark.parametrize("acknowledged_at", [109.0, 110.0, 111.0])
def test_flush_success_requires_ledger_acceptance_before_original_deadline(
    tmp_path, monkeypatch, capfire, acknowledged_at
):
    from types import SimpleNamespace

    from specimen_digitization import bounded_telemetry as telemetry

    clock = [100.0]
    monkeypatch.setattr(telemetry, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    ledger = Ledger.create(tmp_path / "budget.sqlite3", deadline=110, scope="a" * 64)
    calls = []

    def acknowledge(body, timeout):
        calls.append(body)
        assert ledger.snapshot()["unknown"] == 1
        clock[0] = acknowledged_at
        return 200

    processor = telemetry.MetadataBatchProcessor(ledger, acknowledge)
    for span in fixture_spans(capfire):
        processor.on_end(span)
    timely = acknowledged_at < 110
    assert processor.force_flush(timeout_millis=10000) is timely
    processor.shutdown()
    assert processor.force_flush() is timely
    assert len(calls) == 1
    retained = Ledger(ledger.path).snapshot()
    assert retained["requests"] == retained["records"] == 1
    assert retained["accepted"] == int(timely)
    assert retained["unknown"] == int(not timely)


@pytest.mark.parametrize("delay", ["writer_contention", "connection_exit"])
def test_finish_rejects_local_completion_after_deadline(tmp_path, monkeypatch, capfire, delay):
    import sqlite3
    import threading
    from contextlib import contextmanager
    from types import SimpleNamespace

    from specimen_digitization import bounded_telemetry as telemetry

    clock = [100.0]
    monkeypatch.setattr(telemetry, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    ledger = Ledger.create(tmp_path / "budget.sqlite3", deadline=110, scope="a" * 64)
    batch = BatchPreparer(ledger).prepare(fixture_spans(capfire))
    assert ledger.authorize_dispatch(batch)
    connect = ledger._connect
    holder = None
    failures = []
    if delay == "writer_contention":
        locked, updating = threading.Event(), threading.Event()

        def hold_writer():
            try:
                with sqlite3.connect(ledger.path, timeout=2) as db:
                    db.execute("BEGIN IMMEDIATE")
                    locked.set()
                    assert updating.wait(2)
                    clock[0] = 111.0
                    db.rollback()
            except BaseException as exc:
                failures.append(type(exc).__name__)

        holder = threading.Thread(target=hold_writer)
        holder.start()
        assert locked.wait(2)

        @contextmanager
        def delayed_connect():
            with connect() as db:
                db.set_trace_callback(
                    lambda sql: updating.set() if sql.startswith("UPDATE attempts") else None
                )
                yield db
    else:
        @contextmanager
        def delayed_connect():
            with connect() as db:
                yield db
            clock[0] = 111.0

    monkeypatch.setattr(ledger, "_connect", delayed_connect)
    try:
        completed = ledger.finish(batch.attempt, 200)
    finally:
        if holder is not None:
            holder.join(timeout=3)
            assert not holder.is_alive()
    assert not failures
    assert clock[0] == 111.0
    assert completed is False
    # The HTTP receipt was known at t=100. Retaining it is distinct from
    # claiming that the local write/finalization completed before t=110.
    retained = Ledger(ledger.path).snapshot()
    assert retained["accepted"] == retained["requests"] == retained["records"] == 1
    assert ledger.finish(batch.attempt, 200) is False
    assert Ledger(ledger.path).snapshot() == retained


def claim_in_child(payload):
    """Importable fixture for the actual fresh-process boundary."""
    from pathlib import Path

    ledger = Ledger(Path(payload["path"]))
    claim = ledger.reserve(records=1, body=b"synthetic-local-claim")
    return json.dumps({"claim": claim, "snapshot": ledger.snapshot()}).encode()


def scoped_worker_fixture(payload):
    from pathlib import Path

    from specimen_digitization.application.bounded_effect import run_isolated
    from specimen_digitization.bounded_telemetry import worker_trace_scope

    with worker_trace_scope() as ledger:
        Path(payload["marker"]).write_text(str(ledger.path))
        if payload.get("stall"):
            time.sleep(30)
        result = run_isolated(claim_in_child, {"path": str(ledger.path)}, 5, 4096)
        assert result.status == "completed" and result.cleanup_complete
        ledger.reserve(records=1, body=b"synthetic-parent-claim")
        return json.dumps(ledger.snapshot()).encode()


@pytest.mark.parametrize("stall", [False, True])
def test_supervisor_owns_shared_ledger_cleanup_even_after_forced_stop(
    tmp_path, monkeypatch, stall
):
    from pathlib import Path

    from specimen_digitization.application.bounded_effect import run_isolated

    monkeypatch.setenv("SPECIMEN_TRACE_EXPORT_MODE", "bounded-v1")
    monkeypatch.setenv("SPECIMEN_TRACE_SCOPE_SHA256", "a" * 64)
    marker = tmp_path / "workspace.txt"
    result = run_isolated(
        scoped_worker_fixture, {"marker": str(marker), "stall": stall},
        8, 4096, process_group=True,
    )
    assert result.cleanup_complete
    ledger_path = Path(marker.read_text())
    assert not ledger_path.parent.exists()
    if stall:
        assert result.status != "completed"
    else:
        assert result.status == "completed"
        assert json.loads(result.value)["requests"] == 2


def test_bounded_mode_never_falls_back_to_default_native_configuration(monkeypatch):
    from specimen_digitization import observability

    calls = []
    monkeypatch.setenv("SPECIMEN_TRACE_EXPORT_MODE", "bounded-v1")
    monkeypatch.setattr(logfire, "configure", lambda **kwargs: calls.append(kwargs))
    with pytest.raises(observability.ObservabilityConfigurationError,
                       match="bounded_trace_transport_approval_required"):
        observability.configure_observability()
    assert not calls


def test_per_request_limit_and_corruption_fail_closed_without_reset(tmp_path, capfire):
    ledger = ledger_at(tmp_path, per_request_bytes=HEADER_ALLOWANCE)
    assert BatchPreparer(ledger).prepare(fixture_spans(capfire)) is None
    assert ledger.snapshot()["requests"] == 0
    ledger.path.write_bytes(b"corrupt-local-ledger")
    assert ledger.reserve(records=1, body=b"fixture") is None
    with pytest.raises(TraceBudgetError):
        ledger.snapshot()
    assert ledger.path.read_bytes() == b"corrupt-local-ledger"


def test_ledger_deadline_only_tightens(tmp_path):
    ledger = ledger_at(tmp_path)
    ledger.tighten(time.monotonic() - 1)
    ledger.tighten(time.monotonic() + 3600)
    assert ledger.remaining() < 0
    assert ledger.reserve(records=1, body=b"fixture") is None


def test_supported_sdk_options_disable_ambient_native_exporters_and_credentials(
    tmp_path, monkeypatch
):
    import http.client
    import requests

    from specimen_digitization.bounded_telemetry import (
        MetadataBatchProcessor, bounded_sdk_options,
    )

    for name, value in {
        "LOGFIRE_SEND_TO_LOGFIRE": "true",
        "LOGFIRE_TOKEN": "PRIVATE-TOKEN-CANARY",
        "LOGFIRE_API_KEY": "PRIVATE-API-CANARY",  # pragma: allowlist secret - synthetic test marker
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://synthetic-invalid.example.test",
        "OTEL_TRACES_EXPORTER": "otlp", "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_LOGS_EXPORTER": "otlp",
    }.items():
        monkeypatch.setenv(name, value)
    network = []

    def forbidden(*args, **kwargs):
        network.append(True)
        raise AssertionError("No native network allowed in this local test")

    monkeypatch.setattr(requests.Session, "request", forbidden)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", forbidden)
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", forbidden)
    ledger = ledger_at(tmp_path)
    batches = []
    processor = MetadataBatchProcessor(
        ledger, lambda body, timeout: batches.append(body) or 200,
    )
    options = bounded_sdk_options(processor)
    assert options["send_to_logfire"] is False
    assert "CANARY" not in options["token"] + options["api_key"]
    logfire.configure(**options, inspect_arguments=False)
    with logfire.span("Run isolated specimen model", private="CONTENT-CANARY"):
        logfire.info("LOG-CANARY")
    logfire.shutdown(timeout_millis=1000)
    assert not network
    assert len(batches) == 1
    assert b"CANARY" not in batches[0]
    snapshot = ledger.snapshot()
    assert snapshot["records"] == snapshot["requests"] == snapshot["accepted"] == 1


@pytest.mark.parametrize("prompt_name", [
    "literal-label-transcription", "structured-field-extraction",
    "transcription-disagreement-adjudication",
])
def test_bounded_prompt_resolution_uses_code_fallback_without_remote_provider(
    tmp_path, monkeypatch, capfire, prompt_name
):
    import http.client
    import requests
    from logfire.variables.remote import LogfireRemoteVariableProvider

    from specimen_digitization import prompts
    from specimen_digitization.bounded_telemetry import (
        MetadataBatchProcessor, bounded_sdk_options,
    )

    class RemoteProviderForbidden(BaseException):
        pass

    starts, network, batches = [], [], []

    def forbid_provider(*args, **kwargs):
        starts.append(True)
        raise RemoteProviderForbidden

    def forbid_network(*args, **kwargs):
        network.append(True)
        raise AssertionError("Native I/O is forbidden in this local regression")

    monkeypatch.setattr(LogfireRemoteVariableProvider, "start", forbid_provider)
    monkeypatch.setattr(requests.Session, "request", forbid_network)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", forbid_network)
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", forbid_network)
    for key in ("LOGFIRE_TOKEN", "LOGFIRE_API_KEY"):
        monkeypatch.setenv(key, "synthetic-not-a-credential")
    ledger = ledger_at(tmp_path)
    processor = MetadataBatchProcessor(
        ledger, lambda body, timeout: batches.append(body) or 200,
    )
    logfire.configure(**bounded_sdk_options(processor), inspect_arguments=False)
    resolved = None
    try:
        try:
            resolved = prompts.resolve_prompt(
                prompts.PromptName(prompt_name),
                prompts.CollectionPromptInputs(
                    collection_profile_id="synthetic-profile",
                    collection_name="Synthetic collection",
                    schema_version="synthetic-v1",
                ),
            )
        except RemoteProviderForbidden:
            pass
    finally:
        logfire.shutdown(timeout_millis=1000)
    assert not starts and not network
    assert resolved is not None
    defaults = {
        "literal-label-transcription": prompts._LITERAL_TRANSCRIPTION_DEFAULT,
        "structured-field-extraction": prompts._STRUCTURED_EXTRACTION_DEFAULT,
        "transcription-disagreement-adjudication": prompts._DISAGREEMENT_ADJUDICATION_DEFAULT,
    }
    expected = defaults[prompt_name]
    for key, value in {
        "collection_profile_id": "synthetic-profile",
        "collection_name": "Synthetic collection",
        "schema_version": "synthetic-v1",
    }.items():
        expected = expected.replace("{{" + key + "}}", value)
    assert resolved.text == expected
    assert resolved.version is None
    assert resolved.text.encode() not in b"".join(batches)
