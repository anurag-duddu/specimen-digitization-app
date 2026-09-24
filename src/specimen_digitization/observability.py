"""Application-owned Logfire configuration for processing workers."""

from __future__ import annotations

import os
import re
import math
import stat
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import logfire


class ObservabilityConfigurationError(RuntimeError):
    """Raised when telemetry settings would violate the capture policy."""


class CaptureMode(StrEnum):
    """Supported content-capture policies.

    ``approved-content`` includes prompts, outputs, and tool payloads. It never
    includes binary image bytes; source assets remain in application storage.
    """

    METADATA = "metadata"
    APPROVED_CONTENT = "approved-content"


@dataclass(frozen=True, slots=True)
class ObservabilitySettings:
    """Resolved, auditable telemetry settings for one process."""

    environment: str
    service_name: str
    capture_mode: CaptureMode
    head_sample_rate: float
    distributed_tracing: bool

    @property
    def include_content(self) -> bool:
        return self.capture_mode is CaptureMode.APPROVED_CONTENT

    @property
    def include_binary_content(self) -> bool:
        return False

    @property
    def include_model_request_parameters(self) -> bool:
        return True

    @classmethod
    def from_environment(
        cls, *, capture_mode: CaptureMode | None = None
    ) -> ObservabilitySettings:
        environment = os.getenv("APP_ENV", "development").strip().lower()
        resolved_capture_mode = capture_mode or _capture_mode_from_environment()
        head_sample_rate = _sample_rate_from_environment()
        return cls(
            environment=environment,
            service_name=os.getenv(
                "LOGFIRE_SERVICE_NAME", "specimen-digitization"
            ).strip(),
            capture_mode=resolved_capture_mode,
            head_sample_rate=head_sample_rate,
            distributed_tracing=_environment_flag(
                "LOGFIRE_DISTRIBUTED_TRACING", default=False
            ),
        )


_configured_settings: ObservabilitySettings | None = None
_bounded_runtime = None
TRACE_APPROVAL_SHA256 = "06af8483b7b190a5b0f2549475681a60483f2aff98a714472baad28376703b48"  # pragma: allowlist secret (approval digest)


def _bounded_remaining(ledger):
    from .application.bounded_effect import current_effect_deadline
    from .application.worker_deadline import current_deadline

    deadlines = []
    effect = current_effect_deadline()
    if effect is not None:
        deadlines.append(effect)
    owner = current_deadline()
    if owner is not None:
        owner.check()
        deadlines.append(owner.deadline)
    if not deadlines or not all(math.isfinite(value) for value in deadlines):
        raise ObservabilityConfigurationError("trace_supervisor_required")
    remaining = ledger.remaining()
    # The ledger callback can block; recheck the original process clock after it.
    value = min(remaining, min(deadlines) - time.monotonic())
    if not math.isfinite(value) or value <= 0:
        raise ObservabilityConfigurationError("trace_original_deadline_expired")
    return value


def _configure_bounded(settings, *, send_to_logfire):
    global _configured_settings, _bounded_runtime
    from .bounded_telemetry import Ledger, MetadataBatchProcessor, bounded_sdk_options

    if os.getenv("SPECIMEN_TRACE_APPROVAL_SHA256") != TRACE_APPROVAL_SHA256:
        raise ObservabilityConfigurationError("bounded_trace_transport_approval_required")
    expected = {
        "SPECIMEN_TRACE_EXPORT_MODE": "bounded-v1",
        "APP_ENV": "production", "LOGFIRE_CAPTURE_MODE": "metadata",
        "LOGFIRE_SEND_TO_LOGFIRE": "false", "LOGFIRE_HEAD_SAMPLE_RATE": "1.0",
        "LOGFIRE_DISTRIBUTED_TRACING": "false",
    }
    if (any(os.getenv(key) != value for key, value in expected.items())
            or send_to_logfire is True or settings.capture_mode is not CaptureMode.METADATA
            or not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", settings.service_name)
            or any(os.getenv(key) is not None for key in (
                "LOGFIRE_BASE_URL", "LOGFIRE_ENVIRONMENT", "LOGFIRE_SERVICE_VERSION",
                "SSL_CERT_FILE", "SSL_CERT_DIR", "SSLKEYLOGFILE",
            ))
            or any(key.startswith("OTEL_") and not (
                key in {"OTEL_TRACES_EXPORTER", "OTEL_METRICS_EXPORTER", "OTEL_LOGS_EXPORTER"}
                and value == "none"
            ) for key, value in os.environ.items())):
        raise ObservabilityConfigurationError("invalid_bounded_trace_configuration")
    scope = os.getenv("SPECIMEN_TRACE_SCOPE_SHA256", "")
    try:
        path = Path(os.getenv("SPECIMEN_TRACE_LEDGER_PATH", ""))
        parent = path.parent.lstat()
        if (not path.is_absolute() or path.name != "trace-budget.sqlite3"
                or not stat.S_ISDIR(parent.st_mode) or stat.S_IMODE(parent.st_mode) != 0o700
                or parent.st_uid != os.geteuid() or not re.fullmatch(r"[0-9a-f]{64}", scope)):
            raise ValueError
        ledger = Ledger(path)
        if ledger.snapshot()["scope"] != scope:
            raise ValueError
        _bounded_remaining(ledger)
    except Exception:
        raise ObservabilityConfigurationError("invalid_bounded_trace_scope") from None
    binding = (os.getpid(), str(path), scope, settings)
    if _configured_settings is not None:
        if _bounded_runtime is None or _bounded_runtime["binding"] != binding:
            raise ObservabilityConfigurationError("trace_process_already_configured")
        return _configured_settings
    # All approval, capture, scope, ownership and original-clock checks precede
    # this sole credential read. The default SDK receives only neutral sentinels.
    from .bounded_trace_transport import TraceTransport

    try:
        remaining = lambda: _bounded_remaining(ledger)
        processor = MetadataBatchProcessor(
            ledger, TraceTransport(os.getenv("LOGFIRE_TOKEN"), remaining=remaining),
        )
    except Exception:
        raise ObservabilityConfigurationError("invalid_bounded_trace_credential") from None
    options = bounded_sdk_options(processor)
    logfire.configure(
        **options, service_name=settings.service_name, service_version=_service_version(),
        environment=settings.environment, inspect_arguments=False, distributed_tracing=False,
        sampling=logfire.SamplingOptions(head=1.0),
        resource_attributes={"specimen.telemetry.capture_mode": "metadata"},
    )
    logfire.instrument_pydantic_ai(
        include_content=False, include_binary_content=False,
        include_model_request_parameters=False, version=5,
    )
    _bounded_runtime = {"binding": binding, "processor": processor, "remaining": remaining}
    _configured_settings = settings
    return settings


def flush_bounded_observability():
    """Drain synchronously within the original clock; keep failure sticky."""
    runtime = _bounded_runtime
    if runtime is None:
        return {"configured": False, "complete": os.getenv("SPECIMEN_TRACE_EXPORT_MODE") is None}
    processor = runtime["processor"]
    try:
        if runtime["binding"][0] != os.getpid():
            raise ObservabilityConfigurationError("trace_process_mismatch")
        runtime["remaining"]()
        complete = processor.shutdown()
        runtime["remaining"]()
        processor.complete = bool(complete) and processor.complete
    except Exception:
        processor.complete = False
    return {"configured": True, "complete": processor.complete}


def _environment_flag(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _capture_mode_from_environment() -> CaptureMode:
    raw = os.getenv("LOGFIRE_CAPTURE_MODE", CaptureMode.METADATA.value)
    try:
        return CaptureMode(raw.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in CaptureMode)
        raise ObservabilityConfigurationError(
            f"LOGFIRE_CAPTURE_MODE must be one of: {allowed}."
        ) from exc


def _sample_rate_from_environment() -> float:
    raw = os.getenv("LOGFIRE_HEAD_SAMPLE_RATE", "1.0")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ObservabilityConfigurationError(
            "LOGFIRE_HEAD_SAMPLE_RATE must be a number between 0 and 1."
        ) from exc
    if not 0 < value <= 1:
        raise ObservabilityConfigurationError(
            "LOGFIRE_HEAD_SAMPLE_RATE must be greater than 0 and at most 1."
        )
    return value


def _service_version() -> str:
    try:
        return version("specimen-digitization")
    except PackageNotFoundError:
        return "development"


def configure_observability(
    *,
    send_to_logfire: bool | None = None,
    capture_mode: CaptureMode | None = None,
) -> ObservabilitySettings:
    """Configure Logfire once before agent or provider instrumentation.

    Content is exported only when ``approved-content`` is explicitly selected.
    Binary image bytes are never exported by this application integration.
    """
    global _configured_settings
    if os.getenv("SPECIMEN_TRACE_EXPORT_MODE") is not None:
        settings = ObservabilitySettings.from_environment(capture_mode=capture_mode)
        return _configure_bounded(settings, send_to_logfire=send_to_logfire)
    settings = ObservabilitySettings.from_environment(capture_mode=capture_mode)
    if _configured_settings is not None:
        if settings != _configured_settings:
            raise ObservabilityConfigurationError(
                "Logfire is already configured with different settings in this process."
            )
        return _configured_settings

    configure_options: dict[str, object] = {
        "service_name": settings.service_name,
        "service_version": _service_version(),
        "environment": settings.environment,
        "inspect_arguments": False,
        "distributed_tracing": settings.distributed_tracing,
        "sampling": logfire.SamplingOptions(head=settings.head_sample_rate),
        "resource_attributes": {
            "specimen.telemetry.capture_mode": settings.capture_mode.value,
        },
    }
    if send_to_logfire is not None:
        configure_options["send_to_logfire"] = send_to_logfire

    logfire.configure(**configure_options)
    logfire.instrument_pydantic_ai(
        include_content=settings.include_content,
        include_binary_content=settings.include_binary_content,
        include_model_request_parameters=settings.include_model_request_parameters,
        version=5,
    )
    _configured_settings = settings
    return settings


def configured_capture_mode() -> CaptureMode:
    """This process's configured capture mode; metadata when nothing is configured."""
    if _configured_settings is None:
        return CaptureMode.METADATA
    return _configured_settings.capture_mode


def _carrier_capture_mode(context: Mapping[str, str]) -> CaptureMode:
    """The parent's capture mode, from its carrier; metadata when absent or unknown."""
    try:
        return CaptureMode(context.get("capture_mode", CaptureMode.METADATA.value))
    except ValueError:
        return CaptureMode.METADATA


def _model_trace_carrier(context: Mapping[str, str]) -> dict[str, str]:
    """Propagate only the W3C parent, excluding baggage and opaque tracestate."""
    parent = context.get("traceparent", "")
    if isinstance(parent, str) and re.fullmatch(
        r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", parent
    ):
        return {"traceparent": parent}
    return {}


def model_trace_context(specimen_id: str, run_id: str) -> dict[str, str]:
    """Carry application-owned correlation IDs and the parent's capture mode."""
    return {
        **_model_trace_carrier(logfire.get_context()),
        "specimen_id": specimen_id,
        "run_id": run_id,
        # The child configures the same mode as its parent (LANE.md T5b).
        "capture_mode": configured_capture_mode().value,
    }


@contextmanager
def isolated_model_span(
    context: Mapping[str, str],
    *,
    operation: str,
    region_id: str | None = None,
    route_id: str | None = None,
) -> Iterator[logfire.LogfireSpan]:
    """Configure and drain a fresh model child's telemetry, in the parent's mode.

    Configuration, model work, and exporter shutdown all remain inside the
    existing run_isolated deadline. The parent can terminate a stalled exporter;
    this helper does not grant additional time or retry the model operation.
    """
    if operation not in {"classify", "transcribe", "extract"}:
        raise ValueError("Unknown trusted model operation")
    configure_observability(capture_mode=_carrier_capture_mode(context))
    attributes = {"specimen.model.operation": operation}
    for key, value in (
        ("specimen.id", context.get("specimen_id")),
        ("specimen.run.id", context.get("run_id")),
        ("specimen.region.id", region_id),
        ("specimen.route.id", route_id),
    ):
        if value is not None:
            attributes[key] = value
    try:
        with logfire.attach_context(_model_trace_carrier(context)):
            span = logfire.span("Run isolated specimen model", **attributes)
            span.__enter__()
            try:
                yield span
            except BaseException:
                span.set_attribute("specimen.model.outcome", "failed")
                raise
            finally:
                # Unknown storage/validation exceptions can contain source data.
                # Preserve failure semantics without handing their body or local
                # variables to Logfire's automatic exception recording.
                span.__exit__(None, None, None)
    finally:
        if os.getenv("SPECIMEN_TRACE_EXPORT_MODE") is not None:
            flush_bounded_observability()
        else:
            logfire.shutdown(timeout_millis=1_000)
