"""Explicit family recovery uses retained readers and fresh qualified evidence."""
from contextlib import asynccontextmanager
from dataclasses import replace
import hashlib

import pytest

from specimen_digitization.application.domain import Evidence, FieldValue, LookupStatus, ValueState
from specimen_digitization.application.human_field_carry import KEY as CARRY_KEY
from specimen_digitization.application.integrity import verify_evidence
from specimen_digitization.application.workflow import FIELD_RESEARCH, OperationalBlock
from specimen_digitization.field_research.contracts import (
    Candidate, FieldAnswer, FieldOutcome, FieldTask, PlaceRef, Reading, SourceCandidate,
)
from specimen_digitization.field_research.location_reassessment import (
    FIELDS, KEY, active_keys, commit, eligible_keys, working_run,
)
from specimen_digitization.field_research.step import _LocationProposal, _location_readers_agree, build_tasks

from test_step import FakeSources, LiveIllinoisSources, Scripted, TGN_PLACES, build_rig, mounted, settle


def old_location_run(tmp_path):
    text = "ILLINOIS\nClark County\nBloomington"
    candidates = [(key, reader, literal, literal)
        for reader in ("1A", "1B")
        for key, literal in (("city", "ILLINOIS"), ("province_state", "Clark County"),
            ("county", "Clark County"), ("precise_location", "Bloomington"))]
    rig = build_rig(tmp_path, text, candidates=candidates)
    run = rig.specimen.run
    run.fields["city"] = run.fields["city"].model_copy(update={
        "state": ValueState.SUPPORTED, "literal": "ILLINOIS", "parsed": "Illinois",
        "authority_id": "old:wrong-city", "layer": "settled"})
    run.fields["country"] = FieldValue(state=ValueState.SUPPORTED, parsed="PH",
        layer="derived", derived_from=["city"])
    run.attempts[FIELD_RESEARCH] = 2
    run.dependencies[KEY] = {"attempt": 3, "fields": sorted(eligible_keys(run))}
    return rig


class Places(FakeSources):
    def _answer(self, source_id, query):
        # Fixture authority records, never an external lookup.
        if query == "ILLINOIS":
            query = "Illinois"
        answer = super()._answer(source_id, query)
        if answer.evidence is None:
            raw = f"{source_id}: {query}: source unavailable".encode()
            answer = replace(answer, evidence=Evidence(kind="lookup", source=source_id, locator=None,
                excerpt="Source unavailable", raw_ref=self.blobs.put(raw),
                digest=hashlib.sha256(raw).hexdigest()))
        return answer


async def locate(task, readings, tools):
    if task.key in {"province_state", "city"}:
        query = "Clark County" if task.key == "province_state" else "ILLINOIS"
        answer = await tools.lookup("tgn", query, field_key=task.key)
        return FieldOutcome(task.key, FieldAnswer(outcome="label_lacks_value",
            explanation="This text names a different administrative level."),
            evidence=[answer.evidence] if answer.evidence else [], model_calls=1)
    if task.key == "precise_location":
        return FieldOutcome(task.key, FieldAnswer(outcome="several_possibilities",
            explanation="The readings and sources do not settle the town."), model_calls=1)
    return FieldOutcome(task.key, FieldAnswer(outcome="label_lacks_value",
        explanation="No value is written for this field."), model_calls=1)


def execute(rig, monkeypatch, *, outage=False, sources=Places, script=locate):
    monkeypatch.setitem(TGN_PLACES, "Clark County",
        ("counties", ("Illinois", "United States")))
    resolver = Scripted({key: script for key in FIELDS})
    state = mounted(rig, resolver, sources=sources, tools_down=("tgn",) if outage else ())
    original_factory = rig.workflow.field_research.tools_factory
    contexts = []

    @asynccontextmanager
    async def tools(run, profile, blobs):
        contexts.append({key: value.model_copy(deep=True) for key, value in run.fields.items()})
        async with original_factory(run, profile, blobs) as sources:
            yield sources

    rig.workflow.field_research.tools_factory = tools
    saved = rig.repository.save(rig.principal, rig.specimen, rig.specimen.version, "reassess", "reassess")
    before = saved.run.model_copy(deep=True)
    done = rig.workflow.step(rig.principal, saved.id)
    return before, done, resolver, state, contexts


def test_same_run_reassessment_moves_wrong_city_and_rederives_country(tmp_path, monkeypatch):
    rig = old_location_run(tmp_path)
    before, done, resolver, state, contexts = execute(rig, monkeypatch)
    run = done.run
    assert set(resolver.calls) == FIELDS
    assert contexts[0]["country"].parsed is None
    assert contexts[0]["city"].state == ValueState.UNRESOLVED
    assert (run.fields["province_state"].state, run.fields["province_state"].literal) == (
        ValueState.SUPPORTED, "ILLINOIS")
    assert run.fields["county"].state == ValueState.SUPPORTED
    assert run.fields["country"].parsed == "United States"
    assert run.fields["country"].layer == "derived"
    assert run.fields["city"].state == ValueState.NOT_PRESENT
    assert run.fields["precise_location"].state == ValueState.AMBIGUOUS
    assert run.id == before.id and run.observations == before.observations
    assert run.transcripts == before.transcripts and run.profile_snapshot == before.profile_snapshot
    assert run.attempts[FIELD_RESEARCH] == 3
    assert {key: value for key, value in run.attempts.items() if key != FIELD_RESEARCH} == {
        key: value for key, value in before.attempts.items() if key != FIELD_RESEARCH}
    assert run.paid_calls[:-1] == before.paid_calls and state.meters[0].spent_micros > 0
    assert run.usage.reserved_cost_micros >= before.usage.reserved_cost_micros
    assert run.profile.execution == before.profile.execution
    assert KEY not in run.dependencies
    assert {row.id for row in before.evidence} <= {row.id for row in run.evidence}
    fresh_authority = {row.id for row in run.evidence if row.source == "tgn" and row.kind == "authority"}
    assert fresh_authority and fresh_authority <= {call.evidence_id for call in run.tool_calls}
    verify_evidence(done, rig.blobs)


def test_no_qualification_retains_supported_family_and_records_review(tmp_path, monkeypatch):
    rig = old_location_run(tmp_path)
    before, done, resolver, _, _ = execute(rig, monkeypatch, outage=True)
    assert set(resolver.calls) == FIELDS
    assert {key: done.run.fields[key] for key in FIELDS} == {key: before.fields[key] for key in FIELDS}
    assert any(reason.startswith("location_reassessment_unconfirmed:") for reason in done.run.reasons)
    assert done.run.disposition == "needs_human_review"
    assert KEY not in done.run.dependencies
    assert done.run.attempts[FIELD_RESEARCH] == 3
    fresh = {row.id for row in done.run.evidence} - {row.id for row in before.evidence}
    assert fresh & {call.evidence_id for call in done.run.tool_calls}
    verify_evidence(done, rig.blobs)


def test_fresh_state_proof_can_relocate_an_abbreviated_old_city_claim(tmp_path, monkeypatch):
    rig = old_location_run(tmp_path)
    rig.specimen.run.fields["city"].literal = "Ill."
    _, done, _, _, _ = execute(rig, monkeypatch)
    assert done.run.fields["province_state"].literal == "ILLINOIS"
    assert done.run.fields["country"].parsed == "United States"
    assert done.run.fields["city"].state == ValueState.NOT_PRESENT


def test_shared_initial_does_not_disprove_a_different_supported_place(tmp_path):
    run = old_location_run(tmp_path).specimen.run
    run.attempts[FIELD_RESEARCH] = 3
    before = run.model_copy(deep=True)
    working = working_run(run)
    row = Evidence(kind="authority", source="wikidata", locator="Q1415", excerpt="Indiana")
    working.evidence.append(row)
    working.fields["province_state"] = FieldValue(state=ValueState.SUPPORTED,
        literal="I.", parsed="I.", normalized="Indiana", layer="settled", authority_id="Q1415",
        evidence_ids=[row.id], evidence_relations={row.id: "supports"})
    working.fields["country"] = FieldValue(state=ValueState.SUPPORTED, parsed="United States",
        layer="derived", derived_from=["province_state"])
    working.fields["city"] = FieldValue(state=ValueState.NOT_PRESENT)
    # I. can abbreviate both Indiana and Illinois. Only Indiana was qualified;
    # its abbreviation cannot disprove the retained city claim for Illinois.
    assert "city" in commit(run, working, decisions={})
    assert run.fields == before.fields
    assert row in run.evidence


def test_ordinary_retry_still_skips_supported_fields(tmp_path):
    run = old_location_run(tmp_path).specimen.run
    run.dependencies.pop(KEY)
    tasks = build_tasks(run)[1]
    assert {"country", "city"}.isdisjoint(task.key for task in tasks)
    assert any(task.key not in FIELDS for task in tasks)


@pytest.mark.parametrize("lock", [CARRY_KEY, "human_review_field_locks"])
def test_human_locks_excluded_even_after_marker_is_queued(tmp_path, lock):
    run = old_location_run(tmp_path).specimen.run
    run.attempts[FIELD_RESEARCH] = 3
    run.dependencies[lock] = {"country": {"retained": True}}
    assert "country" not in eligible_keys(run)
    assert "country" not in active_keys(run)
    readings, tasks, context = build_tasks(run)
    assert "country" not in {task.key for task in tasks}
    assert context["country"] == run.fields["country"]
    assert readings


@pytest.mark.parametrize(("layer", "literal"), [("settled", "Philippines"), ("verbatim", "Philippines"),
    ("verbatim", None)])
def test_directly_qualified_parent_stays_an_independent_constraint(tmp_path, layer, literal):
    run = old_location_run(tmp_path).specimen.run
    evidence = Evidence(kind="authority", source="wikidata", locator="Q928", excerpt="Philippines")
    run.evidence.append(evidence)
    run.fields["country"] = FieldValue(state=ValueState.SUPPORTED, literal=literal,
        parsed="Philippines", layer=layer, authority_id="Q928", evidence_ids=[evidence.id],
        evidence_relations={evidence.id: "supports"},
        verbatim_by_observation={run.observations[0].id: "Philippines"})
    run.attempts[FIELD_RESEARCH] = 3
    _, tasks, context = build_tasks(run)
    assert "country" not in {task.key for task in tasks}
    assert context["country"] == run.fields["country"]
    assert context["country"].state == ValueState.SUPPORTED


def test_qualified_conflicting_country_blocks_new_us_hierarchy(tmp_path, monkeypatch):
    rig = old_location_run(tmp_path)
    monkeypatch.setitem(TGN_PLACES, "Philippines", ("nations", ()))
    answer = Places(rig.blobs)._answer("tgn", "Philippines")
    run = rig.specimen.run
    run.evidence.append(answer.evidence)
    run.fields["country"] = FieldValue(state=ValueState.SUPPORTED, literal="Philippines",
        parsed="Philippines", layer="settled", authority_id="tgn:Philippines",
        evidence_ids=[answer.evidence.id], evidence_relations={answer.evidence.id: "supports"})
    before, done, resolver, _, _ = execute(rig, monkeypatch)
    assert "country" not in resolver.calls
    assert done.run.fields["country"] == before.fields["country"]
    assert done.run.fields["province_state"].normalized != "Illinois"
    assert done.run.fields["county"].authority_id != "tgn:Clark County"
    assert done.run.disposition == "needs_human_review"


def test_ambiguous_authority_does_not_remove_old_supported_assignment(tmp_path, monkeypatch):
    class AmbiguousPlaces(Places):
        def _answer(self, source_id, query):
            answer = super()._answer(source_id, query)
            if query == "ILLINOIS" and answer.candidates:
                other = replace(answer.candidates[0], authority_id="tgn:other-Illinois",
                    parents=(PlaceRef("Canada"),))
                return replace(answer, candidates=(*answer.candidates, other))
            return answer

    rig = old_location_run(tmp_path)
    before, done, _, _, _ = execute(rig, monkeypatch, sources=AmbiguousPlaces)
    assert {key: done.run.fields[key] for key in FIELDS} == {key: before.fields[key] for key in FIELDS}
    assert "location_reassessment_unconfirmed:city" in done.run.reasons
    assert done.run.disposition == "needs_human_review"


def test_operator_proof_marker_protects_a_reviewed_field(tmp_path):
    run = old_location_run(tmp_path).specimen.run
    run.attempts[FIELD_RESEARCH] = 3
    run.dependencies[KEY]["protected"] = ["city"]
    assert "city" not in active_keys(run)
    assert "country" not in active_keys(run)  # Its retained human child supplies the ancestor.
    assert build_tasks(run)[2]["city"] == run.fields["city"]


def test_operational_retry_renews_only_the_explicit_family_scope(tmp_path, monkeypatch):
    rig = old_location_run(tmp_path)
    run = rig.specimen.run
    run.attempts[FIELD_RESEARCH] = 1
    run.dependencies[KEY]["attempt"] = 2

    async def broken(task, readings, tools):
        return FieldOutcome(task.key, None, failure="model_error", model_calls=1)

    resolver = Scripted({key: broken for key in FIELDS})
    mounted(rig, resolver)
    saved = rig.repository.save(rig.principal, rig.specimen, rig.specimen.version, "retry-test", "retry-test")
    failed = rig.workflow.step(rig.principal, saved.id)
    assert failed.run.stage == "retry_scheduled"
    assert failed.run.dependencies[KEY]["attempt"] == 3
    assert set(failed.run.dependencies[KEY]["fields"]) == FIELDS
    assert set(resolver.calls) == FIELDS
    from datetime import datetime
    rig.clock.now = datetime.fromisoformat(failed.run.next_retry_at)
    resolver.calls.clear()
    last = rig.workflow.step(rig.principal, failed.id)
    assert set(resolver.calls) == FIELDS
    assert last.run.attempts[FIELD_RESEARCH] == 3
    assert KEY not in last.run.dependencies
    assert last.run.fields == saved.run.fields


@pytest.mark.parametrize("marker", [
    {"attempt": 2, "fields": ["country"]},
    {"attempt": True, "fields": ["country"]},
    {"attempt": 3, "fields": ["taxon"]},
    {"attempt": 3, "fields": []},
])
def test_invalid_intent_never_falls_back_to_broader_research(tmp_path, marker):
    run = old_location_run(tmp_path).specimen.run
    run.attempts[FIELD_RESEARCH] = 3
    run.dependencies[KEY] = marker
    assert active_keys(run) == set()
    with pytest.raises(OperationalBlock, match="location_reassessment_unavailable"):
        build_tasks(run)


def test_unsent_run_limit_does_not_mutate_any_field_or_charge(tmp_path):
    rig = old_location_run(tmp_path)
    before = rig.specimen.run.model_copy(deep=True)
    resolver = Scripted()
    state = mounted(rig, resolver)
    rig.workflow.field_research.give_up(rig.workflow, rig.principal, rig.specimen, "active_time_budget_exhausted")
    run = rig.specimen.run
    assert run.fields == before.fields
    assert run.attempts == before.attempts and run.paid_calls == before.paid_calls
    assert run.usage == before.usage and not resolver.calls and not state.meters
    assert KEY not in run.dependencies
    assert "location_reassessment_unconfirmed:run_limit:active_time_budget_exhausted" in run.reasons


class CapturedLocationSources(LiveIllinoisSources):
    """Typed lookup shape from EBFC trace 01a146fc40156e42517723f4b6d4236d.

    These offline records retain source kinds, alternatives and parent chains;
    they neither ask a provider nor treat the query's parent text as evidence.
    """

    def _answer(self, source_id, query):
        if source_id == "wikidata" and query == "ILLINOIS":
            return self._authority(source_id, query, (
                SourceCandidate("Illinois", "wikidata:Q1204", "U.S. state",
                    "in United States; valid from 1818-12-03", (PlaceRef("United States", "wikidata:Q30"),)),
                *(SourceCandidate(name, f"wikidata:fixture-illinois-{index}", kind)
                    for index, (name, kind) in enumerate((
                        ("University of Illinois Urbana-Champaign", "public university"),
                        ("Illinois", "album"), ("Illinois State University", "public university"),
                        ("University of Illinois Chicago", "public university"),
                        ("Miami-Illinois", "language"), ("township of Illinois", None)))),
            ))
        if source_id == "wikidata" and query == "Georgia":
            return self._authority(source_id, query, (
                SourceCandidate("Georgia", "wikidata:Q1428", "U.S. state",
                    parents=(PlaceRef("United States", "wikidata:Q30"),)),))
        if source_id == "nga" and query == "ILLINOIS":
            return self._authority(source_id, query, (
                SourceCandidate("Ilinois", "nga:fixture-farm", "S.FRM",
                    parents=(PlaceRef("Khomas"), PlaceRef("Namibia", iso_code="NA"))),
                *(SourceCandidate("Illinois", f"nga:fixture-street-{province}", "R.ST",
                    parents=(PlaceRef(province), PlaceRef("Philippines", iso_code="PH")))
                    for province in ("Quezon", "Rizal", "Cavite")),
                SourceCandidate("Illinois", "nga:fixture-mexico-town", "P.PPL",
                    parents=(PlaceRef("Coahuila"), PlaceRef("Mexico", iso_code="MX"))),
            ))
        if source_id == "wikidata" and query == "Bloomington":
            return self._authority(source_id, query, tuple(
                SourceCandidate("Bloomington", f"wikidata:fixture-bloomington-{county}", "city",
                    parents=(PlaceRef(county), PlaceRef(state), PlaceRef("United States", "wikidata:Q30")))
                for county, state in (("Monroe County", "Indiana"), ("McLean County", "Illinois"),
                    ("Hennepin County", "Minnesota"), ("Franklin County", "Nebraska"),
                    ("San Bernardino County", "California"), ("Grant County", "Wisconsin"),
                    ("Victoria County", "Texas"))))
        if source_id == "geolocate":
            # Its Illinois query echo is not state/county authority; its town
            # result actually contradicts Clark County.
            if query.startswith("Bloomington"):
                return self._authority(source_id, query, (
                    SourceCandidate("Bloomington", None, "place",
                        parents=(PlaceRef("McLean County"), PlaceRef("Illinois"), PlaceRef("United States"))),))
            return self._authority(source_id, query, (
                SourceCandidate("Illinois", None, "place",
                    parents=(PlaceRef("United States"),)),))
        answer = super()._answer(source_id, query)
        if source_id == "wikidata" and query.startswith("Clark County"):
            answer = replace(answer, candidates=tuple(replace(candidate, authority_id="wikidata:Q110532")
                if candidate.parents[0].name == "Illinois" else candidate for candidate in answer.candidates))
        return answer


def captured_location_run(tmp_path, *, state="ILLINOIS", other_state=None, decided=False):
    text = f"{state}\nClark County\nBloomington"
    candidates = [(key, "1A", literal, literal)
        for key, literal in (("country", "Bloomington"), ("province_state", "Clark County"),
            ("city", "Bloomington"), ("precise_location", "Bloomington"))]
    other = f"{other_state or state}\nclark county\n[unreadable] 69"
    rig = build_rig(tmp_path, text, other=other, decided=decided, candidates=candidates)
    run = rig.specimen.run
    run.fields["country"] = FieldValue(state=ValueState.SUPPORTED, parsed="PH",
        layer="derived", derived_from=["city"])
    run.fields["city"] = run.fields["city"].model_copy(update={"state": ValueState.SUPPORTED,
        "literal": state, "parsed": state, "layer": "settled", "authority_id": "old:wrong-city",
        "verbatim_by_observation": {observation.id: other_state if index and other_state else state
            for index, observation in enumerate(run.observations)}})
    for key in ("province_state", "county"):
        run.fields[key] = run.fields[key].model_copy(update={"state": ValueState.UNRESOLVED,
            "literal": None, "parsed": None, "normalized": None, "layer": None})
    run.attempts[FIELD_RESEARCH] = 2
    run.dependencies[KEY] = {"attempt": 3, "fields": sorted(eligible_keys(run))}
    return rig


def captured_location_script(state="ILLINOIS"):
    async def script(task, readings, tools):
        queries = {
            "country": (("wikidata", state), ("nga", state), ("tgn", state)),
            "province_state": (("wikidata", "Clark County, Illinois, United States"),
                ("geolocate", "Clark County, Illinois, United States")),
            "county": (("wikidata", "Clark County, Illinois, United States"),),
            "city": (("wikidata", "Bloomington"), ("geolocate", "Bloomington, Illinois, United States")),
        }
        answers = [await tools.lookup(source, query, field_key=task.key)
            for source, query in queries.get(task.key, ())]
        return FieldOutcome(task.key, FieldAnswer(
            outcome="several_possibilities" if task.key == "precise_location" else "sources_cannot_resolve",
            explanation="The expert could not settle this field from its own routed sources."),
            evidence=[answer.evidence for answer in answers if answer.evidence], model_calls=1,
            finalized_without_model=task.key in {"province_state", "county", "city"})
    return script


def test_captured_cross_task_answers_recover_admin_chain_without_inventing_town(tmp_path, monkeypatch):
    rig = captured_location_run(tmp_path)
    before, done, resolver, _, _ = execute(rig, monkeypatch,
        sources=CapturedLocationSources, script=captured_location_script())
    fields = done.run.fields
    assert set(resolver.calls) == FIELDS
    assert fields["province_state"].state == ValueState.SUPPORTED
    assert fields["province_state"].authority_id == "wikidata:Q1204"
    assert fields["province_state"].literal == "ILLINOIS"
    assert fields["county"].state == ValueState.SUPPORTED
    assert fields["county"].authority_id == "wikidata:Q110532"
    assert fields["country"].state == ValueState.SUPPORTED
    assert fields["country"].parsed == "United States"
    assert fields["country"].layer == "derived"
    assert fields["city"].state != ValueState.SUPPORTED
    assert fields["city"].parsed is None and fields["city"].normalized is None
    assert fields["precise_location"].state == ValueState.AMBIGUOUS
    assert not any(reason.startswith("location_reassessment_unconfirmed:") for reason in done.run.reasons)
    assert done.run.id == before.id and done.run.attempts[FIELD_RESEARCH] == 3
    assert done.run.observations == before.observations and done.run.transcripts == before.transcripts
    assert done.run.profile_snapshot == before.profile_snapshot
    assert done.run.usage.reserved_cost_micros >= before.usage.reserved_cost_micros
    fresh = {row.id for row in done.run.evidence} - {row.id for row in before.evidence}
    assert fields["province_state"].evidence_ids and fresh & set(fields["province_state"].evidence_ids)
    assert fresh & {call.evidence_id for call in done.run.tool_calls}
    verify_evidence(done, rig.blobs)


def test_captured_conflicting_written_state_cannot_disappear_to_allow_county_derivation(tmp_path, monkeypatch):
    rig = captured_location_run(tmp_path, state="Georgia")
    before, done, _, _, _ = execute(rig, monkeypatch,
        sources=CapturedLocationSources, script=captured_location_script("Georgia"))
    assert {key: done.run.fields[key] for key in FIELDS} == {key: before.fields[key] for key in FIELDS}
    assert "location_reassessment_unconfirmed:city" in done.run.reasons


def test_captured_cross_task_answers_keep_protected_parent_constraint(tmp_path, monkeypatch):
    rig = captured_location_run(tmp_path)
    rig.specimen.run.dependencies["human_review_field_locks"] = {"country": {"retained": True}}
    original = captured_location_script()

    async def with_state_answer(task, readings, tools):
        # Country is locked and has no expert. Another expert still captures
        # the valid US state answer, which must not override the retained PH.
        if task.key == "county":
            await tools.lookup("wikidata", "ILLINOIS", field_key=task.key)
        return await original(task, readings, tools)

    before, done, resolver, _, _ = execute(rig, monkeypatch,
        sources=CapturedLocationSources, script=with_state_answer)
    assert "country" not in resolver.calls
    assert done.run.fields["country"] == before.fields["country"]
    assert {key: done.run.fields[key] for key in FIELDS} == {key: before.fields[key] for key in FIELDS}


def test_captured_same_name_counties_with_same_parent_remain_ambiguous(tmp_path, monkeypatch):
    class TwoIllinoisCounties(CapturedLocationSources):
        def _answer(self, source_id, query):
            answer = super()._answer(source_id, query)
            if source_id == "wikidata" and query.startswith("Clark County"):
                illinois = next(candidate for candidate in answer.candidates
                    if candidate.authority_id == "wikidata:Q110532")
                return self._authority(source_id, query, (*answer.candidates,
                    replace(illinois, authority_id="wikidata:fixture-other-clark-in-illinois")))
            return answer

    rig = captured_location_run(tmp_path)
    _, done, _, _, _ = execute(rig, monkeypatch,
        sources=TwoIllinoisCounties, script=captured_location_script())
    assert done.run.fields["province_state"].authority_id == "wikidata:Q1204"
    assert done.run.fields["county"].state != ValueState.SUPPORTED
    assert done.run.fields["county"].authority_id is None
    assert done.run.fields["city"].state != ValueState.SUPPORTED


def test_unqueried_competing_state_reading_cannot_be_discarded_by_pooling(tmp_path, monkeypatch):
    rig = captured_location_run(tmp_path, other_state="INDIANA")
    before, done, _, _, _ = execute(rig, monkeypatch,
        sources=CapturedLocationSources, script=captured_location_script())
    assert not any(transcript.resolved for transcript in before.transcripts)
    assert {key: done.run.fields[key] for key in FIELDS} == {key: before.fields[key] for key in FIELDS}
    assert "location_reassessment_unconfirmed:city" in done.run.reasons


def test_cross_field_reader_placement_cannot_hide_an_unqueried_alternative(tmp_path):
    candidates = [("country", "1A", "ILLINOIS", "ILLINOIS"),
        ("city", "1B", "INDIANA", "INDIANA"),
        *(("province_state", reader, "Clark County", "Clark County") for reader in ("1A", "1B"))]
    rig = build_rig(tmp_path, "ILLINOIS\nClark County\nBloomington",
        other="INDIANA\nClark County\nBloomington", candidates=candidates)
    for key in ("country", "province_state", "city"):
        rig.specimen.run.fields[key] = rig.specimen.run.fields[key].model_copy(update={
            "literal": None, "parsed": None, "normalized": None})
    settle(rig, Scripted({key: captured_location_script() for key in FIELDS}),
        tools=CapturedLocationSources(rig.blobs))
    assert all(rig.specimen.run.fields[key].state != ValueState.SUPPORTED
        for key in ("country", "province_state", "county"))


def test_decided_transcript_still_authorizes_captured_location_reconciliation(tmp_path, monkeypatch):
    rig = captured_location_run(tmp_path, other_state="INDIANA", decided=True)
    _, done, _, _, _ = execute(rig, monkeypatch,
        sources=CapturedLocationSources, script=captured_location_script())
    assert done.run.fields["province_state"].authority_id == "wikidata:Q1204"
    assert done.run.fields["county"].authority_id == "wikidata:Q110532"
    assert done.run.fields["country"].parsed == "United States"


@pytest.mark.parametrize("captured_no_match", [False, True])
@pytest.mark.parametrize("other_level_namesake", [False, True])
def test_reconciliation_uses_existing_g20_captured_no_match_rule(tmp_path, captured_no_match, other_level_namesake):
    class WithNoMatch(CapturedLocationSources):
        def _answer(self, source_id, query):
            if source_id == "wikidata" and query == "INDIANA":
                return replace(self._authority(source_id, query, ()), status=LookupStatus.NO_MATCH)
            if source_id == "nga" and query == "ILLINOIS" and not other_level_namesake:
                return replace(self._authority(source_id, query, ()), status=LookupStatus.NO_MATCH)
            return super()._answer(source_id, query)

    candidates = [("city", "1A", "ILLINOIS", "ILLINOIS"),
        ("city", "1B", "INDIANA", "INDIANA"),
        *((key, reader, literal, literal) for reader in ("1A", "1B")
            for key, literal in (("country", "Bloomington"), ("province_state", "Clark County")))]
    rig = build_rig(tmp_path, "ILLINOIS\nClark County\nBloomington",
        other="INDIANA\nClark County\nBloomington", candidates=candidates)
    for key in ("country", "province_state"):
        rig.specimen.run.fields[key] = rig.specimen.run.fields[key].model_copy(update={
            "literal": None, "parsed": None, "normalized": None})
    original = captured_location_script()

    async def script(task, readings, tools):
        if captured_no_match and task.key == "country":
            await tools.lookup("wikidata", "INDIANA", field_key=task.key)
        return await original(task, readings, tools)

    settle(rig, Scripted({key: script for key in FIELDS}), tools=WithNoMatch(rig.blobs))
    fields = rig.specimen.run.fields
    if captured_no_match:
        assert fields["province_state"].authority_id == "wikidata:Q1204"
        assert fields["county"].authority_id == "wikidata:Q110532"
        assert fields["country"].parsed == "United States"
    else:
        assert all(fields[key].state != ValueState.SUPPORTED for key in ("country", "province_state", "county"))


@pytest.mark.parametrize("other_label_names_place", [False, True])
def test_transcript_projection_keeps_other_labels_place_alternatives(tmp_path, other_label_names_place):
    rig = captured_location_run(tmp_path)
    source = CapturedLocationSources(rig.blobs)._answer("wikidata", "ILLINOIS")
    town = CapturedLocationSources(rig.blobs)._answer("wikidata", "Bloomington")
    readings = (Reading("1A", "label-1", "observation-1A", "raw_reading", "ILLINOIS\nBloomington"),
        Reading("1B", "label-1", "observation-1B", "raw_reading", "ILLINOIS\n[unreadable]"),
        Reading("2A", "label-2", "observation-2A", "raw_reading", "INDIANA" if other_label_names_place else "A moth"))
    verbatims = {"observation-1A": "ILLINOIS", "observation-1B": "ILLINOIS"}
    candidates = [Candidate("1A", "Bloomington", "Bloomington", "literal-town")]
    if other_label_names_place:
        verbatims["observation-2A"] = "INDIANA"
        candidates.append(Candidate("2A", "INDIANA", "INDIANA", "literal-other-state"))
    task = FieldTask("city", False, FieldValue(literal="ILLINOIS", verbatim_by_observation=verbatims),
        tuple(candidates), ("wikidata",))
    proposal = _LocationProposal("province_state", "ILLINOIS", ("1A", "1B"), "city", "country",
        source, source.candidates[0])
    assert _location_readers_agree(proposal, {"city": task}, readings,
        {"country": [source], "city": [town]}) is not other_label_names_place


@pytest.mark.parametrize("owner_candidates", ["ILLINOIS", "Bloomington"])
@pytest.mark.parametrize("target_alternatives", ["candidates", "verbatims", "unrelated"])
def test_projection_keeps_target_fields_other_label_alternatives(tmp_path, owner_candidates, target_alternatives):
    rig = captured_location_run(tmp_path)
    source = CapturedLocationSources(rig.blobs)._answer("wikidata", "ILLINOIS")
    town = CapturedLocationSources(rig.blobs)._answer("wikidata", "Bloomington")
    readings = tuple(Reading(name, region, name, "raw_reading", text) for name, region, text in (
        ("1A", "label-1", "ILLINOIS\nBloomington"), ("1B", "label-1", "ILLINOIS\n[unreadable]"),
        ("2A", "label-2", "INDIANA"), ("2B", "label-2", "INDIANA")))
    owner = FieldTask("city", False, FieldValue(literal="ILLINOIS",
        verbatim_by_observation={"1A": "ILLINOIS", "1B": "ILLINOIS"}),
        tuple(Candidate(name, owner_candidates, owner_candidates, "owner-row")
            for name in (("1A", "1B") if owner_candidates == "ILLINOIS" else ("1A",))), ("wikidata",))
    target = FieldTask("province_state", False, FieldValue(verbatim_by_observation=
        {"2A": "INDIANA", "2B": "INDIANA"} if target_alternatives == "verbatims" else {}),
        tuple(Candidate(name, "INDIANA", "INDIANA", "target-row") for name in ("2A", "2B"))
            if target_alternatives == "candidates" else (), ("wikidata",))
    proposal = _LocationProposal("province_state", "ILLINOIS", ("1A", "1B"), "city", "country",
        source, source.candidates[0])
    assert _location_readers_agree(proposal, {"city": owner, "province_state": target}, readings,
        {"country": [source], "city": [town]}) is (target_alternatives == "unrelated")


@pytest.mark.parametrize("alternative_storage", ["candidates", "verbatims"])
@pytest.mark.parametrize("proof", ["unknown", "same_level", "other_level", "mixed_levels", "query_echo", "wrong_query"])
def test_same_label_target_alternative_needs_grounded_other_level_proof(tmp_path, alternative_storage, proof):
    rig = captured_location_run(tmp_path)
    sources = CapturedLocationSources(rig.blobs)
    source = sources._answer("wikidata", "ILLINOIS")
    town = sources._answer("wikidata", "Bloomington")
    literal = "Clark County" if proof == "other_level" else "INDIANA"
    readings = tuple(Reading(name, "label", name, "raw_reading", f"ILLINOIS\n{literal}\nBloomington")
        for name in ("1A", "1B"))
    owner = FieldTask("city", False, FieldValue(literal="ILLINOIS",
        verbatim_by_observation={"1A": "ILLINOIS", "1B": "ILLINOIS"}),
        (Candidate("1A", "Bloomington", "Bloomington", "owner-row"),), ("wikidata",))
    target = FieldTask("province_state", False, FieldValue(verbatim_by_observation=
        dict.fromkeys(("1A", "1B"), literal) if alternative_storage == "verbatims" else {}),
        tuple(Candidate(name, literal, literal, "target-row") for name in ("1A", "1B"))
            if alternative_storage == "candidates" else (), ("wikidata",))
    alternatives = []
    if proof == "other_level":
        alternatives.append(sources._answer("wikidata", "Clark County, Illinois, United States"))
    elif proof != "unknown":
        candidates = (SourceCandidate("INDIANA", "fixture:indiana", "U.S. state"
            if proof in {"same_level", "mixed_levels"} else "county"),)
        if proof == "mixed_levels":
            candidates += (SourceCandidate("INDIANA", "fixture:county", "county"),)
        alternatives.append(sources._authority("geolocate" if proof == "query_echo" else "wikidata",
            "Elsewhere" if proof == "wrong_query" else "INDIANA", candidates))
    proposal = _LocationProposal("province_state", "ILLINOIS", ("1A", "1B"), "city", "country",
        source, source.candidates[0])
    assert _location_readers_agree(proposal, {"city": owner, "province_state": target}, readings,
        {"country": [source], "city": [town], "province_state": alternatives}) is (proof == "other_level")


@pytest.mark.parametrize(("literal", "is_county_unit"), [
    ("Macoupin Co.", True), ("Co. Chirripo", False), ("Macoupin County State", False), ("INDIANA", False),
])
def test_existing_county_unit_rule_only_classifies_an_unambiguous_state_fragment(tmp_path, literal, is_county_unit):
    rig = captured_location_run(tmp_path)
    source = CapturedLocationSources(rig.blobs)._answer("wikidata", "ILLINOIS")
    readings = tuple(Reading(name, "label", name, "raw_reading", f"ILLINOIS\n{literal}") for name in ("1A", "1B"))
    owner = FieldTask("country", False, FieldValue(),
        tuple(Candidate(name, "ILLINOIS", "ILLINOIS", "state-text") for name in ("1A", "1B")), ("wikidata",))
    target = FieldTask("province_state", False, FieldValue(),
        tuple(Candidate(name, literal, literal, "other-text") for name in ("1A", "1B")), ("wikidata",))
    proposal = _LocationProposal("province_state", "ILLINOIS", ("1A", "1B"), "country", "country",
        source, source.candidates[0])
    assert _location_readers_agree(proposal, {"country": owner, "province_state": target}, readings,
        {"country": [source]}) is is_county_unit
