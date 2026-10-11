"""A reader answer may write the breaks between its lines another way.

Every handwriting-qwen reading of run 0c7f52e1 (2026-10-11 14:05Z) failed as
`model_malformed_response`: Novita's Qwen/Qwen3-VL-30B-A3B-Instruct split
`lines` at each break but wrote each break in `verbatim_text` as a space, or as
the newline symbol U+21B5, and the exact line rule refused the answer and its
retry. The fixtures are those recorded answers, an earlier answer that wrote
newlines, and one whose text and lines differ in a word
(tests/fixtures/qwen_reader_answers.json). The replays go through the real
Hugging Face client on a mock transport: no test makes a network call.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx
import pytest
from huggingface_hub.hf_api import InferenceProviderMapping
from huggingface_hub.inference._providers._common import (
    HARDCODED_MODEL_INFERENCE_MAPPING,
)
from huggingface_hub.utils import _http as hf_http
from pydantic import ValidationError
from pydantic_ai import BinaryContent
from pydantic_ai.usage import UsageLimits

from specimen_digitization.application.domain import LookupStatus, Scope
from specimen_digitization.application.reliability import (
    AdapterFailure,
    run_agent_bounded,
)
from specimen_digitization.model_gateway import (
    INITIAL_HUGGINGFACE_ROUTES,
    HuggingFaceModelGateway,
)
from specimen_digitization.prompts import PromptName, ResolvedPrompt
from specimen_digitization.transcription import (
    LiteralTranscription,
    build_literal_transcription_agent,
)

ANSWERS = json.loads(
    (Path(__file__).parent / "fixtures" / "qwen_reader_answers.json").read_text()
)["answers"]
OTHER_BREAKS = ["space_joined_two_lines", "space_joined_six_lines", "newline_symbol"]
ROUTE = INITIAL_HUGGINGFACE_ROUTES["handwriting-qwen"]
PROMPT = ResolvedPrompt(
    name=PromptName.LITERAL_TRANSCRIPTION,
    text="Read the recorded fixture literally.",
    requested_label="offline",
    served_label=None,
    version=None,
    resolution_reason="code-default",
)


def recorded(name, index=0):
    return ANSWERS[name]["responses"][index]


def arguments(name, index=0):
    return json.loads(recorded(name, index)["arguments"])


@pytest.mark.parametrize("name", OTHER_BREAKS)
def test_recorded_answers_that_write_breaks_another_way_are_their_lines(name):
    for answer in ANSWERS[name]["responses"]:
        sent = json.loads(answer["arguments"])
        # The recorded answer itself breaks the exact rule.
        assert sent["verbatim_text"] != "\n".join(sent["lines"])

        output = LiteralTranscription.model_validate_json(answer["arguments"])

        assert output.lines == sent["lines"]
        assert output.verbatim_text == "\n".join(sent["lines"])


def test_recorded_answer_that_writes_newlines_is_unchanged():
    sent = arguments("newline_joined")
    output = LiteralTranscription.model_validate_json(
        recorded("newline_joined")["arguments"]
    )
    assert output.verbatim_text == sent["verbatim_text"]
    assert output.lines == sent["lines"]


def test_recorded_answer_whose_words_differ_is_still_refused():
    for answer in ANSWERS["words_differ"]["responses"]:
        with pytest.raises(ValidationError, match="reconstruct"):
            LiteralTranscription.model_validate_json(answer["arguments"])


def test_each_break_may_be_written_its_own_way():
    lines = arguments("space_joined_six_lines")["lines"]
    text = lines[0] + "\n" + lines[1] + "\u21b5" + " ".join(lines[2:])
    output = LiteralTranscription(verbatim_text=text, lines=lines)
    assert output.verbatim_text == "\n".join(lines)


def test_an_empty_line_has_a_break_on_each_side():
    # Exactly one character stands for each break between two lines, so two
    # spaces are accepted only where the lines have two breaks: around an
    # empty line. Two spaces at one break are refused (below).
    lines = ["FMNHINS", "", "4486779"]
    output = LiteralTranscription(verbatim_text="FMNHINS  4486779", lines=lines)
    assert output.verbatim_text == "FMNHINS\n\n4486779"


@pytest.mark.parametrize(
    ("lines", "text"),
    [
        # Two characters at a break.
        (["FMNHINS", "4486779"], "FMNHINS  4486779"),
        (["FMNHINS", "4486779"], "FMNHINS \n4486779"),
        # No break at all.
        (["FMNHINS", "4486779"], "FMNHINS4486779"),
        # A break written as a character that is not a break form.
        (["FMNHINS", "4486779"], "FMNHINS\t4486779"),
        (["FMNHINS", "4486779"], "FMNHINS-4486779"),
        # A character changed, added or dropped.
        (["FMNHINS", "4486779"], "FMNHINS 4486770"),
        (["FMNHINS", "4486779"], "FMNHINS 4486779 "),
        (["FMNHINS", "4486779"], " FMNHINS 4486779"),
        (["FMNHINS", "4486779"], "FMNHINS"),
        (["FMNHINS", "4486779"], "FMNHINS 4486779 4486779"),
        # A break where the lines have none.
        (["FMNHINS 4486779"], "FMNHINS\n4486779"),
        (["FMNHINS 4486779"], "FMNHINS\u21b54486779"),
        # Lines out of order.
        (["FMNHINS", "4486779"], "4486779 FMNHINS"),
    ],
)
def test_text_that_is_not_its_lines_is_still_refused(lines, text):
    with pytest.raises(ValidationError, match="reconstruct"):
        LiteralTranscription(verbatim_text=text, lines=lines)


def test_the_schema_the_reader_is_sent_is_unchanged():
    # The fix is in how an answer is read, not in what the reader is asked:
    # the readers' tool schema and the lane's byte count of it
    # (lane_reservations.reading_prompt_tokens) are those of main at 5332ce4e.
    schema = json.dumps(LiteralTranscription.model_json_schema(), sort_keys=True)
    at_main = "b08ca6f46c8c52acfe768048673b3b4e01cc09caf87284abe096f9d0c6596639"  # pragma: allowlist secret
    assert hashlib.sha256(schema.encode()).hexdigest() == at_main


def replay(monkeypatch, responses):
    """Answer each chat request with the next recorded answer, as the provider did."""
    monkeypatch.setitem(
        HARDCODED_MODEL_INFERENCE_MAPPING,
        ROUTE.provider,
        {
            ROUTE.model_id: InferenceProviderMapping(
                provider=ROUTE.provider,
                hf_model_id=ROUTE.model_id,
                providerId=ROUTE.model_id,
                status="live",
                task="conversational",
            )
        },
    )
    sent = []

    def handler(request):
        assert request.url.path.endswith("/chat/completions")
        payload = json.loads(request.content)
        sent.append(payload)
        answer = responses[len(sent) - 1]
        return httpx.Response(
            200,
            json={
                "id": answer["response_id"],
                "object": "chat.completion",
                "created": 0,
                "model": answer["response_model"],
                "choices": [
                    {
                        "index": 0,
                        # "tool_calls" on the wire; Logfire records Pydantic
                        # AI's name for it, "tool_call".
                        "finish_reason": "tool_calls",
                        "logprobs": None,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": answer["tool_call_id"],
                                    "type": "function",
                                    "function": {
                                        "name": payload["tools"][0]["function"][
                                            "name"
                                        ],
                                        "arguments": answer["arguments"],
                                    },
                                }
                            ],
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": answer["input_tokens"],
                    "completion_tokens": answer["output_tokens"],
                    "total_tokens": answer["input_tokens"] + answer["output_tokens"],
                },
            },
        )

    monkeypatch.setattr(
        hf_http,
        "_GLOBAL_ASYNC_CLIENT_FACTORY",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return sent


def read(monkeypatch, name):
    sent = replay(monkeypatch, ANSWERS[name]["responses"])
    agent = build_literal_transcription_agent(
        HuggingFaceModelGateway(token="hf_synthetic_offline"),
        route_id=ROUTE.route_id,
        prompt=PROMPT,
    )
    try:
        # The reader's own call: production.py's limits, through the same bound.
        return run_agent_bounded(
            agent,
            [
                "Transcribe only the supplied source image.",
                BinaryContent(data=b"recorded answer replay", media_type="image/png"),
            ],
            timeout_seconds=60,
            usage_limits=UsageLimits(request_limit=2, total_tokens_limit=16000),
        ), sent
    finally:
        assert len(sent) <= len(ANSWERS[name]["responses"])


@pytest.mark.parametrize("name", OTHER_BREAKS)
def test_reader_call_accepts_the_recorded_answer_at_once(monkeypatch, name):
    result, sent = read(monkeypatch, name)

    lines = arguments(name)["lines"]
    assert result.output.lines == lines
    assert result.output.verbatim_text == "\n".join(lines)
    # The first answer was valid: no output retry was asked for or paid.
    assert len(sent) == 1
    # The provider's own answer is kept as it was sent.
    response = [m for m in result.all_messages() if m.kind == "response"][-1]
    assert response.parts[0].args == recorded(name)["arguments"]


def test_reader_call_accepts_an_answer_that_writes_newlines(monkeypatch):
    result, sent = read(monkeypatch, "newline_joined")
    assert result.output.verbatim_text == arguments("newline_joined")["verbatim_text"]
    assert len(sent) == 1


def test_reader_call_refuses_an_answer_whose_words_differ(monkeypatch):
    with pytest.raises(AdapterFailure) as failure:
        read(monkeypatch, "words_differ")
    assert failure.value.code == "model_malformed_response"
    assert failure.value.status == LookupStatus.MALFORMED
    assert failure.value.outcome_unknown is False


@pytest.mark.parametrize("name", [*OTHER_BREAKS, "newline_joined", "words_differ"])
def test_production_reader_keeps_the_answer_and_records_its_lines(
    tmp_path, monkeypatch, name
):
    """ProductionAdapters._transcribe_direct, the reader the worker's child runs."""
    from specimen_digitization.application.production import ProductionAdapters
    from specimen_digitization.application.reading_declarations import (
        effective_declarations,
    )
    from specimen_digitization.application.storage import LocalBlobs, SQLiteRepository
    from test_application import SYNTHETIC_COLLECTION, SYNTHETIC_ORG, client, intake

    monkeypatch.setenv("SPECIMEN_APPROVED_INFERENCE", "true")
    monkeypatch.setenv("HF_TOKEN", "hf_synthetic_offline")
    monkeypatch.delenv("HF_BILL_TO", raising=False)
    row = intake(client(tmp_path))
    specimen = SQLiteRepository(tmp_path / "state.sqlite3").get(
        Scope(organization_id=SYNTHETIC_ORG, collection_id=SYNTHETIC_COLLECTION),
        row["specimen_id"],
    )
    blobs = LocalBlobs(tmp_path / "blobs")
    adapter = ProductionAdapters(blobs)
    specimen.run.dependencies = adapter.pin_dependencies(specimen.run)
    region = specimen.run.regions[0]
    sent = replay(monkeypatch, ANSWERS[name]["responses"])

    if name == "words_differ":
        with pytest.raises(AdapterFailure) as failure:
            adapter._transcribe_direct(specimen, region, ROUTE.route_id)
        assert failure.value.code == "model_malformed_response"
        assert len(sent) == 2
        return

    observation = adapter._transcribe_direct(specimen, region, ROUTE.route_id)

    lines = arguments(name)["lines"]
    assert observation.literal_text == "\n".join(lines)
    assert (observation.route_id, observation.provider) == (
        ROUTE.route_id,
        ROUTE.provider,
    )
    assert len(sent) == 1
    # The stored raw response is the provider's answer as it was sent.
    raw = json.loads(blobs.get(observation.raw_ref))
    assert raw[-1]["parts"][0]["args"] == recorded(name)["arguments"]
    assert raw[-1]["provider_response_id"] == recorded(name)["response_id"]
    # Reading the stored raw answer again by the reader's contract gives the
    # observation's text: the rewrite is reproducible from what is retained.
    again = LiteralTranscription.model_validate_json(raw[-1]["parts"][0]["args"])
    assert again.verbatim_text == observation.literal_text
    # The declaration evidence agrees with the observation's text, so its
    # provenance check passes.
    effective_declarations(specimen, observation, blobs)
