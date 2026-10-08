"""The active taxonomy pin preserves frozen v6 and states the G20/G32 boundary."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.agents import PinnedManagedPrompt, ResearchDeps
from specimen_digitization.research_harness.contracts import PromptPin, ROLE_FIELDS, SpecialistRole
from specimen_digitization.research_harness.prompts import (
    TAXONOMY_QUERY_PROMPT_VERSION, TAXONOMY_RECONCILIATION_PROMPT_VERSION,
)

from test_taxon_input_reconciliation import request_for


def test_v7_pin_keeps_frozen_bytes_and_records_the_reconciliation_boundary():
    root = Path(prompts.__file__).parent
    old, new = ((root / f"specimen_taxonomy-v{version}.txt").read_bytes() for version in (6, 7))
    assert new.startswith(old)
    assert hashlib.sha256(old).hexdigest() == "487ee9df157b1f381973da8fc46ff59115507838ea1c176c0b4d2b49ff4314c1"  # pragma: allowlist secret
    assert hashlib.sha256(new).hexdigest() == "cebc8364b50c69a3e7a05082025aad99686a1e4a59f532aee00d83db9671c948"  # pragma: allowlist secret
    current = request_for().prompt
    assert current.version == TAXONOMY_RECONCILIATION_PROMPT_VERSION
    assert current.digest == "ba33889e495c286e089b517366117c5167e788283d8a44eaae02ca14b3a6fc72"  # pragma: allowlist secret
    added = " ".join(new[len(old):].decode("ascii").split())
    for phrase in ("one-completed-lookup stopping rule", "exact query identity",
        "no_match on another label never waives it", "Global Names Verifier and pinned Catalogue of Life",
        "Only completion of the exact failed query", "requires no specimen-user Save"):
        assert phrase in added


def test_frozen_v6_is_injected_without_resolving_the_new_role_pin():
    request = request_for()
    root = Path(prompts.__file__).parent
    historical = ((root / "common-v1.txt").read_text() + "\n"
        + (root / "specimen_taxonomy-v6.txt").read_text()
        + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[SpecialistRole.TAXONOMY])) + ".\n")
    pin = PromptPin.model_validate({**request.prompt.model_dump(mode="json"), "text": historical,
        "digest": hashlib.sha256(historical.encode()).hexdigest(), "version": TAXONOMY_QUERY_PROMPT_VERSION})
    frozen = request.model_copy(update={"prompt": pin})
    context = SimpleNamespace(deps=ResearchDeps({request.role: frozen}, None),
        agent=SimpleNamespace(name=request.role.value))
    assert PinnedManagedPrompt(frozen).get_instructions()(context) == historical
    assert "Taxonomy reconciliation and sufficient-evidence stops" not in historical
