"""Exact scientific input/replay guards; all deciding receipts here are synthetic.

Names mirror the retained reader disagreement; none of the counterfactual
authority settlements below establishes a biological spelling or live result.
"""
import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.research_harness.accepted_output import (
    AcceptedCheckpointProofV1, AcceptedOutputProofV1, HISTORICAL_VALIDATOR_SOURCE_SHA256,
    VALIDATOR_SOURCE_SHA256, VALIDATOR_VERSION, read_accepted_checkpoint_proof,
    validation_boundary_pins,
)
from specimen_digitization.research_harness.contracts import (
    EvidenceItem, EventHypothesis, EventKind, FieldCheckpoint, FieldKey, FieldResolution,
    FragmentRelation, OrganiserCandidate, RelationKind,
    SourceCoverageReceipt, SourceCoverageState, SourceFragment, SourceResult,
    SpecialistRequest, SpecialistRole, ToolReceipt, WorkState, digest,
)
from specimen_digitization.research_harness.evidence import EvidenceError, assemble_field, validate_resolution
from specimen_digitization.research_harness.persistence import (
    ImmutableFileBlobs, StaleWork, canonical,
)
from test_specialist_feedback import graph_request


def request_for(readings=(('raw', 'Epipocus', 'raw_reading'),)):
    original = graph_request(SpecialistRole.TAXONOMY, FieldKey.TAXON, readings[0][1])
    fragments = []
    for observation, text, source in readings:
        offset = 0
        for order, line in enumerate(text.splitlines(keepends=True)):
            literal = line.rstrip('\r\n')
            fragments.append(SourceFragment(id=f'{observation}:{order}', scope=original.scope,
                asset_id='asset', asset_generation='1', asset_digest=digest('asset'), label_id='label',
                region_id='label', observation_id=observation, reader='reader', model_id='fixture',
                prompt_digest=digest('reader'), observation_text=text,
                observation_digest=hashlib.sha256(text.encode()).hexdigest(), start=offset,
                end=offset+len(literal), literal=literal, order=order, granularity='line', input_source=source))
            offset += len(line)
    return SpecialistRequest.model_validate({**original.model_dump(mode='json'),
        'fragments':[f.model_dump(mode='json') for f in fragments], 'assemblies':[], 'events':[],
        'evidence':[], 'organiser_candidates':[]})


def result_for(request, literal, authority='gbif:synthetic-same-authority', *, value='Epipocus'):
    evidence = EvidenceItem(id='evidence:'+literal, kind='source', source_id='gbif',
        locator='fixture://gbif', response_digest=digest(literal), source_version='fixture-v2',
        publisher_assertion_id='synthetic-only', excerpt=literal)
    result = SourceResult(status=LookupStatus.SUCCESS,
        coverage=SourceCoverageReceipt(source_id='gbif', field_key=FieldKey.TAXON,
            state=SourceCoverageState.SEARCHED, source_version='fixture-v2',
            coverage_limit='Synthetic scoped deciding result', reason='fixture-only'),
        evidence=(evidence,), candidate_json=(json.dumps({'field_key':'taxon', 'value':value,
            'authority_id':authority, 'authority_role':'decides', 'input_literal':literal}),))
    payload = json.dumps({'candidate_json':result.candidate_json,
        'evidence':[e.model_dump(mode='json') for e in result.evidence],
        'coverage':result.coverage.model_dump(mode='json'), 'status':str(result.status)},
        sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    receipt = ToolReceipt(id='receipt:'+literal, scope=request.scope, tool_id='gbif', source_id='gbif',
        field_keys=(FieldKey.TAXON,), effect_id=digest(literal), attempt_ids=(digest('attempt:'+literal),),
        request_digest=digest(literal), binding_digest=digest('binding'), outcome=LookupStatus.SUCCESS,
        effect_status='completed', evidence_ids=(evidence.id,), result_json=payload,
        result_digest=hashlib.sha256(payload.encode()).hexdigest())
    return result.model_copy(update={'receipt':receipt})


def resolution_for(request, results, *, observation='raw', literal='Epipocus'):
    producer = next(f for f in request.fragments if f.observation_id == observation and f.literal == literal)
    evidence = tuple(e.id for r in results for e in r.evidence)
    return FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.RESOLVED, value_layer='settled',
        value=FieldValue(state=ValueState.SUPPORTED, literal=literal, parsed='Epipocus', normalized='Epipocus',
            authority_id='gbif:synthetic-same-authority', input_source=producer.input_source,
            source_region_id=producer.region_id, source_observation_id=observation,
            verbatim_by_observation={observation:producer.observation_text},
            settled_observation_ids=[observation], evidence_ids=list(evidence),
            evidence_relations=dict.fromkeys(evidence, 'decides')),
        evidence_ids=evidence, reason='Synthetic exact deciding settlement')


def acceptance(request, resolution, results, **metadata):
    return AcceptedOutputProofV1(original_request=request, native_run_id=str(uuid4()),
        conversation_id='synthetic-test', resolutions=(resolution,), source_results=tuple(results),
        effect_ids=tuple(r.receipt.effect_id for r in results), model_settings_digest=digest('settings'),
        **validation_boundary_pins(), **metadata)


def test_zero_assemblies_cannot_waive_competing_decided_taxon():
    request = request_for((('raw', 'Epipocus', 'raw_reading'), ('decided', 'Epipsocus', 'decided_transcript')))
    result = result_for(request, 'Epipocus')
    resolution = resolution_for(request, (result,))
    assert not request.assemblies and not request.organiser_candidates
    with pytest.raises(EvidenceError, match='each independent taxon assertion'):
        validate_resolution(request, resolution, (result,))
    for version, sha in ((VALIDATOR_VERSION, VALIDATOR_SOURCE_SHA256),
        ('validate_resolution/v1', HISTORICAL_VALIDATOR_SOURCE_SHA256)):
        with pytest.raises(ValidationError, match='each independent taxon assertion'):
            acceptance(request, resolution, (result,), validator_version=version, validator_source_sha256=sha)


@pytest.mark.parametrize('readings', (
    (('raw', 'Epipocus', 'raw_reading'),),
    (('raw', 'Epipocus', 'raw_reading'), ('other', 'Epipocus', 'raw_reading')),
    (('raw', 'Epipocus', 'raw_reading'), ('decided', 'Epipocus', 'decided_transcript')),
    (('raw', 'Guatemala\nEpipocus\nTrap', 'raw_reading'),
        ('decided', 'Guatemala\nEpipocus\nTrap', 'decided_transcript')),
))
def test_raw_only_unanimous_and_ordinary_other_lines_remain_valid(readings):
    request = request_for(readings); result = result_for(request, 'Epipocus')
    resolution = resolution_for(request, (result,))
    assert validate_resolution(request, resolution, (result,)) == resolution
    assert acceptance(request, resolution, (result,)).validator_version == VALIDATOR_VERSION


def test_two_counterfactual_deciding_queries_must_reconcile_to_same_authority():
    request = request_for((('raw', 'Epipocus', 'raw_reading'), ('decided', 'Epipsocus', 'decided_transcript')))
    results = (result_for(request, 'Epipocus'), result_for(request, 'Epipsocus'))
    resolution = resolution_for(request, results)
    assert validate_resolution(request, resolution, results) == resolution
    other = result_for(request, 'Epipsocus', authority='gbif:synthetic-other')
    # Only the deciding evidence for the requested value is cited; an unrelated
    # authority cannot silently settle the competing reader assertion.
    with pytest.raises(EvidenceError, match='each independent taxon assertion'):
        validate_resolution(request, resolution_for(request, results[:1]), (results[0], other))


def test_independent_located_taxon_on_another_label_cannot_be_omitted():
    request = request_for((('raw', 'Epipocus', 'raw_reading'),))
    another = request.fragments[0].model_copy(update={'id':'another', 'region_id':'other-label',
        'label_id':'other-label', 'observation_id':'other', 'literal':'Epipsocus', 'observation_text':'Epipsocus',
        'observation_digest':hashlib.sha256(b'Epipsocus').hexdigest(), 'end':9})
    candidate = OrganiserCandidate(id='taxon-hint', field_key=FieldKey.TAXON, literal='Epipsocus',
        source='extractor', status='located', reason='no_taxon_assembly', region_id='other-label',
        observation_id='other', start=0, end=9)
    request = SpecialistRequest.model_validate({**request.model_dump(mode='json'),
        'fragments':[f.model_dump(mode='json') for f in (*request.fragments, another)],
        'organiser_candidates':[candidate.model_dump(mode='json')]})
    first = result_for(request, 'Epipocus')
    with pytest.raises(EvidenceError, match='each independent taxon assertion'):
        validate_resolution(request, resolution_for(request, (first,)), (first,))
    results = (first, result_for(request, 'Epipsocus'))
    assert validate_resolution(request, resolution_for(request, results), results)


def test_complete_accepted_taxon_assembly_remains_a_grounded_producer():
    request = graph_request(SpecialistRole.TAXONOMY, FieldKey.TAXON, 'Epipocus')
    result = result_for(request,'Epipocus')
    resolution = resolution_for(request,(result,),observation='raw-reading')
    resolution.value.source_observation_id = None
    resolution.value.input_source = None
    resolution = resolution.model_copy(update={'assembly_ids':('accepted-assembly',), 'event_id':'accepted-event'})
    assert validate_resolution(request,resolution,(result,)) == resolution


def complementary_request(*names):
    request = request_for()
    fragments, events, relations, assemblies = [], [], [], []
    for i, name in enumerate(names):
        observation = 'assembled:'+str(i)
        parts = []
        start = 0
        for j, word in enumerate(name.split()):
            part = request.fragments[0].model_copy(update={'id':f'{observation}:{j}',
                'observation_id':observation,'observation_text':name,
                'observation_digest':hashlib.sha256(name.encode()).hexdigest(),
                'literal':word,'start':start,'end':start+len(word),'order':j,'granularity':'span'})
            start += len(word)+1; parts.append(part)
        event = EventHypothesis(id='event:'+observation,scope=request.scope,kind=EventKind.DETERMINATION,
            fragment_ids=tuple(p.id for p in parts),evidence_ids=('fixture-only',),
            reason='Synthetic accepted assertion',status='accepted',validator_version='fixture-v1')
        relation = FragmentRelation(id='relation:'+observation,scope=request.scope,
            fragment_ids=event.fragment_ids,kind=RelationKind.CONTINUATION,event_id=event.id,
            evidence_ids=('fixture-only',),reason='Synthetic exact word continuation',
            proposer_version='fixture-v1',validator_version='fixture-v1',status='accepted')
        assembly = assemble_field(assembly_id='assembly:'+observation,scope=request.scope,field_key=FieldKey.TAXON,
            fragments=parts,event=event,relations=(relation,),assertion_kind='complementary')
        fragments.extend(parts);events.append(event);relations.append(relation);assemblies.append(assembly)
    return SpecialistRequest.model_validate({**request.model_dump(mode='json'),
        'fragments':[f.model_dump(mode='json') for f in fragments],
        'events':[e.model_dump(mode='json') for e in events],
        'relations':[r.model_dump(mode='json') for r in relations],
        'assemblies':[a.model_dump(mode='json') for a in assemblies]})


def assembled_resolution(request, results):
    # A source-supported species retains a truthful reading selector as well
    # as its complete accepted word-span assembly, not a standalone genus.
    ids = tuple(e.id for result in results for e in result.evidence)
    return FieldResolution(field_key=FieldKey.TAXON,work_state=WorkState.RESOLVED,value_layer='settled',
        value=FieldValue(state=ValueState.SUPPORTED,parsed='Danaus plexippus',authority_id='gbif:synthetic-same-authority',
            source_observation_id='assembled:0',source_region_id='label',input_source='raw_reading',
            verbatim_by_observation={'assembled:0':request.fragments[0].observation_text},
            settled_observation_ids=['assembled:0'],evidence_ids=list(ids),evidence_relations=dict.fromkeys(ids,'decides')),
        evidence_ids=ids,assembly_ids=tuple(a.id for a in request.assemblies),
        event_id=request.assemblies[0].event_id,reason='Synthetic assembled source settlement')


def test_valid_complete_word_span_assembly_and_truthful_reading_selector_coexist():
    request = complementary_request('Danaus plexippus')
    result = result_for(request,'Danaus plexippus',value='Danaus plexippus');resolution = assembled_resolution(request,(result,))
    assert validate_resolution(request,resolution,(result,)) == resolution
    assert acceptance(request,resolution,(result,))
    assert not any(json.loads(c)['input_literal'] in {'Danaus','plexippus'} for c in result.candidate_json)


@pytest.mark.parametrize('mutation', ('observation','region','input_source','verbatim','partial_query','unreadable'))
def test_complete_assembly_cannot_launder_a_mismatched_declared_producer(mutation):
    request = complementary_request('Danaus plexippus');result = result_for(request,'Danaus plexippus',value='Danaus plexippus')
    resolution = assembled_resolution(request,(result,))
    if mutation == 'observation':resolution.value.source_observation_id='foreign'
    elif mutation == 'region':resolution.value.source_region_id='foreign'
    elif mutation == 'input_source':resolution.value.input_source='decided_transcript'
    elif mutation == 'verbatim':resolution.value.verbatim_by_observation={'assembled:0':'not the original'}
    elif mutation == 'partial_query':result = result_for(request,'Danaus',value='Danaus plexippus');resolution=assembled_resolution(request,(result,))
    elif mutation == 'unreadable':
        parts=list(request.fragments);parts[-1]=parts[-1].model_copy(update={'unreadable':True})
        request=request.model_copy(update={'fragments':tuple(parts)})
    with pytest.raises(EvidenceError,match='G32'):
        validate_resolution(request,resolution,(result,))


def test_competing_complete_assembly_needs_its_own_deciding_settlement():
    request = complementary_request('Danaus plexippus','Danaus chrysippus')
    first = result_for(request,'Danaus plexippus',value='Danaus plexippus')
    with pytest.raises(EvidenceError,match='each independent taxon assertion'):
        validate_resolution(request,assembled_resolution(request,(first,)),(first,))
    # Explicit counterfactual synonym settlement, not a biological assertion.
    results=(first,result_for(request,'Danaus chrysippus',value='Danaus plexippus'))
    assert validate_resolution(request,assembled_resolution(request,results),results)


@pytest.mark.parametrize('literal', ('Epipocus sp. 1', 'Epipocus Sp.#1', 'Epipocus sp. 1 det. Mockford'))
@pytest.mark.parametrize('query_form', ('full_literal', 'exact_parser_projection'))
def test_established_morphospecies_grammar_preserves_literal_and_genus_projection(literal, query_form):
    request = request_for((('raw',literal,'raw_reading'),))
    query = literal if query_form == 'full_literal' else 'Epipocus'
    result = result_for(request,query)
    resolution = resolution_for(request,(result,),literal=literal)
    before = resolution.model_dump(mode='json')
    assert validate_resolution(request,resolution,(result,)) == resolution
    assert resolution.model_dump(mode='json') == before
    assert resolution.value.literal == literal and resolution.value.verbatim_by_observation == {'raw':literal}


def test_split_morphospecies_annotation_is_retained_in_the_complete_reading():
    request = request_for((('raw','Epipocus\nSp. 1','raw_reading'),))
    result = result_for(request,'Epipocus'); resolution = resolution_for(request,(result,))
    assert validate_resolution(request,resolution,(result,)) == resolution
    assert resolution.value.verbatim_by_observation == {'raw':'Epipocus\nSp. 1'}


def test_projection_cannot_invent_an_unwritten_authorship_suffix():
    request = request_for()
    results = (result_for(request,'Epipocus'),result_for(request,'Epipocus det. Invented'))
    with pytest.raises(EvidenceError,match='exact grounded assertion'):
        validate_resolution(request,resolution_for(request,results),results)


@pytest.mark.parametrize('mutation', ('substring', 'producer', 'route', 'unreadable', 'shifted'))
def test_query_and_producer_cannot_escape_exact_complete_assertion(mutation):
    text = 'Epipocus plexippus' if mutation == 'substring' else 'Epipocus'
    request = request_for((('raw', text, 'raw_reading'),))
    result = result_for(request, 'Epipocus')
    resolution = resolution_for(request, (result,), literal=text)
    if mutation == 'producer':
        resolution.value.source_observation_id = 'foreign'
    elif mutation == 'route':
        resolution.value.input_source = 'decided_transcript'
    elif mutation == 'unreadable':
        request = request.model_copy(update={'fragments':(request.fragments[0].model_copy(update={'unreadable':True}),)})
    elif mutation == 'shifted':
        request = request_for((('raw','Epipocus','raw_reading'), ('decided','Trap\nEpipsocus','decided_transcript')))
        result = result_for(request,'Epipocus'); resolution = resolution_for(request,(result,))
    with pytest.raises(EvidenceError, match='G32'):
        validate_resolution(request, resolution, (result,))


@pytest.mark.parametrize('missing', ('both','region','input_source'))
def test_three_field_raw_producer_and_either_optional_declaration_remain_valid(missing):
    request=request_for();result=result_for(request,'Epipocus');resolution=resolution_for(request,(result,))
    if missing in {'both','region'}:resolution.value.source_region_id=None
    if missing in {'both','input_source'}:resolution.value.input_source=None
    before=resolution.model_dump(mode='json')
    assert validate_resolution(request,resolution,(result,)) == resolution
    assert resolution.model_dump(mode='json') == before  # No invented metadata.


@pytest.mark.parametrize('global_route', (None,'decided_transcript','raw_reading'))
def test_per_observation_route_override_uses_the_canonical_effective_declaration(global_route):
    request=request_for();result=result_for(request,'Epipocus');resolution=resolution_for(request,(result,))
    resolution.value.input_source=global_route
    resolution.value.input_source_by_observation={'raw':'raw_reading'}
    assert validate_resolution(request,resolution,(result,)) == resolution


@pytest.mark.parametrize('mutation', ('region','global_route','per_observation_route','ambiguous_region',
    'ambiguous_route','ambiguous_body','ambiguous_asset','ambiguous_reader'))
def test_optional_metadata_never_waives_provided_or_original_identity_contradictions(mutation):
    request=request_for();result=result_for(request,'Epipocus');resolution=resolution_for(request,(result,))
    resolution.value.source_region_id=None;resolution.value.input_source=None
    if mutation=='region':resolution.value.source_region_id='foreign'
    elif mutation=='global_route':resolution.value.input_source='decided_transcript'
    elif mutation=='per_observation_route':resolution.value.input_source_by_observation={'raw':'decided_transcript'}
    else:
        changed=request.fragments[0].model_copy(update={'id':'other-original-fragment'})
        if mutation=='ambiguous_region':changed=changed.model_copy(update={'region_id':'foreign'})
        elif mutation=='ambiguous_route':changed=changed.model_copy(update={'input_source':'decided_transcript'})
        elif mutation=='ambiguous_body':
            text='Epipocus\nDifferent original body'
            changed=changed.model_copy(update={'observation_text':text,'observation_digest':hashlib.sha256(text.encode()).hexdigest()})
        elif mutation=='ambiguous_asset':changed=changed.model_copy(update={'asset_id':'foreign'})
        elif mutation=='ambiguous_reader':changed=changed.model_copy(update={'reader':'foreign'})
        request=SpecialistRequest.model_validate({**request.model_dump(mode='json'),
            'fragments':[f.model_dump(mode='json') for f in (*request.fragments,changed)]})
    with pytest.raises(EvidenceError,match='identity is not uniquely proved'):
        validate_resolution(request,resolution,(result,))


def test_unresolved_disagreement_is_preserved_without_fabricated_settlement():
    request = request_for((('raw','Epipocus','raw_reading'), ('decided','Epipsocus','decided_transcript')))
    resolution = FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.WAITING_SOURCE,
        value=FieldValue(state=ValueState.UNRESOLVED), reason='retained unavailable lookup')
    assert validate_resolution(request, resolution) == resolution


def test_reordered_taxon_cannot_hide_behind_a_different_line_query():
    request = request_for((('raw','Epipocus\nOthergenus','raw_reading'),
        ('decided','Othergenus\nEpipsocus','decided_transcript')))
    results = (result_for(request,'Epipocus'),result_for(request,'Othergenus'))
    with pytest.raises(EvidenceError,match='alignment'):
        validate_resolution(request,resolution_for(request,results),results)


def test_unanimous_taxon_does_not_infer_taxonomy_from_differing_locality():
    request = request_for((('raw','Guatemala\nEpipocus\n4800 ft','raw_reading'),
        ('decided','Guatemalla\nEpipocus\n4800 feet','decided_transcript')))
    result = result_for(request,'Epipocus')
    assert validate_resolution(request,resolution_for(request,(result,)),(result,))


def test_explicit_non_taxon_field_is_not_a_genus_producer():
    request = request_for()
    original = request.fragments[0]
    text = 'country:Epipocus'
    fragment = original.model_copy(update={'observation_text':text,
        'observation_digest':hashlib.sha256(text.encode()).hexdigest(), 'start':8, 'end':len(text)})
    request = request.model_copy(update={'fragments':(fragment,)})
    result = result_for(request,'Epipocus')
    with pytest.raises(EvidenceError,match='exact declared reading'):
        validate_resolution(request,resolution_for(request,(result,)),(result,))


@pytest.mark.parametrize('metadata', (
    {'validator_version':'validate_resolution/v1', 'validator_source_sha256':VALIDATOR_SOURCE_SHA256},
    {'validator_version':VALIDATOR_VERSION, 'validator_source_sha256':HISTORICAL_VALIDATOR_SOURCE_SHA256},
    {'validator_version':'validate_resolution/v99', 'validator_source_sha256':VALIDATOR_SOURCE_SHA256},
    {'validator_version':VALIDATOR_VERSION, 'validator_source_sha256':digest('unknown')},
))
def test_only_exact_known_validator_pairs_decode(metadata):
    request = request_for(); result = result_for(request,'Epipocus')
    with pytest.raises(ValidationError):
        acceptance(request, resolution_for(request,(result,)), (result,), **metadata)


def test_exact_historical_proof_read_joins_old_pins_and_preserves_body(tmp_path):
    request = request_for(); result = result_for(request,'Epipocus')
    accepted = acceptance(request, resolution_for(request,(result,)), (result,),
        validator_version='validate_resolution/v1', validator_source_sha256=HISTORICAL_VALIDATOR_SOURCE_SHA256)
    # Original engine/journal hashes are retained, not rewritten as installed bytes.
    accepted = AcceptedOutputProofV1.model_validate({**accepted.model_dump(mode='json'),
        'engine_source_sha256':digest('historical engine'), 'journal_source_sha256':digest('historical journal')})
    checkpoint = FieldCheckpoint(scope=request.scope, field_key=FieldKey.TAXON, revision=1,
        resolution=accepted.resolutions[0], prompt_digest=request.prompt.digest,
        source_registry_digest=request.prompt.source_registry_digest,
        model_settings_digest=accepted.model_settings_digest, effect_receipt_ids=accepted.effect_ids)
    proof = AcceptedCheckpointProofV1(acceptance=accepted, checkpoints=(checkpoint,))
    raw = canonical(proof.model_dump(mode='json')); blobs = ImmutableFileBlobs(tmp_path/'blobs')
    ref = blobs.put_at('accepted.json',raw)
    binding = {'proof_digest':proof.proof_digest, 'native_run_id':accepted.native_run_id,
        'conversation_id':accepted.conversation_id, 'agent_name':str(request.role), 'request_digest':digest(request),
        'capture':vars(ref), 'checkpoint_payload_digests':[digest(checkpoint)]}
    native = {'id':'checkpoint','scope':request.scope.model_dump(mode='json'),
        'payload':checkpoint.model_dump(mode='json'),'accepted_output_proof':binding}
    boundary = {'contract_version':'research-acceptance-boundary/v1',
        'validator_version':accepted.validator_version, 'validator_source_sha256':accepted.validator_source_sha256,
        'engine_source_sha256':accepted.engine_source_sha256,'journal_source_sha256':accepted.journal_source_sha256}
    job = {'checkpoints':[native], 'pins':{'sources':{'acceptance_boundary':boundary}}}
    state = {'journal':{accepted.native_run_id:{'scope':native['scope'],'agent_name':str(request.role),
        'record':{'conversation_id':accepted.conversation_id}, 'accepted_outputs':{
            proof.proof_digest:{'proof':binding,'checkpoint_ids':['checkpoint']}}}}, 'budget_policy':{'live_authorized':True}}
    store = SimpleNamespace(_read=lambda scope:SimpleNamespace(state=state), _job=lambda state,scope:job)
    assert read_accepted_checkpoint_proof(store, request.scope, blobs, 'checkpoint') == proof
    assert blobs.get(ref) == raw and canonical(proof.model_dump(mode='json')) == raw
    before = copy.deepcopy(state), copy.deepcopy(job)
    job['pins']['sources']['acceptance_boundary'] = {**boundary,'validator_source_sha256':VALIDATOR_SOURCE_SHA256}
    with pytest.raises(StaleWork,match='source_boundary_unqualified'):
        read_accepted_checkpoint_proof(store, request.scope, blobs, 'checkpoint')
    assert state == before[0] and blobs.get(ref) == raw


def test_journal_cannot_mint_a_new_historical_tagged_capture(tmp_path):
    from test_research_harness_journal import setup
    _, requests, journal, settings = setup(tmp_path)
    request = requests[SpecialistRole.TAXONOMY]
    resolution = FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.WAITING_SOURCE,
        value=FieldValue(), reason='No qualified source')
    proof = AcceptedOutputProofV1(original_request=request, native_run_id=str(uuid4()),
        conversation_id='synthetic',resolutions=(resolution,),source_results=(),effect_ids=(),
        model_settings_digest=settings,**validation_boundary_pins(),validator_version='validate_resolution/v1',
        validator_source_sha256=HISTORICAL_VALIDATOR_SOURCE_SHA256)
    blobs = ImmutableFileBlobs(tmp_path/'blobs'); journal.blobs = blobs
    before = copy.deepcopy(journal.store._read(journal.scope).state)
    with pytest.raises(StaleWork,match='accepted_output_checkpoint_binding_invalid'):
        asyncio.run(journal.commit(request,(resolution,),receipt_ids=(),model_settings_digest=settings,
            accepted_output=proof))
    assert journal.store._read(journal.scope).state == before
    assert not list((tmp_path/'blobs').iterdir())


@pytest.mark.parametrize('mutation', ('old_validator', 'unknown_journal', 'missing_live'))
def test_retained_job_boundary_blocks_before_harness_or_blob_creation(tmp_path, mutation):
    from dataclasses import replace
    from test_research_harness_journal import setup
    current = {'contract_version':'research-acceptance-boundary/v1',
        'validator_version':VALIDATOR_VERSION,'validator_source_sha256':VALIDATOR_SOURCE_SHA256,
        **validation_boundary_pins()}
    bad = dict(current)
    if mutation == 'old_validator':
        bad.update(validator_version='validate_resolution/v1',validator_source_sha256=HISTORICAL_VALIDATOR_SOURCE_SHA256)
    elif mutation == 'unknown_journal':
        bad['journal_source_sha256'] = digest('unknown journal')
    def alter(pins):
        sources = {**pins.sources, **({'acceptance_boundary':bad} if mutation != 'missing_live' else {})}
        return replace(pins,sources=sources)
    _, requests, journal, settings = setup(tmp_path,alter)
    if mutation == 'missing_live':
        # Synthetic local state flag only; no live credential, provider or native
        # authority is constructed. The existing scoped SQLite CAS is real.
        journal.store._mutate(journal.scope,lambda state,now:state['budget_policy'].update(live_authorized=True))
    before = copy.deepcopy(journal.store._read(journal.scope).state)
    with pytest.raises(StaleWork,match='journal_acceptance_boundary_mismatch'):
        asyncio.run(journal.validate_request(requests[SpecialistRole.TAXONOMY],model_settings_digest=settings))
    assert journal.store._read(journal.scope).state == before


def test_current_retained_boundary_admits_the_existing_nonlive_request(tmp_path):
    from dataclasses import replace
    from test_research_harness_journal import setup
    current = {'contract_version':'research-acceptance-boundary/v1',
        'validator_version':VALIDATOR_VERSION,'validator_source_sha256':VALIDATOR_SOURCE_SHA256,
        **validation_boundary_pins()}
    _,requests,journal,settings=setup(tmp_path,lambda pins:replace(pins,sources={**pins.sources,'acceptance_boundary':current}))
    asyncio.run(journal.validate_request(requests[SpecialistRole.TAXONOMY],model_settings_digest=settings))
