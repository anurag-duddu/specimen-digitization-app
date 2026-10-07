"""Measurement v7 extends immutable qualification with evidence-grounded settlement."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.agents import PinnedManagedPrompt, ResearchDeps
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, PromptPin, ResearchScope, SpecialistRequest, SpecialistRole,
)
from specimen_digitization.research_harness.prompts import (
    GEOGRAPHY_FINAL_RESULT_PROMPT_VERSION, HANDOVER_PROMPT_VERSION,
    QUALIFIED_PROMPT_VERSION, ROLE_PROMPTS,
    TAXONOMY_RECONCILIATION_PROMPT_VERSION, TEMPORAL_CONTEXT_PROMPT_VERSION, resolve_prompt,
)

ROOT = Path(prompts.__file__).parent
PIN = "0" * 64
V6_FILE_SHA256 = "7c4647676e5f7d21eb803435133af42628a0d3c8f51debc55ae8ca5ccccd366a"  # pragma: allowlist secret
V7_FILE_SHA256 = "4e2a0c7ea32d3bfd0fc7181d843cb90c2beaf93ca8a7f28dee202c4f342c9a22"  # pragma: allowlist secret
V6_PIN_SHA256 = "fe0cb50517fbfe284f4e2ce7493a5769e266349031d519c5a5a82d47b42b824d"  # pragma: allowlist secret
V7_PIN_SHA256 = "40a20bf9af6494c8a74a7df26cc56fd36fa36a3fe1b42d89c8675cdfbeed3307"  # pragma: allowlist secret


def pin(role=SpecialistRole.MEASUREMENT):
    current = resolve_prompt(role, profile_digest=PIN, source_registry_digest=PIN,
        toolset_digest=PIN, model_route="harness-deepseek", output_schema_digest=PIN)
    if role != SpecialistRole.MEASUREMENT:
        return current
    historical = ((ROOT / "common-v1.txt").read_text() + "\n"
        + (ROOT / "specimen_measurement-v7.txt").read_text()
        + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[role])) + ".\n")
    return PromptPin.model_validate({**current.model_dump(mode="json"), "text": historical,
        "digest": hashlib.sha256(historical.encode()).hexdigest(),
        "version": "measurement-evidence-v7-2026-10-06"})


def test_measurement_v7_appends_to_immutable_v6_and_keeps_its_historical_pin():
    old = (ROOT / "specimen_measurement-v6.txt").read_bytes()
    new = (ROOT / "specimen_measurement-v7.txt").read_bytes()
    assert hashlib.sha256(old).hexdigest() == V6_FILE_SHA256
    assert hashlib.sha256(new).hexdigest() == V7_FILE_SHA256
    assert new.startswith(old) and new != old
    current = pin()
    assert current.version == "measurement-evidence-v7-2026-10-06"
    assert current.digest == V7_PIN_SHA256
    assert current.text.startswith((ROOT / "common-v1.txt").read_text() + "\n" + new.decode("ascii"))


def test_measurement_v7_requires_autonomous_stated_value_settlement_and_preserves_conflicts():
    old = (ROOT / "specimen_measurement-v6.txt").read_bytes()
    new = (ROOT / "specimen_measurement-v7.txt").read_bytes()
    added = " ".join(new[len(old):].decode("ascii").split())
    for phrase in (
        "supersedes the v6 prefix-only, single-quantity and character-for-character unanimity restrictions",
        "inside ordinary locality prose", "heading is not required",
        "complete single values, ranges, approximation and written uncertainty",
        "Properly grouped thousands commas are numeric formatting",
        "Preserve each original literal and reading",
        "Compare retained readings for the same event by their full parsed assertion",
        "A verified decided transcript may ground its exact assertion while another reader is silent",
        "A competing quantity, unit, range, qualifier or uncertainty needs investigation",
        "Do not infer a unit", "every accepted elevation assembly for that event",
        "copy its four exact resolutions and their provenance",
        "does not require a human Fill the rest command", "Never replace a written elevation with DEM",
        "Parser, schema and tool failures are operational failures for repair/retry",
        "Human review is the fallback after evidence cannot settle the remaining ambiguity",
    ):
        assert phrase in added


def test_measurement_v7_change_is_scoped_to_its_role():
    assert {role: ROLE_PROMPTS[role] for role in SpecialistRole if role != SpecialistRole.MEASUREMENT} == {
        SpecialistRole.TAXONOMY: ("specimen_taxonomy-v7.txt", TAXONOMY_RECONCILIATION_PROMPT_VERSION),
        SpecialistRole.GEOGRAPHY: ("specimen_geography-v8.txt", GEOGRAPHY_FINAL_RESULT_PROMPT_VERSION),
        SpecialistRole.TEMPORAL: ("specimen_temporal-v7.txt", TEMPORAL_CONTEXT_PROMPT_VERSION),
        SpecialistRole.PARTIES: ("specimen_parties-v5.txt", HANDOVER_PROMPT_VERSION),
        SpecialistRole.COLLECTION: ("specimen_collection-v5.txt", HANDOVER_PROMPT_VERSION),
    }
    for role in SpecialistRole:
        assert ("Evidence-grounded elevation resolution (v7" in pin(role).text) == (role == SpecialistRole.MEASUREMENT)


def test_frozen_measurement_v6_request_keeps_its_exact_prompt_after_resolver_moves_to_v7():
    historical = ((ROOT / "common-v1.txt").read_text() + "\n"
        + (ROOT / "specimen_measurement-v6.txt").read_text()
        + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[SpecialistRole.MEASUREMENT])) + ".\n")
    data = pin().model_dump(mode="json")
    data.update(text=historical, digest=hashlib.sha256(historical.encode()).hexdigest(),
        version=QUALIFIED_PROMPT_VERSION)
    historical_pin = PromptPin.model_validate(data)
    assert historical_pin.digest == V6_PIN_SHA256
    scope = ResearchScope(organization_id="org", collection_id="coll", specimen_id="synthetic",
        job_id="job", generation=1, input_digest=PIN, profile_digest=PIN, sensitive=False)
    frozen = SpecialistRequest(scope=scope, role=SpecialistRole.MEASUREMENT,
        field_keys=ROLE_FIELDS[SpecialistRole.MEASUREMENT], prompt=historical_pin)
    reopened = SpecialistRequest.model_validate(frozen.model_dump(mode="json"))
    deps = ResearchDeps({reopened.role: reopened}, None)
    context = SimpleNamespace(deps=deps, agent=SimpleNamespace(name=reopened.role.value))
    assert PinnedManagedPrompt(reopened).get_instructions()(context) == historical
    assert reopened.prompt == historical_pin and reopened.prompt != pin()
