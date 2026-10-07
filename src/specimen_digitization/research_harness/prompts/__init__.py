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
# Geography v6 supersedes model-selected placement and activates the qualified
# historical roster while reserving G38 computed geometry for the trusted worker.
GEOGRAPHY_SOURCE_PROMPT_VERSION = "geography-qualified-sources-v6-2026-10-05"
# Geography v7 clarifies that correcting a query never clears refused same-field
# source history. The v6 file stays unchanged for frozen jobs and audit.
GEOGRAPHY_HISTORY_PROMPT_VERSION = "geography-source-history-v7-2026-10-06"
# Geography v8 keeps every v7 source-history and publication instruction, then
# makes the final typed response check explicit after the live role timed out
# before output feedback. Frozen v7 requests retain their original bytes/pin.
GEOGRAPHY_FINAL_RESULT_PROMPT_VERSION = "geography-final-result-v8-2026-10-07"
# Taxonomy v6 excludes genus-free morphocodes from the lookup-first instruction;
# the declared missing-policy path and historical v5 bytes stay intact.
TAXONOMY_QUERY_PROMPT_VERSION = "taxonomy-scientific-name-v6-2026-10-06"
# Stated elevation is parser-qualified from exact transcript spans, including
# ordinary prose, ranges and grouped numbers. v9 requires genuine native
# dependencies for narrowed requests; frozen v6/v7/v8 jobs retain their exact pins.
MEASUREMENT_EVIDENCE_PROMPT_VERSION = "measurement-evidence-v9-2026-10-07"
# Complete collecting dates may be grounded by same-label locality and collector
# evidence. The coherent v7 instructions replace only the active temporal pin.
TEMPORAL_CONTEXT_PROMPT_VERSION = "temporal-collecting-context-v7-2026-10-07"

# Role -> (role file, pin version). Each role's text is common-v1.txt, the role
# file and its owned-fields line. A role moves to a new file and version without
# changing any other role's text, digest or pin. Superseded files stay on disk
# for audit.
ROLE_PROMPTS = MappingProxyType({
    SpecialistRole.TAXONOMY: ("specimen_taxonomy-v6.txt", TAXONOMY_QUERY_PROMPT_VERSION),
    SpecialistRole.GEOGRAPHY: ("specimen_geography-v8.txt", GEOGRAPHY_FINAL_RESULT_PROMPT_VERSION),
    SpecialistRole.TEMPORAL: ("specimen_temporal-v7.txt", TEMPORAL_CONTEXT_PROMPT_VERSION),
    SpecialistRole.MEASUREMENT: ("specimen_measurement-v9.txt", MEASUREMENT_EVIDENCE_PROMPT_VERSION),
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
