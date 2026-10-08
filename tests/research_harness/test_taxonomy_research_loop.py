"""Scripted agent turns exercise taxonomy feedback; no model/provider calls."""
import hashlib

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, ToolCallPart

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.contracts import FieldKey, SourceCoverageState, SourceQuery, WorkState, digest
from specimen_digitization.research_harness.sources import result_envelope
from specimen_digitization.research_harness.taxonomy import taxonomy_stop_defect

from test_specialist_feedback import policy_output, retry_parts, tool_agent
from test_taxon_input_reconciliation import request_for, resolution_for, result_for
from test_taxonomy_reader_negatives import negative_for


def supporting_negative(request, source, literal="Epipocus"):
    result = negative_for(request, literal)
    result = result.model_copy(update={
        "coverage": result.coverage.model_copy(update={"source_id": source,
            "query_digest": digest(SourceQuery(source_id=source, field_key=FieldKey.TAXON, query_text=literal))}),
        "evidence": tuple(item.model_copy(update={"source_id": source, "role": "supports"}) for item in result.evidence),
    })
    payload = result_envelope(result)
    return result.model_copy(update={"receipt": result.receipt.model_copy(update={
        "source_id": source, "result_json": payload,
        "result_digest": hashlib.sha256(payload.encode()).hexdigest()})})


def test_one_negative_cannot_stop_before_supporting_research_and_can_correct():
    request = request_for()
    gbif = negative_for(request, "Epipocus")
    turns = []
    def respond(messages, info):
        turns.append(messages)
        if len(turns) == 2:
            assert "taxonomy_research_incomplete" in retry_parts(messages)[-1].content
            deps.tool_results[request.role].extend(supporting_negative(request, source)
                for source in ("global_names_verifier", "catalogue_of_life"))
        return ModelResponse(parts=[ToolCallPart("final_result", policy_output(request).model_dump(mode="json"))])
    agent, deps = tool_agent(request, respond)
    deps.tool_results[request.role] = [gbif]
    output = agent.run_sync("go", deps=deps).output
    assert len(turns) == 2 and output.resolutions[0].work_state == WorkState.WAITING_POLICY
    assert len(deps.tool_results[request.role]) == 3


def test_repeated_premature_stop_uses_only_existing_one_retry():
    request = request_for()
    turns = []
    def respond(messages, info):
        turns.append(messages)
        return ModelResponse(parts=[ToolCallPart("final_result", policy_output(request).model_dump(mode="json"))])
    agent, deps = tool_agent(request, respond)
    deps.tool_results[request.role] = [negative_for(request, "Epipocus")]
    with pytest.raises(UnexpectedModelBehavior, match="maximum output retries \\(1\\)"):
        agent.run_sync("go", deps=deps)
    assert len(turns) == 2 and len(deps.tool_results[request.role]) == 1


def test_no_named_genus_requires_no_source_and_terminates_without_question():
    request = request_for((("raw", "sp.30", "raw_reading"),))
    def respond(messages, info):
        return ModelResponse(parts=[ToolCallPart("final_result", policy_output(request).model_dump(mode="json"))])
    agent, deps = tool_agent(request, respond)
    output = agent.run_sync("go", deps=deps).output
    assert not deps.tool_results and output.resolutions[0].question is None
    assert output.resolutions[0].value.parsed is None


def test_exact_negative_alternative_survives_invalid_output_then_corrects():
    request = request_for((("raw", "Epipocus", "raw_reading"),
                           ("decided", "Epipsocus", "decided_transcript")))
    positive, negative = result_for(request, "Epipocus"), negative_for(request, "Epipsocus")
    good = resolution_for(request, (positive,))
    bad = good.model_copy(update={"value": good.value.model_copy(update={"parsed": "Inventedgenus"})})
    turns = []
    def respond(messages, info):
        turns.append(messages)
        if len(turns) == 2:
            assert "exact_source_candidate_required" in retry_parts(messages)[-1].content
        return ModelResponse(parts=[ToolCallPart("final_result", SpecialistOutput(role=request.role,
            resolutions=(bad if len(turns) == 1 else good,)).model_dump(mode="json"))])
    agent, deps = tool_agent(request, respond)
    deps.tool_results[request.role] = [positive, negative]
    assert agent.run_sync("go", deps=deps).output.resolutions == (good,)
    assert len(turns) == 2 and deps.tool_results[request.role] == [positive, negative]


def test_supporting_disagreement_does_not_veto_gbif():
    request = request_for()
    gbif = result_for(request, "Epipocus")
    support = result_for(request, "Epipocus", authority="gnv:synthetic-other", value="Othergenus")
    support = support.model_copy(update={"coverage": support.coverage.model_copy(update={"source_id": "global_names_verifier"}),
        "evidence": tuple(item.model_copy(update={"source_id": "global_names_verifier", "role": "supports"}) for item in support.evidence)})
    payload = result_envelope(support)
    support = support.model_copy(update={"receipt": support.receipt.model_copy(update={"source_id": "global_names_verifier",
        "result_json": payload, "result_digest": hashlib.sha256(payload.encode()).hexdigest()})})
    from specimen_digitization.research_harness.evidence import validate_resolution
    assert validate_resolution(request, resolution_for(request, (gbif,)), (gbif, support))


def test_unreceipted_support_does_not_prove_completed_research():
    request = request_for()
    results = (negative_for(request, "Epipocus"), supporting_negative(request, "global_names_verifier"),
        supporting_negative(request, "catalogue_of_life").model_copy(update={"receipt": None}))
    assert "waiting_source" in taxonomy_stop_defect(request, results)


def test_explicit_unqualified_support_is_recorded_but_not_a_negative():
    request = request_for()
    refused = supporting_negative(request, "catalogue_of_life")
    refused = refused.model_copy(update={"status": LookupStatus.POLICY, "evidence": (), "receipt": None,
        "coverage": refused.coverage.model_copy(update={"state": SourceCoverageState.UNQUALIFIED})})
    results = (negative_for(request, "Epipocus"), supporting_negative(request, "global_names_verifier"), refused)
    assert taxonomy_stop_defect(request, results) is None


def test_one_reader_negative_with_support_cannot_drop_the_other_reader():
    request = request_for((("raw", "Epipocus", "raw_reading"),
                           ("decided", "Epipsocus", "decided_transcript")))
    results = [negative_for(request, "Epipocus"), supporting_negative(request, "global_names_verifier"),
               supporting_negative(request, "catalogue_of_life")]
    assert "each evidenced reader alternative" in taxonomy_stop_defect(request, tuple(results))
    results.append(negative_for(request, "Epipsocus"))
    assert taxonomy_stop_defect(request, tuple(results)) is not None
    results.extend(supporting_negative(request, source, "Epipsocus")
                   for source in ("global_names_verifier", "catalogue_of_life"))
    assert taxonomy_stop_defect(request, tuple(results)) is None


def test_an_explicit_named_taxon_cannot_stop_without_any_lookup():
    from specimen_digitization.research_harness.contracts import SpecialistRole
    from test_specialist_feedback import graph_request
    request = graph_request(SpecialistRole.TAXONOMY, FieldKey.TAXON, "Epipocus")
    assert "explicitly evidenced named taxon" in taxonomy_stop_defect(request, ())


def test_explicit_genus_free_code_requires_no_lookup():
    from specimen_digitization.research_harness.contracts import SpecialistRole
    from test_specialist_feedback import graph_request
    request = graph_request(SpecialistRole.TAXONOMY, FieldKey.TAXON, "sp.30")
    assert taxonomy_stop_defect(request, ()) is None


def test_an_accepted_complete_gbif_settlement_cannot_be_discarded_as_policy():
    request = request_for()
    positive = result_for(request, "Epipocus")
    results = (positive, supporting_negative(request, "global_names_verifier"),
        supporting_negative(request, "catalogue_of_life"))
    assert "settled_candidate" in taxonomy_stop_defect(request, results)


def test_conflicting_accepted_genera_still_allow_an_unresolved_stop_after_research():
    request = request_for((("raw", "Epipocus", "raw_reading"),
                           ("other", "Epipsocus", "raw_reading")))
    results = [result_for(request, "Epipocus"),
        result_for(request, "Epipsocus", authority="gbif:other", value="Epipsocus")]
    results.extend(supporting_negative(request, source, literal)
        for source in ("global_names_verifier", "catalogue_of_life") for literal in ("Epipocus", "Epipsocus"))
    assert taxonomy_stop_defect(request, tuple(results)) is None


def test_unused_regional_flag_does_not_hide_completed_support_searches():
    request = request_for()
    results = [negative_for(request, "Epipocus", north_american=True)]
    for source in ("global_names_verifier", "catalogue_of_life"):
        result = supporting_negative(request, source)
        result = result.model_copy(update={"coverage": result.coverage.model_copy(update={
            "query_digest": digest(SourceQuery(source_id=source, field_key=FieldKey.TAXON,
                query_text="Epipocus", north_american=True))})})
        payload = result_envelope(result)
        result = result.model_copy(update={"receipt": result.receipt.model_copy(update={
            "result_json": payload, "result_digest": hashlib.sha256(payload.encode()).hexdigest()})})
        results.append(result)
    assert taxonomy_stop_defect(request, tuple(results)) is None
