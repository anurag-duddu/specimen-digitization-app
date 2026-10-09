"""Narrow measurement output requires real native dependency closure."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.agents import PinnedManagedPrompt, ResearchDeps
from specimen_digitization.research_harness.contracts import ROLE_FIELDS, PromptPin, SpecialistRole
from specimen_digitization.research_harness.prompts import MEASUREMENT_EVIDENCE_PROMPT_VERSION, ROLE_PROMPTS, resolve_prompt
from test_organiser_raw_reading_evidence import build, request_for, two_labels

ROOT = Path(prompts.__file__).parent
PIN = "0" * 64


def test_current_measurement_v10_requires_exact_native_dependency_closure_for_requested_rows():
    pin = resolve_prompt(SpecialistRole.MEASUREMENT, profile_digest=PIN,
        source_registry_digest=PIN, toolset_digest=PIN, model_route="harness-deepseek",
        output_schema_digest=PIN)
    assert ROLE_PROMPTS[SpecialistRole.MEASUREMENT] == (
        "specimen_measurement-v10.txt", MEASUREMENT_EVIDENCE_PROMPT_VERSION)
    assert pin.version == "measurement-evidence-v10-2026-10-07"
    assert pin.digest == "b745c0dae603f181182fbf95ffc47fd50d29a05b69e23f0bd30df0ad83506111"  # pragma: allowlist secret
    body = (ROOT / "specimen_measurement-v10.txt").read_bytes()
    assert hashlib.sha256(body).hexdigest() == "0312d35c411c2cd5cff0f8ec5168209bebc0f294602e669002b6db1001b272e5"  # pragma: allowlist secret
    text = " ".join(body.decode("ascii").split())
    for phrase in (
        "For each derived requested row, check every returned dependency pin",
        "exactly equal a genuine pin in request.dependencies",
        "a different source field whose exact RESOLVED sibling resolution you return",
        "with the matching digest and the derivation's source_field",
        "A field-revision number alone", "An unresolved sibling cannot supply one",
        "work_state waiting_policy with value.state unresolved",
        'protected_native_dependency_unavailable:<source_field>',
        "no literal, parsed, normalized, authority_id, evidence IDs, dependency pins or human question",
        "The full four-row utility provenance stays intact as tool context",
        "Do not ask a person to supply a number already written",
        "A requested written native From resolution may settle and supply its exact derived siblings as before",
    ):
        assert phrase in text


def test_previous_measurement_versions_and_current_temporal_bytes_remain_immutable():
    expected = {
        "specimen_measurement-v6.txt": "7c4647676e5f7d21eb803435133af42628a0d3c8f51debc55ae8ca5ccccd366a",  # pragma: allowlist secret
        "specimen_measurement-v7.txt": "4e2a0c7ea32d3bfd0fc7181d843cb90c2beaf93ca8a7f28dee202c4f342c9a22",  # pragma: allowlist secret
        "specimen_measurement-v8.txt": "9ac0433945135e17d3b2bd9291dc60502beeaf34baa62572e5af2aed53a1ed41",  # pragma: allowlist secret
        "specimen_measurement-v9.txt": "59e704aaddc6c8fa0aa4abf3657afcf2cb6f8a98c2475b968e1ab3a7b40a164a",  # pragma: allowlist secret
        "specimen_temporal-v7.txt": "aa75d8239e4f41606e3e1b17dc1b9256c972ea9e443e35d3b5d1cb50a02737be",  # pragma: allowlist secret
    }
    for name, checksum in expected.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == checksum


@pytest.mark.parametrize(("version", "expected_digest"), (
    (8, "06310d03a1419ac509d8c23b1c68340b8213ec008d67223dca1840309e64e7f7"),  # pragma: allowlist secret
    (9, "65e3c30aeac9d55d165eb147bf36d88c208400238bb206d4361c1f348dc812e7"),  # pragma: allowlist secret
))
def test_serialized_frozen_request_retains_its_exact_instructions_after_v10_resolution(version, expected_digest):
    request = request_for(build(two_labels()), SpecialistRole.MEASUREMENT)
    text = ((ROOT / "common-v1.txt").read_text() + "\n"
        + (ROOT / f"specimen_measurement-v{version}.txt").read_text()
        + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[request.role])) + ".\n")
    historical = PromptPin.model_validate({**request.prompt.model_dump(mode="json"),
        "text": text, "digest": hashlib.sha256(text.encode()).hexdigest(),
        "version": f"measurement-evidence-v{version}-2026-10-07"})
    assert historical.digest == expected_digest
    reopened = type(request).model_validate(request.model_copy(update={"prompt": historical}).model_dump(mode="json"))
    context = SimpleNamespace(deps=ResearchDeps({reopened.role: reopened}, None),
        agent=SimpleNamespace(name=reopened.role.value))
    assert PinnedManagedPrompt(reopened).get_instructions()(context) == text
    assert reopened.prompt == historical and reopened.prompt != request.prompt
