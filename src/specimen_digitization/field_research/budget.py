"""The hard per-run ceiling on model spend (owner, 2026-10-03: USD 1 per run).

Before every model call the run reserves that call's worst case from what is
left of its ceiling, and settles to the real usage after (FIELD_RESEARCH.md,
Budget). A call whose worst case does not fit is never sent, so the ceiling
cannot be crossed however many experts share the meter. Money is integer
micro-dollars, always rounded up.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelRequest
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings
from pydantic_core import to_jsonable_python

MILLION = 1_000_000
# Every request is capped at this many output tokens unless its settings say less.
DEFAULT_MAX_TOKENS = 2048
# Far above what one field's expert needs (instructions, every reading, a few
# source answers); a request over it means something grew without bound.
DEFAULT_MAX_INPUT_TOKENS = 48_000
# The provider's chat template around what is sent: role markers and the tool
# and output schemas as it renders them (lane_reservations.PROMPT_FRAMING_TOKENS).
TEMPLATE_TOKENS = 512


class BudgetExhausted(Exception):
    """A model call was refused before it was sent: it could cross the run's ceiling."""


class InputTooLarge(BudgetExhausted):
    """A model call was refused before it was sent: what it would send is over the input bound."""


class CostMeter:
    """One run's ceiling, shared by every expert of the run."""

    def __init__(
        self,
        cap_micros: int,
        *,
        input_micros_per_million: int,
        output_micros_per_million: int,
    ) -> None:
        for value in (cap_micros, input_micros_per_million, output_micros_per_million):
            if type(value) is not int or value < 0:
                raise ValueError("a ceiling and its prices are non-negative integer micros")
        self.cap_micros = cap_micros
        self.input_micros_per_million = input_micros_per_million
        self.output_micros_per_million = output_micros_per_million
        self._lock = asyncio.Lock()
        self._tickets: dict[int, int] = {}
        self._next_ticket = 0
        self._spent = 0
        self._outstanding = 0

    def cost(self, input_tokens: int, output_tokens: int) -> int:
        """Micro-dollars for this many tokens, rounded up (as lane_reservations prices)."""
        total = (
            max(0, input_tokens) * self.input_micros_per_million
            + max(0, output_tokens) * self.output_micros_per_million
        )
        return -(-total // MILLION)

    async def reserve(self, input_tokens: int, output_tokens: int) -> int:
        """Hold a call's worst case; raise BudgetExhausted when it does not fit."""
        worst = self.cost(input_tokens, output_tokens)
        async with self._lock:
            if self._spent + self._outstanding + worst > self.cap_micros:
                raise BudgetExhausted("run_cost_ceiling")
            ticket = self._next_ticket
            self._next_ticket += 1
            self._tickets[ticket] = worst
            self._outstanding += worst
            return ticket

    def settle(self, ticket: int, input_tokens: int, output_tokens: int) -> int:
        """Replace a reservation with the call's actual cost; return that cost."""
        # No await between the lookup and the update, so no lock is needed here.
        reserved = self._tickets.pop(ticket, None)
        if reserved is None:
            raise ValueError("unknown or already settled reservation")
        actual = self.cost(input_tokens, output_tokens)
        self._outstanding -= reserved
        self._spent += actual
        return actual

    @property
    def spent_micros(self) -> int:
        return self._spent

    @property
    def outstanding_micros(self) -> int:
        return self._outstanding

    @property
    def remaining_micros(self) -> int:
        return max(0, self.cap_micros - self._spent - self._outstanding)


def _json_bytes(value: Any) -> int:
    return len(json.dumps(to_jsonable_python(value), ensure_ascii=False).encode())


def input_token_bound(
    messages: list[ModelMessage], parameters: ModelRequestParameters
) -> int:
    """At most the input tokens a request can be: the UTF-8 bytes of all it sends.

    A byte-level tokenizer never makes more tokens than bytes. The count takes the
    instructions once (the model sends only the current ones), every part of every
    message serialized with its metadata, and the JSON of the tool definitions and
    the output schema, so it only ever over-counts.
    """
    if parameters.instruction_parts is not None:
        instructions = "\n\n".join(part.content for part in parameters.instruction_parts)
    else:
        instructions = next(
            (
                m.instructions
                for m in reversed(messages)
                if isinstance(m, ModelRequest) and m.instructions is not None
            ),
            "",
        )
    without = [
        dataclasses.replace(m, instructions=None) if isinstance(m, ModelRequest) else m
        for m in messages
    ]
    total = len(instructions.encode()) + len(ModelMessagesTypeAdapter.dump_json(without))
    total += _json_bytes(parameters.function_tools) + _json_bytes(parameters.output_tools)
    if parameters.output_object is not None:
        total += _json_bytes(parameters.output_object)
    return total


class MeteredModel(WrapperModel):
    """A model whose every request is reserved against a CostMeter before it is sent.

    The reservation is the request's input bound plus the chat template's
    TEMPLATE_TOKENS, so the usage a provider reports cannot exceed it. Settled
    from the provider's reported usage; a request that reports none, or that
    fails or is cancelled after it may have been sent, keeps its worst case as
    spent. `model_calls` and `cost_micros` count this instance's own requests.
    """

    def __init__(
        self,
        wrapped: Model,
        meter: CostMeter,
        *,
        max_input_tokens: int = DEFAULT_MAX_INPUT_TOKENS,
        default_max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        super().__init__(wrapped)
        self.meter = meter
        self.max_input_tokens = max_input_tokens
        self.default_max_tokens = default_max_tokens
        self.model_calls = 0
        self.cost_micros = 0

    def _bounds(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> tuple[ModelSettings, int, int]:
        settings: ModelSettings = dict(model_settings or {})  # type: ignore[assignment]
        # The wrapped model merges its own settings under these; measure what it will send.
        merged, prepared = self.prepare_request(settings, model_request_parameters)
        max_tokens = (merged or {}).get("max_tokens")
        if max_tokens is None:
            max_tokens = settings["max_tokens"] = self.default_max_tokens
        input_bound = input_token_bound(messages, prepared)
        if input_bound > self.max_input_tokens:
            raise InputTooLarge("model_input_over_bound")
        return settings, input_bound + TEMPLATE_TOKENS, max_tokens

    def _settle(self, ticket: int, input_tokens: int, output_tokens: int) -> None:
        self.model_calls += 1
        self.cost_micros += self.meter.settle(ticket, input_tokens, output_tokens)

    async def request(self, messages, model_settings, model_request_parameters):
        settings, input_bound, output_bound = self._bounds(
            messages, model_settings, model_request_parameters
        )
        ticket = await self.meter.reserve(input_bound, output_bound)
        try:
            response = await self.wrapped.request(messages, settings, model_request_parameters)
        except BaseException:
            self._settle(ticket, input_bound, output_bound)
            raise
        usage = response.usage
        if usage.has_values():
            self._settle(ticket, usage.input_tokens, usage.output_tokens)
        else:
            self._settle(ticket, input_bound, output_bound)
        return response

    @asynccontextmanager
    async def request_stream(
        self, messages, model_settings, model_request_parameters, run_context=None
    ) -> AsyncIterator[StreamedResponse]:
        settings, input_bound, output_bound = self._bounds(
            messages, model_settings, model_request_parameters
        )
        ticket = await self.meter.reserve(input_bound, output_bound)
        stream: StreamedResponse | None = None
        completed = False
        try:
            async with self.wrapped.request_stream(
                messages, settings, model_request_parameters, run_context
            ) as stream:
                yield stream
            completed = True
        finally:
            # A stream cut short may have been billed for more than it reported.
            usage = stream.usage if completed and stream is not None else None
            if usage is not None and usage.has_values():
                self._settle(ticket, usage.input_tokens, usage.output_tokens)
            else:
                self._settle(ticket, input_bound, output_bound)
