"""Offline real Agent/journal recovery: retained From is not reopened for To.

SQLite, model replies and labels are synthetic. These are native checkpoint
proofs, not live provider, SQL Connect or museum scientific acceptance.
"""
import asyncio
from dataclasses import asdict, replace
import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.application.human_field_carry import contract_pin
from specimen_digitization.research_harness.accepted_output import read_accepted_checkpoint_proof
from specimen_digitization.research_harness.agents import specialist_output_schema_digest
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, DependencyPin, FieldKey, FieldResolution, SpecialistRequest,
    SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import temporal_resolutions
from specimen_digitization.research_harness.gateway import ModelBinding
from specimen_digitization.research_harness.initial_requests import NativeGenerationRequestFactory
from specimen_digitization.research_harness.journal import DurableResearchJournal
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from specimen_digitization.research_harness.persistence import ImmutableFileBlobs
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.runtime import build_research_engine, runtime_pins
from specimen_digitization.research_harness.sources import SourceBroker, SourceRegistry, local_settlement_result
from test_organiser_raw_reading_evidence import build, two_labels
from test_preserved_human_outcomes import carried  # noqa: F401 -- actual named-human fixture
from test_specialist_feedback import policy_output, retry_parts, tool_agent
from test_temporal_collecting_context import collecting_fixture
from test_organiser_raw_reading_evidence import request_for


def narrowed_case():
    built = collecting_fixture()
    request = request_for(built, SpecialistRole.TEMPORAL)
    assembly = next(item for item in request.assemblies if item.field_key == FieldKey.DATE_VISITED_FROM)
    event = next(item for item in request.events if item.id == assembly.event_id)
    base, _ = temporal_resolutions(request, event_id=event.id)
    pin = DependencyPin(field_key=FieldKey.DATE_VISITED_FROM, revision=7, digest=digest(base))
    narrowed = SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "field_keys": (FieldKey.DATE_VISITED_TO,), "field_revisions": {FieldKey.DATE_VISITED_TO: 0},
        "dependencies": (pin,)})
    return request, narrowed, event, base, pin


def test_to_only_utility_and_replay_consume_exact_native_source_without_reproposing_from():
    _, request, event, base, pin = narrowed_case()
    result = local_settlement_result(request, "settle_temporal", {
        "field_key": "date_visited_to", "event_id": event.id})
    rows = [FieldResolution.model_validate(row) for row in json.loads(result.candidate_json[0])["resolutions"]]
    assert rows[0] == base
    assert rows[1].dependencies == (pin,)
    assert rows[1].derivation.source_revision == 7
    assert verify_local_utility_v2(request, result).field_key == "date_visited_to"


@pytest.mark.parametrize("change", ("missing", "digest", "event", "evidence"))
def test_to_repair_refuses_missing_or_changed_consumed_evidence(change):
    _, request, event, _, pin = narrowed_case()
    data = request.model_dump(mode="json")
    if change == "missing":
        data["dependencies"] = ()
    elif change == "digest":
        data["dependencies"] = (pin.model_copy(update={"digest": digest("wrong source")}),)
    elif change == "event":
        event = event.model_copy(update={"id": "other-event"})
    else:
        data["events"] = [item.model_copy(update={"evidence_ids": (request.evidence[-1].id,)})
            if item.id == event.id else item for item in request.events]
    changed = SpecialistRequest.model_validate(data)
    with pytest.raises(ValueError):
        local_settlement_result(changed, "settle_temporal", {
            "field_key": "date_visited_to", "event_id": event.id})


def test_agent_invalid_date_is_corrected_to_exact_tool_output_before_acceptance():
    _, request, event, _, _ = narrowed_case()
    turns = []
    def respond(messages, _info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_temporal", "arguments": {"field_key": "date_visited_to", "event_id": event.id}})])
        result = next(part.content for message in messages for part in message.parts if isinstance(part, ToolReturnPart))
        row = next(item for item in json.loads(result.candidate_json[0])["resolutions"] if item["field_key"] == "date_visited_to")
        if len(turns) == 2:
            row["value"]["normalized"] = "1946-09-15"
        else:
            assert retry_parts(messages)
        return ModelResponse(parts=[ToolCallPart("final_result", {"role": request.role, "resolutions": [row]})])
    agent, deps = tool_agent(request, respond)
    output = agent.run_sync("Repair To only", deps=deps).output
    assert len(turns) == 3
    assert output.resolutions[0].value.normalized == "1946-09-14"


def test_absent_native_source_is_corrected_to_structured_unresolved_output():
    _, request, event, _, _ = narrowed_case()
    request = SpecialistRequest.model_validate({**request.model_dump(mode="json"), "dependencies": ()})
    turns = []
    def respond(messages, _info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_temporal", "arguments": {"field_key": "date_visited_to", "event_id": event.id}})])
        assert retry_parts(messages)
        output = policy_output(request)
        row = output.resolutions[0].model_copy(update={
            "reason": "protected_native_dependency_unavailable:date_visited_from; written date retained"})
        return ModelResponse(parts=[ToolCallPart("final_result", {
            "role": request.role, "resolutions": [row.model_dump(mode="json")]})])
    agent, deps = tool_agent(request, respond)
    output = agent.run_sync("Repair To with protected From", deps=deps).output
    [row] = output.resolutions
    assert row.field_key == FieldKey.DATE_VISITED_TO and row.work_state == WorkState.WAITING_POLICY
    assert row.derivation is None and row.dependencies == () and row.value.normalized is None


def native_case(carried, tmp_path, *, protect_from=False):
    if protect_from:
        carried.case.review("date_visited_from", state="unknown", reason="The date is not yet verified")
        carried.verified = carried.case.reprocess()
    durable = replace(carried.durable, job_id=carried.durable.job_id + "-temporal-recovery")
    scope = carried.scope.model_copy(update={"job_id": durable.job_id,
        "input_digest": carried.verified.snapshot_sha256})
    text = "Collected: IX-14-46"
    built = build(two_labels(a=text), [("date_visited_from", name, "IX-14-46", text) for name in ("2A", "2B")])
    fragments, events, assemblies, evidence, decisions, candidates = NativeGenerationRequestFactory._build_graph(built.specimen, scope)
    role, keys = SpecialistRole.TEMPORAL, ROLE_FIELDS[SpecialistRole.TEMPORAL]
    request = SpecialistRequest(scope=scope, role=role, field_keys=keys,
        prompt=resolve_prompt(role, profile_digest=scope.profile_digest, source_registry_digest="b" * 64,
            toolset_digest="c" * 64, model_route="harness-deepseek", output_schema_digest=specialist_output_schema_digest()),
        fragments=fragments, events=events, assemblies=assemblies, evidence=evidence,
        accepted_decisions=decisions, organiser_candidates=tuple(c for c in candidates if c.field_key in keys),
        field_revisions={key: 0 for key in keys})
    bindings = {role: ModelBinding("harness-deepseek", "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepinfra", 128, 10, "offline-native-temporal-v1")}
    settings = {"max_tokens": 128}
    pins = runtime_pins(carried.profile, {role: request},
        model={key: {"route": value.route_id, **asdict(value)} for key, value in bindings.items()}, settings=settings)
    pins = replace(pins, sources={**pins.sources, "human_field_carry": contract_pin()})
    carried.backend.grant(durable)
    carried.store.create_job(durable, pins, list(ALL_FIELDS), record_revision=carried.case.current.version,
        human_locks={key: value.proof_digest for key, value in carried.verified.outcomes.items()},
        preserved_human_outcomes={key: value.model_dump(mode="json") for key, value in carried.verified.outcomes.items()})
    blobs = ImmutableFileBlobs(tmp_path / "temporal-native")
    journal = DurableResearchJournal(carried.store, durable, carried.store.claim(durable, "dates-first-window"), blobs)
    return request, journal, durable, blobs, bindings, settings


def run_native(carried, request, journal, durable, blobs, bindings, settings, respond, *, broker=None):
    engine = build_research_engine(profile=carried.profile, requests={request.role: request},
        store=carried.store, scope=durable, lease=journal.lease, blobs=blobs,
        tool_broker=broker or SourceBroker(SourceRegistry(())), bindings=bindings, settings=settings,
        source_pins={"registry_digest": request.prompt.source_registry_digest, "human_field_carry": contract_pin()},
        base_model_factory=lambda _request: FunctionModel(respond), actual_cost=lambda _response: 1)
    return asyncio.run(engine.run())


def respond_with_settlement(request, turns, *, target):
    event = next(item for item in request.events if item.status == "accepted" and item.kind == "collecting")
    def respond(messages, _info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_temporal", "arguments": {"field_key": str(target), "event_id": event.id}})],
                usage=RequestUsage(input_tokens=1, output_tokens=1))
        assert not retry_parts(messages)
        result = next(part.content for message in messages for part in message.parts if isinstance(part, ToolReturnPart))
        rows = [row for row in json.loads(result.candidate_json[0])["resolutions"] if row["field_key"] == target]
        return ModelResponse(parts=[ToolCallPart("final_result", {"role": request.role, "resolutions": rows})],
            usage=RequestUsage(input_tokens=1, output_tokens=1))
    return respond


def test_new_worker_resumes_to_from_real_accepted_checkpoint_without_reopening_source(carried, tmp_path):
    request, journal, durable, blobs, bindings, settings = native_case(carried, tmp_path)
    from_only = SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "field_keys": (FieldKey.DATE_VISITED_FROM,), "field_revisions": {FieldKey.DATE_VISITED_FROM: 0}})
    first_turns = []
    run_native(carried, from_only, journal, durable, blobs, bindings, settings,
        respond_with_settlement(request, first_turns, target=FieldKey.DATE_VISITED_FROM))
    before = carried.store.job(durable)
    source_row = before["fields"]["date_visited_from"]["checkpoint"]
    assert len(first_turns) == 2 and source_row["revision"] == 1
    assert before["fields"]["date_visited_to"]["revision"] == 0
    carried.store.release(durable, journal.lease)
    resumed = DurableResearchJournal(carried.store, durable, carried.store.claim(durable, "dates-resumed-window"), blobs)
    to_only = SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "field_keys": (FieldKey.DATE_VISITED_TO,), "field_revisions": {FieldKey.DATE_VISITED_TO: 0}})
    turns = []
    run_native(carried, to_only, resumed, durable, blobs, bindings, settings,
        respond_with_settlement(request, turns, target=FieldKey.DATE_VISITED_TO))
    job = carried.store.job(durable)
    assert len(turns) == 2
    assert job["fields"]["date_visited_from"]["checkpoint"] == source_row
    end_row = job["fields"]["date_visited_to"]["checkpoint"]
    proof = read_accepted_checkpoint_proof(carried.store, durable, blobs, end_row["id"])
    [pin] = proof.acceptance.original_request.dependencies
    assert pin.field_key == FieldKey.DATE_VISITED_FROM and pin.revision == 1
    source_proof = read_accepted_checkpoint_proof(carried.store, durable, blobs, source_row["id"])
    assert pin.digest == digest(source_proof.checkpoints[0].resolution)
    [end] = proof.checkpoints
    assert end.resolution.value.normalized == "1946-09-14"
    assert end.resolution.dependencies == (pin,) and end.resolution.derivation.source_revision == 1
    assert end_row["dependencies"] == {"date_visited_from": 1}
    assert verify_local_utility_v2(proof.acceptance.original_request, proof.acceptance.source_results[0]).field_key == "date_visited_to"


def test_actual_named_human_from_is_preserved_while_to_stays_policy_blocked(carried, tmp_path):
    request, journal, durable, blobs, bindings, settings = native_case(carried, tmp_path, protect_from=True)
    to_only = SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "field_keys": (FieldKey.DATE_VISITED_TO,), "field_revisions": {FieldKey.DATE_VISITED_TO: 0}})
    before = carried.store.job(durable)["preserved_human_outcomes"]["date_visited_from"]
    turns = []
    event = next(item for item in request.events if item.status == "accepted" and item.kind == "collecting")
    def respond(messages, _info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_temporal", "arguments": {"field_key": "date_visited_to", "event_id": event.id}})],
                usage=RequestUsage(input_tokens=1, output_tokens=1))
        assert retry_parts(messages)
        resolution = FieldResolution(field_key=FieldKey.DATE_VISITED_TO,
            work_state=WorkState.WAITING_POLICY, value=FieldValue(state=ValueState.UNRESOLVED),
            reason="protected_native_dependency_unavailable:date_visited_from; written date retained")
        return ModelResponse(parts=[ToolCallPart("final_result", {
            "role": request.role, "resolutions": [resolution.model_dump(mode="json")]})],
            usage=RequestUsage(input_tokens=1, output_tokens=1))
    run_native(carried, to_only, journal, durable, blobs, bindings, settings, respond)
    job = carried.store.job(durable)
    assert len(turns) == 2
    assert job["preserved_human_outcomes"]["date_visited_from"] == before
    assert job["fields"]["date_visited_from"]["locked"] is True
    assert job["fields"]["date_visited_from"]["checkpoint"] is None
    row = job["fields"]["date_visited_to"]["checkpoint"]
    proof = read_accepted_checkpoint_proof(carried.store, durable, blobs, row["id"])
    assert proof.acceptance.original_request.dependencies == ()
    assert proof.checkpoints[0].resolution.work_state == WorkState.WAITING_POLICY
    assert proof.checkpoints[0].resolution.derivation is None


def test_interrupted_local_helper_preserves_accepted_source_and_resumes_under_new_lease(carried, tmp_path):
    request, journal, durable, blobs, bindings, settings = native_case(carried, tmp_path)
    source = SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "field_keys": (FieldKey.DATE_VISITED_FROM,), "field_revisions": {FieldKey.DATE_VISITED_FROM: 0}})
    run_native(carried, source, journal, durable, blobs, bindings, settings,
        respond_with_settlement(request, [], target=FieldKey.DATE_VISITED_FROM))
    source_row = carried.store.job(durable)["fields"]["date_visited_from"]["checkpoint"]
    target = SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "field_keys": (FieldKey.DATE_VISITED_TO,), "field_revisions": {FieldKey.DATE_VISITED_TO: 0}})
    class InterruptedBroker(SourceBroker):
        async def invoke_utility(self, *_args, **_kwargs):
            raise asyncio.CancelledError("synthetic interruption before local parser returned")
    with pytest.raises(asyncio.CancelledError):
        run_native(carried, target, journal, durable, blobs, bindings, settings,
            respond_with_settlement(request, [], target=FieldKey.DATE_VISITED_TO),
            broker=InterruptedBroker(SourceRegistry(())))
    interrupted = carried.store.job(durable)
    assert interrupted["fields"]["date_visited_from"]["checkpoint"] == source_row
    assert interrupted["fields"]["date_visited_to"]["checkpoint"] is None
    # The model turn completed, and the interrupted helper is local. No unknown
    # external send is cleared to obtain this fresh lease.
    carried.store.release(durable, journal.lease)
    resumed = DurableResearchJournal(carried.store, durable, carried.store.claim(durable, "dates-after-interruption"), blobs)
    turns = []
    run_native(carried, target, resumed, durable, blobs, bindings, settings,
        respond_with_settlement(request, turns, target=FieldKey.DATE_VISITED_TO))
    job = carried.store.job(durable)
    assert job["fields"]["date_visited_from"]["checkpoint"] == source_row
    assert job["fields"]["date_visited_to"]["work_state"] == "resolved"


def test_changed_native_revision_fails_before_model_dispatch(carried, tmp_path):
    request, journal, durable, blobs, bindings, settings = native_case(carried, tmp_path)
    source = SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "field_keys": (FieldKey.DATE_VISITED_FROM,), "field_revisions": {FieldKey.DATE_VISITED_FROM: 0}})
    run_native(carried, source, journal, durable, blobs, bindings, settings,
        respond_with_settlement(request, [], target=FieldKey.DATE_VISITED_FROM))
    source_row = carried.store.job(durable)["fields"]["date_visited_from"]["checkpoint"]
    source_proof = read_accepted_checkpoint_proof(carried.store, durable, blobs, source_row["id"])
    target = SpecialistRequest.model_validate({**request.model_dump(mode="json"),
        "field_keys": (FieldKey.DATE_VISITED_TO,), "field_revisions": {FieldKey.DATE_VISITED_TO: 0},
        "dependencies": (DependencyPin(field_key=FieldKey.DATE_VISITED_FROM, revision=2,
                                      digest=digest(source_proof.checkpoints[0].resolution)),)})
    turns = []
    result = run_native(carried, target, journal, durable, blobs, bindings, settings,
        respond_with_settlement(request, turns, target=FieldKey.DATE_VISITED_TO))
    job = carried.store.job(durable)
    assert turns == [] and job["fields"]["date_visited_from"]["checkpoint"] == source_row
    assert result.fields[FieldKey.DATE_VISITED_TO].work_state == WorkState.OPERATIONAL_FAILED
    assert job["fields"]["date_visited_to"]["work_state"] == "pending"
    assert job["fields"]["date_visited_to"]["checkpoint"] is None
