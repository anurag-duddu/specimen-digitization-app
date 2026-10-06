"""Offline regression of retained failures; no provider or scientific admission."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.application.lookup import COL_XR, _shape_ok, row_one, scientific_name
from specimen_digitization.research_harness.agents import ResearchDeps, SpecialistHarness, SpecialistOutput, utility_model_view
from specimen_digitization.research_harness.contracts import (
    ROLE_FIELDS, EvidenceItem, EventHypothesis, EventKind, FieldKey, FieldResolution,
    ResearchScope, SourceFragment, SourceQuery, SpecialistRequest, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.evidence import assemble_field, elevation_resolutions, settle_elevation, validate_resolution
from specimen_digitization.research_harness.local_utility_proof_v2 import verify_local_utility_v2
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.sources import (
    FixtureSourceTransport, SourceBroker, SourceRegistry, insects_registry, local_settlement_result,
)
from test_geolocate_validator import YEPOCAPA, candidates, geography_request, lookup


def graph_request(role, key, text):
    scope = ResearchScope(organization_id="org", collection_id="insects", specimen_id="synthetic",
        job_id="job", generation=1, input_digest=digest("input"), profile_digest=digest("profile"), sensitive=False)
    fragment = SourceFragment(id="reading", scope=scope, asset_id="asset", asset_generation="1",
        asset_digest=digest("asset"), label_id="label", region_id="label", observation_id="raw-reading",
        reader="reader", model_id="fixture", prompt_digest=digest("reader prompt"), observation_text=text,
        observation_digest=hashlib.sha256(text.encode()).hexdigest(), start=0, end=len(text), literal=text, order=0)
    evidence = EvidenceItem(id="event-evidence", kind="literal", source_id="fixture", locator="fixture://label",
        response_digest=digest(text), source_version="fixture-v1", publisher_assertion_id="fixture-only", excerpt=text)
    event = EventHypothesis(id="accepted-event", scope=scope, kind=EventKind.COLLECTING,
        fragment_ids=(fragment.id,), evidence_ids=(evidence.id,), reason="Explicit synthetic annotation",
        status="accepted", validator_version="fixture-v1")
    assembly = assemble_field(assembly_id="accepted-assembly", scope=scope, field_key=key,
        fragments=(fragment,), event=event, assertion_kind="complete")
    prompt = resolve_prompt(role, profile_digest=scope.profile_digest, source_registry_digest=digest("registry"),
        toolset_digest=digest("tools"), model_route="harness-deepseek", output_schema_digest=digest("schema"))
    return SpecialistRequest(scope=scope, role=role, field_keys=ROLE_FIELDS[role], prompt=prompt,
        fragments=(fragment,), events=(event,), assemblies=(assembly,), evidence=(evidence,),
        field_revisions={field:0 for field in ROLE_FIELDS[role]})


def policy_output(request):
    return SpecialistOutput(role=request.role, resolutions=tuple(FieldResolution(field_key=key,
        work_state=WorkState.WAITING_POLICY, value=FieldValue(state=ValueState.UNRESOLVED),
        reason="missing_policy:unstructured_label_event_unqualified") for key in request.field_keys))


def tool_agent(request, respond, *, broker=None, output_type=SpecialistOutput):
    agent = Agent(FunctionModel(respond), name=request.role.value, deps_type=ResearchDeps,
        output_type=output_type, retries=1)
    SpecialistHarness._register_tools(agent)
    if output_type is SpecialistOutput:
        SpecialistHarness._register_output_validation(agent)
    deps = ResearchDeps({request.role:request}, broker or SourceBroker(SourceRegistry(())))
    return agent, deps


def retry_parts(messages):
    return [part for message in messages for part in message.parts if isinstance(part, RetryPromptPart)]


def test_collector_event_is_correctable_but_never_settles_a_date():
    request = graph_request(SpecialistRole.TEMPORAL, FieldKey.COLLECTORS, "R.D. Mitchell")
    turns = []
    def respond(messages, info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {"tool_id":"settle_temporal",
                "arguments":{"field_key":"date_visited_from", "event_id":"accepted-event"}})])
        retries = retry_parts(messages)
        assert len(retries) == 1 and "research_utility_invalid_input" in retries[0].content
        assert "No written" not in retries[0].content  # Sanitized, no private exception/body.
        return ModelResponse(parts=[ToolCallPart("final_result", policy_output(request).model_dump(mode="json"))])
    agent, deps = tool_agent(request, respond)
    output = agent.run_sync("go", deps=deps).output
    assert len(turns) == 2 and len(output.resolutions) == 3
    assert all(r.work_state == WorkState.WAITING_POLICY and r.value.literal is None
        and r.value.parsed is None and r.value.century_rule is None for r in output.resolutions)
    assert not deps.tool_results


def test_repeated_invalid_utility_stops_at_existing_one_retry():
    request = graph_request(SpecialistRole.TEMPORAL, FieldKey.COLLECTORS, "Collector")
    turns = []
    def respond(messages, info):
        turns.append(messages)
        return ModelResponse(parts=[ToolCallPart("invoke_utility", {"tool_id":"settle_temporal",
            "arguments":{"field_key":"date_visited_from", "event_id":"accepted-event"}})])
    agent, deps = tool_agent(request, respond)
    with pytest.raises(UnexpectedModelBehavior, match="max retries count of 1"):
        agent.run_sync("go", deps=deps)
    assert len(turns) == 2 and not deps.tool_results


def test_unexpected_utility_failure_remains_fatal_and_private():
    request = graph_request(SpecialistRole.TEMPORAL, FieldKey.COLLECTORS, "Collector")
    class BrokenBroker:
        async def invoke_utility(self, *args):
            raise RuntimeError("PRIVATE infrastructure failure")
    turns = []
    def respond(messages, info):
        turns.append(messages)
        return ModelResponse(parts=[ToolCallPart("invoke_utility", {"tool_id":"settle_temporal", "arguments":{}})])
    agent, deps = tool_agent(request, respond, broker=BrokenBroker())
    with pytest.raises(RuntimeError, match="^research_utility_tool_failed$"):
        agent.run_sync("go", deps=deps)
    assert len(turns) == 1 and not deps.tool_results


def test_compact_elevation_result_roundtrips_every_exact_scientific_field():
    request = graph_request(SpecialistRole.MEASUREMENT, FieldKey.ELEVATION_FROM_FT, "4800 ft")
    result = local_settlement_result(request, "settle_elevation", {"field_key":"elevation_from_ft",
        "event_id":"accepted-event", "assembly_ids":["accepted-assembly"]})
    view = utility_model_view(result)
    expected = elevation_resolutions(settle_elevation(request, assembly_ids=("accepted-assembly",), source_revision=0))
    complete = json.dumps({"resolutions":[r.model_dump(mode="json") for r in expected]}, separators=(",",":"))
    restored = SpecialistOutput.model_validate({"role":request.role, **json.loads(view.candidate_json[0])})
    assert restored.resolutions == expected and len(restored.resolutions) == 4
    assert result.candidate_json[0] == json.dumps(json.loads(complete), sort_keys=True, separators=(",",":"))
    assert verify_local_utility_v2(request, result).result_digest == digest(result)
    assert len(view.candidate_json[0]) < len(complete) * .8
    for resolution in restored.resolutions:
        assert validate_resolution(request, resolution) == resolution
        assert resolution.evidence_ids and resolution.assembly_ids
        assert resolution.value.evidence_relations and resolution.value.verbatim_by_observation
        if resolution.value_layer == "derived":
            assert resolution.derivation and resolution.derivation.source_digest and resolution.dependencies


def test_agent_copies_compact_utility_into_real_four_field_final_output():
    request = graph_request(SpecialistRole.MEASUREMENT, FieldKey.ELEVATION_FROM_FT, "4800 ft")
    turns = []
    def respond(messages, info):
        turns.append(messages)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("invoke_utility", {"tool_id":"settle_elevation",
                "arguments":{"field_key":"elevation_from_ft", "event_id":"accepted-event",
                             "assembly_ids":["accepted-assembly"]}})])
        assert not retry_parts(messages)
        tool_return = next(part for message in messages for part in message.parts if isinstance(part, ToolReturnPart))
        result = tool_return.content
        return ModelResponse(parts=[ToolCallPart("final_result", {"role":request.role,
            **json.loads(result.candidate_json[0])})])
    agent, deps = tool_agent(request, respond)
    output = agent.run_sync("go", deps=deps).output
    expected = elevation_resolutions(settle_elevation(request, assembly_ids=("accepted-assembly",), source_revision=0))
    assert len(turns) == 2 and output.resolutions == expected
    assert len(deps.tool_results[request.role]) == 1
    retained = deps.tool_results[request.role][0]
    assert verify_local_utility_v2(request, retained).result_digest == digest(retained)
    assert retained.candidate_json[0] == json.dumps({"resolutions":[r.model_dump(mode="json") for r in expected]},
        sort_keys=True, separators=(",",":"))


@pytest.mark.parametrize(("role", "key", "text", "tool"), (
    (SpecialistRole.MEASUREMENT, FieldKey.ELEVATION_FROM_FT, "4800 ft", "settle_elevation"),
    (SpecialistRole.TEMPORAL, FieldKey.DATE_VISITED_FROM, "1948-04-24", "settle_temporal"),
))
def test_original_utility_proof_bytes_survive_model_presentation(role, key, text, tool):
    request = graph_request(role, key, text)
    arguments = {"field_key":str(key), "event_id":"accepted-event"}
    if tool == "settle_elevation":
        arguments["assembly_ids"] = ["accepted-assembly"]
    result = local_settlement_result(request, tool, arguments)
    original_json = result.model_dump_json()
    original_digest = digest(result)
    original_proof = verify_local_utility_v2(request, result)
    view = utility_model_view(result)
    assert view != result and view.coverage == result.coverage
    assert result.model_dump_json() == original_json and digest(result) == original_digest
    assert verify_local_utility_v2(request, result) == original_proof
    assert original_proof.utility_version == "deterministic-settlement-v1"
    assert original_proof.result_digest == original_digest and original_proof.arguments == arguments
    # The model's faithful presentation is never substituted for the exact
    # authoritative result in an accepted proof or native materialization.
    with pytest.raises(PublicationUnavailable, match="canonical_local_utility_unproved"):
        verify_local_utility_v2(request, view)
    altered = json.loads(result.candidate_json[0])
    altered["resolutions"][0]["value"]["parsed"] = "altered scientific value"
    tampered = result.model_copy(update={"candidate_json":(json.dumps(altered, sort_keys=True, separators=(",",":")),)})
    with pytest.raises(PublicationUnavailable, match="canonical_local_utility_unproved"):
        verify_local_utility_v2(request, tampered)


def test_exact_source_value_feedback_corrects_without_relaxing_deciding_evidence():
    key = FieldKey.PRECISE_LOCATION
    request = geography_request().model_copy(update={"field_keys":(key,)})
    source = lookup("yepocapa-modern.json", key, YEPOCAPA, "Yepocapa", request=request)
    candidate = candidates(source)[0]
    ids = tuple(e.id for e in source.evidence)
    value = FieldValue(state=ValueState.SUPPORTED, normalized=candidate["value"], authority_id=candidate["authority_id"],
        evidence_ids=list(ids), evidence_relations=dict.fromkeys(ids,"supports"))
    good = FieldResolution(field_key=key, work_state=WorkState.RESOLVED, value=value,
        value_layer="settled", evidence_ids=ids, reason="Exact recorded source candidate")
    bad = good.model_copy(update={"value":value.model_copy(update={"normalized":"different place"})})
    turns = []
    def respond(messages, info):
        turns.append(messages)
        if len(turns) == 2:
            feedback = retry_parts(messages)[-1].content
            assert "field=precise_location" in feedback and "exact_source_candidate_required" in feedback
        return ModelResponse(parts=[ToolCallPart("final_result", SpecialistOutput(role=request.role,
            resolutions=(bad if len(turns)==1 else good,)).model_dump(mode="json"))])
    agent, deps = tool_agent(request, respond)
    deps.tool_results[request.role] = [source]
    assert agent.run_sync("go", deps=deps).output.resolutions == (good,)
    assert len(turns) == 2


def test_recorded_gbif_v2_series_zoology_is_documented_not_malformed():
    # Retained public provider body plus the repository's trailing newline;
    # removing that one fixture newline restores the exact captured bytes.
    raw = (Path(__file__).parent / "fixtures/production_e2e/gbif-series-zoology.json").read_bytes().removesuffix(b"\n")
    assert hashlib.sha256(raw).hexdigest() == "17bb6e469725c6260fe1b2e41205557f537cfe5ba439c67798021e87a20d661e"  # pragma: allowlist secret
    payload = json.loads(raw)
    assert _shape_ok(payload)
    assert row_one(scientific_name("Epipocus"), payload["usage"], payload["classification"], payload["diagnostics"]["alternatives"])
    unknown = copy.deepcopy(payload)
    unknown["classification"][7]["rank"] = "UNREVIEWED_FUTURE_RANK"
    assert not _shape_ok(unknown)


def test_actual_gbif_adapter_retains_candidate_without_claiming_label_settlement():
    request = graph_request(SpecialistRole.TAXONOMY, FieldKey.COLLECTORS, "Collector")
    raw = (Path(__file__).parent / "fixtures/production_e2e/gbif-series-zoology.json").read_bytes().removesuffix(b"\n")
    calls = []
    async def read(url, policy):
        calls.append(url)
        return 200, raw
    registry = insects_registry()
    broker = SourceBroker(registry, transport=FixtureSourceTransport(read))
    policy = registry.get("gbif").model_copy(update={"source_release":f"col-xr:{COL_XR}"})
    result = asyncio.run(broker._execute(policy, request,
        SourceQuery(source_id="gbif", field_key=FieldKey.TAXON, query_text="Epipocus")))
    assert len(calls) == 1 and "/v2/species/match?" in calls[0]
    assert result.status == LookupStatus.SUCCESS
    candidate = json.loads(result.candidate_json[0])
    assert candidate["authority_id"].endswith(":KV9P4") and candidate["rank"] == "GENUS"
    assert candidate["authority_role"] == "decides" and candidate["input_literal"] == "Epipocus"
    # A parsed source assertion still needs durable capture, reader provenance,
    # and full specialist acceptance; this method cannot settle the label.
    assert result.receipt is None and request.assemblies[0].field_key == FieldKey.COLLECTORS
