"""The program's model allowance (docs/execution/golive/LANE.md, T2b; G9, G30).

One compare-and-set ledger adds every paid step's reservation before the call,
alongside the run's own budget. A step whose reservation would cross the
allowance is not called. Only a known, matching call receipt releases its own unused reservation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from .domain import Scope
from .lane_worker import stored_integer
from .storage import Conflict, Missing, canonical_json

LEDGER_KIND = "worker_cursor"  # The worker's own state documents, one actor only.
ATTEMPTS = 5  # Collections may share the ledger; a conflict is read and retried.
EXHAUSTED = "program_allowance_exhausted"
UNAVAILABLE = "program_allowance_ledger_unavailable"


@dataclass(frozen=True)
class Reservation:
    issue: str | None  # None when the step may be called.
    position: dict | None  # The program's position, recorded on the run.


class LegacyLedgerUnavailable(RuntimeError):
    """Missing original cumulative ledger is a typed operational HOLD."""


class ProgramLedger:
    def __init__(self, repository, scope, *, clock=None):
        self.repository, self.scope = repository, scope
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.ident = str(
            uuid5(
                NAMESPACE_URL,
                f"processing-lane-allowance:{scope.organization_id}/{scope.collection_id}",
            )
        )

    def read(self) -> dict:
        try:
            current = self.repository.document(self.scope, LEDGER_KIND, self.ident)
        except Missing:
            raise LegacyLedgerUnavailable(UNAVAILABLE) from None
        return dict(
            current,
            revision=stored_integer(current["revision"]),
            reserved_total_micros=stored_integer(current["reserved_total_micros"]),
        )

    @staticmethod
    def _ordinary_key(specimen_id, run_id, step, attempt):
        if (any(type(value) is not str or not value for value in (specimen_id, run_id, step))
            or type(attempt) is not int or attempt <= 0):
            raise LegacyLedgerUnavailable(UNAVAILABLE)
        return canonical_json([specimen_id, run_id, step, attempt])

    def _position(self, current, allowance_micros):
        total = current["reserved_total_micros"]
        return {"allowance_micros": allowance_micros, "reserved_total_micros": total,
            "remaining_micros": max(0, allowance_micros - total),
            "ledger_revision": current["revision"], "at": self.clock().isoformat()}

    def reserve(self, allowance_micros, micros, *, specimen_id, run_id, step, attempt):
        """One ordinary step/attempt is reserved at most once, by envelope."""
        try:
            key = self._ordinary_key(specimen_id, run_id, step, attempt)
            if (type(micros) is not int or micros <= 0 or type(allowance_micros) is not int
                or allowance_micros <= 0):
                raise LegacyLedgerUnavailable(UNAVAILABLE)
        except LegacyLedgerUnavailable:
            return Reservation(UNAVAILABLE, None)
        envelope = {"reserved_micros": micros, "allowance_micros": allowance_micros}
        for _ in range(ATTEMPTS):
            try:
                current = self.read()
                entries = dict(current.get("ordinary_effects", {}))
            except (Conflict, LegacyLedgerUnavailable, TypeError, ValueError):
                return Reservation(UNAVAILABLE, None)
            previous = entries.get(key)
            if previous is not None:
                if (not isinstance(previous, dict) or any(previous.get(name) != value
                    for name, value in envelope.items())):
                    return Reservation(UNAVAILABLE, None)
                issue = EXHAUSTED if current["reserved_total_micros"] > allowance_micros else None
                return Reservation(issue, self._position(current, allowance_micros))
            total = current["reserved_total_micros"] + micros
            if total > allowance_micros:
                return Reservation(EXHAUSTED, {**self._position(current, allowance_micros), "requested_micros": micros})
            at = self.clock().isoformat()
            last = {"specimen_id": specimen_id, "run_id": run_id, "step": step,
                "attempt": attempt, "micros": micros, "allowance_micros": allowance_micros, "at": at}
            entries[key] = {**envelope, "settled_micros": None}
            try:
                stored = self.repository.put_document(self.scope, LEDGER_KIND, self.ident,
                    {**current, "sensitive": False, "reserved_total_micros": total,
                        "last": last, "ordinary_effects": entries}, current["revision"])
            except Conflict:
                continue
            return Reservation(None, self._position({**current, "reserved_total_micros": total,
                "revision": stored["revision"]}, allowance_micros))
        return Reservation(UNAVAILABLE, None)

    def settle(self, allowance_micros, reserved, spent, *, specimen_id, run_id, step, attempt):
        """Settle only this attempt's proven reservation, exactly once.

        A legacy aggregate alone proves no individual reservation. Missing or
        mismatched envelopes retain all liabilities and return None.
        """
        try:
            key = self._ordinary_key(specimen_id, run_id, step, attempt)
            if any(type(value) is not int or value < 0 for value in (reserved, spent, allowance_micros)):
                raise LegacyLedgerUnavailable(UNAVAILABLE)
        except LegacyLedgerUnavailable:
            return None
        for _ in range(ATTEMPTS):
            try:
                current = self.read()
                entries = dict(current.get("ordinary_effects", {}))
            except (Conflict, LegacyLedgerUnavailable, TypeError, ValueError):
                return None
            previous = entries.get(key)
            if (not isinstance(previous, dict) or previous.get("reserved_micros") != reserved
                or previous.get("allowance_micros") != allowance_micros):
                return None
            if previous.get("settled_micros") is not None:
                return self._position(current, allowance_micros) if previous["settled_micros"] == spent else None
            total = current["reserved_total_micros"] - reserved + spent
            if total < 0:
                return None
            last = {"specimen_id": specimen_id, "run_id": run_id, "step": step, "attempt": attempt,
                "reserved_micros": reserved, "settled_micros": spent, "at": self.clock().isoformat()}
            entries[key] = {**previous, "settled_micros": spent}
            try:
                stored = self.repository.put_document(self.scope, LEDGER_KIND, self.ident,
                    {**current, "sensitive": False, "reserved_total_micros": total,
                        "last": last, "ordinary_effects": entries}, current["revision"])
            except Conflict:
                continue
            return self._position({**current, "reserved_total_micros": total,
                "revision": stored["revision"]}, allowance_micros)
        return None

    def research_effect(self, allowance_micros, key, micros, *, settle=False, historical=False):
        """Idempotently charge one durable research attempt to the shared ledger.

        A new send must fit. Previously incurred liabilities are carried even
        above the limit, so migration/recovery cannot erase a bill. Settlement
        changes only this attempt's hold; every other field and prior total stay.
        """
        if (type(micros) is not int or micros < 0 or type(key) is not str or not key
            or type(allowance_micros) is not int or allowance_micros <= 0):
            raise ValueError("Invalid research program liability")
        for _ in range(ATTEMPTS):
            current = self.read()
            entries = dict(current.get("research_effects", {}))
            previous = entries.get(key)
            if (not historical and not settle and current["reserved_total_micros"] > allowance_micros):
                raise LegacyLedgerUnavailable(EXHAUSTED)
            if previous is not None:
                if (not isinstance(previous, dict) or type(previous.get("micros")) is not int
                    or previous["micros"] < 0 or previous.get("status") not in {"held", "settled"}):
                    raise LegacyLedgerUnavailable(UNAVAILABLE)
                if previous.get("status") == "settled":
                    if settle and previous["micros"] != micros:
                        raise ValueError("Research settlement changed")
                    return
                if not settle:
                    if previous["micros"] != micros:
                        raise ValueError("Research reservation changed")
                    return
            elif settle and not historical:
                raise ValueError("Research settlement has no reservation")
            total = current["reserved_total_micros"] - (previous["micros"] if previous else 0) + micros
            if previous is None and not historical and total > allowance_micros:
                raise LegacyLedgerUnavailable(EXHAUSTED)
            entries[key] = {"micros": micros, "status": "settled" if settle else "held"}
            try:
                self.repository.put_document(self.scope, LEDGER_KIND, self.ident,
                    {**current, "research_effects": entries, "reserved_total_micros": total}, current["revision"])
                return
            except Conflict:
                continue
        raise LegacyLedgerUnavailable(UNAVAILABLE)


def reserve_step(repository, principal, specimen, step, cost, clock=None) -> str | None:
    """Reserve a paid step on the program's ledger; an issue blocks the run.

    The ledger is consulted only when the run carries the program's allowance.
    """
    run = specimen.run
    policy = run.profile.execution
    if not cost or policy.program_allowance_micros is None:
        return None
    ledger = ProgramLedger(
        repository,
        Scope(
            organization_id=principal.scope.organization_id,
            collection_id=policy.program_ledger_collection,
        ),
        clock=clock,
    )
    reservation = ledger.reserve(
        policy.program_allowance_micros,
        cost,
        specimen_id=specimen.id,
        run_id=run.id,
        step=step,
        attempt=run.attempts.get(step, 0) + 1,
    )
    if reservation.position is not None:
        run.program_allowance = reservation.position
    return reservation.issue
