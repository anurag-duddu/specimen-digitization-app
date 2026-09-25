"""Deterministic retry decisions and explicit external-effect failure semantics."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import random
from .domain import LookupStatus

# What a later request's validation feedback may carry (HARNESS.md section 15).
RETRY_FEEDBACK_MAX_ERRORS = 20
RETRY_FEEDBACK_MAX_BYTES = 8192
# The chat template around a later request's new parts, in tokens.
LATER_REQUEST_FRAMING_TOKENS = 256


class AdapterFailure(RuntimeError):
    def __init__(
        self,
        code: str,
        status: LookupStatus = LookupStatus.PROVIDER,
        *,
        retry_after_seconds: int | None = None,
        outcome_unknown=False,
    ):
        super().__init__(code)
        self.code = code
        self.status = status
        self.retry_after_seconds = retry_after_seconds
        self.outcome_unknown = outcome_unknown


class ReadingStopped(RuntimeError):
    """A reading stopped by its limits (G6, G30; HARNESS.md section 15).

    Its token limits or its reservation stopped it after the provider answered.
    It is a failed reading: the step completes with no observation.
    """

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def retry_after(value: str | None, current: datetime | None = None) -> int | None:
    if not value:
        return None
    try:
        if value.strip().isdigit():
            return max(0, int(value.strip()))
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return max(
            0, int((date - (current or datetime.now(timezone.utc))).total_seconds())
        )
    except (ValueError, TypeError, OverflowError):
        return None


def retry_delay(
    attempt: int, provider_seconds: int | None = None, random_value=None
) -> float:
    # Jitter never schedules before a provider's Retry-After minimum.
    jitter = (random_value or random.random)()
    base = min(300, 2 ** min(attempt, 8))
    return max(float(provider_seconds or 0), base) + jitter * base


def has_active_lease(run, current: datetime | None = None) -> bool:
    return bool(
        run.lease_until
        and datetime.fromisoformat(run.lease_until)
        > (current or datetime.now(timezone.utc))
    )


def _shown(value, limit):
    """A value short enough to show as it is; a longer one cut, as text."""
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return value if len(text) <= limit else text[:limit] + "…"


def bounded_feedback(part):
    """A retry prompt whose feedback, as the provider receives it, fits the bound."""
    if isinstance(part.content, str):
        if len(part.model_response().encode()) <= RETRY_FEEDBACK_MAX_BYTES:
            return part
        frame = len(replace(part, content="…").model_response().encode())
        text = part.content.encode()[: RETRY_FEEDBACK_MAX_BYTES - frame]
        return replace(part, content=text.decode(errors="ignore") + "…")
    errors = [
        {
            **{k: v for k, v in error.items() if k not in {"ctx", "url"}},
            "msg": _shown(error["msg"], 300),
            **({"input": _shown(error["input"], 200)} if "input" in error else {}),
        }
        for error in part.content
    ]
    keep = min(len(errors), RETRY_FEEDBACK_MAX_ERRORS)
    while True:
        shown = errors[:keep]
        if keep < len(errors):
            shown.append(
                {
                    "type": "too_many_errors",
                    "loc": (),
                    "msg": f"{len(errors) - keep} more errors not shown",
                    "input": None,
                }
            )
        bounded = replace(part, content=shown)
        if len(bounded.model_response().encode()) <= RETRY_FEEDBACK_MAX_BYTES or not keep:
            return bounded
        keep //= 2


def bounded_messages(messages):
    """The conversation with every retry prompt's feedback within its bound."""
    from pydantic_ai.messages import ModelRequest, RetryPromptPart

    return [
        replace(
            message,
            parts=[
                bounded_feedback(p) if isinstance(p, RetryPromptPart) else p
                for p in message.parts
            ],
        )
        if isinstance(message, ModelRequest)
        and any(isinstance(p, RetryPromptPart) for p in message.parts)
        else message
        for message in messages
    ]


@dataclass(frozen=True)
class CallBudget:
    """A call's reservation and its route's prices, in micro-dollars (G30)."""

    reserved_micros: int
    input_micros_per_million: int
    output_micros_per_million: int

    def micros(self, input_tokens, output_tokens):
        cost = (
            input_tokens * self.input_micros_per_million
            + output_tokens * self.output_micros_per_million
        )
        return -(-cost // 1_000_000)


def _later_request_input(messages):
    """At most the next request's input tokens, or None when it cannot be bounded."""
    from pydantic_ai.messages import (
        ModelResponse,
        RetryPromptPart,
        SystemPromptPart,
        ToolReturnPart,
        UserPromptPart,
    )

    last = [m for m in messages if isinstance(m, ModelResponse)][-1]
    if not last.usage.input_tokens:
        return None
    new = 0
    for part in messages[-1].parts:
        if isinstance(part, RetryPromptPart):
            text = bounded_feedback(part).model_response()
        elif isinstance(part, ToolReturnPart):
            text = part.model_response_str()
        elif isinstance(part, SystemPromptPart):
            text = part.content
        elif isinstance(part, UserPromptPart) and isinstance(part.content, str):
            text = part.content
        elif isinstance(part, UserPromptPart) and all(
            isinstance(item, str) for item in part.content
        ):
            text = "".join(part.content)
        else:
            return None  # An image or another part a byte count cannot bound.
        new += len(text.encode())
    return (
        last.usage.input_tokens
        + last.usage.output_tokens
        + new
        + LATER_REQUEST_FRAMING_TOKENS
    )


def run_agent_bounded(
    agent, prompt, *, timeout_seconds: float, usage_limits, budget=None
):
    import asyncio
    from pydantic_ai.messages import ModelResponse
    from pydantic_ai.exceptions import (
        ModelHTTPError,
        UnexpectedModelBehavior,
        UsageLimitExceeded,
    )

    # UsageLimits checks returned token usage; it does not tell the provider to
    # stop generation. Bound each initial/retry response at request time too.
    # Input/image billing and aggregate monetary reservations remain separate.
    def bounded_settings(ctx):
        # Pydantic resolves model/agent settings (including callables) before
        # this per-request layer. Do not evaluate an agent callback a second time.
        caps = [4096]
        for settings in (getattr(ctx.model, "settings", None), ctx.model_settings):
            if settings and settings.get("max_tokens") is not None:
                caps.append(settings["max_tokens"])
        limits = ctx.usage_limits
        if limits.output_tokens_limit is not None:
            caps.append(limits.output_tokens_limit - ctx.usage.output_tokens)
        if limits.total_tokens_limit is not None:
            # The next prompt's input/image tokens are not yet known; this is
            # a remaining-generation bound, not a total-cost guarantee.
            caps.append(limits.total_tokens_limit - ctx.usage.total_tokens)
        output_cap = min(caps)
        if output_cap <= 0:
            raise UsageLimitExceeded("No output token allowance remains")
        # A later request goes only if it cannot cross the call's reservation
        # (HARNESS.md section 15). The lane sized the reservation for the first.
        if budget is not None and any(isinstance(m, ModelResponse) for m in ctx.messages):
            next_input = _later_request_input(ctx.messages)
            if next_input is None or (
                budget.micros(ctx.usage.input_tokens, ctx.usage.output_tokens)
                + budget.micros(next_input, output_cap)
                > budget.reserved_micros
            ):
                raise UsageLimitExceeded(
                    "The next request could cross the call's reservation"
                )
        return {"max_tokens": output_cap}

    async def call():
        return await asyncio.wait_for(
            agent.run(
                prompt,
                usage_limits=usage_limits,
                model_settings=bounded_settings,
            ),
            timeout=timeout_seconds,
        )

    try:
        return asyncio.run(call())
    except TimeoutError as exc:
        raise AdapterFailure(
            "provider_deadline_outcome_unknown", outcome_unknown=True
        ) from exc
    except ModelHTTPError as exc:
        status = {
            401: LookupStatus.AUTHENTICATION,
            403: LookupStatus.AUTHORIZATION,
            429: LookupStatus.RATE_LIMITED,
        }.get(exc.status_code, LookupStatus.PROVIDER)
        # A gateway/server failure may follow an accepted billable effect.
        # A workflow retry must never turn an ambiguous 5xx into duplicate spend.
        raise AdapterFailure(
            "model_" + status.value, status, outcome_unknown=exc.status_code >= 500
        ) from exc
    except UnexpectedModelBehavior as exc:
        # The provider answered, but its output stayed invalid after the retry.
        raise AdapterFailure(
            "model_malformed_response", LookupStatus.MALFORMED, outcome_unknown=False
        ) from exc
