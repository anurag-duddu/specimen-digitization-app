"""Optional monthly budget caps per organization and collection (cost meter, PR 2).

docs/execution/golive/TENANT_BUDGETS.md. An organization administrator may set a
monthly cap for the organization and for any of its collections
(``TenantBudgetCap`` rows, read through ``repository.tenant_caps``). The caps
that apply to a run are the organization's and those of the run's collection
and each of its ancestors. Each applies through its own monthly ledger, a
compare-and-set document with the program ledger's semantics
(lane_allowance.ProgramLedger): a paid step reserves its worst case before the
call, settles to what its calls cost, overspend counts, nothing is released
except by a settlement to less, and an unknown outcome stays held in full.

No cap set, no ledger: with no applicable cap nothing here reads or writes a
ledger document, and the step goes on to the program's allowance exactly as
before. A repository that cannot hold caps (the local SQLite store) has none.
Everything else fails closed: caps or a ledger that cannot be read, or a ledger
whose compare-and-set keeps losing, block the run as ``tenant_budget_unavailable``;
a reservation the month's cap cannot cover blocks it as ``tenant_budget_exhausted``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from .domain import Scope
from .lane_allowance import ATTEMPTS, LEDGER_KIND, LegacyLedgerUnavailable, ProgramLedger
from .lane_worker import stored_integer
from .storage import Conflict, Missing

EXHAUSTED = "tenant_budget_exhausted"
UNAVAILABLE = "tenant_budget_unavailable"
# The cap row and ledger key of the organization itself; any other key is a
# collection id.
ORGANIZATION = "organization"
# Where a run records, per paid attempt, the month and the ledgers it reserved
# in: run.dependencies[RECORD]["<step>:<attempt>"] = {"month", "keys",
# "ledger_collection"}. Settlement reads it, never the caps.
RECORD = "tenant_budget"
# The largest cap or total a ledger keeps exact (lane_worker.stored_integer).
MAX_CAP_MICROS = 2**53 - 1
# More rows than this in one answer cannot be shown complete (TenantBudgetCapsV1).
MAX_ROWS = 1000


class TenantBudgetUnavailable(RuntimeError):
    """Caps or a ledger could not be read or trusted: no call is made."""

    def __init__(self, code=UNAVAILABLE):
        super().__init__(code)


@dataclass(frozen=True)
class Reservation:
    issue: str | None  # None when the step may be called.
    position: dict | None  # The ledger's position after the reservation.
    held: bool  # Whether the ledger holds this attempt's reservation now.


def utc_now():
    return datetime.now(timezone.utc)


def month_of(moment: datetime) -> str:
    """The UTC calendar month of ``moment``, as ``YYYY-MM``."""
    return moment.astimezone(timezone.utc).strftime("%Y-%m")


def _uuid(value) -> str:
    """A collection id in the one form ledgers and records use."""
    if type(value) is not str or not value:
        raise TenantBudgetUnavailable()
    try:
        return str(UUID(value))
    except ValueError:
        raise TenantBudgetUnavailable() from None


def cap_key(value) -> str:
    """``organization``, or a collection id normalized."""
    return ORGANIZATION if value == ORGANIZATION else _uuid(value)


def cap_micros(value) -> int | None:
    """A stored cap: None (no cap) or a whole number of micros. The transport
    may carry an Int64 as a decimal string or a double."""
    if value is None:
        return None
    if type(value) is str and value.isdigit() and len(value) <= 19:
        value = int(value)
    if type(value) is float and value.is_integer():
        value = int(value)
    if type(value) is not int or not 0 <= value <= MAX_CAP_MICROS:
        raise TenantBudgetUnavailable()
    return value


def ledger_ident(organization_id: str, key: str, month: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"tenant-budget:{organization_id}/{key}/{month}"))


def read_caps(repository, scope):
    """The organization's caps and collection tree, or None for a repository
    that cannot hold caps. Raises TenantBudgetUnavailable when they cannot be
    read; a connector that cannot be reached at all raises as any other read."""
    reader = getattr(repository, "tenant_caps", None)
    if reader is None:
        return None
    try:
        return reader(scope)
    except (Conflict, Missing, ValueError, TypeError, KeyError, AttributeError) as error:
        raise TenantBudgetUnavailable() from error


def _caps_and_parents(answer):
    """{key: micros} for every set cap, and {collection: parent} for the tree."""
    try:
        rows, collections = answer["caps"], answer["collections"]
        if (not isinstance(rows, list) or not isinstance(collections, list)
                or len(rows) > MAX_ROWS or len(collections) > MAX_ROWS):
            raise TenantBudgetUnavailable()
        caps = {}
        for row in rows:
            key, micros = cap_key(row["collection_key"]), cap_micros(row["monthly_cap_micros"])
            if key in caps:
                raise TenantBudgetUnavailable()
            caps[key] = micros
        parents = {}
        for row in collections:
            ident, parent = _uuid(row["id"]), row["parent_id"]
            if ident in parents:
                raise TenantBudgetUnavailable()
            parents[ident] = None if parent is None else _uuid(parent)
    except (KeyError, TypeError):
        raise TenantBudgetUnavailable() from None
    return {key: micros for key, micros in caps.items() if micros is not None}, parents


def lineage(parents: dict, collection_id: str) -> list[str]:
    """The collection and each ancestor, nearest first. A collection the tree
    does not hold, or a cycle, cannot say which caps apply."""
    chain, current = [], _uuid(collection_id)
    while current is not None:
        if current in chain or current not in parents:
            raise TenantBudgetUnavailable()
        chain.append(current)
        current = parents[current]
    return chain


def applicable(answer, collection_id: str) -> list[tuple[str, int]]:
    """The caps that apply to a run in ``collection_id``: the organization's,
    then the collection's and each ancestor's, as (key, monthly cap)."""
    if answer is None:
        return []
    caps, parents = _caps_and_parents(answer)
    if not caps:
        return []
    keys = [ORGANIZATION, *lineage(parents, collection_id)]
    return [(key, caps[key]) for key in keys if key in caps]


class TenantLedger:
    """One cap's ledger for one UTC month, with ProgramLedger's compare-and-set,
    idempotent envelopes and settlement. It is created at zero by the first
    reservation; two workers creating it at once conflict and one retries on a
    fresh read. The cap is passed in and is not part of an entry's envelope, so
    a cap changed while an attempt is held never makes that hold unreadable."""

    def __init__(self, repository, scope: Scope, key: str, month: str, *, clock=None):
        self.repository, self.scope, self.key, self.month = repository, scope, key, month
        self.clock = clock or utc_now
        self.ident = ledger_ident(scope.organization_id, key, month)

    def read(self) -> dict:
        try:
            current = self.repository.document(self.scope, LEDGER_KIND, self.ident)
        except Missing:
            return {"revision": 0, "reserved_total_micros": 0, "ordinary_effects": {}}
        if (current.get("organization_id"), current.get("collection_key"), current.get("month")) != (
            self.scope.organization_id, self.key, self.month
        ) or not isinstance(current.get("ordinary_effects", {}), dict):
            raise Conflict("A tenant budget ledger names another tenant or month")
        return dict(
            current,
            revision=stored_integer(current["revision"]),
            reserved_total_micros=stored_integer(current["reserved_total_micros"]),
        )

    def _position(self, current, cap):
        total = current["reserved_total_micros"]
        return {"collection_key": self.key, "month": self.month, "monthly_cap_micros": cap,
            "reserved_total_micros": total, "remaining_micros": max(0, cap - total),
            "ledger_revision": current["revision"], "at": self.clock().isoformat()}

    def _write(self, current, total, last, entries):
        return self.repository.put_document(self.scope, LEDGER_KIND, self.ident,
            {**current, "sensitive": False, "organization_id": self.scope.organization_id,
                "collection_key": self.key, "month": self.month, "reserved_total_micros": total,
                "last": last, "ordinary_effects": entries}, current["revision"])

    def admits(self, cap, micros, key) -> str | None:
        """What ``reserve`` would answer for ``key``, read only."""
        try:
            current = self.read()
            previous = current.get("ordinary_effects", {}).get(key)
        except (Conflict, TypeError, ValueError, KeyError):
            return UNAVAILABLE
        if previous is not None:
            if not isinstance(previous, dict) or previous.get("reserved_micros") != micros:
                return UNAVAILABLE
            return EXHAUSTED if current["reserved_total_micros"] > cap else None
        return EXHAUSTED if current["reserved_total_micros"] + micros > cap else None

    def reserve(self, cap, micros, *, specimen_id, run_id, step, attempt) -> Reservation:
        """One step/attempt is reserved at most once, by envelope."""
        try:
            key = ProgramLedger._ordinary_key(specimen_id, run_id, step, attempt)
            if (type(micros) is not int or micros <= 0 or type(cap) is not int
                    or not 0 <= cap <= MAX_CAP_MICROS):
                raise LegacyLedgerUnavailable(UNAVAILABLE)
        except LegacyLedgerUnavailable:
            return Reservation(UNAVAILABLE, None, False)
        envelope = {"reserved_micros": micros}
        for _ in range(ATTEMPTS):
            try:
                current = self.read()
                entries = dict(current.get("ordinary_effects", {}))
            except (Conflict, TypeError, ValueError, KeyError):
                return Reservation(UNAVAILABLE, None, False)
            previous = entries.get(key)
            if previous is not None:
                if not isinstance(previous, dict) or previous.get("reserved_micros") != micros:
                    return Reservation(UNAVAILABLE, None, False)
                issue = EXHAUSTED if current["reserved_total_micros"] > cap else None
                return Reservation(issue, self._position(current, cap), True)
            total = current["reserved_total_micros"] + micros
            if total > cap:
                return Reservation(EXHAUSTED, {**self._position(current, cap), "requested_micros": micros}, False)
            last = {"specimen_id": specimen_id, "run_id": run_id, "step": step, "attempt": attempt,
                "micros": micros, "monthly_cap_micros": cap, "at": self.clock().isoformat()}
            entries[key] = {**envelope, "settled_micros": None}
            try:
                stored = self._write(current, total, last, entries)
            except Conflict:
                continue
            return Reservation(None, self._position({**current, "reserved_total_micros": total,
                "revision": stored["revision"]}, cap), True)
        return Reservation(UNAVAILABLE, None, False)

    def settle(self, reserved, spent, *, specimen_id, run_id, step, attempt) -> dict | None:
        """Settle only this attempt's own reservation, exactly once. A missing
        or different envelope, or a ledger that cannot be read, keeps the hold
        and returns None."""
        try:
            key = ProgramLedger._ordinary_key(specimen_id, run_id, step, attempt)
            if any(type(value) is not int or value < 0 for value in (reserved, spent)):
                raise LegacyLedgerUnavailable(UNAVAILABLE)
        except LegacyLedgerUnavailable:
            return None
        for _ in range(ATTEMPTS):
            try:
                current = self.read()
                entries = dict(current.get("ordinary_effects", {}))
            except (Conflict, TypeError, ValueError, KeyError):
                return None
            previous = entries.get(key)
            if not isinstance(previous, dict) or previous.get("reserved_micros") != reserved:
                return None
            if previous.get("settled_micros") is not None:
                return current if previous["settled_micros"] == spent else None
            total = current["reserved_total_micros"] - reserved + spent
            if total < 0:
                return None
            last = {"specimen_id": specimen_id, "run_id": run_id, "step": step, "attempt": attempt,
                "reserved_micros": reserved, "settled_micros": spent, "at": self.clock().isoformat()}
            entries[key] = {**previous, "settled_micros": spent}
            try:
                return self._write(current, total, last, entries)
            except Conflict:
                continue
        return None

    def settled(self, key, reserved) -> int | None:
        """What this ledger settled ``key`` at, when it holds exactly ``reserved`` for it."""
        try:
            entry = self.read().get("ordinary_effects", {}).get(key)
            if (not isinstance(entry, dict) or entry.get("settled_micros") is None
                    or stored_integer(entry.get("reserved_micros")) != reserved):
                return None
            return stored_integer(entry["settled_micros"])
        except Exception:  # noqa: BLE001 - an unreadable ledger proves no settlement
            return None


def ledger_scope(principal, specimen) -> Scope:
    """Where the ledgers live: beside the program's ledger, else in the run's
    own collection (a run without a ledger collection, outside the lane)."""
    policy = specimen.run.profile.execution
    return Scope(organization_id=principal.scope.organization_id,
        collection_id=policy.program_ledger_collection or principal.scope.collection_id)


def _records(run) -> dict:
    records = run.dependencies.get(RECORD, {})
    if not isinstance(records, dict):
        raise TenantBudgetUnavailable()
    return records


def _record(run, step, attempt) -> dict | None:
    record = _records(run).get(f"{step}:{attempt}")
    if record is None:
        return None
    if (not isinstance(record, dict) or type(record.get("month")) is not str
            or not isinstance(record.get("keys"), list)
            or type(record.get("ledger_collection")) is not str):
        raise TenantBudgetUnavailable()
    return record


def _ledgers(repository, principal, specimen, caps, month, clock, record=None):
    scope = (ledger_scope(principal, specimen) if record is None else
        Scope(organization_id=principal.scope.organization_id, collection_id=record["ledger_collection"]))
    return [(TenantLedger(repository, scope, key, month, clock=clock), cap) for key, cap in caps]


def _program_admits(repository, principal, specimen, step, cost, attempt, clock) -> str | None:
    """The program ledger's answer to this attempt, read only, so a step it
    would refuse holds nothing on a tenant ledger first."""
    from .lane_allowance import EXHAUSTED as PROGRAM_EXHAUSTED, UNAVAILABLE as PROGRAM_UNAVAILABLE

    policy = specimen.run.profile.execution
    if policy.program_allowance_micros is None:
        return None
    ledger = ProgramLedger(repository, Scope(organization_id=principal.scope.organization_id,
        collection_id=policy.program_ledger_collection), clock=clock)
    try:
        current = ledger.read()
        key = ProgramLedger._ordinary_key(specimen.id, specimen.run.id, step, attempt)
        if key in current.get("ordinary_effects", {}):
            return None  # A replay: reserve_step decides on its own envelope.
        total = current["reserved_total_micros"]
    except (Conflict, LegacyLedgerUnavailable, TypeError, ValueError, KeyError):
        return PROGRAM_UNAVAILABLE
    return PROGRAM_EXHAUSTED if total + cost > policy.program_allowance_micros else None


def reserve_step(repository, principal, specimen, step, cost, clock=None) -> str | None:
    """Reserve a paid step on every tenant ledger whose cap applies; an issue
    blocks the run. Called before lane_allowance.reserve_step.

    Every applicable ledger, and the program's, is read first: a step any of
    them would refuse holds nothing. Then each tenant ledger reserves, and the
    record of the ones that hold the attempt is kept on the run, so a block
    later in the chain (a race, then the program's allowance) is replayed, not
    reserved twice, when the same attempt comes round again. The month is the
    UTC month of the attempt's first reservation.
    """
    run = specimen.run
    if not cost:
        return None
    clock = clock or utc_now
    attempt = run.attempts.get(step, 0) + 1
    try:
        caps = applicable(read_caps(repository, principal.scope), principal.scope.collection_id)
        record = _record(run, step, attempt)
    except TenantBudgetUnavailable:
        return UNAVAILABLE
    if not caps:
        return None
    month = record["month"] if record else month_of(clock())
    entry = ProgramLedger._ordinary_key(specimen.id, run.id, step, attempt)
    ledgers = _ledgers(repository, principal, specimen, caps, month, clock, record)
    for ledger, cap in ledgers:
        issue = ledger.admits(cap, cost, entry)
        if issue:
            return issue
    issue = _program_admits(repository, principal, specimen, step, cost, attempt, clock)
    if issue:
        return issue
    keys = list(record["keys"]) if record else []
    for ledger, cap in ledgers:
        reservation = ledger.reserve(cap, cost, specimen_id=specimen.id, run_id=run.id,
            step=step, attempt=attempt)
        if reservation.held and ledger.key not in keys:
            keys.append(ledger.key)
            run.dependencies[RECORD] = {**_records(run), f"{step}:{attempt}": {
                "month": month, "keys": keys, "ledger_collection": ledger.scope.collection_id}}
        if reservation.issue:
            return reservation.issue
    return None


def settle_step(repository, principal, specimen, step, attempt, reserved, spent, clock=None) -> None:
    """Settle the attempt on every tenant ledger it reserved in, in the month it
    reserved in (lane_costs.settle_step). Nothing when it reserved in none; a
    ledger that cannot be read or settled keeps its hold."""
    try:
        record = _record(specimen.run, step, attempt)
    except TenantBudgetUnavailable:
        return
    if record is None:
        return
    scope = Scope(organization_id=principal.scope.organization_id,
        collection_id=record["ledger_collection"])
    for key in record["keys"]:
        TenantLedger(repository, scope, key, record["month"], clock=clock).settle(
            reserved, spent, specimen_id=specimen.id, run_id=specimen.run.id, step=step,
            attempt=attempt)


def settled_micros(repository, principal, specimen, step, attempt, reserved) -> int | None:
    """What every tenant ledger the attempt reserved in settled it at, when they
    agree; None otherwise (Workflow._ledger_settlement)."""
    try:
        record = _record(specimen.run, step, attempt)
    except TenantBudgetUnavailable:
        return None
    if not record or not record["keys"]:
        return None
    scope = Scope(organization_id=principal.scope.organization_id,
        collection_id=record["ledger_collection"])
    key = ProgramLedger._ordinary_key(specimen.id, specimen.run.id, step, attempt)
    amounts = {TenantLedger(repository, scope, name, record["month"]).settled(key, reserved)
        for name in record["keys"]}
    return amounts.pop() if len(amounts) == 1 and None not in amounts else None


def admits(repository, principal, specimen, cost, clock=None) -> str | None:
    """What ``reserve_step`` would block a step of ``cost`` with on a tenant
    ledger, read only (lane_allowance.admits, for workflow.RESEARCH_LIMITS)."""
    if not cost:
        return None
    clock = clock or utc_now
    try:
        caps = applicable(read_caps(repository, principal.scope), principal.scope.collection_id)
    except TenantBudgetUnavailable:
        return UNAVAILABLE
    if not caps:
        return None
    if type(cost) is not int or cost <= 0:
        return UNAVAILABLE
    for ledger, cap in _ledgers(repository, principal, specimen, caps, month_of(clock()), clock):
        try:
            total = ledger.read()["reserved_total_micros"]
        except (Conflict, TypeError, ValueError, KeyError):
            return UNAVAILABLE
        if total + cost > cap:
            return EXHAUSTED
    return None


def remaining(repository, principal, specimen, clock=None) -> int | None:
    """The least any applicable cap has left this month, or None when no cap
    applies (FieldResearchStep.reservation). Raises TenantBudgetUnavailable."""
    clock = clock or utc_now
    caps = applicable(read_caps(repository, principal.scope), principal.scope.collection_id)
    if not caps:
        return None
    left = []
    for ledger, cap in _ledgers(repository, principal, specimen, caps, month_of(clock()), clock):
        try:
            left.append(max(0, cap - ledger.read()["reserved_total_micros"]))
        except (Conflict, TypeError, ValueError, KeyError):
            raise TenantBudgetUnavailable() from None
    return min(left)


def applies(repository, scope) -> bool:
    """Whether any cap applies to work in ``scope``. Raises TenantBudgetUnavailable."""
    return bool(applicable(read_caps(repository, scope), scope.collection_id))


def cap_positions(caps, collections, month, spent_by_collection):
    """Each cap's position for ``month``, for the cost meter's report.

    ``caps`` is {"organization" or collection id: monthly micros or None},
    ``collections`` is {collection id: parent id or None} and
    ``spent_by_collection`` is {collection id: micros spent in the month by that
    collection's own runs}. A collection's cap counts its own spend and every
    descendant's; the organization's counts every collection's. Returns
    {"organization": position or None, "collections": {id: position or None}},
    a position being {"monthly_cap_micros", "month", "spent_micros",
    "remaining_micros"}. A cycle, or a parent outside the tree, raises
    ValueError.
    """
    parents = {_uuid(ident): None if parent is None else _uuid(parent)
        for ident, parent in collections.items()}
    caps = {cap_key(key): cap_micros(value) for key, value in caps.items()}
    spent = {_uuid(ident): value for ident, value in spent_by_collection.items()}
    if any(type(value) is not int or value < 0 for value in spent.values()):
        raise ValueError("Spent amounts must be whole, non-negative micros")
    totals = dict.fromkeys(parents, 0)
    for ident, value in spent.items():
        try:
            chain = lineage(parents, ident)
        except TenantBudgetUnavailable:
            raise ValueError("The collection tree does not hold this collection") from None
        for ancestor in chain:
            totals[ancestor] += value
    for ident in parents:
        try:
            lineage(parents, ident)
        except TenantBudgetUnavailable:
            raise ValueError("The collection tree has a cycle or an unknown parent") from None

    def position(cap, used):
        if cap is None:
            return None
        return {"monthly_cap_micros": cap, "month": month, "spent_micros": used,
            "remaining_micros": max(0, cap - used)}

    return {
        "organization": position(caps.get(ORGANIZATION), sum(spent.values())),
        "collections": {ident: position(caps.get(ident), totals[ident]) for ident in parents},
    }
