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


def run_agent_bounded(agent, prompt, *, timeout_seconds: float, usage_limits):
    import asyncio
    from pydantic_ai.exceptions import ModelHTTPError

    async def call():
        return await asyncio.wait_for(
            agent.run(prompt, usage_limits=usage_limits), timeout=timeout_seconds
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
