"""Reviewed repository prompts resolved once and pinned for durable continuation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import MappingProxyType

from ..contracts import PromptPin, ROLE_FIELDS, SpecialistRole

# Pin version of the roles still on their 2026-09-29 role files.
PROMPT_VERSION = "specialists-v1-2026-09-29"
# Geography's historian prompt validated by GEOLocate (owner G-geo-1..3, 2026-10-03).
GEOGRAPHY_PROMPT_VERSION = "geography-historian-v2-2026-10-03"

# Role -> (role file, pin version). Each role's text is common-v1.txt, the role
# file and its owned-fields line. A role moves to a new file and version without
# changing any other role's text, digest or pin. Superseded files stay on disk
# for audit.
ROLE_PROMPTS = MappingProxyType({
    SpecialistRole.TAXONOMY: ("specimen_taxonomy-v1.txt", PROMPT_VERSION),
    SpecialistRole.GEOGRAPHY: ("specimen_geography-v2.txt", GEOGRAPHY_PROMPT_VERSION),
    SpecialistRole.TEMPORAL: ("specimen_temporal-v1.txt", PROMPT_VERSION),
    SpecialistRole.MEASUREMENT: ("specimen_measurement-v1.txt", PROMPT_VERSION),
    SpecialistRole.PARTIES: ("specimen_parties-v1.txt", PROMPT_VERSION),
    SpecialistRole.COLLECTION: ("specimen_collection-v1.txt", PROMPT_VERSION),
})


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
    name, version = ROLE_PROMPTS[role]
    root = Path(__file__).parent
    text = (root / "common-v1.txt").read_text(encoding="utf-8") + "\n" + (root / name).read_text(encoding="utf-8")
    text += "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n"
    return PromptPin(
        role=role, version=version, text=text,
        digest=hashlib.sha256(text.encode()).hexdigest(),
        output_schema_digest=output_schema_digest, profile_digest=profile_digest,
        source_registry_digest=source_registry_digest, toolset_digest=toolset_digest,
        model_route=model_route,
    )
