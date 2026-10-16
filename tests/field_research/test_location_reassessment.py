"""Explicit family recovery uses retained readers and fresh qualified evidence."""
from contextlib import asynccontextmanager
from dataclasses import replace
import hashlib

import pytest

from specimen_digitization.application.domain import Evidence, FieldValue, ValueState
from specimen_digitization.application.human_field_carry import KEY as CARRY_KEY
from specimen_digitization.application.integrity import verify_evidence
from specimen_digitization.application.workflow import FIELD_RESEARCH, OperationalBlock
from specimen_digitization.field_research.contracts import FieldAnswer, FieldOutcome, PlaceRef
from specimen_digitization.field_research.location_reassessment import (
    FIELDS, KEY, active_keys, commit, eligible_keys, working_run,
)
from specimen_digitization.field_research.step import build_tasks

from test_step import FakeSources, Scripted, TGN_PLACES, build_rig, mounted


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


def execute(rig, monkeypatch, *, outage=False, sources=Places):
    monkeypatch.setitem(TGN_PLACES, "Clark County",
        ("counties", ("Illinois", "United States")))
    resolver = Scripted({key: locate for key in FIELDS})
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
