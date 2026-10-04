"""Application-owned Logfire configuration for processing workers."""

from __future__ import annotations

import os
import json
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
    if os.getenv("APP_ENV", "").strip().lower() == "production":
        # API embeds its build record inside application; worker/SAM at package root.
        candidates = [Path(__file__).with_name("_build.json"),
                      Path(__file__).parent / "application" / "_build.json"]
        values = []
        try:
            for path in candidates:
                if path.exists():
                    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(fd, "rb") as stream:
                        info = os.fstat(stream.fileno())
                        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 4096:
                            raise ValueError
                        raw = stream.read(4097)
                    if len(raw) > 4096:
                        raise ValueError
                    value = json.loads(raw)["source_sha"]
                    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
                        raise ValueError
                    values.append(value)
            if not values or len(set(values)) != 1:
                raise ValueError
            return values[0]
        except (OSError, ValueError, KeyError, TypeError):
            raise ObservabilityConfigurationError("production_trace_build_provenance_invalid") from None
    try:
        return version("specimen-digitization")
    except PackageNotFoundError:
        return "development"


def configure_observability(
    *,
    send_to_logfire: bool | None = None,
    capture_mode: CaptureMode | None = None,
    instrument_agents: bool = True,
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
    if settings.environment == "production" and settings.capture_mode is CaptureMode.APPROVED_CONTENT:
        # G3/G11 standard SDK export; no retired ledger or implicit project creation.
        forbidden = ("LOGFIRE_BASE_URL", "LOGFIRE_ENVIRONMENT", "LOGFIRE_SERVICE_VERSION")
        if any(os.getenv(name) for name in forbidden) or any(
            name.startswith("OTEL_") and not (
                name in {"OTEL_TRACES_EXPORTER", "OTEL_METRICS_EXPORTER", "OTEL_LOGS_EXPORTER"}
                and value == "none"
            ) for name, value in os.environ.items()
        ):
            raise ObservabilityConfigurationError("production_trace_ambient_export_refused")
        token = os.getenv("LOGFIRE_TOKEN")
        if not token or not token.isascii() or token.strip() != token:
            raise ObservabilityConfigurationError("production_trace_writer_required")
        from logfire.variables.config import VariablesConfig
        configure_options.update(
            token=token, console=False, metrics=False,
            advanced=logfire.AdvancedOptions(base_url="https://logfire-us.pydantic.dev",
                exception_callback=_private_exception_callback),
            variables=logfire.LocalVariablesOptions(config=VariablesConfig(variables={}),
                include_resource_attributes_in_context=False,
                include_baggage_in_context=False, instrument=False),
            add_baggage_to_attributes=False,
            scrubbing=logfire.ScrubbingOptions(extra_patterns=[
                r"(?:firebase|app)[._ -]?(?:user|uid)", r"user[._ -]?(?:id|email)",
                r"authorization", r"bearer", r"credential", r"email",
            ]),
        )
    logfire.configure(**configure_options)
    if instrument_agents:
        logfire.instrument_pydantic_ai(
            include_content=settings.include_content,
            include_binary_content=settings.include_binary_content,
            include_model_request_parameters=settings.include_model_request_parameters,
            version=5,
        )
    _configured_settings = settings
    return settings




def _private_exception_callback(helper):
    # SDK callbacks run before exception body/validation detail recording. Clear
    # the escaped status description too: exception strings may contain tokens.
    from opentelemetry.trace import Status, StatusCode
    helper.no_record_exception()
    helper.span.set_status(Status(StatusCode.ERROR))

def configure_production_observability(service: str, *, instrument_agents: bool = True):
    """Standing G3 service configuration; live cost/identity admission remains separate."""
    if service not in {"specimen-api", "specimen-worker", "specimen-sam"}:
        raise ObservabilityConfigurationError("production_trace_service_invalid")
    expected = {"APP_ENV": "production", "LOGFIRE_CAPTURE_MODE": "approved-content",
                "LOGFIRE_SEND_TO_LOGFIRE": "true", "LOGFIRE_SERVICE_NAME": service,
                "LOGFIRE_HEAD_SAMPLE_RATE": "1.0", "LOGFIRE_DISTRIBUTED_TRACING": "true"}
    if any(os.getenv(key) != value for key, value in expected.items()) or any(
        key.startswith("SPECIMEN_TRACE_") for key in os.environ
    ):
        raise ObservabilityConfigurationError("production_trace_standing_configuration_invalid")
    return configure_observability(send_to_logfire=True,
        capture_mode=CaptureMode.APPROVED_CONTENT, instrument_agents=instrument_agents)


# The flush bounds, in milliseconds. Every caller keeps FLUSH_MILLIS (one second) except the
# drain, whose last act is logfire.shutdown with FINAL_FLUSH_MILLIS: the last specimen's spans
# are still queued then (about 350 KB gzip behind a TLS connection that may be cold), and one
# second would false-alarm drain_trace_export_incomplete on a healthy tail longer than that
# (shown offline with a sleeping exporter, not observed in production). The ceiling keeps any
# explicit bound finite.
FLUSH_MILLIS = 1_000
FINAL_FLUSH_MILLIS = 10_000
FLUSH_CEILING_MILLIS = 30_000


def flush_production_observability(*, shutdown=False, maximum_millis=FLUSH_MILLIS):
    """Flush within the existing effect/task clock; grant no extra work or cleanup time.

    ``complete`` is False when the flush took longer than ``maximum_millis``, or when the
    effect/task deadline is nearer than that. The SDK's batch processor does not interrupt an
    export in progress (opentelemetry-python issue 4568), so the bound decides the verdict, not
    the duration: a stuck export ends only when the exporter's own HTTP timeout does. It does not
    say whether the export succeeded.
    """
    from .application.bounded_effect import current_effect_deadline
    from .application.worker_deadline import current_deadline
    deadlines = [value for value in [current_effect_deadline(),
        current_deadline().deadline if current_deadline() is not None else None]
        if value is not None]
    deadline = min(deadlines) if deadlines else None
    if type(maximum_millis) is not int or not 0 < maximum_millis <= FLUSH_CEILING_MILLIS:
        raise ObservabilityConfigurationError("production_trace_flush_bound_invalid")
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if not math.isfinite(remaining) or remaining <= 0:
            return {"configured": _configured_settings is not None, "complete": False}
        maximum_millis = min(maximum_millis, int(remaining * 1000))
    if maximum_millis <= 0 or _configured_settings is None:
        return {"configured": _configured_settings is not None, "complete": False}
    try:
        complete = (logfire.shutdown if shutdown else logfire.force_flush)(timeout_millis=maximum_millis)
    except Exception:
        complete = False
    if deadline is not None and time.monotonic() >= deadline:
        complete = False
    return {"configured": True, "complete": complete is True}


def install_api_trace_spans(app):
    @app.middleware("http")
    async def request_trace(request, call_next):
        # HTTP input, headers, paths, exceptions and app-user identities are never exported.
        method = request.method if request.method in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"} else "OTHER"
        span = logfire.span("Specimen API request", **{"http.request.method": method})
        span.__enter__()
        try:
            response = await call_next(request)
            span.set_attribute("http.response.status_code", response.status_code)
            return response
        except BaseException:
            span.set_attribute("specimen.api.outcome", "failed")
            raise
        finally:
            span.__exit__(None, None, None)

def _model_trace_carrier(context: Mapping[str, str]) -> dict[str, str]:
    """Propagate only the W3C parent, excluding baggage and opaque tracestate."""
    parent = context.get("traceparent", "")
    if isinstance(parent, str) and re.fullmatch(
        r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", parent
    ) and int(parent.split("-")[1], 16) != 0 and int(parent.split("-")[2], 16) != 0:
        return {"traceparent": parent}
    return {}



@contextmanager
def sam3_trace_span(request, headers):
    # No bytes, storage credentials, caller identity, arbitrary headers or exceptions.
    from .application.collection_profiles import Sam3Parameters
    for identifier in (request.specimen_id, request.run_id, request.collection_id):
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", identifier):
            raise ObservabilityConfigurationError("sam3_trace_identity_invalid")
    attributes = {"specimen.id": request.specimen_id, "specimen.run.id": request.run_id,
                  "specimen.collection.id": request.collection_id,
                  "sam3.model": request.model_id, "sam3.revision": request.model_revision,
                  "sam3.prompt": request.prompt,
                  "sam3.parameters": Sam3Parameters.model_validate(request.parameters).applied()}
    with logfire.attach_context(_model_trace_carrier({"traceparent": headers.get("traceparent", "")})):
        span = logfire.span("SAM 3 segmentation", **attributes)
        span.__enter__()
        try:
            yield span
        except BaseException:
            span.set_attribute("sam3.outcome", "failed")
            raise
        else:
            span.set_attribute("sam3.outcome", "completed")
        finally:
            span.__exit__(None, None, None)

def model_trace_context(specimen_id: str, run_id: str) -> dict[str, str]:
    """Carry application-owned correlation IDs, never specimen content."""
    return {
        **_model_trace_carrier(logfire.get_context()),
        "specimen_id": specimen_id,
        "run_id": run_id,
    }


@contextmanager
def isolated_model_span(
    context: Mapping[str, str],
    *,
    operation: str,
    region_id: str | None = None,
    route_id: str | None = None,
) -> Iterator[logfire.LogfireSpan]:
    """Configure and drain a fresh model child's metadata-only telemetry.

    Configuration, model work, and exporter shutdown all remain inside the
    existing run_isolated deadline. The parent can terminate a stalled exporter;
    this helper does not grant additional time or retry the model operation.
    """
    if operation not in {"classify", "transcribe", "first_pass", "extract"}:
        raise ValueError("Unknown trusted model operation")
    if os.getenv("APP_ENV") == "production" and os.getenv("SPECIMEN_TRACE_EXPORT_MODE") is None:
        configure_production_observability("specimen-worker")
    else:
        configure_observability(capture_mode=_capture_mode_from_environment())
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
            flush_production_observability(shutdown=True)
