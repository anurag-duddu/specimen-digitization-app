"""The LLM first pass (stage 6): which reader's raw transcript the harness runs on.

In the owner's words (docs/execution/golive/PLAN.md section 1): "LLM does first
pass at which final RAW transcript should run against (it should also give at a
VLM level what was returned to the harness)". It never writes text: the decided
transcript is the selected reading verbatim. Spec: docs/execution/golive/HARNESS.md
section 3.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import string
import time

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent, BinaryContent, ModelRetry
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.usage import UsageLimits

from ..model_gateway import HuggingFaceModelGateway
from ..prompts import PromptName, ResolvedPrompt
from ..provider_privacy import PrivateProviderModel
from .domain import (
    FirstPassDecision,
    FirstPassDifference,
    Observation,
    ReaderHandoff,
    ReadingSpan,
    RunFinding,
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
    "uncertain. Then choose the reader whose raw transcript the lookups should "
    "run against. Choose a reader only if the image supports that reader's text "
    "at every difference that is more than capitalization. Otherwise answer "
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
    the differences with one span per reader."""
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
        description="The letter of the reader whose raw transcript the lookups "
        "should run against, or null unless the image supports that reader's "
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


def first_pass_direct(adapter, specimen, region, readings) -> FirstPassDecision:
    """Run the first pass for one region in the isolated model child."""
    from .lane_reservations import image_rule
    from .reliability import run_agent_bounded
    from .workflow import OperationalBlock, crop_bytes

    if os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true":
        raise OperationalBlock("provider_data_policy_and_spending_approval_required")
    if not 2 <= len(readings) <= len(string.ascii_uppercase):
        # Two or more readings, one reader letter each (build_request).
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
        prompt = ResolvedPrompt.model_validate(
            run.dependencies["prompts"][PromptName.DISAGREEMENT_ADJUDICATION.value]
        )
    except (KeyError, ValueError) as exc:
        raise OperationalBlock("pinned_prompt_unavailable") from exc
    differences = reading_differences_among([r.literal_text for r in readings])
    request, letters = build_request(readings, differences)
    image = crop_bytes(adapter.blobs, specimen, region)
    # The bounds the step's reservation assumed: each request's input, checked
    # before it is sent, and each answer's tokens, capped by the provider.
    prices = run.profile.execution.price_list or {}
    price = prices.get("models", {}).get(route_id) or {}
    model = PrivateProviderModel(gateway.model_for(route_id))
    if bound := price.get("max_input_tokens") or price.get("context_tokens"):
        model = InputBoundModel(model, bound, image_rule(prices, route_id))
    output_cap = price.get("max_output_tokens")
    # No instrumentation override: the lane's global setting applies (HARNESS.md 3).
    agent = Agent(
        model,
        name="first_pass_" + route_id.replace("-", "_"),
        output_type=FirstPassOutput,
        instructions=prompt.text,
        model_settings={"max_tokens": output_cap} if output_cap else None,
    )

    @agent.output_validator
    def complete(output: FirstPassOutput) -> FirstPassOutput:
        if problems := output_problems(output, letters, len(differences)):
            raise ModelRetry("; ".join(problems))
        return output

    started = time.monotonic()
    try:
        result = run_agent_bounded(
            agent,
            [request, BinaryContent(data=image, media_type="image/png")],
            timeout_seconds=timeout,
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
    last = responses[-1] if responses else None
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
        call=Observation(
            latency_seconds=latency_seconds,
            latency_basis="validated_agent_call_wall_seconds",
            finish_state=getattr(last, "finish_reason", None),
            completion_state="validated_output"
            if result is not None
            else "usage_limit",
            # The settings every request carried: the route's own (its request
            # options, model_gateway) under the agent's.
            parameters={**(model.settings or {}), **(agent.model_settings or {})}
            or None,
            provider_model_id=getattr(last, "model_name", None),
            input_asset_id=specimen.asset.id,
            input_crop_ref=adapter.blobs.put(image),
            region_id=region.id,
            route_id=route_id,
            model_id=selected.model_id,
            provider=selected.provider,
            prompt_version=hashlib.sha256(prompt.text.encode()).hexdigest(),
            # The crop's digest, as for every observation; the request's apart.
            input_sha256=hashlib.sha256(image).hexdigest(),
            request_sha256=hashlib.sha256(request.encode()).hexdigest(),
            literal_text="",
            raw_ref=adapter.blobs.put(raw),
            raw_sha256=hashlib.sha256(raw).hexdigest(),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        ),
    )


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


def adjudication_record(readings, texts, resolved, decision):
    """The region's transcript text, whether it is resolved, and its first-pass
    fields: identical readings keep the existing rule; differing readings take
    the first pass's selected reading verbatim, or no text."""
    if len(readings) > 1 and len(texts) == 1:
        selected, notes = readings[0].id if resolved else None, {}
        record = {"decision_kind": "identical_readings"}
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
