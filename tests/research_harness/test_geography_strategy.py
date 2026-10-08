"""Bounded strategy stops and real Agent correction over offline captured receipts."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage
from pydantic_ai_harness.step_persistence import InMemoryStepStore

from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.research_harness.agents import SpecialistHarness, SpecialistOutput
from specimen_digitization.research_harness.contracts import (
    FieldKey, FieldResolution, HumanQuestion, SourceCoverageReceipt, SourceCoverageState,
    SourceQuery, SourceResult, ToolReceipt, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import EvidenceError, validate_resolution
from specimen_digitization.research_harness.geography_strategy import SourceAttempt, geography_progress
from specimen_digitization.research_harness.prompts import (
    GEOGRAPHY_PROGRESS_PROMPT_VERSION, GEOGRAPHY_RESEARCH_PROMPT_VERSION,
)
from specimen_digitization.research_harness.sources import result_envelope

from test_research_harness_agents import model, requests, sql_broker


def request():
    original = requests()[next(role for role in requests() if role.value == 'specimen_geography')]
    return original.model_copy(update={'field_keys': (FieldKey.CITY,)})


def capture(request, source, status=LookupStatus.NO_MATCH, candidates=()):
    field_key = request.field_keys[0]
    result = SourceResult(status=status, candidate_json=tuple(json.dumps(item) for item in candidates),
        coverage=SourceCoverageReceipt(source_id=source, field_key=field_key,
            state=SourceCoverageState.SEARCHED, source_version='offline-fixture',
            coverage_limit='offline recorded semantic fixture',
            reason=f'{status}: no exact place' if source == 'geolocate' else 'fixture coverage'))
    data = result_envelope(result)
    return result.model_copy(update={'receipt': ToolReceipt(id=digest((source, status, candidates)),
        scope=request.scope, source_id=source, tool_id='source_lookup', field_keys=(field_key,),
        effect_id=digest((source, status, candidates)), attempt_ids=(digest(source),),
        request_digest=digest(source), binding_digest=digest('fixture-binding'), outcome=status,
        effect_status='completed', result_json=data, result_digest=hashlib.sha256(data.encode()).hexdigest())})


def attempt(request, source, status=LookupStatus.NO_MATCH, candidates=(), text='Yepocapa'):
    if source == 'geolocate':
        text = json.dumps({'country':'Guatemala','locality':text,'place':text,'value':text})
    return SourceAttempt(SourceQuery(source_id=source, field_key=FieldKey.CITY, query_text=text),
        capture(request, source, status, candidates))


def test_first_no_match_requires_one_available_place_name_alternative():
    req = request()
    retained = [attempt(req, 'geolocate')]
    progress = geography_progress(req, FieldKey.CITY, retained, ('geolocate', 'tgn', 'wikidata', 'nga'))
    assert not progress.review_eligible
    assert progress.stop_reason == 'relevant_place_name_alternative_remaining'
    assert set(progress.next_sources) == {'tgn', 'wikidata', 'nga'}
    retained.append(attempt(req, 'nga'))
    progress = geography_progress(req, FieldKey.CITY, retained, ('geolocate', 'tgn', 'wikidata', 'nga'))
    assert progress.review_eligible and progress.next_sources == ()
    assert len(progress.attempted_query_digests) == 2


def test_historical_success_requires_a_distinct_later_deciding_lookup():
    req = request()
    historical = {'field_key':'city', 'value':'San Pedro Yepocapa', 'authority_id':'nga:123',
        'settlement_allowed':False, 'validation_required':'geolocate'}
    retained = [attempt(req, 'geolocate'), attempt(req, 'nga', LookupStatus.SUCCESS, (historical,))]
    progress = geography_progress(req, FieldKey.CITY, retained, ('geolocate', 'nga'))
    assert not progress.review_eligible and progress.next_sources == ('geolocate',)
    retained.append(attempt(req, 'geolocate', text='San Pedro Yepocapa'))
    assert geography_progress(req, FieldKey.CITY, retained, ('geolocate', 'nga')).review_eligible


@pytest.mark.parametrize('status', [LookupStatus.TIMEOUT, LookupStatus.PROVIDER, LookupStatus.POLICY])
def test_operational_alternative_never_becomes_absence_even_with_receipt(status):
    req = request()
    retained = [attempt(req, 'geolocate'), attempt(req, 'nga', status)]
    progress = geography_progress(req, FieldKey.CITY, retained, ('geolocate', 'nga'))
    assert progress.state == 'waiting_source' and not progress.review_eligible


def test_duplicate_captured_effect_keeps_one_query_identity():
    req = request()
    item = attempt(req, 'geolocate')
    first = geography_progress(req, FieldKey.CITY, [item], ('geolocate',))
    second = geography_progress(req, FieldKey.CITY, [item, item], ('geolocate',))
    assert first == second and first.review_eligible


def test_cached_original_query_and_unrelated_lookup_do_not_finish_research():
    req = request()
    first = attempt(req, 'geolocate')
    hypothesis = {'field_key':'city','value':'San Pedro Yepocapa','authority_id':'nga:123',
                  'settlement_allowed':False,'validation_required':'geolocate'}
    alt = attempt(req, 'nga', LookupStatus.SUCCESS, (hypothesis,))
    progress = geography_progress(req,FieldKey.CITY,[first,alt,first],('geolocate','nga'))
    assert not progress.review_eligible and progress.stop_reason=='captured_historical_hypothesis_needs_validation'
    unrelated = attempt(req, 'geolocate', text='Guatemala City')
    assert not geography_progress(req,FieldKey.CITY,[first,alt,unrelated],('geolocate','nga')).review_eligible
    unrelated_alt = attempt(req, 'nga', text='Guatemala')
    progress = geography_progress(req,FieldKey.CITY,[first,unrelated_alt],('geolocate','nga'))
    assert not progress.review_eligible and progress.stop_reason=='relevant_place_name_alternative_remaining'
    # JSON formatting alone also cannot create a new strategy.
    formatted = first.query.model_copy(update={'query_text':json.dumps(json.loads(first.query.query_text),indent=1)})
    repeat = SourceAttempt(formatted,first.result)
    assert geography_progress(req,FieldKey.CITY,[first,alt,repeat],('geolocate','nga')).stop_reason == geography_progress(
        req,FieldKey.CITY,[first,alt],('geolocate','nga')).stop_reason
    failed = SourceAttempt(first.query,first.result.model_copy(update={'receipt':None,'status':LookupStatus.POLICY}))
    assert geography_progress(req,FieldKey.CITY,[first,alt,failed],('geolocate','nga')).state == 'waiting_source'


def test_unrequested_field_and_mismatched_source_are_refused():
    req = request()
    with pytest.raises(ValueError, match='outside_requested_field'):
        geography_progress(req, FieldKey.COUNTRY, (), ())
    bad = SourceAttempt(SourceQuery(source_id='nga', field_key=FieldKey.CITY), capture(req, 'geolocate'))
    with pytest.raises(ValueError, match='attempt_result_mismatch'):
        geography_progress(req, FieldKey.CITY, [bad], ())


def unresolved_question(req, result):
    return FieldResolution(field_key=FieldKey.CITY, work_state=WorkState.WAITING_HUMAN,
        value=FieldValue(state=ValueState.UNRESOLVED), reason='Scoped offline no-match',
        question=HumanQuestion(field_key=FieldKey.CITY, question='Choose the evidenced locality',
            reason='scoped_absence', coverage=(result.coverage,)))


def test_historical_candidate_cannot_settle_but_does_not_hide_valid_human_ambiguity():
    req = request()
    candidate = {'field_key':'city', 'value':'Yepocapa', 'authority_id':'nga:123',
        'settlement_allowed':False, 'validation_required':'geolocate'}
    history = capture(req, 'nga', LookupStatus.SUCCESS, (candidate,))
    resolution = FieldResolution(field_key=FieldKey.CITY, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, normalized='Yepocapa', authority_id='nga:123',
            evidence_ids=['context-fixture']), evidence_ids=('context-fixture',),
        reason='This context has not been independently validated')
    with pytest.raises(EvidenceError, match='Historical geography candidate requires'):
        validate_resolution(req, resolution, (history,))
    no_match = capture(req, 'geolocate')
    question = unresolved_question(req, no_match)
    assert validate_resolution(req, question, (no_match, history)) == question


@pytest.mark.parametrize("historical_v9", [False, True])
def test_real_agent_cannot_stop_after_first_no_match_and_corrects_with_alternative(tmp_path, historical_v9):
    req = request()
    if historical_v9:
        from prompt_test_fixtures import retained_text
        text = retained_text(req.role, 9)
        req = req.model_copy(update={"prompt": req.prompt.model_copy(update={
            "version": GEOGRAPHY_RESEARCH_PROMPT_VERSION, "text": text,
            "digest": hashlib.sha256(text.encode()).hexdigest()})})
    store, scope, lease, broker = sql_broker(tmp_path)
    records, calls = InMemoryStepStore(), []
    no_match, alternate = capture(req, 'geolocate'), capture(req, 'nga')

    class Tools:
        def available_sources(self, request):
            return ('geolocate', 'nga')
        async def query_source(self, request, query):
            calls.append(query.source_id)
            return no_match if query.source_id == 'geolocate' else alternate

    turns = []
    def respond(messages, info):
        turns.append(messages)
        n = len(turns)
        if n == 1 or n == 3:
            source = 'geolocate' if n == 1 else 'nga'
            query_text = json.dumps({'country':'Guatemala','place':'Yepocapa','locality':'Yepocapa','value':'Yepocapa'}) if n == 1 else 'Yepocapa'
            part = ToolCallPart('lookup_source', {'query':{
                'source_id':source, 'field_key':'city', 'query_text':query_text}}, tool_call_id=f'lookup-{n}')
        else:
            part = ToolCallPart(info.output_tools[0].name,
                SpecialistOutput(role=req.role, resolutions=(unresolved_question(req, no_match),)).model_dump(mode='json'),
                tool_call_id=f'output-{n}')
        return ModelResponse([part], usage=RequestUsage(input_tokens=10, output_tokens=8))

    runtime = SpecialistHarness(requests={req.role:req}, tool_broker=Tools(),
        model_factory=lambda request:model(FunctionModel(respond), request=request,
            broker=broker, scope=scope, lease=lease), step_store_factory=lambda _:records)
    result = asyncio.run(runtime.run_specialist(req.role))
    assert result.resolutions[0].work_state == WorkState.WAITING_HUMAN
    assert calls == ['geolocate', 'nga'] and len(turns) == 4
    assert any('geography_research_incomplete' in str(part) for message in turns[2] for part in message.parts)
    assert len(result.source_results) == 2 and store.budget(scope)['held_micro_usd'] == 0


def test_current_query_and_stop_instructions_are_coherent_and_old_v8_is_unchanged():
    req = request()
    assert req.prompt.version == GEOGRAPHY_PROGRESS_PROMPT_VERSION
    text = req.prompt.text
    assert 'Do not supply latitude, longitude, radius_km' in text
    assert 'geography_hierarchy()' in text and 'geography_progress_all()' in text
    assert 'there is no required all-provider sequence' in text
    assert 'waiting_source with the precise' in text and 'no specimen-user Save is required' in text
    old = Path('src/specimen_digitization/research_harness/prompts/specimen_geography-v8.txt').read_bytes()
    assert hashlib.sha256(old).hexdigest() == '1f8a49b243c19e1c2e4dcb1238bce199e21a9d81b4eb037c5810955905c02490'  # pragma: allowlist secret (frozen prompt SHA256)


def test_historical_context_does_not_preempt_a_verified_verbatim_locality():
    from test_geolocate_validator import assembled_request
    from test_geography_context import captured as historical_capture
    from production_e2e_support import _literal
    req = assembled_request('Near Yepocapa')
    literal = _literal(req, FieldKey.PRECISE_LOCATION)
    context = historical_capture(field=FieldKey.PRECISE_LOCATION)
    context = context.model_copy(update={'receipt':context.receipt.model_copy(update={'scope':req.scope})})
    assert validate_resolution(req,literal,()) == literal
    assert validate_resolution(req,literal,(context,)) == literal


def test_harness_resumes_completed_source_progress_without_resetting_usage(tmp_path):
    """Real native step persistence + SQL model effects, fixture source verifier seam."""
    from pydantic_ai.capabilities import AbstractCapability
    from specimen_digitization.research_harness.sources import result_envelope

    req = request()
    store, scope, lease, broker = sql_broker(tmp_path)
    records, source_calls = InMemoryStepStore(), []
    query = SourceQuery(source_id='geolocate', field_key=FieldKey.CITY, query_text='Yepocapa')
    result = capture(req, 'geolocate')
    result = result.model_copy(update={'coverage':result.coverage.model_copy(update={'query_digest':digest(query)})})
    semantic = result_envelope(result)
    result = result.model_copy(update={'receipt':result.receipt.model_copy(update={
        'result_json':semantic, 'result_digest':hashlib.sha256(semantic.encode()).hexdigest()})})

    class Tools:
        trusted_results = []
        def available_sources(self, request):
            return ('geolocate',)
        async def query_source(self, request, source_query):
            source_calls.append(source_query)
            return result

    class StopAfterCapturedSource(AbstractCapability):
        toolset_digest = req.prompt.toolset_digest
        async def before_model_request(self, ctx, request_context):
            if any(getattr(part, 'tool_name', None) == 'lookup_source' and
                   getattr(part, 'part_kind', None) == 'tool-return'
                   for message in request_context.messages for part in message.parts):
                raise RuntimeError('offline_process_interruption_before_dispatch')
            return request_context

    def respond(messages, info):
        has_source = any(getattr(part, 'tool_name', None) == 'lookup_source' and
                         getattr(part, 'part_kind', None) == 'tool-return'
                         for message in messages for part in message.parts)
        part = (ToolCallPart(info.output_tools[0].name,
            SpecialistOutput(role=req.role, resolutions=(unresolved_question(req, result),)).model_dump(mode='json'),
            tool_call_id='resume-output') if has_source else ToolCallPart('lookup_source',
            {'query':query.model_dump(mode='json')}, tool_call_id='captured-before-interruption'))
        return ModelResponse([part], usage=RequestUsage(input_tokens=10, output_tokens=8))

    tools = Tools()
    def runtime(extra=None, verifier=None):
        return SpecialistHarness(requests={req.role:req}, tool_broker=tools,
            model_factory=lambda request:model(FunctionModel(respond), request=request,
                broker=broker, scope=scope, lease=lease), step_store_factory=lambda _:records,
            extra_capabilities_factory=extra, recovery_source_verifier=verifier)

    with pytest.raises(RuntimeError, match='offline_process_interruption'):
        asyncio.run(runtime(lambda _: [StopAfterCapturedSource()]).run_specialist(req.role))
    assert source_calls == [query] and store.budget(scope)['held_micro_usd'] == 0

    async def verify(request, supplied):
        # Explicit offline canonical source seam; production uses SQL capture proof.
        assert request == req and supplied == result
        return result

    resumed = asyncio.run(runtime(verifier=verify).run_specialist(req.role))
    assert source_calls == [query]
    assert resumed.source_results == (result,) and resumed.resolutions[0].work_state == WorkState.WAITING_HUMAN
    assert resumed.usage.requests == 3 and resumed.usage.tool_calls >= 1
    assert store.budget(scope)['settled_micro_usd'] == 6 and store.budget(scope)['held_micro_usd'] == 0


def test_admin_hypothesis_requires_the_exact_verified_hierarchy_query():
    from test_geography_context import request as context_request, captured as historical_capture
    req = context_request(fields=(FieldKey.PROVINCE_STATE,))
    wrong = SourceQuery(source_id='geolocate',field_key=FieldKey.PROVINCE_STATE,query_text=json.dumps({
        'country':'Guatemala','state':'Sacatepequez','locality':'Yepocapa','place':'Yepocapa','value':'Sacatepequez'}))
    first = SourceAttempt(wrong,capture(req,'geolocate'))
    alt = SourceAttempt(SourceQuery(source_id='nga',field_key=FieldKey.PROVINCE_STATE,query_text='Yepocapa'),
        historical_capture(field=FieldKey.PROVINCE_STATE))
    # Merely querying the right place with a wrong field interpretation is insufficient.
    changed = wrong.model_copy(update={'query_text':json.dumps({
        'country':'Guatemala','state':'Chimaltenango','locality':'Yepocapa','place':'Yepocapa','value':'Sacatepequez'})})
    progress=geography_progress(req,FieldKey.PROVINCE_STATE,[first,alt,SourceAttempt(changed,capture(req,'geolocate'))],
        ('geolocate','nga'))
    assert not progress.review_eligible and progress.stop_reason=='captured_hierarchy_interpretation_needs_validation'
    from specimen_digitization.research_harness.geography_context import hierarchy_research
    correct=hierarchy_research(req,(alt.result,)).next_queries[0]
    progress=geography_progress(req,FieldKey.PROVINCE_STATE,[first,alt,SourceAttempt(correct,capture(req,'geolocate'))],
        ('geolocate','nga'))
    assert progress.review_eligible
    equivalent=correct.model_copy(update={'query_text':json.dumps({**json.loads(correct.query_text),'county':''})})
    assert geography_progress(req,FieldKey.PROVINCE_STATE,[first,alt,SourceAttempt(equivalent,capture(req,'geolocate'))],
        ('geolocate','nga')).review_eligible


def test_authorized_retry_has_its_own_conversation_and_keeps_the_same_sql_budget(tmp_path):
    """Retry admission remains upstream; this tests the admitted command's lineage."""
    from pydantic_ai_harness.step_persistence import RunRecord, StepEvent
    from specimen_digitization.research_harness.package_qualification import SERIALIZATION_VERSION
    req=request()
    store,scope,lease,broker=sql_broker(tmp_path)
    records=InMemoryStepStore()
    prior_conversation=f'{req.scope.job_id}:{req.scope.generation}:{req.role.value}'
    async def old_failed_run():
        await records.register_run(RunRecord(run_id='old-failed',agent_name=req.role.value,
            conversation_id=prior_conversation,metadata={'job_id':req.scope.job_id,'generation':'1',
                'prompt_digest':req.prompt.digest,'serialization_version':SERIALIZATION_VERSION}))
        await records.append_event(StepEvent(run_id='old-failed',kind='run_failed',step_index=0))
    asyncio.run(old_failed_run())
    retry=req.model_copy(update={'retry_command_id':digest('already-admitted-offline-retry'),
        'field_revisions':{FieldKey.CITY:1}})
    def respond(messages,info):
        output=SpecialistOutput(role=retry.role,resolutions=(FieldResolution(field_key=FieldKey.CITY,
            work_state=WorkState.WAITING_SOURCE,value=FieldValue(),reason='source prerequisite'),))
        return ModelResponse([ToolCallPart(info.output_tools[0].name,output.model_dump(mode='json'),
            tool_call_id='retry-final')],usage=RequestUsage(input_tokens=10,output_tokens=8))
    runtime=SpecialistHarness(requests={retry.role:retry},tool_broker=object(),
        model_factory=lambda request:model(FunctionModel(respond),request=request,broker=broker,scope=scope,lease=lease),
        step_store_factory=lambda _:records)
    result=asyncio.run(runtime.run_specialist(retry.role))
    assert result.conversation_id==prior_conversation+':retry:'+retry.retry_command_id
    assert store.budget(scope)['settled_micro_usd']==3
    assert len(asyncio.run(records.list_runs(conversation_id=prior_conversation)))==1


def test_completed_ambiguous_hierarchy_can_request_human_review_without_choosing_a_parent():
    from test_geography_context import request as context_request, captured as historical_capture
    req=context_request(fields=(FieldKey.PROVINCE_STATE,))
    query=SourceQuery(source_id='geolocate',field_key=FieldKey.PROVINCE_STATE,query_text=json.dumps({
        'country':'Guatemala','state':'Chimaltenango','locality':'Yepocapa','place':'Yepocapa','value':'Chimaltenango'}))
    first=SourceAttempt(query,capture(req,'geolocate',LookupStatus.AMBIGUOUS))
    alt=SourceAttempt(SourceQuery(source_id='nga',field_key=FieldKey.PROVINCE_STATE,query_text='Yepocapa'),
        historical_capture(field=FieldKey.PROVINCE_STATE,status=LookupStatus.AMBIGUOUS))
    progress=geography_progress(req,FieldKey.PROVINCE_STATE,[first,alt],('geolocate','nga'))
    assert progress.review_eligible and progress.state=='needs_human'
