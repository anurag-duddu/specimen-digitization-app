"""A model call that sends a crop reserves its worst case (docs/execution/golive/LANE.md, T2b).

PLAN 4.3 and the coordinator's ruling of 2026-09-24. Before the call, it
reserves for each request it may make; each request reserves the lesser of
(a) the route's context length at the input price plus the output cap, and
(b), where the route documents its image-token rule, the crop's tokens under
that rule plus the prompt and the output cap. The stage's reservation is the
floor.

A route whose price names `max_input_tokens` reserves that in place of its
context length in (a), and `max_output_tokens` as its output cap; the call
enforces both (the coordinator, 2026-10-03: bound the first pass's request).
"""

from __future__ import annotations

import json
from math import ceil

MILLION = 1_000_000
# run_agent_bounded's limits on a reading (production.py): two requests, each
# answer capped at 4,096 tokens.
REQUESTS = 2
OUTPUT_CAP = 4_096
# The retry's validation feedback, at most (HARNESS.md section 15), and the
# chat template around a later request's new parts.
FEEDBACK_BYTES = 8_192
LATER_FRAMING_TOKENS = 256
# The chat template and the request line around the instructions and schema.
PROMPT_FRAMING_TOKENS = 512
# An image's delimiters and a tiny crop's upscaling.
IMAGE_SLACK_TOKENS = 256
# Match the deployed SAM profile: 600s startup at boosted 8 vCPU, 300s
# request, 10s boosted post-start and 10s shutdown. Idle warming belongs to
# the cumulative infrastructure budget. Request seconds never refund startup.
SAM_STARTUP_SECONDS = 600
SAM_REQUEST_SECONDS = 300
SAM_BOOST_SECONDS = 10
SAM_SHUTDOWN_SECONDS = 10


def image_tokens(rule: dict, width: int, height: int) -> int:
    """At most the tokens a crop becomes under a documented rule."""
    side = rule["pixels_per_token"]
    rows, columns = ceil(height / side), ceil(width / side)
    grid, separators = rows * columns, rows + columns
    cap = rule.get("max_tokens")
    if cap is not None:
        grid, separators = min(grid, cap), min(separators, cap + 1)
    return grid + separators + IMAGE_SLACK_TOKENS


def _micros(price: dict, input_tokens: int, output_tokens: int) -> int:
    cost = (
        input_tokens * price["input_micros_per_million"]
        + output_tokens * price["output_micros_per_million"]
    )
    return -(-cost // MILLION)


def call_micros(price: dict, crop_and_prompt: int | None) -> int:
    """The call's worst case: each request the lesser of (a) and (b).

    `crop_and_prompt` is None when the route documents no image rule, and then
    every request reserves (a).
    """
    output_cap = price.get("max_output_tokens") or OUTPUT_CAP
    input_cap = min(
        price["context_tokens"], price.get("max_input_tokens") or price["context_tokens"]
    )
    bound_a = _micros(price, input_cap, output_cap)
    total = 0
    for request in range(REQUESTS):
        if crop_and_prompt is None:
            total += bound_a
            continue
        tokens = crop_and_prompt
        if request:
            # The retry resends the crop, the first answer and the feedback.
            tokens += output_cap + FEEDBACK_BYTES + LATER_FRAMING_TOKENS
        total += min(bound_a, _micros(price, tokens, output_cap))
    return total


def reading_prompt_tokens(run) -> int:
    """The pinned instructions and the answer's schema, counted in bytes."""
    from ..prompts import PromptName
    from ..transcription import LiteralTranscription

    pinned = run.dependencies.get("prompts", {}).get(
        PromptName.LITERAL_TRANSCRIPTION.value
    ) or {}
    schema = json.dumps(LiteralTranscription.model_json_schema())
    return (
        len(pinned.get("text", "").encode())
        + len(schema.encode())
        + PROMPT_FRAMING_TOKENS
    )


def reading_reservation(run, step: str, floor):
    """A reading's reservation: its worst case, the stage's amount at least.

    None when the route has no price or no context length, or the run has no
    such crop: the step cannot be sized, and it blocks before the call.
    """
    prices = run.profile.execution.price_list
    if not floor or prices is None:
        return floor
    _, region_id, route = step.split(":", 2)
    region = next((r for r in run.regions if r.id == region_id), None)
    price = prices.get("models", {}).get(route)
    if region is None or not price or not price.get("context_tokens"):
        return None
    rule = price.get("image_tokens")
    crop_and_prompt = (
        image_tokens(rule, region.width, region.height) + reading_prompt_tokens(run)
        if rule
        else None
    )
    return max(floor, call_micros(price, crop_and_prompt))


def step_reservation(run, step: str):
    """A paid step's reservation: the stage's amount, or a reading's worst case.

    One function for the workflow, which reserves it, and for the cost record,
    which reports it, so the two never differ.
    """
    policy = run.profile.execution
    floor = (
        policy.stage_cost_reservations.for_step(step)
        if policy.stage_cost_reservations is not None
        else policy.request_cost_reservation_micros
    )
    if floor and step == "segment" and policy.price_list is not None:
        from .lane_costs import segmentation_cost
        service = policy.price_list.get("segmentation")
        if not service:
            return None
        base = segmentation_cost(policy.price_list,
            SAM_STARTUP_SECONDS + SAM_REQUEST_SECONDS + SAM_SHUTDOWN_SECONDS)
        boost = ceil((SAM_STARTUP_SECONDS + SAM_BOOST_SECONDS) * service["vcpus"]
            * service["vcpu_micros_per_million_seconds"] / MILLION)
        return max(floor, base + boost)
    if floor and step.startswith("transcribe:"):
        return reading_reservation(run, step, floor)
    if floor and step.startswith("first_pass:"):
        prices = policy.price_list
        price = (prices or {}).get("models", {}).get(run.profile.first_pass_route)
        if not price or not price.get("context_tokens"):
            return None  # No qualified numeric route price: refuse before call.
        # Each request at its input bound (first_pass.InputBoundModel enforces it).
        # The byte/image guard bounds payload size, but is not the provider's
        # tokenizer. Reserve the whole route context, including both requests.
        return max(floor, call_micros({**price, "max_input_tokens": None}, None))
    if floor and step == "parse" and policy.price_list is not None:
        # extract_with_agent uses the first reader route and permits two model
        # requests. The stage's historical USD .02 floor was not a bound.
        route = run.profile.routes[0] if run.profile.routes else None
        price = policy.price_list.get("models", {}).get(route)
        if not price or not price.get("context_tokens"):
            return None
        return max(floor, call_micros({**price, "max_input_tokens": None}, None))
    return floor


def image_rule(prices: dict, route: str) -> dict | None:
    """The route's documented image rule, or else the most conservative pinned
    rule on uncapped pixels (the coordinator's ruling of 2026-09-24)."""
    models = prices.get("models", {})
    rule = models.get(route, {}).get("image_tokens")
    if rule:
        return rule
    pinned = [m["image_tokens"] for m in models.values() if m.get("image_tokens")]
    if not pinned:
        return None
    return {"pixels_per_token": min(r["pixels_per_token"] for r in pinned)}


def request_input_tokens(messages, parameters, rule: dict | None) -> int | None:
    """At most the input tokens one request with these messages and tools becomes.

    Text counts a token per UTF-8 byte, which a byte-level tokenizer never
    exceeds; an image counts its tokens under `rule`; the chat template counts
    its framing. None when a part cannot be sized, so the request is refused.
    """
    import io

    from PIL import Image
    from pydantic_ai.messages import (
        BinaryContent,
        ModelRequest,
        RetryPromptPart,
        SystemPromptPart,
        TextContent,
        TextPart,
        ThinkingPart,
        ToolCallPart,
        ToolReturnPart,
        UserPromptPart,
    )

    texts, images = [], []
    instructions = parameters.instruction_parts
    texts += [part.content for part in instructions or []]
    for tool in [*parameters.function_tools, *parameters.output_tools]:
        # As the request carries it (HuggingFaceModel._map_tool_definition).
        function = {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters_json_schema,
        }
        texts.append(json.dumps({"type": "function", "function": function}))
    for message in messages:
        if not isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, ToolCallPart):
                    texts += [part.tool_name, part.args_as_json_str(), part.tool_call_id or ""]
                elif isinstance(part, TextPart | ThinkingPart):
                    texts.append(part.content)
            continue
        if instructions is None and message.instructions:
            texts.append(message.instructions)
        for part in message.parts:
            if isinstance(part, RetryPromptPart):
                texts.append(part.model_response())
            elif isinstance(part, ToolReturnPart):
                texts.append(part.model_response_str())
            elif isinstance(part, SystemPromptPart):
                texts.append(part.content)
            elif isinstance(part, UserPromptPart):
                content = part.content
                for item in [content] if isinstance(content, str) else content:
                    if isinstance(item, str | TextContent):
                        texts.append(item if isinstance(item, str) else item.content)
                    elif isinstance(item, BinaryContent) and item.is_image:
                        images.append(item.data)
                    else:
                        return None
            else:
                return None
    tokens = sum(len(text.encode()) for text in texts)
    for data in images:
        if rule is None:
            return None
        try:
            with Image.open(io.BytesIO(data)) as image:
                width, height = image.size
        except Exception:
            return None
        tokens += image_tokens(rule, width, height)
    return tokens + PROMPT_FRAMING_TOKENS + LATER_FRAMING_TOKENS * (len(messages) - 1)
