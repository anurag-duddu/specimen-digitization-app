"""Offline output-contract controls for the retained collectors/catalogue failure.

Real utility results pass through the actual tool adapter and strict output
validator. No provider, publication, native checkpoint or reading selection runs.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness import prompts
from specimen_digitization.research_harness.contracts import (
    FieldKey, FieldResolution, SpecialistRequest, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import EvidenceError, validate_resolution
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from specimen_digitization.research_harness.prompts import (
    COLLECTION_EVIDENCE_PROMPT_VERSION, COLLECTION_PROVENANCE_PROMPT_VERSION,
    PARTIES_EVIDENCE_PROMPT_VERSION, PARTIES_PROVENANCE_PROMPT_VERSION,
)

from prompt_test_fixtures import retained_text
from test_collection_qualification import collection_request, retained
from test_people_utility import collector_request
from test_specialist_feedback import retry_parts, tool_agent


def one_field_request(role):
    if role == SpecialistRole.PARTIES:
        request, arguments = collector_request()
        tool, key = "settle_collectors", FieldKey.COLLECTORS
    else:
        request = collection_request(retained("FMNH INS\n0012345\nHabitat: oak woodland"))
        tool, key = "settle_collection", FieldKey.FMNH_INS_NUMBER
        arguments = {"field_key": str(key)}
    data = request.model_dump(mode="json")
    data.update(field_keys=[str(key)], field_revisions={str(key): request.field_revisions[key]})
    return SpecialistRequest.model_validate(data), tool, arguments


@pytest.mark.parametrize("role", (SpecialistRole.PARTIES, SpecialistRole.COLLECTION))
@pytest.mark.parametrize("fault", ("omitted_reading_maps", "changed_original_text"))
def test_strict_retry_recovers_complete_original_utility_row_without_repeating_tool(role, fault):
    request, tool, arguments = one_field_request(role)
    original_request_json = request.model_dump_json()
    turns, retained_rows, tool_views = [], [], []

    def respond(messages, info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": tool, "arguments": arguments})])
        [view] = [part.content for message in messages for part in message.parts
            if isinstance(part, ToolReturnPart)]
        if len(turns) == 2:
            tool_views.append(view.model_dump_json())
            [row] = json.loads(view.candidate_json[0])["resolutions"]
            retained_rows.append(row)
            assert row["value"]["verbatim_by_observation"]
            assert row["value"]["input_source_by_observation"]
            assert row["value"]["settled_observation_ids"]
            proposed = copy.deepcopy(row)
            if fault == "omitted_reading_maps":
                # Retained failures named readings in prose but omitted their
                # typed custody. Neither accepted assemblies nor prose fix it.
                for name in ("verbatim_by_observation", "input_source_by_observation",
                        "settled_observation_ids"):
                    proposed["value"].pop(name)
                proposed["reason"] = "Original reading IDs: " + ", ".join(
                    row["value"]["verbatim_by_observation"])
            else:
                observation = next(iter(proposed["value"]["verbatim_by_observation"]))
                proposed["value"]["verbatim_by_observation"][observation] += " invented suffix"
        else:
            assert len(turns) == 3
            [feedback] = retry_parts(messages)
            assert "specialist_output_literal_lacks_original_reading" in feedback.content
            assert "value.verbatim_by_observation" in feedback.content
            assert "value.input_source_by_observation" in feedback.content
            assert "value.settled_observation_ids" in feedback.content
            assert "Do not summarize or repeat the completed tool" in feedback.content
            assert view.model_dump_json() == tool_views[0]
            proposed = retained_rows[0]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "role": str(role), "resolutions": [proposed]})])

    agent, deps = tool_agent(request, respond)
    run = agent.run_sync(request.prompt.text, deps=deps,
        conversation_id=f"offline-original-reading-{role}-{fault}")
    assert len(turns) == 3
    [source] = deps.tool_results[role]
    [exact] = [FieldResolution.model_validate(row)
        for row in json.loads(source.candidate_json[0])["resolutions"]]
    assert run.output.resolutions == (exact,)
    assert exact == FieldResolution.model_validate(retained_rows[0])
    assert exact.work_state == WorkState.RESOLVED
    assert request.model_dump_json() == original_request_json
    proof = verify_local_utility_v2(request, source)
    assert proof.arguments == arguments and proof.original_request_digest == digest(request)
    assert proof.result_digest == digest(source)


@pytest.mark.parametrize(("role", "old_version", "new_version", "old_digest"), (
    (SpecialistRole.PARTIES, PARTIES_EVIDENCE_PROMPT_VERSION, PARTIES_PROVENANCE_PROMPT_VERSION,
        "6d281d2f407e3df3270aa2b715ab184775368e51c00c15a94d0b2299baa81df8"),  # pragma: allowlist secret
    (SpecialistRole.COLLECTION, COLLECTION_EVIDENCE_PROMPT_VERSION, COLLECTION_PROVENANCE_PROMPT_VERSION,
        "c8be41841669a1e9cfb0c21bf435ecc9e78db7925e0132031f64eb924637ebeb"),  # pragma: allowlist secret
))
def test_new_role_pin_preserves_historical_v6_reading_and_science_instructions(
        role, old_version, new_version, old_digest):
    root = Path(prompts.__file__).parent
    previous = (root / f"{role.value}-v6.txt").read_bytes()
    current = (root / f"{role.value}-v7.txt").read_bytes()
    assert current.startswith(previous) and current != previous
    assert hashlib.sha256(retained_text(role, 6).encode()).hexdigest() == old_digest
    request, _, _ = one_field_request(role)
    assert request.prompt.version == new_version and new_version != old_version


@pytest.mark.parametrize("version", (COLLECTION_EVIDENCE_PROMPT_VERSION, COLLECTION_PROVENANCE_PROMPT_VERSION))
@pytest.mark.parametrize("fault", ("wrong_scientific_value", "avoidable_policy_hold"))
def test_collection_v7_retains_v6_exact_qualification_and_unresolved_controls(version, fault):
    request, _, _ = one_field_request(SpecialistRole.COLLECTION)
    if version == COLLECTION_EVIDENCE_PROMPT_VERSION:
        text = retained_text(SpecialistRole.COLLECTION, 6)
        request = request.model_copy(update={"prompt": request.prompt.model_copy(update={
            "version": version, "text": text, "digest": hashlib.sha256(text.encode()).hexdigest()})})
    from specimen_digitization.research_harness.collection import collection_resolution
    exact = collection_resolution(request, FieldKey.FMNH_INS_NUMBER)
    assert validate_resolution(request, exact) == exact
    if fault == "wrong_scientific_value":
        invalid = exact.model_copy(update={"value": exact.value.model_copy(update={
            "parsed": "0019999", "normalized": "0019999"})})
        reason = "Collection result must cover all exact independent field assertions"
    else:
        invalid = FieldResolution(field_key=FieldKey.FMNH_INS_NUMBER, work_state=WorkState.WAITING_POLICY,
            value=FieldValue(state=ValueState.UNRESOLVED), reason="missing_policy:fixture")
        reason = "Qualified present collection evidence makes this unresolved output avoidable"
    with pytest.raises(EvidenceError, match=reason):
        validate_resolution(request, invalid)
