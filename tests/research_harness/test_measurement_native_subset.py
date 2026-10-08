"""Actual offline Agent/checkpoint closure with named preserved-human proof.

The label and model responses are synthetic. No remote provider or canonical
publication is executed; the real journal captures and verifies native proofs.
"""
import asyncio
from dataclasses import asdict, replace
import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from specimen_digitization.application.human_field_carry import contract_pin, verify
from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness.accepted_output import (
    AcceptedCheckpointProofV1, AcceptedOutputProofV1, read_accepted_checkpoint_proof,
    validation_boundary_pins,
)
from specimen_digitization.research_harness.agents import specialist_output_schema_digest
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, FieldCheckpoint, FieldKey, FieldResolution, SpecialistRequest,
    SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
from specimen_digitization.research_harness.gateway import ModelBinding
from specimen_digitization.research_harness.journal import DurableResearchJournal
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from specimen_digitization.research_harness.persistence import ImmutableFileBlobs
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.runtime import build_research_engine, runtime_pins
from specimen_digitization.research_harness.sources import SourceBroker, SourceRegistry
from test_organiser_raw_reading_evidence import build, two_labels
from test_preserved_human_outcomes import carried  # noqa: F401 -- shared named-save fixture
from test_specialist_feedback import retry_parts


def measurement_case(carried, tmp_path, *, source_key, literal):
    durable = replace(carried.durable, job_id=carried.durable.job_id + "-measurement-subset")
    scope = carried.scope.model_copy(update={"job_id": durable.job_id})
    line = "Camp at " + literal
    built = build(two_labels(a=line), [(source_key, "2A", literal, line),
                                      (source_key, "2B", literal, line)])
    fragments, events, assemblies, evidence, decisions, candidates = NativeGenerationRequestFactory._build_graph(
        built.specimen, scope)
    role = SpecialistRole.MEASUREMENT
    keys = tuple(key for key in ROLE_FIELDS[role] if key != FieldKey.ELEVATION_FROM_M)
    request = SpecialistRequest(scope=scope, role=role, field_keys=keys,
        prompt=resolve_prompt(role, profile_digest=scope.profile_digest,
            source_registry_digest="b" * 64, toolset_digest="c" * 64,
            model_route="harness-deepseek", output_schema_digest=specialist_output_schema_digest()),
        fragments=fragments, events=events, assemblies=assemblies, evidence=evidence,
        accepted_decisions=decisions, organiser_candidates=tuple(c for c in candidates if c.field_key in ROLE_FIELDS[role]),
        field_revisions={key: 0 for key in keys})
    bindings = {role: ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra", 128, 10, "offline-native-subset-v1")}
    settings = {"max_tokens": 128}
    pins = runtime_pins(carried.profile, {role: request},
        model={key: {"route": value.route_id, **asdict(value)} for key, value in bindings.items()}, settings=settings)
    pins = replace(pins, sources={**pins.sources, "human_field_carry": contract_pin()})
    carried.backend.grant(durable)
    carried.store.create_job(durable, pins, list(ALL_FIELDS), record_revision=carried.case.current.version,
        human_locks={key: value.proof_digest for key, value in carried.verified.outcomes.items()},
        preserved_human_outcomes={key: value.model_dump(mode="json") for key, value in carried.verified.outcomes.items()})
    blobs = ImmutableFileBlobs(tmp_path / "native-acceptance")
    journal = DurableResearchJournal(carried.store, durable,
        carried.store.claim(durable, "offline-measurement-subset"), blobs)
    return request, journal, durable, blobs, bindings, settings


@pytest.mark.parametrize(("source_key", "literal", "unsafe"), (
    ("elevation_to_m", "1200 m", True),
    ("elevation_from_ft", "6,400 ft", False),
))
def test_actual_agent_repairs_orphaned_derivation_before_native_checkpoint_and_preserves_human_unknown(
        carried, tmp_path, source_key, literal, unsafe):
    request, journal, durable, blobs, bindings, settings = measurement_case(
        carried, tmp_path, source_key=source_key, literal=literal)
    before = carried.verified.outcomes["elevation_from_m"].value
    assert before.state == ValueState.UNKNOWN
    protected = asyncio.run(journal.preserved_human_outcomes(request.scope))
    assert "elevation_from_m" in protected
    asyncio.run(journal.validate_request(request, model_settings_digest=digest(settings)))
    assembly = next(item for item in request.assemblies if str(item.field_key) == source_key)
    arguments = {"field_key": source_key, "event_id": assembly.event_id,
        "assembly_ids": [item.id for item in request.assemblies if item.event_id == assembly.event_id]}
    turns, unsafe_resolutions = [], []

    def respond(messages, _info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_elevation", "arguments": arguments})],
                usage=RequestUsage(input_tokens=1, output_tokens=1))
        if len(turns) == 2:
            result = next(part.content for message in messages for part in message.parts
                if isinstance(part, ToolReturnPart))
            rows = json.loads(result.candidate_json[0])["resolutions"]
            assert len(rows) == 4
            selected = [row for row in rows if FieldKey(row["field_key"]) in request.field_keys]
            if unsafe:
                unsafe_resolutions.extend(FieldResolution.model_validate(row) for row in selected)
            return ModelResponse(parts=[ToolCallPart("final_result", {
                "role": request.role, "resolutions": selected})],
                usage=RequestUsage(input_tokens=1, output_tokens=1))
        assert unsafe and len(turns) == 3
        retries = retry_parts(messages)
        assert retries and "specialist_output_has_unavailable_native_dependency" in str(retries[-1].content)
        assert "protected_native_dependency_unavailable:elevation_from_m" in str(retries[-1].content)
        assert "written assertion remains evidence" in str(retries[-1].content)
        corrected = [FieldResolution(field_key=key, work_state=WorkState.WAITING_POLICY,
            value=FieldValue(state=ValueState.UNRESOLVED),
            reason="protected_native_dependency_unavailable:elevation_from_m; written 1200 m is retained, "
                   "but its native From source is protected and has no genuine checkpoint pin") for key in request.field_keys]
        return ModelResponse(parts=[ToolCallPart("final_result", {
            "role": request.role, "resolutions": [row.model_dump(mode="json") for row in corrected]})],
            usage=RequestUsage(input_tokens=1, output_tokens=1))

    engine = build_research_engine(profile=carried.profile, requests={request.role: request},
        store=carried.store, scope=durable, lease=journal.lease, blobs=blobs,
        tool_broker=SourceBroker(SourceRegistry(())), bindings=bindings, settings=settings,
        source_pins={"registry_digest": request.prompt.source_registry_digest, "human_field_carry": contract_pin()},
        base_model_factory=lambda _request: FunctionModel(respond), actual_cost=lambda _response: 1)
    run = asyncio.run(engine.run())
    assert len(turns) == (3 if unsafe else 2)
    job = carried.store.job(durable)
    proof = read_accepted_checkpoint_proof(carried.store, durable, blobs, job["checkpoints"][0]["id"])
    [utility] = proof.acceptance.source_results
    assert len(json.loads(utility.candidate_json[0])["resolutions"]) == 4
    assert verify_local_utility_v2(request, utility).arguments == arguments

    def accept(resolutions):
        return AcceptedOutputProofV1(original_request=request, native_run_id=proof.acceptance.native_run_id,
            conversation_id=proof.acceptance.conversation_id, resolutions=resolutions, source_results=(utility,),
            effect_ids=proof.acceptance.effect_ids, model_settings_digest=digest(settings), **validation_boundary_pins())

    if unsafe:
        # This is the pre-fix seam: typed output acceptance passes, but the real
        # checkpoint fence has no native From sibling. Do not weaken that fence.
        unsafe_acceptance = accept(tuple(unsafe_resolutions))
        checkpoints = tuple(FieldCheckpoint(scope=request.scope, field_key=row.field_key, revision=1,
            resolution=row, prompt_digest=request.prompt.digest, model_settings_digest=digest(settings),
            source_registry_digest=request.prompt.source_registry_digest) for row in unsafe_resolutions)
        with pytest.raises(ValueError, match="accepted_checkpoint_sibling_invalid"):
            AcceptedCheckpointProofV1(acceptance=unsafe_acceptance, checkpoints=checkpoints)
        assert all(row.work_state == WorkState.WAITING_POLICY and row.value.state == ValueState.UNRESOLVED
                   and row.question is None and not row.dependencies for row in proof.acceptance.resolutions)

    acceptance = proof.acceptance
    checkpoints = run.checkpoints
    assert {row.field_key for row in checkpoints} == set(request.field_keys)
    assert FieldKey.ELEVATION_FROM_M not in {row.field_key for row in checkpoints}
    assert job["fields"]["elevation_from_m"]["locked"] is True
    assert job["fields"]["elevation_from_m"]["checkpoint"] is None
    assert proof.acceptance == acceptance
    assert {row.field_key: row for row in proof.checkpoints} == {row.field_key: row for row in checkpoints}
    assert proof.acceptance.source_results == (utility,)
    assert len(json.loads(proof.acceptance.source_results[0].candidate_json[0])["resolutions"]) == 4
    if not unsafe:
        assert all(row.resolution.work_state == WorkState.RESOLVED for row in checkpoints)
        native_from = next(row for row in checkpoints if row.field_key == FieldKey.ELEVATION_FROM_FT)
        for checkpoint in checkpoints:
            for pin in checkpoint.resolution.dependencies:
                assert pin.field_key == native_from.field_key and pin.revision == native_from.revision
                assert pin.digest == digest(native_from.resolution)
    assert asyncio.run(journal.preserved_human_outcomes(request.scope)) == protected
    current = verify(carried.case.repo, carried.case.current, carried.case.repo.graph_blobs)
    assert current.outcomes["elevation_from_m"].value == before


def test_interrupted_local_calculation_resumes_with_captured_model_replay_and_preserved_human(carried, tmp_path):
    """Actual engine/journal/model-effect recovery; local synthetic calculation.

    Cancellation occurs after pure calculation, before its tool result/final
    output is accepted. No provider send is uncertain and no hold is cleared.
    The restarted Agent restores the captured response frontier and reconstructs
    the exact utility with a fresh no-transport broker; no model is repeated.
    """
    request, journal, durable, blobs, bindings, settings = measurement_case(
        carried, tmp_path, source_key="elevation_from_ft", literal="6,400 ft")
    before = asyncio.run(journal.preserved_human_outcomes(request.scope))
    assembly = request.assemblies[0]
    arguments = {"field_key": "elevation_from_ft", "event_id": assembly.event_id,
        "assembly_ids": [item.id for item in request.assemblies if item.event_id == assembly.event_id]}
    calculated, dispatches = [], []
    broker = SourceBroker(SourceRegistry(()))

    class InterruptedCalculator:
        async def invoke_utility(self, *args):
            result = await broker.invoke_utility(*args)
            calculated.append(result)
            if len(calculated) == 1:
                raise asyncio.CancelledError
            return result

    def respond(messages, _info):
        dispatches.append(messages)
        if len(dispatches) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_elevation", "arguments": arguments})],
                usage=RequestUsage(input_tokens=1, output_tokens=1))
        assert len(dispatches) == 2 and not retry_parts(messages)
        result = next(part.content for message in messages for part in message.parts
            if isinstance(part, ToolReturnPart))
        rows = [row for row in json.loads(result.candidate_json[0])["resolutions"]
            if row["field_key"] in request.field_keys]
        return ModelResponse(parts=[ToolCallPart("final_result", {
            "role": request.role, "resolutions": rows})],
            usage=RequestUsage(input_tokens=1, output_tokens=1))

    def engine():
        return build_research_engine(profile=carried.profile, requests={request.role: request},
            store=carried.store, scope=durable, lease=journal.lease, blobs=blobs,
            tool_broker=InterruptedCalculator(), bindings=bindings, settings=settings,
            source_pins={"registry_digest": request.prompt.source_registry_digest,
                         "human_field_carry": contract_pin()},
            base_model_factory=lambda _request: FunctionModel(respond), actual_cost=lambda _response: 1)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(engine().run())
    assert not carried.store.job(durable)["checkpoints"]
    effects = carried.store._read(durable).state["effects"]
    assert len(effects) == 1 and {item["status"] for item in effects.values()} == {"completed"}
    assert len(dispatches) == len(calculated) == 1

    resumed = asyncio.run(engine().run())
    assert len(dispatches) == 2  # first captured response replayed without dispatch
    # Recovery reconstructs the interrupted pure result through a fresh
    # no-transport broker. The custom interrupted wrapper is not re-entered.
    assert len(calculated) == 1
    assert len(resumed.checkpoints) == 3
    assert all(row.resolution.work_state == WorkState.RESOLVED for row in resumed.checkpoints)
    assert FieldKey.ELEVATION_FROM_M not in {row.field_key for row in resumed.checkpoints}
    assert asyncio.run(journal.preserved_human_outcomes(request.scope)) == before
    effects = carried.store._read(durable).state["effects"]
    assert len(effects) == 2 and {item["status"] for item in effects.values()} == {"completed"}
    proof = read_accepted_checkpoint_proof(carried.store, durable, blobs,
        carried.store.job(durable)["checkpoints"][0]["id"])
    assert proof.acceptance.source_results == (calculated[0],)
    assert verify_local_utility_v2(request, calculated[0]).arguments == arguments
