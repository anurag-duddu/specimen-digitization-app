"""The LLM first pass (stage 6): which reader's raw transcript it prefers.

In the owner's words (docs/execution/golive/PLAN.md section 1): "LLM does first
pass at which final RAW transcript should run against (it should also give at a
VLM level what was returned to the harness)". It never writes text: the decided
transcript is the selected reading verbatim. Since 2026-10-25 its pick is advice
to the field harness, which may settle a field on any reader's text: "There an
LLM opinion that's put in front along with actual Raw transcription per model to
the harness if needed as then harness does its thing per field and settles as
written or derived and so on" (the owner). Spec: docs/execution/golive/HARNESS.md
section 3.

first_pass_units_direct, below, is the units path's call (docs/execution/units/PLAN.md,
WP 1.2).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import string
import time
from types import SimpleNamespace

from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic_ai import Agent, BinaryContent, ModelRetry
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.usage import UsageLimits

from ..model_gateway import HuggingFaceModelGateway
from ..prompts import PromptName, ResolvedPrompt
from ..provider_privacy import PrivateProviderModel
from .domain import (
    MANDATORY,
    FirstPassDecision,
    FirstPassDifference,
    Observation,
    ReaderHandoff,
    ReadingSpan,
    RunFinding,
)
from .reading_units import (  # noqa: F401 - OLD, SETTING, first_pass_path: the path's names here too
    NOT_VISIBLE,
    OLD,
    SETTING,
    UNCERTAIN,
    UNITS,
    first_pass_path,
    ReadingUnit,
    ReadingUnits,
    UnitText,
    problems as unit_problems,
    splits_a_range,
)

_TOKEN = re.compile(r"\w+|[^\w\s]")
UNRESOLVED_VERDICTS = frozenset({"neither", "uncertain"})
# The texts a first pass has written for "no reader" in place of JSON null.
NULL_TEXTS = frozenset({"null", "none", ""})
SYNTHETIC_RATIONALE = "Synthetic fixture: no visual evidence."
_PREAMBLE = (
    "Independent readers transcribed the attached label image. Their raw "
    "transcripts follow, unchanged."
)
_TASK = (
    "For each numbered difference, look at the image and say which reader's "
    "text the visual evidence supports: the reader's letter, neither, or "
    "uncertain. Then choose the reader whose raw transcript the image supports, "
    "as advice to the field harness. Choose a reader only if the image supports "
    "that reader's text at every difference that is more than capitalization. Otherwise answer "
    "null: that is how material ambiguity goes to human review. Add one short "
    "note per reader."
)
# A first pass stopped by its caps selects no reading, so G19 sends the raw
# readings on (PLAN section 1; HARNESS.md section 3).
CAP_RATIONALE = (
    "The first pass reached its token cap before an answer; no reading was selected."
)
# A first pass given up on after its last attempt failed (HARNESS.md section 3,
# Failures): a warning beside the record, `first_pass_given_up:<region>:<code>`.
GIVEN_UP = "first_pass_given_up"
GIVEN_UP_RULES = "first-pass-given-up-v1"


def _span(text: str, tokens: list[re.Match], start: int, end: int) -> ReadingSpan:
    if end > start:
        first, last = tokens[start].start(), tokens[end - 1].end()
    else:
        first = last = tokens[start - 1].end() if start else 0
    return ReadingSpan(start=first, end=last, text=text[first:last])


def _pair_tokens(a: list[str], b: list[str]) -> list[tuple[tuple, tuple]]:
    """Align a replaced block token by token: substituting a similar token
    costs less than deleting one and inserting another (Needleman-Wunsch)."""

    def substitute(x: str, y: str) -> float:
        return 1 - difflib.SequenceMatcher(None, x.lower(), y.lower()).ratio()

    cost = [[float(i + j) for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost[i][j] = min(
                cost[i - 1][j] + 1,
                cost[i][j - 1] + 1,
                cost[i - 1][j - 1] + substitute(a[i - 1], b[j - 1]),
            )
    pairs, i, j = [], len(a), len(b)
    while i or j:
        if (
            i
            and j
            and cost[i][j] == cost[i - 1][j - 1] + substitute(a[i - 1], b[j - 1])
        ):
            pairs.append(((i - 1, i), (j - 1, j)))
            i, j = i - 1, j - 1
        elif i and cost[i][j] == cost[i - 1][j] + 1:
            pairs.append(((i - 1, i), (j, j)))
            i -= 1
        else:
            pairs.append(((i, i), (j - 1, j)))
            j -= 1
    return pairs[::-1]


def reading_differences(
    first: str, second: str
) -> list[tuple[ReadingSpan, ReadingSpan]]:
    """Token differences between two readings, as exact spans of each reading.

    Differences in whitespace alone are dropped. A replaced block of at most
    twelve tokens a side is aligned token by token, so each difference stays
    as small as the alignment allows.
    """
    left, right = list(_TOKEN.finditer(first)), list(_TOKEN.finditer(second))
    matcher = difflib.SequenceMatcher(
        a=[m.group() for m in left], b=[m.group() for m in right], autojunk=False
    )
    differences = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        block = _span(first, left, i1, i2).text, _span(second, right, j1, j2).text
        if op == "equal" or "".join(block[0].split()) == "".join(block[1].split()):
            continue
        pairs = [((i1, i2), (j1, j2))]
        if op == "replace" and i2 - i1 <= 12 and j2 - j1 <= 12:
            pairs = [
                ((i1 + a1, i1 + a2), (j1 + b1, j1 + b2))
                for (a1, a2), (b1, b2) in _pair_tokens(
                    [m.group() for m in left[i1:i2]], [m.group() for m in right[j1:j2]]
                )
            ]
        for (a1, a2), (b1, b2) in pairs:
            a, b = _span(first, left, a1, a2), _span(second, right, b1, b2)
            if "".join(a.text.split()) != "".join(b.text.split()):
                differences.append((a, b))
    return differences


def _segments(first: str, other: str, left: list[re.Match], right: list[re.Match]):
    """Two readings' token alignment as reading_differences makes it, as
    consecutive segments (i1, i2, j1, j2, equal) that cover both readings'
    tokens: each equal block whole, and every other block split as
    reading_differences splits it (a replaced block of at most twelve tokens a
    side, unless it differs in whitespace alone, token by token)."""
    matcher = difflib.SequenceMatcher(
        a=[m.group() for m in left], b=[m.group() for m in right], autojunk=False
    )
    segments = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            segments.append((i1, i2, j1, j2, True))
            continue
        block = _span(first, left, i1, i2).text, _span(other, right, j1, j2).text
        pairs = [((i1, i2), (j1, j2))]
        if (
            op == "replace"
            and i2 - i1 <= 12
            and j2 - j1 <= 12
            and "".join(block[0].split()) != "".join(block[1].split())
        ):
            pairs = [
                ((i1 + a1, i1 + a2), (j1 + b1, j1 + b2))
                for (a1, a2), (b1, b2) in _pair_tokens(
                    [m.group() for m in left[i1:i2]], [m.group() for m in right[j1:j2]]
                )
            ]
        segments += [(a1, a2, b1, b2, False) for (a1, a2), (b1, b2) in pairs]
    return segments


def _clusters(intervals) -> list[tuple[int, int]]:
    """The pairwise differences' token intervals on the first reading, merged
    where a difference crosses another: intervals that overlap by at least one
    token are one difference, as is an insertion point inside one; intervals
    that only touch stay apart, and insertions at one point are one. In reading
    order, an insertion before the tokens that start at its point."""
    merged: list[list[int]] = []
    for start, end in sorted({(s, e) for s, e in intervals if s < e}):
        if merged and start < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    points = {
        s for s, e in intervals if s == e and not any(a < s < b for a, b in merged)
    }
    return sorted([*((a, b) for a, b in merged), *((p, p) for p in points)])


def reading_differences_among(texts) -> list[tuple[ReadingSpan, ...]]:
    """Token differences among two or more readings, one exact span per reading.

    Two readings: reading_differences, unchanged. With more, each later reading
    is aligned with the first as reading_differences aligns two (_segments),
    and the pairwise differences are merged on the first reading's tokens
    (_clusters): a difference grows until each of its ends is a point where
    every reading is aligned with the first, so it is as small as the pairwise
    alignments allow. Each reading's span is its text between those points:
    empty, at the offset where its text would be, when it has nothing there
    (an insertion in another reading, or an empty reading). A difference whose
    spans are all equal ignoring whitespace is dropped.
    """
    texts = list(texts)
    if len(texts) < 2:
        raise ValueError("Differences need two or more readings")
    if len(texts) == 2:
        return reading_differences(*texts)
    tokens = [list(_TOKEN.finditer(text)) for text in texts]
    first = tokens[0]
    intervals: list[tuple[int, int]] = []
    # For each later reading: the first reading's token boundaries mapped to its
    # own, lowest and highest (they differ where it inserted tokens).
    bounds = []
    for text, other in zip(texts[1:], tokens[1:]):
        low: dict[int, int] = {}
        high: dict[int, int] = {}

        def align(i: int, j: int) -> None:
            low[i], high[i] = min(low.get(i, j), j), max(high.get(i, j), j)

        align(0, 0)
        align(len(first), len(other))
        for i1, i2, j1, j2, equal in _segments(texts[0], text, first, other):
            if equal:
                for step in range(i2 - i1 + 1):
                    align(i1 + step, j1 + step)
            else:
                align(i1, j1)
                align(i2, j2)
                intervals.append((i1, i2))
        bounds.append((low, high))
    differences = []
    for start, end in _clusters(intervals):
        spans = [_span(texts[0], first, start, end)]
        for text, other, (low, high) in zip(texts[1:], tokens[1:], bounds):
            if start == end:
                spans.append(_span(text, other, low[start], high[start]))
            else:
                spans.append(_span(text, other, high[start], low[end]))
        if len({"".join(span.text.split()) for span in spans}) > 1:
            differences.append(tuple(spans))
    return differences


def _line(text: str, offset: int) -> str:
    end = text.find("\n", offset)
    return text[text.rfind("\n", 0, offset) + 1 : len(text) if end < 0 else end]


def build_request(
    readings: list[Observation], differences: list[tuple[ReadingSpan, ...]]
) -> tuple[str, dict[str, Observation]]:
    """The user message: readers by letter only (A, B, C ...), their raw texts,
    the differences with one span per reader. The letters run to Z, so the
    message can name 26 readers; a profile names at most 8
    (review_risk.MAX_LABEL_READINGS), the budget of the label risk measure."""
    letters = dict(zip(string.ascii_uppercase, readings))
    lines = [_PREAMBLE, ""]
    for letter, reading in letters.items():
        lines += [f"Reader {letter}:", "<<<", reading.literal_text, ">>>", ""]
    lines.append(
        "The transcripts differ at these points:"
        if differences
        else "The transcripts differ only in whitespace."
    )
    for number, spans in enumerate(differences, 1):
        parts = [
            f'Reader {letter}: "{span.text}" '
            f'(in line "{_line(reading.literal_text, span.start)}")'
            for (letter, reading), span in zip(letters.items(), spans)
        ]
        lines.append(f"{number}. " + " | ".join(parts))
    return "\n".join([*lines, "", _TASK]), letters


class DifferenceVerdict(BaseModel):
    number: int = Field(description="The difference's number as listed.")
    supported: str = Field(
        description="The letter of the reader whose text the image supports here, "
        "'neither' when the image shows something else, or 'uncertain'."
    )


class FirstPassOutput(BaseModel):
    selected_reader: str | None = Field(
        description="The letter of the reader whose raw transcript the image "
        "supports, as advice to the field harness, which may settle a field on "
        "another reader's text; null unless the image supports that reader's "
        "text at every difference that is more than capitalization."
    )
    verdicts: list[DifferenceVerdict]
    rationale: str = Field(min_length=1)
    reader_notes: dict[str, str] = Field(
        description="One short note per reader letter."
    )

    @field_validator("selected_reader", mode="before")
    @classmethod
    def _null_written_as_text(cls, value):
        """A pick written as the text "null", "None" or "" is no pick (null).

        GLM-5.3-Flash on Novita writes the JSON null this field asks for as a
        string, and writes it again on the output retry, so the whole answer was
        refused as malformed (HARNESS.md section 3, "A first pass's null written
        as text"). Such a value names no reader, so it never selects a reading.
        """
        if isinstance(value, str) and value.strip().lower() in NULL_TEXTS:
            return None
        return value


def output_problems(output: FirstPassOutput, letters, count: int) -> list[str]:
    """Why an answer cannot be used, phrased for the model's one output retry."""
    problems = []
    if output.selected_reader is not None and output.selected_reader not in letters:
        problems.append(f"selected_reader must be one of {sorted(letters)} or null")
    # With no difference listed (the readings differ only in whitespace) there is
    # nothing to judge: a verdict is for a difference that does not exist, and
    # first_pass_direct reads verdicts 1..len(differences) only, so none here.
    verdicts = output.verdicts if count else []
    if sorted(v.number for v in verdicts) != list(range(1, count + 1)):
        problems.append(f"give exactly one verdict for each difference 1 to {count}")
    allowed = {*letters, *UNRESOLVED_VERDICTS}
    if any(v.supported not in allowed for v in verdicts):
        problems.append(f"each verdict's supported must be one of {sorted(allowed)}")
    if set(output.reader_notes) != set(letters):
        problems.append(f"give one note for each reader {sorted(letters)}")
    return problems


def is_material(spans) -> bool:
    """More than capitalization: the spans differ once lower-cased, so a spelling
    variant stays material. The code decides it, not the model (the coordinator's
    12:31Z reading and 14:05Z ruling; HARNESS.md section 3)."""
    return len({span.text.lower() for span in spans}) > 1


def supports(difference, selected: str | None) -> bool:
    """Whether a difference's verdict supports the selected reading: it names
    that reading, or a reading whose text there is the selected reading's,
    compared as is_material compares them (lower-cased). With two readings a
    material difference's two texts differ, so only a verdict naming the
    selected reading supports it; with more, readers that agree at a
    difference share its verdict."""
    if difference.verdict == selected:
        return True
    spans = difference.spans
    return (
        selected in spans
        and difference.verdict in spans
        and spans[difference.verdict].text.lower() == spans[selected].text.lower()
    )


def g19_pick(selected: str | None, differences) -> str | None:
    """The picked reading, or None when a material difference does not support
    it: material ambiguity returns no reading (G19; the coordinator's 12:31Z
    reading; HARNESS.md section 3)."""
    if any(
        is_material(d.spans.values()) and not supports(d, selected) for d in differences
    ):
        return None
    return selected


class InputBoundModel(WrapperModel):
    """Sends a request only when its input cannot exceed the route's bound, so
    the call never spends past its reservation (lane_reservations). A first
    request over the bound blocks the step; a retry over it stops the call at
    its cap, which selects no reading (G19)."""

    def __init__(self, wrapped, bound: int, rule: dict | None):
        super().__init__(wrapped)
        self.bound, self.rule = bound, rule

    async def request(self, messages, model_settings, model_request_parameters):
        from .lane_reservations import request_input_tokens
        from .workflow import OperationalBlock

        size = request_input_tokens(messages, model_request_parameters, self.rule)
        if size is None or size > self.bound:
            if not any(message.kind == "response" for message in messages):
                raise OperationalBlock("first_pass_input_over_bound")
            raise UsageLimitExceeded("The retry's input could exceed its bound")
        return await self.wrapped.request(
            messages, model_settings, model_request_parameters
        )


def _prepared(adapter, specimen, region, readings, prompt_name: PromptName):
    """The checks first_pass_direct and first_pass_units_direct make before they send
    anything, and what they send with: the pinned route's model (bounded by its input and
    output caps), the pinned prompt and the crop."""
    from .lane_reservations import image_rule
    from .workflow import OperationalBlock, crop_bytes

    if os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true":
        raise OperationalBlock("provider_data_policy_and_spending_approval_required")
    if not 2 <= len(readings) <= len(string.ascii_uppercase):
        # Two or more readings, one reader letter each (build_request): this
        # call could letter 26. A profile names at most 8 readers, so a label
        # never has more (review_risk.MAX_LABEL_READINGS).
        raise OperationalBlock("first_pass_reading_count_unsupported")
    run = specimen.run
    routes = [reading.route_id for reading in readings]
    if (
        any(reading.region_id != region.id for reading in readings)
        or any(
            reading.input_asset_id not in (None, specimen.asset.id)
            for reading in readings
        )
        or len({reading.id for reading in readings}) != len(readings)
        or routes != [route for route in run.profile.routes if route in routes]
    ):
        # The region's own readings, once each, in route order (HARNESS.md 3).
        raise OperationalBlock("first_pass_contract_invalid")
    route_id = run.profile.first_pass_route
    timeout = run.profile.execution.effect_timeout_for_step("first_pass:" + region.id)
    gateway = HuggingFaceModelGateway(timeout_seconds=timeout / 2)
    if route_id is None or route_id not in gateway.routes:
        raise OperationalBlock("pinned_model_route_unavailable")
    selected = gateway.route(route_id)
    if not selected.serves_with_images("transcription_first_pass"):
        # The crop goes only to a first-pass route with image input (HARNESS.md 5).
        raise OperationalBlock("pinned_model_route_unavailable")
    if run.dependencies.get("routes", {}).get(route_id) != {
        "model_id": selected.model_id,
        "provider": selected.provider,
    }:
        raise OperationalBlock("pinned_model_route_unavailable")
    try:
        prompt = ResolvedPrompt.model_validate(run.dependencies["prompts"][prompt_name.value])
    except (KeyError, ValueError) as exc:
        raise OperationalBlock("pinned_prompt_unavailable") from exc
    image = crop_bytes(adapter.blobs, specimen, region)
    # The bounds the step's reservation assumed: each request's input, checked
    # before it is sent, and each answer's tokens, capped by the provider.
    prices = run.profile.execution.price_list or {}
    price = prices.get("models", {}).get(route_id) or {}
    model = PrivateProviderModel(gateway.model_for(route_id))
    if bound := price.get("max_input_tokens") or price.get("context_tokens"):
        model = InputBoundModel(model, bound, image_rule(prices, route_id))
    return SimpleNamespace(
        route_id=route_id,
        selected=selected,
        prompt=prompt,
        timeout=timeout,
        image=image,
        model=model,
        output_cap=price.get("max_output_tokens"),
    )


def _agent(prepared, name: str, output_type, request_options=None):
    """The call's agent. `request_options` replace the route's own request options of the same
    name for this call's requests (model_gateway, request_options)."""
    settings = {"max_tokens": prepared.output_cap} if prepared.output_cap else {}
    if request_options:
        settings["extra_body"] = {
            **dict(prepared.selected.request_options),
            **request_options,
        }
    # No instrumentation override: the lane's global setting applies (HARNESS.md 3).
    return Agent(
        prepared.model,
        name=name + prepared.route_id.replace("-", "_"),
        output_type=output_type,
        instructions=prepared.prompt.text,
        model_settings=settings or None,
    )


def _called(agent, prepared, request: str):
    """The agent's run on the request and the crop: its result (None when it stopped at its
    caps), usage, wall time, the provider responses and the last one."""
    from .reliability import run_agent_bounded

    started = time.monotonic()
    try:
        result = run_agent_bounded(
            agent,
            [request, BinaryContent(data=prepared.image, media_type="image/png")],
            timeout_seconds=prepared.timeout,
            usage_limits=UsageLimits(request_limit=2, total_tokens_limit=16000),
        )
        history, usage = result.all_messages(), result.usage
    except UsageLimitExceeded as stop:
        # No answer within its caps: no reading (G19); the call keeps its usage.
        result, history, usage = None, stop.run_messages, stop.run_usage
    latency_seconds = time.monotonic() - started
    # Every provider response, retries included; the image-bearing request is not.
    responses = [m for m in history if m.kind == "response"]
    raw = ModelMessagesTypeAdapter.dump_json(responses)
    return result, usage, latency_seconds, raw, responses[-1] if responses else None


def _call_record(adapter, specimen, region, prepared, agent, request, called) -> Observation:
    """The first pass's own call, as an observation with no text (HARNESS.md section 4)."""
    result, usage, latency_seconds, raw, last = called
    return Observation(
        latency_seconds=latency_seconds,
        latency_basis="validated_agent_call_wall_seconds",
        finish_state=getattr(last, "finish_reason", None),
        completion_state="validated_output" if result is not None else "usage_limit",
        # The settings every request carried: the route's own (its request
        # options, model_gateway) under the agent's.
        parameters={**(prepared.model.settings or {}), **(agent.model_settings or {})}
        or None,
        provider_model_id=getattr(last, "model_name", None),
        input_asset_id=specimen.asset.id,
        input_crop_ref=adapter.blobs.put(prepared.image),
        region_id=region.id,
        route_id=prepared.route_id,
        model_id=prepared.selected.model_id,
        provider=prepared.selected.provider,
        prompt_version=hashlib.sha256(prepared.prompt.text.encode()).hexdigest(),
        # The crop's digest, as for every observation; the request's apart.
        input_sha256=hashlib.sha256(prepared.image).hexdigest(),
        request_sha256=hashlib.sha256(request.encode()).hexdigest(),
        literal_text="",
        raw_ref=adapter.blobs.put(raw),
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )


def first_pass_direct(adapter, specimen, region, readings) -> FirstPassDecision:
    """Run the first pass for one region in the isolated model child."""
    prepared = _prepared(
        adapter, specimen, region, readings, PromptName.DISAGREEMENT_ADJUDICATION
    )
    differences = reading_differences_among([r.literal_text for r in readings])
    request, letters = build_request(readings, differences)
    agent = _agent(prepared, "first_pass_", FirstPassOutput)

    @agent.output_validator
    def complete(output: FirstPassOutput) -> FirstPassOutput:
        if problems := output_problems(output, letters, len(differences)):
            raise ModelRetry("; ".join(problems))
        return output

    called = _called(agent, prepared, request)
    result = called[0]
    ids = {letter: reading.id for letter, reading in letters.items()}
    spans = [dict(zip(ids.values(), group)) for group in differences]
    if result is None:
        # No answer: every difference stays open, and G19 decides (HARNESS.md 3).
        picked, rationale, notes = None, CAP_RATIONALE, {}
        verdicts = ["uncertain"] * len(spans)
    else:
        output = result.output
        picked, rationale = ids.get(output.selected_reader), output.rationale
        notes = {ids[letter]: note for letter, note in output.reader_notes.items()}
        supported = {verdict.number: verdict.supported for verdict in output.verdicts}
        verdicts = [
            ids.get(supported[n], supported[n]) for n in range(1, len(spans) + 1)
        ]
    decided = [
        FirstPassDifference(
            number=number,
            spans=pair,
            verdict=verdict,
            material=is_material(pair.values()),
        )
        for number, (pair, verdict) in enumerate(zip(spans, verdicts), 1)
    ]
    return FirstPassDecision(
        region_id=region.id,
        # A pick a material difference does not support is no reading (G19;
        # the coordinator's 12:31Z reading).
        selected_observation_id=g19_pick(picked, decided),
        rationale=rationale,
        notes=notes,
        differences=decided,
        call=_call_record(adapter, specimen, region, prepared, agent, request, called),
    )


def _agreed(texts, starts, ends) -> list[list[tuple[int, int]]]:
    """The agreed stretch between two differences, cut at the white space every reading has."""
    marks = [
        [i for i in range(start, end) if not text[i].isspace()]
        for text, start, end in zip(texts, starts, ends)
    ]
    shown = {"".join(text[i] for i in mark) for text, mark in zip(texts, marks)}
    if not any(marks):
        return []
    if len(shown) > 1:
        # The readings' texts here differ: one piece.
        return [
            [(mark[0], mark[-1] + 1) if mark else (start, start) for mark, start in zip(marks, starts)]
        ]
    cuts = [
        k for k in range(1, len(marks[0]))
        if all(mark[k] - mark[k - 1] > 1 for mark in marks)
    ]
    bounds = [0, *cuts, len(marks[0])]
    return [
        [(mark[low], mark[high - 1] + 1) for mark in marks]
        for low, high in zip(bounds, bounds[1:])
    ]


def _apart(texts, before, after) -> bool:
    """Whether a segment may end between two pieces: every reading that wrote text on both
    sides has white space between them, and no reading has a range across the gap."""
    for text, (low, end), (start, stop) in zip(texts, before, after):
        if splits_a_range(text, end, start) or (low < end and start < stop and end == start):
            return False
    return True


def _joined(text: str, spans) -> ReadingSpan:
    """One reading's span over consecutive pieces: from its first text to its last, or empty
    where its first piece is when it wrote nothing in any."""
    written = [(low, high) for low, high in spans if high > low]
    low, high = (written[0][0], written[-1][1]) if written else (spans[0][0], spans[0][0])
    return ReadingSpan(start=low, end=high, text=text[low:high])


def reading_segments(texts) -> list[tuple[ReadingSpan, ...]]:
    """The readings cut into consecutive segments, one span per reading each. The pieces are
    reading_differences_among's differences and, between them, _agreed's cuts at the white
    space the readings share; _apart joins two pieces when a reading with text on both sides
    has no white space between them or a range spans the gap. A reading with no text at a
    difference has an empty span there. Readings with no text give no segment."""
    texts = list(texts)
    differences = reading_differences_among(texts) if len(texts) > 1 else []
    pieces: list[list[tuple[int, int]]] = []
    cursor = [0] * len(texts)
    for difference in [*differences, None]:
        ends = [len(t) for t in texts] if difference is None else [s.start for s in difference]
        if any(end < start for start, end in zip(cursor, ends)):
            raise ValueError("The alignment's differences are out of reading order")
        pieces += _agreed(texts, cursor, ends)
        if difference is not None:
            pieces.append([(s.start, s.end) for s in difference])
            cursor = [s.end for s in difference]
    # Each group: each reading's pieces of one segment.
    groups: list[list[list[tuple[int, int]]]] = []
    for spans in pieces:
        if groups:
            before = [_joined(text, own) for text, own in zip(texts, groups[-1])]
            if not _apart(texts, [(span.start, span.end) for span in before], spans):
                for own, span in zip(groups[-1], spans):
                    own.append(span)
                continue
        groups.append([[span] for span in spans])
    return [
        tuple(_joined(text, own) for text, own in zip(texts, group)) for group in groups
    ]


# The line boundaries str.splitlines recognises: "\r\n" is one, as are "\r", "\n", the vertical
# tab, the form feed, the file, group and record separators, NEL, U+2028 and U+2029.
LINE_BREAK = re.compile("\r\n|[\n\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")


def _line_number(text: str, offset: int) -> int:
    """The line, from 1, that the character at `offset` of `text` is on."""
    return 1 + len(LINE_BREAK.findall(text, 0, offset))


def _lines(readings, spans) -> tuple[int, int]:
    """The lines of a unit's first and last character (at `end - 1`), in the first reading
    with text there."""
    for reading, span in zip(readings, spans):
        if span.text:
            text = reading.literal_text
            return _line_number(text, span.start), _line_number(text, span.end - 1)
    return 1, 1


def _unit(region_id: str, number: int, readings, spans, **judged) -> ReadingUnit:
    return ReadingUnit(
        id=f"{region_id}:{number}",
        label=region_id,
        lines=_lines(readings, spans),
        readers={
            reading.id: UnitText(text=span.text, start=span.start, end=span.end)
            for reading, span in zip(readings, spans)
        },
        **judged,
    )


def alignment_units(region_id: str, readings) -> ReadingUnits | None:
    """A label's units from reading_segments alone, a unit per segment, its image uncertain.
    None when no reading holds text."""
    segments = reading_segments([r.literal_text for r in readings])
    if not segments:
        return None
    return ReadingUnits(
        label=region_id,
        units=[
            _unit(region_id, number, readings, spans, image=UNCERTAIN)
            for number, spans in enumerate(segments, 1)
        ],
    )


_UNITS_TASK = (
    "Group segments 1 to {count} into reading units: each unit is one segment or several "
    "consecutive ones, and every segment belongs to exactly one unit, in order. Give each unit's "
    "first and last segment and what the image shows there; give means, role, fields and note "
    "only where they apply, and leave out a key that does not."
)


def build_units_request(readings, segments) -> tuple[str, dict[str, Observation]]:
    """The units path's user message: the readers by letter, then the numbered segments grouped
    by the line _lines gives each, a segment's text once when the readers' texts are equal,
    else each reader's."""
    letters = dict(zip(string.ascii_uppercase, readings))
    names = list(letters)
    readers = ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else names[0]
    lines = [
        f"Independent readers {readers} transcribed the attached label image. Their texts, "
        "unchanged, cut at spaces or line breaks they share, a range kept whole, in numbered "
        'segments line by line; where the readers differ, each reader\'s text ("" where it '
        "wrote nothing):"
    ]
    row, line = [], None
    for number, spans in enumerate(segments, 1):
        texts = [span.text for span in spans]
        shown = (
            json.dumps(texts[0], ensure_ascii=False)
            if len(set(texts)) == 1
            else "{"
            + ", ".join(f"{letter} {json.dumps(text, ensure_ascii=False)}" for letter, text in zip(names, texts))
            + "}"
        )
        first = _lines(readings, spans)[0]
        if row and first != line:
            lines.append(f"Line {line}: " + " ".join(row))
            row = []
        row.append(f"[{number}] {shown}")
        line = first
    if row:
        lines.append(f"Line {line}: " + " ".join(row))
    return "\n".join([*lines, "", _UNITS_TASK.format(count=len(segments))]), letters


class UnitAnswer(BaseModel):
    first: int
    # A unit of one segment may give its first alone.
    last: int | None = None
    image: str
    means: str = ""
    role: Literal["", "genus", "species", "author", "day", "month", "year"] = ""
    fields: list[str] = Field(default_factory=list)
    note: str = ""


class UnitsOutput(BaseModel):
    units: list[UnitAnswer] = Field(min_length=1)


def _last(unit: UnitAnswer) -> int:
    return unit.first if unit.last is None else unit.last


def units_output_problems(output: UnitsOutput, letters, segments) -> list[str]:
    """Why a units answer cannot be used, phrased for the model's one output retry."""
    found = []
    expected = 1
    for number, unit in enumerate(output.units, 1):
        if unit.first != expected or _last(unit) < unit.first:
            found.append(
                f"the units must cover segments 1 to {len(segments)}, each once and in order: "
                f"unit {number} should start at segment {expected} and end at or after it"
            )
            break
        expected = _last(unit) + 1
    else:
        if expected != len(segments) + 1:
            found.append(f"the units must end at segment {len(segments)}, the last")
    ids = {letter: index for index, letter in enumerate(letters)}
    for number, unit in enumerate(output.units, 1):
        if unit.image in ids:
            if not 1 <= unit.first <= _last(unit) <= len(segments) or not "".join(
                segments[n - 1][ids[unit.image]].text for n in range(unit.first, _last(unit) + 1)
            ):
                found.append(f"unit {number}: reader {unit.image} wrote nothing there")
        elif unit.image not in (UNCERTAIN, NOT_VISIBLE):
            found.append(
                f"unit {number}: image must be one of {sorted(ids)}, {UNCERTAIN!r} or {NOT_VISIBLE!r}"
            )
        if unknown := [key for key in unit.fields if key not in MANDATORY]:
            found.append(f"unit {number}: {', '.join(unknown)} is not a field key")
        if len(set(unit.fields)) != len(unit.fields):
            found.append(f"unit {number} names a field twice")
    return found


def _plain(text: str) -> str:
    """A text compared without case, white space or punctuation."""
    return "".join(character for character in text.casefold() if character.isalnum())


def units_from_output(region_id: str, output: UnitsOutput, letters, segments) -> ReadingUnits:
    """The label's units from an answer units_output_problems accepted."""
    readings = list(letters.values())
    units = []
    for number, answer in enumerate(output.units, 1):
        group = segments[answer.first - 1 : _last(answer)]
        spans = [
            _joined(reading.literal_text, [(s[i].start, s[i].end) for s in group])
            for i, reading in enumerate(readings)
        ]
        image = answer.image
        if image in letters:
            image = spans[list(letters).index(image)].text
        means = answer.means.strip()
        if _plain(means) in {_plain(span.text) for span in spans}:
            # A meaning equal to a reader's text here (_plain) is left empty.
            means = ""
        units.append(
            _unit(
                region_id, number, readings, spans,
                image=image, means=means, role=answer.role,
                fields=answer.fields, note=answer.note.strip(),
            )
        )
    return ReadingUnits(label=region_id, units=units)


# Request options first_pass_units_direct's agent sends over the route's own (_agent).
UNITS_REQUEST_OPTIONS = {"reasoning_effort": "low"}


# _unpicked's decision selects no reading and gives each difference the verdict uncertain.
UNITS_RATIONALE = "The first pass cut the label into reading units; it names no reading."


def _unpicked(region_id: str, readings, rationale: str, call: Observation) -> FirstPassDecision:
    differences = reading_differences_among([r.literal_text for r in readings])
    return FirstPassDecision(
        region_id=region_id,
        selected_observation_id=None,
        rationale=rationale,
        notes={},
        differences=[
            FirstPassDifference(
                number=number,
                spans={reading.id: span for reading, span in zip(readings, group)},
                verdict="uncertain",
                material=is_material(group),
            )
            for number, group in enumerate(differences, 1)
        ],
        call=call,
    )


def first_pass_units_direct(adapter, specimen, region, readings):
    """The units path's call for one region, in the isolated model child: the label's units and
    the _unpicked decision."""
    from .workflow import OperationalBlock

    prepared = _prepared(adapter, specimen, region, readings, PromptName.FIRST_PASS_UNITS)
    segments = reading_segments([r.literal_text for r in readings])
    if not segments:
        # No segment: no reading holds text.
        raise OperationalBlock("first_pass_contract_invalid")
    request, letters = build_units_request(readings, segments)
    texts = {reading.id: reading.literal_text for reading in readings}
    agent = _agent(prepared, "first_pass_units_", UnitsOutput, UNITS_REQUEST_OPTIONS)

    @agent.output_validator
    def complete(output: UnitsOutput) -> UnitsOutput:
        found = units_output_problems(output, letters, segments)
        if not found:
            try:
                found = unit_problems(units_from_output(region.id, output, letters, segments), texts)
            except ValidationError as error:
                found = [str(item["msg"]) for item in error.errors()]
        if found:
            raise ModelRetry("; ".join(found))
        return output

    called = _called(agent, prepared, request)
    result = called[0]
    call = _call_record(adapter, specimen, region, prepared, agent, request, called)
    if result is None:
        # No answer within its caps: alignment_units.
        return _unpicked(region.id, readings, CAP_RATIONALE, call), alignment_units(
            region.id, readings
        )
    units = units_from_output(region.id, result.output, letters, segments)
    return _unpicked(region.id, readings, UNITS_RATIONALE, call), units


def synthetic_units(blobs, region, readings):
    """Deterministic fixture of the units path: synthetic_decision and alignment_units."""
    return synthetic_decision(blobs, region, readings), alignment_units(region.id, readings)


def synthetic_decision(blobs, region, readings) -> FirstPassDecision:
    """Deterministic fixture: without visual evidence no reading is selected."""
    differences = reading_differences_among([r.literal_text for r in readings])
    summary = {"region_id": region.id, "selected_observation_id": None}
    detail = dict(summary, differences=len(differences), rationale=SYNTHETIC_RATIONALE)
    raw = b"SYNTHETIC FIXTURE\n" + json.dumps(detail).encode()
    return FirstPassDecision(
        **summary,
        rationale=SYNTHETIC_RATIONALE,
        notes={reading.id: "Synthetic fixture reading." for reading in readings},
        differences=[
            FirstPassDifference(
                number=number,
                spans={reading.id: span for reading, span in zip(readings, group)},
                verdict="uncertain",
                material=is_material(group),
            )
            for number, group in enumerate(differences, 1)
        ],
        call=Observation(
            region_id=region.id,
            route_id="synthetic-first-pass",
            model_id="synthetic-first-pass",
            provider="synthetic",
            prompt_version="fixture-v1",
            # The input the readers saw, as for their observations.
            input_sha256=readings[0].input_sha256,
            literal_text="",
            raw_ref=blobs.put(raw),
            raw_sha256=hashlib.sha256(raw).hexdigest(),
        ),
    )


# A run's pinned first-pass route moved to another provider of the same model
# (HARNESS.md section 3, Failures): `run.dependencies[ROUTE_REPINS]` keeps each move.
ROUTE_REPINS = "route_repins"
ROUTE_REPIN_RULES = "first-pass-same-model-provider-repin-v1"


def repinnable_first_pass_route(run):
    """The current registered first-pass route when the run's pin names the same
    model at another provider; else None.

    Only the provider may differ: a pin of another model, a malformed pin, a
    route that is no longer registered or no longer serves the first pass with
    images is never moved, so its step still blocks as
    ``pinned_model_route_unavailable``. The price list is keyed by route, so the
    step's reservation and the run's cap are unchanged.
    """
    from ..model_gateway import HUGGINGFACE_ROUTES

    route_id = run.profile.first_pass_route
    pins = run.dependencies.get("routes")
    if route_id is None or not isinstance(pins, dict):
        return None
    pinned, current = pins.get(route_id), HUGGINGFACE_ROUTES.get(route_id)
    if (
        current is None
        or not current.serves_with_images("transcription_first_pass")
        or not isinstance(pinned, dict)
        or set(pinned) != {"model_id", "provider"}
        or pinned["model_id"] != current.model_id
        or pinned["provider"] == current.provider
    ):
        return None
    return current


def repin_first_pass_route(run, at) -> bool:
    """Move the run's first-pass pin to the registered provider of the same model,
    recording the move (old and new provider, when) in ``ROUTE_REPINS``."""
    current = repinnable_first_pass_route(run)
    if current is None:
        return False
    pins = run.dependencies["routes"]
    previous = pins[current.route_id]["provider"]
    pins[current.route_id] = {"model_id": current.model_id, "provider": current.provider}
    run.dependencies.setdefault(ROUTE_REPINS, []).append(
        {
            "route_id": current.route_id,
            "model_id": current.model_id,
            "from_provider": previous,
            "to_provider": current.provider,
            "at": at.isoformat(),
            "rule": ROUTE_REPIN_RULES,
        }
    )
    return True


def give_up(run, region_id: str, code: str) -> None:
    """Record that the run gave up on a label's first pass, and the code its last
    attempt failed with: one warning finding per label. A finding never routes
    the record by itself; the label's transcript stays unresolved, which does."""
    run.findings = [
        f for f in run.findings if not (f.rule_id == GIVEN_UP and _region(f) == region_id)
    ] + [
        RunFinding(
            rule_id=GIVEN_UP,
            rule_version=GIVEN_UP_RULES,
            severity="warning",
            reason_code=f"{GIVEN_UP}:{region_id}:{code}",
        )
    ]


def given_up_regions(run) -> frozenset[str]:
    """The labels whose first pass the run gave up on (``give_up``) and holds no
    decision for."""
    decided = {d.region_id for d in run.first_pass_decisions}
    return frozenset(
        _region(f) for f in run.findings if f.rule_id == GIVEN_UP
    ) - decided


def _region(finding) -> str:
    return finding.reason_code.split(":")[1]


def adjudication_record(readings, texts, resolved, decision, *, keep_call=False):
    """The region's transcript text, whether it is resolved, and its first-pass
    fields: identical readings keep the existing rule; differing readings take
    the first pass's selected reading verbatim, or no text. With `keep_call`,
    identical readings with a decision also record its call."""
    if len(readings) > 1 and len(texts) == 1:
        selected, notes = readings[0].id if resolved else None, {}
        record = {"decision_kind": "identical_readings"}
        if keep_call and decision is not None:
            record["first_pass_call"] = decision.call
    elif len(texts) > 1 and decision is not None:
        selected, notes = decision.selected_observation_id, decision.notes
        record = {
            "decision_kind": "first_pass",
            "first_pass_call": decision.call,
            "differences": decision.differences,
            "reason": decision.rationale,
        }
    else:
        return None, False, {}
    record["selected_observation_id"] = selected
    record["handoffs"] = [
        ReaderHandoff(
            observation_id=reading.id,
            role="decided_transcript" if reading.id == selected else "raw_reading",
            handed_text=reading.literal_text,
            note=notes.get(reading.id),
        )
        for reading in readings
    ]
    text = next((r.literal_text for r in readings if r.id == selected), None)
    return text, text is not None, record
