"""Reviewed repository prompts resolved once and pinned for durable continuation."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..contracts import PromptPin, ROLE_FIELDS, SpecialistRole

PROMPT_VERSION = "specialists-v1-2026-09-29"


def resolve_prompt(
    role: SpecialistRole,
    *,
    profile_digest: str,
    source_registry_digest: str,
    toolset_digest: str,
    model_route: str,
    output_schema_digest: str,
) -> PromptPin:
    """Return immutable exact instructions; never resolve mutable labels on replay."""
    role = SpecialistRole(role)
    root = Path(__file__).parent
    text = (root / "common-v1.txt").read_text() + "\n" + (root / f"{role.value}-v1.txt").read_text()
    text += "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n"
    return PromptPin(
        role=role, version=PROMPT_VERSION, text=text,
        digest=hashlib.sha256(text.encode()).hexdigest(),
        output_schema_digest=output_schema_digest, profile_digest=profile_digest,
        source_registry_digest=source_registry_digest, toolset_digest=toolset_digest,
        model_route=model_route,
    )
