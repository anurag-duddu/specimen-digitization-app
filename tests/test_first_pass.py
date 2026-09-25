"""The LLM first-pass call (stage 6): docs/execution/golive/HARNESS.md section 3."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from specimen_digitization.application import first_pass as first_pass_module
from specimen_digitization.application import workflow as workflow_module
from specimen_digitization.application.domain import (
    LookupStatus,
    Observation,
    Profile,
    Region,
    Run,
    StageCostReservations,
)
from specimen_digitization.application.first_pass import (
    FirstPassOutput,
    build_request,
    output_problems,
    reading_differences,
)
from specimen_digitization.application.reliability import AdapterFailure
from specimen_digitization.application.storage import LocalBlobs
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


def test_output_problems_demand_one_verdict_per_difference_and_known_letters():
    output = FirstPassOutput(
        selected_reader="C",
        verdicts=[{"number": 1, "supported": "B", "material": True}],
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
        {"number": 1, "supported": "uncertain", "material": True},
        {"number": 2, "supported": "B", "material": True},
        {"number": 3, "supported": "B", "material": False},
    ],
    "rationale": "The image shows Epipsocus.",
    "reader_notes": {"A": "misread", "B": "matches"},
}
INCOMPLETE = dict(VALID, verdicts=VALID["verdicts"][:1])


def direct_first_pass(monkeypatch, tmp_path, calls, *answers, settings=None):
    """first_pass_direct against a fake provider that gives these answers in turn;
    `settings` collects each request's model settings."""

    def respond(messages, info):
        calls.append(messages)
        if settings is not None:
            settings.append(info.model_settings)
        answer = answers[min(len(calls), len(answers)) - 1]
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, json.dumps(answer))],
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
    pinned = {"model_id": ROUTE.model_id, "provider": ROUTE.provider}
    run = Run(
        profile=Profile(first_pass_route=ROUTE.route_id),
        dependencies={
            "routes": {ROUTE.route_id: pinned},
            "prompts": {PROMPT.name.value: PROMPT.model_dump(mode="json")},
        },
    )
    readings = [reading("handwriting-qwen", QWEN), reading("handwriting-muse", MUSE)]
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
    assert [(d.number, d.verdict, d.material) for d in decision.differences] == [
        (1, "uncertain", True),
        (2, second.id, True),
        (3, second.id, False),
    ]
    assert decision.differences[1].spans[first.id].text == "Epipocous"
    call = decision.call
    assert (call.route_id, call.model_id) == (ROUTE.route_id, ROUTE.model_id)
    assert call.literal_text == "" and call.completion_state == "validated_output"
    assert (call.finish_state, call.provider_model_id) == ("stop", "fake-vision")
    assert call.prompt_version == hashlib.sha256(PROMPT.text.encode()).hexdigest()
    raw = json.loads(LocalBlobs(tmp_path).get(call.raw_ref))
    assert raw[-1]["model_name"] == call.provider_model_id
    assert len(calls) == 1 and calls[0][0].instructions == PROMPT.text
    assert any("Reader A:" in str(part.content) for part in calls[0][0].parts)


def test_an_incomplete_answer_is_retried_once_with_the_problem(monkeypatch, tmp_path):
    calls = []
    decision, _ = direct_first_pass(monkeypatch, tmp_path, calls, INCOMPLETE, VALID)

    assert len(calls) == 2 and decision.rationale == VALID["rationale"]
    retry = calls[1][-1].parts[-1]
    assert retry.content == "give exactly one verdict for each difference 1 to 3"


def test_every_first_pass_request_is_capped_at_its_measured_output_budget(
    monkeypatch, tmp_path
):
    # G30: each request reserves its worst case; T1's first passes used at most
    # 406 output tokens.
    settings = []

    direct_first_pass(monkeypatch, tmp_path, [], INCOMPLETE, VALID, settings=settings)

    assert [s["max_tokens"] for s in settings] == [1024, 1024]
    assert first_pass_module.MAX_OUTPUT_TOKENS == 1024


def test_an_answer_that_stays_invalid_is_a_known_malformed_response(
    monkeypatch, tmp_path
):
    calls = []
    with pytest.raises(AdapterFailure) as failure:
        direct_first_pass(monkeypatch, tmp_path, calls, INCOMPLETE)

    assert len(calls) == 2
    assert failure.value.status == LookupStatus.MALFORMED
    assert failure.value.outcome_unknown is False
