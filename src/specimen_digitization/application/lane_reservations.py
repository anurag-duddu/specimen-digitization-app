"""A model call that sends a crop reserves its worst case (docs/execution/golive/LANE.md, T2b).

PLAN 4.3 and the coordinator's ruling of 2026-09-24. Before the call, it
reserves for each request it may make; each request reserves the lesser of
(a) the route's context length at the input price plus the output cap, and
(b), where the route documents its image-token rule, the crop's tokens under
that rule plus the prompt and the output cap. The stage's reservation is the
floor.
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


def call_micros(price: dict, crop_and_prompt: int | None, output_cap=OUTPUT_CAP) -> int:
    """The call's worst case: each request the lesser of (a) and (b).

    `crop_and_prompt` is None when the route documents no image rule, and then
    every request reserves (a).
    """
    bound_a = _micros(price, price["context_tokens"], output_cap)
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
    if floor and step.startswith("transcribe:"):
        return reading_reservation(run, step, floor)
    return floor
