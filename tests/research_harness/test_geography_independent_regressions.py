"""Geography research reuses related captures and rejects contradicted event context.

All sources and dependency proofs are offline fixtures. No scientific/live claim.
"""

import asyncio
import hashlib
import json
from dataclasses import replace

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.research_harness.contracts import (
    EventHypothesis, EventKind, EvidenceItem, FieldKey, SourceFragment, SourceQuery,
)
from specimen_digitization.research_harness.evidence import assemble_field
from specimen_digitization.research_harness.geography_context import (
    accepted_collecting_context, hierarchy_research,
)
from specimen_digitization.research_harness.geography_strategy import SourceAttempt, geography_progress
from test_geography_context import PIN, SCOPE, TOWN, accepted_dependency, captured, request
from test_geography_strategy import capture


@pytest.mark.parametrize('narrowed', [False, True])
def test_captured_city_hierarchy_is_reused_for_a_related_province_no_match(narrowed):
    req = request()
    history = captured()
    required = next(query for query in hierarchy_research(req, (history,)).next_queries
                    if query.field_key == FieldKey.PROVINCE_STATE)
    if narrowed:
        req = req.model_copy(update={'field_keys': (FieldKey.PROVINCE_STATE,)})
    no_match = capture(req.model_copy(update={'field_keys': (FieldKey.PROVINCE_STATE,)}), 'geolocate')
    attempts = (
        SourceAttempt(SourceQuery(source_id='nga', field_key=FieldKey.CITY, query_text='Yepocapa'), history),
        SourceAttempt(required, no_match),
    )
    result = geography_progress(req, FieldKey.PROVINCE_STATE, attempts, ('geolocate', 'nga'))
    assert result.review_eligible, result
    assert result.stop_reason == 'scoped_absence_or_semantic_ambiguity_after_relevant_strategies'
    assert history.evidence[0].id in result.evidence_ids


def test_unrelated_city_capture_cannot_close_a_province_research_strategy():
    req = request()
    history = captured(replace(TOWN, name='Guatemala City'), written='Guatemala City')
    lookup = SourceQuery(source_id='geolocate', field_key=FieldKey.PROVINCE_STATE,
        query_text=json.dumps({'country':'Guatemala', 'place':'Yepocapa', 'locality':'Yepocapa',
                              'value':'Chimaltenango'}))
    no_match = capture(req.model_copy(update={'field_keys': (FieldKey.PROVINCE_STATE,)}), 'geolocate')
    result = geography_progress(req, FieldKey.PROVINCE_STATE, (
        SourceAttempt(SourceQuery(source_id='nga', field_key=FieldKey.CITY, query_text='Guatemala City'), history),
        SourceAttempt(lookup, no_match),
    ), ('geolocate','nga'))
    assert not result.review_eligible
    assert result.stop_reason == 'relevant_place_name_alternative_remaining'


def locality_request(event_kind, *, event_id='other-locality-event'):
    proof, pin = accepted_dependency()
    text = 'Yepocapa'
    evidence = EvidenceItem(id='place-evidence', kind='literal', source_id='offline_fixture',
        locator='fixture://place', response_digest=PIN, source_version='fixture-v1', publisher_assertion_id='fixture-only', excerpt=text)
    fragment = SourceFragment(id='locality-fragment', scope=SCOPE, asset_id='asset', asset_generation='1',
        asset_digest=PIN, label_id='place-label', region_id='place-region', observation_id='place-reading',
        reader='fixture', model_id='fixture', prompt_digest=PIN, observation_text=text,
        observation_digest=hashlib.sha256(text.encode()).hexdigest(), start=0,end=len(text),
        literal=text, order=0)
    event = EventHypothesis(id=event_id,scope=SCOPE,kind=event_kind,fragment_ids=(fragment.id,),
        evidence_ids=(evidence.id,),reason='Explicit event-specific locality fixture',status='accepted',
        validator_version='fixture-event-v1')
    assembly = assemble_field(assembly_id='place-assembly',scope=SCOPE,field_key=FieldKey.CITY,
        fragments=(fragment,),event=event)
    req = request(dependencies=(pin,), fragments=(fragment,), events=(event,),
        assemblies=(assembly,),evidence=(evidence,))
    return req, accepted_collecting_context(req,(proof,))


@pytest.mark.parametrize('kind', [EventKind.COLLECTING,EventKind.DETERMINATION,EventKind.PREPARATION])
def test_accepted_date_for_another_event_cannot_select_a_historical_locality(kind):
    req, context = locality_request(kind)
    source = captured(replace(TOWN,valid_from='1940',valid_to='1950'))
    result = hierarchy_research(req,(source,),context=context)
    assert result.proposals == result.next_queries == (), result
    assert set(reason for _,reason in result.unresolved) == {'historical_locality_event_context_unqualified'}


def test_same_accepted_collecting_event_can_supply_historical_date_context():
    req,context = locality_request(EventKind.COLLECTING,event_id='collecting-event')
    result = hierarchy_research(req,(captured(replace(TOWN,valid_from='1940',valid_to='1950')),),context=context)
    assert {proposal.field_key for proposal in result.proposals} == {FieldKey.COUNTRY,FieldKey.PROVINCE_STATE}


def test_unrelated_dependency_does_not_prevent_undated_captured_hierarchy_research():
    req,context = locality_request(EventKind.COLLECTING)
    result = hierarchy_research(req,(captured(),),context=context)
    assert {proposal.field_key for proposal in result.proposals} == {FieldKey.COUNTRY,FieldKey.PROVINCE_STATE}


def test_prior_city_capture_authorizes_hierarchy_validation_after_checkpoint_narrowing():
    from specimen_digitization.research_harness.sources import FixtureSourceTransport, SourceBroker
    from test_geolocate_capture import RECORDED_BODY
    from test_geolocate_validator import REGISTRY, completed_effect, geography_request
    req = geography_request(scope=SCOPE).model_copy(update={'field_keys': (FieldKey.PROVINCE_STATE,)})
    history = captured()
    query = hierarchy_research(req, (history,)).next_queries[0]
    calls = []

    async def read(url, policy):
        calls.append(url)
        return 200, RECORDED_BODY

    broker = SourceBroker(REGISTRY, transport=FixtureSourceTransport(read), effect_dispatch=completed_effect)
    broker.trusted_results.append(history)
    result = asyncio.run(broker.query_source(req, query))
    assert result.status == LookupStatus.SUCCESS, result.coverage.reason
    assert result.coverage.field_key == FieldKey.PROVINCE_STATE
    assert len(calls) == 1


@pytest.mark.parametrize('place,waiting', [('Yepocapa', True), ('Guatemala City', False)])
def test_only_relevant_sibling_source_failures_hold_target_research(place, waiting):
    req = request()
    query = hierarchy_research(req,(captured(),)).next_queries[1]
    target = capture(req.model_copy(update={'field_keys':(FieldKey.PROVINCE_STATE,)}),'geolocate')
    prior = capture(req.model_copy(update={'field_keys':(FieldKey.CITY,)}),'nga',LookupStatus.TIMEOUT)
    result = geography_progress(req,FieldKey.PROVINCE_STATE,(
        SourceAttempt(SourceQuery(source_id='nga',field_key=FieldKey.CITY,query_text=place),prior),
        SourceAttempt(query,target),
    ),('geolocate','nga'))
    assert (result.state == 'waiting_source') is waiting
    assert not result.review_eligible


def test_sibling_deciding_success_never_settles_a_missing_province_lookup():
    req = request()
    sibling = capture(req.model_copy(update={'field_keys':(FieldKey.CITY,)}),'geolocate',LookupStatus.SUCCESS,
        ({'field_key':'city','value':'Yepocapa','authority_id':'geolocate:fixture'},))
    query = SourceQuery(source_id='geolocate',field_key=FieldKey.CITY,
        query_text=json.dumps({'country':'Guatemala','place':'Yepocapa','locality':'Yepocapa','value':'Yepocapa'}))
    result = geography_progress(req,FieldKey.PROVINCE_STATE,(SourceAttempt(query,sibling),),('geolocate','nga'))
    assert result.state == 'research_pending' and not result.review_eligible
    assert result.next_sources == ('geolocate',)
