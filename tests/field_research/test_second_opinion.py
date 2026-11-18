"""The fields' second opinion (field_research/second_opinion.py) as its own workflow step
(application/second_opinion_step.py): one stored result on the run, marks derived at every finalize
from it and the current values, and no failure of the step blocking or failing the run.

Each case of the two Codex verdicts on the earlier structure (PR #456, heads 54f7f987 and a4782758)
has a test here, its expected outcome under this structure in its docstring.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import pytest
from pydantic_ai.messages import BinaryContent, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage
from test_step import FIELD_RESEARCH, Gazetteer, Scripted, answering, build_rig, failing, mounted, research_paid

from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import AuditEvent, Disposition, FieldValue, ValueState
from specimen_digitization.application.integrity import verify_evidence
from specimen_digitization.application.model_option import active_routes
from specimen_digitization.application.worker_deadline import WorkerDeadlineExceeded
from specimen_digitization.application.workflow import SECOND_OPINION
from specimen_digitization.field_research import second_opinion as so
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer
from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES, SECOND_OPINION_ROUTE

# The product's behaviour: the marks are derived (tests/conftest.py).
USES_SECOND_OPINION = True
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
    # a decimal separator or a sign attached to digits is kept
    ("precise_location", "1.5 km N Moron", "15 km N Moron", False),
    ("precise_location", "14,5 km NNW", "14.5 km NNW", False),
    ("precise_location", "14.5 km NNW", "14.5km NNW.", True),
    ("habitat", "-80 m", "80 m", False),
    ("precise_location", "80-90 m", "8090 m", False),
    ("precise_location", "Aisen-Chili", "Aisen Chili", True),
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


# ---- the answer: the tool schema, field by field ----------------------------------------------

def full(**fields):
    answer = {key: {"value": None, "evidence": ""} for key in so.FIELDS}
    answer.update(fields)
    return answer


def test_an_answer_holds_all_twenty_fields_each_with_value_and_evidence():
    record = so.read_answer(json.dumps(full(city={"value": "Harvard", "evidence": "L1: Harvard,"},
        taxon={"value": None, "evidence": "UNSURE: readers differ"},
        elevation_from_m={"value": "549", "evidence": "L1: 549 m"})))
    assert record["city"] == so.Opinion("Harvard", "L1: Harvard,")
    assert record["habitat"] == so.Opinion(None, "")
    assert record["taxon"].unsure and record["taxon"].value is None
    assert record["elevation_from_m"].value == "549"
    assert set(record) == set(so.FIELDS)


@pytest.mark.parametrize("arguments", [
    "{not json",
    [],
    # a missing field: a judged one, the catalogue number, the IRN
    {key: value for key, value in full().items() if key != "city"},
    {key: value for key, value in full().items() if key != "fmnh_ins_number"},
    {key: value for key, value in full().items() if key not in ("fmnh_ins_number", "identified_by_irn")},
    # an extra field
    {**full(), "collector": {"value": "J. Smith", "evidence": ""}},
    # a null entry (Codex round 2, 6: "city": null was read as not on the label)
    full(city=None),
    # a bare value, an extra key, a wrong type
    full(city="Harvard"),
    full(city={"value": "Harvard", "evidence": "", "confidence": 1}),
    full(city={"value": ["Harvard"], "evidence": ""}),
    full(city={"value": True, "evidence": ""}),
    full(city={"value": "Harvard", "evidence": 3}),
    {key: {} for key in so.FIELDS},
    full(city={"evidence": "L1: Harvard"}),
    full(city={"value": "Harvard"}),
    full(elevation_from_m={"value": 549, "evidence": ""}),
], ids=lambda value: None)
def test_anything_but_the_schema_is_malformed(arguments):
    """Codex round 1, 8 and round 2, 6: schema-invalid and partial answers are "not obtained:
    malformed", with no verdicts (the workflow test below)."""
    with pytest.raises(so.NotObtained) as caught:
        so.read_answer(arguments)
    assert caught.value.code == "malformed"


def test_the_instruction_is_the_benchmarks_byte_for_byte():
    assert so.instruction().startswith("You fill the record of one insect specimen slide")
    assert so.tool_schema()["required"] == list(so.FIELDS)


# ---- the route and its price -----------------------------------------------------------------

def test_the_route_is_registered_priced_checked_by_preflight_and_mounted_in_production():
    route = HUGGINGFACE_ROUTES[ROUTE]
    assert (route.model_id, route.provider, route.transport, route.request_options) == (
        "meta-models/Muse-Spark-Open-816B-A42B", "baseten", "router", ())
    price = published_registry().profiles[0].processing.price_list.models[ROUTE]
    assert (price.input_micros_per_million, price.output_micros_per_million) == (1_250_000, 4_250_000)
    assert ROUTE in active_routes(()) and ROUTE in active_routes(("readers", "first_pass", "field_research"))
    assert so.production_step().model_factory is so.production_model
    assert so.STEP == SECOND_OPINION == "field_second_opinion"
    from types import SimpleNamespace

    from specimen_digitization.research_harness.workflow_bridge import compose_field_research_workflow

    composed = compose_field_research_workflow(SimpleNamespace(), repository=None, field_research=object())
    assert isinstance(composed.second_opinion, so.SecondOpinionStep)


def test_production_needs_the_inference_approval(monkeypatch):
    monkeypatch.delenv("SPECIMEN_APPROVED_INFERENCE", raising=False)
    with pytest.raises(RuntimeError, match="approval_required"):
        so.production_model()


def test_a_crop_over_the_providers_aspect_limit_is_padded():
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (2000, 20), "black").save(out, format="PNG")
    png, width, height, padded = so.pad(out.getvalue(), 2000, 20)
    assert padded and (width, height) == (2000, 50) and so.pad(out.getvalue(), 2000, 20)[0] == png
    assert so.pad(png, width, height)[3] is False


# ---- the rig ---------------------------------------------------------------------------------

class Opinion:
    """The second opinion's model: a FunctionModel answering `answer` (or raising `error`); it keeps
    every request it was sent."""

    def __init__(self, answer=None, *, error=None, delay=0.0, tokens=(5_000, 700), raw=None):
        self.answer, self.error, self.delay, self.tokens, self.raw = answer, error, delay, tokens, raw
        self.requests, self.built = [], 0

    def factory(self):
        self.built += 1

        async def respond(messages, info: AgentInfo):
            self.requests.append((messages, info))
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.error is not None:
                raise self.error
            return ModelResponse(parts=[ToolCallPart(so.TOOL_NAME, self.raw if self.raw is not None
                else json.dumps(self.answer))], usage=RequestUsage(input_tokens=self.tokens[0],
                output_tokens=self.tokens[1]))

        return FunctionModel(respond)


def with_opinion(rig, opinion, resolver=None, **kwargs):
    state = mounted(rig, resolver or Scripted(), **kwargs)
    rig.workflow.second_opinion = None if opinion is None else so.SecondOpinionStep(model_factory=opinion.factory)
    return state


def to_end(rig):
    return rig.workflow.drain(rig.principal, rig.specimen.id)


def main_like(tmp_path, resolver=None, **kwargs):
    """The same run on main: no second opinion step and no derived marks."""
    twin = build_rig(tmp_path)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(so, "derived", lambda run, readings=(): [])
        mounted(twin, resolver or Scripted(), **kwargs)
        done = to_end(twin)
    return done.run


def shown_values(tmp_path):
    return {key: so.shown(value) for key, value in main_like(tmp_path / "shown").fields.items()
            if value.state == ValueState.SUPPORTED}


def agreeing(tmp_path, **changes):
    values = shown_values(tmp_path)
    answer = {key: {"value": values.get(key), "evidence": "L1: synthetic" if values.get(key) else ""}
              for key in so.FIELDS}
    answer.update(changes)
    return answer


def own(run, why=None):
    return [code for code in run.reasons if so.own(code) and (why is None or code.endswith(":" + why))]


def step_paid(run):
    return [call for call in run.paid_calls if call["step"] == so.STEP]


def judged_keys(run):
    return [key for key in so.JUDGED if so._settled(run.fields.get(key))]


def research_part(run):
    """Everything of the run research decides: fields, findings, evidence and the reasons that are
    not the second opinion's; the record's own identifiers (labels, rows, readings) set aside, since
    two rigs draw different ones."""
    import re

    names = {region.id: f"L{n}" for n, region in enumerate(run.regions, start=1)}
    uid = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

    def plain(value):
        text = json.dumps(value, sort_keys=True, default=str)
        for region, name in names.items():
            text = text.replace(region, name)
        return json.loads(uid.sub("ID", text))

    def field(value):
        dumped = value.model_dump(mode="json")
        dumped["evidence_relations"] = sorted(dumped.get("evidence_relations", {}).values())
        return dumped

    return (plain({key: field(value) for key, value in run.fields.items()}),
        plain([finding.model_dump(mode="json", exclude={"id"}) for finding in run.findings]),
        plain([(item.kind, item.source, item.locator, item.excerpt) for item in run.evidence]),
        plain([code for code in run.reasons if not so.own(code)]))


# ---- P1: its own step, after research, before the record is finalized -------------------------

def test_research_then_the_step_then_the_record_finalized_and_an_agreeing_opinion_clears(tmp_path):
    rig = build_rig(tmp_path)
    opinion = Opinion(agreeing(tmp_path))
    with_opinion(rig, opinion)
    researched = rig.workflow.step(rig.principal, rig.specimen.id).run
    # Field research completed and finalized in memory; the record waits for the step, unfinalized.
    assert FIELD_RESEARCH in researched.completed_steps and not opinion.requests
    assert (researched.stage, researched.disposition, researched.blocker) == (SECOND_OPINION, None, None)
    assert own(researched) and all(code.endswith(":" + so.NOT_CHECKED) for code in own(researched))
    done = rig.workflow.step(rig.principal, rig.specimen.id)
    run = done.run
    assert (run.stage, run.disposition, run.blocker, run.reasons) == ("finalized", Disposition.CLEARED, None, [])
    assert len(opinion.requests) == 1 and run.attempts[so.STEP] == 1
    # Its own paid call, its own attempt, its own settlement; research's untouched.
    [research] = research_paid(run)
    [second] = step_paid(run)
    assert (second["route_id"], second["attempt"], second["outcome"], second["cost_basis"]) == (
        ROUTE, 1, "completed", "computed")
    assert second["reserved_micros"] == so.CAP_MICROS
    assert second["cost_micros"] == -(-(5_000 * 1_250_000 + 700 * 4_250_000) // 1_000_000)
    assert run.usage.reserved_cost_micros == research["cost_micros"] + second["cost_micros"]
    assert run.dependencies["ordinary_cost_settlements"][f"{so.STEP}:1"] == {
        "reserved_micros": so.CAP_MICROS, "settled_micros": second["cost_micros"]}
    assert run.lease_until is None and run.usage.reserved_active_seconds == 0
    assert [e.reason for e in done.audit if e.action == "workflow_step"][-2:] == [FIELD_RESEARCH, so.STEP]
    verify_evidence(done, rig.blobs)


def test_research_is_mains_with_the_step_present(tmp_path):
    """P1: research's code path is main's: its fields, findings, evidence and reasons are the same
    with the step present (and differing everywhere) as on main."""
    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(full()))
    run = to_end(rig).run
    assert research_part(run) == research_part(main_like(tmp_path / "main"))
    assert own(run, so.DIFFERS)


def test_the_request_carries_the_crops_and_the_readers_texts_but_none_of_the_pipelines_fields(tmp_path):
    rig = build_rig(tmp_path)
    opinion = Opinion(agreeing(tmp_path))
    with_opinion(rig, opinion)
    run = to_end(rig).run
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
    for key in ("country", "elevation_from_m", "taxon"):
        value = run.fields[key]
        for text in (value.normalized, value.parsed if value.layer == "derived" else None):
            if text and text not in "\n".join(o.literal_text for o in run.observations):
                assert text not in texts, key
    assert "supported" not in texts and "harness" not in texts


# ---- P2: one stored result, no finding, no mark, no evidence blob ------------------------------

def test_the_one_stored_key_holds_the_status_the_judged_fields_and_the_answer_inline(tmp_path):
    rig = build_rig(tmp_path)
    answer = agreeing(tmp_path, habitat={"value": "Synthetic meadow", "evidence": "L1: meadow"})
    with_opinion(rig, Opinion(answer))
    done = to_end(rig)
    run = done.run
    stored = run.second_opinion
    assert stored["status"] == so.OBTAINED and stored["attempt"] == 1 and stored["route"] == ROUTE
    assert stored["answer"] == answer and stored["instruction_sha256"] == so.INSTRUCTION_SHA256
    assert stored["labels"] == {"1": run.regions[0].id} and stored["padded_labels"] == []
    assert set(stored["fields"]) == set(judged_keys(run))
    assert stored["fields"]["habitat"] == {"compared": so.shown(run.fields["habitat"]),
        "value": "Synthetic meadow", "evidence": "L1: meadow", "verdict": "differs"}
    assert stored["fields"]["country"]["verdict"] == "agrees"
    assert "fmnh_ins_number" not in stored["fields"] and "identified_by_irn" not in stored["fields"]
    # No finding, no evidence row, no blob of its own; every field is research's.
    assert not [f for f in run.findings if "second_opinion" in f.rule_id + f.reason_code]
    assert not [e for e in run.evidence if "second_opinion" in (e.kind or "") + (e.source or "")]
    assert research_part(run)[:3] == research_part(main_like(tmp_path / "main"))[:3]
    verify_evidence(done, rig.blobs)
    # It is the run's own field, a few kilobytes, read back exactly.
    assert len(json.dumps(stored)) < 8_000
    assert rig.repository.get(rig.principal.scope, rig.specimen.id).run.second_opinion == stored


def test_the_key_is_omitted_while_unset(tmp_path):
    from test_step import make_specimen

    from specimen_digitization.application.storage import LocalBlobs

    dumped = make_specimen(LocalBlobs(tmp_path), "x").run.model_dump(mode="json")
    assert "second_opinion" not in dumped and "person_decided_fields" not in dumped


# ---- P3: marks derived at finalize from the key and the current values -------------------------

def test_a_differing_value_is_marked_and_nothing_else_changes(tmp_path):
    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(agreeing(tmp_path, habitat={"value": "Synthetic meadow", "evidence": "L1: meadow"},
        county={"value": None, "evidence": ""})))
    run = to_end(rig).run
    region = run.regions[0].id
    assert sorted(own(run)) == [f"marked:county:{region}:second_opinion_differs",
                                f"marked:habitat:{region}:second_opinion_differs"]
    assert run.disposition == Disposition.REVIEW and run.stage == "finalized"
    assert research_part(run) == research_part(main_like(tmp_path / "main"))[:3] + (
        [code for code in run.reasons if not so.own(code)],)


def test_an_unsure_second_opinion_is_a_difference(tmp_path):
    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(agreeing(tmp_path, collectors={"value": None, "evidence": "UNSURE: no marker"})))
    run = to_end(rig).run
    assert [code.split(":")[1] for code in own(run)] == ["collectors"]


def test_the_catalogue_number_and_the_irn_are_never_judged(tmp_path):
    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(agreeing(tmp_path, fmnh_ins_number={"value": "999", "evidence": "L1: 999"})))
    run = to_end(rig).run
    assert run.reasons == [] and so.EXCLUDED == {"fmnh_ins_number", "identified_by_irn"}


def test_a_value_changed_after_it_was_judged_is_not_checked_until_judged_again(tmp_path):
    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(agreeing(tmp_path)))
    run = to_end(rig).run
    assert run.reasons == [] and not so.due(run)
    run.fields["habitat"].literal = run.fields["habitat"].normalized = run.fields["habitat"].parsed = "Changed"
    assert so.reasons(run) == [f"marked:habitat:{run.regions[0].id}:second_opinion_not_checked"]
    assert so.due(run)


def test_a_field_another_rule_marks_and_an_open_or_blank_field_get_no_mark(tmp_path):
    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(full()))
    run = to_end(rig).run
    marked = {code.split(":")[1] for code in run.reasons if code.startswith("marked:") and not so.own(code)}
    open_ = {key for key, value in run.fields.items() if not so._settled(value)}
    assert {code.split(":")[1] for code in own(run)} == set(judged_keys(run)) - marked - open_
    assert not {code.split(":")[1] for code in own(run)} & (marked | open_)


def test_only_a_run_on_the_units_path_is_marked(tmp_path):
    rig = build_rig(tmp_path)
    with_opinion(rig, None)
    run = to_end(rig).run
    assert own(run)
    run.first_pass_path = "old"
    assert so.reasons(run) == [] and not so.due(run)


# ---- the step's failures never block or fail the run -----------------------------------------

def stage_and_blocker_unchanged(run, main):
    """No failure of the step changes the run's stage or blocker: research's, finalized with none;
    the values it answers for are not checked; research's part is main's."""
    assert (run.stage, run.blocker) == (main.stage, main.blocker) == ("finalized", None)
    assert run.disposition == Disposition.REVIEW
    assert {code.split(":")[1] for code in own(run, so.NOT_CHECKED)} == {
        code.split(":")[1] for code in own(run)} and own(run)
    assert research_part(run)[:3] == research_part(main)[:3]


@pytest.mark.parametrize(("make", "code"), [
    (lambda: Opinion(error=__import__("pydantic_ai.exceptions").exceptions.ModelHTTPError(
        402, "second-opinion", body="credit")), "provider_error_402"),
    (lambda: Opinion(error=__import__("pydantic_ai.exceptions").exceptions.ModelHTTPError(
        503, "second-opinion", body="down")), "provider_error_503"),
    (lambda: Opinion(error=RuntimeError("provider_request_failed")), "provider_error"),
    (lambda: Opinion(raw="{not json"), "malformed"),
    (lambda: Opinion({key: value for key, value in full().items() if key != "fmnh_ins_number"}), "malformed"),
    (lambda: Opinion(full(city=None)), "malformed"),
], ids=["402", "503", "error", "not-json", "partial", "null-entry"])
def test_a_provider_error_or_a_malformed_answer_is_not_obtained_and_never_blocks(tmp_path, make, code):
    rig = build_rig(tmp_path)
    opinion = make()
    with_opinion(rig, opinion)
    run = to_end(rig).run
    stage_and_blocker_unchanged(run, main_like(tmp_path / "main"))
    assert (run.second_opinion["status"], run.second_opinion["reason"]) == (so.NOT_OBTAINED, code)
    assert "fields" not in run.second_opinion and "answer" not in run.second_opinion
    # A malformed answer is asked again once; a provider error is not.
    assert len(opinion.requests) == (2 if code == "malformed" else 1)
    [paid] = step_paid(run)
    assert paid["failure_code"] == code and paid["outcome"] in ("failed", "unknown")


def test_a_timeout_is_not_obtained(tmp_path, monkeypatch):
    monkeypatch.setattr(so, "TIMEOUT_SECONDS", 15.5)
    monkeypatch.setattr(so, "MIN_SECONDS", 15.0)
    rig = build_rig(tmp_path)
    opinion = Opinion(full(), delay=2.0)
    with_opinion(rig, opinion)
    real = so.ask

    async def short(model, labels, text, meter, *, deadline, **kwargs):
        return await real(model, labels, text, meter, deadline=deadline - 14.0, **kwargs)

    monkeypatch.setattr(so, "ask", short)
    run = to_end(rig).run
    assert run.second_opinion["reason"] == "timeout"
    stage_and_blocker_unchanged(run, main_like(tmp_path / "main"))
    # Sent and unanswered: its worst case, known.
    [paid] = step_paid(run)
    assert paid["cost_basis"] == "computed" and paid["cost_micros"] > 0


def test_an_exception_anywhere_in_the_step_is_not_obtained(tmp_path, monkeypatch):
    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(full()))
    monkeypatch.setattr(so, "obtain", lambda run, **kwargs: (_ for _ in ()).throw(ValueError("boom")))
    run = to_end(rig).run
    assert run.second_opinion["reason"] == "error"
    stage_and_blocker_unchanged(run, main_like(tmp_path / "main"))
    # Its spend is not known: the reservation stays held.
    [paid] = step_paid(run)
    assert (paid["cost_basis"], paid["cost_micros"]) == ("reserved", so.CAP_MICROS)


def test_a_failure_while_building_the_request_releases_the_reservation(tmp_path, monkeypatch):
    """Codex round 1, 4: a request that cannot be built is never sent and costs a known zero: the
    step's reservation is settled to zero."""
    rig = build_rig(tmp_path)
    opinion = Opinion(full())
    with_opinion(rig, opinion)
    monkeypatch.setattr(so, "request_parts", lambda labels: (_ for _ in ()).throw(RuntimeError("parts")))
    run = to_end(rig).run
    assert run.second_opinion["reason"] == "error" and not opinion.requests
    [research] = research_paid(run)
    [paid] = step_paid(run)
    assert (paid["cost_micros"], paid["cost_basis"]) == (0, "computed")
    assert run.usage.reserved_cost_micros == research["cost_micros"]


def test_a_model_factory_that_refuses_and_a_missing_price_row_are_not_obtained(tmp_path, monkeypatch):
    rig = build_rig(tmp_path)
    with_opinion(rig, None)
    rig.workflow.second_opinion = so.SecondOpinionStep(model_factory=lambda: (_ for _ in ()).throw(OSError("no")))
    run = to_end(rig).run
    assert run.second_opinion["reason"] == "unconfigured"
    stage_and_blocker_unchanged(run, main_like(tmp_path / "main"))
    rig = build_rig(tmp_path / "priceless")
    opinion = Opinion(full())
    with_opinion(rig, opinion)
    monkeypatch.setattr(so, "route_price", lambda run: None)
    run = to_end(rig).run
    assert run.second_opinion["reason"] == "unconfigured" and not step_paid(run) and not opinion.requests
    assert so.STEP not in run.attempts


def test_switched_off_says_not_checked_and_asks_nothing(tmp_path):
    """Codex round 1, 7: switched off, every value it answers for is marked not checked."""
    rig = build_rig(tmp_path)
    with_opinion(rig, None)
    run = to_end(rig).run
    assert run.second_opinion["status"] == so.SWITCHED_OFF and not step_paid(run)
    stage_and_blocker_unchanged(run, main_like(tmp_path / "main"))
    assert {code.split(":")[1] for code in own(run)} == set(judged_keys(run)) - {
        code.split(":")[1] for code in run.reasons if code.startswith("marked:") and not so.own(code)}


def test_money_the_run_cannot_afford_is_not_obtained_with_nothing_reserved(tmp_path, monkeypatch):
    rig = build_rig(tmp_path)
    opinion = Opinion(full())
    with_opinion(rig, opinion)
    monkeypatch.setattr(so, "CAP_MICROS", 5_000_000)
    run = to_end(rig).run
    assert run.second_opinion["reason"] == "budget" and not opinion.requests and not step_paid(run)
    [research] = research_paid(run)
    assert run.usage.reserved_cost_micros == research["cost_micros"]
    stage_and_blocker_unchanged(run, main_like(tmp_path / "main"))


def test_a_request_dearer_than_its_cap_is_not_sent(tmp_path, monkeypatch):
    rig = build_rig(tmp_path)
    opinion = Opinion(full())
    with_opinion(rig, opinion)
    monkeypatch.setattr(so, "CAP_MICROS", 10)
    run = to_end(rig).run
    assert run.second_opinion["reason"] == "budget" and not opinion.requests
    [paid] = step_paid(run)
    assert (paid["cost_micros"], paid["cost_basis"]) == (0, "computed")


def test_the_attempts_used_end_it_unsent(tmp_path):
    rig = build_rig(tmp_path)
    opinion = Opinion(full())
    with_opinion(rig, opinion)
    pending = rig.workflow.step(rig.principal, rig.specimen.id)
    pending.run.attempts[so.STEP] = pending.run.profile.execution.max_attempts
    rig.repository.save(rig.principal, pending, pending.version, "attempts", "attempts")
    run = to_end(rig).run
    assert run.second_opinion["reason"] == "attempts_used" and not opinion.requests and run.stage == "finalized"


def test_a_worker_deadline_during_the_request_is_found_after_the_lease_and_never_sent_twice(tmp_path):
    """Codex round 1, 3 and round 2, 1: the worker's deadline (a BaseException) ends the worker in the
    request. The intent saved before it holds the run; once its lease ends, the next step records it
    "not obtained: outcome_unknown", its whole reservation held, and finalizes the record, with the
    stage and blocker research gave it. Nothing is sent again."""
    rig = build_rig(tmp_path)
    opinion = Opinion(error=WorkerDeadlineExceeded())
    with_opinion(rig, opinion)
    rig.workflow.step(rig.principal, rig.specimen.id)
    with pytest.raises(WorkerDeadlineExceeded):
        rig.workflow.step(rig.principal, rig.specimen.id)
    held = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    # The open intent sets no blocker: it is never an unknown outcome that blocks.
    assert (held.stage, held.blocker, held.attempts[so.STEP]) == (SECOND_OPINION, None, 1)
    assert held.second_opinion["status"] == so.ASKING and held.lease_until and not step_paid(held)
    from specimen_digitization.application.storage import work_available_at

    assert work_available_at(rig.repository.get(rig.principal.scope, rig.specimen.id)) == held.lease_until
    # Within the lease: left as it is.
    assert rig.workflow.step(rig.principal, rig.specimen.id).version == rig.repository.get(
        rig.principal.scope, rig.specimen.id).version
    rig.clock.now = datetime.fromisoformat(held.lease_until) + timedelta(seconds=1)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert run.second_opinion["reason"] == "outcome_unknown" and len(opinion.requests) == 1
    [paid] = step_paid(run)
    assert (paid["outcome"], paid["cost_basis"], paid["cost_micros"]) == ("unknown", "reserved", so.CAP_MICROS)
    stage_and_blocker_unchanged(run, main_like(tmp_path / "main"))
    assert rig.workflow.step(rig.principal, rig.specimen.id).run == run  # finalized: nothing more


def test_the_steps_own_save_failing_is_found_the_same_way(tmp_path):
    """Codex round 2, 5: the step stores nothing beside the run, so evidence verification cannot fail
    because of it; its one write is the run's save. When that fails, the record is the intent's, and
    the next step after the lease finalizes it not obtained."""
    rig = build_rig(tmp_path)
    opinion = Opinion(agreeing(tmp_path))
    with_opinion(rig, opinion)
    rig.workflow.step(rig.principal, rig.specimen.id)
    save = rig.repository.save

    def failing_save(principal, specimen, revision, key, *args, **kwargs):
        if key.startswith("second-opinion:"):
            raise OSError("storage unavailable")
        return save(principal, specimen, revision, key, *args, **kwargs)

    rig.repository.save = failing_save
    with pytest.raises(OSError):
        rig.workflow.step(rig.principal, rig.specimen.id)
    rig.repository.save = save
    held = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    rig.clock.now = datetime.fromisoformat(held.lease_until) + timedelta(seconds=1)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert run.second_opinion["reason"] == "outcome_unknown" and len(opinion.requests) == 1
    stage_and_blocker_unchanged(run, main_like(tmp_path / "main"))


# ---- with research's retries ------------------------------------------------------------------

def test_no_step_while_research_has_a_retry_pending_then_one(tmp_path):
    """Codex round 1, 5: the step runs only once research has nothing left to ask again, so it never
    spends research's retry money."""
    rig = build_rig(tmp_path)
    opinion = Opinion(full())
    with_opinion(rig, opinion, Scripted({"country": failing("source_unavailable")}))
    blocked = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert blocked.stage == "retry_scheduled" and not opinion.requests and not step_paid(blocked)
    assert blocked.second_opinion is None
    mounted(rig, Scripted())
    rig.clock.now += timedelta(hours=1)
    run = to_end(rig).run
    assert run.attempts[FIELD_RESEARCH] == 2 and len(opinion.requests) == 1 and run.stage == "finalized"


def test_feet_inference_on_a_retry_is_mains_with_the_step_present(tmp_path):
    """Codex round 2, 2: the Philippines settles, the feet expert cannot resolve "Elev.6400" against
    "Elev.6400'", and elevation_from_m fails retryably. On the retry the metres expert answers absent;
    main infers 6400 ft and derives its partners. With the step present the retry's research is the
    same: nothing the step left (a not-checked mark is derived, never stored) is read by research."""
    from test_elevations_and_extent import CANNOT, LACKS, NO_PLACES_BELOW, PARTNERS, PHILIPPINES, elevation_label

    text, second = elevation_label("Elev.6400", "Elev.6400'")
    first = {**PHILIPPINES, **NO_PLACES_BELOW, "elevation_from_ft": answering(CANNOT),
             **dict.fromkeys(PARTNERS, answering(LACKS)), "elevation_from_m": failing("source_unavailable")}
    retry = {**first, "elevation_from_m": answering(LACKS)}

    def run_twice(folder, *, step):
        rig = build_rig(folder, text, second)
        with pytest.MonkeyPatch.context() as patch:
            if not step:
                patch.setattr(so, "derived", lambda run, readings=(): [])
            mounted(rig, Scripted(first), sources=Gazetteer)
            rig.workflow.second_opinion = so.SecondOpinionStep(model_factory=Opinion(full()).factory) if step else None
            blocked = rig.workflow.step(rig.principal, rig.specimen.id).run
            assert blocked.stage == "retry_scheduled"
            if step:
                assert own(blocked, so.NOT_CHECKED) and "country" in {c.split(":")[1] for c in own(blocked)}
            mounted(rig, Scripted(retry), sources=Gazetteer)
            rig.clock.now += timedelta(hours=1)
            return to_end(rig).run

    with_step, on_main = run_twice(tmp_path / "step", step=True), run_twice(tmp_path / "main", step=False)
    assert on_main.fields["elevation_from_ft"].parsed == "6400" and on_main.fields["elevation_from_m"].parsed == "1950.72"
    assert research_part(with_step) == research_part(on_main)


# ---- a person's authority ---------------------------------------------------------------------

def test_a_persons_field_with_the_apps_payload_is_never_marked_and_survives_a_retry(tmp_path):
    """Codex round 1, 1: the reviewer confirms the habitat with the app's own save payload (no layer).
    The endpoint records it on the run and in the audit as recorded; no mark is derived on it, before
    or after a retry that researches it again and an opinion that disputes it."""
    from test_step import decide, failing as fail, review_client

    rig = build_rig(tmp_path)
    opinion = Opinion(agreeing(tmp_path, habitat={"value": "Synthetic meadow", "evidence": "L1: meadow"}))
    with_opinion(rig, opinion, Scripted({"country": fail("source_unavailable")}))
    blocked = rig.workflow.step(rig.principal, rig.specimen.id).run
    habitat = blocked.fields["habitat"]
    app_after = {"literal": habitat.literal, "parsed": habitat.parsed, "normalized": habitat.normalized,
                 "state": habitat.state.value, "reason": habitat.reason}
    decided = decide(review_client(rig), rig, "field-habitat", "field", target_id="habitat", after=app_after,
        evidence_ids=list(habitat.evidence_ids))
    assert decided.person_decided_fields == ["habitat"]
    stored = rig.repository.get(rig.principal.scope, rig.specimen.id)
    [event] = [e for e in stored.audit if e.action == "review_field"]
    assert event.after[so.DECIDED_MARK] == "habitat"
    mounted(rig, Scripted())
    rig.clock.now += timedelta(hours=1)
    run = to_end(rig).run
    assert run.attempts[FIELD_RESEARCH] == 2 and len(opinion.requests) == 1
    assert run.second_opinion["fields"]["habitat"]["verdict"] == "differs"
    assert not [code for code in own(run) if code.startswith("marked:habitat:")]
    assert so.authority(run) >= {"habitat"}


def test_a_value_resting_on_a_persons_transcript_is_never_marked(tmp_path):
    """Codex round 1, 2: a person's transcript decision binds the label; no mark is derived on a value
    resting on it, whatever the stored verdicts say."""
    from specimen_digitization.field_research.contracts import Reading

    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(full()))
    run = to_end(rig).run
    assert own(run)
    readings = tuple(Reading(r.name, r.region_id, r.observation_id, r.input_source, r.text, person_decided=True,
        units=r.units) for r in field_step.run_readings(run))
    assert so.derived(run, readings) == []


def test_carried_decisions_locks_and_protected_fields_are_a_persons(tmp_path):
    rig = build_rig(tmp_path)
    with_opinion(rig, None)
    run = to_end(rig).run
    run.dependencies[field_step.CARRY_KEY] = {"habitat": {}}
    run.dependencies[so.LOCKS] = {"county": {"selection_id": "s"}}
    run.dependencies["location_reassessment"] = {"protected": ["city"]}
    run.person_decided_fields = ["collectors"]
    held = {"habitat", "county", "city", "collectors"}
    assert so.authority(run) >= held
    assert not {code.split(":")[1] for code in so.reasons(run)} & held


def test_a_legacy_records_field_decisions_are_adopted_once_at_load(tmp_path):
    """Codex round 2, 3: a decision saved before the endpoint recorded it on the run is named only by
    the specimen's review audit. It is adopted where the record is loaded, and no mark is derived on it.
    A record with nothing to adopt loads exactly as stored. (The stored payload is built by hand: the
    repository refuses to save a review event the endpoint did not make.)"""
    from specimen_digitization.application import active_graph

    rig = build_rig(tmp_path)
    with_opinion(rig, None)
    done = to_end(rig)
    loaded = rig.repository.get(rig.principal.scope, rig.specimen.id)
    assert loaded.run.person_decided_fields == [] and loaded.model_dump(mode="json") == done.model_dump(mode="json")
    payload = done.model_dump(mode="json")
    payload["audit"] += [AuditEvent(actor="reviewer-1", action=action, reason="Reviewed.", before={"run_id": run_id},
        after=after).model_dump(mode="json") for action, run_id, after in (
        ("review_field", done.run.id, {"field_key": "habitat", "state": "supported"}),
        ("review_taxonomy_resolution", done.run.id, {"field_key": "taxon"}),
        ("review_field", "an-earlier-run", {"field_key": "county"}),
        ("review_field", done.run.id, {"field_key": "city", so.DECIDED_MARK: "city"}))]
    loaded = active_graph.unpack(payload, rig.blobs)
    assert loaded.run.person_decided_fields == ["habitat", "taxon"]
    assert not {code.split(":")[1] for code in so.reasons(loaded.run)} & {"habitat", "taxon"}
    assert "county" in {code.split(":")[1] for code in so.reasons(loaded.run)}


def test_a_restore_returns_the_revisions_own_result_and_list_self_consistently(tmp_path):
    """Codex round 2, 4: a history restore returns the run to the restored revision's own state: its
    stored result and its person-decided list. A decision made after that revision is undone by the
    restore itself (not a defect), and is not adopted back at load: its audit says it was recorded.
    The restored reasons are what the derivation gives on the restored run."""
    from test_step import decide, review_client

    from specimen_digitization.application.history_restore import restored_specimen

    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(agreeing(tmp_path, habitat={"value": "Synthetic meadow", "evidence": "L1: meadow"})))
    revision = to_end(rig)
    region = revision.run.regions[0].id
    assert own(revision.run) == [f"marked:habitat:{region}:second_opinion_differs"]
    habitat = revision.run.fields["habitat"]
    decided = decide(review_client(rig), rig, "field-habitat", "field", target_id="habitat",
        after=habitat.model_dump(mode="json", exclude={"evidence_ids"}), evidence_ids=list(habitat.evidence_ids))
    assert decided.person_decided_fields == ["habitat"] and not own(decided)
    base = rig.repository.get(rig.principal.scope, rig.specimen.id)
    source = rig.repository.version(rig.principal.scope, rig.specimen.id, revision.version)
    restored = restored_specimen(base, source)
    run = restored.run
    assert run.person_decided_fields == [] and run.second_opinion == revision.run.second_opinion
    assert own(run) == so.reasons(run) == [f"marked:habitat:{region}:second_opinion_differs"]
    saved = rig.repository.save(rig.principal, restored, base.version, "restore", "restore")
    assert rig.repository.get(rig.principal.scope, saved.id).run.person_decided_fields == []


def test_a_persons_approval_refinalizes_with_the_marks_derived_from_the_key(tmp_path):
    from test_step import decide, review_client

    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(agreeing(tmp_path, habitat={"value": "Synthetic meadow", "evidence": "L1: meadow"})))
    to_end(rig)
    approved = decide(review_client(rig), rig, "approve", "approve")
    # A person's approval is the person's (the G51 ruling): no second-opinion code, as main's marks.
    assert own(approved) == so.reasons(approved) == [] and approved.disposition == Disposition.CLEARED


# ---- no double run, no double charge -----------------------------------------------------------

def test_a_recheck_with_the_values_judged_asks_nothing_and_a_not_obtained_keeps_earlier_verdicts(tmp_path):
    rig = build_rig(tmp_path)
    opinion = Opinion(agreeing(tmp_path))
    with_opinion(rig, opinion)
    run = to_end(rig).run
    # A completed run reaching the handover again (Retry, Resume): the recheck; nothing is due.
    specimen = rig.repository.get(rig.principal.scope, rig.specimen.id)
    specimen.run.stage, specimen.run.disposition = "plan", None
    rig.repository.save(rig.principal, specimen, specimen.version, "resume", "resume")
    again = to_end(rig).run
    assert len(opinion.requests) == 1 and again.reasons == [] and len(step_paid(again)) == 1
    # A not obtained result keeps the verdicts given on values that are still current.
    so.record(run, so.Result(so.NOT_OBTAINED, "provider_error_402"), attempt=2, at="t")
    assert run.second_opinion["status"] == so.NOT_OBTAINED and run.second_opinion["fields"]
    assert so.reasons(run) == []


# ---- Codex round 3 on 91176adf: the optional step's lifecycle ----------------------------------

def graph_size(specimen):
    from specimen_digitization.application import active_graph

    return len(active_graph.encoded(active_graph.envelope(specimen)))


BULKY = {key: {"value": "v" * 2_000, "evidence": "L1: " + "x" * 2_000} for key in so.FIELDS}


def pending_rig(folder, opinion, monkeypatch):
    from specimen_digitization.application import active_graph

    rig = build_rig(folder)
    with_opinion(rig, opinion)
    pending = rig.workflow.step(rig.principal, rig.specimen.id)
    monkeypatch.setattr(active_graph, "GRAPH_THRESHOLD", 0)
    return rig, pending


def test_a_record_near_its_size_limit_asks_nothing_and_never_blocks(tmp_path, monkeypatch):
    """Codex round 4, 1: the intent would fit just below the limit, and a refused factory's paid call
    and settlement would cross it. With less than twice MARGIN_BYTES below the limit nothing is
    reserved, saved as an intent or sent: "not obtained: record_too_large", the record finalized with
    research's stage and blocker."""
    from specimen_digitization.application import active_graph, second_opinion_step

    opinion = Opinion(error=RuntimeError("refused"))
    rig, pending = pending_rig(tmp_path, opinion, monkeypatch)
    monkeypatch.setattr(active_graph, "NORMAL_GRAPH_LIMIT", graph_size(pending) + 1_024)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (run.second_opinion["status"], run.second_opinion["reason"]) == (so.NOT_OBTAINED, "record_too_large")
    assert not opinion.requests and not step_paid(run) and so.STEP not in run.attempts
    stage_and_blocker_unchanged(run, main_like(tmp_path / "main"))
    assert second_opinion_step.headroom(rig.repository.get(rig.principal.scope, rig.specimen.id)) >= 0


def test_a_result_that_would_leave_too_little_room_is_not_stored_and_a_later_approval_fits(tmp_path, monkeypatch):
    """Codex round 4, 2: an obtained result that would leave less than MARGIN_BYTES below the limit is
    not stored ("not obtained: result_too_large"), so a person's approval afterwards (its values digest)
    is not the write that crosses it."""
    from test_step import decide, review_client

    from specimen_digitization.application import active_graph, second_opinion_step

    rig, pending = pending_rig(tmp_path, Opinion(BULKY), monkeypatch)
    monkeypatch.setattr(active_graph, "NORMAL_GRAPH_LIMIT", graph_size(pending) + 2 * second_opinion_step.MARGIN_BYTES)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert (run.second_opinion["status"], run.second_opinion["reason"]) == (so.NOT_OBTAINED, "result_too_large")
    assert "answer" not in run.second_opinion and "fields" not in run.second_opinion
    stage_and_blocker_unchanged(run, main_like(tmp_path / "main"))
    approved = decide(review_client(rig), rig, "approve-after", "approve")
    assert (approved.stage, approved.blocker) == ("finalized", None)


def test_the_stored_answer_is_bounded(tmp_path):
    """Codex round 4, 1 and 2: the stored answer is the 20 values and their texts, each clipped."""
    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(BULKY))
    stored = to_end(rig).run.second_opinion
    assert stored["status"] == so.OBTAINED and set(stored["answer"]) == set(so.FIELDS)
    assert all(len(entry["evidence"]) == len(entry["value"]) == so.TEXT_LIMIT for entry in stored["answer"].values())
    assert all(len(entry["evidence"]) <= so.TEXT_LIMIT for entry in stored["fields"].values())
    assert len(json.dumps(stored)) < 40 * so.TEXT_LIMIT * 4



def test_a_decision_while_the_intent_is_open_abandons_it_and_the_run_moves_on(tmp_path, monkeypatch):
    """Codex round 3, 2: after the intent is saved, a person approves the record. The approval's
    finalize abandons the open intent (not obtained, "abandoned", its reservation held) and finalizes
    as on main; the provider's result then loses its save, and the step returns the record the approval
    left. Nothing is blocked; later steps see a finalized record."""
    from test_step import decide, review_client

    rig = build_rig(tmp_path)
    client = review_client(rig)
    opinion = Opinion(agreeing(tmp_path))
    with_opinion(rig, opinion)
    rig.workflow.step(rig.principal, rig.specimen.id)
    real = so.obtain

    def approve_meanwhile(run, **kwargs):
        decide(client, rig, "approve-meanwhile", "approve")
        return real(run, **kwargs)

    monkeypatch.setattr(so, "obtain", approve_meanwhile)
    returned = rig.workflow.step(rig.principal, rig.specimen.id)
    stored = rig.repository.get(rig.principal.scope, rig.specimen.id)
    assert returned.version == stored.version
    run = stored.run
    # The approval is the person's: cleared with no second-opinion code (the G51 ruling).
    assert (run.stage, run.blocker) == ("finalized", None) and run.disposition == Disposition.CLEARED
    assert (run.second_opinion["status"], run.second_opinion["reason"]) == (so.NOT_OBTAINED, "abandoned")
    [paid] = step_paid(run)
    assert (paid["cost_basis"], paid["cost_micros"]) == ("reserved", so.CAP_MICROS) and run.lease_until is None
    assert not own(run) and len(opinion.requests) == 1
    assert rig.workflow.step(rig.principal, rig.specimen.id).run == run


def test_a_reservation_that_raises_ends_it_not_obtained_and_releases_its_holds(tmp_path, monkeypatch):
    """Codex round 3, 3: a ledger that cannot be read while reserving: no request, the monthly caps'
    holds released, not obtained ("budget"), the record finalized; nothing is retried."""
    from specimen_digitization.application import lane_allowance, tenant_budget

    main = main_like(tmp_path / "main")
    rig = build_rig(tmp_path)
    opinion = Opinion(full())
    with_opinion(rig, opinion)
    rig.workflow.step(rig.principal, rig.specimen.id)
    released = []
    real_release = tenant_budget.release_unsent
    monkeypatch.setattr(tenant_budget, "release_unsent",
        lambda run, step: released.append(step) or real_release(run, step))
    monkeypatch.setattr(lane_allowance, "reserve_step",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("ledger unreadable")))
    run = to_end(rig).run
    assert run.second_opinion["reason"] == "budget" and not opinion.requests and not step_paid(run)
    assert released == [so.STEP] and so.STEP not in run.attempts
    [research] = research_paid(run)
    assert run.usage.reserved_cost_micros == research["cost_micros"]
    stage_and_blocker_unchanged(run, main)


class SimpleRun:
    regions = ()
    observations = ()
    profile = type("P", (), {"routes": ()})()
    fields = {}


def test_a_crop_read_that_hangs_ends_by_the_deadline(monkeypatch):
    """Codex round 3, 4: reading the crops runs in a worker thread waited for until the deadline."""
    import time

    monkeypatch.setattr(so, "MIN_SECONDS", 0.2)
    started = time.monotonic()
    result = so.obtain(SimpleRun(), model_factory=lambda: None, crops=lambda: time.sleep(5),
        price=object(), seconds=0.5, meter_factory=lambda cap, price: None)
    assert (result.status, result.reason) == (so.NOT_OBTAINED, "no_time")
    assert time.monotonic() - started < 2


def test_a_client_that_never_closes_ends_by_the_deadline(monkeypatch):
    """Codex round 3, 4: the client's closing is cut at the deadline too; the answer stands."""
    import time

    from specimen_digitization.field_research import experts

    async def never(model):
        await asyncio.sleep(60)

    monkeypatch.setattr(experts, "_close_client", never)
    label = so.Label(1, "r1", b"png", 10, 10, ("a", "b"))
    price = published_registry().profiles[0].processing.price_list.models[ROUTE]
    meter = field_step.cost_meter(so.CAP_MICROS, price)
    started = time.monotonic()
    arguments = asyncio.run(so.ask(Opinion(full()).factory(), [label], "x", meter, deadline=time.monotonic() + 1.0))
    assert json.loads(arguments) == full() and time.monotonic() - started < 3
    assert meter.outstanding_micros == 0


def test_the_token_budget_guards_it_as_it_guards_a_mandatory_paid_step(tmp_path):
    """Codex round 3, 5: at the run's token limit the step does not run ("not obtained: run_limit");
    otherwise it reserves tokens as a mandatory paid step does and counts what the provider reported."""
    rig = build_rig(tmp_path)
    opinion = Opinion(agreeing(tmp_path), tokens=(5_000, 700))
    with_opinion(rig, opinion)
    pending = rig.workflow.step(rig.principal, rig.specimen.id)
    before = (pending.run.usage.reserved_tokens, pending.run.usage.tokens)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert run.second_opinion["status"] == so.OBTAINED
    assert (run.usage.reserved_tokens, run.usage.tokens) == (before[0] + so.RESERVED_TOKENS, before[1] + 5_700)
    limited = build_rig(tmp_path / "limited")
    blocked = Opinion(full())
    with_opinion(limited, blocked)
    pending = limited.workflow.step(limited.principal, limited.specimen.id)
    pending.run.usage.reserved_tokens = pending.run.profile.execution.max_tokens
    limited.repository.save(limited.principal, pending, pending.version, "tokens", "tokens")
    run = limited.workflow.step(limited.principal, limited.specimen.id).run
    assert run.second_opinion["reason"] == "run_limit" and not blocked.requests and run.stage == "finalized"


def test_a_malformed_answer_is_asked_again_once(tmp_path):
    """The coordinator's ruling on round 3: a malformed answer is asked again once, as the readers'
    are, inside the step's deadline and reservation; the second answer stands."""
    rig = build_rig(tmp_path)

    class Twice(Opinion):
        def factory(self):
            self.raw = "{not json" if not self.built else None
            return super().factory()

    opinion = Twice(agreeing(tmp_path))
    with_opinion(rig, opinion)
    run = to_end(rig).run
    assert run.second_opinion["status"] == so.OBTAINED and len(opinion.requests) == 2
    assert run.reasons == [] and run.disposition == Disposition.CLEARED
    [paid] = step_paid(run)
    assert paid["usage"]["model_calls"] == 2 and paid["cost_micros"] <= so.CAP_MICROS


# ---- Codex round 4 on 489516c9 ----------------------------------------------------------------------

def test_a_field_decision_while_the_intent_is_open_abandons_it_and_leaves_no_mark_on_the_field(tmp_path, monkeypatch):
    """Codex round 4, 3: a person confirms Country while the intent is open. The endpoint abandons the
    intent there and then and finalizes the record as research left it, so the decision proceeds as on
    main: no lease, no open intent, and no derived mark on the person's field; the provider's result then
    loses its save."""
    from test_step import decide, review_client

    rig = build_rig(tmp_path)
    client = review_client(rig)
    opinion = Opinion(agreeing(tmp_path))
    with_opinion(rig, opinion)
    rig.workflow.step(rig.principal, rig.specimen.id)
    real = so.obtain
    seen = {}

    def decide_meanwhile(run, **kwargs):
        current = rig.repository.get(rig.principal.scope, rig.specimen.id).run
        country = current.fields["country"]
        seen["decided"] = decide(client, rig, "country-meanwhile", "field", target_id="country",
            after=country.model_dump(mode="json", exclude={"evidence_ids"}), evidence_ids=list(country.evidence_ids))
        return real(run, **kwargs)

    monkeypatch.setattr(so, "obtain", decide_meanwhile)
    rig.workflow.step(rig.principal, rig.specimen.id)
    decided = seen["decided"]
    assert (decided.second_opinion["status"], decided.second_opinion["reason"]) == (so.NOT_OBTAINED, "abandoned")
    assert decided.lease_until is None and decided.stage == "finalized" and decided.person_decided_fields == ["country"]
    assert not [code for code in decided.reasons if code.startswith("marked:country:") and so.own(code)]
    run = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    assert run == decided and len(opinion.requests) == 1


def test_an_unanswered_call_is_never_asked_again_for_the_same_values(tmp_path):
    """Codex round 4, 4: the worker dies in the request; after the lease, Retry or Resume puts the run
    back at the handover. The recheck finalizes it, the lost intent is abandoned, and the step is not due
    again for the same values: nothing is sent twice. A changed value makes it due again."""
    rig = build_rig(tmp_path)
    opinion = Opinion(error=WorkerDeadlineExceeded())
    with_opinion(rig, opinion)
    rig.workflow.step(rig.principal, rig.specimen.id)
    with pytest.raises(WorkerDeadlineExceeded):
        rig.workflow.step(rig.principal, rig.specimen.id)
    held = rig.repository.get(rig.principal.scope, rig.specimen.id)
    rig.clock.now = datetime.fromisoformat(held.run.lease_until) + timedelta(seconds=1)
    # What Retry or Resume does to a record that is not blocked: back to the handover (api.py, lane.queue).
    held.run.stage, held.run.disposition = "plan", None
    rig.repository.save(rig.principal, held, held.version, "resume", "resume")
    opinion.error = None
    opinion.answer = full()
    run = to_end(rig).run
    assert (run.stage, run.blocker) == ("finalized", None) and len(opinion.requests) == 1
    assert run.second_opinion["reason"] in so.UNANSWERED and run.second_opinion["asked"]
    assert not so.due(run)
    key = next(iter(run.second_opinion["asked"]))
    run.fields[key].literal = run.fields[key].parsed = run.fields[key].normalized = "Changed"
    assert so.due(run)


def test_the_ledgers_are_settled_only_after_the_result_is_saved(tmp_path, monkeypatch):
    """Codex round 4, 5: an approval abandons the intent (its whole reservation held); the late answer's
    known cost then loses its save and settles nothing, so the ledgers and the run agree on the held
    reservation. A result that is saved settles the ledgers once, after its save."""
    from test_step import decide, review_client

    from specimen_digitization.application import lane_costs

    settled = []
    real_settle = lane_costs.settle_step
    monkeypatch.setattr(lane_costs, "settle_step",
        lambda repository, principal, specimen, step, *a, **k: settled.append((step, specimen.version))
        or real_settle(repository, principal, specimen, step, *a, **k))
    rig = build_rig(tmp_path)
    client = review_client(rig)
    with_opinion(rig, Opinion(agreeing(tmp_path)))
    rig.workflow.step(rig.principal, rig.specimen.id)
    real = so.obtain

    def approve_meanwhile(run, **kwargs):
        decide(client, rig, "approve-meanwhile", "approve")
        return real(run, **kwargs)

    monkeypatch.setattr(so, "obtain", approve_meanwhile)
    rig.workflow.step(rig.principal, rig.specimen.id)
    run = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    assert [s for s, _ in settled if s == so.STEP] == []
    assert f"{so.STEP}:1" not in run.dependencies.get("ordinary_cost_settlements", {})
    [paid] = step_paid(run)
    assert (paid["cost_basis"], paid["cost_micros"]) == ("reserved", so.CAP_MICROS)
    monkeypatch.setattr(so, "obtain", real)
    other = build_rig(tmp_path / "saved")
    with_opinion(other, Opinion(agreeing(tmp_path / "again")))
    done = to_end(other)
    [(step, version)] = [(s, v) for s, v in settled if s == so.STEP]
    assert version == done.version
    [paid] = step_paid(done.run)
    assert done.run.dependencies["ordinary_cost_settlements"][f"{so.STEP}:1"] == {
        "reserved_micros": so.CAP_MICROS, "settled_micros": paid["cost_micros"]}


def test_two_external_calls_are_reserved_and_counted_since_a_retry_is_possible(tmp_path):
    """Codex round 4, 6: with one external call left the step does not run ("run_limit"); otherwise it
    counts two, as a retry-capable mandatory model step reserves."""
    rig = build_rig(tmp_path)
    opinion = Opinion(full())
    with_opinion(rig, opinion)
    pending = rig.workflow.step(rig.principal, rig.specimen.id)
    pending.run.usage.external_calls = pending.run.profile.execution.max_external_calls - 1
    rig.repository.save(rig.principal, pending, pending.version, "calls", "calls")
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert run.second_opinion["reason"] == "run_limit" and not opinion.requests
    counted = build_rig(tmp_path / "counted")
    with_opinion(counted, Opinion(full()))
    pending = counted.workflow.step(counted.principal, counted.specimen.id)
    before = pending.run.usage.external_calls
    run = counted.workflow.step(counted.principal, counted.specimen.id).run
    assert run.usage.external_calls == before + so.REQUESTS


# ---- Codex round 5 on 77f82a6e ----------------------------------------------------------------------

@pytest.mark.parametrize("room", [16, 0])
def test_when_nothing_of_the_step_can_be_saved_the_record_is_finalized_as_main_would(tmp_path, monkeypatch, room):
    """Codex round 5, 1: research's pending record sits so near the limit that not even "not obtained"
    can be stored. The step writes nothing of its own and the record is finalized exactly as research
    left it, as main would save it: no stored result, the marks not checked, the revision advanced, no
    blocker. `room` is the bytes left below the limit by main's own finalized record."""
    from specimen_digitization.application import active_graph

    rig = build_rig(tmp_path)
    opinion = Opinion(full())
    with_opinion(rig, opinion)
    pending = rig.workflow.step(rig.principal, rig.specimen.id)
    monkeypatch.setattr(active_graph, "GRAPH_THRESHOLD", 0)
    as_main = pending.model_copy(deep=True)
    so.finish(as_main.run)
    monkeypatch.setattr(active_graph, "NORMAL_GRAPH_LIMIT", graph_size(as_main) + room)
    done = rig.workflow.step(rig.principal, rig.specimen.id)
    run = done.run
    assert done.version > pending.version and (run.stage, run.blocker) == ("finalized", None)
    assert run.second_opinion is None and not opinion.requests and not step_paid(run)
    assert own(run) and all(code.endswith(":" + so.NOT_CHECKED) for code in own(run))
    # Compared with research's own saved state, not with a finish of a copy (G51 round 2).
    assert others(run) == others(pending.run) and run.disposition == as_main.run.disposition


def test_a_timed_out_call_is_not_asked_again_on_resume(tmp_path, monkeypatch):
    """Codex round 5, 2: a request that was sent and timed out is final for the values it asked about:
    Resume, with the same values and money left, asks nothing."""
    monkeypatch.setattr(so, "TIMEOUT_SECONDS", 15.5)
    monkeypatch.setattr(so, "MIN_SECONDS", 15.0)
    rig = build_rig(tmp_path)
    opinion = Opinion(full(), delay=2.0)
    with_opinion(rig, opinion)
    real = so.ask

    async def short(model, labels, text, meter, *, deadline, **kwargs):
        return await real(model, labels, text, meter, deadline=deadline - 14.0, **kwargs)

    monkeypatch.setattr(so, "ask", short)
    run = to_end(rig).run
    assert run.second_opinion["reason"] == "timeout" and run.second_opinion["asked"] and len(opinion.requests) == 1
    held = rig.repository.get(rig.principal.scope, rig.specimen.id)
    held.run.stage, held.run.disposition = "plan", None
    rig.repository.save(rig.principal, held, held.version, "resume", "resume")
    again = to_end(rig).run
    assert (again.stage, again.blocker) == ("finalized", None) and len(opinion.requests) == 1


def test_confirming_an_unchanged_field_after_an_abandoned_call_does_not_re_ask(tmp_path, monkeypatch):
    """Codex round 5, 3: the intent covers Country and Habitat among others; a person confirms Country
    unchanged, which abandons the intent. On Resume the fields it answers for now are all asked with the
    same values (Country left the set): nothing is asked again."""
    from test_step import decide, review_client

    rig = build_rig(tmp_path)
    client = review_client(rig)
    opinion = Opinion(agreeing(tmp_path))
    with_opinion(rig, opinion)
    rig.workflow.step(rig.principal, rig.specimen.id)
    real = so.obtain

    def decide_meanwhile(run, **kwargs):
        current = rig.repository.get(rig.principal.scope, rig.specimen.id).run
        country = current.fields["country"]
        decide(client, rig, "country-meanwhile", "field", target_id="country",
            after=country.model_dump(mode="json", exclude={"evidence_ids"}), evidence_ids=list(country.evidence_ids))
        return real(run, **kwargs)

    monkeypatch.setattr(so, "obtain", decide_meanwhile)
    rig.workflow.step(rig.principal, rig.specimen.id)
    monkeypatch.setattr(so, "obtain", real)
    held = rig.repository.get(rig.principal.scope, rig.specimen.id)
    assert {"country", "habitat"} <= set(held.run.second_opinion["asked"])
    held.run.stage, held.run.disposition = "plan", None
    rig.repository.save(rig.principal, held, held.version, "resume", "resume")
    again = to_end(rig).run
    assert (again.stage, again.blocker) == ("finalized", None) and len(opinion.requests) == 1
    assert not so.due(again)


# ---- Codex round 6 on 1f491ed5 ----------------------------------------------------------------------

def resume(rig, **changes):
    held = rig.repository.get(rig.principal.scope, rig.specimen.id)
    held.run.stage, held.run.disposition = "plan", None
    for key, value in changes.items():
        held.run.fields[key].literal = held.run.fields[key].parsed = held.run.fields[key].normalized = value
    rig.repository.save(rig.principal, held, held.version, f"resume:{held.version}", f"resume:{held.version}")
    return to_end(rig).run


def test_a_discarded_oversized_answer_keeps_what_it_asked_and_is_not_bought_again(tmp_path, monkeypatch):
    """Codex round 6, 2: an answer too large to store (it would breach the margin) was still sent: its
    outcome keeps the asked values and the request count, and Resume on the same values asks nothing."""
    from specimen_digitization.application import active_graph, second_opinion_step

    opinion = Opinion(BULKY)
    rig, pending = pending_rig(tmp_path, opinion, monkeypatch)
    monkeypatch.setattr(active_graph, "NORMAL_GRAPH_LIMIT", graph_size(pending) + 2 * second_opinion_step.MARGIN_BYTES)
    run = rig.workflow.step(rig.principal, rig.specimen.id).run
    assert run.second_opinion["reason"] == "result_too_large" and run.second_opinion["asked"]
    assert len(opinion.requests) == 1
    again = resume(rig)
    assert (again.stage, again.blocker) == ("finalized", None) and len(opinion.requests) == 1


def test_a_later_refusal_that_sent_nothing_keeps_the_earlier_coverage(tmp_path, monkeypatch):
    """Codex round 6, 3: a sent opinion times out; research later settles City anew, so another is due;
    a budget guard refuses it, sending nothing; a person then confirms City. With money back, Resume
    asks nothing: the timed-out call's coverage of the other fields was kept through the refusal."""
    monkeypatch.setattr(so, "TIMEOUT_SECONDS", 15.5)
    monkeypatch.setattr(so, "MIN_SECONDS", 15.0)
    rig = build_rig(tmp_path)
    opinion = Opinion(full(), delay=2.0)
    with_opinion(rig, opinion)
    real = so.ask

    async def short(model, labels, text, meter, *, deadline, **kwargs):
        return await real(model, labels, text, meter, deadline=deadline - 14.0, **kwargs)

    monkeypatch.setattr(so, "ask", short)
    first = to_end(rig).run
    asked = dict(first.second_opinion["asked"])
    assert first.second_opinion["reason"] == "timeout" and "city" in asked
    monkeypatch.setattr(so, "CAP_MICROS", 50_000_000)
    refused = resume(rig, city="Evanston")
    assert refused.second_opinion["reason"] == "budget" and refused.second_opinion["asked"] == asked
    assert len(opinion.requests) == 1
    monkeypatch.setattr(so, "CAP_MICROS", 120_000)
    held = rig.repository.get(rig.principal.scope, rig.specimen.id)
    held.run.person_decided_fields = ["city"]
    rig.repository.save(rig.principal, held, held.version, "person-city", "person-city")
    again = resume(rig)
    assert (again.stage, again.blocker) == ("finalized", None) and len(opinion.requests) == 1


# ---- the G51 sign-off review on 84cedd73 ------------------------------------------------------------

def swamp(rig, client, key="habitat-swamp"):
    """The reviewer's decision: habitat saved as a person's value with the app's own payload."""
    from test_step import decide

    current = rig.repository.get(rig.principal.scope, rig.specimen.id).run
    habitat = current.fields["habitat"]
    after = {"literal": habitat.literal, "parsed": "Person's swamp", "normalized": "Person's swamp",
             "state": "supported", "reason": habitat.reason}
    return decide(client, rig, key, "field", target_id="habitat", after=after, evidence_ids=list(habitat.evidence_ids))


def outcome(rig):
    from specimen_digitization.application.api import summary

    stored = rig.repository.get(rig.principal.scope, rig.specimen.id)
    run = stored.run
    return ([code for code in run.reasons if not so.own(code)], run.disposition,
        summary(stored, "reviewer")["cleared_by"], [code for code in run.reasons if so.own(code) and ":habitat:" in code])


def main_outcome(folder, act):
    """The same act on main: no second opinion, no derived marks."""
    from test_step import review_client

    twin = build_rig(folder)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(so, "derived", lambda run, readings=(): [])
        mounted(twin, Scripted())
        to_end(twin)
        act(twin, review_client(twin))
        return outcome(twin)


def test_an_approval_clears_a_record_the_opinion_disputed_as_main_clears_one_it_marked(tmp_path):
    """G51, 1(a): the opinion differs on habitat; a person approves through the API: cleared, approved,
    cleared by a person, exactly as main treats its own marks once a person approved."""
    from test_step import decide, review_client

    from specimen_digitization.application.api import summary

    rig = build_rig(tmp_path)
    with_opinion(rig, Opinion(agreeing(tmp_path, habitat={"value": "Synthetic meadow", "evidence": "L1: meadow"})))
    assert own(to_end(rig).run, so.DIFFERS)
    approved = decide(review_client(rig), rig, "approve", "approve")
    assert (approved.disposition, approved.human_approved, approved.reasons) == (Disposition.CLEARED, True, [])
    assert summary(rig.repository.get(rig.principal.scope, rig.specimen.id), "reviewer")["cleared_by"] == "person"
    assert not so.due(approved) and so.reasons(approved) == []


@pytest.mark.parametrize("action", ["resume", "retry"])
def test_a_record_main_cleared_and_a_person_approved_stays_cleared_on_resume_and_retry(tmp_path, monkeypatch, action):
    """G51, 1(b): a record written as main writes it (no second opinion), approved and cleared; then the
    head's production runner is mounted and the record resumed or retried: it stays cleared, no mark,
    and the step is not attempted."""
    from test_step import ORG, decide, review_client

    from specimen_digitization.application import api as app_api
    from specimen_digitization.application.domain import now

    rig = build_rig(tmp_path)
    client = review_client(rig)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(so, "derived", lambda run, readings=(): [])
        mounted(rig, Scripted())
        to_end(rig)
        approved = decide(client, rig, "approve", "approve")
    assert (approved.disposition, approved.human_approved) == (Disposition.CLEARED, True)

    def queue(specimen, registry, actor):
        specimen.run.stage, specimen.run.queued_at = "pending", now()

    monkeypatch.setattr(app_api, "queue", queue)
    rig.workflow.second_opinion = so.production_step()
    current = rig.repository.get(rig.principal.scope, rig.specimen.id)
    response = client.post(f"/v1/organizations/{ORG}/runs/{current.run.id}/actions",
        headers={"Authorization": "Bearer reviewer", "Idempotency-Key": action},
        json={"expected_revision": current.version, "action": action, "reason": "Again."})
    assert response.status_code == 200, response.text
    run = to_end(rig).run
    assert (run.stage, run.disposition, run.blocker) == ("finalized", Disposition.CLEARED, None)
    assert not own(run) and not step_paid(run) and so.STEP not in run.attempts


@pytest.mark.parametrize("window", ["before_the_intent", "while_the_intent_is_open", "after_the_step"])
def test_a_persons_field_decision_is_finalized_as_main_finalizes_it(tmp_path, monkeypatch, window):
    """G51, 2: a person saves habitat "Person's swamp" with the app's payload after research's save and
    before the step's intent, while the intent is open, or after the step finished; the step obtains an
    agreeing opinion. In each the reasons, disposition and cleared_by equal main's for that decision on
    its finalized record, no mark lands on the person's field, and nothing clears without approval."""
    from test_step import review_client

    expected = main_outcome(tmp_path / "main", lambda twin, client: swamp(twin, client))
    rig = build_rig(tmp_path)
    client = review_client(rig)
    with_opinion(rig, Opinion(agreeing(tmp_path)))
    if window == "before_the_intent":
        pending = rig.workflow.step(rig.principal, rig.specimen.id)
        assert pending.run.stage == so.STEP
        swamp(rig, client)
        to_end(rig)
    elif window == "while_the_intent_is_open":
        rig.workflow.step(rig.principal, rig.specimen.id)
        real = so.obtain

        def meanwhile(run, **kwargs):
            swamp(rig, client)
            return real(run, **kwargs)

        monkeypatch.setattr(so, "obtain", meanwhile)
        rig.workflow.step(rig.principal, rig.specimen.id)
        monkeypatch.setattr(so, "obtain", real)
        to_end(rig)
    else:
        to_end(rig)
        swamp(rig, client)
    got = outcome(rig)
    assert got[:3] == expected[:3] and got[3] == []
    assert got[1] == Disposition.REVIEW and "human_approval_required" in got[0]


# ---- the G51 review, round 2 (d016678b): research's retained reassessment reasons ----------------------

def others(run):
    return [code for code in run.reasons if not so.own(code)]


class Current:
    """An opinion that answers each settled value as the stored record shows it (agrees), or with
    "Elsewhere" for each (differs)."""

    def __init__(self, rig, *, differ=False):
        self.rig, self.differ, self.requests = rig, differ, 0

    def factory(self):
        async def respond(messages, info: AgentInfo):
            self.requests += 1
            run = self.rig.repository.get(self.rig.principal.scope, self.rig.specimen.id).run
            answer = {key: {"value": ("Elsewhere" if self.differ else so.shown(run.fields[key]))
                if so._settled(run.fields.get(key)) else None, "evidence": "L1"} for key in so.FIELDS}
            return ModelResponse(parts=[ToolCallPart(so.TOOL_NAME, json.dumps(answer))],
                usage=RequestUsage(input_tokens=5_000, output_tokens=700))

        return FunctionModel(respond)


def reassessed_unconfirmed(tmp_path, monkeypatch, runner):
    """The repository's unconfirmed-reassessment fixture (test_location_reassessment: the gazetteer down):
    research's own saved state, with `runner` as the second opinion."""
    from test_location_reassessment import execute, old_location_run

    rig = old_location_run(tmp_path)
    rig.workflow.second_opinion = runner(rig) if runner else None
    _, done, *_ = execute(rig, monkeypatch, outage=True)
    if runner:
        rig.workflow.second_opinion = runner(rig)
    assert any(code.startswith(so.REASSESSMENT_UNCONFIRMED + ":") for code in done.run.reasons)
    return rig, done


@pytest.mark.parametrize("how", ["agrees", "differs", "not_obtained", "size_fallback"])
def test_the_step_keeps_the_reassessment_reasons_research_left(tmp_path, monkeypatch, how):
    """G51 round 2, (a): after the step finishes, however it finishes, the run's reasons other than the
    second opinion's equal what research left on its own saved run, the retained
    location_reassessment_unconfirmed reasons included, and the record is for review."""
    from specimen_digitization.application import active_graph

    def runner(rig):
        if how == "not_obtained":
            return so.SecondOpinionStep(model_factory=lambda: Opinion(error=RuntimeError("down")).factory())
        return so.SecondOpinionStep(model_factory=Current(rig, differ=how == "differs").factory)

    rig, research = reassessed_unconfirmed(tmp_path, monkeypatch, runner)
    if how == "size_fallback":
        monkeypatch.setattr(active_graph, "GRAPH_THRESHOLD", 0)
        monkeypatch.setattr(active_graph, "NORMAL_GRAPH_LIMIT", graph_size(research) + 64)
    final = to_end(rig).run
    assert (final.stage, final.blocker) == ("finalized", None) and final.disposition == Disposition.REVIEW
    assert others(final) == others(research.run)


def test_a_resume_at_the_steps_stage_keeps_them_and_a_decision_afterwards_is_mains(tmp_path, monkeypatch):
    """G51 round 2, (b) and (c): the reassessment's research left the record waiting for the step; a
    Resume there keeps the retained reasons; a person's decision afterwards drops them as on main (the
    same refinalize)."""
    from test_step import decide, review_client

    rig, research = reassessed_unconfirmed(tmp_path, monkeypatch, lambda rig: so.SecondOpinionStep(
        model_factory=Current(rig).factory))
    if research.run.stage == so.STEP:
        held = rig.repository.get(rig.principal.scope, rig.specimen.id)
        held.run.stage, held.run.disposition = "plan", None
        rig.repository.save(rig.principal, held, held.version, "resume", "resume")
    resumed = to_end(rig).run
    retained = [code for code in research.run.reasons if code.startswith(so.REASSESSMENT_UNCONFIRMED + ":")]
    assert retained and all(code in resumed.reasons for code in retained)
    assert resumed.disposition == Disposition.REVIEW
    habitat = resumed.fields["habitat"]
    decided = decide(review_client(rig), rig, "habitat-after", "field", target_id="habitat",
        after=habitat.model_dump(mode="json", exclude={"evidence_ids"}), evidence_ids=list(habitat.evidence_ids))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(so, "derived", lambda run, readings=(): [])
        mainlike = rig.repository.get(rig.principal.scope, rig.specimen.id).run.model_copy(deep=True)
        from specimen_digitization.field_research.step import refinalize

        mainlike.reasons = [code for code in resumed.reasons if not so.own(code)]
        refinalize(mainlike, decided=True)
    assert others(decided) == others(mainlike)
