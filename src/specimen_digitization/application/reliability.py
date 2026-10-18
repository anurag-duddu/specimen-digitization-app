"""Deterministic retry decisions and explicit external-effect failure semantics."""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import random
from .domain import LookupStatus


class AdapterFailure(RuntimeError):
    """A known failure of an external call.

    ``refused`` is set only when the provider refused the call before doing any
    work: an HTTP 429 answering the call's first request (``run_agent_bounded``).
    Nothing was generated, so nothing is billed, and the call is recorded at no
    cost (``lane_costs.record_refused``).

    ``usage`` is set only when the provider reported the tokens of every
    request the call sent (``reported_usage``): an answer that stayed malformed
    after its retry. The failed call is then recorded at what those tokens cost
    (``lane_costs.record_step``). Every other failure has no usage and stays
    reserved in full.
    """

    def __init__(
        self,
        code: str,
        status: LookupStatus = LookupStatus.PROVIDER,
        *,
        retry_after_seconds: int | None = None,
        outcome_unknown=False,
        refused=False,
        usage: dict | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.status = status
        self.retry_after_seconds = retry_after_seconds
        self.outcome_unknown = outcome_unknown
        self.refused = refused
        self.usage = usage


class ReadingStopped(RuntimeError):
    """A reading stopped by its token limits (#153).

    It is a failed reading with a known outcome: its step completes with no
    observation, and the run goes on. ``usage`` is what the provider reported
    the stopped call used, as ``AdapterFailure.usage`` is, or None.
    """

    def __init__(self, code: str, usage: dict | None = None):
        super().__init__(code)
        self.code = code
        self.usage = usage


def reported_usage(
    messages, usage, usage_limits=None, *, stopped=False, completed=False
) -> dict | None:
    """The tokens a model call's provider reported, when it reported every request's.

    ``usage`` is the call's ``RunUsage``. Pydantic AI adds an answer's tokens
    to it as the answer arrives, then checks the token limits, and only then
    counts the answer in ``usage.requests`` and keeps it in ``messages``.
    ``messages`` holds every request from just before it would be sent. So
    when ``usage.requests`` equals the requests in ``messages``, every request
    was answered and its tokens counted.

    The agent may hold one request more:
    - In a call ``stopped`` by its limits (``UsageLimitExceeded``), either the
      limits stopped it before it was sent, or it was answered and its tokens
      counted before the limit refused the answer. Its tokens are counted
      either way.
    - In a call whose answers used up its ``request_limit``, it cannot have
      been sent (Pydantic AI refuses it first): a malformed answer's retry
      prompt, queued after the last answer. The production model reads all set
      ``request_limit=2``; with a limit the answers did not use up there is no
      such proof, and the call is held.
    - In a ``completed`` call (one that returned its output), the output
      tool's return: Pydantic AI queues it as the last message, after the
      answer that ended the call, and nothing sends it. Every request before
      that answer was answered, or the call could not have gone on.

    None in every other case: a sent request with no counted answer (a reply
    the model client could not read, which the provider may still have
    billed), or an answer that reported no input tokens. That spend is unknown
    and stays reserved in full.
    """
    if usage is None or messages is None:
        return None
    sent = sum(m.kind == "request" for m in messages)
    answered = usage.requests
    limit = getattr(usage_limits, "request_limit", None)
    one_more = sent == answered + 1 and (
        stopped
        or (completed and messages[-1].kind == "request")
        or (limit is not None and answered >= limit)
    )
    answers = [m for m in messages if m.kind == "response"]
    if (
        not (sent == answered or one_more)
        or not usage.input_tokens
        or any(not m.usage.input_tokens for m in answers)
    ):
        return None
    return {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}


def checked_usage(value) -> dict | None:
    """Reported usage as the cost record prices it: two token counts, input above
    zero. Anything else (None, another shape, a value from across the model
    child's process boundary that is not this) is unknown usage, which keeps the
    call reserved in full.
    """
    if (
        isinstance(value, dict)
        and value.keys() == {"input_tokens", "output_tokens"}
        and all(type(n) is int and n >= 0 for n in value.values())
        and value["input_tokens"] > 0
    ):
        return dict(value)
    return None


def stopped_usage(stop) -> dict | None:
    """What a call stopped by its limits used (``run_agent_bounded``), or None."""
    return getattr(stop, "reported_usage", None)


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
    operation (``transcribe``). The first pass has its own narrower policy below;
    the organiser, field research and every effectful step keep their unknown
    outcome as a block. So does a reader of the evidence pilot, whose exact
    cohort reservations and zero
    retries never replay a paid call. This is the one place that rule lives;
    widening or narrowing it is this line.
    """
    return (
        step.split(":", 1)[0] == "transcribe"
        and "evidence_pilot" not in run.dependencies
    )


def first_pass_failure_is_recoverable(run, step: str) -> bool:
    """Whether a first-pass comparison may recover a transient failed call.

    This tool-free model call compares retained readings and a retained crop.
    Its child only writes content-addressed provenance; the parent records one
    decision per region after the call returns. Repeating a failed comparison
    cannot duplicate a specimen or publish a result. It can bill again: every
    uncertain attempt keeps its full reservation and each retry reserves anew.

    This does not make malformed answers or contract failures retryable, does
    not clear an already persisted unknown outcome, and does not cover the
    evidence pilot or any organiser, research, or publication operation.
    """
    return (
        step.split(":", 1)[0] == "first_pass"
        and "evidence_pilot" not in run.dependencies
    )


def extraction_failure_is_recoverable(run, step: str) -> bool:
    """Whether the organiser's extraction call (``parse``'s one model call,
    ``harness.extract_with_agent``) may recover a failed call.

    Like the first pass, it is a tool-free model read: it reads the run's
    retained readings, its child writes only content-addressed provenance, and
    the parent applies the candidates after the call returns. Repeating it
    cannot duplicate a specimen or publish a result. It can bill again: every
    uncertain attempt keeps its full reservation and each retry reserves anew.
    When its attempts are used up, or its answer stays malformed, the
    extraction is given up on and the run goes on without its candidates
    (``Workflow.extraction_has_no_attempt_left``).

    ``step`` is the workflow step (``parse``) or the model operation
    (``extract``). The evidence pilot is excluded, as it is from reader and
    first-pass recovery.
    """
    return (
        step.split(":", 1)[0] in {"parse", "extract"}
        and "evidence_pilot" not in run.dependencies
    )


def model_read_is_recoverable(run, step: str) -> bool:
    """A reader, an ordinary first pass or the organiser's extraction: the model
    reads whose failed calls the workflow repeats and, at the end, gives up on."""
    return (
        reader_failure_is_recoverable(run, step)
        or first_pass_failure_is_recoverable(run, step)
        or extraction_failure_is_recoverable(run, step)
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


# The least wait, in seconds, before a rate-limited step is sent again: after
# its first attempt, then after every later one. The backoff alone waits 2 to 4
# seconds after a first attempt and 4 to 8 after a second, too short for a
# provider's rate limit to clear, and the model calls' failures carry no
# Retry-After (``AdapterFailure.retry_after_seconds`` is None).
RATE_LIMIT_FLOORS = (30, 90)


def retry_delay(
    attempt: int,
    provider_seconds: int | None = None,
    random_value=None,
    *,
    rate_limited: bool = False,
) -> float:
    # Jitter never schedules before a provider's Retry-After minimum.
    jitter = (random_value or random.random)()
    base = min(300, 2 ** min(attempt, 8))
    if rate_limited:
        # Long enough for a provider's rate limit to clear, jittered upward as
        # every other wait is, so runs refused together are not sent together.
        floor = RATE_LIMIT_FLOORS[min(max(attempt, 1), len(RATE_LIMIT_FLOORS)) - 1]
        base = max(base, floor)
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
        # Preserve that uncertainty. Only the workflow's explicitly repeatable
        # model reads may retry, reserving again without releasing this cost.
        # A 429 that answers the call's first request is a refusal before any
        # work: no answer came back, so nothing was generated or billed. One
        # after an answer (the agent's output retry) is not: that answer was.
        # "Proven" assumes no layer under these routes retries on its own: the
        # huggingface_hub/httpx client sends each request once, and Pydantic AI
        # does not retry HTTP errors. A client with built-in retries (the OpenAI
        # SDK retries twice by default) could put a billed attempt before a 429.
        refused = exc.status_code == 429 and not any(
            m.kind == "response" for m in messages
        )
        raise AdapterFailure(
            "model_" + status.value,
            status,
            outcome_unknown=exc.status_code >= 500,
            refused=refused,
        ) from exc
    except UsageLimitExceeded as exc:
        exc.run_messages, exc.run_usage = messages, usage
        exc.reported_usage = reported_usage(messages, usage, usage_limits, stopped=True)
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
            stopped.reported_usage = reported_usage(messages, usage, usage_limits)
            raise stopped from exc
        # The provider answered, but its output stayed invalid after the retry.
        # The tokens it reported are what the call cost (PLAN 4.3).
        raise AdapterFailure(
            "model_malformed_response",
            LookupStatus.MALFORMED,
            outcome_unknown=False,
            usage=reported_usage(messages, usage, usage_limits),
        ) from exc
