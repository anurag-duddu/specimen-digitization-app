"""Offline correction of refused geography history; no private journal copies."""

import asyncio
import json

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart

from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.contracts import (
    FieldKey, FieldResolution, SourceCoverageState, WorkState,
)
from specimen_digitization.research_harness.evidence import EvidenceError, validate_resolution
from specimen_digitization.research_harness.sources import (
    FixtureSourceTransport, SourceBroker,
)
from test_geolocate_validator import (
    MCKINLEY, MCKINLEY_LABEL, REGISTRY, assembled_request, lookup, query, question,
)
from test_specialist_feedback import retry_parts, tool_agent

KEY = FieldKey.PRECISE_LOCATION


def history():
    request = assembled_request(MCKINLEY_LABEL).model_copy(update={"field_keys": (KEY,)})

    async def no_effect(*_):
        raise AssertionError("A refused argument cannot dispatch or send a provider request")

    broker = SourceBroker(REGISTRY, transport=FixtureSourceTransport(no_effect), effect_dispatch=no_effect)
    refused = asyncio.run(broker.query_source(request,
        query(KEY, {**MCKINLEY, "locality": "E. slope Mt. McKinley"}, MCKINLEY_LABEL)))
    corrected = lookup("mckinley-modern.json", KEY, MCKINLEY, MCKINLEY_LABEL, request)
    assert refused.status == LookupStatus.POLICY
    assert refused.coverage.state == SourceCoverageState.UNQUALIFIED and refused.receipt is None
    assert corrected.status == LookupStatus.NO_MATCH and corrected.receipt.effect_status == "completed"
    return request, refused, corrected


def human_output(request, result):
    asked = question(result, KEY, "scoped_absence")
    return SpecialistOutput(role=request.role, resolutions=(FieldResolution(field_key=KEY,
        work_state=WorkState.WAITING_HUMAN, value=FieldValue(state=ValueState.UNRESOLVED,
        literal=MCKINLEY_LABEL), question=asked, reason="Recorded source did not match the label place"),))


def source_output(request):
    return SpecialistOutput(role=request.role, resolutions=(FieldResolution(field_key=KEY,
        work_state=WorkState.WAITING_SOURCE, value=FieldValue(state=ValueState.UNRESOLVED,
        literal=MCKINLEY_LABEL), reason="Earlier source refusal remains in the same-field lookup history"),))


def assert_source_feedback(messages):
    feedback = retry_parts(messages)[-1].content
    for expected in ("field=precise_location", "source_history_blocks_human_review",
                     "waiting_source", "value.state unresolved", "no human question",
                     "Preserve all lookup history", "corrected query does not erase"):
        assert expected in feedback
    for private in ("GEOLocate locality", "Mount McKinley", "Philippines", "https://", "copy the deciding"):
        assert private not in feedback


def test_refused_then_corrected_no_match_gets_one_actionable_output_correction():
    request, refused, corrected = history()
    original = tuple(item.model_dump_json() for item in (refused, corrected))
    bad, good = human_output(request, corrected), source_output(request)
    with pytest.raises(EvidenceError, match="Human source coverage"):
        validate_resolution(request, bad.resolutions[0], (refused, corrected))
    turns = []

    def respond(messages, info):
        turns.append(messages)
        if len(turns) == 2:
            assert_source_feedback(messages)
        return ModelResponse(parts=[ToolCallPart("final_result",
            (bad if len(turns) == 1 else good).model_dump(mode="json"))])

    agent, deps = tool_agent(request, respond)
    deps.tool_results[request.role] = [refused, corrected]
    assert agent.run_sync("go", deps=deps).output == good
    assert len(turns) == 2
    assert tuple(item.model_dump_json() for item in deps.tool_results[request.role]) == original


def test_repeating_waiting_human_exhausts_existing_single_output_retry():
    request, refused, corrected = history()
    bad = human_output(request, corrected)
    turns = []

    def respond(messages, info):
        turns.append(messages)
        if len(turns) == 2:
            assert_source_feedback(messages)
        return ModelResponse(parts=[ToolCallPart("final_result", bad.model_dump(mode="json"))])

    agent, deps = tool_agent(request, respond)
    deps.tool_results[request.role] = [refused, corrected]
    with pytest.raises(UnexpectedModelBehavior, match="retries"):
        agent.run_sync("go", deps=deps)
    assert len(turns) == 2 and deps.tool_results[request.role] == [refused, corrected]


@pytest.mark.parametrize("failure", ["no_receipt", "held_unknown", "wrong_scope", "wrong_field", "changed_semantics"])
def test_same_field_failed_or_unproved_history_never_clears_after_no_match(failure):
    request, refused, corrected = history()
    previous = corrected
    if failure == "no_receipt":
        previous = corrected.model_copy(update={"receipt": None})
    else:
        change = {
            "held_unknown": {"effect_status": "held_unknown"},
            "wrong_scope": {"scope": request.scope.model_copy(update={"specimen_id": "other-specimen"})},
            "wrong_field": {"field_keys": (FieldKey.COUNTRY,)},
            "changed_semantics": {"result_json": json.dumps({"untrusted": "private receipt body"})},
        }[failure]
        previous = corrected.model_copy(update={"receipt": corrected.receipt.model_copy(update=change)})
    bad, good = human_output(request, corrected), source_output(request)
    turns = []

    def respond(messages, info):
        turns.append(messages)
        if len(turns) == 2:
            assert_source_feedback(messages)
        return ModelResponse(parts=[ToolCallPart("final_result",
            (bad if len(turns) == 1 else good).model_dump(mode="json"))])

    agent, deps = tool_agent(request, respond)
    deps.tool_results[request.role] = [previous, corrected]
    assert agent.run_sync("go", deps=deps).output == good
    assert len(turns) == 2 and deps.tool_results[request.role] == [previous, corrected]


@pytest.mark.parametrize("other_field_refused", [False, True])
def test_all_receipted_same_field_no_match_still_allows_human_review(other_field_refused):
    request, refused, corrected = history()
    retained = [corrected, corrected]
    if other_field_refused:
        retained.insert(0, refused.model_copy(update={"coverage": refused.coverage.model_copy(update={
            "field_key": FieldKey.COUNTRY})}))
    good = human_output(request, corrected)
    turns = []

    def respond(messages, info):
        turns.append(messages)
        assert not retry_parts(messages)
        return ModelResponse(parts=[ToolCallPart("final_result", good.model_dump(mode="json"))])

    agent, deps = tool_agent(request, respond)
    deps.tool_results[request.role] = retained
    assert agent.run_sync("go", deps=deps).output == good
    assert len(turns) == 1 and deps.tool_results[request.role] == retained


def test_false_coverage_claim_with_healthy_history_keeps_existing_scope_feedback():
    request, refused, corrected = history()
    good = human_output(request, corrected)
    claimed = corrected.coverage.model_copy(update={"query_digest": "f" * 64})
    bad = good.model_copy(update={"resolutions": (good.resolutions[0].model_copy(update={
        "question": good.resolutions[0].question.model_copy(update={"coverage": (claimed,)})}),)})
    turns = []

    def respond(messages, info):
        turns.append(messages)
        if len(turns) == 2:
            feedback = retry_parts(messages)[-1].content
            assert "invalid_evidence_or_scope" in feedback
            assert "source_history_blocks_human_review" not in feedback
        return ModelResponse(parts=[ToolCallPart("final_result",
            (bad if len(turns) == 1 else good).model_dump(mode="json"))])

    agent, deps = tool_agent(request, respond)
    deps.tool_results[request.role] = [corrected]
    assert agent.run_sync("go", deps=deps).output == good
    assert len(turns) == 2 and deps.tool_results[request.role] == [corrected]
