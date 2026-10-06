"""New taxonomy jobs clarify genus-free codes; frozen jobs keep their prompt.

Offline prompt-pin and deterministic-input checks, not proof of model compliance.
"""
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from specimen_digitization.application.lookup import scientific_name
from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.agents import PinnedManagedPrompt, ResearchDeps
from specimen_digitization.research_harness.committed_pins import (
    UNQUALIFIED_LABEL_POLICY, committed_research_profile,
)
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, FieldKey, PromptPin, SpecialistRole,
)
from specimen_digitization.research_harness.prompts import (
    HANDOVER_PROMPT_VERSION, ROLE_PROMPTS, TAXONOMY_QUERY_PROMPT_VERSION, resolve_prompt,
)

from test_source_capture_v2 import make_capture_rig


def current_taxonomy_pin():
    return resolve_prompt(SpecialistRole.TAXONOMY, profile_digest="0" * 64,
        source_registry_digest="0" * 64, toolset_digest="0" * 64,
        model_route="function-fixture", output_schema_digest="0" * 64)


def test_v6_appends_to_frozen_v5_and_pins_the_declared_no_name_abstention():
    root = Path(prompts.__file__).parent
    old = (root / "specimen_taxonomy-v5.txt").read_bytes()
    new = (root / "specimen_taxonomy-v6.txt").read_bytes()
    assert new.startswith(old)
    assert hashlib.sha256(old).hexdigest() == "45ae9af8ae5bdad7c2cc540379b7ca3922f6a4b13674cc8ece19e94efc98e19e"  # pragma: allowlist secret
    assert hashlib.sha256(new).hexdigest() == "487ee9df157b1f381973da8fc46ff59115507838ea1c176c0b4d2b49ff4314c1"  # pragma: allowlist secret
    appended = " ".join(new[len(old):].decode("ascii").split())
    for phrase in ("sp. 30", "sp. 01", "not a sendable scientific-name assertion",
                   "does not trigger the instruction above to look a named taxon up first",
                   "Do not query GBIF with it, its bare number, or an invented genus",
                   "do not turn locality/collection context into genus evidence",
                   "actual genus or full scientific name evidenced in a taxon assertion",
                   "existing reading, producer and deciding-source rules",
                   "make no lookup and abstain", "work_state waiting_policy",
                   "value.state unresolved", "no literal, parsed, normalized, authority_id, evidence IDs or question",
                   f"reason missing_policy:{UNQUALIFIED_LABEL_POLICY}",
                   "Preserve raw morphocode readings, history and provenance",
                   "argument refusal opens no provider request and proves no scientific no_match",
                   "source lookup still requires waiting_source",
                   "Nothing here settles or clears a prior held or unknown source effect"):
        assert phrase in appended
    profile = committed_research_profile("org", "collection")
    taxon = next(row for row in profile.fields if row.field_key == FieldKey.TAXON)
    assert taxon.missing_policy == UNQUALIFIED_LABEL_POLICY
    assert ROLE_PROMPTS[SpecialistRole.TAXONOMY] == (
        "specimen_taxonomy-v6.txt", TAXONOMY_QUERY_PROMPT_VERSION)
    current = current_taxonomy_pin()
    assert current.version == TAXONOMY_QUERY_PROMPT_VERSION == "taxonomy-scientific-name-v6-2026-10-06"
    assert current.digest == "0779190ab08f2fedc0e3e52c3c57e62ada71f2282289922ae140c0b6002eb53c"  # pragma: allowlist secret


def test_frozen_v5_request_uses_its_original_prompt_after_new_jobs_move_to_v6(tmp_path):
    rig = make_capture_rig(tmp_path)
    root = Path(prompts.__file__).parent
    historical = ((root / "common-v1.txt").read_text() + "\n"
        + (root / "specimen_taxonomy-v5.txt").read_text()
        + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[SpecialistRole.TAXONOMY])) + ".\n")
    current = current_taxonomy_pin()
    data = current.model_dump(mode="json")
    data.update(text=historical, digest=hashlib.sha256(historical.encode()).hexdigest(),
        version=HANDOVER_PROMPT_VERSION)
    frozen_pin = PromptPin.model_validate(data)
    request = rig.request.model_copy(update={"prompt": frozen_pin})
    deps = ResearchDeps({request.role: request}, None)
    ctx = SimpleNamespace(deps=deps, agent=SimpleNamespace(name=request.role.value))
    assert PinnedManagedPrompt(request).get_instructions()(ctx) == historical
    assert request.prompt == frozen_pin and request.prompt.digest != current.digest
    assert "Scientific-name query correction (2026-10-06):" not in historical


@pytest.mark.parametrize("literal", ["sp. 30", "sp. 01", "sp.30", "Sp. 30"])
def test_genus_free_morphocodes_do_not_become_scientific_name_arguments(literal):
    parsed = scientific_name(literal)
    assert parsed is None or not parsed.genus


def test_morphocode_with_an_actual_genus_preserves_existing_genus_rank():
    parsed = scientific_name("Danaus sp. 30")
    assert parsed.genus == "Danaus" and parsed.query == "Danaus" and parsed.rank == "GENUS"
