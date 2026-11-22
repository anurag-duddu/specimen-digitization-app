"""Literal, evidence-preserving specimen-label transcription agent."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai import Agent

from .application.reading_declarations import DeclarationCandidates
from .model_gateway import HuggingFaceModelGateway
from .provider_privacy import PrivateProviderModel, agent_instrumentation
from .prompts import PromptName, ResolvedPrompt

# The characters a reader may write, in `verbatim_text`, at the break between
# two of its `lines`: any run of them, of any length and mix, or none at all
# (_breaks_only). A newline is what the schema asks for. Novita's server for
# Qwen/Qwen3-VL-30B-A3B-Instruct (the handwriting-qwen route) has also written
# every break as a space (production, 2026-10-03 and 2026-10-11), as the
# newline symbol U+21B5 (production, 2026-10-11), as two spaces and as nothing,
# the lines run together (production, 2026-11-22 08:24Z to 09:04Z), with `lines`
# still split at each break. Before this rule (written 2026-11-22) exactly one
# of these characters was accepted at each break, and by the count of the
# autonomy program's coordinator in Logfire 15 of 104 reader runs were refused
# on 2026-11-20, 3 of 6 on 2026-11-21 and 12 of 40 on 2026-11-22. The twelve
# gave five distinct answers, two with two spaces at every break and three with
# nothing; the answers of the two earlier days were not among the evidence for
# this rule. tests/fixtures/qwen_reader_answers.json holds six answers of
# 2026-10-11 and the five of 2026-11-22. No answer in that file writes a tab or
# a carriage return at a break, so neither is a form.
LINE_BREAK_FORMS = frozenset({"\n", " ", "\u21b5"})
_BREAKS = "".join(sorted(LINE_BREAK_FORMS))
# The first character that is not a break form, or the end of the text.
_RUN_END = re.compile(f"[^{re.escape(_BREAKS)}]|\\Z")


def _breaks_only(text: str, lines: list[str]) -> bool:
    """Whether `text` is `lines` in order with only break forms between them.

    `text` must begin with the first line and end with the last, and between
    two lines there may stand any run of LINE_BREAK_FORMS characters, an empty
    run included, and nothing else. Every character of every line must be in
    `text`, in place and in order; the only freedom is how each break between
    two lines is written. A character changed, or any character that is not a
    break form added, dropped or moved, is refused. A line that is empty or
    holds only break forms cannot be told from a break: lines "a", "" and "b"
    are found in "ab", "a b" and "a  b" alike.

    The places where the next line may start are one stretch of `text`: from
    `low`, the leftmost place where the lines so far can end, to `high`, the
    end of the run of break forms that begins there. A line that holds a
    character that is not a break form can start at one place only: its
    leading break forms are the last of the run, because the first character
    that is not a break form stands at `high` (when `text` ends there, no such
    line fits). A line that is empty or holds break forms only lies inside the
    run, and its leftmost place there leaves every later place open to the
    lines after it; when it is the last line it must be the end of `text`
    instead.

    A run is walked to its end once: the next walk starts after the line that
    holds the character that ended it. Each line is compared with `text` once,
    at the one place it can be, except a line of break forms only that is not
    the last, which `str.find` looks for from `low` on. So apart from what
    `str.find` costs on such a line, the work is in proportion to the length
    of `text`, the lengths of the lines and their number.
    """
    if not text.startswith(lines[0]):
        return False
    low = len(lines[0])
    if len(lines) == 1:
        return low == len(text)
    high = _RUN_END.search(text, low).start()
    for index in range(1, len(lines)):
        line = lines[index]
        lead = len(line) - len(line.lstrip(_BREAKS))
        if lead < len(line):
            start = high - lead
            if start < low or not text.startswith(line, start):
                return False
            low = start + len(line)
            high = _RUN_END.search(text, low).start()
        elif index < len(lines) - 1:
            start = text.find(line, low, high)
            if start < 0:
                return False
            low = start + len(line)
        else:
            return (
                high == len(text)
                and len(text) - len(line) >= low
                and text.endswith(line)
            )
    return low == len(text)


class LiteralTranscription(DeclarationCandidates):
    """Faithful visual reading before any field normalization or enrichment."""

    model_config = ConfigDict(frozen=True)

    verbatim_text: str = Field(
        min_length=1,
        description=(
            "The whole transcription as one string: the entries of `lines` joined "
            "with a single newline character, with no other change."
        ),
    )
    lines: list[str] = Field(
        min_length=1,
        description=(
            "The same transcription split on newlines, one entry per line in "
            "reading order. Joining the entries with a single newline character "
            "must give `verbatim_text` exactly."
        ),
    )
    unreadable_spans: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def line_breaks_written_as_newlines(cls, data):
        """Write each break between `lines` as one newline in `verbatim_text`.

        An answer whose `verbatim_text` is its `lines` in order, with each
        break between two lines written as any run of LINE_BREAK_FORMS
        characters or as nothing (_breaks_only), is the same transcription;
        `verbatim_text` becomes the lines joined with single newlines, as the
        schema asks. Anything else is left as it came, for the exact rule
        below to judge.
        """
        if not isinstance(data, dict):
            return data
        text, lines = data.get("verbatim_text"), data.get("lines")
        if not (
            isinstance(text, str)
            and isinstance(lines, list)
            and lines
            and all(isinstance(line, str) for line in lines)
        ):
            return data
        joined = "\n".join(lines)
        if text != joined and _breaks_only(text, lines):
            return {**data, "verbatim_text": joined}
        return data

    @model_validator(mode="after")
    def lines_must_reconstruct_verbatim_text(self) -> LiteralTranscription:
        if "\n".join(self.lines) != self.verbatim_text:
            raise ValueError("lines must reconstruct verbatim_text exactly")
        return self


class LiteralTranscriptionRun(BaseModel):
    """Typed output plus the route and prompt evidence needed for replay."""

    model_config = ConfigDict(frozen=True)

    output: LiteralTranscription
    route_id: str
    model_id: str
    upstream_provider: str
    prompt_name: PromptName
    prompt_requested_label: str
    prompt_served_label: str | None
    prompt_version: int | None
    input_tokens: int
    output_tokens: int


def _agent_name(route_id: str) -> str:
    return f"literal_transcriber_{route_id.replace('-', '_')}"


def build_literal_transcription_agent(
    gateway: HuggingFaceModelGateway,
    *,
    route_id: str,
    prompt: ResolvedPrompt,
) -> Agent[None, LiteralTranscription]:
    """Build a stably named agent for the Logfire Agents view.

    The HTTP client's own timeout (httpx.TimeoutException, no TimeoutError) is
    made a TimeoutError beneath PrivateProviderModel, as the field experts'
    is (experts.ClientTimeouts), so run_agent_bounded reports it as a timeout
    and not as an unmapped provider failure."""
    from .field_research.experts import ClientTimeouts

    agent = Agent(
        PrivateProviderModel(ClientTimeouts(gateway.model_for(route_id))),
        name=_agent_name(route_id),
        output_type=LiteralTranscription,
        instructions=prompt.text,
    )
    # Prompt, messages and output follow the configured capture mode (G3);
    # the image bytes are never recorded.
    agent.instrument = agent_instrumentation()
    return agent
