"""Reviewed repository prompts resolved once and pinned for durable continuation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import MappingProxyType

from ..contracts import PromptPin, ROLE_FIELDS, SpecialistRole

# Pin version of the 2026-09-29 role files. No role resolves to them now; the
# files stay on disk unchanged.
PROMPT_VERSION = "specialists-v1-2026-09-29"
# Geography's historian prompt validated by GEOLocate (owner G-geo-1..3, 2026-10-03).
GEOGRAPHY_PROMPT_VERSION = "geography-historian-v2-2026-10-03"
# The five non-geography roles with the G23 relation rule (2026-10-03). Each v2
# file is its v1 file followed by the rule. Temporal and measurement copy the
# relations their settlement gives and add none, because the validator admits
# only the settlement's exact result for a written date or an elevation.
RELATIONS_PROMPT_VERSION = "specialists-relations-v2-2026-10-03"
# All six roles with the publication rules a real label needs (Lane P, 2026-10-03).
# Each v3 file is its v2 file followed by one or two blocks: a resolution with no
# assembly cites the reading it interpreted so its lookup has a producer, and a
# human question cites its evidence only on the question. The v2 files stay on disk
# unchanged for audit (GEOGRAPHY_PROMPT_VERSION and RELATIONS_PROMPT_VERSION name them).
READING_CITATION_PROMPT_VERSION = "specialists-reading-citation-v3-2026-10-03"
# All six roles, for the fields the committed research profile declares missing
# policy "unstructured_label_event_unqualified" (committed_pins.py). Each v4 file is
# its v3 file followed by one block that tells the role to return waiting_policy,
# never waiting_source, for an owned declared field that no assembly and no source
# can ground, and waiting_source only for a source that failed or is unconfigured.
# The v3 files stay on disk unchanged for audit (READING_CITATION_PROMPT_VERSION).
MISSING_POLICY_PROMPT_VERSION = "specialists-missing-policy-v4-2026-10-03"
# All six roles, with the hand-over (Lane P W5, 2026-10-04): the request carries the ordinary
# extractor's field values as organiser_candidates (initial_requests.py), and each v5 file is its
# v4 file followed by one block that says how to verify a candidate against the raw readings, how
# a grounded candidate resolves from its accepted assembly, and what to return for one the
# readings do not support. The v4 files stay on disk unchanged for audit
# (MISSING_POLICY_PROMPT_VERSION names them).
HANDOVER_PROMPT_VERSION = "specialists-handover-v5-2026-10-04"
# Temporal and measurement now have a qualified two-reader event/unit route to
# exact local settlement. Their v6 files append the superseding instructions;
# all v5 files remain unchanged for replay and audit.
QUALIFIED_PROMPT_VERSION = "specialists-qualified-event-v6-2026-10-04"

# Role -> (role file, pin version). Each role's text is common-v1.txt, the role
# file and its owned-fields line. A role moves to a new file and version without
# changing any other role's text, digest or pin. Superseded files stay on disk
# for audit.
ROLE_PROMPTS = MappingProxyType({
    SpecialistRole.TAXONOMY: ("specimen_taxonomy-v5.txt", HANDOVER_PROMPT_VERSION),
    SpecialistRole.GEOGRAPHY: ("specimen_geography-v5.txt", HANDOVER_PROMPT_VERSION),
    SpecialistRole.TEMPORAL: ("specimen_temporal-v6.txt", QUALIFIED_PROMPT_VERSION),
    SpecialistRole.MEASUREMENT: ("specimen_measurement-v6.txt", QUALIFIED_PROMPT_VERSION),
    SpecialistRole.PARTIES: ("specimen_parties-v5.txt", HANDOVER_PROMPT_VERSION),
    SpecialistRole.COLLECTION: ("specimen_collection-v5.txt", HANDOVER_PROMPT_VERSION),
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
