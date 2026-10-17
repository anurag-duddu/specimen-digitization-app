"""A country ambiguity between lower-level place texts is not country evidence.

Terminal shape: EBFC attempt-four trace 01a14868ec97861f879a771443c63fc7.
These are offline typed stand-ins; the actual response/terminal replay remains
in .context/ebfc-actual-fourth-postexpert-replay.py with pinned input digests.
"""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import FieldValue, LookupStatus, ValueState
from specimen_digitization.field_research.contracts import Candidate, FieldAnswer, FieldOutcome, FieldTask, PlaceRef, Reading, SourceCandidate
from specimen_digitization.field_research.location_reassessment import FIELDS
from specimen_digitization.field_research.step import _country_alternatives_are_lower_places
from test_location_reassessment import CapturedLocationSources, captured_location_run, captured_location_script, execute


async def fourth_outcome_shape(task, readings, tools):
    """Actual fourth country terminal shape, with offline typed source stand-ins."""
    result = await captured_location_script()(task, readings, tools)
    if task.key == "country":
        return replace(result, answer=FieldAnswer(outcome="several_possibilities",
            reading_names=["1A", "1B"], options=["ILLINOIS", "Bloomington"],
            explanation="The expert treated the state and town text as country alternatives."))
    return result


def test_fourth_country_outcome_shape_derives_country_without_inventing_town(tmp_path, monkeypatch):
    rig = captured_location_run(tmp_path)
    before, done, _, _, _ = execute(rig, monkeypatch,
        sources=CapturedLocationSources, script=fourth_outcome_shape)
    assert done.run.fields["country"].state == ValueState.SUPPORTED
    assert done.run.fields["country"].parsed == "United States"
    assert done.run.fields["country"].authority_id == "wikidata:Q30"
    assert done.run.fields["country"].layer == "derived"
    assert done.run.fields["province_state"].authority_id == "wikidata:Q1204"
    assert done.run.fields["county"].authority_id == "wikidata:Q110532"
    assert done.run.fields["city"].state != ValueState.SUPPORTED
    assert done.run.fields["city"].parsed is None
    assert done.run.fields["precise_location"].state == ValueState.AMBIGUOUS
    assert not any(reason.startswith("location_reassessment_unconfirmed:") for reason in done.run.reasons)
    assert done.run.observations == before.observations and done.run.transcripts == before.transcripts
    assert done.run.profile == before.profile and done.run.profile_snapshot == before.profile_snapshot


def test_original_country_human_lock_still_blocks_fourth_outcome_shape(tmp_path, monkeypatch):
    rig = captured_location_run(tmp_path)
    rig.specimen.run.dependencies["human_review_field_locks"] = {"country": {"retained": True}}
    async def script(task, readings, tools):
        if task.key == "county":
            await tools.lookup("wikidata", "ILLINOIS", field_key=task.key)
        return await fourth_outcome_shape(task, readings, tools)
    before, done, resolver, _, _ = execute(rig, monkeypatch,
        sources=CapturedLocationSources, script=script)
    assert "country" not in resolver.calls
    assert {key: done.run.fields[key] for key in FIELDS} == {key: before.fields[key] for key in FIELDS}


@pytest.fixture
def proof(tmp_path):
    rig = captured_location_run(tmp_path)
    sources = CapturedLocationSources(rig.blobs)
    state, town = (sources._answer("wikidata", text) for text in ("ILLINOIS", "Bloomington"))
    run = rig.specimen.run.model_copy(deep=True)
    run.fields["country"] = FieldValue(state=ValueState.AMBIGUOUS)
    run.fields["province_state"] = FieldValue(state=ValueState.SUPPORTED, literal="ILLINOIS",
        normalized="Illinois", authority_id="wikidata:Q1204", layer="settled",
        evidence_ids=[state.evidence.id], evidence_relations={state.evidence.id: "supports"})
    readings = (Reading("1A", "label1", "obs1", "raw_reading", "ILLINOIS\nBloomington"),
        Reading("1B", "label1", "obs2", "raw_reading", "ILLINOIS\n[unreadable] 69"),
        Reading("2A", "label2", "obs3", "raw_reading", "CANADA"))
    task = FieldTask("country", False, FieldValue(),
        (Candidate("1A", "Bloomington", "Bloomington", "town-row"),), ("wikidata",))
    outcome = FieldOutcome("country", FieldAnswer(outcome="several_possibilities",
        options=["ILLINOIS", "Bloomington"], explanation="Two place texts."))
    return SimpleNamespace(run=run, sources=sources, task=task, outcome=outcome, readings=readings,
        received={"country": [state], "city": [town]}, fresh={state.evidence.id, town.evidence.id})


def qualifies(proof):
    return _country_alternatives_are_lower_places(proof.run, proof.task, proof.outcome,
        readings=proof.readings, received=proof.received, fresh=proof.fresh)


def test_exact_fresh_whole_literal_proof_qualifies(proof):
    assert qualifies(proof)


@pytest.mark.parametrize("storage", ["options", "literal", "verbatim", "candidate"])
@pytest.mark.parametrize("kind", ["country", "unknown", "unqueried", "geolocate", "wrong_query", "mixed"])
def test_all_retained_other_label_country_alternatives_need_lower_level_proof(proof, storage, kind):
    if storage == "options":
        proof.outcome.answer.options.append("CANADA")
    elif storage == "literal":
        proof.task = replace(proof.task, current=FieldValue(literal="CANADA"))
    elif storage == "verbatim":
        proof.task = replace(proof.task, current=FieldValue(verbatim_by_observation={"obs3": "CANADA"}))
    else:
        proof.task = replace(proof.task, candidates=(*proof.task.candidates,
            Candidate("2A", "CANADA", "CANADA", "other-country")))
    if kind != "unqueried":
        candidates = (SourceCandidate("CANADA", "fixture:canada", "country" if kind in {"country", "mixed"} else "city"),)
        if kind == "mixed":
            candidates += (SourceCandidate("CANADA", "fixture:city-canada", "city"),)
        answer = proof.sources._authority("geolocate" if kind == "geolocate" else "wikidata",
            "Elsewhere" if kind == "wrong_query" else "CANADA", candidates)
        if kind == "unknown":
            answer = replace(answer, status=LookupStatus.NO_MATCH, candidates=())
        proof.received["county"] = [answer]
        proof.fresh.add(answer.evidence.id)
    assert not qualifies(proof)


@pytest.mark.parametrize("failure", ["empty_options", "unreadable", "ungrounded", "compound",
    "stale_source", "stale_child", "no_ancestry", "derived_child", "unsupported_child"])
def test_proof_does_not_erase_unproven_country_ambiguity(proof, failure):
    if failure == "empty_options": proof.outcome.answer.options = []
    elif failure == "unreadable": proof.outcome.answer.options.append("[unreadable] 69")
    elif failure == "ungrounded": proof.outcome.answer.options.append("Indiana")
    elif failure == "compound": proof.outcome.answer.options.append("ILLINOIS Bloomington")
    elif failure == "stale_source": proof.fresh.remove(proof.received["city"][0].evidence.id)
    elif failure == "stale_child": proof.fresh.remove(proof.received["country"][0].evidence.id)
    elif failure == "no_ancestry":
        source = proof.received["country"][0]
        proof.received["country"] = [replace(source, candidates=tuple(
            replace(candidate, parents=()) for candidate in source.candidates))]
    elif failure == "derived_child": proof.run.fields["province_state"].layer = "derived"
    elif failure == "unsupported_child": proof.run.fields["province_state"].state = ValueState.UNRESOLVED
    assert not qualifies(proof)


def test_incompatible_qualified_parent_countries_restore_original_ambiguity(tmp_path, monkeypatch):
    class ConflictingParents(CapturedLocationSources):
        def _answer(self, source_id, query):
            answer = super()._answer(source_id, query)
            if source_id == "wikidata" and query.startswith("Clark County"):
                answer = replace(answer, candidates=tuple(replace(candidate,
                    parents=(*candidate.parents[:-1], PlaceRef("Mexico", "wikidata:Q96")))
                    if candidate.authority_id == "wikidata:Q110532" else candidate
                    for candidate in answer.candidates))
            return answer
    rig = captured_location_run(tmp_path)
    before, done, _, _, _ = execute(rig, monkeypatch,
        sources=ConflictingParents, script=fourth_outcome_shape)
    assert {key: done.run.fields[key] for key in FIELDS} == {key: before.fields[key] for key in FIELDS}
    assert "location_reassessment_unconfirmed:country" in done.run.reasons


@pytest.mark.parametrize("selected", ["fixture:selected", "fixture:missing", None])
def test_derivation_uses_selected_authority_before_same_name(proof, selected):
    from specimen_digitization.field_research.derive import _settling_candidate
    first = SourceCandidate("Clark County", "fixture:first", "county",
        parents=(PlaceRef("Canada", "fixture:canada"),))
    chosen = SourceCandidate("Clark County", "fixture:selected", "county",
        parents=(PlaceRef("United States", "wikidata:Q30"),))
    source = proof.sources._authority("wikidata", "Clark County", (first, chosen))
    field = FieldValue(state=ValueState.SUPPORTED, literal="Clark County", authority_id=selected,
        evidence_ids=[source.evidence.id])
    assert _settling_candidate(field, [source]) == (
        chosen if selected == "fixture:selected" else first if selected is None else None)


@pytest.mark.parametrize("kind", [None, "", " "])
def test_an_untyped_matching_place_cannot_hide_beside_a_typed_city(proof, kind):
    source = proof.received["city"][0]
    proof.received["city"] = [replace(source, candidates=(*source.candidates,
        SourceCandidate("Bloomington", "fixture:untyped-place", kind)))]
    assert not qualifies(proof)


@pytest.mark.parametrize("recognized_lower_proof", [False, True])
@pytest.mark.parametrize("unmodeled_kind", ["album", "unmodeled geographic class"])
def test_unmodeled_class_neither_proves_nor_disproves_country_level(proof, recognized_lower_proof, unmodeled_kind):
    source = proof.received["city"][0]
    unknown = SourceCandidate("Bloomington", "fixture:unmodeled", unmodeled_kind)
    proof.received["city"] = [replace(source,
        candidates=(*source.candidates, unknown) if recognized_lower_proof else (unknown,))]
    assert qualifies(proof) is recognized_lower_proof


@pytest.mark.parametrize("protection", ["human_review_field_locks", "preserved_human_fields", "location_reassessment"])
def test_new_derivation_branch_itself_preserves_human_protections(proof, protection):
    proof.run.dependencies[protection] = ({"protected": ["country"]} if protection == "location_reassessment"
        else {"country": {"retained": True}})
    assert not qualifies(proof)
