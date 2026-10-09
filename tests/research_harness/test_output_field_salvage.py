"""Real offline Agent output retries preserve validated independent siblings."""

import hashlib
import asyncio
from dataclasses import asdict
from pathlib import Path

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.contracts import (
    DependencyPin, FieldKey, FieldResolution, PromptPin, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import validate_resolution

from test_specialist_feedback import graph_request, retry_parts, tool_agent


def collection_output():
    request = graph_request(SpecialistRole.COLLECTION, FieldKey.HABITAT, "oak woodland")
    # The common admission test deliberately preserves the frozen v5 contract;
    # domain v6's stronger multi-reader rules are tested by its own integration.
    from specimen_digitization.research_harness import prompts
    text = ((Path(prompts.__file__).parent / "common-v1.txt").read_text() + "\n"
        + (Path(prompts.__file__).parent / "specimen_collection-v5.txt").read_text()
        + "\nOwned fields: " + ", ".join(map(str, request.field_keys)) + ".\n")
    request = request.model_copy(update={"prompt": PromptPin.model_validate({
        **request.prompt.model_dump(mode="json"), "version": prompts.HANDOVER_PROMPT_VERSION,
        "text": text, "digest": hashlib.sha256(text.encode()).hexdigest()})})
    evidence = request.assemblies[0].evidence_ids
    good = FieldResolution(field_key=FieldKey.HABITAT, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal="oak woodland", parsed="oak woodland",
            normalized="oak woodland", evidence_ids=list(evidence),
            evidence_relations=dict.fromkeys(evidence, "supports"),
            verbatim_by_observation={"raw-reading": "oak woodland"},
            input_source_by_observation={"raw-reading": "raw_reading"},
            settled_observation_ids=["raw-reading"]), evidence_ids=evidence,
        assembly_ids=(request.assemblies[0].id,), event_id=request.events[0].id,
        reason="Exact synthetic literal assembly")
    assert validate_resolution(request, good) == good
    bad = FieldResolution(field_key=FieldKey.FMNH_INS_NUMBER, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, parsed="0012345", normalized="0012345",
            evidence_ids=list(evidence)), evidence_ids=evidence,
        reason="Wrong field borrowed the habitat evidence")
    resolutions = tuple(good if key == good.field_key else bad if key == bad.field_key else
        FieldResolution(field_key=key, work_state=WorkState.WAITING_POLICY
            if key == FieldKey.VERBATIM_DTS else WorkState.WAITING_SOURCE,
            value=FieldValue(state=ValueState.UNRESOLVED), reason="source_prerequisite")
        for key in request.field_keys)
    return request, SpecialistOutput(role=request.role, resolutions=resolutions)


def run_output(request, output, *, correct=None, source_results=()):
    turns = []
    def respond(messages, info):
        turns.append(messages)
        selected = correct if correct is not None and len(turns) > 1 else output
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
            selected.model_dump(mode="json"))])
    agent, deps = tool_agent(request, respond)
    deps.tool_results[request.role] = list(source_results)
    return agent, deps, turns


def test_independent_valid_sibling_survives_after_the_original_correction_is_exhausted():
    request, output = collection_output()
    agent, deps, turns = run_output(request, output)
    admitted = agent.run_sync("resolve", deps=deps).output
    by_field = {item.field_key: item for item in admitted.resolutions}
    assert len(turns) == 2 and len(retry_parts(turns[-1])) == 1
    assert by_field[FieldKey.HABITAT] == output.resolutions[2]
    assert by_field[FieldKey.HABITAT].work_state == WorkState.RESOLVED
    failed = by_field[FieldKey.FMNH_INS_NUMBER]
    assert failed.work_state == WorkState.OPERATIONAL_FAILED
    assert failed.value == FieldValue(state=ValueState.UNRESOLVED)
    assert not failed.evidence_ids and not failed.dependencies and failed.question is None
    assert failed.value.authority_id is None
    assert tuple(by_field) == request.field_keys


@pytest.mark.parametrize("mutation", ("role", "coverage", "duplicate", "foreign"))
def test_structural_output_failure_is_not_salvageable(mutation):
    request, output = collection_output()
    if mutation == "role":
        output = output.model_copy(update={"role": SpecialistRole.GEOGRAPHY})
    elif mutation == "coverage":
        output = output.model_copy(update={"resolutions": output.resolutions[1:]})
    elif mutation == "duplicate":
        output = output.model_copy(update={"resolutions": (*output.resolutions[1:], output.resolutions[1])})
    else:
        output = output.model_copy(update={"resolutions": (output.resolutions[0].model_copy(
            update={"field_key": FieldKey.COUNTRY}), *output.resolutions[1:])})
    agent, deps, turns = run_output(request, output)
    with pytest.raises(UnexpectedModelBehavior):
        agent.run_sync("resolve", deps=deps)
    assert len(turns) == 2


def test_first_correction_can_repair_the_field_without_creating_a_failure():
    request, bad = collection_output()
    corrected = bad.model_copy(update={"resolutions": (FieldResolution(
        field_key=FieldKey.FMNH_INS_NUMBER, work_state=WorkState.WAITING_SOURCE,
        value=FieldValue(), reason="source_prerequisite"), *bad.resolutions[1:])})
    agent, deps, turns = run_output(request, bad, correct=corrected)
    assert agent.run_sync("resolve", deps=deps).output == corrected
    assert len(turns) == 2


def test_two_invalid_fields_do_not_suppress_one_valid_field():
    request, output = collection_output()
    second = output.resolutions[0].model_copy(update={"field_key": FieldKey.COLLECTION_CODE})
    output = output.model_copy(update={"resolutions": (output.resolutions[0], second, *output.resolutions[2:])})
    agent, deps, turns = run_output(request, output)
    admitted = agent.run_sync("resolve", deps=deps).output
    assert [item.work_state for item in admitted.resolutions[:3]] == [
        WorkState.OPERATIONAL_FAILED, WorkState.OPERATIONAL_FAILED, WorkState.RESOLVED]
    assert len(turns) == 2


def test_failure_propagates_to_derived_fields_but_preserves_an_independent_written_endpoint():
    from specimen_digitization.research_harness.evidence import elevation_resolutions, settle_elevation
    request = graph_request(SpecialistRole.MEASUREMENT, FieldKey.ELEVATION_FROM_FT, "1200-1500 ft")
    good = elevation_resolutions(settle_elevation(request, assembly_ids=("accepted-assembly",), source_revision=0))
    original = {item.field_key: item for item in good}
    output = SpecialistOutput(role=request.role, resolutions=tuple(item.model_copy(update={
        "value": item.value.model_copy(update={"parsed": "9999", "normalized": "9999"})})
        if item.field_key == FieldKey.ELEVATION_FROM_FT else item for item in good))
    agent, deps, turns = run_output(request, output)
    admitted = {item.field_key: item for item in agent.run_sync("resolve", deps=deps).output.resolutions}
    assert len(turns) == 2
    assert admitted[FieldKey.ELEVATION_FROM_FT].work_state == WorkState.OPERATIONAL_FAILED
    assert admitted[FieldKey.ELEVATION_FROM_M].work_state == WorkState.OPERATIONAL_FAILED
    assert admitted[FieldKey.ELEVATION_TO_FT] == original[FieldKey.ELEVATION_TO_FT]
    assert admitted[FieldKey.ELEVATION_TO_M] == original[FieldKey.ELEVATION_TO_M]
    assert not admitted[FieldKey.ELEVATION_FROM_M].derivation


@pytest.mark.parametrize("mutation", ("scope", "unknown_send", "field_scope", "source"))
def test_unsafe_source_receipt_cannot_be_hidden_by_salvage(mutation):
    from test_taxon_input_reconciliation import result_for
    request, output = collection_output()
    result = result_for(request, "Fixturegenus")
    updates = {"scope": {"scope": request.scope.model_copy(update={"specimen_id": "foreign"})},
        "unknown_send": {"effect_status": "held_unknown"},
        "field_scope": {"field_keys": (FieldKey.COUNTRY,)}, "source": {"source_id": "foreign"}}[mutation]
    receipt = result.receipt.model_copy(update=updates)
    agent, deps, turns = run_output(request, output, source_results=(result.model_copy(update={"receipt": receipt}),))
    with pytest.raises(UnexpectedModelBehavior):
        agent.run_sync("resolve", deps=deps)
    assert len(turns) == 2


def test_changed_consumed_dependency_is_a_whole_request_fence():
    request, output = collection_output()
    pin = DependencyPin(field_key=FieldKey.COLLECTORS, revision=1, digest=digest("settled"))
    request = request.model_copy(update={"dependencies": (pin,)})
    output = output.model_copy(update={"resolutions": tuple(item.model_copy(update={
        "dependencies": (pin.model_copy(update={"revision": 2}),)})
        if item.field_key == FieldKey.HABITAT else item for item in output.resolutions)})
    agent, deps, turns = run_output(request, output)
    with pytest.raises(UnexpectedModelBehavior):
        agent.run_sync("resolve", deps=deps)
    assert len(turns) == 2


def test_canonical_failure_guard_never_admits_a_value_or_provenance():
    from specimen_digitization.research_harness.output_admission import validation_failure
    request, _ = collection_output()
    bare = validation_failure(FieldKey.VERBATIM_DTS)
    assert validate_resolution(request, bare) == bare
    forged = bare.model_copy(update={"value": FieldValue(literal="invented")})
    with pytest.raises(ValueError, match="D/T/S"):
        validate_resolution(request, forged)


def test_no_independent_sibling_keeps_the_existing_failure_path():
    request, output = collection_output()
    request = request.model_copy(update={"field_keys": (FieldKey.FMNH_INS_NUMBER,),
        "field_revisions": {FieldKey.FMNH_INS_NUMBER: 0}})
    output = output.model_copy(update={"resolutions": output.resolutions[:1]})
    agent, deps, turns = run_output(request, output)
    with pytest.raises(UnexpectedModelBehavior):
        agent.run_sync("resolve", deps=deps)
    assert len(turns) == 2


def test_foreign_fragment_scope_cannot_be_hidden_by_salvage():
    request, output = collection_output()
    request = request.model_copy(update={"fragments": tuple(item.model_copy(update={
        "scope": item.scope.model_copy(update={"specimen_id": "foreign"})}) for item in request.fragments)})
    agent, deps, turns = run_output(request, output)
    with pytest.raises(UnexpectedModelBehavior):
        agent.run_sync("resolve", deps=deps)
    assert len(turns) == 2


def test_model_cannot_use_the_controller_marker_to_skip_the_original_correction():
    from specimen_digitization.research_harness.output_admission import validation_failure
    request, output = collection_output()
    output = output.model_copy(update={"resolutions": (
        validation_failure(FieldKey.FMNH_INS_NUMBER), *output.resolutions[1:])})
    agent, deps, turns = run_output(request, output)
    admitted = agent.run_sync("resolve", deps=deps).output
    assert len(turns) == 2
    assert "requires_controller_admission" in retry_parts(turns[-1])[0].content
    assert admitted.resolutions[0] == validation_failure(FieldKey.FMNH_INS_NUMBER)
    assert admitted.resolutions[2] == output.resolutions[2]


def test_actual_harness_engine_and_durable_journal_keep_salvage_with_native_acceptance_on_restart(tmp_path):
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.usage import RequestUsage
    from specimen_digitization.research_harness.accepted_output import read_accepted_checkpoint_proof
    from specimen_digitization.research_harness.contracts import (
        ALL_FIELDS, CollectionProfile, FieldProfile, SpecialistRequest,
    )
    from specimen_digitization.research_harness.gateway import ModelBinding
    from specimen_digitization.research_harness.persistence import (
        BudgetPolicy, DurabilityScope, ImmutableFileBlobs, ResearchStore, SqliteStateBackend,
    )
    from specimen_digitization.research_harness.runtime import build_research_engine, runtime_pins
    from specimen_digitization.research_harness.sources import SourceBroker, insects_registry

    request, output = collection_output()
    profile = CollectionProfile(id="insects", version="salvage-test-v1", organization_id="org",
        collection_id="insects", ancestry=("org", "insects"),
        fields=tuple(FieldProfile(field_key=key) for key in ALL_FIELDS), knowledge_version="test-v1")
    scope = request.scope.model_copy(update={"profile_digest": digest(profile)})
    registry = insects_registry()
    data = request.model_dump(mode="json")
    data.update(scope=scope.model_dump(mode="json"))
    for roster in ("fragments", "events", "assemblies", "relations"):
        data[roster] = [dict(row, scope=data["scope"]) for row in data[roster]]
    from specimen_digitization.research_harness.agents import specialist_output_schema_digest
    data["prompt"].update(profile_digest=scope.profile_digest, source_registry_digest=registry.digest,
        output_schema_digest=specialist_output_schema_digest())
    request = SpecialistRequest.model_validate(data)
    role = request.role
    binding = ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra", 128, 10, "offline-test-v1")
    settings = {"max_tokens": 128}
    pins = runtime_pins(profile, {role: request},
        model={role: {"route": binding.route_id, **asdict(binding)}}, settings=settings)
    durable = DurabilityScope(scope.organization_id, scope.collection_id, scope.specimen_id,
        scope.job_id, scope.generation, "test-operator", False)
    backend = SqliteStateBackend(tmp_path / "salvage.sqlite")
    backend.grant(durable)
    store = ResearchStore(backend, "disposable-salvage-test")
    store.initialize(durable, BudgetPolicy(1000))
    store.create_job(durable, pins, list(ALL_FIELDS))
    lease = store.claim(durable, "test-worker", ttl_seconds=120)
    blobs = ImmutableFileBlobs(tmp_path / "blobs")
    calls = []
    def respond(messages, info):
        calls.append(messages)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
            output.model_dump(mode="json"), tool_call_id=f"salvage-output-{len(calls)}")],
            usage=RequestUsage(input_tokens=1, output_tokens=1))
    engine = build_research_engine(profile=profile, requests={role: request}, store=store,
        scope=durable, lease=lease, blobs=blobs, tool_broker=SourceBroker(registry),
        bindings={role: binding}, settings=settings,
        base_model_factory=lambda selected: FunctionModel(respond), actual_cost=lambda response: 1)
    result = asyncio.run(engine.run())
    assert len(calls) == 2
    assert result.fields[FieldKey.HABITAT].work_state == WorkState.RESOLVED
    assert result.fields[FieldKey.FMNH_INS_NUMBER].work_state == WorkState.OPERATIONAL_FAILED
    checkpoints = store.job(durable)["checkpoints"]
    proofs = [read_accepted_checkpoint_proof(store, durable, blobs, item["id"]) for item in checkpoints]
    assert len(proofs) == len(request.field_keys)
    assert len({proof.proof_digest for proof in proofs}) == 1
    assert {item.field_key: item for item in proofs[0].acceptance.resolutions} == {
        key: result.fields[key] for key in request.field_keys}
    from specimen_digitization.research_harness.journal import DurableResearchJournal
    cold = DurableResearchJournal(store, durable, lease, blobs)
    assert {item.field_key: item for item in asyncio.run(cold.load(request.scope))} == {
        item.field_key: item for item in result.checkpoints}
    assert asyncio.run(engine.run()).checkpoints == result.checkpoints
    assert len(calls) == 2
