"""Coherent collecting-context instructions retain immutable temporal history."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.agents import PinnedManagedPrompt, ResearchDeps
from specimen_digitization.research_harness.contracts import ROLE_FIELDS, PromptPin, ResearchScope, SpecialistRequest, SpecialistRole
from specimen_digitization.research_harness.prompts import QUALIFIED_PROMPT_VERSION, TEMPORAL_CONTEXT_PROMPT_VERSION, ROLE_PROMPTS, resolve_prompt

ROOT = Path(prompts.__file__).parent
PIN = "0" * 64


def current():
    return resolve_prompt(SpecialistRole.TEMPORAL, profile_digest=PIN, source_registry_digest=PIN,
        toolset_digest=PIN, model_route="harness-deepseek", output_schema_digest=PIN)


def test_coherent_temporal_v7_preserves_v6_bytes_and_replaces_only_the_current_temporal_instructions():
    old = (ROOT / "specimen_temporal-v6.txt").read_bytes()
    new = (ROOT / "specimen_temporal-v7.txt").read_bytes()
    assert hashlib.sha256(old).hexdigest() == "c65fcdc5ee24d7164c665f2a70b3dec2509eee5c03100927f72e6d8c1f949047"  # pragma: allowlist secret
    assert hashlib.sha256(new).hexdigest() == "aa75d8239e4f41606e3e1b17dc1b9256c972ea9e443e35d3b5d1cb50a02737be"  # pragma: allowlist secret
    assert not new.startswith(old)
    assert ROLE_PROMPTS[SpecialistRole.TEMPORAL] == ("specimen_temporal-v7.txt", TEMPORAL_CONTEXT_PROMPT_VERSION)
    assert current().version == "temporal-collecting-context-v7-2026-10-07"
    assert current().digest == "e0b10dd8e01796863fba405022c6a4f2e4bb2818eff2af060ecfe0ce6478f50c"  # pragma: allowlist secret
    text = new.decode("ascii")
    assert "Complete collecting dates need no literal Collected: heading" in text
    assert "IX-14-46 3300'" in text and "IX-17-66-1" in text
    assert "whose field_key is in request.field_keys" in text
    assert "A protected To field may be absent" in text
    assert "no tool you have returns" not in text and "No rule yet qualifies" not in text


def test_serialized_frozen_temporal_v6_request_keeps_its_exact_old_prompt():
    historical = ((ROOT / "common-v1.txt").read_text() + "\n"
        + (ROOT / "specimen_temporal-v6.txt").read_text()
        + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[SpecialistRole.TEMPORAL])) + ".\n")
    data = current().model_dump(mode="json")
    data.update(text=historical, digest=hashlib.sha256(historical.encode()).hexdigest(), version=QUALIFIED_PROMPT_VERSION)
    pin = PromptPin.model_validate(data)
    assert pin.digest == "30744762b50a9ada2ea145bd24f8392b260696ccf94b6953a9b06bd71ead99cf"  # pragma: allowlist secret
    scope = ResearchScope(organization_id="org", collection_id="coll", specimen_id="synthetic", job_id="job",
        generation=1, input_digest=PIN, profile_digest=PIN, sensitive=False)
    frozen = SpecialistRequest(scope=scope, role=SpecialistRole.TEMPORAL,
        field_keys=ROLE_FIELDS[SpecialistRole.TEMPORAL], prompt=pin)
    reopened = SpecialistRequest.model_validate(frozen.model_dump(mode="json"))
    deps = ResearchDeps({reopened.role: reopened}, None)
    ctx = SimpleNamespace(deps=deps, agent=SimpleNamespace(name=reopened.role.value))
    assert PinnedManagedPrompt(reopened).get_instructions()(ctx) == historical
    assert reopened.prompt == pin and reopened.prompt != current()
