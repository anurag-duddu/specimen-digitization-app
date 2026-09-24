"""The program's model allowance (docs/execution/golive/LANE.md, T2b; G9, G30).

One compare-and-set ledger adds every paid step's reservation before the call,
alongside the run's own budget. A step whose reservation would cross the
allowance is not called. Reservations are never refunded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from .domain import Scope
from .lane_worker import stored_integer
from .storage import Conflict, Missing

LEDGER_KIND = "worker_cursor"  # The worker's own state documents, one actor only.
ATTEMPTS = 5  # Collections may share the ledger; a conflict is read and retried.
EXHAUSTED = "program_allowance_exhausted"
UNAVAILABLE = "program_allowance_ledger_unavailable"


@dataclass(frozen=True)
class Reservation:
    issue: str | None  # None when the step may be called.
    position: dict | None  # The program's position, recorded on the run.


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
            return {"revision": 0, "reserved_total_micros": 0}
        return dict(
            current,
            revision=stored_integer(current["revision"]),
            reserved_total_micros=stored_integer(current["reserved_total_micros"]),
        )

    def reserve(self, allowance_micros, micros, *, specimen_id, run_id, step, attempt):
        for _ in range(ATTEMPTS):
            try:
                current = self.read()
            except Conflict:
                return Reservation(UNAVAILABLE, None)
            at = self.clock().isoformat()
            total = current["reserved_total_micros"] + micros
            if total > allowance_micros:
                return Reservation(
                    EXHAUSTED,
                    {
                        "allowance_micros": allowance_micros,
                        "reserved_total_micros": current["reserved_total_micros"],
                        "remaining_micros": max(
                            0, allowance_micros - current["reserved_total_micros"]
                        ),
                        "requested_micros": micros,
                        "ledger_revision": current["revision"],
                        "at": at,
                    },
                )
            last = {
                "specimen_id": specimen_id,
                "run_id": run_id,
                "step": step,
                "attempt": attempt,
                "micros": micros,
                "allowance_micros": allowance_micros,
                "at": at,
            }
            try:
                stored = self.repository.put_document(
                    self.scope,
                    LEDGER_KIND,
                    self.ident,
                    {"sensitive": False, "reserved_total_micros": total, "last": last},
                    current["revision"],
                )
            except Conflict:
                continue
            return Reservation(
                None,
                {
                    "allowance_micros": allowance_micros,
                    "reserved_total_micros": total,
                    "remaining_micros": allowance_micros - total,
                    "ledger_revision": stored["revision"],
                    "at": at,
                },
            )
        return Reservation(UNAVAILABLE, None)

    def settle(self, allowance_micros, reserved, spent, *, specimen_id, run_id, step, attempt):
        """Replace a call's reservation with what it cost (T2c, G30).

        The program's position, or None when the ledger stays busy or cannot be
        read; the reservation then stays counted.
        """
        for _ in range(ATTEMPTS):
            try:
                current = self.read()
            except Conflict:
                return None
            at = self.clock().isoformat()
            total = max(0, current["reserved_total_micros"] - reserved + spent)
            last = {
                "specimen_id": specimen_id,
                "run_id": run_id,
                "step": step,
                "attempt": attempt,
                "reserved_micros": reserved,
                "settled_micros": spent,
                "at": at,
            }
            try:
                stored = self.repository.put_document(
                    self.scope,
                    LEDGER_KIND,
                    self.ident,
                    {"sensitive": False, "reserved_total_micros": total, "last": last},
                    current["revision"],
                )
            except Conflict:
                continue
            return {
                "allowance_micros": allowance_micros,
                "reserved_total_micros": total,
                "remaining_micros": max(0, allowance_micros - total),
                "ledger_revision": stored["revision"],
                "at": at,
            }
        return None


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
