"""The drain's end-of-run trace flush against a slow exporter. No network.

flush_production_observability(shutdown=True) is the worker's last act
(application/worker.py, _run_drain). It returns complete=False, and the drain exits 2
(drain_trace_export_incomplete), when the whole shutdown took longer than its bound.
The SDK's batch processor ignores the flush timeout (opentelemetry-python issue 4568),
so the bound is a completion check on elapsed time, not an interruption. The exporter
here is a stand-in that sleeps; the processors, logfire.shutdown and _run_drain are the
production code.
"""
import time
from types import SimpleNamespace
from unittest.mock import Mock

import logfire
import pytest
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

from specimen_digitization import observability as O
from specimen_digitization.application import worker
from specimen_digitization.application.worker_deadline import WorkerDeadline
from specimen_digitization.application.workflow import OperationalBlock


class SlowExporter(SpanExporter):
    def __init__(self, seconds):
        self.seconds, self.exported = seconds, []

    def export(self, spans):
        time.sleep(self.seconds)
        self.exported.extend(span.name for span in spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True


def settings():
    return O.ObservabilitySettings(environment="production", service_name="specimen-worker",
        capture_mode=O.CaptureMode.APPROVED_CONTENT, head_sample_rate=1.0, distributed_tracing=True)


@pytest.fixture
def slow_exporter(monkeypatch):
    """Real logfire with a batch processor whose only export is the final flush's."""
    def install(seconds):
        exporter = SlowExporter(seconds)
        # A schedule delay far beyond the test: the tail is exported only by the final flush.
        logfire.configure(send_to_logfire=False, console=False, additional_span_processors=[
            BatchSpanProcessor(exporter, schedule_delay_millis=600_000)])
        monkeypatch.setattr(O, "_configured_settings", settings())
        return exporter
    yield install
    logfire.configure(send_to_logfire=False, console=False)


def run_drain(monkeypatch):
    def execute(args, deadline):
        with logfire.span("the last specimen's spans"):
            pass
    monkeypatch.setattr(worker, "_execute_drain", execute)
    worker._run_drain(SimpleNamespace(max_seconds=601, check_config=False))


def test_a_normal_tail_slower_than_one_second_does_not_fail_the_drain(slow_exporter, monkeypatch):
    # A full specimen's last batch is about 350 KB on the wire (gzip) behind a fresh TLS
    # connection; one second is not a safe bound for that, and the exporter is healthy.
    exporter = slow_exporter(1.3)
    started = time.monotonic()
    run_drain(monkeypatch)
    assert time.monotonic() - started >= 1.3
    assert exporter.exported == ["the last specimen's spans"]


def test_a_stuck_exporter_still_ends_the_drain_with_exit_2_and_the_named_reason(slow_exporter, monkeypatch, capsys):
    # The bound is smaller than the exporter's stall: the flush must not report success.
    monkeypatch.setattr(O, "FINAL_FLUSH_MILLIS", 300, raising=False)
    slow_exporter(1.3)
    with pytest.raises(OperationalBlock, match="^drain_trace_export_incomplete$"):
        run_drain(monkeypatch)


def test_an_explicit_bound_shorter_than_the_export_is_incomplete(slow_exporter):
    exporter = slow_exporter(1.0)
    with logfire.span("a tail"):
        pass
    assert O.flush_production_observability(shutdown=True, maximum_millis=300) == {
        "configured": True, "complete": False}
    assert exporter.exported == ["a tail"]


def test_the_drain_flushes_with_the_final_bound_and_every_other_caller_keeps_one_second(monkeypatch):
    assert O.FLUSH_MILLIS == 1_000
    assert 5_000 <= O.FINAL_FLUSH_MILLIS <= O.FLUSH_CEILING_MILLIS <= 60_000
    monkeypatch.setattr(O, "_configured_settings", settings())
    shutdown, force_flush = Mock(return_value=True), Mock(return_value=True)
    monkeypatch.setattr(logfire, "shutdown", shutdown)
    monkeypatch.setattr(logfire, "force_flush", force_flush)
    # The API's and the pilot CLI's shutdown, and the SAM server's per-request flush: unchanged.
    assert O.flush_production_observability(shutdown=True)["complete"]
    shutdown.assert_called_once_with(timeout_millis=1000)
    assert O.flush_production_observability()["complete"]
    force_flush.assert_called_once_with(timeout_millis=1000)
    shutdown.reset_mock()
    # The drain's last act.
    monkeypatch.setattr(worker, "_execute_drain", lambda args, deadline: None)
    worker._run_drain(SimpleNamespace(max_seconds=601, check_config=False))
    shutdown.assert_called_once_with(timeout_millis=O.FINAL_FLUSH_MILLIS)


def test_the_final_flush_still_cannot_outlive_the_task_deadline(monkeypatch):
    monkeypatch.setattr(O, "_configured_settings", settings())
    monkeypatch.setattr(O.time, "monotonic", lambda: 10)
    shutdown = Mock(return_value=True)
    monkeypatch.setattr(logfire, "shutdown", shutdown)
    with WorkerDeadline(10.25, monotonic=lambda: 10).scope():
        assert O.flush_production_observability(shutdown=True, maximum_millis=O.FINAL_FLUSH_MILLIS)["complete"]
    shutdown.assert_called_once_with(timeout_millis=250)
    # Past the deadline nothing is flushed and the verdict is incomplete.
    shutdown.reset_mock()
    with WorkerDeadline(10.25, monotonic=lambda: 10).scope():
        monkeypatch.setattr(O.time, "monotonic", lambda: 10.30)
        assert not O.flush_production_observability(shutdown=True, maximum_millis=O.FINAL_FLUSH_MILLIS)["complete"]
    shutdown.assert_not_called()


@pytest.mark.parametrize("bound", [0, -1, True, 1.5, "1000", None, 30_001, 10**9])
def test_a_bound_outside_the_ceiling_is_refused(monkeypatch, bound):
    monkeypatch.setattr(O, "_configured_settings", settings())
    shutdown = Mock(return_value=True)
    monkeypatch.setattr(logfire, "shutdown", shutdown)
    with pytest.raises(O.ObservabilityConfigurationError, match="^production_trace_flush_bound_invalid$"):
        O.flush_production_observability(shutdown=True, maximum_millis=bound)
    shutdown.assert_not_called()


def test_an_explicit_bound_up_to_the_ceiling_is_accepted(monkeypatch):
    monkeypatch.setattr(O, "_configured_settings", settings())
    shutdown = Mock(return_value=True)
    monkeypatch.setattr(logfire, "shutdown", shutdown)
    assert O.flush_production_observability(shutdown=True, maximum_millis=5_000)["complete"]
    shutdown.assert_called_once_with(timeout_millis=5_000)
