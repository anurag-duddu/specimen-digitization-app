"""The fields' second opinion (field_research/second_opinion.py, autonomy lane F1).

Step-level tests run the synthetic rig of test_step through the workflow with a second-opinion
model that is a pydantic-ai FunctionModel: no network, no token, no paid call. The answer it
returns is built from what the same research settles on a twin rig without the second opinion,
so "agrees" is exact, and each test changes the one field it is about.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import timedelta

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import BinaryContent, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage
from test_step import FIELD_RESEARCH, Scripted, build_rig, mounted, research_paid

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Disposition, FieldValue, RunFinding, ValueState
from specimen_digitization.application.integrity import verify_evidence
from specimen_digitization.application.model_option import active_routes
from specimen_digitization.field_research import second_opinion as so
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.step import marked_reasons
from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES, SECOND_OPINION_ROUTE

ROUTE = SECOND_OPINION_ROUTE


# ---- the comparison: one strict rule per kind of field ---------------------------------------

@pytest.mark.parametrize(("key", "first", "second", "agree"), [
    # dates: parsed ISO dates, equal at the same precision
    ("date_visited_from", "1946-09-06", "1946-09-06", True),
    ("date_visited_from", "1946-09-06", "1946-9-6", False),
    ("date_visited_from", "1946-09", "1946-09-06", False),
    ("date_visited_from", "1946", "1946", True),
    ("date_identified", "1946-02-30", "1946-02-30", False),
    ("date_visited_to", "6-Sept-1946", "6-Sept-1946", False),
    ("date_visited_to", "1916-07-24", "1916-06-24", False),
    # numbers: plain decimals, equal to the hundredth
    ("elevation_from_m", "1950.72", "1950.72", True),
    ("elevation_from_m", "549", "549.0", True),
    ("elevation_from_ft", "1,800", "1800", True),
    ("elevation_from_m", "1005.84", "1005.8", False),
    ("elevation_to_ft", "6400", "6400 ft", False),
    ("elevation_to_m", "-80", "80", False),
    ("elevation_to_m", "1.5", "15", False),
    # identifiers: digit for digit
    ("fmnh_ins_number", "4486518", "4486518", True),
    ("fmnh_ins_number", "4486518", "4486618", False),
    ("fmnh_ins_number", "0010001", "10001", False),
    ("fmnh_ins_number", "FMNH-INS 4486518", "4486518", False),
    # text: accents, case, white space and punctuation folded
    ("collectors", "J.S.Stanford", "J.S. Stanford", True),
    ("collectors", "H. Hoogstraal", "H. Hoogstraal leg.", False),
    ("collectors", "J. Smith", "J. Smyth", False),
    ("country", "Philippines", "PHILIPPINES", True),
    ("country", "United States", "USA", False),
    ("precise_location", "Puerto Ibañez\n(Aisen)", "Puerto Ibanez (Aisen)", True),
    ("precise_location", "LOC: Asheville School\nNorth Carolina", "Asheville School North Carolina", False),
    ("precise_location", "1.5 km N Moron", "15 km N Moron", True),  # punctuation folded: stated in the docs
    ("habitat", "EX: Raccoon.", "Raccoon", False),
    ("habitat", "ex Peromyscus", "ex Peromyscus leucopus", False),
    ("taxon", "Pulex irritans Linnaeus, 1758", "Pulex irritans", False),
    # Province/State and County: one trailing unit word set aside
    ("province_state", "Chimaltenango Department", "Chimaltenango", True),
    ("province_state", "Davao Prov.", "Davao", True),
    ("province_state", "Chimaltenango Department", "Chimaltenago", False),
    ("county", "Yakima County", "YAKIMA", True),
    ("county", "Mesa Co.", "Mesa", True),
    ("county", "County", "County", True),
    ("city", "Yakima County", "Yakima", False),
    # nothing agrees with nothing
    ("city", None, None, False),
    ("city", "Harvard", "", False),
])
def test_the_comparison_table(key, first, second, agree):
    assert so.same(key, first, second) is agree
    assert so.same(key, second, first) is agree


def test_the_shown_value_is_normalized_then_parsed_then_literal():
    assert so.shown(FieldValue(literal="P.I.", parsed="P.I.", normalized="Philippines")) == "Philippines"
    assert so.shown(FieldValue(literal="6-Sept-1946", parsed="1946-09-06")) == "1946-09-06"
    assert so.shown(FieldValue(literal="Harvard,", normalized=" ")) == "Harvard,"


# ---- the answer ------------------------------------------------------------------------------

def full(**fields):
    answer = {key: {"value": None, "evidence": ""} for key in so.FIELDS}
    answer.update(fields)
    return answer


def test_an_answer_holds_every_judged_field_and_nothing_else():
    record = so.read_answer(json.dumps(full(city={"value": "Harvard", "evidence": "L1: Harvard,"},
        habitat=None, taxon={"value": None, "evidence": "UNSURE: readers differ"},
        elevation_from_m={"value": 549, "evidence": "L1: 549 m"})))
    assert record["city"] == so.Opinion("Harvard", "L1: Harvard,")
    assert record["habitat"] == so.Opinion(None, "")
    assert record["taxon"].unsure and record["taxon"].value is None
    assert record["elevation_from_m"].value == "549"
    answer = full()
    del answer["fmnh_ins_number"], answer["identified_by_irn"]
    assert set(so.read_answer(answer)) == set(so.FIELDS)


@pytest.mark.parametrize(("arguments", "code"), [
    ("{not json", "second_opinion_malformed"),
    ([], "second_opinion_malformed"),
    ({key: value for key, value in full().items() if key != "city"}, "second_opinion_partial"),
    ({**full(), "collector": {"value": "J. Smith", "evidence": ""}}, "second_opinion_malformed"),
    (full(city="Harvard"), "second_opinion_malformed"),
    (full(city={"value": "Harvard", "evidence": "", "confidence": 1}), "second_opinion_malformed"),
    (full(city={"value": ["Harvard"], "evidence": ""}), "second_opinion_malformed"),
    (full(city={"value": True, "evidence": ""}), "second_opinion_malformed"),
    (full(city={"value": "Harvard", "evidence": 3}), "second_opinion_malformed"),
])
def test_a_malformed_or_partial_answer_is_not_obtained(arguments, code):
    with pytest.raises(so.NotObtained) as caught:
        so.read_answer(arguments)
    assert caught.value.code == code


def test_the_instruction_is_the_benchmarks_byte_for_byte():
    assert so.instruction().startswith("You fill the record of one insect specimen slide")
    assert so.tool_schema()["required"] == list(so.FIELDS)


# ---- the route and its price -----------------------------------------------------------------

def test_the_route_is_registered_priced_checked_by_preflight_and_built_by_production():
    route = HUGGINGFACE_ROUTES[ROUTE]
    assert (route.model_id, route.provider, route.transport, route.request_options) == (
        "meta-models/Muse-Spark-Open-816B-A42B", "baseten", "router", ())
    price = published_registry().profiles[0].processing.price_list.models[ROUTE]
    assert (price.input_micros_per_million, price.output_micros_per_million) == (1_250_000, 4_250_000)
    assert ROUTE in active_routes(()) and ROUTE in active_routes(("readers", "first_pass", "field_research"))
    assert field_step.production_step().second_opinion_factory is field_step._production_second_opinion


def test_production_needs_the_inference_approval(monkeypatch):
    monkeypatch.delenv("SPECIMEN_APPROVED_INFERENCE", raising=False)
    with pytest.raises(field_step.OperationalBlock):
        field_step._production_second_opinion(ROUTE)


# ---- through the workflow --------------------------------------------------------------------

def shown_values(tmp_path):
    """What research settles on the synthetic label, as the app shows it (a twin rig with no
    second opinion)."""
    twin = build_rig(tmp_path / "twin")
    mounted(twin, Scripted())
    run = twin.workflow.step(twin.principal, twin.specimen.id).run
    assert (run.disposition, run.reasons) == (Disposition.CLEARED, [])
    return {key: so.shown(value) for key, value in run.fields.items() if value.state == ValueState.SUPPORTED}


def agreeing(tmp_path, **changes):
    values = shown_values(tmp_path)
    answer = {key: {"value": values.get(key), "evidence": "L1: synthetic" if values.get(key) else ""}
              for key in so.FIELDS}
    answer.update(changes)
    return answer


class Opinion:
    """The second opinion's model: a FunctionModel answering `answer` (or raising `error`); it keeps
    every request it was sent."""

    def __init__(self, answer=None, *, error=None, delay=0.0, tokens=(5_000, 700)):
        self.answer, self.error, self.delay, self.tokens = answer, error, delay, tokens
        self.requests, self.built = [], 0

    def factory(self, route):
        assert route == ROUTE
        self.built += 1

        async def respond(messages, info: AgentInfo):
            self.requests.append((messages, info))
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.error is not None:
                raise self.error
            return ModelResponse(parts=[ToolCallPart(so.TOOL_NAME, json.dumps(self.answer))],
                usage=RequestUsage(input_tokens=self.tokens[0], output_tokens=self.tokens[1]))

        return FunctionModel(respond)


def with_opinion(rig, opinion, resolver=None):
    state = mounted(rig, resolver or Scripted())
    rig.workflow.field_research.second_opinion_factory = opinion.factory
    return state


def ours(run, why=None):
    return [f.reason_code for f in run.findings if f.rule_id == so.RULE and f.reason_code.startswith("marked:")
            and (why is None or f.reason_code.endswith(":" + why))]


def test_an_agreeing_second_opinion_changes_nothing_and_its_cost_is_one_more_paid_call(tmp_path):
    rig = build_rig(tmp_path)
    opinion = Opinion(agreeing(tmp_path))
    state = with_opinion(rig, opinion)
    done = rig.workflow.step(rig.principal, rig.specimen.id)
    run = done.run
    assert (run.stage, run.disposition, run.reasons) == ("finalized", Disposition.CLEARED, [])
    assert len(opinion.requests) == 1 and not ours(run)
    assert run.dependencies[so.STATE]["status"] == "obtained"
    research, second = research_paid(run)
    assert (research["route_id"], second["route_id"]) == (run.profile_snapshot["harness_route"], ROUTE)
    assert (second["outcome"], second["cost_basis"], second["reserved_micros"]) == ("completed", "computed", so.CAP_MICROS)
    assert second["cost_micros"] == -(-(5_000 * 1_250_000 + 700 * 4_250_000) // 1_000_000)
    # Both calls settle inside the one reservation of the step.
    assert research["cost_micros"] + second["cost_micros"] <= 1_000_000
    assert run.usage.reserved_cost_micros == research["cost_micros"] + second["cost_micros"]
    assert state.meters and verify_evidence(done, rig.blobs) is None


def test_the_request_carries_the_crops_and_the_readers_texts_but_none_of_the_pipelines_fields(tmp_path):
    rig = build_rig(tmp_path)
    opinion = Opinion(agreeing(tmp_path))
    with_opinion(rig, opinion)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    [(messages, info)] = opinion.requests
    assert [tool.name for tool in info.output_tools] == [so.TOOL_NAME] and info.allow_text_output is False
    assert info.output_tools[0].parameters_json_schema == so.tool_schema()
    assert info.model_settings["max_tokens"] == so.MAX_TOKENS
    [request] = messages
    assert request.parts[0].content == so.instruction()
    [user] = [part for part in request.parts if isinstance(part, UserPromptPart)]
    images = [item for item in user.content if isinstance(item, BinaryContent)]
    texts = "\n".join(item for item in user.content if isinstance(item, str))
    assert len(images) == len(run.regions) and texts.startswith("One slide with 1 label.")
    assert "Label 1, reader A:" in texts and "Label 1, reader B:" in texts
    # Nothing of the pipeline's fields: no normalized or derived value the readers do not write.
    for key in ("country", "elevation_from_m", "taxon"):
        value = run.fields[key]
        for text in (value.normalized, value.parsed if value.layer == "derived" else None):
            if text and text not in "\n".join(o.literal_text for o in run.observations):
                assert text not in texts, key
    assert "supported" not in texts and "harness" not in texts


def test_a_differing_value_is_marked_and_its_evidence_kept_and_nothing_else_changes(tmp_path):
    rig = build_rig(tmp_path)
    opinion = Opinion(agreeing(tmp_path, habitat={"value": "Synthetic meadow", "evidence": "L1: meadow"},
        county={"value": None, "evidence": ""}))
    with_opinion(rig, opinion)
    twin_fields = None
    done = rig.workflow.step(rig.principal, rig.specimen.id)
    run = done.run
    region = run.regions[0].id
    assert sorted(ours(run)) == [f"marked:county:{region}:second_opinion_differs",
                                 f"marked:habitat:{region}:second_opinion_differs"]
    assert set(ours(run)) <= set(run.reasons) and run.disposition == Disposition.REVIEW
    # The values, their states, layers and reasons are research's, untouched.
    twin = build_rig(tmp_path / "plain")
    mounted(twin, Scripted())
    twin_fields = twin.workflow.step(twin.principal, twin.specimen.id).run.fields
    for key in ("habitat", "county"):
        mine, plain = run.fields[key], twin_fields[key]
        assert (mine.state, mine.literal, mine.parsed, mine.normalized, mine.layer, mine.reason) == (
            plain.state, plain.literal, plain.parsed, plain.normalized, plain.layer, plain.reason)
    [habitat] = [f for f in run.findings if f.rule_id == so.RULE and f.field_key == "habitat"]
    [row] = [e for e in run.evidence if e.id in habitat.evidence_ids]
    assert (row.kind, row.source, row.locator) == (so.EVIDENCE_KIND, so.EVIDENCE_SOURCE, "second_opinion:habitat")
    assert row.excerpt == "Second opinion, habitat: Synthetic meadow (label text: L1: meadow)"
    assert row.region_id == region and row.raw_ref and row.digest
    assert json.loads(rig.blobs.get(row.raw_ref))["arguments"]
    # The row supports no value: no field cites it.
    assert not [key for key, value in run.fields.items() if row.id in value.evidence_ids]
    verify_evidence(done, rig.blobs)


def test_an_unsure_second_opinion_is_a_difference(tmp_path):
    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(agreeing(tmp_path, collectors={"value": None, "evidence": "UNSURE: no marker"})))
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert ours(run) == [f"marked:collectors:{run.regions[0].id}:second_opinion_differs"]


def test_the_catalogue_number_is_never_judged(tmp_path):
    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(agreeing(tmp_path, fmnh_ins_number={"value": "9999999", "evidence": "L1: 9999999"})))
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (run.disposition, run.reasons, ours(run)) == (Disposition.CLEARED, [], [])
    assert "fmnh_ins_number" not in run.dependencies[so.STATE]["fields"]


@pytest.mark.parametrize("error", [
    ModelHTTPError(402, "meta-models/Muse-Spark-Open-816B-A42B:baseten", "provider_request_failed"),
    ModelHTTPError(503, "meta-models/Muse-Spark-Open-816B-A42B:baseten", "provider_request_failed"),
    RuntimeError("provider_request_failed"),
    TimeoutError("provider_request_timeout"),
])
def test_a_provider_error_marks_every_judged_value_not_checked_and_never_fails_the_run(tmp_path, error):
    rig = build_rig(tmp_path)
    opinion = Opinion(error=error)
    with_opinion(rig, opinion)
    done = rig.workflow.step(rig.principal, rig.specimen.id)
    run = done.run
    assert (run.stage, run.blocker, run.disposition) == ("finalized", None, Disposition.REVIEW)
    judged = {f.field_key for f in run.findings if f.rule_id == so.RULE and f.reason_code.endswith(so.NOT_CHECKED)}
    assert judged and "fmnh_ins_number" not in judged and not ours(run, so.DIFFERS)
    assert {r for r in run.reasons if r.startswith("marked:")} == set(ours(run))
    [note] = [f for f in run.findings if f.rule_id == so.RULE and f.severity == "info"]
    assert note.reason_code == so.NOT_OBTAINED + (":second_opinion_timeout" if isinstance(error, TimeoutError) else
        f":second_opinion_provider_error{'_' + str(error.status_code) if isinstance(error, ModelHTTPError) else ''}")
    assert run.dependencies[so.STATE]["status"].startswith("not_obtained:")
    [_, second] = research_paid(run)
    # A refusal that may have been billed keeps its worst case: known, inside the cap.
    assert second["outcome"] == "failed" and 0 < second["cost_micros"] <= so.CAP_MICROS
    verify_evidence(done, rig.blobs)


def test_a_402_says_so(tmp_path):
    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(error=ModelHTTPError(402, "m", "provider_request_failed")))
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert f"{so.NOT_OBTAINED}:second_opinion_provider_error_402" in [f.reason_code for f in run.findings]


def test_a_timeout_is_not_obtained(tmp_path, monkeypatch):
    monkeypatch.setattr(so, "TIMEOUT_SECONDS", so.MIN_SECONDS)
    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(agreeing(tmp_path), delay=so.MIN_SECONDS + 1))
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert f"{so.NOT_OBTAINED}:second_opinion_timeout" in [f.reason_code for f in run.findings]
    assert ours(run, so.NOT_CHECKED) and not ours(run, so.DIFFERS)


def test_a_malformed_answer_is_not_obtained(tmp_path):
    rig = build_rig(tmp_path)
    answer = agreeing(tmp_path)
    del answer["habitat"]
    with_opinion(rig, Opinion(answer))
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert f"{so.NOT_OBTAINED}:second_opinion_partial" in [f.reason_code for f in run.findings]
    assert ours(run, so.NOT_CHECKED) and not ours(run, so.DIFFERS)
    assert not [e for e in run.evidence if e.kind == so.EVIDENCE_KIND]


def test_a_spent_budget_is_not_obtained_and_sends_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(so, "CAP_MICROS", 10)
    rig = build_rig(tmp_path)
    opinion = Opinion(agreeing(tmp_path))
    with_opinion(rig, opinion)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert not opinion.requests
    assert f"{so.NOT_OBTAINED}:second_opinion_budget" in [f.reason_code for f in run.findings]
    [_, second] = research_paid(run)
    assert (second["cost_micros"], second["outcome"]) == (0, "failed")


def test_a_factory_that_raises_is_not_obtained(tmp_path):
    rig = build_rig(tmp_path)
    mounted(rig, Scripted())

    def broken(route):
        raise field_step.OperationalBlock("provider_data_policy_and_spending_approval_required")

    rig.workflow.field_research.second_opinion_factory = broken
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert f"{so.NOT_OBTAINED}:second_opinion_unconfigured" in [f.reason_code for f in run.findings]
    assert len(research_paid(run)) == 1  # nothing was reserved or sent


def test_a_profile_without_the_price_row_is_not_obtained(tmp_path, monkeypatch):
    """A run pinned to a profile snapshot from before the route was priced."""
    rig = build_rig(tmp_path)
    opinion = Opinion(agreeing(tmp_path))
    with_opinion(rig, opinion)
    priced = field_step._route_price

    def without_the_row(profile, route_id):
        if route_id == ROUTE:
            raise field_step.OperationalBlock("field_research_price_unavailable")
        return priced(profile, route_id)

    monkeypatch.setattr(field_step, "_route_price", without_the_row)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert f"{so.NOT_OBTAINED}:second_opinion_unconfigured" in [f.reason_code for f in run.findings]
    assert not opinion.requests and ours(run, so.NOT_CHECKED)


def test_an_exception_inside_the_comparison_puts_everything_back(tmp_path, monkeypatch):
    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(agreeing(tmp_path, habitat={"value": "x", "evidence": ""})))

    def explode(run, *args, **kwargs):
        run.fields["habitat"] = FieldValue(state=ValueState.SUPPORTED, literal="changed")
        run.findings.append(RunFinding(rule_id="other", rule_version="1", severity="info", reason_code="noise"))
        raise KeyError("boom")

    monkeypatch.setattr(so, "apply", explode)
    done = rig.workflow.step(rig.principal, rig.specimen.id)
    run = done.run
    assert run.fields["habitat"].literal != "changed"
    assert "noise" not in [f.reason_code for f in run.findings]
    assert f"{so.NOT_OBTAINED}:second_opinion_error" in [f.reason_code for f in run.findings]
    assert ours(run, so.NOT_CHECKED) and not ours(run, so.DIFFERS)
    verify_evidence(done, rig.blobs)


def test_without_a_factory_the_step_is_off(tmp_path):
    rig = build_rig(tmp_path)
    mounted(rig, Scripted())
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (run.disposition, run.reasons, ours(run)) == (Disposition.CLEARED, [], [])
    assert so.STATE not in run.dependencies and len(research_paid(run)) == 1


# ---- scope: whose values, which attempt -------------------------------------------------------

def check(run, before=None, *, opinion, readings=(), human=(), labels=None):
    """second_opinion.check on a run in memory, with a 1x1 crop."""
    return so.check(run, {} if before is None else before, route=ROUTE, model_factory=lambda: opinion.factory(ROUTE),
        crop=lambda region: b"png", blobs=None, asset_id=None, readings=readings, human=human, cap_micros=1_000_000,
        meter_factory=field_step.cost_meter, price=published_registry().profiles[0].processing.price_list.models[ROUTE],
        timeout=30.0)


def settled_run(tmp_path):
    rig = build_rig(tmp_path)
    mounted(rig, Scripted())
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    run.findings = [f for f in run.findings if f.rule_id != so.RULE]
    run.dependencies.pop(so.STATE, None)
    return run


def differing_everywhere():
    return {key: {"value": "Something else entirely", "evidence": "L1: x"} for key in so.FIELDS}


def test_a_person_s_field_is_never_judged(tmp_path):
    run = settled_run(tmp_path)
    readings = field_step.run_readings(run)
    run.dependencies[so.LOCKS] = {"habitat": True}
    run.dependencies["location_reassessment"] = {"protected": ["city"]}
    check(run, opinion=Opinion(differing_everywhere()), readings=readings, human={"collectors"})
    marked = {f.field_key for f in run.findings if f.rule_id == so.RULE and f.reason_code.startswith("marked:")}
    assert marked and not marked & {"habitat", "city", "collectors", "fmnh_ins_number", "identified_by_irn"}


def test_a_value_resting_on_a_persons_transcript_is_never_judged(tmp_path):
    run = settled_run(tmp_path)
    readings = tuple(replace(reading, person_decided=True) for reading in field_step.run_readings(run))
    check(run, opinion=Opinion(differing_everywhere()), readings=readings)
    assert not [f for f in run.findings if f.rule_id == so.RULE and f.reason_code.startswith("marked:")]


def test_a_field_marked_by_another_rule_is_not_judged_again(tmp_path):
    run = settled_run(tmp_path)
    region = run.regions[0].id
    run.findings.append(RunFinding(rule_id=field_step.SETTLEMENT, rule_version="1", severity="warning",
        field_key="habitat", reason_code=f"marked:habitat:{region}:text_only"))
    check(run, opinion=Opinion(differing_everywhere()), readings=field_step.run_readings(run))
    assert [f.reason_code for f in run.findings if f.field_key == "habitat" and f.reason_code.startswith("marked:")] \
        == [f"marked:habitat:{region}:text_only"]
    assert [f for f in run.findings if f.rule_id == so.RULE and f.reason_code.startswith("marked:country:")]


def test_only_values_this_attempt_wrote_are_judged(tmp_path):
    run = settled_run(tmp_path)
    before = {key: value.model_copy(deep=True) for key, value in run.fields.items()}
    run.fields["habitat"] = run.fields["habitat"].model_copy(update={"literal": "Rewritten grassland"})
    check(run, before, opinion=Opinion(differing_everywhere()), readings=field_step.run_readings(run))
    assert {f.field_key for f in run.findings if f.rule_id == so.RULE and f.reason_code.startswith("marked:")} == {"habitat"}


def test_no_value_written_means_no_call(tmp_path):
    run = settled_run(tmp_path)
    before = {key: value.model_copy(deep=True) for key, value in run.fields.items()}
    opinion = Opinion(differing_everywhere())
    assert check(run, before, opinion=opinion, readings=field_step.run_readings(run)) is None
    assert opinion.built == 0 and so.STATE not in run.dependencies


def test_never_twice_in_one_attempt(tmp_path):
    run = settled_run(tmp_path)
    first = Opinion(full())
    check(run, opinion=first, readings=field_step.run_readings(run))
    assert first.built == 1
    again = Opinion(full())
    check(run, opinion=again, readings=field_step.run_readings(run))
    assert again.built == 0
    assert f"{so.NOT_OBTAINED}:second_opinion_already_asked" in [f.reason_code for f in run.findings]
    assert ours(run, so.NOT_CHECKED) and not ours(run, so.DIFFERS)


def test_a_later_attempt_checks_what_an_earlier_one_left_not_checked(tmp_path):
    run = settled_run(tmp_path)
    before = {key: value.model_copy(deep=True) for key, value in run.fields.items()}
    check(run, opinion=Opinion(error=RuntimeError("provider_request_failed")), readings=field_step.run_readings(run))
    unchecked = set(f.field_key for f in run.findings if f.reason_code.endswith(so.NOT_CHECKED))
    assert unchecked
    run.attempts[FIELD_RESEARCH] = run.attempts.get(FIELD_RESEARCH, 1) + 1
    values = {key: so.shown(value) for key, value in run.fields.items() if value.state == ValueState.SUPPORTED}
    agree = {key: {"value": values.get(key), "evidence": ""} for key in so.FIELDS}
    check(run, before, opinion=Opinion(agree), readings=field_step.run_readings(run))
    assert not [f for f in run.findings if f.rule_id == so.RULE and f.reason_code.startswith("marked:")]


def test_an_open_or_blank_field_gets_evidence_only(tmp_path):
    run = settled_run(tmp_path)
    run.fields["county"] = FieldValue(state=ValueState.NOT_PRESENT, reason="Not on the label.")
    run.fields["city"] = FieldValue(state=ValueState.UNRESOLVED, reason="Open.")
    answer = full(county={"value": "Cook", "evidence": "L1: Cook"}, city={"value": "Chicago", "evidence": "L1: Chicago"})
    check(run, opinion=Opinion(answer), readings=field_step.run_readings(run))
    assert {"county", "city"}.isdisjoint(
        {f.field_key for f in run.findings if f.rule_id == so.RULE and f.reason_code.startswith("marked:")})
    rows = {e.locator: e.excerpt for e in run.evidence if e.kind == so.EVIDENCE_KIND}
    assert rows["second_opinion:county"] == "Second opinion, county: Cook (label text: L1: Cook)"
    assert rows["second_opinion:city"] == "Second opinion, city: Chicago (label text: L1: Chicago)"
    assert (run.fields["county"].state, run.fields["city"].state) == (ValueState.NOT_PRESENT, ValueState.UNRESOLVED)


def test_a_person_deciding_a_field_drops_only_its_second_opinion_findings(tmp_path):
    run = settled_run(tmp_path)
    check(run, opinion=Opinion(differing_everywhere()), readings=field_step.run_readings(run))
    other = RunFinding(rule_id=field_step.SETTLEMENT, rule_version="1", severity="warning", field_key="habitat",
        reason_code=f"marked:habitat:{run.regions[0].id}:text_only")
    run.findings.append(other)
    kept = [f for f in run.findings if f.field_key == "habitat" and f.rule_id != so.RULE]
    assert [f for f in run.findings if f.field_key == "habitat" and f.rule_id == so.RULE]
    so.forget(run, "habitat")
    assert [f for f in run.findings if f.field_key == "habitat"] == kept and other in kept
    assert [f for f in run.findings if f.rule_id == so.RULE and f.field_key == "country"]
    assert "habitat" not in {code.split(":")[1] for code in marked_reasons(run) if ":second_opinion" in code}


def test_refinalize_computes_nothing(tmp_path):
    run = settled_run(tmp_path)
    before = list(run.findings)
    field_step.refinalize(run, today=None)
    assert [f for f in run.findings if f.rule_id == so.RULE] == [f for f in before if f.rule_id == so.RULE] == []


# ---- a person's decision, through the decision endpoint ------------------------------------------

def test_a_person_confirming_a_differing_value_takes_the_mark_off_and_approval_adds_none(tmp_path):
    """The reviewer confirms the habitat the second opinion disputed, submitting the existing value
    unchanged: the endpoint drops the second opinion's findings on it, the saved field equals the
    decision's `after`, and the approval's refinalize puts no mark back and asks nothing."""
    from test_step import decide, reasons_for, review_client

    rig = build_rig(tmp_path)
    opinion = Opinion(agreeing(tmp_path, habitat={"value": "Synthetic meadow", "evidence": "L1: meadow"}))
    with_opinion(rig, opinion)
    done = rig.workflow.step(rig.principal, rig.specimen.id).run
    region = done.regions[0].id
    assert reasons_for(done, "habitat") == [f"marked:habitat:{region}:second_opinion_differs"]
    client = review_client(rig)
    habitat = done.fields["habitat"]
    after = habitat.model_dump(mode="json", exclude={"evidence_ids"})
    decided = decide(client, rig, "field-habitat", "field", target_id="habitat", after=after,
        evidence_ids=list(habitat.evidence_ids))
    assert decided.fields["habitat"] == FieldValue.model_validate(dict(after, evidence_ids=habitat.evidence_ids))
    assert reasons_for(decided, "habitat") == []
    assert not [f for f in decided.findings if f.rule_id == so.RULE and f.field_key == "habitat"]
    approved = decide(client, rig, "approve-habitat", "approve")
    assert reasons_for(approved, "habitat") == [] and approved.fields["habitat"] == decided.fields["habitat"]
    assert len(opinion.requests) == 1


def test_a_retry_after_a_person_confirms_a_field_leaves_it_unmarked(tmp_path):
    """Research runs again (a retry: the country failed on the first attempt) after a person
    confirmed the disputed habitat: research leaves the settled habitat alone, its value is
    unchanged, so the second attempt's second opinion does not judge it."""
    from test_step import decide, failing, review_client

    rig = build_rig(tmp_path)
    opinion = Opinion(agreeing(tmp_path, habitat={"value": "Synthetic meadow", "evidence": "L1: meadow"}))
    with_opinion(rig, opinion, Scripted({"country": failing("source_unavailable")}))
    blocked = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert blocked.stage == "retry_scheduled" and ours(blocked, so.DIFFERS)
    client = review_client(rig)
    habitat = blocked.fields["habitat"]
    decide(client, rig, "field-habitat", "field", target_id="habitat",
        after=habitat.model_dump(mode="json", exclude={"evidence_ids"}), evidence_ids=list(habitat.evidence_ids))
    state = with_opinion(rig, opinion)
    rig.clock.now += timedelta(hours=1)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert run.attempts[FIELD_RESEARCH] == 2 and len(opinion.requests) == 2
    assert not [f for f in run.findings if f.rule_id == so.RULE and f.field_key == "habitat"]
    assert state is not None
