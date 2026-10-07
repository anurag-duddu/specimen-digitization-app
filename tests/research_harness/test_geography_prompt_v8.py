"""A short final-result reminder advances only new geography jobs.

The recorded live response was captured but never accepted: the role deadline
expired before output feedback, and its proposed literal/source history would
still have been refused. These checks pin the new instructions and the frozen
v7 replay path; source and output validators remain the actual authority.
"""

import hashlib
from pathlib import Path
from types import SimpleNamespace

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.agents import PinnedManagedPrompt, ResearchDeps
from specimen_digitization.research_harness.contracts import ROLE_FIELDS, PromptPin, SpecialistRole
from specimen_digitization.research_harness.prompts import (
    GEOGRAPHY_FINAL_RESULT_PROMPT_VERSION, GEOGRAPHY_HISTORY_PROMPT_VERSION,
    ROLE_PROMPTS, resolve_prompt,
)
from test_geolocate_validator import geography_request


ROOT = Path(prompts.__file__).parent
V7_FILE_SHA256 = "0dc19e84a30d657fa958a11f4694259ffd7cd1115af1aa4e09faa663df5db505"  # pragma: allowlist secret
V7_PIN_SHA256 = "71ab1cdee1cc836a3c3127d59d530fca03b4314091fbe7f7618fb6d01e073139"  # pragma: allowlist secret
V8_FILE_SHA256 = "1f8a49b243c19e1c2e4dcb1238bce199e21a9d81b4eb037c5810955905c02490"  # pragma: allowlist secret
V8_PIN_SHA256 = "30f5b580a78c53207d8f119f7b4afeaaed815c4b4ba79d8f426542f3adc09bba"  # pragma: allowlist secret


def prompt_text(filename):
    return ((ROOT / "common-v1.txt").read_text() + "\n"
        + (ROOT / filename).read_text()
        + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[SpecialistRole.GEOGRAPHY])) + ".\n")


def test_v8_is_a_new_pin_with_an_explicit_final_result_checklist():
    old = (ROOT / "specimen_geography-v7.txt").read_bytes()
    new = (ROOT / "specimen_geography-v8.txt").read_bytes()
    assert new.startswith(old) and new != old
    assert hashlib.sha256(old).hexdigest() == V7_FILE_SHA256
    assert hashlib.sha256(new).hexdigest() == V8_FILE_SHA256
    added = " ".join(new[len(old):].decode("ascii").split())
    for requirement in (
        "exactly one FieldResolution for each key in this request's field_keys",
        "none for unrequested or human-protected fields",
        "saved human choice, completed checkpoint or field-specific retry",
        "complete retained lookup history", "a corrected query does not erase one",
        "return waiting_source", "no human question", "do not repeat a provider request",
        "A genuine later success may resolve only under the existing exact candidate and evidence rules",
        "declared county/city missing-unit waiting_policy rule",
        "For every non-null value.literal", "source_observation_id",
        "source_region_id", "input_source", "verbatim_by_observation",
        "settled_observation_ids", "set value.literal null", "preserve its reason, source coverage",
        "printed place and named geographic or administrative unit words",
        "accepted precise_location assembly", "Do not send a full label",
    ):
        assert requirement in added
    assert ROLE_PROMPTS[SpecialistRole.GEOGRAPHY] == (
        "specimen_geography-v8.txt", GEOGRAPHY_FINAL_RESULT_PROMPT_VERSION)
    pin = resolve_prompt(SpecialistRole.GEOGRAPHY, profile_digest="0" * 64,
        source_registry_digest="0" * 64, toolset_digest="0" * 64,
        model_route="harness-deepseek", output_schema_digest="0" * 64)
    assert pin.text == prompt_text("specimen_geography-v8.txt")
    assert pin.version == "geography-final-result-v8-2026-10-07"
    assert pin.digest == V8_PIN_SHA256


def test_frozen_v7_request_still_replays_its_original_instruction_bytes():
    historical = prompt_text("specimen_geography-v7.txt")
    assert hashlib.sha256(historical.encode()).hexdigest() == V7_PIN_SHA256
    request = geography_request()
    data = request.prompt.model_dump(mode="json")
    data.update(text=historical, digest=V7_PIN_SHA256,
        version=GEOGRAPHY_HISTORY_PROMPT_VERSION)
    frozen = request.model_copy(update={"prompt": PromptPin.model_validate(data)})
    deps = ResearchDeps({frozen.role: frozen}, None)
    ctx = SimpleNamespace(deps=deps, agent=SimpleNamespace(name=frozen.role.value))
    assert PinnedManagedPrompt(frozen).get_instructions()(ctx) == historical
    assert frozen.prompt != request.prompt
