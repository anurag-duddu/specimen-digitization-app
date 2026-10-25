"""The LLM first-pass call (stage 6): docs/execution/golive/HARNESS.md section 3."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from specimen_digitization.application import first_pass as first_pass_module
from specimen_digitization.application import workflow as workflow_module
from specimen_digitization.application import model_runtime
from specimen_digitization.application import production
from specimen_digitization.application.domain import (
    Asset,
    LookupStatus,
    Observation,
    Profile,
    ReadingSpan,
    Region,
    Run,
    StageCostReservations,
)
from specimen_digitization.application.first_pass import (
    DifferenceVerdict,
    FirstPassOutput,
    build_request,
    output_problems,
    reading_differences,
)
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.storage import LocalBlobs
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.model_gateway import (
    HUGGINGFACE_ROUTES,
    HuggingFaceInferenceRoute,
)
from specimen_digitization.prompts import PromptName, ResolvedPrompt

QWEN = "VI-24-68-7.\nEpipocous\nsp.1\n♀ terminalia"
MUSE = "VI-24-68-7\nEpipsocus\nSp. 1\n♀ terminalia"
# The same characters, spaced differently: the shape of the pilot's position-10
# R1 pair, whose first pass listed no difference.
COMPACT = "IX-3-66-10\nIX-14-46"
SPACED = "IX - 3 - 66 - 10\nIX - 14 - 46"
REGION = Region(
    asset_id="asset-1", x=0, y=0, width=9, height=9, order=0, method="m", version="1"
)


def reading(route, text):
    return Observation(
        region_id=REGION.id,
        route_id=route,
        model_id="model-" + route,
        provider="provider-" + route,
        prompt_version="p",
        input_sha256="0" * 64,
        literal_text=text,
        raw_ref="raw-" + route,
        raw_sha256="1" * 64,
    )


def test_differences_are_exact_spans_and_ignore_whitespace():
    differences = reading_differences(QWEN, MUSE)

    assert [(a.text, b.text) for a, b in differences] == [
        (".", ""),
        ("Epipocous", "Epipsocus"),
        ("sp", "Sp"),
    ]
    for a, b in differences:
        assert QWEN[a.start : a.end] == a.text and MUSE[b.start : b.end] == b.text
    assert reading_differences("E Slope, Elev. 6400", "ESlope, Elev.6400") == []


def test_request_names_readers_by_letter_with_verbatim_texts():
    readings = [reading("handwriting-qwen", QWEN), reading("handwriting-muse", MUSE)]

    request, letters = build_request(readings, reading_differences(QWEN, MUSE))

    assert list(letters) == ["A", "B"] and letters["B"] is readings[1]
    assert QWEN in request and MUSE in request
    assert (
        '2. Reader A: "Epipocous" (in line "Epipocous") | Reader B: "Epipsocus"'
        in request
    )
    assert "qwen" not in request.lower() and "muse" not in request.lower()


def test_the_request_states_g19_and_asks_nothing_about_materiality():
    # G19 in the model's terms; the code decides what is material (the
    # coordinator's reading, 12:31Z on 2026-09-25).
    readings = [reading("handwriting-qwen", QWEN), reading("handwriting-muse", MUSE)]

    request, _ = build_request(readings, reading_differences(QWEN, MUSE))

    assert (
        "Choose a reader only if the image supports that reader's text at every "
        "difference that is more than capitalization. Otherwise answer null: that "
        "is how material ambiguity goes to human review."
    ) in request
    assert "material" not in request.replace("material ambiguity", "")
    assert set(DifferenceVerdict.model_fields) == {"number", "supported"}


def test_output_problems_demand_one_verdict_per_difference_and_known_letters():
    output = FirstPassOutput(
        selected_reader="C",
        verdicts=[{"number": 1, "supported": "B"}],
        rationale="r",
        reader_notes={"A": "a"},
    )

    assert output_problems(output, {"A": 0, "B": 1}, 2) == [
        "selected_reader must be one of ['A', 'B'] or null",
        "give exactly one verdict for each difference 1 to 2",
        "give one note for each reader ['A', 'B']",
    ]


def answer(**update):
    return FirstPassOutput(
        **{
            "selected_reader": "A",
            "verdicts": [],
            "rationale": "r",
            "reader_notes": {"A": "a", "B": "b"},
            **update,
        }
    )


@pytest.mark.parametrize(
    "verdicts",
    [
        [],
        [{"number": 1, "supported": "A"}],
        [{"number": 1, "supported": "B"}, {"number": 2, "supported": "neither"}],
        [{"number": 7, "supported": "nobody"}],
    ],
    ids=[
        "none",
        "one for a difference not listed",
        "two",
        "a number and letter unknown",
    ],
)
def test_verdicts_are_ignored_when_no_difference_is_listed(verdicts):
    # Nothing is numbered, so a verdict is for a difference that does not exist;
    # first_pass_direct reads verdicts 1..len(differences) only, none here.
    assert output_problems(answer(verdicts=verdicts), {"A": 0, "B": 1}, 0) == []


def test_a_call_with_no_difference_still_needs_its_pick_and_its_notes():
    output = answer(
        selected_reader="C",
        verdicts=[{"number": 1, "supported": "A"}],
        reader_notes={"A": "a"},
    )

    assert output_problems(output, {"A": 0, "B": 1}, 0) == [
        "selected_reader must be one of ['A', 'B'] or null",
        "give one note for each reader ['A', 'B']",
    ]


@pytest.mark.parametrize(
    "verdicts",
    [
        [],
        [{"number": 2, "supported": "A"}],
        [{"number": 1, "supported": "A"}, {"number": 1, "supported": "A"}],
        [{"number": 1, "supported": "A"}, {"number": 2, "supported": "A"}],
    ],
    ids=[
        "a verdict missing",
        "the wrong number",
        "a number twice",
        "a phantom verdict",
    ],
)
def test_a_listed_difference_still_demands_exactly_its_own_verdict(verdicts):
    assert output_problems(answer(verdicts=verdicts), {"A": 0, "B": 1}, 1) == [
        "give exactly one verdict for each difference 1 to 1"
    ]


def test_a_listed_difference_is_met_by_its_verdict_and_its_letter_is_checked():
    letters = {"A": 0, "B": 1}

    assert (
        output_problems(answer(verdicts=[{"number": 1, "supported": "B"}]), letters, 1)
        == []
    )
    assert output_problems(
        answer(verdicts=[{"number": 1, "supported": "C"}]), letters, 1
    ) == ["each verdict's supported must be one of ['A', 'B', 'neither', 'uncertain']"]


def test_first_pass_cost_reservation_is_one_key_for_every_region():
    reservations = StageCostReservations(
        version="stage-cost-reservations-v1", cost_micros={"first_pass": 900}
    )

    assert reservations.for_step("first_pass:region-7") == 900


ROUTE = HuggingFaceInferenceRoute(
    "fp-test", "transcription_first_pass", "vendor/vision", "novita"
)
PROMPT = ResolvedPrompt(
    name=PromptName.DISAGREEMENT_ADJUDICATION,
    text="Compare the candidate transcripts against the supplied image.",
    requested_label="test",
    served_label=None,
    version=None,
    resolution_reason="fixture",
)
VALID = {
    "selected_reader": "B",
    "verdicts": [
        {"number": 1, "supported": "B"},
        {"number": 2, "supported": "B"},
        {"number": 3, "supported": "B"},
    ],
    "rationale": "The image shows Epipsocus.",
    "reader_notes": {"A": "misread", "B": "matches"},
}
INCOMPLETE = dict(VALID, verdicts=VALID["verdicts"][:1])
PINNED = {"model_id": ROUTE.model_id, "provider": ROUTE.provider}
PROMPTS = {PROMPT.name.value: PROMPT.model_dump(mode="json")}
DEPENDENCIES = {"routes": {ROUTE.route_id: PINNED}, "prompts": PROMPTS}


def pinned_route(route_id):
    """Dependencies that pin this registered route exactly, with the prompt."""
    route = HUGGINGFACE_ROUTES[route_id]
    pin = {"model_id": route.model_id, "provider": route.provider}
    return {"routes": {route_id: pin}, "prompts": PROMPTS}


def direct_first_pass(
    monkeypatch,
    tmp_path,
    calls,
    *answers,
    readings=None,
    profile=None,
    dependencies=None,
    approved=True,
    crop=b"PNG",
    infos=None,
):
    """first_pass_direct against a fake provider that gives these answers in turn:
    an answer sent as its tool call, or a function of the output tool's name that
    returns the provider's whole response. `infos` collects what each request
    carried besides its messages."""

    def respond(messages, info):
        calls.append(messages)
        if infos is not None:
            infos.append(info)
        answer = answers[min(len(calls), len(answers)) - 1]
        tool = info.output_tools[0].name
        if callable(answer):
            return answer(tool)
        return ModelResponse(
            parts=[ToolCallPart(tool, json.dumps(answer))], finish_reason="stop"
        )

    class Gateway:
        def __init__(self, timeout_seconds=None):
            self.routes = {ROUTE.route_id: ROUTE, **HUGGINGFACE_ROUTES}

        def route(self, route_id):
            return self.routes[route_id]

        def model_for(self, route_id):
            return FunctionModel(respond, model_name="fake-vision")

    if approved:
        monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    else:
        monkeypatch.delenv("SPECIMEN_APPROVED_INFERENCE", raising=False)
    monkeypatch.setattr(first_pass_module, "HuggingFaceModelGateway", Gateway)
    monkeypatch.setattr(workflow_module, "crop_bytes", lambda *args: crop)
    run = Run(
        profile=profile or Profile(first_pass_route=ROUTE.route_id),
        dependencies=DEPENDENCIES if dependencies is None else dependencies,
    )
    if readings is None:
        readings = [
            reading("handwriting-qwen", QWEN),
            reading("handwriting-muse", MUSE),
        ]
    decision = first_pass_module.first_pass_direct(
        SimpleNamespace(blobs=LocalBlobs(tmp_path)),
        SimpleNamespace(asset=SimpleNamespace(id="asset-1"), run=run),
        REGION,
        readings,
    )
    return decision, readings


def test_first_pass_records_the_decision_by_reading_and_its_own_call(
    monkeypatch, tmp_path
):
    calls = []
    decision, (first, second) = direct_first_pass(monkeypatch, tmp_path, calls, VALID)

    assert decision.region_id == REGION.id == decision.call.region_id
    assert decision.selected_observation_id == second.id
    assert decision.notes == {first.id: "misread", second.id: "matches"}
    # The code decides materiality: difference 3 is capitalization alone.
    assert [(d.number, d.verdict, d.material) for d in decision.differences] == [
        (1, second.id, True),
        (2, second.id, True),
        (3, second.id, False),
    ]
    assert decision.differences[1].spans[first.id].text == "Epipocous"
    call = decision.call
    assert (call.route_id, call.model_id) == (ROUTE.route_id, ROUTE.model_id)
    assert call.literal_text == "" and call.completion_state == "validated_output"
    assert (call.finish_state, call.provider_model_id) == ("stop", "fake-vision")
    assert call.prompt_version == hashlib.sha256(PROMPT.text.encode()).hexdigest()
    blobs = LocalBlobs(tmp_path)
    raw = json.loads(blobs.get(call.raw_ref))
    assert raw[-1]["model_name"] == call.provider_model_id
    assert len(calls) == 1 and calls[0][0].instructions == PROMPT.text
    assert any("Reader A:" in str(part.content) for part in calls[0][0].parts)
    # The crop's digest, as for every observation; the request's on its own (S5).
    crop = blobs.get(call.input_crop_ref)
    assert crop == b"PNG" and call.input_sha256 == hashlib.sha256(crop).hexdigest()
    request, _ = build_request([first, second], reading_differences(QWEN, MUSE))
    assert call.request_sha256 == hashlib.sha256(request.encode()).hexdigest()


@pytest.mark.parametrize(
    "selected,supported,expected",
    [
        ("B", ["uncertain", "B", "B"], None),
        ("B", ["neither", "B", "B"], None),
        ("B", ["A", "B", "B"], None),
        ("B", ["B", "B", "uncertain"], "B"),
        ("A", ["A", "A", "B"], "A"),
        (None, ["B", "B", "B"], None),
    ],
    ids=[
        "a material difference left uncertain",
        "a material difference left neither",
        "material verdicts split between the readers",
        "capitalization alone left uncertain",
        "every material difference supports the pick",
        "the model picks no reading",
    ],
)
def test_a_pick_stands_only_when_every_material_difference_supports_it(
    monkeypatch, tmp_path, selected, supported, expected
):
    # G19 as the coordinator read it (12:31Z on 2026-09-25): otherwise there is no
    # reading, with no retry and no block (the 12:32Z confirmation); the model's
    # pick stays on record.
    answer = dict(
        VALID,
        selected_reader=selected,
        verdicts=[{"number": n, "supported": s} for n, s in enumerate(supported, 1)],
    )
    calls = []

    decision, (first, second) = direct_first_pass(monkeypatch, tmp_path, calls, answer)

    ids = {"A": first.id, "B": second.id}
    assert len(calls) == 1
    assert decision.selected_observation_id == ids.get(expected)
    assert [d.verdict for d in decision.differences] == [
        ids.get(s, s) for s in supported
    ]
    assert decision.rationale == VALID["rationale"]
    raw = json.loads(LocalBlobs(tmp_path).get(decision.call.raw_ref))
    assert json.loads(raw[-1]["parts"][0]["args"])["selected_reader"] == selected


@pytest.mark.parametrize(
    "bind",
    [
        lambda a, b: [a.model_copy(update={"region_id": "region-2"}), b],
        lambda a, b: [a.model_copy(update={"input_asset_id": "asset-2"}), b],
        lambda a, b: [a, a],
        lambda a, b: [b, a],
    ],
    ids=["another region", "another asset", "one reading twice", "out of route order"],
)
def test_readings_must_be_the_regions_own_in_route_order(monkeypatch, tmp_path, bind):
    # The steward's review of #97: the call is bound to its region's readings.
    calls = []
    readings = bind(
        reading("handwriting-qwen", QWEN), reading("handwriting-muse", MUSE)
    )

    with pytest.raises(OperationalBlock, match="^first_pass_contract_invalid$"):
        direct_first_pass(monkeypatch, tmp_path, calls, VALID, readings=readings)

    assert calls == []


def test_a_reading_that_records_the_runs_asset_is_bound(monkeypatch, tmp_path):
    readings = [
        reading("handwriting-qwen", QWEN).model_copy(
            update={"input_asset_id": "asset-1"}
        ),
        reading("handwriting-muse", MUSE),
    ]

    decision, _ = direct_first_pass(monkeypatch, tmp_path, [], VALID, readings=readings)

    assert decision.selected_observation_id == readings[1].id


def test_an_incomplete_answer_is_retried_once_with_the_problem(monkeypatch, tmp_path):
    calls = []
    decision, _ = direct_first_pass(monkeypatch, tmp_path, calls, INCOMPLETE, VALID)

    assert len(calls) == 2 and decision.rationale == VALID["rationale"]
    retry = calls[1][-1].parts[-1]
    assert retry.content == "give exactly one verdict for each difference 1 to 3"


def test_an_answer_that_stays_invalid_is_a_known_malformed_response(
    monkeypatch, tmp_path
):
    calls = []
    with pytest.raises(AdapterFailure) as failure:
        direct_first_pass(monkeypatch, tmp_path, calls, INCOMPLETE)

    assert len(calls) == 2
    assert failure.value.status == LookupStatus.MALFORMED
    assert failure.value.outcome_unknown is False


def test_a_phantom_verdict_for_a_listed_difference_is_still_malformed(
    monkeypatch, tmp_path
):
    # The count-0 rule does not weaken a real difference's check: a fourth
    # verdict for three listed differences is retried once, then malformed.
    phantom = dict(
        VALID, verdicts=[*VALID["verdicts"], {"number": 4, "supported": "B"}]
    )
    calls = []
    with pytest.raises(AdapterFailure) as failure:
        direct_first_pass(monkeypatch, tmp_path, calls, phantom)

    assert len(calls) == 2 and failure.value.status == LookupStatus.MALFORMED
    retried, _ = direct_first_pass(monkeypatch, tmp_path, [], phantom, VALID)
    assert retried.selected_observation_id is not None


def whitespace_pair():
    return [reading("handwriting-qwen", COMPACT), reading("handwriting-muse", SPACED)]


NO_DIFFERENCE = {
    "selected_reader": "A",
    "verdicts": [],
    "rationale": "The same characters, spaced differently.",
    "reader_notes": {"A": "compact", "B": "spaced"},
}
PHANTOM_VERDICT = dict(NO_DIFFERENCE, verdicts=[{"number": 1, "supported": "A"}])


def test_a_phantom_verdict_does_not_fail_a_call_with_no_difference_to_judge(
    monkeypatch, tmp_path
):
    # The pilot's position 10, R1: the readers differ only in whitespace, so no
    # difference is listed; the model's verdict for a difference that does not
    # exist failed validation twice and blocked the run as
    # model_malformed_response. Scripted: the same phantom answer twice.
    first, second = whitespace_pair()
    assert reading_differences(first.literal_text, second.literal_text) == []
    calls = []

    decision, _ = direct_first_pass(
        monkeypatch,
        tmp_path,
        calls,
        PHANTOM_VERDICT,
        PHANTOM_VERDICT,
        readings=[first, second],
    )

    assert len(calls) == 1, "no output retry is spent on it"
    request = next(
        str(part.content)
        for part in calls[0][0].parts
        if "Reader A:" in str(part.content)
    )
    assert "The transcripts differ only in whitespace." in request
    assert decision.call.completion_state == "validated_output"
    assert decision.differences == []
    assert decision.selected_observation_id == first.id
    assert decision.notes == {first.id: "compact", second.id: "spaced"}
    assert decision.rationale == NO_DIFFERENCE["rationale"]
    # What the model said stays in the call's raw responses, unread.
    raw = json.loads(LocalBlobs(tmp_path).get(decision.call.raw_ref))
    assert json.loads(raw[-1]["parts"][0]["args"])["verdicts"] == [
        {"number": 1, "supported": "A"}
    ]


@pytest.mark.parametrize("selected,index", [("A", 0), ("B", 1), (None, None)])
def test_a_call_with_no_difference_and_no_verdicts_is_accepted_with_the_models_pick(
    monkeypatch, tmp_path, selected, index
):
    readings = whitespace_pair()
    calls = []

    decision, _ = direct_first_pass(
        monkeypatch,
        tmp_path,
        calls,
        dict(NO_DIFFERENCE, selected_reader=selected),
        readings=readings,
    )

    assert len(calls) == 1 and decision.differences == []
    assert decision.selected_observation_id == (
        None if index is None else readings[index].id
    )


@pytest.mark.parametrize(
    "stop,requests,kept,tokens",
    [
        (
            lambda tool: ModelResponse(
                parts=[ToolCallPart(tool, '{"selected_reader": "B", "verd')],
                finish_reason="length",
                usage=RequestUsage(input_tokens=1_200, output_tokens=4_096),
            ),
            2,  # The output retry is cut off too.
            ["length", "length"],
            (2_400, 8_192),
        ),
        (
            lambda tool: ModelResponse(
                parts=[ToolCallPart(tool, json.dumps(VALID))],
                finish_reason="stop",
                usage=RequestUsage(input_tokens=15_500, output_tokens=900),
            ),
            1,
            [],  # Pydantic AI counts the response past its total but keeps none.
            (15_500, 900),
        ),
    ],
    ids=["an answer cut off at its output cap", "a token total past 16,000"],
)
def test_a_first_pass_stopped_by_its_cap_selects_no_reading(
    monkeypatch, tmp_path, stop, requests, kept, tokens
):
    # No answer within its caps is no reading, so G19 sends the raw readings on
    # (PLAN section 1: "can rely on raw ... if LLM decided transcript output fails").
    calls = []

    decision, (first, second) = direct_first_pass(monkeypatch, tmp_path, calls, stop)

    assert len(calls) == requests
    assert decision.selected_observation_id is None
    assert decision.rationale == first_pass_module.CAP_RATIONALE
    assert [(d.verdict, d.material) for d in decision.differences] == [
        ("uncertain", True),
        ("uncertain", True),
        ("uncertain", False),
    ]
    assert all(set(d.spans) == {first.id, second.id} for d in decision.differences)
    call = decision.call
    assert call.completion_state == "usage_limit"
    assert call.finish_state == (kept[-1] if kept else None)
    assert (call.input_tokens, call.output_tokens) == tokens
    raw = json.loads(LocalBlobs(tmp_path).get(call.raw_ref))
    assert [response["finish_reason"] for response in raw] == kept


@pytest.mark.parametrize(
    "a,b,material",
    [
        ("sp", "Sp", False),
        ("Straße", "Strasse", True),
        ("Epipocous", "Epipsocus", True),
        (".", "", True),
    ],
)
def test_only_capitalization_is_not_material(a, b, material):
    # The coordinator's ruling at 14:05Z: spans equal once lower-cased, not
    # case-folded, so a spelling variant stays material.
    spans = [
        ReadingSpan(start=0, end=len(a), text=a),
        ReadingSpan(start=0, end=len(b), text=b),
    ]

    assert first_pass_module.is_material(spans) is material


@pytest.mark.parametrize(
    "change,code",
    [
        ({"approved": False}, "provider_data_policy_and_spending_approval_required"),
        ({"count": 1}, "first_pass_reading_count_unsupported"),
        # Three readings are supported; this third reader is not the profile's.
        ({"count": 3}, "first_pass_contract_invalid"),
        # One reader letter each, A to Z: a 27th reading has none.
        ({"count": 27}, "first_pass_reading_count_unsupported"),
        ({"profile": Profile()}, "pinned_model_route_unavailable"),
        (
            {"profile": Profile(first_pass_route="fp-unregistered")},
            "pinned_model_route_unavailable",
        ),
        (
            {
                "dependencies": {
                    "routes": {ROUTE.route_id: dict(PINNED, provider="other")},
                    "prompts": PROMPTS,
                }
            },
            "pinned_model_route_unavailable",
        ),
        (
            {"dependencies": {"routes": {ROUTE.route_id: PINNED}}},
            "pinned_prompt_unavailable",
        ),
        (
            {
                "profile": Profile(first_pass_route="harness-deepseek"),
                "dependencies": pinned_route("harness-deepseek"),
            },
            "pinned_model_route_unavailable",
        ),
        (
            {
                "profile": Profile(first_pass_route="handwriting-qwen"),
                "dependencies": pinned_route("handwriting-qwen"),
            },
            "pinned_model_route_unavailable",
        ),
    ],
    ids=[
        "no spending approval",
        "one reading",
        "three readings, the third not the profile's",
        "twenty-seven readings",
        "no first-pass route",
        "an unregistered route",
        "a route pinned to another provider",
        "no pinned prompt",
        "the harness route, pinned",
        "a reader route, pinned",
    ],
)
def test_each_block_stops_the_first_pass_before_any_request(
    monkeypatch, tmp_path, change, code
):
    change = dict(change)
    count = change.pop("count", 2)
    readings = [
        reading(route, text)
        for route, text in (
            ("handwriting-qwen", QWEN),
            ("handwriting-muse", MUSE),
            ("handwriting-third", QWEN),
        )
    ][:count]
    if count > len(readings):
        readings = [reading(f"reader-{n}", QWEN) for n in range(count)]
    calls = []

    with pytest.raises(OperationalBlock, match=f"^{code}$"):
        direct_first_pass(
            monkeypatch, tmp_path, calls, VALID, readings=readings, **change
        )

    assert calls == []


@pytest.mark.parametrize(
    "route,pinned",
    [
        ("first-pass-glm", True),
        ("fp-unregistered", False),
        # Registered, but for the harness and for text only.
        ("harness-deepseek", False),
    ],
)
def test_pin_dependencies_pins_only_a_first_pass_route_that_takes_the_crop(
    tmp_path, route, pinned
):
    # A route registered for the first pass, with image input (HARNESS.md
    # section 5); any other stays unpinned, so the first-pass step blocks.
    run = Run(profile=Profile(first_pass_route=route))

    pins = production.ProductionAdapters(LocalBlobs(tmp_path)).pin_dependencies(run)

    routes = pins["routes"]
    assert set(routes) == {*run.profile.routes, *([route] * pinned)}
    if pinned:
        stage = HUGGINGFACE_ROUTES[route]
        assert routes[route] == {"model_id": stage.model_id, "provider": stage.provider}


ASSET = Asset(
    id="asset-1",
    sha256="0" * 64,
    blob_ref="label",
    media_type="image/png",
    size_bytes=1,
    width=9,
    height=9,
    filename="label.png",
    uploader="synthetic",
)


def first_pass_child(payload):
    """The isolated model child, spawned by name, with a fake first-pass provider."""
    from specimen_digitization.application import first_pass, workflow
    from specimen_digitization.application.model_runtime import model_child

    class Gateway:
        def __init__(self, timeout_seconds=None):
            self.routes = {ROUTE.route_id: ROUTE}

        def route(self, route_id):
            return self.routes[route_id]

        def model_for(self, route_id):
            def respond(messages, info):
                return ModelResponse(
                    parts=[ToolCallPart(info.output_tools[0].name, json.dumps(VALID))],
                    finish_reason="stop",
                )

            return FunctionModel(respond, model_name="fake-vision")

    first_pass.HuggingFaceModelGateway = Gateway
    workflow.crop_bytes = lambda *args: b"PNG"
    return model_child(payload)


def invoke_first_pass(tmp_path, readings, effect):
    run = Run(
        profile=Profile(first_pass_route=ROUTE.route_id), dependencies=DEPENDENCIES
    )
    return model_runtime.invoke_model(
        SimpleNamespace(blobs=LocalBlobs(tmp_path / "blobs"), model_effect=effect),
        SimpleNamespace(id="specimen-1", asset=ASSET, run=run),
        "first_pass",
        region=REGION,
        readings=readings,
    )


def test_the_first_pass_crosses_the_model_child_and_back(monkeypatch, tmp_path):
    # #97's closeout: the child refuses an operation its span allow-list lacks.
    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    readings = [reading("handwriting-qwen", QWEN), reading("handwriting-muse", MUSE)]

    decision = invoke_first_pass(tmp_path, readings, first_pass_child)

    assert decision.selected_observation_id == readings[1].id
    call = decision.call
    assert (call.route_id, call.input_asset_id) == (ROUTE.route_id, ASSET.id)
    assert call.completion_state == "validated_output"
    assert LocalBlobs(tmp_path / "blobs").get(call.input_crop_ref) == b"PNG"


@pytest.mark.parametrize(
    "field,value", [("route_id", "another-route"), ("input_asset_id", "asset-2")]
)
def test_a_call_returned_for_another_route_or_asset_is_refused(
    monkeypatch, tmp_path, field, value
):
    decision, readings = direct_first_pass(monkeypatch, tmp_path, [], VALID)
    call = decision.call.model_copy(update={field: value})
    forged = decision.model_copy(update={"call": call})
    body = {
        "status": "completed",
        "value": {"decision": forged.model_dump(mode="json")},
    }
    result = SimpleNamespace(
        status="completed", cleanup_complete=True, value=json.dumps(body).encode()
    )
    monkeypatch.setattr(model_runtime, "run_isolated", lambda *args, **kw: result)

    with pytest.raises(OperationalBlock, match="^external_outcome_unknown$"):
        invoke_first_pass(tmp_path, readings, None)


# Two or more readings: Nemotron as reader C (NVIDIA_NEMOTRON_OPTION.md 1).

from specimen_digitization.application.domain import FirstPassDifference  # noqa: E402
from specimen_digitization.application.first_pass import (  # noqa: E402
    g19_pick,
    reading_differences_among,
    supports,
    synthetic_decision,
)

THREE_ROUTES = ("handwriting-qwen", "handwriting-muse", "handwriting-nemotron")
# Reader C agrees with B on the taxon and with A on the capitalization.
READER_C = "VI-24-68-7\nEpipsocus\nsp.1\n♀ terminalia"


@pytest.mark.parametrize(
    "first,second",
    [(QWEN, MUSE), (COMPACT, SPACED), ("", "abc"), ("abc def", ""), ("Chicago, Ill.", "Chicago, Il1.")],
)
def test_two_readings_keep_the_pairwise_differences(first, second):
    assert reading_differences_among([first, second]) == reading_differences(first, second)


def test_the_request_for_two_readings_is_byte_for_byte_the_one_before_reader_c():
    # SHA-256 of the request first_pass_direct built for these readings at
    # origin/main 8f748c2f8, before the first pass took more than two readings.
    readings = [reading("handwriting-qwen", QWEN), reading("handwriting-muse", MUSE)]

    request, letters = build_request(readings, reading_differences_among([QWEN, MUSE]))

    assert list(letters) == ["A", "B"]
    assert hashlib.sha256(request.encode()).hexdigest() == (
        "b9757ca6d5000039cb137c906f831b81704c8d4837561714a2309f7d99353dc8"  # pragma: allowlist secret
    )


@pytest.mark.parametrize(
    "texts,expected",
    [
        # One reader dissents: one difference, the agreeing readers' text twice.
        (["Mt. Apo 1946", "Mt. Apo 1946", "Mt. Apa 1946"], [(("Apo", 4), ("Apo", 4), ("Apa", 4))]),
        # An insertion: empty spans where the others have nothing, each at the
        # offset where the inserted text would be.
        (["Davao Prov.", "Davao Prov.", "Davao, Prov."], [(("", 5), ("", 5), (",", 5))]),
        (["a c", "a c", "a b c"], [(("", 1), ("", 1), ("b", 2))]),
        # Differences in whitespace alone are no difference.
        (["E Slope, Elev. 6400", "ESlope, Elev.6400", "E Slope , Elev. 6400"], []),
        # An empty reading: one difference over the whole label.
        (["Mt. Apo", "Mt. Apo", ""], [(("Mt. Apo", 0), ("Mt. Apo", 0), ("", 0))]),
        (["", "Mt. Apo", "Mt. Apo"], [(("", 0), ("Mt. Apo", 0), ("Mt. Apo", 0))]),
        # Two readers' differences at different words stay two differences.
        (["a b c d", "a X c d", "a b Y d"], [(("b", 2), ("X", 2), ("b", 2)), (("c", 4), ("c", 4), ("Y", 4))]),
        # A block one reader replaces word by word is split where the alignments allow.
        (
            ["a b c d e", "a b X d e", "a Q R S e"],
            [(("b", 2), ("b", 2), ("Q", 2)), (("c", 4), ("X", 4), ("R", 4)), (("d", 6), ("d", 6), ("S", 6))],
        ),
        (
            [QWEN, MUSE, READER_C],
            [
                ((".", 10), ("", 10), ("", 10)),
                (("Epipocous", 12), ("Epipsocus", 11), ("Epipsocus", 11)),
                (("sp", 22), ("Sp", 21), ("sp", 21)),
            ],
        ),
    ],
    ids=[
        "one dissenter",
        "an inserted comma",
        "an inserted word",
        "whitespace alone",
        "an empty last reading",
        "an empty first reading",
        "two readers at two words",
        "a replaced block, word by word",
        "three readers of the pilot label",
    ],
)
def test_three_readings_give_one_exact_span_per_reading_per_difference(texts, expected):
    differences = reading_differences_among(texts)

    assert [tuple((span.text, span.start) for span in group) for group in differences] == expected
    for group in differences:
        assert len(group) == len(texts)
        for text, span in zip(texts, group):
            assert text[span.start : span.end] == span.text


def test_a_difference_grows_until_every_reader_is_aligned_at_its_ends():
    # Reader B replaces thirteen words, a block too long to align word by word
    # (reading_differences); reader C changes the seventh. No point inside B's
    # block is aligned with A, so the two make one difference.
    words = [f"w{n}" for n in range(1, 14)]
    first = " ".join(["x", *words, "y"])
    second = " ".join(["x", *(f"q{n}" for n in range(1, 14)), "y"])
    third = first.replace("w7", "R")

    differences = reading_differences_among([first, second, third])

    assert [tuple(span.text for span in group) for group in differences] == [
        (" ".join(words), second[2:-2], third[2:-2])
    ]
    # Without reader B, C's change is one word.
    assert [tuple(s.text for s in g) for g in reading_differences_among([first, first, third])] == [
        ("w7", "w7", "R")
    ]


def test_the_request_lists_every_reader_by_letter():
    readings = [reading(route, text) for route, text in zip(THREE_ROUTES, (QWEN, MUSE, READER_C))]

    request, letters = build_request(readings, reading_differences_among([QWEN, MUSE, READER_C]))

    assert list(letters) == ["A", "B", "C"] and letters["C"] is readings[2]
    assert "Reader C:\n<<<\n" + READER_C + "\n>>>" in request
    assert (
        '2. Reader A: "Epipocous" (in line "Epipocous") | Reader B: "Epipsocus" '
        '(in line "Epipsocus") | Reader C: "Epipsocus" (in line "Epipsocus")'
    ) in request
    assert "nemotron" not in request.lower()


def difference(spans, verdict):
    texts = dict(zip("ABC", spans))
    return FirstPassDifference(
        number=1,
        spans={key: ReadingSpan(start=0, end=len(text), text=text) for key, text in texts.items()},
        verdict=verdict,
        material=first_pass_module.is_material(
            [ReadingSpan(start=0, end=len(t), text=t) for t in texts.values()]
        ),
    )


@pytest.mark.parametrize("selected", ["A", "B", None])
@pytest.mark.parametrize("verdict", ["A", "B", "neither", "uncertain"])
@pytest.mark.parametrize("spans", [("Apo", "Apa"), ("sp", "Sp"), ("", ".")])
def test_with_two_readings_a_verdict_supports_only_the_reading_it_names(spans, verdict, selected):
    # The rule before reader C: a material difference whose verdict is not the
    # selected reading returns no reading.
    item = difference(spans, verdict)
    before = None if (item.verdict != selected and item.material) else selected

    assert g19_pick(selected, [item]) == before


@pytest.mark.parametrize(
    "spans,verdict,selected,expected",
    [
        # B and C read "Apo"; a verdict for B supports C's identical text.
        (("Apa", "Apo", "Apo"), "B", "C", "C"),
        (("Apa", "Apo", "Apo"), "C", "B", "B"),
        # Compared as materiality is: lower-cased.
        (("Apa", "APO", "apo"), "B", "C", "C"),
        (("Apa", "Apo", "Apo"), "A", "C", None),
        (("Apa", "Apo", "Apo"), "neither", "C", None),
        (("Apa", "Apo", "Apo"), "uncertain", "B", None),
        # An empty span is a text too: "" supports "" only.
        (("", ".", ""), "C", "A", "A"),
        (("", ".", ""), "B", "A", None),
        # No pick stays no pick.
        (("Apa", "Apo", "Apo"), "B", None, None),
    ],
)
def test_with_three_readings_a_verdict_supports_every_reading_with_its_text(
    spans, verdict, selected, expected
):
    item = difference(spans, verdict)

    assert supports(item, selected) is (expected is not None)
    assert g19_pick(selected, [item]) == expected


def test_capitalization_alone_never_blocks_a_pick_of_three():
    item = difference(("Sp", "sp", "SP"), "uncertain")

    assert not item.material and g19_pick("A", [item]) == "A"


@pytest.mark.parametrize(
    "verdicts,expected",
    [
        (["B", "B", "C"], "C"),  # Every material difference supports C's text.
        (["C", "C", "uncertain"], "C"),  # The third is capitalization alone.
        (["B", "A", "C"], None),  # At difference 2, A's text is not C's.
    ],
)
def test_the_first_pass_takes_three_readings_and_judges_each_reader_by_its_text(
    monkeypatch, tmp_path, verdicts, expected
):
    readings = [reading(route, text) for route, text in zip(THREE_ROUTES, (QWEN, MUSE, READER_C))]
    answer = {
        "selected_reader": "C",
        "verdicts": [{"number": n, "supported": s} for n, s in enumerate(verdicts, 1)],
        "rationale": "The image shows Epipsocus.",
        "reader_notes": {"A": "misread", "B": "close", "C": "matches"},
    }
    calls = []

    decision, _ = direct_first_pass(
        monkeypatch,
        tmp_path,
        calls,
        answer,
        readings=readings,
        profile=Profile(routes=THREE_ROUTES, first_pass_route=ROUTE.route_id),
    )

    ids = {letter: r.id for letter, r in zip("ABC", readings)}
    assert len(calls) == 1
    assert any("Reader C:" in str(part.content) for part in calls[0][0].parts)
    assert decision.selected_observation_id == ids.get(expected)
    assert decision.notes == {ids["A"]: "misread", ids["B"]: "close", ids["C"]: "matches"}
    assert [set(d.spans) for d in decision.differences] == [set(ids.values())] * 3
    assert [d.material for d in decision.differences] == [True, True, False]
    assert [d.verdict for d in decision.differences] == [ids.get(v, v) for v in verdicts]
    request, _ = build_request(readings, reading_differences_among([QWEN, MUSE, READER_C]))
    assert decision.call.request_sha256 == hashlib.sha256(request.encode()).hexdigest()


def test_the_first_pass_refuses_three_readings_out_of_route_order(monkeypatch, tmp_path):
    a, b, c = (reading(route, text) for route, text in zip(THREE_ROUTES, (QWEN, MUSE, READER_C)))

    with pytest.raises(OperationalBlock, match="^first_pass_contract_invalid$"):
        direct_first_pass(
            monkeypatch, tmp_path, [], VALID, readings=[a, c, b],
            profile=Profile(routes=THREE_ROUTES, first_pass_route=ROUTE.route_id),
        )


def test_two_of_three_readings_in_route_order_are_compared(monkeypatch, tmp_path):
    # Reader B gave up: A and C, still in route order, are the label's readings.
    a, c = reading(THREE_ROUTES[0], QWEN), reading(THREE_ROUTES[2], READER_C)
    answer = dict(VALID, verdicts=VALID["verdicts"][:2], reader_notes={"A": "a", "B": "b"})

    decision, _ = direct_first_pass(
        monkeypatch, tmp_path, [], answer, readings=[a, c],
        profile=Profile(routes=THREE_ROUTES, first_pass_route=ROUTE.route_id),
    )

    assert decision.selected_observation_id == c.id
    assert [set(d.spans) for d in decision.differences] == [{a.id, c.id}] * 2


def test_the_synthetic_first_pass_lists_every_reading_at_every_difference(tmp_path):
    readings = [reading(route, text) for route, text in zip(THREE_ROUTES, (QWEN, MUSE, READER_C))]

    decision = synthetic_decision(LocalBlobs(tmp_path), REGION, readings)

    assert decision.selected_observation_id is None
    assert [
        tuple(d.spans[r.id].text for r in readings) for d in decision.differences
    ] == [(".", "", ""), ("Epipocous", "Epipsocus", "Epipsocus"), ("sp", "Sp", "sp")]
    assert {d.verdict for d in decision.differences} == {"uncertain"}
    assert decision.notes == {r.id: "Synthetic fixture reading." for r in readings}
