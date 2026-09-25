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
from specimen_digitization.model_gateway import HuggingFaceInferenceRoute
from specimen_digitization.prompts import PromptName, ResolvedPrompt

QWEN = "VI-24-68-7.\nEpipocous\nsp.1\n♀ terminalia"
MUSE = "VI-24-68-7\nEpipsocus\nSp. 1\n♀ terminalia"
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


def test_first_pass_cost_reservation_is_one_key_for_every_region():
    reservations = StageCostReservations(
        version="stage-cost-reservations-v1", cost_micros={"first_pass": 900}
    )

    assert reservations.for_step("first_pass:region-7") == 900


ROUTE = HuggingFaceInferenceRoute("fp-test", "first_pass", "vendor/vision", "novita")
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


def direct_first_pass(
    monkeypatch,
    tmp_path,
    calls,
    *answers,
    readings=None,
    profile=None,
    dependencies=None,
    approved=True,
):
    """first_pass_direct against a fake provider that gives these answers in turn:
    an answer sent as its tool call, or a function of the output tool's name that
    returns the provider's whole response."""

    def respond(messages, info):
        calls.append(messages)
        answer = answers[min(len(calls), len(answers)) - 1]
        tool = info.output_tools[0].name
        if callable(answer):
            return answer(tool)
        return ModelResponse(
            parts=[ToolCallPart(tool, json.dumps(answer))], finish_reason="stop"
        )

    class Gateway:
        def __init__(self, timeout_seconds=None):
            self.routes = {ROUTE.route_id: ROUTE}

        def route(self, route_id):
            return self.routes[route_id]

        def model_for(self, route_id):
            return FunctionModel(respond, model_name="fake-vision")

    if approved:
        monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    else:
        monkeypatch.delenv("SPECIMEN_APPROVED_INFERENCE", raising=False)
    monkeypatch.setattr(first_pass_module, "HuggingFaceModelGateway", Gateway)
    monkeypatch.setattr(workflow_module, "crop_bytes", lambda *args: b"PNG")
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
        ({"count": 3}, "first_pass_reading_count_unsupported"),
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
    ],
    ids=[
        "no spending approval",
        "one reading",
        "three readings",
        "no first-pass route",
        "an unregistered route",
        "a route pinned to another provider",
        "no pinned prompt",
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
    calls = []

    with pytest.raises(OperationalBlock, match=f"^{code}$"):
        direct_first_pass(
            monkeypatch, tmp_path, calls, VALID, readings=readings, **change
        )

    assert calls == []


@pytest.mark.parametrize("registered", [True, False])
def test_pin_dependencies_pins_only_a_registered_first_pass_route(
    monkeypatch, tmp_path, registered
):
    if registered:
        routes = {**production.INITIAL_HUGGINGFACE_ROUTES, ROUTE.route_id: ROUTE}
        monkeypatch.setattr(production, "INITIAL_HUGGINGFACE_ROUTES", routes)
    run = Run(profile=Profile(first_pass_route=ROUTE.route_id))

    pins = production.ProductionAdapters(LocalBlobs(tmp_path)).pin_dependencies(run)

    routes = pins["routes"]
    assert set(routes) == {*run.profile.routes, *([ROUTE.route_id] * registered)}
    if registered:
        assert routes[ROUTE.route_id] == PINNED


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
