"""Local metadata batch preparation and durable accounting; no network transport."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote

import logfire
from logfire.variables.config import VariablesConfig
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk.trace import SpanProcessor

HEADER_ALLOWANCE = 8192
_worker_completion = ContextVar("worker_trace_completion", default=None)


def record_child_completion(report):
    """Keep a child reporting failure sticky even if its SQLite write failed."""
    retained = _worker_completion.get()
    if retained is not None:
        retained["complete"] = retained["complete"] and (
            type(report) is dict and report.get("configured") is True
            and report.get("complete") is True
        )


class TraceBudgetError(RuntimeError):
    """Fixed, content-free configuration or accounting failure."""


@dataclass(frozen=True)
class Limits:
    records: int = 10_000
    requests: int = 500
    request_bytes: int = 64 * 1024**2
    per_request_bytes: int = 2 * 1024**2

    def __post_init__(self):
        for key, ceiling in (
            ("records", 10_000), ("requests", 500),
            ("request_bytes", 64 * 1024**2), ("per_request_bytes", 2 * 1024**2),
        ):
            value = getattr(self, key)
            if type(value) is not int or not 0 < value <= ceiling:
                raise TraceBudgetError("invalid_trace_limits")


class Ledger:
    """Private SQLite claims survive child loss; they are never refunded."""

    def __init__(self, path):
        self.path = Path(path)

    @classmethod
    def create(cls, path, *, deadline, scope, limits=Limits()):
        if not math.isfinite(deadline) or not re.fullmatch(r"[0-9a-f]{64}", scope):
            raise TraceBudgetError("invalid_trace_scope")
        ledger = cls(path)
        try:
            fd = os.open(ledger.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            with ledger._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("CREATE TABLE config (payload TEXT NOT NULL)")
                db.execute(
                    "INSERT INTO config VALUES (?)",
                    (json.dumps({"deadline": deadline, "scope": scope, "completion": True,
                                 "limits": asdict(limits)}),),
                )
                db.execute(
                    "CREATE TABLE attempts (id INTEGER PRIMARY KEY, records INTEGER NOT NULL, "
                    "request_bytes INTEGER NOT NULL, body_sha256 TEXT NOT NULL, "
                    "state TEXT NOT NULL, http_status INTEGER)"
                )
                db.commit()
            parent_fd = os.open(ledger.path.parent, os.O_RDONLY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except (OSError, sqlite3.Error):
            raise TraceBudgetError("trace_ledger_creation_failed") from None
        return ledger

    @contextmanager
    def _connect(self):
        db = None
        try:
            info = self.path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600):
                raise TraceBudgetError("unsafe_trace_ledger")
            db = sqlite3.connect(
                "file:" + quote(str(self.path), safe="/") + "?mode=rw",
                uri=True, timeout=2, isolation_level=None,
            )
            db.execute("PRAGMA synchronous=FULL")
            yield db
        except (OSError, sqlite3.Error):
            raise TraceBudgetError("trace_ledger_unavailable") from None
        finally:
            if db is not None:
                db.close()

    @staticmethod
    def _config(db):
        try:
            rows = db.execute("SELECT payload FROM config").fetchall()
            if len(rows) != 1:
                raise ValueError
            config = json.loads(rows[0][0])
            limits = Limits(**config["limits"])
            if (not math.isfinite(config["deadline"])
                    or type(config["completion"]) is not bool
                    or not re.fullmatch(r"[0-9a-f]{64}", config["scope"])):
                raise ValueError
            return config, limits
        except (ValueError, TypeError, KeyError):
            raise TraceBudgetError("invalid_trace_ledger") from None

    @staticmethod
    def _counts(db):
        row = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(records),0), COALESCE(SUM(request_bytes),0), "
            "COALESCE(SUM(state='accepted'),0), COALESCE(SUM(state='rejected'),0), "
            "COALESCE(SUM(state IN ('reserved','dispatched')),0) FROM attempts"
        ).fetchone()
        if any(type(value) is not int or value < 0 for value in row):
            raise TraceBudgetError("invalid_trace_ledger")
        if row[0] != sum(row[3:]):
            raise TraceBudgetError("invalid_trace_ledger")
        return dict(zip(
            ("requests", "records", "request_bytes", "accepted", "rejected", "unknown"), row
        ))

    def snapshot(self):
        with self._connect() as db:
            config, limits = self._config(db)
            result = self._counts(db)
            if any(result[key] > getattr(limits, key)
                   for key in ("requests", "records", "request_bytes")):
                raise TraceBudgetError("invalid_trace_ledger")
            retained = _worker_completion.get()
            complete = config["completion"]
            if retained is not None and retained["path"] == self.path:
                complete = complete and retained["complete"]
            return dict(result, scope=config["scope"], limits=asdict(limits),
                        completion=complete)

    def record_completion(self, complete):
        """Retain incomplete process drains independently of HTTP receipts."""
        if type(complete) is not bool:
            raise TraceBudgetError("invalid_trace_completion")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            config, _ = self._config(db)
            if time.monotonic() >= config["deadline"]:
                raise TraceBudgetError("trace_completion_expired")
            config["completion"] = config["completion"] and complete
            db.execute("UPDATE config SET payload=?", (json.dumps(config),))
            db.commit()
        if time.monotonic() >= config["deadline"]:
            raise TraceBudgetError("trace_completion_expired")

    def remaining(self):
        with self._connect() as db:
            config, _ = self._config(db)
            return config["deadline"] - time.monotonic()

    def tighten(self, deadline):
        if not math.isfinite(deadline):
            raise TraceBudgetError("invalid_trace_deadline")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            config, _ = self._config(db)
            config["deadline"] = min(config["deadline"], deadline)
            db.execute("UPDATE config SET payload=?", (json.dumps(config),))
            db.commit()

    def reserve(self, *, records, body):
        if type(records) is not int or records <= 0 or type(body) is not bytes:
            return None
        size = len(body) + HEADER_ALLOWANCE
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                config, limits = self._config(db)
                used = self._counts(db)
                if (time.monotonic() >= config["deadline"]
                        or size > limits.per_request_bytes
                        or used["requests"] + 1 > limits.requests
                        or used["records"] + records > limits.records
                        or used["request_bytes"] + size > limits.request_bytes):
                    db.rollback()
                    return None
                result = db.execute(
                    "INSERT INTO attempts(records,request_bytes,body_sha256,state) "
                    "VALUES (?,?,?,'reserved')",
                    (records, size, hashlib.sha256(body).hexdigest()),
                )
                db.commit()
                return result.lastrowid
        except TraceBudgetError:
            return None

    def finish(self, attempt, status):
        """Retain a timely HTTP receipt; require timely local completion for success."""
        if type(status) is not int or not 100 <= status <= 599:
            return False
        with self._connect() as db:
            config, _ = self._config(db)
            if time.monotonic() >= config["deadline"]:
                return False
            result = db.execute(
                "UPDATE attempts SET state=?,http_status=? WHERE id=? AND state='dispatched'",
                ("accepted" if 200 <= status < 300 else "rejected", status, attempt),
            )
            accepted = result.rowcount == 1 and 200 <= status < 300
        # UPDATE/commit or connection finalization can block after the receipt
        # was checked. Its stored status does not prove an in-bound completion.
        return accepted and time.monotonic() < config["deadline"]

    def authorize_dispatch(self, batch):
        """Atomically consume one prepared claim; never dispatch it twice."""
        try:
            request = ExportTraceServiceRequest.FromString(batch.body)
            records = sum(
                len(s.spans) for r in request.resource_spans for s in r.scope_spans
            )
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                config, _ = self._config(db)
                if time.monotonic() >= config["deadline"]:
                    return False
                result = db.execute(
                    "UPDATE attempts SET state='dispatched' WHERE id=? AND state='reserved' "
                    "AND records=? AND request_bytes=? AND body_sha256=?",
                    (batch.attempt, records, len(batch.body) + HEADER_ALLOWANCE,
                     hashlib.sha256(batch.body).hexdigest()),
                )
                db.commit()
                return result.rowcount == 1
        except Exception:
            return False


_ID_ATTRIBUTES = frozenset({
    "specimen.id", "specimen.run.id", "specimen.region.id", "specimen.route.id",
    "specimen.observation.id", "specimen_id", "collection_id",
    "gen_ai.request.model", "gen_ai.provider.name",
    "gen_ai.system", "gen_ai.operation.name",
})
_NUMBER_ATTRIBUTES = frozenset({
    "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
    "gen_ai.usage.cache_read.input_tokens", "gen_ai.usage.cache_creation.input_tokens",
})
_RESOURCE_ATTRIBUTES = frozenset({
    "service.name", "service.version", "deployment.environment.name",
    "specimen.telemetry.capture_mode",
})


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,256}", value)


def encode_metadata_spans(spans):
    """Encode completed span structure and explicitly allowlisted metadata only."""
    clean = ExportTraceServiceRequest()
    for span in spans:
        attributes = dict(span.attributes or {})
        if attributes.get("logfire.span_type", "span") != "span":
            continue
        context = span.context
        if context is None or not context.is_valid or span.end_time is None:
            continue
        resource = clean.resource_spans.add()
        for key in _RESOURCE_ATTRIBUTES:
            value = span.resource.attributes.get(key)
            if _identifier(value):
                resource.resource.attributes.add(key=key).value.string_value = value
        scope = resource.scope_spans.add()
        scope.scope.name = "specimen.bounded.telemetry"
        output = scope.spans.add()
        output.trace_id = context.trace_id.to_bytes(16, "big")
        output.span_id = context.span_id.to_bytes(8, "big")
        if span.parent is not None and span.parent.is_valid:
            output.parent_span_id = span.parent.span_id.to_bytes(8, "big")
        output.flags = int(context.trace_flags)
        output.kind = span.kind.value + 1
        output.start_time_unix_nano = span.start_time
        output.end_time_unix_nano = span.end_time
        output.name = (
            span.name if span.name in {
                "Process specimen checkpoint", "Run isolated specimen model"
            } else "Invoke specimen agent" if span.name.startswith("invoke_agent ")
            else "Call specimen model" if span.name.startswith("chat ")
            else "Specimen processing span"
        )
        output.status.code = span.status.status_code.value
        for key in _ID_ATTRIBUTES:
            value = attributes.get(key)
            if _identifier(value):
                output.attributes.add(key=key).value.string_value = value
        for key in _NUMBER_ATTRIBUTES:
            value = attributes.get(key)
            if type(value) is int and 0 <= value <= 10**12:
                output.attributes.add(key=key).value.int_value = value
        for key, allowed in (
            ("specimen.model.operation", {"classify", "transcribe", "extract"}),
            ("specimen.model.outcome", {"completed", "adapter_failure", "blocked", "failed"}),
        ):
            value = attributes.get(key)
            if isinstance(value, str) and value in allowed:
                output.attributes.add(key=key).value.string_value = value
        for key, value in (("logfire.span_type", "span"), ("logfire.msg", output.name)):
            attr = output.attributes.add(key=key)
            attr.value.string_value = value
    return clean.SerializeToString()


@dataclass(frozen=True)
class PreparedBatch:
    body: bytes
    attempt: int


class BatchPreparer:
    """Reserve a metadata batch locally; transport is deliberately absent."""

    def __init__(self, ledger):
        self.ledger = ledger

    def prepare(self, spans):
        body = encode_metadata_spans(spans)
        request = ExportTraceServiceRequest.FromString(body)
        records = sum(len(s.spans) for r in request.resource_spans for s in r.scope_spans)
        if not records:
            return None
        attempt = self.ledger.reserve(records=records, body=body)
        return None if attempt is None else PreparedBatch(body=body, attempt=attempt)


class MetadataBatchProcessor(SpanProcessor):
    """Bounded synchronous processor with an explicitly supplied dispatcher.

    There is no default dispatcher, network implementation, background thread,
    credential lookup, disk payload spool, or retry. Production installation is
    separately gated in configure_observability; tests supply a local recorder.
    """

    def __init__(self, ledger, dispatch):
        self.ledger = ledger
        self.dispatch = dispatch
        self.preparer = BatchPreparer(ledger)
        self.pending = []
        self.lock = threading.RLock()
        self.complete = True
        self.closed = False

    def on_end(self, span):
        if (span.attributes or {}).get("logfire.span_type", "span") != "span":
            return
        with self.lock:
            if self.closed:
                return
            self.pending.append(span)
            if len(self.pending) >= 20:
                self.force_flush()

    def force_flush(self, timeout_millis=1000):
        if (type(timeout_millis) not in (int, float) or not math.isfinite(timeout_millis)
                or timeout_millis <= 0):
            self.complete = False
            return False
        deadline = time.monotonic() + timeout_millis / 1000
        with self.lock:
            try:
                if self.ledger.remaining() <= 0 or time.monotonic() >= deadline:
                    self.complete = False
                    return False
                if not self.pending:
                    return self.complete
                spans, self.pending = self.pending, []
                batch = self.preparer.prepare(spans)
                if batch is None or not self.ledger.authorize_dispatch(batch):
                    self.complete = False
                    return False
                remaining = min(self.ledger.remaining(), deadline - time.monotonic(), 2.0)
                if remaining <= 0:
                    self.complete = False
                    return False
                with logfire.suppress_instrumentation():
                    status = self.dispatch(batch.body, remaining)
                if (not self.ledger.finish(batch.attempt, status)
                        or time.monotonic() >= deadline):
                    self.complete = False
            except Exception:
                self.complete = False
            return self.complete

    def shutdown(self):
        with self.lock:
            complete = self.force_flush()
            self.closed = True
            return complete


def bounded_sdk_options(processor):
    """Supported SDK configuration for local/custom spans only; no default I/O.

    Non-secret placeholders avoid SDK fallback to ambient writer/API credentials.
    Production installation remains blocked until its dispatcher is approved.
    """
    for signal in ("TRACES", "METRICS", "LOGS"):
        os.environ[f"OTEL_{signal}_EXPORTER"] = "none"
    return {
        "send_to_logfire": False,
        "token": "disabled-for-bounded-export",
        "api_key": "disabled-for-bounded-export",  # pragma: allowlist secret - noncredential SDK sentinel
        "console": False,
        "metrics": False,
        # None permits lazy remote polling when any API key is configured.
        # An explicit empty local provider retains code-owned prompt defaults.
        "variables": logfire.LocalVariablesOptions(
            config=VariablesConfig(variables={}),
            include_resource_attributes_in_context=False,
            include_baggage_in_context=False,
            instrument=False,
        ),
        "add_baggage_to_attributes": False,
        "additional_span_processors": [processor],
        "advanced": logfire.AdvancedOptions(
            log_record_processors=[], resource_detectors=[],
        ),
    }


@contextmanager
def worker_trace_scope():
    """Place accounting in the existing supervisor-owned private workspace.

    This local scope does not configure a transport or read credentials. The
    supervisor retains directory cleanup after both success and forced stop.
    """
    mode = os.getenv("SPECIMEN_TRACE_EXPORT_MODE")
    if mode is None:
        yield None
        return
    if mode != "bounded-v1":
        raise TraceBudgetError("invalid_trace_export_mode")
    from .application.worker_deadline import current_deadline

    owner = current_deadline()
    if owner is None or owner.workspace is None:
        raise TraceBudgetError("trace_supervisor_required")
    if os.getenv("SPECIMEN_TRACE_LEDGER_PATH"):
        raise TraceBudgetError("trace_scope_already_owned")
    owner.check()
    scope = os.getenv("SPECIMEN_TRACE_SCOPE_SHA256", "")
    ledger = Ledger.create(
        owner.workspace / "trace-budget.sqlite3", deadline=owner.deadline, scope=scope,
    )
    os.environ["SPECIMEN_TRACE_LEDGER_PATH"] = str(ledger.path)
    token = _worker_completion.set({"path": ledger.path, "complete": True})
    try:
        with owner.track_tightening(ledger.tighten):
            yield ledger
    finally:
        _worker_completion.reset(token)
        os.environ.pop("SPECIMEN_TRACE_LEDGER_PATH", None)
