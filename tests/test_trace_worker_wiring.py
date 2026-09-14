"""Synthetic deadline, child IPC and final drain checks; no external services."""

from contextlib import contextmanager
import json
import os
import time
from types import SimpleNamespace

import pytest

from specimen_digitization import bounded_telemetry as telemetry
from specimen_digitization.application import bounded_effect, worker
from specimen_digitization.application.worker_deadline import (
    WorkerDeadline, WorkerDeadlineExceeded,
)
from trace_worker_fixtures import child_deadline_and_flush, generic_child_without_tracing


@pytest.mark.parametrize("loaded", [False, True])
def test_generic_child_does_not_require_or_touch_tracing(tmp_path, monkeypatch, loaded):
    monkeypatch.setenv("SPECIMEN_TRACE_EXPORT_MODE", "bounded-v1")
    monkeypatch.setenv("SPECIMEN_TRACE_SCOPE_SHA256", "a" * 64)
    with WorkerDeadline(time.monotonic() + 20, workspace=tmp_path).scope():
        with telemetry.worker_trace_scope() as ledger:
            result = bounded_effect.run_isolated(generic_child_without_tracing, {
                "loaded": loaded, "unexpected": str(tmp_path / "unexpected"),
            }, 5, 1024)
            assert result.status == "completed" and result.value == b"known generic response"
            assert result.trace_export is None
            assert not (tmp_path / "unexpected").exists()
            assert ledger.snapshot()["completion"] is True
            assert ledger.snapshot()["requests"] == 0


def test_required_model_missing_trace_configuration_is_incomplete(tmp_path, monkeypatch):
    monkeypatch.setenv("SPECIMEN_TRACE_EXPORT_MODE", "bounded-v1")
    monkeypatch.setenv("SPECIMEN_TRACE_SCOPE_SHA256", "a" * 64)
    with WorkerDeadline(time.monotonic() + 20, workspace=tmp_path).scope():
        with telemetry.worker_trace_scope() as ledger:
            result = bounded_effect.run_isolated(generic_child_without_tracing, {
                "unexpected": str(tmp_path / "unexpected"),
            }, 5, 1024, trace_required=True)
            assert result.status == "completed" and result.value == b"known generic response"
            assert result.trace_export == {"configured": False, "complete": False}
            assert ledger.snapshot()["completion"] is False
            assert not (tmp_path / "unexpected").exists()


@pytest.mark.parametrize("requirement", [None, 1, "true", {}, []])
def test_trace_requirement_must_be_an_explicit_boolean(requirement):
    with pytest.raises(ValueError, match="trace_required"):
        bounded_effect.run_isolated(
            generic_child_without_tracing, {}, 1, 1024, trace_required=requirement,
        )


def test_worker_group_cannot_select_model_child_trace_requirement():
    with pytest.raises(ValueError, match="trace_required"):
        bounded_effect.run_isolated(
            generic_child_without_tracing, {}, 1, 1024,
            trace_required=True, process_group=True,
        )


def test_model_runtime_requires_child_trace_completion(monkeypatch):
    from specimen_digitization.application import model_runtime
    from specimen_digitization.application.workflow import OperationalBlock

    calls = []
    def isolated(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status="completed", cleanup_complete=True,
                               value=b'{"status":"blocked","code":"synthetic_block"}')

    monkeypatch.setattr(model_runtime, "run_isolated", isolated)
    monkeypatch.setattr(model_runtime, "storage_descriptor", lambda blobs: {})
    profile = SimpleNamespace(model_dump=lambda **kwargs: {}, execution=SimpleNamespace(
        effect_timeout_for_step=lambda step: 1,
    ))
    specimen = SimpleNamespace(id="synthetic-specimen", asset=SimpleNamespace(
        model_dump=lambda **kwargs: {},
    ), run=SimpleNamespace(id="synthetic-run", profile=profile, dependencies={},
                           transcripts=[], fields={}))
    with pytest.raises(OperationalBlock, match="synthetic_block"):
        model_runtime.invoke_model(SimpleNamespace(blobs=None, model_effect=None), specimen, "extract")
    assert calls == [{"max_input_bytes": 4 * 1024 * 1024, "trace_required": True}]


def test_classifier_runtime_requires_child_trace_completion(tmp_path, monkeypatch):
    from specimen_digitization.application.classifier_runtime import ConfiguredClassifier
    from specimen_digitization.application.hf_collection_classifier import HFClassifierConfig
    from specimen_digitization.application.storage import LocalBlobs
    from specimen_digitization.application.workflow import OperationalBlock

    calls = []
    def isolated(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status="worker_failed", cleanup_complete=True)

    monkeypatch.setattr(bounded_effect, "run_isolated", isolated)
    config = HFClassifierConfig(
        route_id="synthetic-classifier", expected_model_id="fixture/classifier",
        expected_provider="novita", prompt_text="Synthetic prompt", prompt_version="1",
        approved=True, total_deadline_seconds=5,
    )
    facade = ConfiguredClassifier(LocalBlobs(tmp_path / "blobs"), config)
    run = SimpleNamespace(profile=SimpleNamespace(execution=SimpleNamespace(
        external_timeout_seconds=5,
    )), dependencies={})
    run.dependencies["classifier"] = facade.pin(run)
    specimen = SimpleNamespace(run=run, asset=SimpleNamespace(model_dump=lambda **kwargs: {}))
    classifier = facade.bind(specimen, SimpleNamespace(nodes=[]))
    with pytest.raises(OperationalBlock, match="external_outcome_unknown"):
        classifier.classify(SimpleNamespace(model_dump=lambda **kwargs: {}))
    assert calls == [{"trace_required": True}]


@pytest.mark.parametrize("complete,raises", [(True, False), (False, False), (False, True)])
def test_child_retains_known_output_and_separate_trace_completion(
    tmp_path, monkeypatch, complete, raises,
):
    ledger = telemetry.Ledger.create(
        tmp_path / "budget.sqlite3", deadline=time.monotonic() + 30, scope="a" * 64,
    )
    monkeypatch.setenv("SPECIMEN_TRACE_EXPORT_MODE", "bounded-v1")
    monkeypatch.setenv("SPECIMEN_TRACE_LEDGER_PATH", str(ledger.path))
    original_remaining = ledger.remaining()
    started = time.monotonic()
    result = bounded_effect.run_isolated(child_deadline_and_flush, {
        "deadline": str(tmp_path / "deadline"), "flush": str(tmp_path / "flush"),
        "complete": complete, "raise": raises,
    }, 5, 1024, trace_required=True)
    assert result.status == "completed" and result.value == b"known model output"
    assert result.trace_export == {"configured": True, "complete": complete}
    assert (tmp_path / "flush").read_text() == "once"
    assert started < float((tmp_path / "deadline").read_text()) <= started + 5.05
    assert ledger.remaining() > original_remaining - 5
    assert ledger.snapshot()["completion"] is complete
    assert ledger.snapshot()["requests"] == 0
    assert "CANARY" not in json.dumps(result.trace_export)


def test_stalled_child_flush_is_stopped_by_original_effect_clock(tmp_path, monkeypatch):
    monkeypatch.setenv("SPECIMEN_TRACE_EXPORT_MODE", "bounded-v1")
    result = bounded_effect.run_isolated(child_deadline_and_flush, {
        "deadline": str(tmp_path / "deadline"), "flush": str(tmp_path / "flush"),
        "complete": True, "stall": True,
    }, 0.8, 1024, trace_required=True)
    assert (tmp_path / "flush").exists()
    assert result.status == "deadline_exceeded" and result.value is None
    assert result.trace_export is None
    assert result.cleanup_complete and result.elapsed_seconds < 3


def test_worker_reductions_tighten_shared_ledger_and_failure_blocks_work(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("SPECIMEN_TRACE_EXPORT_MODE", "bounded-v1")
    monkeypatch.setenv("SPECIMEN_TRACE_SCOPE_SHA256", "a" * 64)
    owner = WorkerDeadline(time.monotonic() + 60, workspace=tmp_path)
    with owner.scope(), telemetry.worker_trace_scope() as ledger:
        owner.tighten_until(30, 10)
        assert 19 < ledger.remaining() <= 20
        owner.tighten_until(15, 10)
        assert 4 < ledger.remaining() <= 5
        ledger.path.write_bytes(b"corrupt")
        with pytest.raises(WorkerDeadlineExceeded):
            owner.tighten_until(12, 10)
        with pytest.raises(WorkerDeadlineExceeded):
            owner.check()


def test_incomplete_trace_completion_is_sticky(tmp_path):
    ledger = telemetry.Ledger.create(
        tmp_path / "budget.sqlite3", deadline=time.monotonic() + 20, scope="a" * 64,
    )
    assert ledger.snapshot()["completion"] is True
    ledger.record_completion(False)
    telemetry.Ledger(ledger.path).record_completion(True)
    assert ledger.snapshot()["completion"] is False


def test_failed_supervisor_deadline_publication_also_blocks_further_work():
    def fail(deadline):
        raise OSError("synthetic deadline publication failure")

    owner = WorkerDeadline(time.monotonic() + 20, publish=fail)
    with pytest.raises(WorkerDeadlineExceeded):
        owner.tighten_until(12, 10)
    with pytest.raises(WorkerDeadlineExceeded):
        owner.check()


def test_parent_retains_child_flush_failure_when_child_receipt_write_fails(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("SPECIMEN_TRACE_EXPORT_MODE", "bounded-v1")
    monkeypatch.setenv("SPECIMEN_TRACE_SCOPE_SHA256", "a" * 64)
    with WorkerDeadline(time.monotonic() + 20, workspace=tmp_path).scope():
        with telemetry.worker_trace_scope() as ledger:
            result = bounded_effect.run_isolated(child_deadline_and_flush, {
                "deadline": str(tmp_path / "deadline"), "flush": str(tmp_path / "flush"),
                "complete": True, "record_failure": True,
            }, 5, 1024, trace_required=True)
            assert result.status == "completed" and result.value == b"known model output"
            assert result.trace_export == {"configured": True, "complete": False}
            with ledger._connect() as db:
                config, _ = ledger._config(db)
                assert config["completion"] is True
            assert ledger.snapshot()["completion"] is False


@pytest.mark.parametrize("pending", [False, True])
def test_processor_checks_original_flush_bound_after_completion(
    tmp_path, monkeypatch, capfire, pending,
):
    from test_bounded_telemetry import fixture_spans

    clock = [100.0]
    monkeypatch.setattr(telemetry, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    ledger = telemetry.Ledger.create(tmp_path / "budget.sqlite3", deadline=110, scope="a" * 64)

    def dispatch(body, timeout):
        clock[0] = 102.0
        return 200

    processor = telemetry.MetadataBatchProcessor(ledger, dispatch)
    if pending:
        for span in fixture_spans(capfire):
            processor.on_end(span)
    else:
        clock[0] = 110.0
    assert processor.force_flush(timeout_millis=1000) is False
    assert processor.shutdown() is False


@pytest.mark.parametrize("child_complete,flush_complete", [(True, True), (False, True), (True, False)])
def test_worker_flushes_before_snapshot_and_reports_completion_separately(
    tmp_path, monkeypatch, child_complete, flush_complete,
):
    from specimen_digitization import observability

    monkeypatch.setenv("SPECIMEN_TRACE_EXPORT_MODE", "bounded-v1")
    monkeypatch.setenv("SPECIMEN_TRACE_SCOPE_SHA256", "a" * 64)
    events = []

    @contextmanager
    def materialize(args):
        yield args

    def run(args):
        events.append("run")
        telemetry.Ledger(os.environ["SPECIMEN_TRACE_LEDGER_PATH"]).record_completion(child_complete)
        print(json.dumps({"status": "completed"}))

    def flush():
        events.append("flush")
        return {"configured": True, "complete": flush_complete}

    original_snapshot = telemetry.Ledger.snapshot

    def snapshot(ledger):
        events.append("snapshot")
        return original_snapshot(ledger)

    monkeypatch.setattr(worker, "materialized_worker_args", materialize)
    monkeypatch.setattr(worker, "_run", run)
    monkeypatch.setattr(observability, "flush_bounded_observability", flush, raising=False)
    monkeypatch.setattr(telemetry.Ledger, "snapshot", snapshot)
    with WorkerDeadline(time.monotonic() + 20, workspace=tmp_path).scope():
        report = json.loads(worker._production_operation({"mode": "production"}))
    assert events == ["run", "flush", "snapshot"]
    assert report["trace_export"]["complete"] is (child_complete and flush_complete)
    assert report["trace_export"]["accepted"] == 0
    assert report["exit_code"] == (0 if child_complete and flush_complete else 2)
    assert json.loads(report["output"])["status"] == "completed"
