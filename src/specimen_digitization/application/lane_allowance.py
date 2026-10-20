"""The program's model allowance (docs/execution/golive/LANE.md, T2b; G9, G30).

One compare-and-set ledger adds every paid step's reservation before the call,
alongside the run's own budget. A step whose reservation would cross the
allowance is not called. Only a known, matching call receipt releases its own unused reservation.

The ledger's head document holds the total and the effects it has not archived.
Every save also stores the whole document as a version row (SaveDocumentV2), so
a head that kept every effect grew those rows with the square of the program's
paid steps (2,003 versions, 197 MB of JSON by 2026-10-20). A charge still writes
the total and its effect together in one head save. After an ordinary save past
HEAD_EFFECTS, effects move to one archive document each and leave the head
(docs/execution/PROGRAM_LEDGER_ARCHIVE.md). An archive holds an
effect before the head lets go of it and only ever moves forward (held, then
settled), so an effect is the head's while the head holds it and its archive's
after: read after the head, an archive is never older than that head.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from .domain import Scope
from .lane_worker import stored_integer
from .storage import Conflict, Missing, canonical_json

LOGGER = logging.getLogger(__name__)
LEDGER_KIND = "worker_cursor"  # The worker's own state documents, one actor only.
ATTEMPTS = 5  # Collections may share the ledger; a conflict is read and retried.
EXHAUSTED = "program_allowance_exhausted"
UNAVAILABLE = "program_allowance_ledger_unavailable"
ORDINARY, RESEARCH = "ordinary_effects", "research_effects"
HEAD_EFFECTS = 16  # The head archives its effects once it holds more than this.
ARCHIVE_BATCH = 64  # Effects archived per pass; a long legacy head drains over several.
_UNARCHIVED = object()


@dataclass(frozen=True)
class Reservation:
    issue: str | None  # None when the step may be called.
    position: dict | None  # The program's position, recorded on the run.


class LegacyLedgerUnavailable(RuntimeError):
    """Missing original cumulative ledger is a typed operational HOLD."""


def _rank(family, effect):
    """An effect's state, held 0 then settled 1; None when it cannot be archived."""
    if not isinstance(effect, dict):
        return None
    if family == ORDINARY:
        return 0 if effect.get("settled_micros") is None else 1
    return {"held": 0, "settled": 1}.get(effect.get("status"))


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

    def archive_id(self, family, key):
        """The one archive document of an effect, derived like the head's own id."""
        return str(uuid5(NAMESPACE_URL, f"processing-lane-allowance-effect:{self.ident}/{family}/{key}"))

    def effect(self, family, key, current=None):
        """One effect: the head's while it holds it, else its archive's, else None.

        The head is read first: an effect leaves it only once its archive holds
        the same state, and an archive never moves back.
        """
        current = self.read() if current is None else current
        effects = current.get(family, {})
        if not isinstance(effects, dict):
            raise LegacyLedgerUnavailable(UNAVAILABLE)
        if key in effects:
            return effects[key]
        try:
            stored = self.repository.document(self.scope, LEDGER_KIND, self.archive_id(family, key))
        except Missing:
            return None
        if ((stored.get("ledger"), stored.get("family"), stored.get("key")) != (self.ident, family, key)
            or _rank(family, stored.get("effect")) is None):
            raise LegacyLedgerUnavailable(UNAVAILABLE)
        return stored["effect"]

    def _archive_one(self, family, key, effect):
        """Write one effect's state to its archive; True once the archive holds exactly it."""
        rank = _rank(family, effect)
        if rank is None:
            return False  # A malformed effect stays in the head, which refuses it.
        ident = self.archive_id(family, key)
        payload = {"sensitive": False, "ledger": self.ident, "family": family, "key": key, "effect": effect}
        try:
            self.repository.put_document(self.scope, LEDGER_KIND, ident, payload, 0)
            return True
        except Conflict:
            stored = self.repository.document(self.scope, LEDGER_KIND, ident)
        if (stored.get("ledger"), stored.get("family"), stored.get("key")) != (self.ident, family, key):
            return False
        if stored.get("effect") == effect:
            return True
        # Only a held archive moves, forward to the settled state of the same charge.
        if (_rank(family, stored.get("effect")) != 0 or rank != 1 or (family == ORDINARY and any(
                stored["effect"].get(name) != effect.get(name) for name in ("reserved_micros", "allowance_micros")))):
            return False
        try:
            self.repository.put_document(self.scope, LEDGER_KIND, ident, payload, stored_integer(stored["revision"]))
        except Conflict:
            return False
        return True

    def _archive(self, head):
        """After a charge: past HEAD_EFFECTS, archive effects and drop them from the head.

        The charge is already saved, so a failure here is only logged: every
        effect not dropped stays in the head, which remains authoritative. Only
        an effect still equal to its archived state leaves the head.
        """
        try:
            pending = [(family, key, effect) for family in (ORDINARY, RESEARCH)
                for key, effect in head.get(family, {}).items()]
            if len(pending) <= HEAD_EFFECTS:
                return
            archived = {(family, key): effect for family, key, effect in pending[:ARCHIVE_BATCH]
                if self._archive_one(family, key, effect)}
            for _ in range(ATTEMPTS):
                kept = {family: {key: effect for key, effect in head[family].items()
                        if archived.get((family, key), _UNARCHIVED) != effect}
                    for family in (ORDINARY, RESEARCH) if family in head}
                if all(len(kept[family]) == len(head[family]) for family in kept):
                    return
                try:
                    self.repository.put_document(self.scope, LEDGER_KIND, self.ident,
                        {**head, **kept}, head["revision"])
                    return
                except Conflict:
                    head = self.read()
        except Exception as exc:  # noqa: BLE001 - archiving is housekeeping; the charge stands
            LOGGER.warning("program ledger archiving deferred: %s", type(exc).__name__)

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
                entries = dict(current.get(ORDINARY, {}))
                previous = self.effect(ORDINARY, key, current)
            except (Conflict, LegacyLedgerUnavailable, TypeError, ValueError):
                return Reservation(UNAVAILABLE, None)
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
                        "last": last, ORDINARY: entries}, current["revision"])
            except Conflict:
                continue
            self._archive(stored)
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
                entries = dict(current.get(ORDINARY, {}))
                previous = self.effect(ORDINARY, key, current)
            except (Conflict, LegacyLedgerUnavailable, TypeError, ValueError):
                return None
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
                        "last": last, ORDINARY: entries}, current["revision"])
            except Conflict:
                continue
            self._archive(stored)
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
            entries = dict(current.get(RESEARCH, {}))
            previous = self.effect(RESEARCH, key, current)
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
                # A research charge runs inside its send's lease, so it does not
                # wait for archiving; the next ordinary save archives both families.
                self.repository.put_document(self.scope, LEDGER_KIND, self.ident,
                    {**current, RESEARCH: entries, "reserved_total_micros": total}, current["revision"])
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


def admits(repository, principal, specimen, cost, clock=None) -> str | None:
    """What ``reserve_step`` would block the step with, read only: nothing is
    reserved. None when the run carries no allowance, the step costs nothing,
    or the ledger has room for ``cost``. Used where a step that ends without a
    call must still keep a money block first (workflow.RESEARCH_LIMITS)."""
    policy = specimen.run.profile.execution
    allowance = policy.program_allowance_micros
    if not cost or allowance is None:
        return None
    if type(cost) is not int or cost <= 0 or type(allowance) is not int or allowance <= 0:
        return UNAVAILABLE
    ledger = ProgramLedger(
        repository,
        Scope(
            organization_id=principal.scope.organization_id,
            collection_id=policy.program_ledger_collection,
        ),
        clock=clock,
    )
    try:
        total = ledger.read()["reserved_total_micros"]
    except (Conflict, LegacyLedgerUnavailable, TypeError, ValueError, KeyError):
        return UNAVAILABLE
    return EXHAUSTED if total + cost > allowance else None
