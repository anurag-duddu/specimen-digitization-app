"""Deterministic retry decisions and explicit external-effect failure semantics."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import random
from .domain import LookupStatus


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
    """A reading stopped by its token limits (#153).

    It is a failed reading with a known outcome: its step completes with no
    observation, and the run goes on.
    """

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def reader_failure_is_recoverable(run, step: str) -> bool:
    """Whether a failed model call of this step is a known, retryable failure.

    A reader (``transcribe``) is a pure read. It writes nothing of its own: the
    parent saves its observation only after the call returns, so asking again
    cannot corrupt data or duplicate an observation, and costs one more
    reservation at most (a retry reserves again, and an attempt whose outcome is
    unknown keeps its reservation in full). A reader's failure is therefore known
    even where the provider may have billed (a timeout, a 5xx, a child that
    ended without an answer): the workflow retries it within ``max_attempts``,
    then completes the reading with no observation so the record goes to review
    (G6). It never blocks the run as ``external_outcome_unknown``.

    ``step`` is a workflow step (``transcribe:<region>:<route>``) or a model
    operation (``transcribe``). Every other step keeps its unknown outcome as a
    block: a first pass, the organiser, field research and every effectful step
    may have changed something that a repeat would change again. So does a
    reader of the evidence pilot, whose exact cohort reservations and zero
    retries never replay a paid call. This is the one place that rule lives;
    widening or narrowing it is this line.
    """
    return (
        step.split(":", 1)[0] == "transcribe"
        and "evidence_pilot" not in run.dependencies
    )


def failure_is_retryable(run, step: str, status: LookupStatus) -> bool:
    """Whether a known failure of this step is scheduled for another attempt.

    A provider that rate-limited, timed out or failed is asked again. A reader's
    malformed answer is too: it is a pure read and the next answer may be valid.
    A credential or permission failure is not (asking again repeats it), so it
    stays a block that names its cause.
    """
    if status in {
        LookupStatus.RATE_LIMITED,
        LookupStatus.TIMEOUT,
        LookupStatus.PROVIDER,
    }:
        return True
    return status == LookupStatus.MALFORMED and reader_failure_is_recoverable(
        run, step
    )


# HTTP statuses of a request the provider refuses as invalid: a bad request, an
# unknown model or route, an input too large, an unprocessable one.
REJECTED_HTTP_STATUSES = frozenset({400, 404, 413, 422})


def retry_after(value: str | None, current: datetime | None = None) -> int | None:
    if not value:
        return None
    try:
        if value.strip().isdigit():
            return max(0, int(value.strip()))
        import math

        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        # Rounded up, so a retry never comes sooner than the date asks.
        seconds = (date - (current or datetime.now(timezone.utc))).total_seconds()
        return max(0, math.ceil(seconds))
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


def run_agent_bounded(agent, prompt, *, timeout_seconds: float, usage_limits):
    import asyncio
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
        return {"max_tokens": output_cap}

    async def call():
        return await asyncio.wait_for(
            agent.run(
                prompt,
                usage_limits=usage_limits,
                model_settings=bounded_settings,
                # Counted in place, so a stopped run still reports its usage.
                usage=usage,
            ),
            timeout=timeout_seconds,
        )

    from pydantic_ai import capture_run_messages
    from pydantic_ai.exceptions import IncompleteToolCall
    from pydantic_ai.usage import RunUsage

    # A run stopped by its limits raises Pydantic AI's UsageLimitExceeded with
    # the messages it kept and the usage it counted, for the caller's record of
    # what the stopped call used (HARNESS.md section 3).
    usage = RunUsage()
    try:
        with capture_run_messages() as messages:
            return asyncio.run(call())
    except TimeoutError as exc:
        raise AdapterFailure(
            "provider_deadline_outcome_unknown", outcome_unknown=True
        ) from exc
    except ModelHTTPError as exc:
        if exc.status_code in REJECTED_HTTP_STATUSES:
            # The provider refused the request itself, and refuses it the same
            # way every time: a known block that names its cause, never retried
            # and never given up on in silence. 402 is not here: it is transient.
            raise AdapterFailure("model_request_rejected", LookupStatus.POLICY) from exc
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
    except UsageLimitExceeded as exc:
        exc.run_messages, exc.run_usage = messages, usage
        raise
    except UnexpectedModelBehavior as exc:
        last = next((m for m in reversed(messages) if m.kind == "response"), None)
        if isinstance(exc, IncompleteToolCall) or (
            last is not None and last.finish_reason == "length"
        ):
            # Cut off at its output cap: a cap hit, which every caller routes as
            # it routes the run's own limits, not a malformed answer (HARNESS.md
            # section 3, agreed with S3).
            stopped = UsageLimitExceeded("The answer was cut off at its output cap")
            stopped.run_messages, stopped.run_usage = messages, usage
            raise stopped from exc
        # The provider answered, but its output stayed invalid after the retry.
        raise AdapterFailure(
            "model_malformed_response", LookupStatus.MALFORMED, outcome_unknown=False
        ) from exc
