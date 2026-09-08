"""Application-owned Logfire configuration for processing workers."""

from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version

import logfire

_configured = False


def _environment_flag(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _service_version() -> str:
    try:
        return version("specimen-digitization")
    except PackageNotFoundError:
        return "development"


def configure_observability(*, send_to_logfire: bool | None = None) -> None:
    """Configure Logfire once, before any agent or provider instrumentation.

    Model messages, tool payloads, and binary images are excluded by default.
    They may be enabled only for approved, non-sensitive development fixtures.
    """
    global _configured
    if _configured:
        return

    configure_options: dict[str, object] = {
        "service_name": os.getenv("LOGFIRE_SERVICE_NAME", "specimen-digitization"),
        "service_version": _service_version(),
        "environment": os.getenv("APP_ENV", "development"),
        "inspect_arguments": False,
    }
    if send_to_logfire is not None:
        configure_options["send_to_logfire"] = send_to_logfire

    logfire.configure(**configure_options)
    logfire.instrument_pydantic_ai(
        include_content=_environment_flag("LOGFIRE_INCLUDE_CONTENT", default=False),
        include_binary_content=_environment_flag(
            "LOGFIRE_INCLUDE_BINARY_CONTENT", default=False
        ),
        include_model_request_parameters=_environment_flag(
            "LOGFIRE_INCLUDE_MODEL_REQUEST_PARAMETERS", default=False
        ),
    )
    _configured = True
