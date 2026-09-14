"""Application-owned Logfire configuration for processing workers."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import PackageNotFoundError, version

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
        # Fail closed while the separately reviewed native transport is pending.
        # Never fall through to the SDK's unbounded default native exporters.
        raise ObservabilityConfigurationError("bounded_trace_transport_approval_required")
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


def _model_trace_carrier(context: Mapping[str, str]) -> dict[str, str]:
    """Propagate only the W3C parent, excluding baggage and opaque tracestate."""
    parent = context.get("traceparent", "")
    if isinstance(parent, str) and re.fullmatch(
        r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", parent
    ):
        return {"traceparent": parent}
    return {}


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
    if operation not in {"transcribe", "extract"}:
        raise ValueError("Unknown trusted model operation")
    configure_observability(capture_mode=CaptureMode.METADATA)
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
        logfire.shutdown(timeout_millis=1_000)
