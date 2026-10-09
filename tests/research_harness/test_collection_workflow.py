"""Real collection tools/validation and composed publication on offline fixtures."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.application.production import actor_uid
from specimen_digitization.research_harness.accepted_output import AcceptedOutputProofV1, validation_boundary_pins
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.collection import COLLECTION_FIELDS, collection_resolution
from specimen_digitization.research_harness.contracts import (
    FieldKey, FieldResolution, SpecialistRequest, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.engine import ResearchEngine
from specimen_digitization.research_harness.evidence import dts_policy_resolution
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from specimen_digitization.research_harness.sources import SourceBroker, SourceRegistry

from test_collection_qualification import collection_request, retained
from test_collection_qualification import build, FieldSpec, RegionSpec
from test_organiser_handover_composer import STORED, build_rig, run
import test_unkeyed_label_review as review
from production_e2e_support import research_state
from test_specialist_feedback import retry_parts, tool_agent

sys.path.insert(0, str(Path(__file__).parents[1]))
from test_research_harness_engine import Journal, inputs  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx
    def refuse(*args, **kwargs):
        raise AssertionError("Collection workflow tests must remain offline")
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


def collection_model(request, *, invalid_first=False, recorded=None):
    keys = tuple(key for key in request.field_keys if key in COLLECTION_FIELDS)
    turns = []
    def respond(messages, info):
        turns.append(messages)
        returns = [part.content for message in messages for part in message.parts
            if isinstance(part, ToolReturnPart) and part.tool_name == "invoke_utility"]
        if len(returns) < len(keys):
            key = keys[len(returns)]
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_collection", "arguments": {"field_key": str(key)}})])
        resolutions = [FieldResolution.model_validate(json.loads(result.candidate_json[0])["resolutions"][0])
            for result in returns]
        if FieldKey.VERBATIM_DTS in request.field_keys:
            resolutions.append(dts_policy_resolution(None))
        if invalid_first and not retry_parts(messages):
            resolutions[0] = resolutions[0].model_copy(update={"value": resolutions[0].value.model_copy(
                update={"parsed": "0019999", "normalized": "0019999"})})
        if recorded is not None:
            recorded.append((request, tuple(resolutions), tuple(returns)))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
            SpecialistOutput(role=request.role, resolutions=tuple(resolutions)).model_dump(mode="json"))])
    return FunctionModel(respond), turns


@pytest.mark.parametrize("invalid_first", (False, True))
def test_real_agent_copies_collection_tools_and_corrects_an_invalid_final_without_repeating_tools(invalid_first):
    request = collection_request(retained(
        "FMNH INS 0012345\nHabitat: oak woodland\nMethod: light trap\nCollection code: INSECTS"))
    model, turns = collection_model(request, invalid_first=invalid_first)
    agent, deps = tool_agent(request, model.function)
    result = agent.run_sync("Resolve requested collection fields", deps=deps,
        conversation_id="offline-collection-tools")
    assert len(turns) == 5 + int(invalid_first)
    assert len(deps.tool_results[request.role]) == 4
    assert [row.value.normalized for row in result.output.resolutions] == [
        "0012345", "INSECTS", "oak woodland", "light trap", None]
    assert result.output.resolutions[-1].work_state == WorkState.WAITING_POLICY
    if invalid_first:
        assert "specialist_output_has_invalid_evidence_or_scope" in retry_parts(turns[-1])[-1].content
    accepted = AcceptedOutputProofV1(original_request=request, native_run_id=result.run_id,
        conversation_id=result.conversation_id, resolutions=result.output.resolutions,
        source_results=tuple(deps.tool_results[request.role]), effect_ids=(),
        model_settings_digest=digest("offline-collection-model"), **validation_boundary_pins())
    for source in accepted.source_results:
        assert verify_local_utility_v2(request, source).tool_id == "settle_collection"
        assert source.receipt is None


def test_composed_offline_native_workflow_recovers_misfiled_spans_and_publishes_without_save(tmp_path, monkeypatch):
    texts = ("Chicago, Cook County\nIllinois, United States\ngrassland station",
        "FMNH INS\n0010001\nSynthetic Colléctor ♂\n12 June 1948\n1200 ft\n"
        "Habitat: oak\n  woodland margin\nMethod: light trap\nCollection code: INSECTS")
    stored = tuple(row for row in STORED if FieldKey(row[0]) not in COLLECTION_FIELDS) + (
        ("habitat", "light trap", 1),)
    rig, token = build_rig(tmp_path, monkeypatch, stored=stored, texts=texts)
    actual = []
    base = review.specialist_factory(rig.model_calls)
    def factory(request, binding):
        if request.role != SpecialistRole.COLLECTION:
            return base(request, binding)
        model, _ = collection_model(request, recorded=actual)
        return model
    try:
        parsed, specimen, hold = run(rig, factory)
    finally:
        actor_uid.reset(token)
    assert hold is None, hold
    assert parsed.run.fields["habitat"].literal == "light trap"  # organiser hint stays in frozen input
    expected = {"fmnh_ins_number": "0010001", "collection_code": "INSECTS",
        "habitat": "oak\n  woodland margin", "collection_method": "light trap"}
    assert {key: specimen.run.fields[key].parsed for key in expected} == expected
    assert specimen.run.stage == "finalized" and specimen.run.disposition == "needs_human_review"
    assert "mandatory_unresolved:verbatim_dts" in specimen.run.reasons
    assert not any(reason.startswith("kind_mismatch:verbatim_dts") for reason in specimen.run.reasons)
    _, state = research_state(rig.fake, rig.specimen_id)
    job = next(iter(state["jobs"].values()))
    assert {key: job["fields"][key]["work_state"] for key in expected} == dict.fromkeys(expected, "resolved")
    assert set(expected) <= {row["causal_proof"]["changed_field"] for row in rig.fake.receipts.values()}
    request, resolutions, results = actual[-1]
    assert len(results) == 4 and all(row.receipt is None for row in results)
    assert request.organiser_candidates[0].literal == "light trap"
    assert {row.work_state for row in resolutions if row.field_key in COLLECTION_FIELDS} == {WorkState.RESOLVED}


def test_interruption_after_local_utility_keeps_saved_sibling_and_resumes_narrowed_request():
    profile, scope, _ = inputs()
    built = retained("FMNH INS 0012345\nHabitat: oak woodland")
    # Rebuild the graph with the engine fixture's genuinely pinned scope/profile.
    from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
    graph = NativeGenerationRequestFactory._build_graph(built.specimen, scope)
    built.scope, built.graph = scope, graph
    request = collection_request(built)
    journal = Journal()
    saved = collection_resolution(request, FieldKey.FMNH_INS_NUMBER)
    asyncio.run(journal.commit(request, (saved,), receipt_ids=(), model_settings_digest=digest("engine fixture")))
    calls, effects = [], []
    interrupted = True
    class Harness:
        def __init__(self, selected):
            self.selected = selected
        async def run_specialist(self, role):
            nonlocal interrupted
            narrowed = self.selected[role]
            calls.append(narrowed.field_keys)
            broker = SourceBroker(SourceRegistry(()))
            result = await broker.invoke_utility(narrowed, "settle_collection", {"field_key": "habitat"})
            effects.append(result)
            if interrupted:
                interrupted = False
                raise asyncio.CancelledError()
            resolutions = tuple(collection_resolution(narrowed, key) if key in COLLECTION_FIELDS
                else dts_policy_resolution(None) for key in narrowed.field_keys)
            return SimpleNamespace(resolutions=resolutions, source_results=(result,), model_effect_ids=())
    engine = ResearchEngine(profile=profile, requests={request.role: request}, journal=journal,
        harness_factory=Harness, model_settings_digest=digest("engine fixture"))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(engine.run())
    assert set(journal.checkpoints) == {FieldKey.FMNH_INS_NUMBER}
    original = journal.checkpoints[FieldKey.FMNH_INS_NUMBER]
    outcome = asyncio.run(engine.run())
    assert journal.checkpoints[FieldKey.FMNH_INS_NUMBER] == original
    assert FieldKey.FMNH_INS_NUMBER not in calls[0] and calls[0] == calls[1]
    assert outcome.fields[FieldKey.HABITAT].work_state == WorkState.RESOLVED
    assert effects[0] == effects[1] and all(row.receipt is None for row in effects)
    assert verify_local_utility_v2(SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "field_keys": calls[-1], "field_revisions": {key: 0 for key in calls[-1]}}), effects[-1])


@pytest.mark.parametrize(("text", "literal", "key"), (
    ("Habitat: oak woodland\nHabitat: wet grassland", "oak woodland", FieldKey.HABITAT),
    ("Catalog number: 0012345\nCatalog number: 0012345.6", "0012345", FieldKey.FMNH_INS_NUMBER),
))
def test_retained_raw_contradiction_cannot_be_hidden_by_only_one_native_quote(text, literal, key):
    built = build((RegionSpec(text),), (FieldSpec("country", literal,
        shape="reading", readers=(0,), quote=literal),))
    request = collection_request(built)
    assert len([row for row in request.assemblies if row.field_key == key]) == 1
    outcome = collection_resolution(request, key)
    assert outcome.work_state == WorkState.WAITING_POLICY and outcome.value.parsed is None


@pytest.mark.parametrize("metadata", (
    {"authority_id": "0012345"},
    {"authority_identity": {"module": "ecatalogue", "irn": 12345}},
    {"layer": "derived"},
    {"derived_from": ["elevation_from_m"]},
))
def test_a_local_catalogue_value_cannot_manufacture_identity_or_derivation(metadata):
    from specimen_digitization.research_harness.evidence import EvidenceError, validate_resolution
    request = collection_request(retained("FMNH INS 0012345"))
    outcome = collection_resolution(request, FieldKey.FMNH_INS_NUMBER)
    invented = outcome.model_copy(update={"value": outcome.value.model_copy(update=metadata)})
    with pytest.raises(EvidenceError):
        validate_resolution(request, invented)
