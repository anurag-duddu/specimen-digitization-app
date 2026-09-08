"""Persisted circuit admission only; never retries or reconciles workflow effects."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Callable, Literal, Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import Field, ValidationError, model_validator

from .authority_registry import Frozen, canonical, digest


class CircuitConflict(Exception):
    """Persistence CAS lost; safe to reload within the bounded attempt budget."""


class CircuitStore(Protocol):
    def load(self, key: str) -> tuple[int, dict] | None: ...
    def compare_and_swap(
        self, key: str, expected_revision: int | None, state: dict
    ) -> int: ...


class CircuitKey(Frozen):
    organization_id: str = Field(min_length=1, max_length=100)
    collection_id: str = Field(min_length=1, max_length=100)
    provider: str = Field(pattern=r"^[a-zA-Z0-9_.-]{1,100}$")
    config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def fingerprint(self) -> str:
        return digest(canonical(self.model_dump()).encode())

    @property
    def storage_key(self) -> str:
        # UUID fits the existing worker_cursor key schema; no tenant/provider text
        # or credentials are exposed in persistence keys.
        return str(
            uuid5(NAMESPACE_URL, "specimen:provider-circuit:v1:" + self.fingerprint)
        )


class CircuitPolicy(Frozen):
    failure_threshold: int = Field(default=3, ge=1, le=100, strict=True)
    cooldown_seconds: int = Field(default=30, ge=1, le=300, strict=True)
    max_cooldown_seconds: int = Field(default=300, ge=1, le=300, strict=True)
    max_cas_attempts: int = Field(default=4, ge=1, le=4, strict=True)
    max_inflight: int = Field(default=128, ge=1, le=128, strict=True)
    max_lease_seconds: int = Field(default=300, ge=1, le=300, strict=True)

    @model_validator(mode="after")
    def ordered_cooldown(self):
        if self.cooldown_seconds > self.max_cooldown_seconds:
            raise ValueError("invalid_policy_cooldown_order")
        return self


class PermitToken(Frozen):
    storage_key: str
    fingerprint: str
    token_id: str
    epoch: int = Field(ge=0, strict=True)
    expires_at_ms: int = Field(ge=0, le=253402300799000, strict=True)
    probe: bool


class PendingPermit(Frozen):
    token_id: str = Field(min_length=1)
    epoch: int = Field(ge=0, strict=True)
    expires_at_ms: int = Field(ge=0, le=253402300799000, strict=True)


class CircuitState(Frozen):
    schema_version: Literal[1] = 1
    fingerprint: str
    policy_sha256: str
    state: Literal["CLOSED", "OPEN", "HALF_OPEN"] = "CLOSED"
    epoch: int = Field(default=0, ge=0, strict=True)
    transient_failures: int = Field(default=0, ge=0, le=10000, strict=True)
    open_count: int = Field(default=0, ge=0, le=10000, strict=True)
    open_until_ms: int | None = Field(
        default=None, ge=0, le=253402300799000, strict=True
    )
    last_clock_ms: int = Field(ge=0, le=253402300799000, strict=True)
    pending: tuple[PendingPermit, ...] = Field(default=(), max_length=128)
    last_reason: str = "initial"
    last_failure_class: (
        Literal[
            "rate_limited",
            "timeout",
            "provider_error",
            "authentication_error",
            "authorization_error",
            "policy_blocked",
            "malformed_response",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def consistent(self):
        if len({p.token_id for p in self.pending}) != len(self.pending):
            raise ValueError("duplicate_pending_tokens")
        if any(p.epoch != self.epoch for p in self.pending):
            raise ValueError("pending_epoch_mismatch")
        if self.state == "OPEN" and (self.open_until_ms is None or self.pending):
            raise ValueError("invalid_open_state")
        if self.state != "OPEN" and self.open_until_ms is not None:
            raise ValueError("unexpected_open_deadline")
        if self.state == "HALF_OPEN" and len(self.pending) != 1:
            raise ValueError("half_open_requires_one_probe")
        return self


class Admission(Frozen):
    status: Literal["permitted", "open", "busy", "blocked"]
    token: PermitToken | None = None
    retry_at: datetime | None = None
    reason: str


class CircuitOutcome(Frozen):
    status: Literal["recorded", "stale", "blocked"]
    reason: str
    retry_at: datetime | None = None


class _Blocked(Exception):
    pass


def _date(milliseconds: int | None) -> datetime | None:
    return (
        datetime.fromtimestamp(milliseconds / 1000, timezone.utc)
        if milliseconds is not None
        else None
    )


class ProviderCircuit:
    """Injected UTC clock and persistent CAS; no networking, sleeping or secrets.

    Only the worker holding an admitted token can report its outcome. These are
    fencing tokens, not authentication credentials. The outer workflow owns
    authorization, external-effect intent, retries and outcome-unknown recovery.
    """

    def __init__(
        self,
        store: CircuitStore,
        clock: Callable[[], datetime],
        policy: CircuitPolicy = CircuitPolicy(),
    ):
        if not isinstance(policy, CircuitPolicy):
            raise ValueError("invalid_circuit_policy")
        self.store, self.clock, self.policy = store, clock, policy
        self.policy_sha256 = digest(canonical(policy.model_dump()).encode())

    def _now(self) -> int:
        try:
            value = self.clock()
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() != timedelta(0)
            ):
                raise ValueError("UTC clock required")
            milliseconds = math.floor(value.timestamp() * 1000)
            if not 0 <= milliseconds <= 253402214399000:
                raise ValueError("clock outside representable lease/deadline range")
            return milliseconds
        except Exception as exc:
            raise _Blocked("clock_invalid") from exc

    def _load(
        self, key: str, fingerprint: str, now: int
    ) -> tuple[int | None, CircuitState]:
        try:
            loaded = self.store.load(key)
        except Exception as exc:
            raise _Blocked("circuit_storage_unavailable") from exc
        if loaded is None:
            return None, CircuitState(
                fingerprint=fingerprint,
                policy_sha256=self.policy_sha256,
                last_clock_ms=now,
            )
        try:
            revision, data = loaded
            if type(revision) is not int or revision < 0 or not isinstance(data, dict):
                raise ValueError("invalid persistence envelope")
            state = CircuitState.model_validate(data)
        except (ValueError, TypeError, ValidationError) as exc:
            raise _Blocked("circuit_state_malformed") from exc
        if (
            state.fingerprint != fingerprint
            or state.policy_sha256 != self.policy_sha256
        ):
            raise _Blocked("circuit_identity_or_policy_mismatch")
        if now < state.last_clock_ms:
            raise _Blocked("clock_regressed")
        return revision, state

    def _save(self, key: str, revision: int | None, state: CircuitState) -> None:
        try:
            # Validate model_copy mutations before persistence.
            state = CircuitState.model_validate(state.model_dump())
            new_revision = self.store.compare_and_swap(
                key, revision, state.model_dump(mode="json")
            )
            if (
                type(new_revision) is not int
                or new_revision < 0
                or (revision is not None and new_revision <= revision)
            ):
                raise ValueError("invalid CAS acknowledgement")
        except CircuitConflict:
            raise
        except Exception as exc:
            raise _Blocked("circuit_commit_outcome_unknown") from exc

    def _open(
        self, state: CircuitState, now: int, reason: str, retry_after_seconds: float = 0
    ) -> CircuitState:
        local_delay = min(
            self.policy.max_cooldown_seconds,
            self.policy.cooldown_seconds * 2 ** min(state.open_count, 10),
        )
        deadline = now + math.ceil(max(local_delay, retry_after_seconds) * 1000)
        return state.model_copy(
            update=dict(
                state="OPEN",
                epoch=state.epoch + 1,
                pending=(),
                open_count=min(10000, state.open_count + 1),
                open_until_ms=deadline,
                last_clock_ms=now,
                last_reason=reason,
            )
        )

    def admit(self, configkey: CircuitKey, probelease_seconds: float) -> Admission:
        if (
            isinstance(probelease_seconds, bool)
            or not isinstance(probelease_seconds, (float, int))
            or not math.isfinite(probelease_seconds)
            or not 0 < probelease_seconds <= self.policy.max_lease_seconds
        ):
            return Admission(status="blocked", reason="invalid_probe_lease")
        for _ in range(self.policy.max_cas_attempts):
            try:
                now = self._now()
                revision, state = self._load(
                    configkey.storage_key, configkey.fingerprint, now
                )
                if state.state == "OPEN" and now < state.open_until_ms:
                    return Admission(
                        status="open",
                        retry_at=_date(state.open_until_ms),
                        reason="circuit_cooldown",
                    )
                if state.state == "HALF_OPEN":
                    if now < state.pending[0].expires_at_ms:
                        return Admission(
                            status="busy",
                            retry_at=_date(state.pending[0].expires_at_ms),
                            reason="half_open_probe_in_flight",
                        )
                    reopened = self._open(state, now, "probe_expired_outcome_unknown")
                    self._save(configkey.storage_key, revision, reopened)
                    return Admission(
                        status="open",
                        retry_at=_date(reopened.open_until_ms),
                        reason=reopened.last_reason,
                    )
                pending = tuple(p for p in state.pending if p.expires_at_ms > now)
                if len(pending) >= self.policy.max_inflight:
                    return Admission(
                        status="busy",
                        retry_at=_date(min(p.expires_at_ms for p in pending)),
                        reason="circuit_inflight_limit",
                    )
                probe = state.state == "OPEN"
                epoch = state.epoch + 1 if probe else state.epoch
                permit = PendingPermit(
                    token_id=str(uuid4()),
                    epoch=epoch,
                    expires_at_ms=now + math.ceil(probelease_seconds * 1000),
                )
                updated = state.model_copy(
                    update=dict(
                        state="HALF_OPEN" if probe else "CLOSED",
                        epoch=epoch,
                        pending=(permit,) if probe else (*pending, permit),
                        open_until_ms=None,
                        last_clock_ms=now,
                        last_reason="probe_admitted" if probe else "closed_admitted",
                    )
                )
                self._save(configkey.storage_key, revision, updated)
                token = PermitToken(
                    storage_key=configkey.storage_key,
                    fingerprint=configkey.fingerprint,
                    token_id=permit.token_id,
                    epoch=epoch,
                    expires_at_ms=permit.expires_at_ms,
                    probe=probe,
                )
                return Admission(
                    status="permitted", token=token, reason=updated.last_reason
                )
            except CircuitConflict:
                continue
            except _Blocked as exc:
                return Admission(status="blocked", reason=str(exc))
        return Admission(status="blocked", reason="circuit_cas_contention")

    def record_success(self, token: PermitToken) -> CircuitOutcome:
        return self._record(token, None, 0)

    def record_failure(
        self, token: PermitToken, transientclass: str, retry_after: float | None = None
    ) -> CircuitOutcome:
        known = {
            "rate_limited",
            "timeout",
            "provider_error",
            "authentication_error",
            "authorization_error",
            "policy_blocked",
            "malformed_response",
        }
        if transientclass not in known:
            return CircuitOutcome(status="blocked", reason="failure_class_unrecognized")
        delay = retry_after if retry_after is not None else 0
        if (
            isinstance(delay, bool)
            or not isinstance(delay, (int, float))
            or not math.isfinite(delay)
            or not 0 <= delay <= 86400
        ):
            return CircuitOutcome(
                status="blocked", reason="retry_after_invalid_requires_review"
            )
        return self._record(token, transientclass, delay)

    def _record(
        self, token: PermitToken, failure: str | None, delay: float
    ) -> CircuitOutcome:
        for _ in range(self.policy.max_cas_attempts):
            try:
                now = self._now()
                revision, state = self._load(token.storage_key, token.fingerprint, now)
                permit = next(
                    (p for p in state.pending if p.token_id == token.token_id), None
                )
                if (
                    revision is None
                    or permit is None
                    or state.epoch != token.epoch
                    or permit.epoch != token.epoch
                    or permit.expires_at_ms != token.expires_at_ms
                    or token.probe != (state.state == "HALF_OPEN")
                ):
                    return CircuitOutcome(status="stale", reason="circuit_token_fenced")
                if now >= permit.expires_at_ms:
                    return CircuitOutcome(
                        status="stale", reason="circuit_token_lease_expired"
                    )
                pending = tuple(
                    p for p in state.pending if p.token_id != permit.token_id
                )
                transient = failure in {"rate_limited", "timeout", "provider_error"}
                count = (
                    state.transient_failures + 1
                    if transient
                    else state.transient_failures
                )
                if failure is None:
                    updated = state.model_copy(
                        update=dict(
                            state="CLOSED",
                            epoch=state.epoch + 1 if token.probe else state.epoch,
                            pending=() if token.probe else pending,
                            transient_failures=0,
                            open_count=0,
                            open_until_ms=None,
                            last_clock_ms=now,
                            last_reason="success",
                        )
                    )
                elif token.probe or (
                    transient and (count >= self.policy.failure_threshold or delay > 0)
                ):
                    updated = self._open(
                        state.model_copy(
                            update={"transient_failures": min(count, 10000)}
                        ),
                        now,
                        "probe_failed"
                        if token.probe
                        else "provider_retry_after"
                        if delay > 0
                        else "transient_threshold",
                        delay,
                    )
                else:
                    updated = state.model_copy(
                        update=dict(
                            pending=pending,
                            transient_failures=count,
                            last_clock_ms=now,
                            last_reason="transient_failure"
                            if transient
                            else "nontransient_not_counted",
                        )
                    )
                updated = updated.model_copy(update={"last_failure_class": failure})
                self._save(token.storage_key, revision, updated)
                return CircuitOutcome(
                    status="recorded",
                    reason=updated.last_reason,
                    retry_at=_date(updated.open_until_ms),
                )
            except CircuitConflict:
                continue
            except _Blocked as exc:
                return CircuitOutcome(status="blocked", reason=str(exc))
        return CircuitOutcome(status="blocked", reason="circuit_cas_contention")
