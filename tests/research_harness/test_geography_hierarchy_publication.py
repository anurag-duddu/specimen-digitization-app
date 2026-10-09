"""Missing Guatemala hierarchy publishes through the actual offline composer.

Recorded NGA/GEOLocate sources, real capture/effect/journal/writer code, scripted
model and the existing in-memory connector. No network, live processing or Save.
"""

import json
from urllib.parse import parse_qs, urlsplit

from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.contracts import FieldKey, FieldResolution, SourceQuery, SpecialistRole, WorkState
from specimen_digitization.research_harness.geography_context import hierarchy_research
from specimen_digitization.research_harness.sources import FixtureSourceTransport
from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow

import production_e2e_support as support
import test_production_e2e as composed
from test_historical_gazetteers import FixtureFetch
from test_geolocate_capture import RECORDED_BODY, RECORDED_URL, YEPOCAPA


def test_missing_country_admin_publish_automatically_and_county_stays_honestly_unresolved(tmp_path, monkeypatch):
    # Country and province are genuinely absent from every synthetic reading.
    values = {key:value for key,value in support.LABEL_VALUES.items()
        if key not in {'country','province_state','county'}}
    values.update(city='Yepocapa', precise_location='Yepocapa')
    text = '\n'.join(f'{key}: {value}' for key,value in values.items())
    assert 'Guatemala' not in text and 'Chimaltenango' not in text
    monkeypatch.setattr(support, 'LABEL_TEXT', text)
    monkeypatch.setattr(composed, 'LABEL_TEXT', text)
    import httpx
    def refuse(*args, **kwargs):
        raise AssertionError('offline publication never performs network HTTP')
    monkeypatch.setattr(httpx.Client, 'send', refuse)
    monkeypatch.setattr(httpx.AsyncClient, 'send', refuse)
    lifecycle = composed.build_rig(tmp_path)
    rig = next(lifecycle)
    try:
        ordinary_models = support.scripted_model_factory(rig.model_calls)
        seen_geography, model_errors = [], []

        def model_factory(request, binding):
            if request.role != SpecialistRole.GEOGRAPHY:
                return ordinary_models(request, binding)
            def respond(messages, info):
                try:
                    results, _ = support._results(messages)
                    rig.model_calls.append((str(request.role), 1 + sum(isinstance(m, ModelResponse) for m in messages)))
                    if not results:
                        parts = [ToolCallPart('lookup_source', {'query':{
                            'source_id':'nga', 'field_key':'city', 'query_text':'Yepocapa'}}, tool_call_id='hierarchy-nga')]
                    elif len(results) == 1:
                        research = hierarchy_research(request, results)
                        assert {q.field_key for q in research.next_queries} == {FieldKey.COUNTRY,FieldKey.PROVINCE_STATE}
                        seen_geography.append(research)
                        parts = [ToolCallPart('lookup_source', {'query':q.model_dump(mode='json')},
                            tool_call_id='derived-'+str(q.field_key)) for q in research.next_queries]
                    elif len(results) == 3:
                        parts = [ToolCallPart('lookup_source', {'query':SourceQuery(source_id='geolocate',
                            field_key=FieldKey.CITY, query_text=json.dumps(YEPOCAPA)).model_dump(mode='json')},
                            tool_call_id='validated-city')]
                    else:
                        fields = []
                        for key in request.field_keys:
                            if key == FieldKey.COUNTY:
                                value = FieldResolution(field_key=key, work_state=WorkState.WAITING_POLICY,
                                    value=FieldValue(), reason='missing_policy:unstructured_label_event_unqualified; Guatemala county mapping unqualified')
                            elif key == FieldKey.PRECISE_LOCATION:
                                value = support._literal(request, key)
                            else:
                                rows = support._assemblies(request,key)
                                value = support._geolocated(key,results,rows)
                                assert value is not None
                                if not rows:
                                    reading = next((f for f in request.fragments if f.input_source=='decided_transcript'),request.fragments[0])
                                    value = value.model_copy(update={'value':value.value.model_copy(update={
                                        'source_observation_id':reading.observation_id,
                                        'source_region_id':reading.region_id, 'input_source':reading.input_source,
                                        'verbatim_by_observation':{reading.observation_id:reading.observation_text},
                                        'settled_observation_ids':[reading.observation_id]})})
                            fields.append(value)
                        parts = [ToolCallPart(info.output_tools[0].name,
                            SpecialistOutput(role=request.role,resolutions=tuple(fields)).model_dump(mode='json'),
                            tool_call_id='geography-result')]
                    return ModelResponse(parts,usage=support.USAGE)
                except Exception as error:
                    model_errors.append(repr(error))
                    raise
            return FunctionModel(respond)

        recorded = support.fixture_source_transport(rig.source_urls)
        nga = FixtureFetch('nga','Yepocapa')
        async def read(url,policy):
            if policy.id=='nga':
                rig.source_urls.append(url)
                parts=urlsplit(url)
                return await nga(parts.scheme+'://'+parts.netloc+parts.path,
                    {key:value[0] for key,value in parse_qs(parts.query).items()})
            if policy.id=='geolocate':
                rig.source_urls.append(url)
                assert url==RECORDED_URL
                return 200,RECORDED_BODY
            return await recorded.get(url,policy=policy)

        workflow = compose_production_research_workflow(rig.ordinary,repository=rig.repository,
            environ=composed.SWITCH_ON,actor_uid=support.WORKER,state_backend=rig.backend,
            model_factory=model_factory,source_transport=FixtureSourceTransport(read),blobs=rig.research_blobs)
        composed.to_plan(workflow,rig)
        with composed.supervised():
            published=workflow.step(rig.principal,rig.specimen_id)
        assert not model_errors and len(seen_geography)==1
        assert len(seen_geography[0].place_authority_ids)==2, 'town and municipality ambiguity is retained'
        assert published.run.fields['country'].normalized=='Guatemala'
        assert published.run.fields['province_state'].normalized=='Chimaltenango'
        assert published.run.fields['city'].normalized=='Yepocapa'
        assert published.run.fields['precise_location'].normalized=='Yepocapa'
        assert published.run.fields['country'].literal is None and published.run.fields['province_state'].literal is None
        assert published.run.fields['county'].state != ValueState.SUPPORTED
        assert published.run.disposition.value=='needs_human_review'
        binding=rig.fake.active_binding(rig.specimen_id)
        state=support.research_state(rig.fake,rig.specimen_id)[1]
        job=list(state['jobs'].values())[0]
        assert job['fields']['country']['work_state']=='resolved'
        assert job['fields']['province_state']['work_state']=='resolved'
        assert job['fields']['county']['work_state']=='waiting_policy'
        receipts=list(rig.fake.receipts.values())
        changed={row['causal_proof']['changed_field'] for row in receipts}
        assert {'country','province_state','city','precise_location'} <= changed
        assert not rig.fake.duplicates and len(nga.calls)==3
        assert len([url for url in rig.source_urls if url==RECORDED_URL])==3
        assert all(effect['status']=='completed' and effect['held_micro_usd']==0 for effect in state['effects'].values())
    finally:
        lifecycle.close()
