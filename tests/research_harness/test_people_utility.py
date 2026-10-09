"""Real people tool/agent/replay controls with captured synthetic label input.

No external person source, paid model, native SQL or live publication is claimed.
"""

import asyncio
import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart

from test_organiser_raw_reading_evidence import request_for
from test_people_evidence import recovery_fixture
from test_specialist_feedback import retry_parts, tool_agent

from specimen_digitization.application.domain import ValueState
from specimen_digitization.research_harness.accepted_output import (
    AcceptedOutputProofV1, validation_boundary_pins,
)
from specimen_digitization.research_harness.agents import SpecialistOutput, utility_model_view
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import (
    EventKind, FieldKey, FieldResolution, LookupStatus, SourceCoverageState,
    SourceQuery, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import missing_irn_resolution, validate_resolution
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from specimen_digitization.research_harness.sources import SourceBroker, SourceRegistry, insects_registry


def collector_request():
    built = recovery_fixture()
    request = request_for(built, SpecialistRole.PARTIES)
    assembly = next(item for item in request.assemblies if item.field_key == FieldKey.COLLECTORS)
    return request, {"field_key": "collectors", "event_id": assembly.event_id}


def settle(request, arguments):
    return asyncio.run(SourceBroker(SourceRegistry(())).invoke_utility(
        request, "settle_collectors", arguments))


def test_actual_people_agent_invokes_settlement_and_copies_exact_compact_result_in_two_turns():
    request, arguments = collector_request()
    turns = []

    def respond(messages, info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {
                "tool_id": "settle_collectors", "arguments": arguments})])
        assert not retry_parts(messages)
        [view] = [part.content for message in messages for part in message.parts
            if isinstance(part, ToolReturnPart)]
        payload = json.loads(view.candidate_json[0])
        assert len(payload["resolutions"]) == 1
        assert payload["resolutions"][0]["field_key"] == "collectors"
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "role": str(request.role), "resolutions": [*payload["resolutions"],
                missing_irn_resolution().model_dump(mode="json")],
        })])

    agent, deps = tool_agent(request, respond)
    run = agent.run_sync("Resolve retained people evidence", deps=deps,
        conversation_id="offline-people-utility")
    assert len(turns) == 2 and isinstance(run.output, SpecialistOutput)
    [result] = deps.tool_results[request.role]
    [collector] = [item for item in run.output.resolutions if item.field_key == FieldKey.COLLECTORS]
    [exact] = [FieldResolution.model_validate(item)
        for item in json.loads(result.candidate_json[0])["resolutions"]]
    assert collector == exact
    assert collector.value.literal == collector.value.normalized == "J. Smith & A. Brown"
    assert collector.assembly_ids and collector.event_id == arguments["event_id"]
    assert collector.value.verbatim_by_observation and collector.value.input_source_by_observation
    assert collector.value.settled_observation_ids and collector.value.evidence_ids
    assert collector.value.authority_id is None
    assert validate_resolution(request, collector) == collector
    assert run.output.resolutions[-1] == missing_irn_resolution()
    assert result.receipt is None and not result.evidence
    view = utility_model_view(result)
    assert len(view.candidate_json[0]) < len(result.candidate_json[0])
    restored = FieldResolution.model_validate(json.loads(view.candidate_json[0])["resolutions"][0])
    assert restored == exact
    replay = verify_local_utility_v2(request, result)
    assert replay.as_receipt()["arguments"] == arguments
    assert replay.result_digest == digest(result) and replay.original_request_digest == digest(request)
    accepted = AcceptedOutputProofV1(original_request=request, native_run_id=run.run_id,
        conversation_id=run.conversation_id, resolutions=run.output.resolutions,
        source_results=(result,), effect_ids=(), model_settings_digest=digest("offline people utility"),
        **validation_boundary_pins())
    assert accepted.resolutions == run.output.resolutions and accepted.source_results == (result,)


@pytest.mark.parametrize("mutation", ("value", "evidence", "version", "request_role", "request_event"))
def test_people_utility_replay_refuses_tampered_result_or_original_input(mutation):
    request, arguments = collector_request()
    result = settle(request, arguments)
    if mutation in {"value", "evidence"}:
        payload = json.loads(result.candidate_json[0])
        if mutation == "value":
            payload["resolutions"][0]["value"]["normalized"] = "Invented Person"
        else:
            payload["resolutions"][0]["evidence_ids"] = ["invented-evidence"]
        result = result.model_copy(update={"candidate_json": (json.dumps(payload),)})
    elif mutation == "version":
        result = result.model_copy(update={"coverage": result.coverage.model_copy(update={
            "source_version": "unreviewed-people-settlement"})})
    elif mutation == "request_role":
        request = request.model_copy(update={"role": SpecialistRole.TAXONOMY})
    else:
        request = request.model_copy(update={"events": tuple(item.model_copy(update={
            "kind": EventKind.DETERMINATION}) if item.id == arguments["event_id"] else item
            for item in request.events)})
    with pytest.raises(PublicationUnavailable, match="canonical_local_utility_unproved"):
        verify_local_utility_v2(request, result)


@pytest.mark.parametrize("fault", ("role", "field", "unknown_field", "event", "event_type",
    "extra_text", "missing_event", "protected_field", "wrong_event_kind"))
def test_people_settlement_refuses_arguments_outside_its_immutable_owned_input(fault):
    request, arguments = collector_request()
    if fault == "role":
        request = request.model_copy(update={"role": SpecialistRole.COLLECTION})
    elif fault == "field":
        arguments = {**arguments, "field_key": "identified_by_irn"}
    elif fault == "unknown_field":
        arguments = {**arguments, "field_key": "person_name"}
    elif fault == "event":
        arguments = {**arguments, "event_id": "invented-event"}
    elif fault == "event_type":
        arguments = {**arguments, "event_id": {"name": "Jane Smith"}}
    elif fault == "extra_text":
        arguments = {**arguments, "text": "Jane Smith"}
    elif fault == "missing_event":
        arguments = {"field_key": "collectors"}
    elif fault == "protected_field":
        request = request.model_copy(update={"field_keys": (FieldKey.IDENTIFIED_BY_IRN,)})
    else:
        request = request.model_copy(update={"events": tuple(item.model_copy(update={
            "kind": EventKind.PREPARATION}) if item.id == arguments["event_id"] else item
            for item in request.events)})
    with pytest.raises(ValueError):
        settle(request, arguments)


def test_unqualified_eparties_source_sends_no_http_and_irn_stays_honest_nonblocking_unknown(monkeypatch):
    request, _ = collector_request()
    registry = insects_registry()
    request = request.model_copy(update={"prompt": request.prompt.model_copy(update={
        "source_registry_digest": registry.digest})})
    sends = []

    def forbidden(*args, **kwargs):
        sends.append((args, kwargs))
        pytest.fail("Unqualified people source attempted HTTP")

    import httpx
    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)
    broker = SourceBroker(registry)
    result = asyncio.run(broker.query_source(request, SourceQuery(source_id="field_museum_emudata",
        field_key=FieldKey.IDENTIFIED_BY_IRN, query_text="Jane Smith")))
    assert not sends
    assert result.status == LookupStatus.POLICY
    assert result.coverage.state == SourceCoverageState.UNQUALIFIED
    assert not result.coverage.exact_join_attempted and not result.coverage.exact_join_proven
    assert result.receipt is None and not result.candidate_json and not result.evidence
    irn = validate_resolution(request, missing_irn_resolution(), (result,))
    assert irn.work_state == WorkState.NONBLOCKING_EXCEPTION and irn.value.state == ValueState.UNKNOWN
    assert irn.value.literal is irn.value.parsed is irn.value.normalized is irn.value.authority_id is None
    assert irn.question is None and irn.exception.dependency == "qualified_emu_determiner_eparties_identity"
