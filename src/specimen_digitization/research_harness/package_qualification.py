"""Executable boundary for the exact qualified official Harness package surface."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from importlib.metadata import version
from types import MappingProxyType
from typing import Mapping

from pydantic_ai_harness import ManagedPrompt, StepPersistence, SubAgent, SubAgents
from pydantic_ai_harness.media import MediaStore
from pydantic_ai_harness.step_persistence import StepStore

SERIALIZATION_VERSION = "pydantic-ai-2.51.0+harness-0.36.0/v1"
QUALIFIED_PACKAGES: Mapping[str, str] = MappingProxyType(
    {
        "pydantic-ai-slim": "2.51.0",
        "pydantic-evals": "2.51.0",
        "pydantic-graph": "2.51.0",
        "pydantic-ai-harness": "0.36.0",
        "logfire": "5.0.0",
    }
)
OFFICIAL_REFERENCES = (
    "https://github.com/pydantic/pydantic-ai-harness/blob/v0.36.0/pyproject.toml",
    "https://pypi.org/project/pydantic-ai-harness/0.36.0/",
    "https://pypi.org/project/pydantic-ai-slim/2.51.0/",
    "https://github.com/pydantic/pydantic-ai-harness/blob/v0.36.0/docs/subagents.md",
    "https://github.com/pydantic/pydantic-ai-harness/blob/v0.36.0/docs/step-persistence.md",
)

STEP_STORE_METHODS = {
    "register_run": ("self", "record"),
    "get_run": ("self", "run_id"),
    "list_runs": ("self", "parent_run_id", "conversation_id"),
    "append_event": ("self", "event"),
    "list_events": ("self", "run_id"),
    "save_snapshot": ("self", "snapshot"),
    "latest_snapshot": ("self", "run_id", "include_interrupted"),
    "record_tool_effect": ("self", "record"),
    "get_tool_effect": ("self", "run_id", "tool_call_id"),
    "list_unresolved_tool_effects": ("self", "run_id"),
}
MEDIA_STORE_METHODS = {
    "put": ("self", "data", "context"),
    "get": ("self", "uri", "context"),
    "exists": ("self", "uri", "context"),
    "public_url": ("self", "uri", "context"),
    "get_metadata": ("self", "uri", "context"),
}


class PackageCompatibilityError(RuntimeError):
    """An unqualified package or changed selected API cannot be used."""


@dataclass(frozen=True)
class PackageQualification:
    packages: Mapping[str, str]
    serialization_version: str
    references: tuple[str, ...] = OFFICIAL_REFERENCES
    provider_qualification: str = "not_run"
    cloud_qualification: str = "not_run"


def qualify_packages() -> PackageQualification:
    """Verify installed pins and the small API surface without external effects."""
    installed = {name: version(name) for name in QUALIFIED_PACKAGES}
    if installed != dict(QUALIFIED_PACKAGES):
        raise PackageCompatibilityError("installed_package_pins_do_not_match")
    for protocol, methods in ((StepStore, STEP_STORE_METHODS), (MediaStore, MEDIA_STORE_METHODS)):
        for name, parameters in methods.items():
            method = getattr(protocol, name, None)
            if not inspect.iscoroutinefunction(method):
                raise PackageCompatibilityError(f"async_protocol_changed:{name}")
            if tuple(inspect.signature(method).parameters) != parameters:
                raise PackageCompatibilityError(f"protocol_parameters_changed:{name}")
    required = {
        SubAgents: ("agents", "agent_folders", "inherit_tools", "shared_capabilities", "max_depth"),
        SubAgent: ("agent", "usage_limits", "timeout_seconds", "max_calls"),
        ManagedPrompt: ("name", "default", "label"),
        StepPersistence: ("store", "agent_name", "capture_frontier"),
    }
    for cls, parameters in required.items():
        if not set(parameters).issubset(inspect.signature(cls).parameters):
            raise PackageCompatibilityError(f"capability_parameters_changed:{cls.__name__}")
    return PackageQualification(MappingProxyType(installed), SERIALIZATION_VERSION)
