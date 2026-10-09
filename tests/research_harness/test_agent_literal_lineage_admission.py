"""Pre-acceptance literal custody using a synthetic excerpt of the r55 geography shape.

The real retained r55 proof stays private and immutable. These tests exercise the
same P.I. / NO_MATCH / unselected-reader case without importing that capture.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry

from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.research_harness.agents import (
    ResearchDeps, SpecialistHarness, SpecialistOutput, literal_has_original_request_lineage,
    specialist_output_schema_digest,
)
from specimen_digitization.research_harness.contracts import (
    EventHypothesis, EventKind, FieldKey, FieldResolution, FragmentRelation, HumanQuestion,
    OrganiserCandidate, RelationKind, ResearchScope, SourceCoverageReceipt, SourceCoverageState,
    SourceFragment, SourceQuery, SourceResult, SpecialistRequest, SpecialistRole, ToolReceipt, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import (
    assemble_field, dts_policy_resolution, temporal_resolutions,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.geography_strategy import SourceAttempt
from specimen_digitization.research_harness.sources import result_envelope


class _ValidatorAgent:
    def output_validator(self, callback):
        self.validate = callback
        return callback


def _scope():
    return ResearchScope(organization_id="synthetic-org", collection_id="synthetic-insects",
        specimen_id="synthetic-specimen", job_id="synthetic-r55", generation=1,
        input_digest="a" * 64, profile_digest="b" * 64)


def _fragment(scope, observation_id, text, literal, *, fragment_id=None, start=None):
    start = text.index(literal) if start is None else start
    return SourceFragment(id=fragment_id or f"fragment:{observation_id}:{start}", scope=scope,
        asset_id="synthetic-asset", asset_generation="1", asset_digest="c" * 64,
        label_id="synthetic-label", region_id="synthetic-region", observation_id=observation_id,
        reader=observation_id, model_id="synthetic-reader", prompt_digest="d" * 64,
        observation_text=text, observation_digest=hashlib.sha256(text.encode()).hexdigest(),
        start=start, end=start + len(literal), literal=literal, order=0, input_source="raw_reading")


def _request():
    scope = _scope()
    fragments = tuple(_fragment(scope, observation, text, "Mindanao, P.I.") for observation, text in (
        ("reader-a", "Davao Prov.\nMindanao, P.I.\nF.G. Werner"),
        ("reader-b", "Davao Prov.\nMindanao, P.I.\nF.G. wermer"),
    ))
    candidates = tuple(OrganiserCandidate(id=f"organiser:{item.observation_id}",
        field_key=FieldKey.COUNTRY, literal="P.I.", source="fixture", status="located",
        reason="located_label_span", region_id=item.region_id,
        observation_id=item.observation_id,
        start=item.observation_text.index("P.I."), end=item.observation_text.index("P.I.") + 4)
        for item in fragments)
    return SpecialistRequest(scope=scope, role=SpecialistRole.GEOGRAPHY,
        field_keys=(FieldKey.COUNTRY,),
        prompt=resolve_prompt(SpecialistRole.GEOGRAPHY, profile_digest=scope.profile_digest,
            source_registry_digest="e" * 64, toolset_digest="f" * 64,
            model_route="harness-deepseek", output_schema_digest=specialist_output_schema_digest()),
        fragments=fragments, organiser_candidates=candidates)


def _no_match_query():
    return SourceQuery(source_id="geolocate", field_key=FieldKey.COUNTRY,
        query_text=json.dumps({"country": "Philippines", "state": "", "county": "",
            "locality": "Mindanao, P.I.", "place": "Mindanao", "value": "Philippines"}))


def _no_match(request):
    coverage = SourceCoverageReceipt(source_id="geolocate", field_key=FieldKey.COUNTRY,
        state=SourceCoverageState.SEARCHED, source_version="synthetic-geolocate-v2",
        qualification_digest="1" * 64, query_digest=digest(_no_match_query()),
        candidate_count=9, receipt_ids=("source:synthetic-no-match",),
        coverage_limit="bounded synthetic source", reason="no_match: nine matches, no named place")
    bare = SourceResult(status=LookupStatus.NO_MATCH, coverage=coverage)
    envelope = result_envelope(bare)
    receipt = ToolReceipt(id="synthetic-tool-receipt", scope=request.scope, tool_id="geolocate",
        source_id="geolocate", field_keys=(FieldKey.COUNTRY,), effect_id="3" * 64,
        attempt_ids=("synthetic-attempt",), request_digest="4" * 64, binding_digest="5" * 64,
        outcome=LookupStatus.NO_MATCH, effect_status="completed", result_json=envelope,
        result_digest=hashlib.sha256(envelope.encode()).hexdigest())
    return bare.model_copy(update={"receipt": receipt})


def _country(request, result, *, literal="P.I.", **value_updates):
    value = FieldValue(state=ValueState.UNRESOLVED, literal=literal,
        reason="no_match: historical country interpretation unvalidated").model_copy(update=value_updates)
    question = HumanQuestion(field_key=FieldKey.COUNTRY, reason="scoped_absence",
        question="Confirm the country named by P.I. on both raw readings.",
        coverage=(result.coverage,), evidence_ids=result.coverage.receipt_ids)
    return FieldResolution(field_key=FieldKey.COUNTRY, work_state=WorkState.WAITING_HUMAN,
        value=value, question=question, reason="Both readers show P.I.; the source did not settle it")


def _validate(request, result, *resolutions):
    agent = _ValidatorAgent()
    SpecialistHarness._register_output_validation(agent)
    # This synthetic source profile admits GEOLocate only; no alternative
    # historical strategy is left unattempted before scoped-absence review.
    broker = SimpleNamespace(available_sources=lambda request: ("geolocate",))
    deps = ResearchDeps({request.role: request}, broker,
        {request.role: [result] if result is not None else []})
    if request.role == SpecialistRole.GEOGRAPHY and result is not None:
        # Retain the completed synthetic source attempt required by the current
        # Geography stop contract before checking the original literal lineage.
        deps.source_attempts[request.role] = [SourceAttempt(_no_match_query(), result)]
    context = SimpleNamespace(deps=deps, agent=SimpleNamespace(name=request.role.value),
        retry=0, max_retries=1, partial_output=False)
    output = SpecialistOutput(role=request.role, resolutions=resolutions)
    return agent.validate(context, output)


def test_real_shaped_pi_no_match_retries_missing_literal_lineage_without_losing_question():
    request = _request()
    result = _no_match(request)
    unresolved = _country(request, result)
    with pytest.raises(ModelRetry, match="specialist_output_literal_lacks_original_reading"):
        _validate(request, result, unresolved)
    assert unresolved.value.literal == "P.I."
    assert unresolved.question.coverage == (result.coverage,)
    assert unresolved.value.verbatim_by_observation == {}

    absent = _country(request, result, literal=None)
    assert _validate(request, result, absent).resolutions == (absent,)
    assert absent.question == unresolved.question
    assert absent.reason == unresolved.reason


def test_two_explicit_raw_readers_prove_pi_without_selecting_or_inventing_one():
    request = _request()
    result = _no_match(request)
    readings = {item.observation_id: item.observation_text for item in request.fragments}
    resolution = _country(request, result, verbatim_by_observation=readings,
        input_source_by_observation=dict.fromkeys(readings, "raw_reading"))
    assert literal_has_original_request_lineage(request, resolution)
    assert _validate(request, result, resolution).resolutions == (resolution,)
    assert resolution.value.source_observation_id is None
    assert resolution.value.settled_observation_ids == []


@pytest.mark.parametrize("change", (
    {"verbatim_by_observation": {"missing-reader": "Mindanao, P.I."},
     "input_source_by_observation": {"missing-reader": "raw_reading"}},
    {"verbatim_by_observation": {"reader-a": "invented P.I. text"},
     "input_source_by_observation": {"reader-a": "raw_reading"}},
    {"verbatim_by_observation": {"reader-a": "Mindanao, P.I."},
     "input_source_by_observation": {"reader-a": "decided_transcript"}},
    {"verbatim_by_observation": {"reader-a": "Mindanao, P.I."},
     "input_source_by_observation": {"reader-a": "raw_reading"},
     "input_source": "decided_transcript"},
    {"verbatim_by_observation": {"reader-a": "Mindanao, P.I."},
     "input_source_by_observation": {"reader-a": "raw_reading"},
     "source_observation_id": "reader-a"},
))
def test_fake_reader_or_route_cannot_satisfy_literal_admission(change):
    request = _request()
    result = _no_match(request)
    with pytest.raises(ModelRetry, match="specialist_output_literal_lacks_original_reading"):
        _validate(request, result, _country(request, result, **change))


def test_unique_original_route_needs_no_redundant_model_route_declaration():
    request = _request()
    result = _no_match(request)
    resolution = _country(request, result,
        verbatim_by_observation={"reader-a": request.fragments[0].observation_text})
    assert literal_has_original_request_lineage(request, resolution)
    assert _validate(request, result, resolution).resolutions == (resolution,)


def test_actual_deterministic_single_reader_temporal_pair_reaches_agent_acceptance():
    scope = _scope()
    fragment = _fragment(scope, "reader-a", "3 IX '46", "3 IX '46")
    event = EventHypothesis(id="event:collecting-date", scope=scope, kind=EventKind.COLLECTING,
        fragment_ids=(fragment.id,), evidence_ids=("evidence:written-date",),
        reason="Synthetic accepted collecting date", status="accepted", validator_version="synthetic-v1")
    assembly = assemble_field(assembly_id="assembly:collecting-date", scope=scope,
        field_key=FieldKey.DATE_VISITED_FROM, fragments=(fragment,), event=event)
    request = SpecialistRequest(scope=scope, role=SpecialistRole.TEMPORAL,
        field_keys=(FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO),
        prompt=resolve_prompt(SpecialistRole.TEMPORAL, profile_digest=scope.profile_digest,
            source_registry_digest="e" * 64, toolset_digest="f" * 64,
            model_route="harness-deepseek", output_schema_digest=specialist_output_schema_digest()),
        fragments=(fragment,), events=(event,), assemblies=(assembly,))
    resolutions = temporal_resolutions(request, event_id=event.id)
    assert resolutions[0].value.literal == "3 IX '46"
    assert resolutions[0].value.verbatim_by_observation
    assert resolutions[0].value.input_source is None
    assert resolutions[0].value.input_source_by_observation == {}
    assert literal_has_original_request_lineage(request, resolutions[0])
    assert _validate(request, None, *resolutions).resolutions == resolutions


def test_preserved_dts_policy_literal_passes_only_its_existing_input_membership_rule():
    scope = _scope()
    fragment = _fragment(scope, "reader-a", "Synthetic D/T/S", "Synthetic D/T/S")
    request = SpecialistRequest(scope=scope, role=SpecialistRole.COLLECTION,
        field_keys=(FieldKey.VERBATIM_DTS,),
        prompt=resolve_prompt(SpecialistRole.COLLECTION, profile_digest=scope.profile_digest,
            source_registry_digest="e" * 64, toolset_digest="f" * 64,
            model_route="harness-deepseek", output_schema_digest=specialist_output_schema_digest()),
        fragments=(fragment,))
    held = dts_policy_resolution("Synthetic D/T/S")
    assert held.work_state == WorkState.WAITING_POLICY
    assert held.value.verbatim_by_observation == {}
    assert _validate(request, None, held).resolutions == (held,)
    assert held.value.source_observation_id is None

    with pytest.raises(ModelRetry, match="specialist_output_has_invalid_evidence_or_scope"):
        _validate(request, None, dts_policy_resolution("invented D/T/S"))

    with pytest.raises(ValueError, match="Evidence graph cannot cross scoped"):
        SpecialistRequest(scope=scope.model_copy(update={"specimen_id": "other"}),
            role=request.role, field_keys=request.field_keys, prompt=request.prompt,
            fragments=request.fragments)

    # The typed output rejects turning this policy hold into a resolved claim.
    with pytest.raises(ValueError, match="Resolved requires supported legacy value and evidence"):
        _validate(request, None, held.model_copy(update={"work_state": WorkState.RESOLVED}))


@pytest.mark.parametrize("fault", ("outside_fragment", "wrong_scope", "wrong_digest", "wrong_offset", "duplicate"))
def test_original_fragment_identity_and_exact_span_are_required(fault):
    request = _request()
    result = _no_match(request)
    source = request.fragments[0]
    if fault == "outside_fragment":
        changed = source.model_copy(update={"literal": "Davao Prov.", "start": 0, "end": len("Davao Prov.")})
    elif fault == "wrong_scope":
        changed = source.model_copy(update={"scope": request.scope.model_copy(update={"specimen_id": "other"})})
    elif fault == "wrong_digest":
        changed = source.model_copy(update={"observation_digest": "0" * 64})
    elif fault == "wrong_offset":
        changed = source.model_copy(update={"start": 0})
    else:
        changed = source
    fragments = (changed, source) if fault == "duplicate" else (changed,)
    damaged = request.model_copy(update={"fragments": fragments, "organiser_candidates": ()})
    value = {source.observation_id: source.observation_text}
    resolution = _country(damaged, result, verbatim_by_observation=value,
        input_source_by_observation={source.observation_id: "raw_reading"})
    assert not literal_has_original_request_lineage(damaged, resolution)
    typed_refusals = {"wrong_scope": "Evidence graph cannot cross scoped",
        "wrong_digest": "Immutable reading digest mismatch",
        "wrong_offset": "Fragment must preserve exact reading substring"}
    if fault in typed_refusals:
        # The current Geography stop gate first revalidates its immutable input.
        # Invalid scope/bytes/offsets refuse there before output-lineage admission.
        with pytest.raises(ValueError, match=typed_refusals[fault]):
            _validate(damaged, result, resolution)
    else:
        with pytest.raises(ModelRetry, match="specialist_output_literal_lacks_original_reading"):
            _validate(damaged, result, resolution)


def test_joined_literal_requires_exact_target_assembly_and_all_reader_fragments():
    scope = _scope()
    text = "E. slope\nMt. McKinley"
    first = _fragment(scope, "reader-a", text, "E. slope")
    second = _fragment(scope, "reader-a", text, "Mt. McKinley", fragment_id="fragment:second")
    event = EventHypothesis(id="event:collecting", scope=scope, kind=EventKind.COLLECTING,
        fragment_ids=(first.id, second.id), evidence_ids=("evidence:label",),
        reason="Synthetic accepted collecting event", status="accepted", validator_version="synthetic-v1")
    relation = FragmentRelation(id="relation:continuation", scope=scope,
        fragment_ids=event.fragment_ids, kind=RelationKind.CONTINUATION, event_id=event.id,
        evidence_ids=("evidence:label",), reason="Same written locality",
        proposer_version="synthetic-v1", status="accepted", validator_version="synthetic-v1")
    assembly = assemble_field(assembly_id="assembly:locality", scope=scope,
        field_key=FieldKey.PRECISE_LOCATION, fragments=(first, second), event=event,
        relations=(relation,), assertion_kind="complementary")
    request = _request().model_copy(update={"field_keys": (FieldKey.PRECISE_LOCATION,),
        "fragments": (first, second), "events": (event,), "relations": (relation,),
        "assemblies": (assembly,), "organiser_candidates": ()})
    value = FieldValue(state=ValueState.UNRESOLVED, literal=assembly.interpreted_text,
        verbatim_by_observation={first.observation_id: text},
        input_source_by_observation={first.observation_id: "raw_reading"})
    resolution = FieldResolution(field_key=FieldKey.PRECISE_LOCATION, work_state=WorkState.WAITING_POLICY,
        value=value, assembly_ids=(assembly.id,), event_id=event.id, reason="No settling authority")
    assert literal_has_original_request_lineage(request, resolution)
    result = _no_match(request)
    assert _validate(request, result, resolution).resolutions == (resolution,)
    wrong_event = resolution.model_copy(update={"event_id": "wrong"})
    assert not literal_has_original_request_lineage(request, wrong_event)
    with pytest.raises(ModelRetry, match="specialist_output_literal_lacks_original_reading"):
        _validate(request, result, wrong_event)
    assert not literal_has_original_request_lineage(request, resolution.model_copy(update={"assembly_ids": ("missing",)}))
    wrong_field = assembly.model_copy(update={"field_key": FieldKey.COUNTRY})
    assert not literal_has_original_request_lineage(request.model_copy(update={"assemblies": (wrong_field,)}), resolution)
    missing_reader = resolution.model_copy(update={"value": value.model_copy(update={"verbatim_by_observation": {}})})
    assert not literal_has_original_request_lineage(request, missing_reader)
