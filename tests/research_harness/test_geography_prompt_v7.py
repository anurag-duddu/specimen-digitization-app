"""New geography jobs receive explicit immutable source-history instructions."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.agents import PinnedManagedPrompt, ResearchDeps
from specimen_digitization.research_harness.contracts import ROLE_FIELDS, PromptPin, SpecialistRole
from specimen_digitization.research_harness.prompts import (
    GEOGRAPHY_HISTORY_PROMPT_VERSION, GEOGRAPHY_SOURCE_PROMPT_VERSION, ROLE_PROMPTS, resolve_prompt,
)
from test_geolocate_validator import geography_request


def test_v7_appends_to_immutable_v6_and_remains_a_frozen_job_pin():
    root = Path(prompts.__file__).parent
    old = (root / "specimen_geography-v6.txt").read_bytes()
    new = (root / "specimen_geography-v7.txt").read_bytes()
    assert new.startswith(old)
    assert hashlib.sha256(old).hexdigest() == "55a6b4f65b7e38a7c4d598b74b22f1a4491952ebe6961f260c39d2353cb74524"  # pragma: allowlist secret
    assert hashlib.sha256(new).hexdigest() == "0dc19e84a30d657fa958a11f4694259ffd7cd1115af1aa4e09faa663df5db505"  # pragma: allowlist secret
    added = " ".join(new[len(old):].decode("ascii").split())
    for phrase in ("local policy_blocked refusal", "opened no provider request and has no receipt",
                   "when proposing waiting_human or source exhaustion",
                   "county/city waiting_policy rules for a missing unit or unsupported county stay unchanged",
                   "A corrected query does not erase", "earlier refused, failed or unreceipted lookup",
                   "work_state waiting_source", "value.state unresolved", "no human question",
                   "Preserve all lookup history and captured evidence", "existing one output retry",
                   "do not repeat a provider request", "existing waiting_human rule"):
        assert phrase in added
    historical = ((root / "common-v1.txt").read_text() + "\n" + new.decode("ascii")
        + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[SpecialistRole.GEOGRAPHY])) + ".\n")
    assert GEOGRAPHY_HISTORY_PROMPT_VERSION == "geography-source-history-v7-2026-10-06"
    assert hashlib.sha256(historical.encode()).hexdigest() == "71ab1cdee1cc836a3c3127d59d530fca03b4314091fbe7f7618fb6d01e073139"  # pragma: allowlist secret
    assert ROLE_PROMPTS[SpecialistRole.GEOGRAPHY][0] != "specimen_geography-v7.txt"


def test_frozen_v6_request_keeps_its_exact_prompt_after_resolver_moves_to_v7():
    root = Path(prompts.__file__).parent
    request = geography_request()
    historical = ((root / "common-v1.txt").read_text() + "\n"
        + (root / "specimen_geography-v6.txt").read_text()
        + "\nOwned fields: " + ", ".join(map(str, ROLE_FIELDS[SpecialistRole.GEOGRAPHY])) + ".\n")
    data = request.prompt.model_dump(mode="json")
    data.update(text=historical, digest=hashlib.sha256(historical.encode()).hexdigest(),
        version=GEOGRAPHY_SOURCE_PROMPT_VERSION)
    frozen_pin = PromptPin.model_validate(data)
    frozen = request.model_copy(update={"prompt": frozen_pin})
    deps = ResearchDeps({frozen.role: frozen}, None)
    ctx = SimpleNamespace(deps=deps, agent=SimpleNamespace(name=frozen.role.value))
    assert PinnedManagedPrompt(frozen).get_instructions()(ctx) == historical
    assert frozen.prompt == frozen_pin and frozen.prompt != request.prompt
