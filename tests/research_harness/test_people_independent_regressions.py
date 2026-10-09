"""Trusted decided people spans qualify while raw alternatives remain preserved."""

import pytest

from specimen_digitization.application.domain import ValueState
from specimen_digitization.research_harness.contracts import EventHypothesis, EventKind, FieldKey, SourceFragment, SpecialistRole
from specimen_digitization.research_harness.evidence import EvidenceError, assemble_field, missing_irn_resolution, validate_resolution
from specimen_digitization.research_harness.people import collector_resolution
from test_organiser_raw_reading_evidence import Label, build, candidates, request_for, two_labels
from test_people_evidence import collector_assemblies, recovery_fixture


def decided_fixture(decided, *, unreadable=()):
    first, second = 'forest\nCollectors: J. Smith', 'forest\nCollectors: J. Smyth'
    # Native organiser names put the chosen reading first. Quote the actual
    # observation each name identifies, including when Muse is selected.
    quotes = (second, first) if decided == 'b' else (first, second)
    return build(two_labels(a=first,b=second,decided=decided,unreadable=unreadable),
        [('habitat',name,'forest',quote) for name,quote in zip(('2A','2B'),quotes)])


@pytest.mark.parametrize('decided,expected', [('a','J. Smith'), ('b','J. Smyth')])
def test_decided_collector_span_recovers_without_discarding_disagreeing_raw_reader(decided,expected):
    built = decided_fixture(decided)
    [assembly] = collector_assemblies(built)
    req = request_for(built,SpecialistRole.PARTIES)
    result = collector_resolution(req,assembly_id=assembly.id)
    assert result.value.normalized == expected
    assert result.value.state == ValueState.SUPPORTED
    rows = candidates(built,'collectors')
    assert {row.literal for row in rows} == {'J. Smith','J. Smyth'}
    assert len([row for row in rows if row.status == 'grounded']) == 1
    assert any(row.status == 'located' and row.literal != expected for row in rows)
    [fragment] = [row for row in req.fragments if row.id in assembly.fragment_ids]
    assert fragment.input_source == 'decided_transcript'
    assert result.value.verbatim_by_observation == {fragment.observation_id:fragment.observation_text}
    assert any('J. Smith' in row.observation_text for row in req.fragments)
    assert any('J. Smyth' in row.observation_text for row in req.fragments)
    assert validate_resolution(req,missing_irn_resolution()).value.state == ValueState.UNKNOWN


@pytest.mark.parametrize('other', ['Prep. J. Smyth','Det. J. Smyth','Locality: Smith','forest'])
def test_decided_collecting_role_does_not_require_an_unselected_reader_to_find_the_same_role(other):
    built = recovery_fixture('Collectors: J. Smith',other=other,decided='a')
    [assembly] = collector_assemblies(built)
    result = collector_resolution(request_for(built,SpecialistRole.PARTIES),assembly_id=assembly.id)
    assert result.value.normalized == 'J. Smith'


def test_decided_preparer_or_determiner_cannot_be_overruled_by_a_raw_collector_guess():
    for selected in ('Prep. J. Smith','Det. J. Smith','Locality: Smith'):
        built = recovery_fixture('Collectors: J. Smith',other=selected,decided='b')
        assert not collector_assemblies(built)
        assert all(row.status != 'grounded' for row in candidates(built,'collectors'))


def test_missing_native_quote_does_not_become_grounded_merely_because_reading_is_decided():
    built = recovery_fixture('Collectors: J. Smith',other='Collectors: J. Smyth',decided='a',quote=False)
    assert not collector_assemblies(built)
    assert any(row.reason == 'native_literal_evidence_unavailable' for row in candidates(built,'collectors'))


def test_a_decided_label_does_not_hide_a_different_labels_collector_without_an_event_join():
    labels = (Label('Collectors: J. Smith',decided='a'),Label('Collectors: A. Brown',decided='a'))
    answers = [('habitat',name,'Smith' if name.startswith('1') else 'Brown',
        'Collectors: J. Smith' if name.startswith('1') else 'Collectors: A. Brown')
        for name in ('1A','1B','2A','2B')]
    built = build(labels,answers)
    assert not collector_assemblies(built)
    assert {row.literal for row in candidates(built,'collectors')} == {'J. Smith','A. Brown'}


def test_unselected_unreadable_raw_span_does_not_invalidate_a_clean_decided_collector():
    built = decided_fixture('b',unreadable=('J. Smith',))
    [assembly] = collector_assemblies(built)
    result = collector_resolution(request_for(built,SpecialistRole.PARTIES),assembly_id=assembly.id)
    assert result.value.normalized == 'J. Smyth'
    assert any(fragment.unreadable for fragment in built.graph[0])


def test_selected_unreadable_span_stays_unqualified_and_is_preserved():
    built = decided_fixture('a',unreadable=('J. Smith',))
    assert not collector_assemblies(built)
    assert any(row.reason == 'reading_has_unreadable_spans' for row in candidates(built,'collectors'))


def test_validator_cannot_publish_a_raw_collector_span_over_a_decided_preparer():
    raw,decided = 'forest\nCollectors: J. Smith','forest\nPrep. J. Smith'
    built = build(two_labels(a=raw,b=decided,decided='b'),
        [('habitat','2A','forest',decided),('habitat','2B','forest',raw)])
    req = request_for(built,SpecialistRole.PARTIES)
    original = next(fragment for fragment in req.fragments if fragment.input_source == 'raw_reading'
                    and fragment.observation_text == raw)
    start = raw.index('J. Smith')
    fragment = SourceFragment.model_validate(original.model_copy(update={'id':'false-raw-collector',
        'start':start,'end':start+len('J. Smith'),'literal':'J. Smith','granularity':'span'}).model_dump())
    ids = tuple(row.id for row in req.evidence if row.excerpt == raw)
    event = EventHypothesis(id='false-collecting-event',scope=req.scope,kind=EventKind.COLLECTING,
        fragment_ids=(fragment.id,),evidence_ids=ids,status='accepted',validator_version='fixture-only',
        reason='Deliberately wrong extractor assignment of the unselected raw span')
    assembly = assemble_field(assembly_id='false-collecting-assembly',scope=req.scope,field_key=FieldKey.COLLECTORS,
        fragments=(fragment,),event=event)
    req = req.model_copy(update={'fragments':(*req.fragments,fragment),
        'events':(*req.events,event),'assemblies':(*req.assemblies,assembly)})
    with pytest.raises(EvidenceError,match='decided reading'):
        collector_resolution(req,assembly_id=assembly.id)


def test_validator_refuses_an_unreadable_selected_span_even_if_factory_was_bypassed():
    built = decided_fixture('a')
    [assembly] = collector_assemblies(built)
    req = request_for(built,SpecialistRole.PARTIES)
    req = req.model_copy(update={'fragments':tuple(fragment.model_copy(update={'unreadable':True})
        if fragment.id in assembly.fragment_ids else fragment for fragment in req.fragments)})
    with pytest.raises(EvidenceError,match='unreadable'):
        collector_resolution(req,assembly_id=assembly.id)


def test_multiple_decided_readings_cannot_silently_choose_one_collector():
    built = decided_fixture('a')
    [assembly] = collector_assemblies(built)
    req = request_for(built,SpecialistRole.PARTIES)
    req = req.model_copy(update={'fragments':tuple(fragment.model_copy(update={'input_source':'decided_transcript'})
        if fragment.region_id == next(row.region_id for row in req.fragments if row.id in assembly.fragment_ids)
        else fragment for fragment in req.fragments)})
    with pytest.raises(EvidenceError,match='People'):
        collector_resolution(req,assembly_id=assembly.id)


@pytest.mark.parametrize('decided', ['a','b'])
def test_decided_collector_resolution_crosses_the_exact_application_acceptance_boundary(decided):
    from uuid import uuid4
    from specimen_digitization.research_harness.accepted_output import AcceptedOutputProofV1,validation_boundary_pins
    from specimen_digitization.research_harness.contracts import digest
    built = decided_fixture(decided)
    [assembly] = collector_assemblies(built)
    req = request_for(built,SpecialistRole.PARTIES)
    collector = collector_resolution(req,assembly_id=assembly.id)
    accepted = AcceptedOutputProofV1(original_request=req,native_run_id=str(uuid4()),
        conversation_id='offline-decided-collector-acceptance',resolutions=(collector,missing_irn_resolution()),
        source_results=(),effect_ids=(),model_settings_digest=digest('offline fixture settings'),
        **validation_boundary_pins())
    assert accepted.resolutions[0] == collector
    assert accepted.original_request.organiser_candidates == req.organiser_candidates
    assert accepted.resolutions[1].value.state == ValueState.UNKNOWN
