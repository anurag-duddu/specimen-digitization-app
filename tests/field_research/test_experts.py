"""One expert per field (FIELD_RESEARCH.md steps 3 to 5), driven by scripted models.

Each test scripts the model with a pydantic_ai FunctionModel and answers lookups
from a fake SourceTools, so nothing leaves the process and nothing is paid for.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic_ai import ModelRetry
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.instrumented import InstrumentationSettings

from specimen_digitization.application.domain import Evidence, FieldValue, LookupStatus, ValueState
from specimen_digitization.field_research import experts
from specimen_digitization.field_research.budget import CostMeter
from specimen_digitization.field_research.contracts import (
    FIELD_TOOLS,
    Candidate,
    FieldAnswer,
    FieldTask,
    Reading,
    SourceAnswer,
    SourceCandidate,
)
from specimen_digitization.field_research.experts import EXHAUSTED, INPUT_PREFIX, make_resolver

PILOT_DATES = {
    "version": "date-rules-v1", "two_digit_year_century": 1900, "roman_numeral_months": True,
}
READINGS = (
    Reading("1A", "region-1", "obs-1a", "decided_transcript",
            "Epipsocus sp. 1\nP.I. Mindanao, Davao\n4-5-48 coll. F. G. Werner"),
    Reading("1B", "region-1", "obs-1b", "raw_reading",
            "Epipsocus sp. 1\nP.I. Mindanao Davao\n4-5-48 coll. F.G. Werner"),
    Reading("2A", "region-2", "obs-2a", "raw_reading", "alt. 1500 ft\nca. 1200 m"),
)
CONTEXT = {
    "country": FieldValue(state=ValueState.SUPPORTED, literal="P.I."),
    "city": FieldValue(state=ValueState.AMBIGUOUS,
                       verbatim_by_observation={"obs-1a": "Davao", "obs-1b": "Davao"}),
    "habitat": FieldValue(),
}
GBIF_EVIDENCE = Evidence(id="ev-gbif-1", kind="lookup", source="gbif", locator="gbif:1",
                         excerpt="Epipsocus Hagen, 1866")
GBIF_SUCCESS = SourceAnswer(
    source_id="gbif",
    query="Epipsocus",
    status=LookupStatus.SUCCESS,
    candidates=(SourceCandidate("Epipsocus Hagen, 1866", "gbif:1234", "GENUS", "Psocodea"),),
    evidence=GBIF_EVIDENCE,
    note="GBIF: exact accepted match at genus rank",
    taxonomy_lookup={"lookup": "gbif-1"},
)


def task(key: str, *, current: FieldValue | None = None, candidates=()) -> FieldTask:
    return FieldTask(key=key, mandatory=True, current=current or FieldValue(),
                     candidates=tuple(candidates), tools=FIELD_TOOLS[key])


def meter(cap: int = 1_000_000) -> CostMeter:
    return CostMeter(cap, input_micros_per_million=200_000, output_micros_per_million=600_000)


class FakeTools:
    """A record's approved sources, answering from a table."""

    def __init__(self, answers=None, sources=("gbif", "geolocate", "tgn", "wikidata", "nga")):
        self.answers = dict(answers or {})
        self.sources = tuple(sources)
        self.calls: list[tuple[str, str, str]] = []

    async def lookup(self, source_id: str, query: str, *, field_key: str) -> SourceAnswer:
        self.calls.append((source_id, query, field_key))
        answer = self.answers[(source_id, query)]
        if isinstance(answer, BaseException):
            raise answer
        return answer


Step = Callable[[list[ModelMessage], AgentInfo], ModelResponse]


class Script:
    """A model that plays its steps in order and records what each request saw."""

    def __init__(self, *steps: Step | dict) -> None:
        self.steps = list(steps)
        self.seen: list[tuple[list[ModelMessage], AgentInfo]] = []

    def __call__(self, messages, info):
        self.seen.append((list(messages), info))
        step = self.steps.pop(0)
        return step(messages, info) if callable(step) else final(**step)(messages, info)

    def model(self):
        return FunctionModel(self)


def final(**answer) -> Step:
    answer.setdefault("explanation", "Scripted answer.")
    return lambda messages, info: ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, answer)])


def call(tool: str, **args) -> Step:
    return lambda messages, info: ModelResponse(parts=[ToolCallPart(tool, args)])


def retries(messages: list[ModelMessage]) -> list[str]:
    return [part.model_response() for m in messages if isinstance(m, ModelRequest)
            for part in m.parts if isinstance(part, RetryPromptPart)]


def tool_returns(messages: list[ModelMessage]) -> list[object]:
    return [part.content for m in messages if isinstance(m, ModelRequest)
            for part in m.parts if isinstance(part, ToolReturnPart)]


def resolve(script: Script, field: FieldTask, tools=None, *, cost: CostMeter | None = None, **kw):
    resolver = make_resolver(model_factory=script.model, meter=cost or meter(),
                             date_rules=PILOT_DATES, **kw)
    return asyncio.run(resolver(field, READINGS, CONTEXT, tools=tools or FakeTools()))


GBIF_ANSWER = dict(
    outcome="resolved", literal="Epipsocus sp. 1", reading_names=["1A", "1b"],
    value="Epipsocus Hagen, 1866", authority_id="gbif:1234", source_evidence_ids=["ev-gbif-1"],
    explanation="GBIF matches the genus Epipsocus exactly; sp. 1 is genus-level (G25).",
)


def test_a_taxon_resolves_on_a_cited_gbif_success():
    tools = FakeTools({("gbif", "Epipsocus"): GBIF_SUCCESS})
    script = Script(call("lookup", source="gbif", query="Epipsocus"), GBIF_ANSWER)
    cost = meter()

    outcome = resolve(script, task("taxon"), tools, cost=cost)

    assert outcome.failure is None
    assert outcome.answer.outcome == "resolved"
    assert outcome.answer.reading_names == ["1A", "1B"]  # named as the readings name themselves
    assert outcome.answer.value == "Epipsocus Hagen, 1866"
    assert outcome.evidence == [GBIF_EVIDENCE]
    assert outcome.lookups == [{"lookup": "gbif-1"}]
    assert tools.calls == [("gbif", "Epipsocus", "taxon")]
    assert outcome.model_calls == 2 and outcome.cost_micros == cost.spent_micros > 0
    # The model saw the source's answer compactly, with the id to cite.
    shown = tool_returns(script.seen[1][0])[0]
    assert shown["evidence_id"] == "ev-gbif-1" and shown["status"] == "success"
    assert shown["candidates"] == [{"name": "Epipsocus Hagen, 1866", "authority_id": "gbif:1234",
                                    "kind": "GENUS", "detail": "Psocodea"}]


def test_the_expert_gets_its_brief_its_tools_and_every_reading_as_evidence():
    script = Script(dict(outcome="sources_cannot_resolve", explanation="No lookup made."))

    resolve(script, task("taxon", current=FieldValue(
        state=ValueState.AMBIGUOUS, verbatim_by_observation={"obs-1a": "Epipsocus sp. 1"}),
        candidates=[Candidate("1A", "Epipsocus sp. 1", "Epipsocus sp. 1", "ev-1")]))

    messages, info = script.seen[0]
    assert "You are the expert for ONE field" in info.instructions
    assert "Field: Taxon (taxon)" in info.instructions
    assert "Field: Country (country)" not in info.instructions
    assert [tool.name for tool in info.function_tools] == ["lookup"]
    lookup = info.function_tools[0]
    assert "gbif: a scientific name" in lookup.description and "geolocate" not in lookup.description
    assert lookup.parameters_json_schema["properties"]["source"]["enum"] == ["gbif"]
    assert info.model_settings["max_tokens"] == 2048 and info.model_settings["temperature"] == 0
    [request] = messages
    [prompt] = [p.content for p in request.parts if isinstance(p, UserPromptPart)]
    assert prompt.startswith(INPUT_PREFIX)
    document = json.loads(prompt.removeprefix(INPUT_PREFIX))
    assert document["field"] == {"key": "taxon", "label": "Taxon"}
    assert [r["name"] for r in document["readings"]] == ["1A", "1B", "2A"]
    assert document["readings"][0]["text"] == READINGS[0].text
    assert document["organiser_value"]["verbatim_by_observation"] == {"1A": "Epipsocus sp. 1"}
    assert document["organiser_candidates"] == [
        {"reading": "1A", "quote": "Epipsocus sp. 1", "literal": "Epipsocus sp. 1"}]
    assert document["other_fields"] == {"country": "P.I.", "city": ["Davao"]}


@pytest.mark.parametrize(
    ("key", "tools"),
    [("date_visited_from", ["parse_date"]), ("elevation_from_ft", ["parse_elevation"]),
     ("fmnh_ins_number", ["check_catalog_number"]), ("collectors", [])],
)
def test_each_field_gets_only_its_own_tools(key, tools):
    script = Script(dict(outcome="label_lacks_value"))

    resolve(script, task(key))

    assert [tool.name for tool in script.seen[0][1].function_tools] == tools


def test_every_call_starts_with_fresh_context():
    script = Script(dict(outcome="label_lacks_value"), dict(outcome="label_lacks_value"))
    resolver = make_resolver(model_factory=script.model, meter=meter())

    async def twice():
        await resolver(task("habitat"), READINGS, CONTEXT, tools=FakeTools())
        await resolver(task("habitat"), READINGS, CONTEXT, tools=FakeTools())

    asyncio.run(twice())

    assert [len(messages) for messages, _ in script.seen] == [1, 1]


def test_a_literal_not_in_the_reading_is_sent_back_then_accepted_when_corrected():
    script = Script(
        dict(outcome="resolved", literal="F.G. Werner", reading_names=["1A"]),
        dict(outcome="resolved", literal="F. G. Werner", reading_names=["1A"]),
    )

    outcome = resolve(script, task("collectors"))

    assert outcome.failure is None
    assert (outcome.answer.literal, outcome.answer.reading_names) == ("F. G. Werner", ["1A"])
    [message] = retries(script.seen[1][0])
    assert "does not contain the literal 'F.G. Werner' exactly" in message
    assert outcome.model_calls == 2


def test_a_value_from_no_received_candidate_is_refused():
    tools = FakeTools({("gbif", "Epipsocus"): GBIF_SUCCESS})
    invented = {**GBIF_ANSWER, "value": "Epipsocus Banks, 1920", "authority_id": None}
    script = Script(call("lookup", source="gbif", query="Epipsocus"), invented, GBIF_ANSWER)

    outcome = resolve(script, task("taxon"), tools)

    assert outcome.answer.value == "Epipsocus Hagen, 1866"
    [message] = retries(script.seen[2][0])
    assert "'Epipsocus Banks, 1920' differs from the literal" in message


def test_an_expert_that_keeps_inventing_a_value_fails_as_a_model_error():
    tools = FakeTools({("gbif", "Epipsocus"): GBIF_SUCCESS})
    invented = {**GBIF_ANSWER, "value": "Epipsocus Banks, 1920", "authority_id": None}
    script = Script(call("lookup", source="gbif", query="Epipsocus"), invented, invented, invented)

    outcome = resolve(script, task("taxon"), tools)

    assert (outcome.answer, outcome.failure) == (None, "model_error")
    assert outcome.evidence == [GBIF_EVIDENCE]  # what it gathered is still reported


def test_label_lacks_value_carries_no_value():
    script = Script(
        dict(outcome="label_lacks_value", literal="Davao"),
        dict(outcome="label_lacks_value", explanation="No reading names a county."),
    )

    outcome = resolve(script, task("county"))

    assert outcome.failure is None and outcome.answer.outcome == "label_lacks_value"
    assert outcome.answer.literal is None
    assert "leave literal, value and authority_id empty" in retries(script.seen[1][0])[0]


def test_several_possibilities_from_a_date_check():
    script = Script(
        call("parse_date", literal="4-5-48"),
        dict(outcome="several_possibilities", options=["1948-04-05", "1948-06-04"]),
        dict(outcome="several_possibilities", options=["1948-04-05", "1948-05-04"],
             literal="4-5-48", reading_names=["1A", "1B"]),
    )

    outcome = resolve(script, task("date_visited_from"))

    assert outcome.failure is None
    assert outcome.answer.options == ["1948-04-05", "1948-05-04"]
    assert tool_returns(script.seen[1][0])[0]["status"] == "ambiguous"
    assert "'1948-06-04' is not text a reading contains" in retries(script.seen[2][0])[0]


def test_a_resolved_date_takes_its_value_from_the_check():
    script = Script(
        call("parse_date", literal="4-5-48"),
        dict(outcome="resolved", literal="4-5-48", reading_names=["1A"], value="1948-04-05",
             explanation="Another label writes the month by name."),
    )

    outcome = resolve(script, task("date_visited_from"))

    assert outcome.failure is None and outcome.answer.value == "1948-04-05"


@pytest.mark.parametrize("failure", [
    SourceAnswer("gbif", "Epipsocus", LookupStatus.TIMEOUT, (), None, "GBIF timed out"),
    RuntimeError("socket closed"),
])
def test_a_source_outage_leaves_the_field_for_retry(failure):
    tools = FakeTools({("gbif", "Epipsocus"): failure})
    script = Script(
        call("lookup", source="gbif", query="Epipsocus"),
        dict(outcome="sources_cannot_resolve", explanation="GBIF did not answer."),
    )

    outcome = resolve(script, task("taxon"), tools)

    assert outcome.failure == "source_unavailable"
    assert outcome.answer.outcome == "sources_cannot_resolve"  # kept for the retry
    assert tool_returns(script.seen[1][0])[0]["status"] in {"timeout", "provider_error"}


def test_a_query_that_later_succeeds_clears_its_outage():
    tools = FakeTools({("gbif", "Epipsocus"): GBIF_SUCCESS})
    script = Script(
        call("lookup", source="gbif", query="Epipsocus"),
        dict(outcome="sources_cannot_resolve", explanation="GBIF answered; not settled."),
    )
    flaky = iter([SourceAnswer("gbif", "Epipsocus", LookupStatus.RATE_LIMITED, (), None)])

    async def lookup(source_id, query, *, field_key):
        return next(flaky, GBIF_SUCCESS)

    tools.lookup = lookup  # type: ignore[method-assign]
    script.steps.insert(1, call("lookup", source="gbif", query="Epipsocus"))

    outcome = resolve(script, task("taxon"), tools)

    assert outcome.failure is None and outcome.answer.outcome == "sources_cannot_resolve"


def test_an_unapproved_source_is_refused_without_a_call():
    tools = FakeTools(sources=("geolocate",))
    script = Script(call("lookup", source="tgn", query="Davao"),
                    dict(outcome="sources_cannot_resolve", explanation="No source settled it."))

    outcome = resolve(script, task("city"), tools)

    assert tools.calls == []
    refused = tool_returns(script.seen[1][0])[0]
    assert refused["status"] == "policy_blocked" and "geolocate" in refused["note"]
    assert outcome.failure is None  # a refusal is not an outage


def test_a_budget_that_cannot_fit_a_call_fails_the_field():
    script = Script(dict(outcome="label_lacks_value"))

    outcome = resolve(script, task("habitat"), cost=meter(cap=100))

    assert outcome.failure == "budget_exhausted" and outcome.answer is None
    assert script.seen == [] and outcome.model_calls == 0


def test_the_field_deadline_is_a_timeout():
    cost = meter()

    async def slow(messages, info):
        await asyncio.sleep(5)

    resolver = make_resolver(model_factory=lambda: FunctionModel(slow), meter=cost,
                             field_timeout_seconds=0.05)
    outcome = asyncio.run(resolver(task("habitat"), READINGS, CONTEXT, tools=FakeTools()))

    assert outcome.failure == "timeout" and outcome.answer is None
    # The cancelled request keeps its worst case: it may have been billed.
    assert cost.outstanding_micros == 0 and cost.spent_micros == outcome.cost_micros > 0


def test_running_out_of_requests_is_sources_cannot_resolve():
    tools = FakeTools({("gbif", q): SourceAnswer("gbif", q, LookupStatus.NO_MATCH, (), None)
                       for q in ("Epipsocus", "Epipsocvs")})
    script = Script(call("lookup", source="gbif", query="Epipsocus"),
                    call("lookup", source="gbif", query="Epipsocvs"))

    outcome = resolve(script, task("taxon"), tools, request_limit=2)

    assert outcome.failure is None
    assert outcome.answer == FieldAnswer(outcome="sources_cannot_resolve", explanation=EXHAUSTED)
    assert outcome.model_calls == 2


def test_a_provider_error_is_a_model_error_logged_by_class_only(caplog):
    def broken(messages, info):
        raise ModelHTTPError(503, "deepseek", body="label text Epipsocus sp. 1")

    script = Script(broken)
    with caplog.at_level(logging.WARNING, logger="specimen_digitization.field_research.experts"):
        outcome = resolve(script, task("taxon"))

    assert outcome.failure == "model_error" and outcome.answer is None
    assert "ModelHTTPError" in caplog.text and "Epipsocus" not in caplog.text


def test_logfire_shows_each_expert_as_its_own_agent(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(experts, "agent_instrumentation", lambda: InstrumentationSettings(
        tracer_provider=provider, include_content=False, version=5))
    script = Script(dict(outcome="label_lacks_value"), dict(outcome="label_lacks_value"))
    resolver = make_resolver(model_factory=script.model, meter=meter())

    async def both():
        await resolver(task("taxon"), READINGS, CONTEXT, tools=FakeTools())
        await resolver(task("precise_location"), READINGS, CONTEXT, tools=FakeTools())

    asyncio.run(both())

    agents = {span.attributes["gen_ai.agent.name"]: span for span in exporter.get_finished_spans()
              if span.attributes and "gen_ai.agent.name" in span.attributes}
    assert {"field_taxon", "field_precise_location"} <= set(agents)
    assert agents["field_taxon"].attributes["gen_ai.agent.description"] == (
        "Expert for Taxon. Settles it from the label readings and its approved sources.")


def test_every_field_has_a_brief():
    from specimen_digitization.field_research.prompts import FIELD_LABELS, instructions

    assert set(FIELD_LABELS) == set(FIELD_TOOLS)
    for key, label in FIELD_LABELS.items():
        text = instructions(key)
        assert f"Field: {label} ({key})" in text
        assert text.isascii()
        brief = text.split(f"Field: {label} ({key})", 1)[1]
        assert len(brief.splitlines()) <= 25


# The checks on an answer, one rule at a time.

def expert(key: str, answers=()) -> experts._Expert:
    tools = FakeTools()
    made = experts._Expert(task(key), READINGS, tools, PILOT_DATES)
    for answer in answers:
        made.calls.append(experts._Call(answer.source_id, answer.query, answer.status, answer))
    return made


def answer(**fields) -> FieldAnswer:
    fields.setdefault("explanation", "Because.")
    return FieldAnswer(**fields)


@pytest.mark.parametrize(("key", "given", "says"), [
    ("identified_by_irn", dict(outcome="resolved"), "can never be resolved"),
    ("identified_by_irn", dict(outcome="sources_cannot_resolve", literal="F. G. Werner"),
     "Leave literal, value and authority_id empty"),
    ("precise_location", dict(outcome="resolved", literal="Mindanao, Davao", reading_names=["1A"],
                              authority_id="gbif:1234", source_evidence_ids=["ev-gbif-1"]),
     "verbatim locality text"),
    ("precise_location", dict(outcome="resolved", literal="Mindanao, Davao", reading_names=["1A"],
                              value="Davao City"), "verbatim locality text"),
    ("taxon", dict(outcome="resolved", literal="Epipsocus sp. 1", reading_names=["1A"]),
     "GBIF answer with status success"),
    ("elevation_from_m", dict(outcome="resolved", literal="1500", reading_names=["2A"]),
     "elevation_unit_conflict"),
    ("collectors", dict(outcome="resolved", literal="F. G. Werner", reading_names=["3A"]),
     "no reading named '3A'"),
    ("collectors", dict(outcome="resolved", literal="F. G. Werner", reading_names=[]),
     "reading_names"),
    ("collectors", dict(outcome="sources_cannot_resolve", source_evidence_ids=["ev-made-up"]),
     "'ev-made-up' is not the evidence_id"),
    ("collectors", dict(outcome="sources_cannot_resolve", explanation="x" * 601), "600"),
    ("collectors", dict(outcome="sources_cannot_resolve", explanation="  "), "explanation"),
    ("collectors", dict(outcome="several_possibilities", options=["F. G. Werner"]), "two"),
    ("taxon", dict(outcome="resolved", literal="Epipsocus sp. 1", reading_names=["1A"],
                   authority_id="gbif:9999", source_evidence_ids=["ev-gbif-1"]), "authority_id"),
])
def test_answers_that_break_a_rule_are_sent_back(key, given, says):
    made = expert(key, [GBIF_SUCCESS])

    with pytest.raises(ModelRetry, match=says.replace("(", r"\(")):
        made.validate(answer(**given))


def test_a_resolved_elevation_in_its_own_unit_is_accepted():
    made = expert("elevation_from_ft")

    accepted = made.validate(answer(outcome="resolved", literal="1500", reading_names=["2a"]))

    assert accepted.reading_names == ["2A"]
