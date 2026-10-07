"""Frozen measurement v8 retains its coherent instructions and exact history."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.agents import PinnedManagedPrompt, ResearchDeps
from specimen_digitization.research_harness.contracts import ROLE_FIELDS, PromptPin, SpecialistRole
from specimen_digitization.research_harness.prompts import (
    resolve_prompt,
)
from test_organiser_raw_reading_evidence import build, request_for, two_labels

ROOT = Path(prompts.__file__).parent
PIN = "0" * 64
V8_PIN_SHA256 = "06310d03a1419ac509d8c23b1c68340b8213ec008d67223dca1840309e64e7f7"  # pragma: allowlist secret


def test_frozen_coherent_v8_pin_retains_its_exact_subset_instructions():
    pin = resolve_prompt(SpecialistRole.MEASUREMENT, profile_digest=PIN,
        source_registry_digest=PIN, toolset_digest=PIN, model_route="harness-deepseek",
        output_schema_digest=PIN)
    body = (ROOT / "specimen_measurement-v8.txt").read_text()
    historical_text = ((ROOT / "common-v1.txt").read_text() + "\n" + body
        + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[SpecialistRole.MEASUREMENT])) + ".\n")
    pin = PromptPin.model_validate({**pin.model_dump(mode="json"),
        "text": historical_text, "digest": hashlib.sha256(historical_text.encode()).hexdigest(),
        "version": "measurement-evidence-v8-2026-10-07"})
    assert pin.version == "measurement-evidence-v8-2026-10-07"
    assert pin.text.startswith((ROOT / "common-v1.txt").read_text() + "\n" + body)
    assert pin.digest == hashlib.sha256(pin.text.encode()).hexdigest()
    assert pin.digest == V8_PIN_SHA256
    assert "Copy only returned resolutions whose field_key is in the current request's" in body
    assert "Keep the complete\nutility result as tool context" in body
    assert "Do not emit an omitted field simply because the utility returned it" in body
    assert "heading is not required" in body
    assert "no rule\nyet qualifies" not in body
    assert "hand-over\nbuilds no assembly" not in body
    assert "only when every retained reader" not in body
    assert "copy its four exact resolutions" not in body.casefold()


def test_a_saved_v7_pin_keeps_its_exact_instructions_after_new_resolver_moves_to_v8():
    request = request_for(build(two_labels()), SpecialistRole.MEASUREMENT)
    text = ((ROOT / "common-v1.txt").read_text() + "\n"
        + (ROOT / "specimen_measurement-v7.txt").read_text()
        + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[request.role])) + ".\n")
    historical = PromptPin.model_validate({**request.prompt.model_dump(mode="json"),
        "text": text, "digest": hashlib.sha256(text.encode()).hexdigest(),
        "version": "measurement-evidence-v7-2026-10-06"})
    reopened = type(request).model_validate(request.model_copy(update={"prompt": historical}).model_dump(mode="json"))
    context = SimpleNamespace(deps=ResearchDeps({reopened.role: reopened}, None),
        agent=SimpleNamespace(name=reopened.role.value))
    assert PinnedManagedPrompt(reopened).get_instructions()(context) == text
    assert reopened.prompt == historical and reopened.prompt != request.prompt
