"""A reader answer may write the breaks between its lines another way.

Every handwriting-qwen reading of run 0c7f52e1 (2026-10-11 14:05Z) failed as
`model_malformed_response`: Novita's Qwen/Qwen3-VL-30B-A3B-Instruct split
`lines` at each break but wrote each break in `verbatim_text` as a space, or as
the newline symbol U+21B5, and the exact line rule refused the answer and its
retry. The fixtures are those recorded answers, an earlier answer that wrote
newlines, and one whose text and lines differ in a word
(tests/fixtures/qwen_reader_answers.json). The replays go through the real
Hugging Face client on a mock transport: no test makes a network call.

On 2026-11-22 (08:24Z to 09:04Z) the same server wrote each break as two
spaces, or as nothing (the lines run together), with `lines` still split at
each break, and twelve reader runs were refused: five distinct answers, held
under `refused_20261122` in the same fixture file with the two fields, trace id
and time the autonomy program's coordinator read from Logfire. A break may now
be any run of the break forms, an empty run included; the tests from
`sent_arguments` down are that rule's. The search that applies the rule is
compared with the set-based search it replaced (`set_based_search`, kept here
as its oracle) and that with the rule as a regular expression.
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
    LINE_BREAK_FORMS,
    LiteralTranscription,
    _breaks_only,
    build_literal_transcription_agent,
)

ANSWERS = json.loads(
    (Path(__file__).parent / "fixtures" / "qwen_reader_answers.json").read_text()
)["answers"]
OTHER_BREAKS = ["space_joined_two_lines", "space_joined_six_lines", "newline_symbol"]
REFUSED = json.loads(
    (Path(__file__).parent / "fixtures" / "qwen_reader_answers.json").read_text()
)["refused_20261122"]["answers"]
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
    # The two spaces are the two breaks around the empty line, which stays a
    # line: the answer is read as its three lines.
    lines = ["FMNHINS", "", "4486779"]
    output = LiteralTranscription(verbatim_text="FMNHINS  4486779", lines=lines)
    assert output.verbatim_text == "FMNHINS\n\n4486779"


@pytest.mark.parametrize(
    ("lines", "text"),
    [
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


def sent_arguments(name):
    """The tool call arguments of an answer refused on 2026-11-22, rebuilt
    from the two fields that were recorded."""
    answer = REFUSED[name]
    return json.dumps(
        {"lines": answer["lines"], "verbatim_text": answer["verbatim_text"]},
        ensure_ascii=False,
    )


def both_attempts(name):
    """A refused run of 2026-11-22 as the provider answered it: the same answer
    to the call and to the output retry. Everything around the arguments is
    synthetic: the envelope was not recorded."""
    return {
        "responses": [
            {
                "response_id": f"synthetic-response-{attempt}",
                "response_model": "qwen/qwen3-vl-30b-a3b-instruct",
                "tool_call_id": f"synthetic-call-{attempt}",
                "arguments": sent_arguments(name),
                "input_tokens": 10,
                "output_tokens": 5,
            }
            for attempt in (1, 2)
        ]
    }


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_answers_refused_on_2026_11_22_are_their_lines(name):
    lines, text = REFUSED[name]["lines"], REFUSED[name]["verbatim_text"]
    # The answer writes every break the way its entry says, so it breaks the
    # exact rule.
    written = "" if name.startswith("nothing") else "  "
    assert text == written.join(lines) != "\n".join(lines)

    output = LiteralTranscription.model_validate_json(sent_arguments(name))

    assert output.lines == lines
    assert output.verbatim_text == "\n".join(lines)


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_reader_call_accepts_an_answer_refused_on_2026_11_22_at_once(
    monkeypatch, name
):
    monkeypatch.setitem(ANSWERS, name, both_attempts(name))

    result, sent = read(monkeypatch, name)

    assert result.output.lines == REFUSED[name]["lines"]
    assert result.output.verbatim_text == "\n".join(REFUSED[name]["lines"])
    # In production the first answer was refused and the retry gave it again.
    assert len(sent) == 1
    response = [m for m in result.all_messages() if m.kind == "response"][-1]
    assert response.parts[0].args == sent_arguments(name)


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_production_reader_records_an_answer_refused_on_2026_11_22(
    tmp_path, monkeypatch, name
):
    """The checks made of the 2026-10-11 answers, on these: the observation's
    text is the lines joined with newlines, the stored raw response is the
    answer as sent, and the declaration evidence agrees with the observation
    (reading_declarations.effective_declarations)."""
    monkeypatch.setitem(ANSWERS, name, both_attempts(name))

    test_production_reader_keeps_the_answer_and_records_its_lines(
        tmp_path, monkeypatch, name
    )


@pytest.mark.parametrize(
    ("lines", "text"),
    [
        # Refused until this rule: two characters at one break, and no break.
        (["FMNHINS", "4486779"], "FMNHINS  4486779"),
        (["FMNHINS", "4486779"], "FMNHINS \n4486779"),
        (["FMNHINS", "4486779"], "FMNHINS4486779"),
        # A longer run, and one of all three forms.
        (["FMNHINS", "4486779"], "FMNHINS\n\n\n4486779"),
        (["FMNHINS", "4486779"], "FMNHINS \u21b5\n 4486779"),
    ],
)
def test_a_break_may_be_any_run_of_the_forms_or_nothing(lines, text):
    output = LiteralTranscription(verbatim_text=text, lines=lines)
    assert output.lines == lines
    assert output.verbatim_text == "\n".join(lines)


def test_one_answer_may_write_its_breaks_as_a_space_nothing_and_a_newline():
    lines = REFUSED["nothing_eight_lines"]["lines"]
    text = (
        lines[0]
        + " "
        + lines[1]
        + lines[2]
        + "\n"
        + lines[3]
        + "  "
        + lines[4]
        + "\u21b5"
        + lines[5]
        + " \n"
        + lines[6]
        + lines[7]
    )
    output = LiteralTranscription(verbatim_text=text, lines=lines)
    assert output.lines == lines
    assert output.verbatim_text == "\n".join(lines)


@pytest.mark.parametrize(
    ("lines", "text"),
    [
        # A line that begins with a space: the break written as nothing, then
        # as one space. A scan that takes every space for the break finds no
        # second line in the first.
        (["Sp 22", " genitalia"], "Sp 22 genitalia"),
        (["Sp 22", " genitalia"], "Sp 22  genitalia"),
        # A line that ends with a space: the same two.
        (["Sp 22 ", "genitalia"], "Sp 22 genitalia"),
        (["Sp 22 ", "genitalia"], "Sp 22  genitalia"),
        # Both at one break.
        (["Sp 22 ", " genitalia"], "Sp 22  genitalia"),
        (["Sp 22 ", " genitalia"], "Sp 22   genitalia"),
        # A line that is only a space, between two lines and last. Last, with
        # the break a space, a scan that places each line at the first place
        # it fits ends one character short.
        (["Sp 22", " ", "genitalia"], "Sp 22 genitalia"),
        (["Sp 22", " "], "Sp 22 "),
        (["Sp 22", " "], "Sp 22  "),
        # An empty line first or last: the run beside it is its break.
        (["", "Sp 22"], "  Sp 22"),
        (["Sp 22", ""], "Sp 22  "),
        # An empty line cannot be told from a break, so it needs no character.
        (["Sp 22", "", "genitalia"], "Sp 22genitalia"),
        (["Sp 22", "genitalia", ""], "Sp 22 genitalia"),
    ],
)
def test_a_line_that_begins_or_ends_with_a_space_is_matched_exactly(lines, text):
    output = LiteralTranscription(verbatim_text=text, lines=lines)
    # The spaces stay in the lines they are in.
    assert output.lines == lines
    assert output.verbatim_text == "\n".join(lines)


SP_22 = ["Sp 22", "\u2642 genitalia"]  # refused_20261122: nothing_two_lines


@pytest.mark.parametrize(
    ("lines", "text"),
    [
        # A character changed inside a line, the break written as nothing and
        # as two spaces.
        (SP_22, "Sp 23\u2642 genitalia"),
        (SP_22, "Sp 22\u2642 genitalla"),
        (SP_22, "Sp 22  \u2640 genitalia"),
        (SP_22, "sp 22  \u2642 genitalia"),
        # A line's own space missing, or written as another break form.
        (["Sp 22", " genitalia"], "Sp 22genitalia"),
        (["Sp 22 ", "genitalia"], "Sp 22genitalia"),
        (["Sp 22", " genitalia"], "Sp 22\ngenitalia"),
        (SP_22, "Sp\n22\u2642\ngenitalia"),
        # A line dropped: from the text, from the lines.
        (SP_22, "Sp 22"),
        (SP_22, "\u2642 genitalia"),
        (["Sp 22"], "Sp 22\u2642 genitalia"),
        (["\u2642 genitalia"], "Sp 22  \u2642 genitalia"),
        # A line added: to the text, to the lines.
        (SP_22, "Sp 22\u2642 genitaliaFMNH"),
        (SP_22, "Sp 22  FMNH  \u2642 genitalia"),
        ([*SP_22, "FMNH"], "Sp 22\u2642 genitalia"),
        (["Sp 22", "FMNH", "\u2642 genitalia"], "Sp 22  \u2642 genitalia"),
        # Lines out of order.
        (SP_22, "\u2642 genitaliaSp 22"),
        (SP_22, "\u2642 genitalia  Sp 22"),
        # Text before the first line or after the last, a break form included.
        (SP_22, "FMNHSp 22\u2642 genitalia"),
        (SP_22, " Sp 22\u2642 genitalia"),
        (SP_22, "\nSp 22  \u2642 genitalia"),
        (SP_22, "Sp 22\u2642 genitalia "),
        (SP_22, "Sp 22  \u2642 genitalia\n"),
        (SP_22, "Sp 22\u2642 genitalia\u21b5"),
        # A character between two lines that is not a break form, alone and
        # inside a run of break forms. No answer in the fixture writes a tab or
        # a carriage return at a break, so neither is a form.
        (SP_22, "Sp 22\t\u2642 genitalia"),
        (SP_22, "Sp 22\r\u2642 genitalia"),
        (SP_22, "Sp 22\r\n\u2642 genitalia"),
        (SP_22, "Sp 22 \t \u2642 genitalia"),
        (SP_22, "Sp 22 / \u2642 genitalia"),
        (SP_22, "Sp 22\u00a0\u2642 genitalia"),
        (SP_22, "Sp 22\\n\u2642 genitalia"),
    ],
)
def test_text_that_is_not_its_lines_is_refused_however_breaks_are_written(lines, text):
    with pytest.raises(ValidationError, match="reconstruct"):
        LiteralTranscription(verbatim_text=text, lines=lines)


def test_an_answer_with_no_lines_is_still_refused():
    with pytest.raises(ValidationError, match="at least 1 item"):
        LiteralTranscription(verbatim_text="Sp 22\u2642 genitalia", lines=[])


def set_based_search(text, lines):
    """The search of this change's first head (8b1b1318), kept as it was: the
    oracle of the search in use. It follows every place where the lines read
    so far can end, so it tries no shortcut, and it costs a pass over the
    reachable places for each line."""
    ends = {len(lines[0])} if text.startswith(lines[0]) else set()
    for line in lines[1:]:
        # Every place the next line may start: where a line can end, and each
        # place after it that only break forms lead to. A walk stops at a place
        # an earlier walk reached, which went on from there to the run's end.
        starts: set[int] = set()
        for position in ends:
            while position not in starts:
                starts.add(position)
                if text[position : position + 1] in LINE_BREAK_FORMS:
                    position += 1
        ends = {
            start + len(line) for start in starts if text.startswith(line, start)
        }
    return len(text) in ends


def test_the_searches_agree_with_the_rule_on_every_small_answer():
    """The rule as a regular expression (the lines in order, any run of the
    break forms between two, nothing else) against the set-based search, and
    the set-based search against the search in use, for every answer of up to
    three lines of up to two characters and every text of up to five, over a
    letter and two break forms."""
    import itertools
    import re

    def strings(longest):
        return [
            "".join(letters)
            for length in range(longest + 1)
            for letters in itertools.product("a \n", repeat=length)
        ]

    run = "[" + "".join(re.escape(form) for form in sorted(LINE_BREAK_FORMS)) + "]*"
    texts = strings(5)
    compared = 0
    for count in (1, 2, 3):
        for lines in itertools.product(strings(2), repeat=count):
            rule = re.compile(run.join(re.escape(line) for line in lines))
            for text in texts:
                expected = bool(rule.fullmatch(text))
                assert set_based_search(text, list(lines)) == expected, (lines, text)
                assert _breaks_only(text, list(lines)) == expected, (lines, text)
                compared += 1
    assert compared == (13 + 13**2 + 13**3) * 364


def random_answer(rng):
    """A text and lines over two letters and the three break forms. The lines:
    empty ones, ones of break forms only, ones that begin or end with break
    forms, a line repeated, a line the next one begins with, one line alone.
    The text: the lines with a random run at each break, that with one or two
    edits, or random characters."""
    breaks = "".join(sorted(LINE_BREAK_FORMS))

    def some(alphabet, least, most):
        return "".join(
            rng.choice(alphabet) for _ in range(rng.randint(least, most))
        )

    def a_line():
        kind = rng.random()
        if kind < 0.15:
            return ""
        if kind < 0.35:
            return some(breaks, 1, 3)
        before = some(breaks, 1, 2) if rng.random() < 0.3 else ""
        after = some(breaks, 1, 2) if rng.random() < 0.3 else ""
        return before + some("ab", 1, 3) + some("ab" + breaks, 0, 2) + after

    lines = [a_line()]
    for _ in range(rng.choice((0, 0, 1, 1, 2, 2, 3, 4, 5))):
        kind = rng.random()
        if kind < 0.15:
            lines.append(lines[-1])
        elif kind < 0.3:
            lines.append(lines[-1] + a_line())
        else:
            lines.append(a_line())
    kind = rng.random()
    if kind >= 0.85:
        return some("ab" + breaks, 0, 12), lines
    text = lines[0]
    for line in lines[1:]:
        text += (some(breaks, 1, 3) if rng.random() < 0.7 else "") + line
    if kind >= 0.45:
        for _ in range(rng.randint(1, 2)):
            at = rng.randint(0, len(text))
            edit, other = rng.choice("idr"), rng.choice("ab\t" + breaks)
            if edit == "i":
                text = text[:at] + other + text[at:]
            elif edit == "d":
                text = text[:at] + text[at + 1 :]
            else:
                text = text[:at] + other + text[at + 1 :]
    return text, lines


def test_the_search_agrees_with_the_set_based_search_on_random_answers():
    import random

    rng = random.Random(465)
    accepted = 0
    for _ in range(20_000):
        text, lines = random_answer(rng)
        expected = set_based_search(text, lines)
        assert _breaks_only(text, lines) == expected, (lines, text)
        accepted += expected
    # Both outcomes are well represented.
    assert 4_000 < accepted < 16_000


def test_the_search_agrees_with_the_set_based_search_on_every_fixture_answer():
    answers = [
        json.loads(response["arguments"])
        for answer in ANSWERS.values()
        for response in answer["responses"]
    ] + list(REFUSED.values())
    assert len(answers) == 14
    accepted = 0
    for answer in answers:
        text, lines = answer["verbatim_text"], answer["lines"]
        expected = set_based_search(text, lines)
        assert _breaks_only(text, lines) == expected, (lines, text)
        accepted += expected
    # Every one but the two answers whose words differ and the one already
    # written with newlines, which is its lines too.
    assert accepted == 12


class Asked:
    """What a search asks of a text: one for each call, and one for each
    character the call may read. Past `most` it stops the search, so a search
    that asks too much fails at once and does not run on."""

    def __init__(self, most=None):
        self.count, self.most = 0, most

    def more(self, asked):
        self.count += asked
        if self.most is not None and self.count > self.most:
            raise AssertionError(f"asked {self.count}, more than {self.most}")


class CountedText(str):
    """A text that counts the `startswith`, `endswith` and `find` calls made on
    it. A slice of it is a plain string and is not counted."""

    asked: Asked

    def startswith(self, prefix, start=0):
        self.asked.more(1 + len(prefix))
        return str.startswith(self, prefix, start)

    def endswith(self, suffix):
        self.asked.more(1 + len(suffix))
        return str.endswith(self, suffix)

    def find(self, sub, start, end):
        found = str.find(self, sub, start, end)
        searched = found - start + len(sub) if found >= 0 else end - start
        self.asked.more(1 + searched)
        return found


class CountedRunEnd:
    """transcription._RUN_END, counting the characters each search walks."""

    def __init__(self, pattern, asked):
        self.pattern, self.asked = pattern, asked

    def search(self, text, start):
        found = self.pattern.search(text, start)
        self.asked.more(1 + found.start() - start)
        return found


def asked_of(search, monkeypatch, text, lines, most=None):
    import specimen_digitization.transcription as transcription

    asked = Asked(most)
    counted = CountedText(text)
    counted.asked = asked
    with monkeypatch.context() as patch:
        if hasattr(transcription, "_RUN_END"):
            patch.setattr(
                transcription,
                "_RUN_END",
                CountedRunEnd(transcription._RUN_END, asked),
            )
        accepted = search(counted, lines)
    return accepted, asked.count


def degenerate_answers(size):
    """Answers whose lines are empty or hold break forms only, and one of
    ordinary lines with two spaces at each break: each is accepted, and with
    one more character at the end of its text each is refused."""
    return [
        ([""] * size, " " * size),
        ([" " * 50] * (size // 50), " " * size),
        (["\n"] * (size // 50), "\n" + (" " * 49 + "\n") * (size // 50 - 1)),
        (["Sp 22"] * (size // 10), "  ".join(["Sp 22"] * (size // 10))),
    ]


@pytest.mark.parametrize("size", [900, 9_000, 90_000])
def test_the_search_asks_of_a_text_in_proportion_to_its_length(monkeypatch, size):
    # A count of what is asked of the text, not a time: the same on a loaded
    # machine. Twice the answer's size is the most the search may ask: it
    # walks each run once and compares or looks for each line once.
    for lines, text in degenerate_answers(size):
        most = 2 * (len(text) + 1 + sum(len(line) for line in lines) + len(lines))
        accepted, asked = asked_of(_breaks_only, monkeypatch, text, lines, most)
        assert accepted and asked <= most, (size, lines[0], asked, most)
        accepted, asked = asked_of(_breaks_only, monkeypatch, text + "x", lines, most)
        assert not accepted and asked <= most, (size, lines[0], asked, most)


def test_the_set_based_search_asks_far_more_of_a_text_with_empty_lines(monkeypatch):
    # What the count above is there to refuse: on 900 empty lines against 900
    # spaces (3,630 bytes as compact JSON) the set-based search compares every
    # line at every place.
    lines, text = [""] * 900, " " * 900
    accepted, asked = asked_of(set_based_search, monkeypatch, text, lines)
    assert accepted and asked >= 899 * 901
    accepted, asked = asked_of(_breaks_only, monkeypatch, text, lines)
    assert accepted and asked <= 2 * (len(text) + 1 + len(lines))


def test_an_answer_of_empty_lines_and_spaces_is_its_lines():
    output = LiteralTranscription(verbatim_text=" " * 900, lines=[""] * 900)
    assert output.verbatim_text == "\n" * 899
