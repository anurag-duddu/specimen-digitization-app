"""The run's hard ceiling (FIELD_RESEARCH.md, Budget): reserve the worst case, settle the real cost.

Prices are the harness route's (profile price list, harness-deepseek): USD 0.20 per
million input tokens and USD 0.60 per million output tokens. No request leaves the
process: the models are pydantic_ai FunctionModels.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from specimen_digitization.field_research import budget
from specimen_digitization.field_research.budget import (
    DEFAULT_MAX_TOKENS,
    BudgetExhausted,
    CostMeter,
    MeteredModel,
)

INPUT_PRICE, OUTPUT_PRICE = 200_000, 600_000


def meter(cap: int = 1_000_000) -> CostMeter:
    return CostMeter(
        cap, input_micros_per_million=INPUT_PRICE, output_micros_per_million=OUTPUT_PRICE
    )


class Answer(BaseModel):
    text: str


def test_cost_is_integer_micros_rounded_up():
    m = meter()

    assert m.cost(1, 0) == 1  # 0.2 micros
    assert m.cost(1_000_000, 0) == INPUT_PRICE
    assert m.cost(1000, 100) == 260  # 200 + 60
    assert m.cost(-5, -5) == 0


def test_settle_replaces_the_reservation_with_the_actual_cost():
    async def scenario():
        m = meter(10_000)
        ticket = await m.reserve(20_000, 2048)
        worst = m.cost(20_000, 2048)
        assert (m.outstanding_micros, m.spent_micros) == (worst, 0)
        assert m.remaining_micros == 10_000 - worst

        actual = m.settle(ticket, 1200, 300)

        assert actual == m.cost(1200, 300) == 420
        assert (m.outstanding_micros, m.spent_micros) == (0, 420)
        assert m.remaining_micros == 10_000 - 420
        with pytest.raises(ValueError):
            m.settle(ticket, 1, 1)
        # A provider's negative count never makes a refund.
        assert m.settle(await m.reserve(10, 10), -100, -100) == 0
        assert m.spent_micros == 420

    asyncio.run(scenario())


def test_the_ceiling_is_never_exceeded_under_fifty_concurrent_reservations():
    async def scenario():
        m = meter(10_000)
        worst = m.cost(10_000, 2048)  # 2,000 + 1,229 = 3,229 micros
        peaks: list[int] = []

        async def expert(index: int) -> bool:
            await asyncio.sleep(0)
            try:
                ticket = await m.reserve(10_000, 2048)
            except BudgetExhausted:
                return False
            peaks.append(m.spent_micros + m.outstanding_micros)
            await asyncio.sleep(0.001 * (index % 3))
            # Half settle well below their reservation, freeing room for others.
            m.settle(ticket, 1000 if index % 2 else 10_000, 100 if index % 2 else 2048)
            peaks.append(m.spent_micros + m.outstanding_micros)
            return True

        granted = await asyncio.gather(*(expert(i) for i in range(50)))

        assert worst == 3229
        assert max(peaks) <= 10_000
        assert m.spent_micros <= 10_000 and m.outstanding_micros == 0
        assert 3 <= sum(granted) < 50

    asyncio.run(scenario())


def test_a_reservation_that_does_not_fit_waits_for_held_ones_to_settle():
    """Ten experts at once under a ceiling of two worst cases: each settles to
    a tenth of its reservation, so every one is granted in turn and the
    ceiling is never crossed."""
    async def scenario():
        worst = meter().cost(10_000, 2048)
        m = meter(2 * worst)
        peaks: list[int] = []

        async def expert() -> None:
            ticket = await m.reserve(10_000, 2048)
            peaks.append(m.spent_micros + m.outstanding_micros)
            await asyncio.sleep(0.001)
            m.settle(ticket, 1000, 200)

        await asyncio.gather(*(expert() for _ in range(10)))

        assert max(peaks) <= 2 * worst and m.outstanding_micros == 0
        assert m.spent_micros == 10 * m.cost(1000, 200) <= 2 * worst

    asyncio.run(scenario())


def test_a_reservation_is_refused_when_none_is_held_and_it_still_does_not_fit():
    """A true overrun: the held reservation settles to its whole worst case,
    so the waiting one still does not fit and nothing else can free room."""
    async def scenario():
        worst = meter().cost(10_000, 2048)
        m = meter(worst + worst // 2)
        held = await m.reserve(10_000, 2048)
        waiting = asyncio.ensure_future(m.reserve(10_000, 2048))
        await asyncio.sleep(0.001)
        assert not waiting.done()  # it waits while one is held
        m.settle(held, 10_000, 2048)
        with pytest.raises(BudgetExhausted):
            await waiting
        assert (m.spent_micros, m.outstanding_micros) == (worst, 0)
        with pytest.raises(BudgetExhausted):
            await m.reserve(10_000, 2048)

    asyncio.run(scenario())


def test_a_waiting_reservation_that_is_cancelled_holds_nothing():
    async def scenario():
        worst = meter().cost(10_000, 2048)
        m = meter(worst)
        held = await m.reserve(10_000, 2048)
        waiting = asyncio.ensure_future(m.reserve(10_000, 2048))
        await asyncio.sleep(0.001)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        m.settle(held, 100, 10)
        assert m.outstanding_micros == 0 and m._waiters == []

    asyncio.run(scenario())


def _final(info: AgentInfo, **args) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])


def test_metered_model_reserves_before_and_settles_after_each_request():
    m = meter()
    during: list[tuple[int, dict]] = []

    def script(messages, info: AgentInfo) -> ModelResponse:
        during.append((m.outstanding_micros, dict(info.model_settings or {})))
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart("echo", {"text": "a"})],
                usage=RequestUsage(input_tokens=1200, output_tokens=40),
            )
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, {"text": "done"})],
            usage=RequestUsage(input_tokens=1500, output_tokens=60),
        )

    model = MeteredModel(FunctionModel(script), m)
    agent = Agent(model, output_type=Answer, instructions="Answer.")

    @agent.tool_plain
    def echo(text: str) -> str:
        return text

    result = asyncio.run(agent.run("hello"))

    assert result.output.text == "done"
    # Each request held a worst case while it ran: input bytes plus 2048 output tokens.
    assert all(held >= m.cost(0, DEFAULT_MAX_TOKENS) for held, _ in during)
    # max_tokens is always set on what reaches the provider.
    assert all(settings["max_tokens"] == DEFAULT_MAX_TOKENS for _, settings in during)
    assert m.outstanding_micros == 0
    assert m.spent_micros == m.cost(1200, 40) + m.cost(1500, 60)
    assert (model.model_calls, model.cost_micros) == (2, m.spent_micros)


def test_a_smaller_max_tokens_bounds_the_reservation():
    m = meter()
    held: list[int] = []

    def script(messages, info):
        held.append(m.outstanding_micros)
        return _final(info, text="x")

    agent = Agent(MeteredModel(FunctionModel(script), m), output_type=Answer,
                  model_settings={"max_tokens": 10})
    asyncio.run(agent.run("hi"))

    assert held[0] < m.cost(0, DEFAULT_MAX_TOKENS)


def test_the_reservation_covers_the_chat_template_around_what_is_sent(monkeypatch):
    m = meter()
    template = budget.TEMPLATE_TOKENS
    held: list[int] = []
    monkeypatch.setattr(budget, "input_token_bound", lambda messages, parameters: 1000)

    def script(messages, info):
        held.append(m.outstanding_micros)
        # The provider counts its chat template's tokens around the messages too.
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"text": "x"})],
                             usage=RequestUsage(input_tokens=1000 + template, output_tokens=10))

    model = MeteredModel(FunctionModel(script), m)
    asyncio.run(Agent(model, output_type=Answer).run("hi"))

    assert template == 512
    assert held == [m.cost(1000 + template, DEFAULT_MAX_TOKENS)]
    assert m.spent_micros == m.cost(1000 + template, 10) <= held[0]


def test_a_request_over_the_input_bound_is_refused_before_it_is_sent():
    m = meter()
    sent: list[object] = []

    def script(messages, info):
        sent.append(messages)
        return _final(info, text="x")

    model = MeteredModel(FunctionModel(script), m, max_input_tokens=2000)
    agent = Agent(model, output_type=Answer, instructions="Rules. " * 50)

    with pytest.raises(budget.InputTooLarge):
        asyncio.run(agent.run("label text " * 200))

    assert sent == []
    assert (m.spent_micros, m.outstanding_micros, model.model_calls) == (0, 0, 0)


def test_a_call_that_would_cross_the_ceiling_is_not_sent():
    m = meter(cap=500)  # Less than one request's worst case.
    sent: list[object] = []

    def script(messages, info):
        sent.append(messages)
        return _final(info, text="x")

    with pytest.raises(BudgetExhausted):
        asyncio.run(Agent(MeteredModel(FunctionModel(script), m), output_type=Answer).run("hi"))

    assert sent == [] and m.spent_micros == 0


class _NoUsageModel(FunctionModel):
    async def request(self, messages, model_settings, model_request_parameters):
        response = await super().request(messages, model_settings, model_request_parameters)
        response.usage = RequestUsage()
        return response


def test_a_response_without_usage_and_a_failed_request_keep_their_worst_case():
    m = meter()
    held: list[int] = []

    def script(messages, info):
        held.append(m.outstanding_micros)
        return _final(info, text="x")

    model = MeteredModel(_NoUsageModel(script), m)
    asyncio.run(Agent(model, output_type=Answer).run("hi"))

    assert m.spent_micros == held[0] > 0 and m.outstanding_micros == 0

    failing = meter()

    def broken(messages, info):
        held.append(failing.outstanding_micros)
        raise RuntimeError("provider_request_failed")

    model = MeteredModel(FunctionModel(broken), failing)
    with pytest.raises(RuntimeError):
        asyncio.run(Agent(model, output_type=Answer).run("hi"))

    assert failing.spent_micros == held[-1] > 0 and failing.outstanding_micros == 0
    assert model.model_calls == 1


def test_a_streamed_request_is_metered_too():
    m = meter()

    async def stream(messages, info):
        yield "streamed "
        yield "answer"

    model = MeteredModel(FunctionModel(stream_function=stream), m)
    agent = Agent(model, output_type=str)

    async def scenario():
        async with agent.run_stream("hi") as run:
            text = await run.get_output()
        return text

    assert asyncio.run(scenario()) == "streamed answer"
    assert model.model_calls == 1 and m.spent_micros == model.cost_micros > 0
    assert m.outstanding_micros == 0


def test_meter_refuses_bad_prices():
    with pytest.raises(ValueError):
        CostMeter(-1, input_micros_per_million=1, output_micros_per_million=1)
    with pytest.raises(ValueError):
        CostMeter(1, input_micros_per_million=1.5, output_micros_per_million=1)  # type: ignore


def test_text_part_is_counted_in_the_input_bound():
    from pydantic_ai.messages import ModelRequest, UserPromptPart
    from pydantic_ai.models import ModelRequestParameters

    from specimen_digitization.field_research.budget import input_token_bound

    small = input_token_bound([ModelRequest([UserPromptPart("a")])], ModelRequestParameters())
    large = input_token_bound(
        [ModelRequest([UserPromptPart("a" * 1000)], instructions="rules"),
         ModelResponse([TextPart(chr(233) * 10)])],
        ModelRequestParameters(),
    )

    assert large >= small + 999 + len("rules") + 20
