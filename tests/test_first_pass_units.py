"""Work package 1.2: the first pass v2, reading units, behind a switch (docs/execution/units/PLAN.md).

FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md sections 2 and 3: the first pass cuts each label's text
into units at logical breaks, judges the image at each unit and settles nothing. A run records the
path it starts on (SPECIMEN_FIRST_PASS_UNITS, off by default) and keeps it; on the old path nothing
changes. Units come from the model's answer, which code checks (tiling, range) and sends back once
with the failed check named; from the alignment for a label with one reading, one given up on, or
a call that stopped at its caps. The units cross the model child to the parent and are stored on
the run.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from specimen_digitization.application import first_pass as first_pass_module
from specimen_digitization.application import model_runtime
from specimen_digitization.application import workflow as workflow_module
from specimen_digitization.application.domain import (
    LookupStatus,
    Observation,
    Profile,
    Run,
)
from specimen_digitization.application.first_pass import (
    CAP_RATIONALE,
    OLD,
    SETTING,
    UNITS,
    UNITS_RATIONALE,
    UnitsOutput,
    alignment_units,
    build_units_request,
    first_pass_path,
    reading_segments,
    units_from_output,
    units_output_problems,
)
from specimen_digitization.application.production import ProductionAdapters
from specimen_digitization.application.reading_units import (
    NOT_VISIBLE,
    UNCERTAIN,
    ReadingUnit,
    ReadingUnits,
    UnitText,
    problems,
    range_spans,
)
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.workflow import OperationalBlock, store_reading_units
from specimen_digitization.prompts import PromptName, ResolvedPrompt

from test_first_pass import ASSET, REGION, ROUTE, reading

# The last lines of pilot label e98a924c-L2 as three readers wrote them (the design's section 3).
PILOT = (
    "6-Sept-1946, Elev.6400\nH. Hoogstraal leg.\nSp.30 ♀",
    "6-Sept-1946, Elev.6400'\nH. Hoogstraal leg.\nSp.30 ♀\nP-95-81-16",
    "6-Sept-1946, Elev.6400\nH. Hoogstraal leg.\nSp.30 ♂",
)
ROUTES = ("handwriting-qwen", "handwriting-muse", "handwriting-nemotron")
UNITS_PROMPT = ResolvedPrompt(
    name=PromptName.FIRST_PASS_UNITS,
    text="Cut the label into reading units.",
    requested_label="test",
    served_label=None,
    version=None,
    resolution_reason="fixture",
)
DEPENDENCIES = {
    "routes": {ROUTE.route_id: {"model_id": ROUTE.model_id, "provider": ROUTE.provider}},
    "prompts": {UNITS_PROMPT.name.value: UNITS_PROMPT.model_dump(mode="json")},
}
# A valid answer for PILOT's eight segments: what the image shows, what each unit means.
ANSWER = {
    "units": [
        {"first": 1, "image": "A", "means": "1946-09-06", "fields": ["date_visited_from"]},
        {"first": 2, "last": 2, "image": "uncertain", "means": "elevation 6400",
         "fields": ["elevation_from_ft", "elevation_from_m"], "note": "B alone saw a foot mark."},
        {"first": 3, "last": 4, "image": "A", "fields": ["collectors"]},
        {"first": 5, "image": "A", "means": "collected by", "fields": ["collectors"]},
        {"first": 6, "last": 7, "image": "B"},
        {"first": 8, "image": "not visible"},
    ]
}


def pilot_readings(count: int = 3) -> list[Observation]:
    return [reading(route, text) for route, text in zip(ROUTES[:count], PILOT[:count])]


def texts_of(readings) -> dict[str, str]:
    return {r.id: r.literal_text for r in readings}


def output(**changes) -> UnitsOutput:
    return UnitsOutput.model_validate({**ANSWER, **changes})


# ------------------------------------------------------------------------------ the switch


@pytest.mark.parametrize("environ,path", [({}, OLD), ({SETTING: ""}, OLD), ({SETTING: "off"}, OLD),
                                          ({SETTING: "on"}, UNITS)])
def test_the_switch_is_off_unless_it_says_on(environ, path):
    assert first_pass_path(environ) == path


@pytest.mark.parametrize("value", ["true", "ON", "units", "secret-value"])
def test_a_mistyped_switch_raises_naming_the_setting_never_its_value(value):
    with pytest.raises(ValueError) as error:
        first_pass_path({SETTING: value})
    assert SETTING in str(error.value) and value not in str(error.value)


def test_a_run_on_the_old_path_stores_no_path_and_one_on_the_units_path_does():
    assert "first_pass_path" not in Run().model_dump(mode="json")
    assert Run(first_pass_path="units").model_dump(mode="json")["first_pass_path"] == "units"
    with pytest.raises(ValidationError):
        Run(first_pass_path="on")


def test_the_units_prompt_is_pinned_on_the_units_path_and_only_there(tmp_path):
    adapters = ProductionAdapters(LocalBlobs(tmp_path))
    old = adapters.pin_dependencies(Run(profile=Profile(first_pass_route="first-pass-glm")))
    units = adapters.pin_dependencies(
        Run(profile=Profile(first_pass_route="first-pass-glm"), first_pass_path="units")
    )

    assert PromptName.FIRST_PASS_UNITS.value not in old["prompts"]
    assert set(old["prompts"]) == {name.value for name in PromptName} - {"first-pass-units"}
    pinned = ResolvedPrompt.model_validate(units["prompts"]["first-pass-units"])
    # The prompt carries the ontology's first-pass text, so the run pins the version it read.
    from specimen_digitization import ontology

    assert ontology.render(brief=True) in pinned.text
    assert "Specimen ontology, version 1.0." in pinned.text
    assert {k: v for k, v in units["prompts"].items() if k != "first-pass-units"} == old["prompts"]


# --------------------------------------------------------------------------- the range grammar


@pytest.mark.parametrize("text,ranges", [
    ("6400-7000 ft.", ["6400-7000"]),
    ("Elev. 6400 - 7000 ft.", ["6400 - 7000"]),
    ("6400–7000", ["6400–7000"]),
    ("1200 to 1500 m", ["1200 to 1500"]),
    ("3 bis 5 m", ["3 bis 5"]),
    ("3 au 5", ["3 au 5"]),
    ("3 a 5", ["3 a 5"]),
    ("-20 to -10", ["-20 to -10"]),
    ("12-15.VII.1968", ["12-15.VII.1968"]),
    ("12.VII-15.VIII.1968", ["12.VII-15.VIII.1968"]),
    ("10-6-78-1a", ["10-6-78"]),
    # A sign counts only before a digit at the start of a token: two values, no joiner.
    ("6400 -7000", []),
    # A letter-digit code, a line-end hyphen inside a word, a date written with a month's name.
    ("1a2", []),
    ("B12-14", []),
    ("Mos-\nsy forest", []),
    ("6-Sept-1946", []),
    ("Elev.6400 H. Hoogstraal", []),
    # Not the same kind: a Roman month and a number.
    ("VII-1968", []),
])
def test_the_range_grammar_s_token_rules(text, ranges):
    assert [text[start:end] for start, end in range_spans(text)] == ranges


# ------------------------------------------------------------------- the alignment, extended


def test_the_alignment_returns_the_agreed_spans_cut_at_white_space_and_each_difference_as_one():
    readings = pilot_readings()
    segments = reading_segments([r.literal_text for r in readings])

    assert [[span.text for span in spans] for spans in segments] == [
        ["6-Sept-1946,"] * 3,
        # The foot mark B alone wrote joins the text it follows: no space between them.
        ["Elev.6400", "Elev.6400'", "Elev.6400"],
        ["H."] * 3,
        ["Hoogstraal"] * 3,
        ["leg."] * 3,
        ["Sp.30"] * 3,
        ["♀", "♀", "♂"],
        # B's extra line: the others wrote nothing there, an empty span where their text ends.
        ["", "P-95-81-16", ""],
    ]
    assert [(span.start, span.end) for span in segments[-1]] == [(49, 49), (51, 61), (49, 49)]


def test_readings_that_differ_only_in_spacing_keep_their_spacing_in_one_segment():
    segments = reading_segments(["Davao Prov. Mindanao", "DavaoProv. Mindanao"])
    assert [[span.text for span in spans] for spans in segments] == [
        ["Davao Prov.", "DavaoProv."], ["Mindanao", "Mindanao"]
    ]


@pytest.mark.parametrize("count", [1, 2, 3], ids=["one reading", "two identical", "three identical"])
def test_the_fallback_tiles_identical_readings_and_one_reading(count):
    text = "E. slope Mt. McKinley\nDavao Prov.\n3 sept. '46"
    readings = [reading(route, text) for route in ROUTES[:count]]

    units = alignment_units(REGION.id, readings)

    assert problems(units, texts_of(readings)) == []
    assert [unit.readers[readings[0].id].text for unit in units.units] == [
        "E.", "slope", "Mt.", "McKinley", "Davao", "Prov.", "3", "sept.", "'46"
    ]
    assert {unit.image for unit in units.units} == {UNCERTAIN}
    assert [unit.lines for unit in units.units][3:5] == [(1, 1), (2, 2)]
    assert [unit.id for unit in units.units][:2] == [f"{REGION.id}:1", f"{REGION.id}:2"]
    assert all(not (u.means or u.role or u.fields or u.note) for u in units.units)


@pytest.mark.parametrize("text", ["Elev. 6400 - 7000 ft.", "Alt 1200 to 1500 m", "-20 to -10 C"])
def test_the_fallback_keeps_a_range_whole(text):
    readings = [reading(ROUTES[0], text), reading(ROUTES[1], text)]
    units = alignment_units(REGION.id, readings)

    assert problems(units, texts_of(readings)) == []
    (ranged,) = [u for u in units.units if range_spans(text) and
                 u.readers[readings[0].id].start == range_spans(text)[0][0]]
    assert ranged.readers[readings[0].id].end == range_spans(text)[0][1]


def test_the_fallback_tiles_differing_readings_and_a_reader_that_wrote_nothing():
    readings = pilot_readings()
    units = alignment_units(REGION.id, readings)

    assert problems(units, texts_of(readings)) == []
    assert len(units.units) == 8
    # A reader that wrote nothing at a unit has an empty text there; the unit is still the label's.
    last = units.units[-1]
    assert [last.readers[r.id].text for r in readings] == ["", "P-95-81-16", ""]
    assert last.lines == (4, 4)


def test_a_label_whose_readings_hold_no_text_has_no_units():
    assert reading_segments(["", " \n "]) == []
    assert alignment_units(REGION.id, [reading(ROUTES[0], ""), reading(ROUTES[1], "  ")]) is None


def test_the_alignment_tiles_every_recorded_and_varied_reading():
    """Guard: seeded variations of the pilot readings (words dropped, added and changed,
    spacing removed), every segment cut tiles every reading and splits no range."""
    import random

    words = ["Elev.6400", "6400", "-", "7000", "to", "ft.", "Davao", "Prov.", "DavaoProv.", "P.I.",
             "6-Sept-1946,", "♀", "♂", "\n", "IV-29-68-4", "1a2", "12-15.VII.1968", "a", "3", "5",
             "Mos-\nsy", "\U0001f98b", "", "&", "-20", "bis"]
    rng = random.Random(20261028)
    for _ in range(600):
        base = " ".join(rng.choice(words) for _ in range(rng.randint(0, 12)))
        texts = [base]
        for _ in range(rng.randint(0, 3)):
            tokens = base.split(" ")
            for _ in range(rng.randint(0, 3)):
                at = rng.randrange(len(tokens) + 1)
                choice = rng.random()
                if choice < 0.4:
                    tokens.insert(at, rng.choice(words))
                elif tokens:
                    tokens[min(at, len(tokens) - 1)] = rng.choice(words) if choice < 0.8 else ""
            texts.append(("" if rng.random() < 0.1 else " ").join(tokens))
        readings = [reading(f"route-{n}", text) for n, text in enumerate(texts)]
        units = alignment_units(REGION.id, readings)
        if units is None:
            assert not any(text.strip() for text in texts)
            continue
        assert problems(units, texts_of(readings)) == [], texts


# ----------------------------------------------------------------------- section 3's checks


def tile(readings, cuts) -> ReadingUnits:
    """Units cut where `cuts` say, as (start, end) per reading per unit."""
    return ReadingUnits(label=REGION.id, units=[
        ReadingUnit(
            id=f"{REGION.id}:{n}", label=REGION.id, lines=(1, 1), image=UNCERTAIN,
            readers={r.id: UnitText(text=r.literal_text[a:b], start=a, end=b)
                     for r, (a, b) in zip(readings, spans)},
        )
        for n, spans in enumerate(cuts, 1)
    ])


def test_the_checks_accept_units_that_tile_every_reading():
    readings = [reading(ROUTES[0], "Elev. 6400 - 7000 ft."), reading(ROUTES[1], "Elev.  6400-7000 ft")]
    units = tile(readings, [[(0, 5), (0, 5)], [(6, 17), (7, 16)], [(18, 21), (17, 19)]])
    assert problems(units, texts_of(readings)) == []


@pytest.mark.parametrize("cuts,found", [
    # A gap of text between two units.
    ([[(0, 5), (0, 5)], [(13, 17), (12, 16)], [(18, 21), (17, 19)]], "does not go on in reading"),
    # Overlapping units.
    ([[(0, 5), (0, 5)], [(4, 17), (7, 16)], [(18, 21), (17, 19)]], "does not go on in reading"),
    # The end of a reading left out.
    ([[(0, 5), (0, 5)], [(6, 17), (7, 16)]], "do not cover the end of reading"),
    # A unit ends inside the range "6400 - 7000".
    ([[(0, 5), (0, 5)], [(6, 10), (7, 11)], [(11, 17), (11, 16)], [(18, 21), (17, 19)]],
     "begins inside a range"),
    # A unit that holds no reader's text.
    ([[(0, 5), (0, 5)], [(5, 5), (5, 5)], [(6, 17), (7, 16)], [(18, 21), (17, 19)]],
     "holds no reader's text"),
])
def test_the_checks_name_what_fails(cuts, found):
    readings = [reading(ROUTES[0], "Elev. 6400 - 7000 ft."), reading(ROUTES[1], "Elev.  6400-7000 ft")]
    assert any(found in problem for problem in problems(tile(readings, cuts), texts_of(readings)))


def test_the_checks_refuse_units_that_name_other_readings():
    readings = [reading(ROUTES[0], "a b"), reading(ROUTES[1], "a b")]
    units = tile(readings, [[(0, 1), (0, 1)], [(2, 3), (2, 3)]])
    assert problems(units, {readings[0].id: "a b", "another": "a b"}) == [
        "the units do not name exactly the label's readings"
    ]


def test_the_image_names_a_readers_non_empty_text_never_an_empty_one():
    """Carried from the review of PR #423: a reader that wrote nothing has an empty text, which
    let `image == ""` validate."""
    readers = {"a": UnitText(text="", start=3, end=3), "b": UnitText(text="P-95", start=4, end=8)}
    unit = {"id": "L:1", "label": "L", "lines": (1, 1), "readers": readers}

    with pytest.raises(ValidationError, match="non-empty text"):
        ReadingUnit(**unit, image="")
    for image in ("P-95", UNCERTAIN, NOT_VISIBLE):
        assert ReadingUnit(**unit, image=image).image == image


# ---------------------------------------------------------------- the request and the answer


def test_the_request_names_readers_by_letter_and_gives_the_segments_line_by_line():
    readings = pilot_readings()
    request, letters = build_units_request(readings, reading_segments([r.literal_text for r in readings]))

    assert list(letters) == ["A", "B", "C"]
    assert "Independent readers A, B and C transcribed the attached label image." in request
    assert 'Line 1: [1] "6-Sept-1946," [2] {A "Elev.6400", B "Elev.6400\'", C "Elev.6400"}' in request
    assert 'Line 2: [3] "H." [4] "Hoogstraal" [5] "leg."' in request
    assert 'Line 3: [6] "Sp.30" [7] {A "♀", B "♀", C "♂"}' in request
    assert 'Line 4: [8] {A "", B "P-95-81-16", C ""}' in request
    assert request.endswith("leave out a key that does not.")
    assert "Group segments 1 to 8 into reading units" in request


def test_an_answer_becomes_units_that_tile_every_reading():
    readings = pilot_readings()
    segments = reading_segments([r.literal_text for r in readings])
    letters = dict(zip("ABC", readings))

    assert units_output_problems(output(), letters, segments) == []
    units = units_from_output(REGION.id, output(), letters, segments)

    assert problems(units, texts_of(readings)) == []
    a, b, c = readings
    images = [unit.image for unit in units.units]
    assert images == ["6-Sept-1946,", UNCERTAIN, "H. Hoogstraal", "leg.", "Sp.30 ♀", NOT_VISIBLE]
    assert units.units[2].readers[b.id] == UnitText(text="H. Hoogstraal", start=24, end=37)
    assert units.units[4].readers[c.id].text == "Sp.30 ♂"
    assert units.units[0].means == "1946-09-06" and units.units[0].fields == ["date_visited_from"]
    assert units.units[1].note == "B alone saw a foot mark."
    assert [unit.lines for unit in units.units] == [(1, 1), (1, 1), (2, 2), (2, 2), (3, 3), (4, 4)]


@pytest.mark.parametrize("change,problem", [
    ({"units": [{"first": 1, "image": "A"}, {"first": 3, "last": 8, "image": "A"}]},
     "unit 2 should start at segment 2"),
    ({"units": [{"first": 1, "last": 7, "image": "A"}]}, "the units must end at segment 8"),
    ({"units": [{"first": 1, "last": 7, "image": "A"}, {"first": 8, "image": "A"}]},
     "unit 2: reader A wrote nothing there"),
    ({"units": [{"first": 1, "last": 8, "image": "D"}]}, "unit 1: image must be one of"),
    ({"units": [{"first": 1, "last": 8, "image": "A", "fields": ["locality"]}]},
     "unit 1: locality is not a field key"),
    ({"units": [{"first": 1, "last": 8, "image": "A", "fields": ["country", "country"]}]},
     "unit 1 names a field twice"),
])
def test_an_answer_that_fails_a_check_is_told_which(change, problem):
    readings = pilot_readings()
    segments = reading_segments([r.literal_text for r in readings])
    found = units_output_problems(output(**change), dict(zip("ABC", readings)), segments)
    assert any(problem in item for item in found), found


def test_a_meaning_that_repeats_the_text_as_written_is_left_empty():
    readings = pilot_readings()
    segments = reading_segments([r.literal_text for r in readings])
    answer = output(units=[{"first": 1, "image": "A", "means": "6-Sept-1946"},
                           {"first": 2, "last": 8, "image": "uncertain", "means": "an elevation"}])

    units = units_from_output(REGION.id, answer, dict(zip("ABC", readings)), segments)

    assert [unit.means for unit in units.units] == ["", "an elevation"]


# ------------------------------------------------------------------ the call, with a fake provider


def direct_units(monkeypatch, tmp_path, calls, *answers, readings=None):
    """first_pass_units_direct against a fake provider that gives these answers in turn (an
    answer as its tool call's arguments, or a function of the output tool's name)."""

    def respond(messages, info):
        calls.append(messages)
        answer = answers[min(len(calls), len(answers)) - 1]
        if callable(answer):
            return answer(info.output_tools[0].name)
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, json.dumps(answer))],
            usage=RequestUsage(input_tokens=3_000, output_tokens=500),
            finish_reason="stop",
        )

    class Gateway:
        def __init__(self, timeout_seconds=None):
            self.routes = {ROUTE.route_id: ROUTE}

        def route(self, route_id):
            return self.routes[route_id]

        def model_for(self, route_id):
            return FunctionModel(respond, model_name="fake-vision")

    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setattr(first_pass_module, "HuggingFaceModelGateway", Gateway)
    monkeypatch.setattr(workflow_module, "crop_bytes", lambda *args: b"PNG")
    readings = readings or pilot_readings()
    profile = Profile(first_pass_route=ROUTE.route_id, routes=tuple(r.route_id for r in readings))
    run = Run(profile=profile, dependencies=DEPENDENCIES, first_pass_path="units")
    decision, units = first_pass_module.first_pass_units_direct(
        SimpleNamespace(blobs=LocalBlobs(tmp_path)),
        SimpleNamespace(asset=SimpleNamespace(id="asset-1"), run=run),
        REGION,
        readings,
    )
    return decision, units, readings


def test_the_call_records_units_and_a_decision_that_names_no_reading(monkeypatch, tmp_path):
    calls = []
    decision, units, readings = direct_units(monkeypatch, tmp_path, calls, ANSWER)

    assert len(calls) == 1 and calls[0][0].instructions == UNITS_PROMPT.text
    assert [unit.image for unit in units.units][:3] == ["6-Sept-1946,", UNCERTAIN, "H. Hoogstraal"]
    assert problems(units, texts_of(readings)) == []
    # The decision names no reading and every difference keeps the verdict uncertain.
    assert decision.selected_observation_id is None and decision.rationale == UNITS_RATIONALE
    assert decision.notes == {} and decision.differences
    assert {d.verdict for d in decision.differences} == {"uncertain"}
    call = decision.call
    assert call.completion_state == "validated_output"
    assert (call.input_tokens, call.output_tokens) == (3_000, 500)
    # The units path asks for low reasoning over the route's own request options.
    assert call.parameters["extra_body"]["reasoning_effort"] == "low"
    request, _ = build_units_request(readings, reading_segments([r.literal_text for r in readings]))
    import hashlib

    assert call.request_sha256 == hashlib.sha256(request.encode()).hexdigest()


def test_an_answer_that_fails_a_check_is_sent_back_once_with_the_check_named(monkeypatch, tmp_path):
    calls = []
    gap = {"units": [{"first": 1, "image": "A"}, {"first": 3, "last": 8, "image": "A"}]}

    decision, units, _ = direct_units(monkeypatch, tmp_path, calls, gap, ANSWER)

    assert len(calls) == 2
    retry = calls[1][-1].parts[-1].content
    assert "the units must cover segments 1 to 8, each once and in order" in retry
    assert decision.rationale == UNITS_RATIONALE and len(units.units) == 6


def test_an_answer_that_fails_twice_is_a_known_malformed_response(monkeypatch, tmp_path):
    calls = []
    gap = {"units": [{"first": 1, "image": "A"}, {"first": 3, "last": 8, "image": "A"}]}

    with pytest.raises(AdapterFailure) as failure:
        direct_units(monkeypatch, tmp_path, calls, gap)

    assert len(calls) == 2
    assert failure.value.status == LookupStatus.MALFORMED


def test_a_call_stopped_at_its_caps_gets_the_alignments_units(monkeypatch, tmp_path):
    def endless(tool):
        return ModelResponse(
            parts=[ToolCallPart(tool, json.dumps({"units": [{"first": 2, "image": "A"}]}))],
            usage=RequestUsage(input_tokens=9_000, output_tokens=4_000),
        )

    decision, units, readings = direct_units(monkeypatch, tmp_path, [], endless)

    assert decision.rationale == CAP_RATIONALE and decision.selected_observation_id is None
    assert decision.call.completion_state == "usage_limit"
    assert units == alignment_units(REGION.id, readings)


# ------------------------------------------------------------- the workflow, synthetic adapters


def drained(tmp_path, monkeypatch, *, switch="on", alternate="taxon: different", readers=None):
    from test_first_pass_workflow import start

    from specimen_digitization.application.api import SYNTHETIC_TEXT
    from specimen_digitization.application.workflow import SyntheticAdapters

    if switch is None:
        monkeypatch.delenv(SETTING, raising=False)
    else:
        monkeypatch.setenv(SETTING, switch)
    adapters = SyntheticAdapters(LocalBlobs(tmp_path / "blobs"), SYNTHETIC_TEXT, alternate)
    calls = []
    first_pass_units = adapters.first_pass_units
    adapters.first_pass_units = lambda *args: calls.append(args[1].id) or first_pass_units(*args)
    workflow, principal, ident = start(tmp_path, adapters)
    return workflow, principal, ident, calls


def test_a_run_records_its_path_when_it_starts_and_keeps_it(tmp_path, monkeypatch):
    workflow, principal, ident, _ = drained(tmp_path, monkeypatch, switch="on")
    specimen = workflow.step(principal, ident)
    assert specimen.run.completed_steps == ["pin_dependencies"]
    assert specimen.run.first_pass_path == UNITS
    # The switch turned off after the run started: the run keeps its path, and its re-pin after
    # classify keeps the units prompt.
    monkeypatch.setenv(SETTING, "off")
    specimen = workflow.drain(principal, ident)
    assert specimen.run.first_pass_path == UNITS
    assert specimen.run.completed_steps.count("pin_dependencies") == 1
    assert specimen.run.reading_units and specimen.run.first_pass_decisions


def test_a_run_started_on_the_old_path_stays_there(tmp_path, monkeypatch):
    workflow, principal, ident, calls = drained(tmp_path, monkeypatch, switch=None)
    workflow.step(principal, ident)
    monkeypatch.setenv(SETTING, "on")

    run = workflow.drain(principal, ident).run

    assert run.first_pass_path == OLD and run.reading_units == [] and calls == []
    assert "first_pass_path" not in run.model_dump(mode="json")


def test_the_units_path_cuts_differing_readings_and_stores_the_units(tmp_path, monkeypatch):
    workflow, principal, ident, calls = drained(tmp_path, monkeypatch)

    specimen = workflow.drain(principal, ident)
    run = specimen.run
    (region,) = run.regions
    readings = [o for o in run.observations if o.region_id == region.id]

    assert calls == [region.id]
    (units,) = run.reading_units
    assert units.label == region.id and problems(units, texts_of(readings)) == []
    (decision,) = run.first_pass_decisions
    assert decision.selected_observation_id is None
    (transcript,) = run.transcripts
    assert transcript.decision_kind == "first_pass" and not transcript.resolved
    # Stored with the run, and read back whole.
    stored = workflow.repository.get(principal.scope, ident).run
    assert stored.reading_units == run.reading_units and stored.first_pass_path == UNITS


def test_the_units_path_calls_the_first_pass_on_agreed_readings_too(tmp_path, monkeypatch):
    from specimen_digitization.application.api import SYNTHETIC_TEXT

    workflow, principal, ident, calls = drained(tmp_path, monkeypatch, alternate=SYNTHETIC_TEXT)

    run = workflow.drain(principal, ident).run
    (region,) = run.regions

    assert calls == [region.id]
    (transcript,) = run.transcripts
    (decision,) = run.first_pass_decisions
    # Identical readings keep their rule, and the transcript records the call beside it.
    assert transcript.decision_kind == "identical_readings" and transcript.resolved
    assert transcript.first_pass_call == decision.call
    assert run.reading_units[0].label == region.id


def test_the_old_path_calls_no_first_pass_on_agreed_readings(tmp_path, monkeypatch):
    from specimen_digitization.application.api import SYNTHETIC_TEXT

    workflow, principal, ident, calls = drained(tmp_path, monkeypatch, switch="off",
                                                alternate=SYNTHETIC_TEXT)
    run = workflow.drain(principal, ident).run

    assert calls == [] and run.first_pass_decisions == [] and run.reading_units == []
    assert not any(step.startswith("first_pass:") for step in run.completed_steps)


def test_a_label_with_one_reading_gets_the_alignments_units_without_a_call(tmp_path, monkeypatch):
    from specimen_digitization.application.reliability import ReadingStopped

    workflow, principal, ident, calls = drained(tmp_path, monkeypatch)
    transcribe = workflow.adapters.transcribe

    def one_reader(specimen, region, route):
        # Reader B's reading stops at its token limits: the label keeps reader A's alone.
        if route == specimen.run.profile.routes[1]:
            raise ReadingStopped("reader_output_limit")
        return transcribe(specimen, region, route)

    workflow.adapters.transcribe = one_reader
    run = workflow.drain(principal, ident).run
    (region,) = run.regions
    (only,) = [o for o in run.observations if o.region_id == region.id]

    assert calls == [] and run.first_pass_decisions == []
    assert not any(step.startswith("first_pass:") for step in run.completed_steps)
    (units,) = run.reading_units
    assert units == alignment_units(region.id, [only])
    assert problems(units, texts_of([only])) == [] and {u.image for u in units.units} == {UNCERTAIN}


def test_a_label_given_up_on_gets_the_alignments_units_at_adjudicate(tmp_path, monkeypatch):
    workflow, principal, ident, calls = drained(tmp_path, monkeypatch)

    def malformed(*args):
        raise AdapterFailure("first_pass_malformed_response", LookupStatus.MALFORMED)

    workflow.adapters.first_pass_units = malformed
    run = workflow.drain(principal, ident).run
    (region,) = run.regions
    readings = [o for o in run.observations if o.region_id == region.id]

    assert [f.reason_code for f in run.findings if f.rule_id == "first_pass_given_up"] == [
        f"first_pass_given_up:{region.id}:first_pass_malformed_response"
    ]
    assert run.first_pass_decisions == []
    (units,) = run.reading_units
    assert units == alignment_units(region.id, readings)
    assert {unit.image for unit in units.units} == {UNCERTAIN}


def test_an_agreed_label_can_be_given_up_on_the_units_path(tmp_path, monkeypatch):
    from specimen_digitization.application.api import SYNTHETIC_TEXT

    workflow, principal, ident, _ = drained(tmp_path, monkeypatch, alternate=SYNTHETIC_TEXT)

    def malformed(*args):
        raise AdapterFailure("first_pass_malformed_response", LookupStatus.MALFORMED)

    workflow.adapters.first_pass_units = malformed
    run = workflow.drain(principal, ident).run

    assert any(f.rule_id == "first_pass_given_up" for f in run.findings)
    assert run.reading_units and {u.image for u in run.reading_units[0].units} == {UNCERTAIN}


@pytest.mark.parametrize("forge", ["a pick", "units of another label", "units that do not tile", "no units"])
def test_the_step_refuses_a_units_answer_that_breaks_the_contract(tmp_path, monkeypatch, forge):
    workflow, principal, ident, _ = drained(tmp_path, monkeypatch)
    honest = workflow.adapters.first_pass_units

    def forged(specimen, region, readings):
        decision, units = honest(specimen, region, readings)
        if forge == "a pick":
            decision = decision.model_copy(update={"selected_observation_id": readings[0].id,
                                                   "differences": []})
        elif forge == "units of another label":
            units = alignment_units("another", readings)
        elif forge == "units that do not tile":
            first = units.units[0]
            span = next(iter(first.readers.values()))
            moved = {key: UnitText(text=value.text[1:], start=value.start + 1, end=value.end)
                     if key == next(iter(first.readers)) else value for key, value in first.readers.items()}
            assert span.text
            units = units.model_copy(update={"units": [first.model_copy(update={
                "readers": moved, "image": UNCERTAIN}), *units.units[1:]]})
        else:
            units = None
        return decision, units

    workflow.adapters.first_pass_units = forged
    run = workflow.drain(principal, ident).run

    assert run.blocker == "first_pass_contract_invalid"
    assert run.reading_units == []


def test_the_run_s_units_are_built_whole_through_its_validation():
    """Carried from Codex's review of PR #423: the duplicate-label check runs only when the
    list is validated, so the producer stores through store_reading_units."""
    from specimen_digitization.application.domain import Region

    regions = [Region(id=f"L{n}", asset_id="a", x=0, y=0, width=1, height=1, order=n,
                      method="m", version="1") for n in (1, 2)]
    run = Run(regions=regions)
    first = alignment_units("L2", [reading(ROUTES[0], "b")])
    second = alignment_units("L1", [reading(ROUTES[0], "a")])
    store_reading_units(run, [first])
    store_reading_units(run, [second])
    # One entry per label, in label order; a label's entry is replaced, never repeated.
    assert [entry.label for entry in run.reading_units] == ["L1", "L2"]
    store_reading_units(run, [alignment_units("L2", [reading(ROUTES[0], "c")])])
    assert [entry.units[0].image for entry in run.reading_units] == [UNCERTAIN, UNCERTAIN]
    assert run.reading_units[1].units[0].readers[next(iter(run.reading_units[1].units[0].readers))].text == "c"
    with pytest.raises(ValidationError):
        store_reading_units(run, [first, first])


# --------------------------------------------------- the transport: model child -> parent -> run


def units_child(payload):
    """The isolated model child, spawned by name, with a provider that answers each segment as
    its own unit: the image names reader A where A wrote text, else B."""
    from specimen_digitization.application import first_pass, production
    from specimen_digitization.application.model_runtime import model_child
    from specimen_digitization.model_gateway import HUGGINGFACE_ROUTES

    class Gateway:
        def __init__(self, timeout_seconds=None):
            self.routes = dict(HUGGINGFACE_ROUTES)

        def route(self, route_id):
            return self.routes[route_id]

        def model_for(self, route_id):
            def respond(messages, info):
                request = str(messages[0].parts[-1].content[0])
                count = int(re.search(r"Group segments 1 to (\d+)", request).group(1))
                empty_a = {int(n) for n in re.findall(r'\[(\d+)\] \{A ""', request)}
                units = [{"first": n, "image": "B" if n in empty_a else "A",
                          "fields": ["habitat"] if n == 1 else []} for n in range(1, count + 1)]
                return ModelResponse(
                    parts=[ToolCallPart(info.output_tools[0].name, json.dumps({"units": units}))],
                    usage=RequestUsage(input_tokens=3_100, output_tokens=420),
                    finish_reason="stop",
                )

            return FunctionModel(respond, model_name="local-provider")

    production.HuggingFaceModelGateway = Gateway
    first_pass.HuggingFaceModelGateway = Gateway
    return model_child(payload)


def test_the_units_cross_the_model_child_to_the_parent_and_the_stored_run(tmp_path, monkeypatch):
    from test_lane_routes import DisagreeingReaders, start

    class ChildUnits(DisagreeingReaders):
        model_effect = staticmethod(units_child)
        first_pass_units = ProductionAdapters.first_pass_units

    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setenv(SETTING, "on")
    adapters = ChildUnits(LocalBlobs(tmp_path / "blobs"))
    workflow, principal, ident = start(tmp_path, adapters)

    specimen = workflow.drain(principal, ident)
    stored = workflow.repository.get(principal.scope, ident)

    run = stored.run
    assert run.first_pass_path == UNITS and run == specimen.run
    (region,) = run.regions
    readings = [o for o in run.observations if o.region_id == region.id]
    (units,) = run.reading_units
    assert units.label == region.id and problems(units, texts_of(readings)) == []
    assert units.units[0].image == units.units[0].readers[readings[0].id].text
    assert units.units[0].fields == ["habitat"]
    assert units.units[-1].image == units.units[-1].readers[readings[1].id].text == "1946"
    (decision,) = run.first_pass_decisions
    assert decision.selected_observation_id is None and decision.call.input_tokens == 3_100
    # The call is costed as every first pass is: its tokens at the route's prices.
    (call,) = [c for c in run.paid_calls if c["step"] == f"first_pass:{region.id}"]
    # 3,100 input and 420 output tokens at 0.15 and 0.50 dollars a million.
    assert (call["route_id"], call["cost_basis"], call["cost_micros"]) == ("first-pass-glm", "computed", 675)


def invoke(tmp_path, value):
    """The parent's side of a units-path call whose child answered `value`."""
    body = {"status": "completed", "value": value}
    result = SimpleNamespace(status="completed", cleanup_complete=True,
                             value=json.dumps(body).encode())
    run = Run(profile=Profile(first_pass_route=ROUTE.route_id), dependencies=DEPENDENCIES,
              first_pass_path="units")
    original = model_runtime.run_isolated
    model_runtime.run_isolated = lambda *args, **kw: result
    try:
        return model_runtime.invoke_model(
            SimpleNamespace(blobs=LocalBlobs(tmp_path), model_effect=None),
            SimpleNamespace(id="specimen-1", asset=ASSET, run=run),
            "first_pass", region=REGION, readings=pilot_readings(2),
        )
    finally:
        model_runtime.run_isolated = original


@pytest.mark.parametrize("units", ["missing", "another label", "not a record"])
def test_the_parent_refuses_units_it_cannot_validate(tmp_path, monkeypatch, units):
    decision, _, readings = direct_units(monkeypatch, tmp_path, [], ANSWER, readings=pilot_readings(2))
    decision = decision.model_copy(update={"call": decision.call.model_copy(
        update={"input_asset_id": ASSET.id})})
    value = {"decision": decision.model_dump(mode="json")}
    if units == "another label":
        value["units"] = alignment_units("another", readings).model_dump(mode="json")
    elif units == "not a record":
        value["units"] = {"label": REGION.id, "units": []}

    with pytest.raises(OperationalBlock, match="^external_outcome_unknown$"):
        invoke(tmp_path, value)


def test_the_parent_validates_and_returns_the_units(tmp_path, monkeypatch):
    decision, units, _ = direct_units(monkeypatch, tmp_path, [], ANSWER, readings=pilot_readings(2))
    decision = decision.model_copy(update={"call": decision.call.model_copy(
        update={"input_asset_id": ASSET.id})})

    got = invoke(tmp_path, {"decision": decision.model_dump(mode="json"),
                            "units": units.model_dump(mode="json")})

    assert got == (decision, units)


# ------------------------------------------------------- the old path: main's stored record bytes

# Pins computed on main 4172ab824 (before this change) by this module's frozen_old_path_run,
# whose readings differ, so the old path's first pass runs: the stored record's bytes as
# SQLiteRepository writes them, and the projection's writes. Written "sha256:<hex>".
MAIN_OLD_PATH_STORED = "sha256:0fe7d7e02313df9943b7ebc3355130f1c29e8459facfe3ca6261b800de877cc9"
MAIN_OLD_PATH_WRITES = "sha256:3c5e8fbcf98fcdc4e378a2d55857008f239c2764cc8ecfa84dd1aae9049da077"


def frozen_old_path_run(tmp_path, monkeypatch, *, switch=None):
    """A whole synthetic run on the old path (switch unset or off) with readings that differ,
    its ids and clocks fixed as the API contract exporter fixes them."""
    import itertools
    from datetime import datetime, timezone
    from uuid import UUID

    from specimen_digitization.application import api, domain, provider_circuit, review_risk, search

    fixed = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz else fixed.replace(tzinfo=None)

    for module in (domain, api, workflow_module, search, review_risk):
        monkeypatch.setattr(module, "datetime", FixedDatetime, raising=False)
    ids = (UUID(int=n) for n in itertools.count(100))
    circuit = (UUID(int=n) for n in itertools.count(5000))
    monkeypatch.setattr(domain, "uuid4", lambda: next(ids))
    monkeypatch.setattr(provider_circuit, "uuid4", lambda: next(circuit))
    original = workflow_module.Workflow.__init__

    def deterministic(self, *args, **kwargs):
        kwargs["clock"] = lambda: fixed
        kwargs["monotonic"] = lambda: 100.0
        original(self, *args, **kwargs)

    monkeypatch.setattr(workflow_module.Workflow, "__init__", deterministic)
    from test_first_pass_workflow import start

    from specimen_digitization.application.api import SYNTHETIC_TEXT
    from specimen_digitization.application.workflow import SyntheticAdapters

    if switch is None:
        monkeypatch.delenv(SETTING, raising=False)
    else:
        monkeypatch.setenv(SETTING, switch)
    adapters = SyntheticAdapters(LocalBlobs(tmp_path / "blobs"), SYNTHETIC_TEXT, "taxon: different")
    workflow, principal, ident = start(tmp_path, adapters)
    return workflow.drain(principal, ident)


def old_path_pins(specimen) -> tuple[str, str]:
    import hashlib

    from test_reading_units import locate

    from specimen_digitization.application.active_graph import pack
    from specimen_digitization.application.projection import writes
    from specimen_digitization.application.storage import digest

    stored = json.dumps(pack(specimen.model_copy(deep=True), None), ensure_ascii=False,
                        separators=(",", ":"))
    rows = [[w.operation, w.variables, w.key] for w in writes(specimen, locate, lambda ref: 1, "worker-uid")]
    return ("sha256:" + hashlib.sha256(stored.encode()).hexdigest(), "sha256:" + digest(rows))


@pytest.mark.parametrize("switch", [None, "off"], ids=["unset", "off"])
def test_an_old_path_run_stores_main_s_bytes(tmp_path, monkeypatch, switch):
    specimen = frozen_old_path_run(tmp_path, monkeypatch, switch=switch)
    run = specimen.run

    assert run.first_pass_path == OLD and run.reading_units == []
    assert any(step.startswith("first_pass:") for step in run.completed_steps)
    assert old_path_pins(specimen) == (MAIN_OLD_PATH_STORED, MAIN_OLD_PATH_WRITES)



# -------------------------------------------------------------- integrity and the projection


def test_integrity_holds_a_units_path_run_to_its_units(tmp_path, monkeypatch):
    from specimen_digitization.application.integrity import EvidenceIntegrityError, verify_evidence

    workflow, principal, ident, _ = drained(tmp_path, monkeypatch)
    specimen = workflow.drain(principal, ident)
    verify_evidence(specimen, workflow.blobs)

    broken = specimen.model_copy(deep=True)
    entry = broken.run.reading_units[0]
    first = entry.units[0]
    key = next(iter(first.readers))
    span = first.readers[key]
    # The first unit's text in one reading moved by a character: it no longer tiles the reading.
    shifted = UnitText(text=span.text[1:], start=span.start + 1, end=span.end)
    broken.run.reading_units = [entry.model_copy(update={"units": [
        first.model_copy(update={"readers": {**first.readers, key: shifted}, "image": UNCERTAIN}),
        *entry.units[1:],
    ]})]
    with pytest.raises(EvidenceIntegrityError):
        verify_evidence(broken, workflow.blobs)


def test_integrity_holds_a_units_path_decision_to_naming_no_reading(tmp_path, monkeypatch):
    from specimen_digitization.application.api import SYNTHETIC_TEXT
    from specimen_digitization.application.integrity import EvidenceIntegrityError, verify_evidence

    workflow, principal, ident, _ = drained(tmp_path, monkeypatch, alternate=SYNTHETIC_TEXT)
    specimen = workflow.drain(principal, ident)
    verify_evidence(specimen, workflow.blobs)

    (decision,) = specimen.run.first_pass_decisions
    picked = specimen.model_copy(deep=True)
    picked.run.first_pass_decisions = [decision.model_copy(
        update={"selected_observation_id": specimen.run.observations[0].id})]
    with pytest.raises(EvidenceIntegrityError):
        verify_evidence(picked, workflow.blobs)
    # The agreed label's transcript records the call its decision holds, and no other.
    other = specimen.model_copy(deep=True)
    other.run.transcripts = [other.run.transcripts[0].model_copy(update={"first_pass_call": None})]
    with pytest.raises(EvidenceIntegrityError):
        verify_evidence(other, workflow.blobs)


def test_a_decided_transcript_candidate_on_a_label_with_units_names_its_transcription_version(
    tmp_path, monkeypatch
):
    """Carried from the review of PR #423: main's writes pin holds no decided-transcript
    candidate, so the candidate id formula under units is pinned here directly."""
    from test_reading_units import locate

    from specimen_digitization.application.api import SYNTHETIC_TEXT
    from specimen_digitization.application.domain import FieldValue, ValueState
    from specimen_digitization.application.projection import derived_id, writes
    from specimen_digitization.application.storage import digest

    workflow, principal, ident, _ = drained(tmp_path, monkeypatch, alternate=SYNTHETIC_TEXT)
    specimen = workflow.drain(principal, ident)
    run = specimen.run
    (region,) = run.regions
    reader = run.observations[0].id
    run.fields["city"] = FieldValue(state=ValueState.SUPPORTED, literal="Chicago",
                                    input_source="decided_transcript", source_region_id=region.id)
    run.fields["county"] = FieldValue(state=ValueState.SUPPORTED, literal="Cook",
                                      input_source="raw_reading", source_region_id=region.id,
                                      source_observation_id=reader)

    rows = writes(specimen, locate, lambda ref: 1, "worker-uid")
    (version,) = [w.variables for w in rows if w.operation == "AppendTranscriptionVersionV3"]
    candidates = {w.variables["fieldKey"]: w.variables for w in rows
                  if w.operation == "AppendFieldCandidateV2"}

    city = candidates["city"]
    assert city["id"] == derived_id(
        "candidate", run.id, "city", "-", digest(run.fields["city"].model_dump(mode="json")), version["id"]
    )
    assert (city["inputSource"], city["sourceTranscriptionId"]) == ("decided_transcript", version["id"])
    # A raw reading's candidate keeps main's formula: no transcription in it.
    assert candidates["county"]["id"] == derived_id(
        "candidate", run.id, "county", reader, digest(run.fields["county"].model_dump(mode="json"))
    )


def test_an_agreed_label_s_units_are_projected_with_the_call_that_cut_them(tmp_path, monkeypatch):
    from test_reading_units import locate

    from specimen_digitization.application.api import SYNTHETIC_TEXT
    from specimen_digitization.application.projection import writes

    workflow, principal, ident, _ = drained(tmp_path, monkeypatch, alternate=SYNTHETIC_TEXT)
    specimen = workflow.drain(principal, ident)
    (decision,) = specimen.run.first_pass_decisions

    rows = writes(specimen, locate, lambda ref: 1, "worker-uid")
    (version,) = [w.variables for w in rows if w.operation == "AppendTranscriptionVersionV3"]

    assert version["decisionKind"] == "identical_readings"
    assert version["firstPassObservationId"] == decision.call.id
    assert version["readingUnits"] == specimen.run.reading_units[0].model_dump(mode="json")
    assert [w.operation for w in rows if w.variables.get("id") == decision.call.id] != []
