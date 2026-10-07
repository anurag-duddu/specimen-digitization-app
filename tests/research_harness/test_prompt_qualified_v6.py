"""Two immutable v6 prompts activate exact local date/elevation settlement."""

import hashlib
from pathlib import Path

import pytest

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.contracts import SpecialistRole
from specimen_digitization.research_harness.prompts import (
    MEASUREMENT_EVIDENCE_PROMPT_VERSION, QUALIFIED_PROMPT_VERSION, TEMPORAL_CONTEXT_PROMPT_VERSION, ROLE_PROMPTS, resolve_prompt,
)

ROOT = Path(prompts.__file__).parent
PIN = "0" * 64
CASES = (
    (SpecialistRole.TEMPORAL, "c65fcdc5ee24d7164c665f2a70b3dec2509eee5c03100927f72e6d8c1f949047",  # pragma: allowlist secret
     "settle_temporal", "date_visited_from", "date_identified"),
    (SpecialistRole.MEASUREMENT, "7c4647676e5f7d21eb803435133af42628a0d3c8f51debc55ae8ca5ccccd366a",  # pragma: allowlist secret
     "settle_elevation", "elevation", "unit"),
)


@pytest.mark.parametrize(("role", "sha", "utility", "field", "qualifier"), CASES)
def test_immutable_v6_file_extends_v5_and_the_active_pin_retains_its_exact_qualification(role, sha, utility, field, qualifier):
    name, version = ROLE_PROMPTS[role]
    expected_version = MEASUREMENT_EVIDENCE_PROMPT_VERSION if role == SpecialistRole.MEASUREMENT else TEMPORAL_CONTEXT_PROMPT_VERSION
    assert name == f"{role.value}-v{9 if role == SpecialistRole.MEASUREMENT else 7}.txt"
    assert version == expected_version
    old = (ROOT / f"{role.value}-v5.txt").read_bytes()
    new = (ROOT / f"{role.value}-v6.txt").read_bytes()
    assert new.startswith(old) and hashlib.sha256(new).hexdigest() == sha
    if role == SpecialistRole.MEASUREMENT:
        assert (ROOT / "specimen_measurement-v7.txt").read_bytes().startswith(new)
    added = new[len(old):].decode("ascii")
    assert "supersedes the v4 statement" in added and "v5 statement" in added
    assert "every retained reader" in added and "no external source authority" in added
    assert utility in added and field in added and qualifier in added
    assert "Copy" in added and "exactly" in added and "relations" in added
    resolved = resolve_prompt(role, profile_digest=PIN, source_registry_digest=PIN,
        toolset_digest=PIN, model_route="harness-deepseek", output_schema_digest=PIN)
    assert resolved.version == expected_version
    assert utility in resolved.text
    if role == SpecialistRole.MEASUREMENT:
        assert "Copy only returned resolutions whose field_key" in resolved.text
        assert "copy its four exact resolutions" not in resolved.text.casefold()
    else:
        assert "whose field_key is in request.field_keys" in resolved.text
