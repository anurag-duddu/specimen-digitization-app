"""App-owned SQL durability and immutable effect capture for Harness.

The SQL aggregate is lifecycle data, never the canonical specimen value store.
CAS reducers contain no network/model work. Provider acceptance is deliberately
outside the SQL transaction: a sent request without a verified capture is held.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import inspect
import json
import logging
import os
import random
import re
import sqlite3
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Any, Awaitable, Callable, Mapping, Protocol
from uuid import uuid4

CONTRACT_VERSION = "research-durability/v1"
# One corrected specimen retains both immutable research jobs, effects, journal
# and publication outbox in this aggregate. The bounded two-revision rehearsal
# reaches 1,027,331 bytes; 1.5 MB leaves room for that complete replay without
# discarding earlier proof or cost. Longer histories still need archival.
MAX_STATE_BYTES = 1_500_000
# One lease covers a complete role window and its publication. Renewing the
# lease during a window would invalidate the publication's exact lease match.
MAX_LEASE_TTL_SECONDS = 900
CAS_PAUSE_FIRST_SECONDS = 0.01
CAS_PAUSE_MAX_SECONDS = 0.5

# These connector queries have no business-state writes. The separately named
# clock read updates observedAt only (research_harness.gql:14-23), never a lease,
# revision, effect, publication or lifecycle state. HTTP POST is not an allowlist.
_SQL_SEMANTIC_READS = frozenset({"GetCanonicalResearchBindingV2",
    "GetCanonicalResearchMaterializationInputsV2", "GetResearchPublicationIntentV2",
    "GetResearchPublicationReceiptV2", "GetRetainedResearchPublicationLocatorsV2"})
_SQL_CLOCK_READ = "ReadResearchHarnessStateV1"
_SQL_CONTEXT_OPERATIONS = _SQL_SEMANTIC_READS | {_SQL_CLOCK_READ,
    "RegisterCanonicalResearchBindingV2", "RetainResearchPublicationIntentV2",
    "RetainResearchPublicationPreparationV2", "MarkResearchPublicationAttemptV2",
    "PublishCanonicalResearchV2", "CreateResearchHarnessStateV1", "CompareResearchHarnessStateV1"}
_SQL_ATTEMPT_TIMEOUT_SECONDS = 30.0
_SQL_READ_BUDGET_SECONDS = 60.0


def _sql_transport_context(error, operation, phase, attempt):
    """Attach safe context without changing an exception's type or error mapping."""
    name = operation if type(operation) is str and operation in _SQL_CONTEXT_OPERATIONS else "unlisted"
    try:
        logging.getLogger(__name__).warning("SQL Connect transport operation=%s phase=%s attempt=%s", name, phase, attempt)
    except Exception:
        pass
    try:
        error.add_note(f"sql_connect_operation={name}; phase={phase}; attempt={attempt}")
    except Exception:
        pass  # Diagnostics never replace the original denial/deadline/failure.


def _sql_connect_transport(repository, operation, variables, mutation, decode, *, clock_read=False, authorize=None):
    """At most one ReadTimeout retry for an explicitly qualified semantic read.

    Requests' timeout is a socket timeout, not a hard wall clock. The existing
    worker deadline/supervisor remains authoritative; no clock is renewed here.
    Admission and successful return check the monotonic 60-second read budget.
    """
    from requests.exceptions import ReadTimeout
    from specimen_digitization.application.worker_deadline import check_deadline, current_deadline, deadline_call

    allowed = type(operation) is str and ((mutation is False and operation in _SQL_SEMANTIC_READS)
        or (clock_read and mutation is True and operation == _SQL_CLOCK_READ))
    limit = 2 if allowed else 1
    parent = current_deadline()
    clock = parent.monotonic if parent is not None else time.monotonic
    end = clock() + _SQL_READ_BUDGET_SECONDS if allowed else None
    body = copy.deepcopy({"operationName": operation, "variables": variables})
    url = repository.url + (":impersonateMutation" if mutation else ":impersonateQuery")
    for attempt in range(1, limit + 1):
        try:
            check_deadline()
        except BaseException as error:
            _sql_transport_context(error, operation, "request_admission", attempt)
            raise
        if authorize is not None:
            try:
                authorize()
            except BaseException as error:
                _sql_transport_context(error, operation, "authorization", attempt)
                raise
        remaining = _SQL_ATTEMPT_TIMEOUT_SECONDS
        if end is not None:
            remaining = min(remaining, end - clock())
        if parent is not None:
            remaining = min(remaining, parent.remaining())
        if remaining <= 0:
            try:
                check_deadline()
                raise ReadTimeout("SQL Connect semantic read deadline exceeded")
            except BaseException as error:
                _sql_transport_context(error, operation, "request_admission", attempt)
                raise
        try:
            response = deadline_call(repository.session.post, url, json=copy.deepcopy(body), timeout=remaining)
        except ReadTimeout as error:
            _sql_transport_context(error, operation, "http_request", attempt)
            check_deadline()
            if attempt < limit and end is not None and clock() < end:
                continue
            raise
        except BaseException as error:
            _sql_transport_context(error, operation, "http_request", attempt)
            raise
        try:
            result = deadline_call(decode, response)
            if end is not None and clock() >= end:
                raise ReadTimeout("SQL Connect semantic read deadline exceeded")
            return result
        except BaseException as error:
            _sql_transport_context(error, operation, "response_validation", attempt)
            raise


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


class StaleWork(RuntimeError):
    """Lease, generation, dependency, human lock or field revision changed."""


class BudgetExceeded(RuntimeError):
    """The shared cumulative ledger cannot authorize another effect."""


class HeldUnknown(RuntimeError):
    """An effect may have been sent; reconcile it before another dispatch."""


class CasConflict(RuntimeError):
    """The aggregate revision changed; retry only the pure SQL reducer."""


class TraceContextConflict(ValueError):
    """A valid generation already retains a different immutable trace parent."""


@dataclass(frozen=True)
class DurabilityScope:
    organization_id: str
    collection_id: str
    specimen_id: str
    job_id: str
    generation: int
    actor_uid: str
    sensitive: bool = True

    def identity(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if k not in {"actor_uid", "sensitive"}}

    @property
    def key(self) -> str:
        return digest({k: v for k, v in self.identity().items() if k != "generation"})


@dataclass(frozen=True)
class _LockedSourceRead:
    broker: Any
    scope: DurabilityScope
    operation_key: str
    request_digest: str
    field_key: str
    verify_current: Callable[[], None]
    closed: Event = field(default_factory=Event, compare=False)


_locked_source_read: ContextVar[_LockedSourceRead | None] = ContextVar(
    "research_trusted_locked_source_read", default=None)


@contextmanager
def _trusted_locked_source_read(broker, scope, operation_key, logical_request, *,
                                field_key, source_id, command_digest, verify_current):
    """Internal capture-only authority, never a serialized/model tool argument.

    The capture broker supplies a callback which re-reads the genuine human
    command, queue revision and anchor proofs. Only its exact logical read may
    cross a human lock. Context propagates through asyncio.to_thread; no grant
    is persisted or survives this call. Publication still refuses locked fields.
    """
    if not isinstance(logical_request, dict):
        raise PermissionError("Trusted locked read requires the complete source request")
    contract = logical_request.get("contract_version")
    arguments_key = {"research-source-request-envelope/v2": "arguments",
                     "research-pinned-dataset-request/v1": "query"}.get(contract)
    arguments = logical_request.get(arguments_key) if arguments_key else None
    request_digest = digest(logical_request)
    if (not isinstance(broker, DurableEffectBroker) or not isinstance(scope, DurabilityScope)
        or source_id not in {"georeference_history", "geolocate"}
        or not isinstance(field_key, str) or not field_key
        or not isinstance(command_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", command_digest)
        or logical_request.get("trusted_derivation_command_digest") != command_digest
        or logical_request.get("tool_id") != "source_lookup"
        or not isinstance(arguments, dict) or arguments.get("source_id") != source_id
        or arguments.get("field_key") != field_key
        or operation_key != "source_capture_v2:" + request_digest or not callable(verify_current)
        or _locked_source_read.get() is not None):
        raise PermissionError("Trusted locked read is not the exact bound source capture")
    permit = _LockedSourceRead(broker, scope, operation_key, request_digest, field_key, verify_current)
    token = _locked_source_read.set(permit)
    try:
        yield
    finally:
        permit.closed.set()
        _locked_source_read.reset(token)


def _revalidate_locked_source_read(store, scope):
    permit = _locked_source_read.get()
    if permit is None:
        return
    if permit.closed.is_set() or permit.broker.store is not store or permit.scope != scope:
        raise PermissionError("Trusted locked read belongs to another store or scope")
    # Keep external proof reads out of CAS reducers; mark_sending also retains
    # the canonical SQL send fence in the same transaction as the effect CAS.
    result = permit.verify_current()
    if inspect.isawaitable(result):
        if inspect.iscoroutine(result):
            result.close()
        raise TypeError("Trusted locked read requires synchronous proof verification")
    if result is not None:
        raise PermissionError("Trusted locked read proof must raise on denial, not return a flag")


@dataclass(frozen=True)
class LiveResearchAuthority:
    """Live research permission for one specimen: the worker actor, a run whose
    profile names a harness route, and SPECIMEN_RESEARCH_HARNESS=on.

    Built only by workflow_bridge.authorize_live_research.
    """
    organization_id: str
    collection_id: str
    specimen_id: str
    actor_uid: str
    harness_route: str
    switch_on: bool

    def __post_init__(self) -> None:
        if self.switch_on is not True or not all(isinstance(v, str) and v for v in (
                self.organization_id, self.collection_id, self.specimen_id, self.actor_uid, self.harness_route)):
            raise ValueError("research_live_authority_invalid")

    def covers(self, scope: DurabilityScope) -> bool:
        return scope.sensitive is False and (scope.organization_id, scope.collection_id,
            scope.specimen_id, scope.actor_uid) == (self.organization_id, self.collection_id,
            self.specimen_id, self.actor_uid)


@dataclass(frozen=True)
class PinnedRuntime:
    input_digest: str
    profile: Mapping[str, Any]
    prompts: Mapping[str, Any]
    sources: Mapping[str, Any]
    model: Mapping[str, Any]
    settings: Mapping[str, Any]
    engine_version: str
    serialization_version: str = "harness-0.36.0/core-2.51.0"

    def payload(self) -> dict[str, Any]:
        return json.loads(canonical(asdict(self)))


@dataclass(frozen=True)
class BudgetPolicy:
    ceiling_micro_usd: int
    external_settled_micro_usd: int = 0
    external_held_micro_usd: int = 0
    external_ledger_digest: str = "local-unqualified"
    live_authorized: bool = False
    hold_reason: str | None = "external_live_admission_not_confirmed"

    def __post_init__(self) -> None:
        for v in (self.ceiling_micro_usd, self.external_settled_micro_usd, self.external_held_micro_usd):
            if type(v) is not int or v < 0:
                raise ValueError("Budget amounts must be nonnegative integer microUSD")
        if self.live_authorized and self.hold_reason:
            raise ValueError("A live allowance cannot carry a hold reason")


@dataclass(frozen=True)
class Lease:
    job_key: str
    owner: str
    fence: int
    generation: int
    expires_at: float


@dataclass(frozen=True)
class BlobRef:
    locator: str
    generation: str
    sha256: str
    byte_size: int


@dataclass(frozen=True)
class CapturedResult:
    typed_payload: Any
    actual_micro_usd: int | None
    raw_payload: Any = None
    provider_request_id: str | None = None
    usage: Mapping[str, Any] = field(default_factory=dict)
    outcome: str = "completed"

    def __post_init__(self) -> None:
        if self.actual_micro_usd is not None and (type(self.actual_micro_usd) is not int or self.actual_micro_usd < 0):
            raise ValueError("Actual cost must be known nonnegative integer microUSD or None")
        if self.outcome not in {"completed", "failed_no_effect"}:
            raise ValueError("Partial-effect failures must remain unknown")


@dataclass(frozen=True)
class EffectReceipt:
    effect_id: str
    attempt_id: str
    typed_payload: Any
    capture: BlobRef
    actual_micro_usd: int | None
    held_micro_usd: int
    provider_request_id: str | None
    usage: Mapping[str, Any]
    outcome: str
    raw_capture: BlobRef | None = None


@dataclass(frozen=True)
class StateDocument:
    revision: int
    server_time: float
    state: dict[str, Any]


class StateBackend(Protocol):
    def load(self, scope: DurabilityScope, program_key: str) -> StateDocument | None: ...
    def create(self, scope: DurabilityScope, program_key: str, state: dict[str, Any]) -> None: ...
    def cas(self, scope: DurabilityScope, program_key: str, revision: int, state: dict[str, Any], *, valid_until: float | None = None, review_required: bool = False, send_authorization: dict | None = None) -> None: ...


class SqliteStateBackend:
    """Persistent local SQL proof; this is not a production SQL Connect claim."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        with self._connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS research_state (
                  organization_id TEXT NOT NULL, program_key TEXT NOT NULL,
                  revision INTEGER NOT NULL, state TEXT NOT NULL,
                  PRIMARY KEY (organization_id, program_key));
                CREATE TABLE IF NOT EXISTS research_membership (
                  organization_id TEXT NOT NULL, collection_id TEXT NOT NULL,
                  actor_uid TEXT NOT NULL, active INTEGER NOT NULL,
                  role TEXT NOT NULL, can_view_sensitive INTEGER NOT NULL,
                  PRIMARY KEY (organization_id, collection_id, actor_uid));
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA busy_timeout=30000")
        return db

    @staticmethod
    def _time(db: sqlite3.Connection) -> float:
        return db.execute("SELECT (julianday('now') - 2440587.5) * 86400.0").fetchone()[0]

    @staticmethod
    def _authorize(db: sqlite3.Connection, scope: DurabilityScope, *, write: bool = True) -> None:
        row = db.execute("SELECT active,role,can_view_sensitive FROM research_membership WHERE organization_id=? AND collection_id=? AND actor_uid=?", (scope.organization_id, scope.collection_id, scope.actor_uid)).fetchone()
        if not row or not row[0] or (write and row[1] not in {"operator", "reviewer", "manager", "admin"}) or (scope.sensitive and not row[2]):
            raise PermissionError("Current collection membership required")

    def grant(self, scope: DurabilityScope, *, role: str = "operator", can_view_sensitive: bool = False) -> None:
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO research_membership VALUES (?,?,?,?,?,?)", (scope.organization_id, scope.collection_id, scope.actor_uid, 1, role, int(can_view_sensitive)))

    def revoke(self, scope: DurabilityScope) -> None:
        with self._connect() as db:
            db.execute("UPDATE research_membership SET active=0 WHERE organization_id=? AND collection_id=? AND actor_uid=?", (scope.organization_id, scope.collection_id, scope.actor_uid))

    def load(self, scope: DurabilityScope, program_key: str) -> StateDocument | None:
        with self._connect() as db:
            self._authorize(db, scope, write=False)
            row = db.execute("SELECT revision,state FROM research_state WHERE organization_id=? AND program_key=?", (scope.organization_id, program_key)).fetchone()
            return StateDocument(row[0], self._time(db), json.loads(row[1])) if row else None

    def create(self, scope: DurabilityScope, program_key: str, state: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._authorize(db, scope)
            try:
                db.execute("INSERT INTO research_state VALUES (?,?,1,?)", (scope.organization_id, program_key, canonical(state).decode()))
            except sqlite3.IntegrityError as exc:
                raise CasConflict("Program already initialized") from exc

    def cas(self, scope: DurabilityScope, program_key: str, revision: int, state: dict[str, Any], *, valid_until: float | None = None, review_required: bool = False, send_authorization: dict | None = None) -> None:
        if send_authorization is not None:
            raise PermissionError("Canonical dispatch authorization requires native SQL Connect")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._authorize(db, scope)
            if review_required:
                role = db.execute("SELECT role FROM research_membership WHERE organization_id=? AND collection_id=? AND actor_uid=?", (scope.organization_id, scope.collection_id, scope.actor_uid)).fetchone()[0]
                if role not in {"reviewer", "manager", "admin"}:
                    raise PermissionError("Human input requires current review authority")
            if valid_until is not None and self._time(db) >= valid_until:
                raise StaleWork("Lease expired at database commit")
            changed = db.execute("UPDATE research_state SET state=?,revision=revision+1 WHERE organization_id=? AND program_key=? AND revision=?", (canonical(state).decode(), scope.organization_id, program_key, revision)).rowcount
            if changed != 1:
                raise CasConflict("Aggregate revision conflict")


class SqlConnectStateBackend:
    """Native named server operations over the existing authenticated repository.

    The repository supplies verified actor context; it must reject forged actor
    IDs. Whole aggregates remain inside this backend and the scoped store.
    """

    def __init__(self, repository: Any):
        self.repository = repository

    def _variables(self, scope: DurabilityScope, program_key: str) -> dict[str, Any]:
        variables = self.repository.variables(scope)
        if variables.get("actorUid") != scope.actor_uid:
            raise PermissionError("Scope actor differs from verified repository context")
        return dict(variables, programKey=program_key, specimenId=scope.specimen_id, sensitive=scope.sensitive)

    def _execute(self, scope: DurabilityScope, program_key: str, operation: str, variables: dict):
        from specimen_digitization.application.production import SqlConnectRepository
        # Do not bypass a repository override merely because it has session/url.
        # Execute-only/custom adapters keep their existing, single-send contract.
        actual_transport = getattr(self.repository.execute, "__func__", None) is SqlConnectRepository.execute
        if actual_transport:
            def authorize():
                if any(variables.get(key) != value for key, value in self._variables(scope, program_key).items()):
                    raise PermissionError("Scope actor differs from verified repository context")

            def decode(response):
                from specimen_digitization.application.worker_deadline import deadline_call
                from specimen_digitization.application.workflow import OperationalBlock
                from specimen_digitization.application.storage import Conflict
                if response.status_code in {401, 403}:
                    raise PermissionError("SQL Connect access denied")
                if response.status_code != 200:
                    raise OperationalBlock("sql_connect_unavailable_or_connector_not_published")
                body = deadline_call(response.json)
                if body.get("errors"):
                    raise Conflict("SQL Connect transaction rejected; reload current revision and membership")
                from .native_json import decode_native_json
                data = decode_native_json(operation, body.get("data", {}))
                if operation == _SQL_CLOCK_READ and (not isinstance(data, dict)
                    or not isinstance(data.get("read"), dict) or "researchHarnessState" not in data["read"]):
                    raise ValueError("SQL Connect clock-read response invalid")
                return data

            return _sql_connect_transport(self.repository, operation, variables, True, decode,
                clock_read=operation == _SQL_CLOCK_READ, authorize=authorize)
        else:
            try:
                return self.repository.execute(operation, variables, mutation=True)
            except BaseException as error:
                _sql_transport_context(error, operation, "adapter_execute", 1)
                raise

    def load(self, scope: DurabilityScope, program_key: str) -> StateDocument | None:
        data = self._execute(scope, program_key, _SQL_CLOCK_READ, self._variables(scope, program_key))
        row = data.get("read", {}).get("researchHarnessState")
        if row is None:
            return None
        if not row.get("stateJson"):
            raise ValueError("Exact persisted research serialization is unavailable")
        state = json.loads(row["stateJson"])
        if state != row["state"]:
            raise ValueError("Research state serialization differs from its SQL policy projection")
        return StateDocument(row["revision"], datetime.fromisoformat(row["observedAt"].replace("Z", "+00:00")).timestamp(), state)

    def create(self, scope: DurabilityScope, program_key: str, state: dict[str, Any]) -> None:
        try:
            self._execute(scope, program_key, "CreateResearchHarnessStateV1", dict(self._variables(scope, program_key), state=state, stateJson=canonical(state).decode()))
        except Exception as exc:
            # Ambiguous transport is not presumed unsent; readback resolves create.
            if self.load(scope, program_key) is not None:
                raise CasConflict("Program exists after create") from exc
            raise

    def cas(self, scope: DurabilityScope, program_key: str, revision: int, state: dict[str, Any], *, valid_until: float | None = None, review_required: bool = False, send_authorization: dict | None = None) -> None:
        variables = dict(self._variables(scope, program_key), expectedRevision=revision, state=state, stateJson=canonical(state).decode(), reviewRequired=review_required, validUntil=datetime.fromtimestamp(valid_until, timezone.utc).isoformat() if valid_until is not None else None)
        if send_authorization is not None:
            variables["sendAuthorizationJson"] = canonical(send_authorization).decode()
        try:
            self._execute(scope, program_key, "CompareResearchHarnessStateV1", variables)
        except Exception as exc:
            # Readback handles both concurrent siblings and a committed response
            # lost in transit. No external dispatch is inside this retry loop.
            current = self.load(scope, program_key)
            if current and current.revision != revision:
                raise CasConflict("SQL-only rebase required") from exc
            if current and valid_until is not None and current.server_time >= valid_until:
                raise StaleWork("Lease expired at connector commit") from exc
            raise


class ResearchStore:
    def __init__(self, backend: StateBackend, program_key: str, *, max_cas_retries: int = 32,
                 live_authority: LiveResearchAuthority | None = None):
        if not program_key:
            raise ValueError("Bind the existing shared ProgramLedger identity")
        self.backend, self.program_key = backend, program_key
        self.max_cas_retries = max_cas_retries
        self.live_authority = live_authority

    def require_live_authority(self, scope: DurabilityScope) -> None:
        """Refuse live work unless this store's authority covers the scope.

        A store built without an authority, such as the API store, refuses
        every live effect and live retry. The budget policy's live flag is
        checked separately when an effect is reserved.
        """
        if self.live_authority is None or not self.live_authority.covers(scope):
            raise PermissionError("research_live_authority_required")

    def initialize(self, scope: DurabilityScope, policy: BudgetPolicy) -> None:
        existing = self.backend.load(scope, self.program_key)
        if existing:
            if existing.state["budget_policy"] != asdict(policy):
                raise ValueError("Existing cumulative allowance cannot be reset")
            return
        state = {"contract_version": CONTRACT_VERSION, "program_key": self.program_key,
                 "budget_policy": asdict(policy), "jobs": {}, "effects": {}, "journal": {},
                 "media": {}, "outbox": {}, "halted": False}
        state["budget_totals"] = self._budget(state)
        try:
            self.backend.create(scope, self.program_key, state)
        except CasConflict:
            self.initialize(scope, policy)

    def reconcile_ordinary_spend(self, scope: DurabilityScope, cumulative_micros: int) -> None:
        """Carry later ordinary calls without changing the immutable policy seed.

        Reviewer corrections may repeat a paid parse. A high-water mark makes
        replay idempotent and never releases a prior known or unknown liability.
        """
        if type(cumulative_micros) is not int or cumulative_micros < 0:
            raise ValueError("Ordinary liability must be nonnegative integer microUSD")

        def reduce(state, _):
            seed = state["budget_policy"]["external_settled_micro_usd"]
            state["ordinary_cost_micros"] = max(seed, state.get("ordinary_cost_micros", seed), cumulative_micros)
        self._mutate(scope, reduce)

    def reserve_ordinary(self, scope: DurabilityScope, key: str, micros: int, cumulative_micros: int) -> None:
        """CAS one ordinary pre-send liability against the research run's cap.

        Failed canonical saves keep their reservations; only an identical
        step/attempt replays without adding another hold. Research reserves use
        this same document and therefore cannot race past the per-run ceiling.
        """
        if (type(key) is not str or not key or type(micros) is not int or micros <= 0
            or type(cumulative_micros) is not int or cumulative_micros < 0):
            raise ValueError("Invalid ordinary reservation")
        def reduce(state, _):
            reservations = state.setdefault("ordinary_reservations", {})
            if key in reservations:
                if reservations[key]["reserved_micros"] != micros:
                    raise HeldUnknown("ordinary_reservation_changed")
                return
            seed = state["budget_policy"]["external_settled_micro_usd"]
            state["ordinary_cost_micros"] = max(seed, state.get("ordinary_cost_micros", seed), cumulative_micros)
            if state["halted"] or micros > self._budget(state)["remaining_micro_usd"]:
                raise BudgetExceeded("run_cost_allowance_exhausted")
            state["ordinary_cost_micros"] += micros
            reservations[key] = {"reserved_micros": micros, "settled_micros": None}
        self._mutate(scope, reduce)

    def settle_ordinary(self, scope: DurabilityScope, key: str, micros: int) -> None:
        """Release only one ordinary attempt's known unused reservation."""
        if type(micros) is not int or micros < 0:
            raise ValueError("Invalid ordinary settlement")
        def reduce(state, _):
            entry = state.get("ordinary_reservations", {}).get(key)
            if entry is None:
                return  # Historical calls remain in the immutable original seed.
            if entry["settled_micros"] is not None:
                if entry["settled_micros"] != micros:
                    raise HeldUnknown("ordinary_settlement_changed")
                return
            seed = state["budget_policy"]["external_settled_micro_usd"]
            state["ordinary_cost_micros"] = max(seed,
                state["ordinary_cost_micros"] - entry["reserved_micros"] + micros)
            entry["settled_micros"] = micros
            if micros > entry["reserved_micros"]:
                state["halted"] = True  # Keep a provider-contract anomaly in full.
        self._mutate(scope, reduce)

    def _read(self, scope: DurabilityScope) -> StateDocument:
        doc = self.backend.load(scope, self.program_key)
        if doc is None or doc.state.get("contract_version") != CONTRACT_VERSION:
            raise ValueError("Missing or unsupported research state")
        return doc

    def _mutate(self, scope: DurabilityScope, reducer: Callable[[dict[str, Any], float], Any], *, lease: Lease | None = None, review_required: bool = False, force_cas: bool = False, send_authorization: dict | None = None) -> Any:
        for attempt in range(self.max_cas_retries):
            doc = self._read(scope)
            state = copy.deepcopy(doc.state)
            result = reducer(state, doc.server_time)
            if state == doc.state and not force_cas and lease is None and not review_required:
                return result
            state["budget_totals"] = self._budget(state)
            if len(canonical(state)) > MAX_STATE_BYTES:
                raise ValueError("Bounded research aggregate is full; no dispatch authorized")
            try:
                self.backend.cas(scope, self.program_key, doc.revision, state, valid_until=lease.expires_at if lease else None, review_required=review_required,
                    **({"send_authorization": send_authorization} if send_authorization is not None else {}))
                return result
            except CasConflict:
                if attempt + 1 < self.max_cas_retries:
                    time.sleep(random.uniform(0, min(CAS_PAUSE_MAX_SECONDS, CAS_PAUSE_FIRST_SECONDS * 2 ** attempt)))
                continue
        raise CasConflict("Bounded SQL rebase limit exceeded")

    @staticmethod
    def _job(state: dict[str, Any], scope: DurabilityScope, *, current: bool = True) -> dict[str, Any]:
        job = state["jobs"].get(scope.key)
        identity = {k: v for k, v in scope.identity().items() if k != "generation"}
        if not job or job["identity"] != identity or job["sensitive"] != scope.sensitive:
            raise PermissionError("Job not found in requested scope")
        if current and job["generation"] != scope.generation:
            raise StaleWork("Input generation changed")
        return job

    @classmethod
    def _lease(cls, state: dict[str, Any], scope: DurabilityScope, lease: Lease, now: float) -> dict[str, Any]:
        job = cls._job(state, scope)
        current = job.get("lease")
        if job["paused"] or lease.job_key != scope.key or lease.generation != scope.generation or current != asdict(lease) or lease.expires_at <= now:
            raise StaleWork("Current active generation and lease fence required")
        return job

    def create_job(self, scope: DurabilityScope, pins: PinnedRuntime, field_keys: list[str], *, dependencies: Mapping[str, int] | None = None, record_revision: int = 0, human_locks: Mapping[str, str] | None = None, preserved_human_outcomes: Mapping[str, Any] | None = None) -> dict[str, Any]:
        human_locks = dict(human_locks or {})
        preserved = copy.deepcopy(dict(preserved_human_outcomes or {}))
        if preserved:
            from specimen_digitization.application.human_field_carry import PreservedHumanFieldOutcome, contract_pin
            if pins.sources.get("human_field_carry") != contract_pin() or not set(preserved) <= set(human_locks):
                raise ValueError("Preserved outcomes require current verified carry provenance")
            for key, raw in preserved.items():
                value = PreservedHumanFieldOutcome.model_validate(raw)
                if str(value.field_key) != key or human_locks[key] != value.proof_digest:
                    raise ValueError("Preserved outcome proof mismatch")
        if not set(human_locks) <= set(field_keys) or any(
                type(proof) is not str or len(proof) != 64 for proof in human_locks.values()):
            raise ValueError("Human locks require verified field provenance")
        if scope.generation < 1 or not field_keys or len(set(field_keys)) != len(field_keys):
            raise ValueError("A job requires a positive generation and distinct field keys")
        payload = pins.payload()
        def reduce(state, _):
            if scope.key in state["jobs"]:
                job = self._job(state, scope)
                if (job["pins"] != payload or set(job["fields"]) != set(field_keys)
                    or job.get("human_lock_proofs", {}) != human_locks
                    or job.get("preserved_human_outcomes", {}) != preserved):
                    raise ValueError("Runtime bindings are immutable for this generation")
                return copy.deepcopy(job)
            job = {"identity": {k: v for k, v in scope.identity().items() if k != "generation"},
                   "generation": scope.generation, "sensitive": scope.sensitive, "pins": payload,
                   "binding_digest": digest(payload), "fence": 0, "lease": None, "paused": False,
                   "record_revision": record_revision, "dependencies": dict(dependencies or {}),
                   "trace_context": None, "human_lock_proofs": human_locks,
                   "fields": {k: {"revision": 0, "locked": k in human_locks, "checkpoint": None,
                       "work_state": "waiting_human" if k in human_locks else "pending", "reuse": None} for k in field_keys},
                   "checkpoints": [], "history": []}
            if preserved:
                job["preserved_human_outcomes"] = preserved
            state["jobs"][scope.key] = job
            return copy.deepcopy(job)
        return self._mutate(scope, reduce)

    def job(self, scope: DurabilityScope) -> dict[str, Any]:
        return copy.deepcopy(self._job(self._read(scope).state, scope))

    def claim(self, scope: DurabilityScope, owner: str, *, ttl_seconds: int = 60) -> Lease:
        if not owner or not 1 <= ttl_seconds <= MAX_LEASE_TTL_SECONDS:
            raise ValueError(f"Lease TTL must be 1..{MAX_LEASE_TTL_SECONDS} seconds")
        def reduce(state, now):
            job = self._job(state, scope)
            if job["paused"] or (job["lease"] and job["lease"]["expires_at"] > now):
                raise StaleWork("Job paused or already claimed")
            job["fence"] += 1
            lease = Lease(scope.key, owner, job["fence"], scope.generation, now + ttl_seconds)
            job["lease"] = asdict(lease)
            return lease
        return self._mutate(scope, reduce)

    def release(self, scope: DurabilityScope, lease: Lease, *, blocked: bool = False) -> None:
        """Release only this known completed step; uncertain effects retain custody.

        ``blocked`` is a window that ended blocked (its publication pass refused or could not
        verify something). It is released too, but custody is kept as well while an effect is only
        reserved (not yet proven unsent or sent) and while a publication was prepared and not
        delivered: its outcome is in doubt (its attempt may be marked at the connector, and the next
        step must reconcile it), so no one else may step in under a fresh lease."""
        def reduce(state, now):
            job = self._lease(state, scope, lease, now)
            uncertain = {"sending", "held_unknown", "reserved"} if blocked else {"sending", "held_unknown"}
            if any(effect["job_key"] == scope.key and effect["scope"] == scope.identity()
                and (effect["status"] in uncertain
                    or effect.get("receipt") is not None and effect["actual_micro_usd"] is None)
                for effect in state["effects"].values()):
                raise HeldUnknown("Uncertain effect retains its lease custody")
            if blocked and any(item.get("kind") == "canonical_publication_required"
                and item.get("delivered") is False and item.get("guard", {}).get("scope") == scope.identity()
                for item in state["outbox"].values()):
                raise HeldUnknown("A publication in doubt retains its lease custody")
            job["lease"] = None
        self._mutate(scope, reduce, lease=lease)

    def heartbeat(self, scope: DurabilityScope, lease: Lease, *, ttl_seconds: int = 60) -> Lease:
        if not 1 <= ttl_seconds <= MAX_LEASE_TTL_SECONDS:
            raise ValueError(f"Lease TTL must be 1..{MAX_LEASE_TTL_SECONDS} seconds")
        def reduce(state, now):
            job = self._lease(state, scope, lease, now)
            renewed = Lease(lease.job_key, lease.owner, lease.fence, lease.generation, now + ttl_seconds)
            job["lease"] = asdict(renewed)
            return renewed
        return self._mutate(scope, reduce, lease=lease)

    def bind_trace(self, scope: DurabilityScope, lease: Lease, trace_context: Mapping[str, Any]) -> None:
        context = dict(trace_context)
        if set(context) != {"trace_id", "span_id", "trace_flags"} or not re.fullmatch(r"[0-9a-f]{32}", context.get("trace_id", "")) or not re.fullmatch(r"[0-9a-f]{16}", context.get("span_id", "")) or int(context["trace_id"], 16) == 0 or int(context["span_id"], 16) == 0 or type(context["trace_flags"]) is not int or not 0 <= context["trace_flags"] <= 255:
            raise ValueError("Validated W3C trace context required")
        def reduce(state, now):
            job = self._lease(state, scope, lease, now)
            if job["trace_context"] is not None and job["trace_context"] != context:
                raise TraceContextConflict("Trace context is immutable within a generation")
            job["trace_context"] = context
        self._mutate(scope, reduce, lease=lease)

    @staticmethod
    def _budget(state: dict[str, Any]) -> dict[str, Any]:
        policy = state["budget_policy"]
        values = [policy["ceiling_micro_usd"], policy["external_held_micro_usd"],
            policy["external_settled_micro_usd"], state.get("ordinary_cost_micros", 0)]
        for effect in state["effects"].values():
            values.extend([effect["held_micro_usd"],
                0 if effect.get("actual_micro_usd") is None else effect["actual_micro_usd"]])
        if any(type(value) is not int or value < 0 for value in values):
            raise HeldUnknown("research_budget_state_unavailable")
        held = policy["external_held_micro_usd"]
        settled = max(policy["external_settled_micro_usd"], state.get("ordinary_cost_micros", 0))
        for effect in state["effects"].values():
            held += effect["held_micro_usd"]
            settled += effect.get("actual_micro_usd") or 0
        return {"held_micro_usd": held, "settled_micro_usd": settled,
                "ceiling_micro_usd": policy["ceiling_micro_usd"],
                "remaining_micro_usd": max(0, policy["ceiling_micro_usd"] - held - settled),
                "halted": state["halted"], "external_ledger_digest": policy["external_ledger_digest"]}

    def budget(self, scope: DurabilityScope) -> dict[str, Any]:
        return self._budget(self._read(scope).state)

    def _field_admission(self, job: dict[str, Any], field_keys: tuple[str, ...] | list[str], *,
                         scope=None, operation_key=None, request_digest=None) -> None:
        served = set(field_keys or job["fields"])
        if any(key not in job["fields"] for key in served):
            raise PermissionError("Effect serves fields outside the pinned job")
        if any(job["fields"][key]["locked"] for key in served):
            permit = _locked_source_read.get()
            if (permit is None or permit.closed.is_set() or permit.broker.store is not self or permit.scope != scope
                or permit.operation_key != operation_key or permit.request_digest != request_digest
                or tuple(field_keys) != (permit.field_key,)):
                raise StaleWork("Effect serves a human-locked field")

    def reserve_effect(self, scope: DurabilityScope, lease: Lease, operation_key: str, request: Any, reservation_micro_usd: int, *, execution_class: str = "offline", field_keys: tuple[str, ...] = ()) -> dict[str, Any]:
        if not operation_key or type(reservation_micro_usd) is not int or reservation_micro_usd <= 0:
            raise ValueError("Every possibly charged effect requires a positive conservative reservation")
        if execution_class not in {"offline", "live"}:
            raise ValueError("Explicit offline or live dispatch class required")
        if execution_class == "live":
            self.require_live_authority(scope)
        _revalidate_locked_source_read(self, scope)
        request_hash = digest(request)
        def reduce(state, now):
            job = self._job(state, scope)
            if any(key not in job["fields"] for key in field_keys):
                raise PermissionError("Effect serves fields outside the pinned job")
            effect_id = digest({"scope": scope.identity(), "operation_key": operation_key,
                                "request_digest": request_hash, "binding_digest": job["binding_digest"]})
            old = state["effects"].get(effect_id)
            if old:
                if old["execution_class"] != execution_class or old["reservation_micro_usd"] != reservation_micro_usd or old.get("field_keys", []) != list(field_keys):
                    raise ValueError("Existing logical effect policy changed")
                if old["status"] == "reserved":
                    self._field_admission(job, field_keys, scope=scope,
                        operation_key=operation_key, request_digest=request_hash)
                return copy.deepcopy(old)
            self._field_admission(job, field_keys, scope=scope,
                operation_key=operation_key, request_digest=request_hash)
            self._lease(state, scope, lease, now)
            budget = self._budget(state)
            if state["halted"] or reservation_micro_usd > budget["remaining_micro_usd"]:
                raise BudgetExceeded("Cumulative settled plus held exceeds shared allowance")
            if execution_class == "live" and not state["budget_policy"]["live_authorized"]:
                raise PermissionError("Live dispatch blocked by imported program HOLD")
            effect = {"effect_id": effect_id, "scope": scope.identity(), "job_key": scope.key,
                      "operation_key": operation_key, "request_digest": request_hash,
                      "binding_digest": job["binding_digest"], "execution_class": execution_class,
                      "field_keys": list(field_keys),
                      "reservation_micro_usd": reservation_micro_usd, "held_micro_usd": reservation_micro_usd,
                      "actual_micro_usd": None, "prior_actual_micro_usd": 0,
                      "status": "reserved", "attempts": [], "receipt": None, "previous_receipts": []}
            state["effects"][effect_id] = effect
            return copy.deepcopy(effect)
        return self._mutate(scope, reduce, lease=lease)

    @staticmethod
    def _effect(state: dict[str, Any], scope: DurabilityScope, effect_id: str) -> dict[str, Any]:
        effect = state["effects"].get(effect_id)
        if not effect or effect["scope"] != scope.identity():
            raise PermissionError("Effect not found in requested scope/generation")
        return effect

    def effect(self, scope: DurabilityScope, effect_id: str) -> dict[str, Any]:
        return copy.deepcopy(self._effect(self._read(scope).state, scope, effect_id))

    def mark_sending(self, scope: DurabilityScope, lease: Lease, effect_id: str, *, send_authorization: dict | None = None) -> dict[str, Any]:
        _revalidate_locked_source_read(self, scope)
        attempt_id = str(uuid4())
        def reduce(state, now):
            job = self._lease(state, scope, lease, now)
            if state["halted"]:
                raise BudgetExceeded("Shared program halted; reserved holds remain unresolved")
            effect = self._effect(state, scope, effect_id)
            self._field_admission(job, effect["field_keys"], scope=scope,
                operation_key=effect["operation_key"], request_digest=effect["request_digest"])
            if effect["status"] != "reserved":
                raise HeldUnknown("Only a proven-unsent reserved intent can dispatch")
            attempt = {"attempt_id": attempt_id, "provider_idempotency_key": effect_id,
                       "capture_locator": f"research-capture/{digest(scope.identity())}/{effect_id}/{attempt_id}",
                       "raw_capture_locator": f"research-capture/{digest(scope.identity())}/{effect_id}/{attempt_id}/raw",
                       "sent_at": now, "status": "sending"}
            effect["attempts"].append(attempt)
            effect["status"] = "sending"
            return copy.deepcopy(attempt)
        return self._mutate(scope, reduce, lease=lease, send_authorization=send_authorization)

    def validate_dispatch(self, scope: DurabilityScope, lease: Lease, effect_id: str, attempt_id: str) -> None:
        _revalidate_locked_source_read(self, scope)
        doc = self._read(scope)
        job = self._lease(doc.state, scope, lease, doc.server_time)
        if doc.state["halted"]:
            raise BudgetExceeded("Shared program halted before dispatch")
        effect = self._effect(doc.state, scope, effect_id)
        self._field_admission(job, effect["field_keys"], scope=scope,
            operation_key=effect["operation_key"], request_digest=effect["request_digest"])
        if effect["status"] != "sending" or effect["attempts"][-1]["attempt_id"] != attempt_id:
            raise HeldUnknown("Current dispatch attempt required")

    def retry_effect(self, scope: DurabilityScope, lease: Lease, effect_id: str) -> None:
        """Explicit bounded retry only after authoritative no-effect/known-cost proof."""
        def reduce(state, now):
            job = self._lease(state, scope, lease, now)
            effect = self._effect(state, scope, effect_id)
            receipt = effect["receipt"]
            settings = job["pins"]["settings"]
            if not settings.get("retry_failed_no_effect", False) or len(effect["attempts"]) >= settings.get("safe_retry_attempt_limit", 1):
                raise PermissionError("Pinned type-specific retry policy does not authorize an attempt")
            if not receipt or receipt["outcome"] != "failed_no_effect" or receipt["actual_micro_usd"] is None:
                raise HeldUnknown("Retry requires a no-effect receipt and authoritative settled cost")
            budget = self._budget(state)
            if state["halted"] or effect["reservation_micro_usd"] > budget["remaining_micro_usd"]:
                raise BudgetExceeded("Retry cannot fit shared cumulative allowance")
            effect["previous_receipts"].append(copy.deepcopy(receipt))
            effect["prior_actual_micro_usd"] = effect["actual_micro_usd"]
            effect.update(status="reserved", receipt=None, held_micro_usd=effect["reservation_micro_usd"])
        self._mutate(scope, reduce, lease=lease)

    def hold_unknown(self, scope: DurabilityScope, effect_id: str, reason: str) -> None:
        def reduce(state, _):
            effect = self._effect(state, scope, effect_id)
            if effect["status"] in {"sending", "held_unknown"}:
                effect["status"] = "held_unknown"
                effect["reason_code"] = reason
                effect["attempts"][-1]["status"] = "held_unknown"
                job = self._job(state, scope, current=False)
                if job["generation"] == scope.generation:
                    for key in effect["field_keys"]:
                        job["fields"][key]["work_state"] = "operational_failed"
        self._mutate(scope, reduce)

    def finalize_effect(self, scope: DurabilityScope, effect_id: str, attempt_id: str, capture: BlobRef, result: CapturedResult, *, raw_capture: BlobRef | None = None) -> EffectReceipt:
        receipt = EffectReceipt(effect_id, attempt_id, result.typed_payload, capture, result.actual_micro_usd,
                                0, result.provider_request_id, dict(result.usage), result.outcome, raw_capture)
        def reduce(state, now):
            effect = self._effect(state, scope, effect_id)
            attempt = next((a for a in effect["attempts"] if a["attempt_id"] == attempt_id), None)
            if not attempt or capture.locator != attempt["capture_locator"]:
                raise PermissionError("Predeclared capture envelope required")
            if raw_capture and raw_capture.locator != attempt["raw_capture_locator"]:
                raise PermissionError("Predeclared raw capture required")
            # Financial reconciliation intentionally survives generation/fence
            # changes. Scientific publication goes through a separate guard.
            final = asdict(receipt)
            final["held_micro_usd"] = effect["reservation_micro_usd"] if result.actual_micro_usd is None else 0
            if effect["receipt"]:
                if effect["receipt"] != final:
                    raise ValueError("Immutable receipt changed")
                return EffectReceipt(**{**final, "capture": BlobRef(**final["capture"]), "raw_capture": BlobRef(**final["raw_capture"]) if final["raw_capture"] else None})
            actual = effect["prior_actual_micro_usd"] + result.actual_micro_usd if result.actual_micro_usd is not None else effect["prior_actual_micro_usd"] or None
            effect.update(status="completed", receipt=final, held_micro_usd=final["held_micro_usd"], actual_micro_usd=actual)
            attempt.update(status="completed", capture=asdict(capture), completed_at=now)
            if result.actual_micro_usd is not None and result.actual_micro_usd > effect["reservation_micro_usd"]:
                state["halted"] = True
            if self._budget(state)["remaining_micro_usd"] == 0:
                state["halted"] = True
            state["outbox"]["receipt/" + effect_id] = {"kind": "effect_completed", "effect_id": effect_id, "scope": scope.identity(), "delivered": False}
            return EffectReceipt(**{**final, "capture": BlobRef(**final["capture"]), "raw_capture": BlobRef(**final["raw_capture"]) if final["raw_capture"] else None})
        return self._mutate(scope, reduce)

    @staticmethod
    def _dependencies(job: dict[str, Any], revisions: Mapping[str, int], digests: Mapping[str, str]) -> None:
        if set(revisions) != set(digests):
            raise ValueError("Every consumed dependency requires its exact resolution digest")
        for key, revision in revisions.items():
            value = job["fields"].get(key)
            checkpoint = value["checkpoint"] if value else None
            if not checkpoint or value["revision"] != revision or checkpoint["revision"] != revision:
                raise StaleWork("Consumed field checkpoint revision changed")
            payload = checkpoint["payload"]
            resolution = payload.get("resolution", payload) if isinstance(payload, dict) else payload
            if digest(resolution) != digests[key] or job["dependencies"].get(key, revision) != revision:
                raise StaleWork("Consumed field checkpoint digest changed")
            job["dependencies"][key] = revision

    def checkpoint(self, scope: DurabilityScope, lease: Lease, field_key: str, payload: Any, *, expected_revision: int, receipt_ids: tuple[str, ...] = (), dependencies: Mapping[str, int] | None = None, dependency_digests: Mapping[str, str] | None = None, retry_command_id: str | None = None) -> dict[str, Any]:
        return self.checkpoint_batch(scope, lease, [{"field_key": field_key, "payload": payload,
            "expected_revision": expected_revision, "receipt_ids": receipt_ids,
            "dependencies": dependencies or {}, "dependency_digests": dependency_digests or {}, "retry_command_id": retry_command_id}])[0]

    def checkpoint_batch(self, scope: DurabilityScope, lease: Lease, entries: list[Mapping[str, Any]], *, accepted_output_proof: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        """Commit an acyclic specialist closure, including derived siblings, in one CAS."""
        frozen = copy.deepcopy(entries)
        proof = copy.deepcopy(accepted_output_proof)
        indexed = {entry["field_key"]: entry for entry in frozen}
        if not frozen or len(indexed) != len(frozen):
            raise ValueError("A checkpoint batch requires distinct fields")
        ordered, visiting, visited = [], set(), set()
        def visit(key):
            if key in visiting:
                raise ValueError("Checkpoint dependency cycle")
            if key in visited:
                return
            visiting.add(key)
            for dependency in sorted(indexed[key].get("dependencies", {})):
                if dependency in indexed:
                    visit(dependency)
            visiting.remove(key)
            visited.add(key)
            ordered.append(indexed[key])
        for key in sorted(indexed):
            visit(key)
        def reduce(state, now):
            job = self._lease(state, scope, lease, now)
            if proof is not None:
                if (set(proof) != {"contract_version", "proof_digest", "native_run_id", "conversation_id",
                    "agent_name", "request_digest", "capture", "checkpoint_payload_digests"}
                    or proof["contract_version"] != "research-accepted-checkpoints/v1"
                    or proof["checkpoint_payload_digests"] != [digest(entry["payload"]) for entry in frozen]
                    or any(not re.fullmatch(r"[a-f0-9]{64}", proof[key])
                        for key in ("proof_digest", "request_digest"))):
                    raise StaleWork("accepted_output_native_binding_invalid")
                run = state["journal"].get(proof["native_run_id"])
                if (run is None or run["scope"] != scope.identity()
                    or run["agent_name"] != proof["agent_name"]
                    or run["record"].get("conversation_id") != proof["conversation_id"]
                    or not any(snapshot.get("state") == "complete" for snapshot in run["snapshots"])):
                    raise StaleWork("accepted_output_native_run_unproven")
                capture = proof["capture"]
                if (set(capture) != {"locator", "generation", "sha256", "byte_size"}
                    or capture["sha256"] != proof["proof_digest"]
                    or type(capture["byte_size"]) is not int or capture["byte_size"] <= 0
                    or capture["locator"] != "research-journal/accepted-output/" + digest(scope.identity())
                        + "/" + proof["proof_digest"] + ".json"):
                    raise StaleWork("accepted_output_native_capture_invalid")
            if len(frozen) == 1 and frozen[0].get("retry_command_id"):
                entry = frozen[0]
                command = self._retry_command(state, scope, entry["retry_command_id"])
                if command.get("result_checkpoint_id"):
                    checkpoint = self._retry_result(job, command, command["result_checkpoint_id"])
                    if command["status"] not in {"running", "completed"} or command.get("lease") != asdict(lease) or command["field_key"] != entry["field_key"] or command["expected_field_revision"] != entry["expected_revision"] or checkpoint["payload"] != entry["payload"] or (proof is not None and checkpoint.get("accepted_output_proof") != proof) or checkpoint["receipt_ids"] != list(entry.get("receipt_ids", ())) or checkpoint["dependencies"] != entry.get("dependencies", {}) or checkpoint["dependency_digests"] != entry.get("dependency_digests", {}):
                        raise StaleWork("Retry checkpoint replay differs from its committed boundary")
                    return [copy.deepcopy(checkpoint)]
            for entry in frozen:
                field_state = job["fields"].get(entry["field_key"])
                if not field_state or field_state["locked"] or field_state["revision"] != entry["expected_revision"]:
                    raise StaleWork("Field revision or human lock changed")
                if any(effect["job_key"] == scope.key and effect["scope"]["generation"] == scope.generation
                    and effect["status"] == "sending" and (not effect["field_keys"] or entry["field_key"] in effect["field_keys"])
                    for effect in state["effects"].values()):
                    raise HeldUnknown("An in-flight field effect must settle before checkpoint publication")
            committed = {}
            for entry in ordered:
                field_key, payload, expected_revision = entry["field_key"], entry["payload"], entry["expected_revision"]
                command_id = entry.get("retry_command_id")
                if isinstance(payload, dict) and "retry_command_id" in payload and payload["retry_command_id"] != command_id:
                    raise StaleWork("Typed checkpoint and native host command pin disagree")
                if command_id:
                    command = self._retry_command(state, scope, command_id)
                    if command["status"] != "running" or command["lease"] != asdict(lease) or command["field_key"] != field_key or command["expected_field_revision"] != expected_revision or command["binding_digest"] != job["binding_digest"] or digest(job["fields"][field_key]["checkpoint"]) != command["checkpoint_digest"] or command.get("result_checkpoint_id"):
                        raise StaleWork("Retry checkpoint does not match the claimed host revision and lease")
                elif job["fields"][field_key].get("retry_command_id"):
                    raise StaleWork("A queued retry checkpoint requires its explicit host command pin")
                receipt_ids = entry.get("receipt_ids", ())
                dependencies, dependency_digests = entry.get("dependencies", {}), entry.get("dependency_digests", {})
                self._dependencies(job, dependencies, dependency_digests)
                for effect_id in receipt_ids:
                    if not self._effect(state, scope, effect_id)["receipt"]:
                        raise HeldUnknown("Checkpoint requires committed effect receipts")
                field_state = job["fields"][field_key]
                checkpoint = {"id": digest({"scope": scope.identity(), "field": field_key, "revision": expected_revision + 1, "payload": payload}),
                              "scope": scope.identity(), "field_key": field_key, "revision": expected_revision + 1,
                              "previous": field_state["checkpoint"]["id"] if field_state["checkpoint"] else None,
                              "sequence": len(job["checkpoints"]) + 1, "payload": copy.deepcopy(payload),
                              "binding_digest": job["binding_digest"], "trace_context": copy.deepcopy(job["trace_context"]),
                              "receipt_ids": list(receipt_ids), "dependencies": dict(dependencies),
                              "dependency_digests": dict(dependency_digests), "at": now}
                checkpoint.update(retry_command_id=command_id, lease_fence=lease.fence, lease_owner=lease.owner)
                if proof is not None:
                    checkpoint["accepted_output_proof"] = copy.deepcopy(proof)
                if command_id:
                    command.update(result_checkpoint_id=checkpoint["id"], result_lease=asdict(lease))
                job["checkpoints"].append(checkpoint)
                resolution = payload.get("resolution", payload) if isinstance(payload, dict) else payload
                work_state = resolution.get("work_state", resolution.get("state", "pending")) if isinstance(resolution, dict) else "pending"
                field_state.update(revision=expected_revision + 1, checkpoint=checkpoint, work_state=work_state, reuse=None, retry_command_id=None)
                if field_key in job["dependencies"]:
                    job["dependencies"][field_key] = expected_revision + 1
                state["outbox"]["checkpoint/" + checkpoint["id"]] = {"kind": "field_checkpoint", "scope": scope.identity(), "checkpoint_id": checkpoint["id"], "delivered": False}
                committed[field_key] = copy.deepcopy(checkpoint)
            if proof is not None:
                run = state["journal"][proof["native_run_id"]]
                accepted = run.setdefault("accepted_outputs", {})
                retained = {"proof":copy.deepcopy(proof),
                    "checkpoint_ids":[committed[entry["field_key"]]["id"] for entry in frozen]}
                old = accepted.get(proof["proof_digest"])
                if old is not None and old != retained:
                    raise StaleWork("accepted_output_immutable_record_changed")
                accepted[proof["proof_digest"]] = retained
            return [committed[entry["field_key"]] for entry in frozen]
        return self._mutate(scope, reduce, lease=lease)

    def pause(self, scope: DurabilityScope, *, expected_generation: int) -> None:
        def reduce(state, _):
            job = self._job(state, scope)
            if job["generation"] != expected_generation:
                raise StaleWork("Generation changed")
            job["paused"] = True
            job["lease"] = None
        self._mutate(scope, reduce)

    def correct_fields(self, scope: DurabilityScope, field_keys: list[str], *, expected_generation: int, new_pins: PinnedRuntime, invalidated_fields: tuple[str, ...] = (), dependency_revisions: Mapping[str, int] | None = None) -> DurabilityScope:
        pins = new_pins.payload()
        if not field_keys or set(field_keys).intersection(invalidated_fields):
            raise ValueError("Corrected and dependent invalidated fields must be explicit and distinct")
        def reduce(state, now):
            job = self._job(state, scope)
            if job["generation"] != expected_generation or any(k not in job["fields"] for k in (*field_keys, *invalidated_fields)):
                raise StaleWork("Generation or correction field changed")
            if pins["input_digest"] == job["pins"]["input_digest"]:
                raise ValueError("A corrected scientific input requires explicit new input bindings")
            new_dependencies = {**job["dependencies"], **dict(dependency_revisions or {})}
            for key in (*field_keys, *invalidated_fields):
                new_dependencies[key] = job["fields"][key]["revision"] + 1
            for key, value in job["fields"].items():
                if key in (*field_keys, *invalidated_fields) or not value["checkpoint"]:
                    continue
                if any(new_dependencies.get(k) != v for k, v in value["checkpoint"]["dependencies"].items()):
                    raise ValueError("Affected dependency closure is incomplete")
                if any(pins[k] != job["pins"][k] for k in pins if k != "input_digest"):
                    raise ValueError("Changed runtime policy requires explicit field invalidation, not implicit reuse")
            job["history"].append({"scope": scope.identity(), "generation": job["generation"], "pins": copy.deepcopy(job["pins"]), "binding_digest": job["binding_digest"], "fields": copy.deepcopy(job["fields"]), "dependencies": copy.deepcopy(job["dependencies"]), "trace_context": copy.deepcopy(job["trace_context"]), "at": now})
            for event in state["outbox"].values():
                command = event.get("command")
                if event["kind"] == "research_field_retry" and command["scope"] == scope.identity():
                    if command["status"] in {"queued", "running"}:
                        command.update(status="blocked", blocked_reason="generation_superseded", completed_at=now)
                    event["delivered"] = True
            for value in job["fields"].values():
                if value.get("retry_command_id") and value["checkpoint"]:
                    payload = value["checkpoint"]["payload"]
                    resolution = payload.get("resolution", payload) if isinstance(payload, dict) else {}
                    value["work_state"] = resolution.get("work_state", resolution.get("state", "pending"))
                value["retry_command_id"] = None
            job["generation"] += 1
            job["pins"], job["binding_digest"] = pins, digest(pins)
            job["lease"], job["paused"] = None, False
            job["dependencies"] = new_dependencies
            new_scope = DurabilityScope(scope.organization_id, scope.collection_id, scope.specimen_id, scope.job_id, job["generation"], scope.actor_uid, scope.sensitive)
            for key in field_keys:
                job["fields"][key].update(locked=True, revision=job["fields"][key]["revision"] + 1, checkpoint=None, work_state="waiting_human", reuse=None)
            for key in invalidated_fields:
                job["fields"][key].update(locked=False, revision=job["fields"][key]["revision"] + 1, checkpoint=None, work_state="pending", reuse=None)
            for key, value in job["fields"].items():
                checkpoint = value["checkpoint"]
                if key not in (*field_keys, *invalidated_fields) and checkpoint:
                    value["reuse"] = {"reused_from_scope_digest": digest(checkpoint["scope"]),
                                     "checkpoint_digest": digest(checkpoint), "into_scope_digest": digest(new_scope.identity()),
                                     "source_binding_digest": checkpoint["binding_digest"], "target_binding_digest": job["binding_digest"],
                                     "retained_dependencies": copy.deepcopy(checkpoint["dependencies"]),
                                     "retained_dependency_digests": copy.deepcopy(checkpoint.get("dependency_digests", {}))}
            return new_scope
        return self._mutate(scope, reduce, review_required=True)

    def accept_human_checkpoint(self, scope: DurabilityScope, field_key: str, payload: Any, *, expected_field_revision: int, canonical_commit_reference: str, verify_commit: Callable[[DurabilityScope, str, Any], bool]) -> dict[str, Any]:
        """Journal an already accepted sole-writer human decision, never invent one."""
        if not canonical_commit_reference or not verify_commit(scope, canonical_commit_reference, payload):
            raise PermissionError("Verified canonical human decision required")
        def reduce(state, now):
            job = self._job(state, scope)
            value = job["fields"].get(field_key)
            if not value or not value["locked"] or value["revision"] != expected_field_revision:
                raise StaleWork("Human decision field revision changed")
            item = {"scope": scope.identity(), "field_key": field_key, "revision": expected_field_revision + 1,
                    "sequence": len(job["checkpoints"]) + 1, "previous": None, "payload": copy.deepcopy(payload),
                    "binding_digest": job["binding_digest"], "trace_context": copy.deepcopy(job["trace_context"]),
                    "receipt_ids": [], "dependencies": {}, "dependency_digests": {}, "canonical_commit_reference": canonical_commit_reference,
                    "authority": "canonical_human_decision", "at": now}
            item["id"] = digest({k: v for k, v in item.items() if k != "at"})
            job["checkpoints"].append(item)
            value.update(revision=expected_field_revision + 1, checkpoint=item, work_state="resolved", reuse=None)
            if field_key in job["dependencies"]:
                job["dependencies"][field_key] = expected_field_revision + 1
            return copy.deepcopy(item)
        return self._mutate(scope, reduce, review_required=True)

    def resume(self, scope: DurabilityScope, *, expected_generation: int, pins: PinnedRuntime, field_keys: tuple[str, ...] = ()) -> None:
        def reduce(state, _):
            job = self._job(state, scope)
            if job["generation"] != expected_generation or job["pins"] != pins.payload():
                raise StaleWork("Resume must use the exact persisted generation bindings")
            fields = set(field_keys or job["fields"])
            if any(k not in job["fields"] for k in fields):
                raise PermissionError("Resume field scope is invalid")
            if any(e["job_key"] == scope.key and e["scope"]["generation"] == scope.generation and e["status"] in {"sending", "held_unknown"} and (not e["field_keys"] or fields.intersection(e["field_keys"])) for e in state["effects"].values()):
                raise HeldUnknown("Resume cannot automatically reissue unknown sent effects")
            job["paused"], job["lease"] = False, None
        self._mutate(scope, reduce)

    def admit_retry(self, scope: DurabilityScope, field_key: str, *, expected_generation: int, expected_field_revision: int, idempotency_key: str, execution_class: str = "live") -> dict[str, Any]:
        """Atomically queue one failed field; only server-configured fixtures use offline.

        A live retry needs a live authority on this store that covers the scope.
        No model call, lease release, budget activation or canonical write occurs.
        A consumer must independently classify its actual transport/provider.
        """
        if execution_class == "live":
            self.require_live_authority(scope)
        if execution_class not in {"offline", "live"} or not idempotency_key:
            raise ValueError("Explicit server-owned execution class and idempotency key required")
        def reduce(state, now):
            job = self._job(state, scope)
            value = job["fields"].get(field_key)
            checkpoint = value["checkpoint"] if value else None
            resolution = checkpoint["payload"].get("resolution", checkpoint["payload"]) if checkpoint and isinstance(checkpoint["payload"], dict) else {}
            failed = {"operational_failed", "retry_scheduled"}
            if expected_generation != job["generation"] or not value or value["revision"] != expected_field_revision or not checkpoint or checkpoint["revision"] != expected_field_revision:
                raise StaleWork("Retry generation or checkpoint revision changed")
            if job["paused"] or value["locked"] or value["work_state"] not in failed or not isinstance(resolution, dict) or resolution.get("work_state", resolution.get("state")) not in failed:
                raise StaleWork("Only an unlocked failed field may be retried")
            if state["halted"]:
                raise BudgetExceeded("Shared program halted")
            for effect in state["effects"].values():
                if effect["job_key"] == scope.key and (not effect["field_keys"] or field_key in effect["field_keys"]) and (effect["status"] in {"sending", "held_unknown"} or (effect["receipt"] is not None and effect["receipt"]["actual_micro_usd"] is None)):
                    raise HeldUnknown("Retry cannot reissue uncertain sent or charged effects")
            command_id = digest({"scope": scope.identity(), "field_key": field_key, "field_revision": expected_field_revision,
                                 "checkpoint_digest": digest(checkpoint), "binding_digest": job["binding_digest"], "idempotency_key": idempotency_key})
            old = state["outbox"].get("retry/" + command_id)
            if old:
                return copy.deepcopy(old["command"])
            if value.get("retry_command_id"):
                raise StaleWork("This checkpoint already has a queued retry command")
            command = {"id": command_id, "kind": "retry_field", "status": "queued", "scope": scope.identity(),
                       "field_key": field_key, "expected_generation": expected_generation,
                       "expected_field_revision": expected_field_revision, "checkpoint_digest": digest(checkpoint),
                       "binding_digest": job["binding_digest"], "execution_class": execution_class,
                       "idempotency_key": idempotency_key, "created_by": scope.actor_uid, "created_at": now}
            value.update(work_state="retry_scheduled", retry_command_id=command_id)
            state["outbox"]["retry/" + command_id] = {"kind": "research_field_retry", "command": command, "delivered": False}
            return copy.deepcopy(command)
        return self._mutate(scope, reduce, force_cas=True)

    def _retry_command(self, state: dict[str, Any], scope: DurabilityScope, command_id: str) -> dict[str, Any]:
        event = state["outbox"].get("retry/" + command_id)
        command = event.get("command") if event else None
        if not command or event["kind"] != "research_field_retry" or command["id"] != command_id or command["scope"] != scope.identity():
            raise PermissionError("Retry command is outside the requested generation")
        if command["execution_class"] != "offline":
            self.require_live_authority(scope)
        return command

    @staticmethod
    def _retry_result(job: dict[str, Any], command: Mapping[str, Any], checkpoint_id: str) -> dict[str, Any]:
        checkpoint = next((cp for cp in job["checkpoints"] if cp["id"] == checkpoint_id), None)
        proof = command.get("result_lease")
        if not checkpoint or checkpoint_id != command.get("result_checkpoint_id") or checkpoint.get("retry_command_id") != command["id"] or checkpoint["scope"] != command["scope"] or checkpoint["binding_digest"] != command["binding_digest"] or checkpoint["field_key"] != command["field_key"] or checkpoint["revision"] != command["expected_field_revision"] + 1 or not proof or checkpoint.get("lease_fence") != proof["fence"] or checkpoint.get("lease_owner") != proof["owner"]:
            raise StaleWork("Retry completion lacks its exact command-bound checkpoint and lease proof")
        return checkpoint

    def claim_retry_command(self, scope: DurabilityScope, lease: Lease, command_id: str) -> dict[str, Any]:
        """Claim queued work, or recover its committed result for acknowledgment only."""
        def reduce(state, now):
            job = self._lease(state, scope, lease, now)
            command = self._retry_command(state, scope, command_id)
            if command["binding_digest"] != job["binding_digest"]:
                raise StaleWork("Retry runtime binding changed")
            if command["status"] == "completed":
                self._retry_result(job, command, command["result_checkpoint_id"])
                state["outbox"]["retry/" + command_id]["delivered"] = True
                return copy.deepcopy(command)
            if command["status"] == "blocked":
                state["outbox"]["retry/" + command_id]["delivered"] = True
                return copy.deepcopy(command)
            value = job["fields"][command["field_key"]]
            if command.get("result_checkpoint_id"):
                self._retry_result(job, command, command["result_checkpoint_id"])
            else:
                self._field_admission(job, [command["field_key"]])
                if state["halted"]:
                    raise BudgetExceeded("Shared program halted")
                if value["revision"] != command["expected_field_revision"] or digest(value["checkpoint"]) != command["checkpoint_digest"] or value.get("retry_command_id") != command_id:
                    raise StaleWork("Retry checkpoint basis changed before claim")
                for effect in state["effects"].values():
                    if effect["job_key"] == scope.key and (not effect["field_keys"] or command["field_key"] in effect["field_keys"]) and (effect["status"] in {"sending", "held_unknown"} or (effect["receipt"] and effect["receipt"]["actual_micro_usd"] is None)):
                        raise HeldUnknown("Retry claim cannot reissue an uncertain effect")
                self._publication_basis(job, scope, command["field_key"])
            if command.get("lease") != asdict(lease):
                command.setdefault("lease_history", []).append(asdict(lease))
                command.update(lease=asdict(lease), claimed_at=now)
            command["status"] = "running"
            if not command.get("result_checkpoint_id"):
                value["work_state"] = "researching"
            return copy.deepcopy(command)
        return self._mutate(scope, reduce, lease=lease, force_cas=True)

    def complete_retry_command(self, scope: DurabilityScope, lease: Lease, command_id: str, *, checkpoint_id: str | None = None, blocked_reason: str | None = None) -> dict[str, Any]:
        """Record an exact command-bound checkpoint or immutable fixed failure reason."""
        if (checkpoint_id is None) == (blocked_reason is None) or (blocked_reason is not None and (not re.fullmatch(r"[a-z0-9_]{1,80}", blocked_reason))):
            raise ValueError("Exactly one committed checkpoint or fixed blocked reason is required")
        def reduce(state, now):
            job = self._lease(state, scope, lease, now)
            command = self._retry_command(state, scope, command_id)
            if command["binding_digest"] != job["binding_digest"] or command.get("lease") != asdict(lease):
                raise StaleWork("Retry completion is outside its active claim")
            if command["status"] in {"completed", "blocked"}:
                if command["status"] == "completed" and checkpoint_id == command.get("result_checkpoint_id"):
                    self._retry_result(job, command, checkpoint_id)
                    state["outbox"]["retry/" + command_id]["delivered"] = True
                    return copy.deepcopy(command)
                if command["status"] == "blocked" and blocked_reason == command.get("blocked_reason"):
                    state["outbox"]["retry/" + command_id]["delivered"] = True
                    return copy.deepcopy(command)
                raise StaleWork("Terminal retry result is immutable")
            if command["status"] != "running":
                raise StaleWork("A running retry claim is required")
            if checkpoint_id is not None:
                self._retry_result(job, command, checkpoint_id)
                command.update(status="completed", completed_at=now)
            else:
                if command.get("result_checkpoint_id"):
                    raise StaleWork("A committed retry checkpoint cannot be relabeled blocked")
                if any(effect["job_key"] == scope.key and effect["scope"]["generation"] == scope.generation
                    and effect["status"] == "sending" and (not effect["field_keys"] or command["field_key"] in effect["field_keys"])
                    for effect in state["effects"].values()):
                    raise HeldUnknown("An in-flight retry effect cannot be terminally blocked by a competing consumer")
                command.update(status="blocked", blocked_reason=blocked_reason, completed_at=now)
                value = job["fields"][command["field_key"]]
                if value.get("retry_command_id") == command_id:
                    value.update(work_state="operational_failed", retry_command_id=None)
            state["outbox"]["retry/" + command_id]["delivered"] = True
            return copy.deepcopy(command)
        return self._mutate(scope, reduce, lease=lease, force_cas=True)

    @staticmethod
    def _publication_basis(job: dict[str, Any], scope: DurabilityScope, field_key: str) -> dict[str, Any]:
        value = job["fields"][field_key]
        checkpoint = value["checkpoint"]
        original_scope = checkpoint["scope"]
        binding = checkpoint["binding_digest"]
        basis = {"scope": original_scope, "binding_digest": binding, "reused": False, "history_digest": None}
        if original_scope == scope.identity():
            if binding != job["binding_digest"] or value["reuse"] is not None:
                raise StaleWork("Checkpoint runtime binding changed")
            return basis
        link = value["reuse"]
        history = next((h for h in job["history"] if h["scope"] == original_scope and h["fields"].get(field_key, {}).get("checkpoint") == checkpoint), None)
        if not link or not history or {k: v for k, v in original_scope.items() if k != "generation"} != {k: v for k, v in scope.identity().items() if k != "generation"} or original_scope["generation"] >= scope.generation:
            raise StaleWork("Prior-generation checkpoint lacks exact same-job history")
        expected_link = {"reused_from_scope_digest": digest(original_scope), "checkpoint_digest": digest(checkpoint),
                         "into_scope_digest": digest(scope.identity()), "source_binding_digest": binding,
                         "target_binding_digest": job["binding_digest"], "retained_dependencies": checkpoint["dependencies"],
                         "retained_dependency_digests": checkpoint.get("dependency_digests", {})}
        if link != expected_link or history["binding_digest"] != binding or digest(history["pins"]) != binding or any(history["pins"][k] != job["pins"][k] for k in history["pins"] if k != "input_digest"):
            raise StaleWork("Prior-generation checkpoint reuse proof changed")
        return {**basis, "reused": True, "history_digest": digest(history)}

    @staticmethod
    def _publication_receipts(state: dict[str, Any], receipt_ids: list[str], basis: Mapping[str, Any]) -> dict[str, Any]:
        result = {}
        for effect_id in receipt_ids:
            effect = state["effects"].get(effect_id)
            if not effect or effect["scope"] != basis["scope"] or effect["binding_digest"] != basis["binding_digest"]:
                raise PermissionError("Publication receipt is outside the checkpoint's verified scope and binding")
            if not effect["receipt"]:
                raise HeldUnknown("Publication needs committed typed receipts")
            result[effect_id] = {"scope": effect["scope"], "binding_digest": effect["binding_digest"],
                                 "attempt_id": effect["receipt"]["attempt_id"], "capture": effect["receipt"]["capture"]}
        return result

    def prepare_publication(self, scope: DurabilityScope, lease: Lease, field_key: str, *, expected_field_revision: int, expected_record_revision: int, receipt_ids: tuple[str, ...] = (), dependencies: Mapping[str, int] | None = None) -> dict[str, Any]:
        """Return a persisted authorization for the sole canonical CAS writer.

        This is not a value save. The writer must check the supplied generation,
        fence, field/dependency revisions and human locks inside its own CAS.
        """
        def reduce(state, now):
            job = self._lease(state, scope, lease, now)
            value = job["fields"].get(field_key)
            if not value or value["locked"] or value["revision"] != expected_field_revision or job["record_revision"] != expected_record_revision or not value["checkpoint"]:
                raise StaleWork("Canonical publication revision or human lock changed")
            checkpoint = value["checkpoint"]
            consumed_receipts = list(receipt_ids) if receipt_ids else checkpoint["receipt_ids"]
            consumed_dependencies = dict(dependencies) if dependencies is not None else checkpoint["dependencies"]
            if consumed_receipts != checkpoint["receipt_ids"] or consumed_dependencies != checkpoint["dependencies"]:
                raise StaleWork("Publication must retain the checkpoint's exact receipt and dependency basis")
            consumed_dependency_digests = checkpoint.get("dependency_digests", {})
            self._dependencies(job, consumed_dependencies, consumed_dependency_digests)
            basis = self._publication_basis(job, scope, field_key)
            receipt_bindings = self._publication_receipts(state, consumed_receipts, basis)
            # binding_digest is digest(job["pins"]), so the guard binds the pins
            # without a full copy in every outbox entry of the state document.
            guard = {"scope": scope.identity(), "lease": asdict(lease), "binding_digest": job["binding_digest"],
                     "input_digest": job["pins"]["input_digest"], "field_key": field_key,
                     "field_revision": expected_field_revision, "record_revision": expected_record_revision,
                     "checkpoint_id": value["checkpoint"]["id"], "checkpoint_digest": digest(value["checkpoint"]),
                     "receipt_ids": consumed_receipts, "dependencies": consumed_dependencies,
                     "dependency_digests": consumed_dependency_digests, "checkpoint_basis": basis,
                     "receipt_bindings": receipt_bindings, "canonical_commit": None}
            guard["idempotency_key"] = digest(guard)
            if any(item.get("kind") == "canonical_publication_required" and item.get("delivered") is True
                and item.get("guard", {}).get("checkpoint_id") == checkpoint["id"]
                for item in state["outbox"].values()):
                raise StaleWork("A delivered publication cannot be reopened")
            state["outbox"]["publish/" + guard["idempotency_key"]] = {"kind": "canonical_publication_required", "guard": guard, "delivered": False}
            return copy.deepcopy(guard)
        return self._mutate(scope, reduce, lease=lease)

    def validate_publication(self, scope: DurabilityScope, guard: Mapping[str, Any]) -> None:
        doc = self._read(scope)
        lease = Lease(**guard["lease"])
        job = self._lease(doc.state, scope, lease, doc.server_time)
        value = job["fields"].get(guard["field_key"])
        if guard["scope"] != scope.identity() or guard["binding_digest"] != job["binding_digest"] or guard["input_digest"] != job["pins"]["input_digest"] or guard["record_revision"] != job["record_revision"] or not value or value["locked"] or value["revision"] != guard["field_revision"] or not value["checkpoint"] or value["checkpoint"]["id"] != guard["checkpoint_id"] or digest(value["checkpoint"]) != guard["checkpoint_digest"]:
            raise StaleWork("Publication authorization superseded")
        if guard["receipt_ids"] != value["checkpoint"]["receipt_ids"] or guard["dependencies"] != value["checkpoint"]["dependencies"]:
            raise StaleWork("Publication receipt or dependency basis changed")
        if guard["dependency_digests"] != value["checkpoint"].get("dependency_digests", {}):
            raise StaleWork("Publication dependency digest basis changed")
        self._dependencies(job, guard["dependencies"], guard["dependency_digests"])
        basis = self._publication_basis(job, scope, guard["field_key"])
        if basis != guard["checkpoint_basis"] or self._publication_receipts(doc.state, guard["receipt_ids"], basis) != guard["receipt_bindings"]:
            raise StaleWork("Publication immutable receipt history changed")


class ImmutableBlobs(Protocol):
    def put_at(self, locator: str, data: bytes) -> BlobRef: ...
    def discover(self, locator: str) -> BlobRef | None: ...
    def get(self, reference: BlobRef) -> bytes: ...


class ImmutableFileBlobs:
    """Local create-only blob emulator with persistent generation and checksum."""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, locator: str) -> Path:
        if not locator or len(locator) > 2048:
            raise ValueError("Invalid immutable locator")
        return self.directory / hashlib.sha256(locator.encode()).hexdigest()

    def put_at(self, locator: str, data: bytes) -> BlobRef:
        path = self._path(locator)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError("Immutable capture mismatch")
        else:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        return BlobRef(locator, "1", hashlib.sha256(data).hexdigest(), len(data))

    def discover(self, locator: str) -> BlobRef | None:
        path = self._path(locator)
        if not path.exists():
            return None
        data = path.read_bytes()
        return BlobRef(locator, "1", hashlib.sha256(data).hexdigest(), len(data))

    def get(self, reference: BlobRef) -> bytes:
        if (reference.generation != "1" or type(reference.byte_size) is not int
            or not 0 <= reference.byte_size <= 8_000_000
            or not re.fullmatch(r"[a-f0-9]{64}", reference.sha256)):
            raise ValueError("Invalid bounded immutable reference")
        import stat
        fd = os.open(self._path(reference.locator), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != reference.byte_size:
                raise ValueError("Immutable object type/size mismatch")
            data = stream.read(reference.byte_size + 1)
        if len(data) != reference.byte_size or hashlib.sha256(data).hexdigest() != reference.sha256:
            raise ValueError("Immutable object checksum/size mismatch")
        return data


class GcsImmutableBlobs:
    """Generation-pinned GCS I/O; constructing this adapter grants no authority."""

    def __init__(self, bucket: Any, *, maximum_bytes: int = 8_000_000):
        self.bucket, self.maximum_bytes = bucket, maximum_bytes

    def _blob(self, locator: str, generation: str | None = None):
        if not locator.startswith(("research-capture/", "research-journal/", "research-media/")) or ".." in locator.split("/"):
            raise ValueError("Unapproved research object namespace")
        return self.bucket.blob(locator, generation=int(generation) if generation else None)

    def put_at(self, locator: str, data: bytes) -> BlobRef:
        if len(data) > self.maximum_bytes:
            raise ValueError("Research blob exceeds configured limit")
        from google.api_core.exceptions import PreconditionFailed
        blob = self._blob(locator)
        blob.metadata = {"sha256": hashlib.sha256(data).hexdigest()}
        try:
            blob.upload_from_string(data, if_generation_match=0, checksum="crc32c", timeout=30)
        except PreconditionFailed:
            reference = self.discover(locator)
            if reference is None or self.get(reference) != data:
                raise ValueError("Immutable GCS capture mismatch")
            return reference
        blob.reload(timeout=30)
        return BlobRef(locator, str(blob.generation), hashlib.sha256(data).hexdigest(), len(data))

    def discover(self, locator: str) -> BlobRef | None:
        from google.api_core.exceptions import NotFound
        blob = self._blob(locator)
        try:
            blob.reload(timeout=30)
        except NotFound:
            return None
        if blob.size is None or blob.size > self.maximum_bytes:
            raise ValueError("GCS evidence size is unavailable or exceeds limit")
        checksum = (blob.metadata or {}).get("sha256")
        if not checksum or len(checksum) != 64:
            raise ValueError("GCS evidence requires a declared SHA256")
        return BlobRef(locator, str(blob.generation), checksum, blob.size)

    def get(self, reference: BlobRef) -> bytes:
        if (type(reference.byte_size) is not int or not 0 <= reference.byte_size <= self.maximum_bytes
            or not isinstance(reference.generation, str)
            or not re.fullmatch(r"[1-9][0-9]*", reference.generation)
            or not re.fullmatch(r"[a-f0-9]{64}", reference.sha256)):
            raise ValueError("Invalid bounded GCS reference")
        blob = self._blob(reference.locator, reference.generation)
        # Native metadata is read at the exact generation before allocating any
        # object body. Caller byte_size cannot authorize a larger remote read.
        blob.reload(timeout=30)
        if (str(blob.generation) != reference.generation or type(blob.size) is not int
            or blob.size != reference.byte_size
            or (blob.metadata or {}).get("sha256") != reference.sha256):
            raise ValueError("GCS immutable metadata mismatch")
        import io
        class BoundedSink(io.BytesIO):
            def write(self, data):
                if self.tell() + len(data) > reference.byte_size:
                    raise ValueError("GCS immutable body exceeds declared limit")
                return super().write(data)
        with BoundedSink() as sink:
            if reference.byte_size:
                blob.download_to_file(sink, start=0, end=reference.byte_size - 1,
                    raw_download=True, if_generation_match=int(reference.generation),
                    checksum="crc32c", timeout=30)
            data = sink.getvalue()
        if len(data) != reference.byte_size or hashlib.sha256(data).hexdigest() != reference.sha256:
            raise ValueError("GCS immutable generation/checksum mismatch")
        return data


class DurableEffectBroker:
    def __init__(self, store: ResearchStore, blobs: ImmutableBlobs):
        self.store, self.blobs = store, blobs

    async def before_send(self, scope: DurabilityScope, intent: dict) -> None:
        """An optional shared program reservation, before a send is marked."""

    def send_authorization(self, execution_class):
        return None

    @staticmethod
    def envelope(scope: DurabilityScope, intent: dict[str, Any], attempt: dict[str, Any], result: CapturedResult, *, raw_capture: BlobRef | None = None) -> bytes:
        payload = asdict(result)
        if isinstance(result.raw_payload, bytes):
            if raw_capture is None:
                raise ValueError("Raw bytes require an immutable raw capture reference")
            payload["raw_payload"] = None
        return canonical({"contract_version": CONTRACT_VERSION, "scope": scope.identity(),
                          "effect_id": intent["effect_id"], "attempt_id": attempt["attempt_id"],
                          "request_digest": intent["request_digest"], "binding_digest": intent["binding_digest"],
                          "raw_capture": asdict(raw_capture) if raw_capture else None, "result": payload})

    def _finish_capture(self, scope: DurabilityScope, intent: dict[str, Any], attempt: dict[str, Any], reference: BlobRef) -> EffectReceipt:
        envelope = json.loads(self.blobs.get(reference))
        expected = {"contract_version": CONTRACT_VERSION, "scope": scope.identity(),
                    "effect_id": intent["effect_id"], "attempt_id": attempt["attempt_id"],
                    "request_digest": intent["request_digest"], "binding_digest": intent["binding_digest"]}
        if any(envelope.get(k) != v for k, v in expected.items()):
            raise PermissionError("Captured effect scope/request/runtime mismatch")
        raw_capture = BlobRef(**envelope["raw_capture"]) if envelope.get("raw_capture") else None
        result = dict(envelope["result"])
        if raw_capture:
            if raw_capture.locator != attempt["raw_capture_locator"]:
                raise PermissionError("Captured raw bytes belong to another attempt")
            result["raw_payload"] = self.blobs.get(raw_capture)
        return self.store.finalize_effect(scope, intent["effect_id"], attempt["attempt_id"], reference, CapturedResult(**result), raw_capture=raw_capture)

    async def execute(self, scope: DurabilityScope, lease: Lease, operation_key: str, request: Any,
                      reservation_micro_usd: int, dispatch: Callable[[str, str], Awaitable[CapturedResult]],
                      *, execution_class: str = "offline", field_keys: tuple[str, ...] = ()) -> EffectReceipt:
        permit = _locked_source_read.get()
        if permit is not None and (permit.closed.is_set() or permit.broker is not self or permit.scope != scope
            or permit.operation_key != operation_key or permit.request_digest != digest(request)
            or tuple(field_keys) != (permit.field_key,)):
            raise PermissionError("Trusted locked read cannot authorize a different effect")
        intent = await asyncio.to_thread(self.store.reserve_effect, scope, lease, operation_key, request, reservation_micro_usd, execution_class=execution_class, field_keys=field_keys)
        if intent["receipt"]:
            receipt = intent["receipt"]
            reference = BlobRef(**receipt["capture"])
            return await asyncio.to_thread(self._finish_capture, scope, intent, intent["attempts"][-1], reference)
        if intent["status"] != "reserved":
            attempt = intent["attempts"][-1]
            reference = await asyncio.to_thread(self.blobs.discover, attempt["capture_locator"])
            if reference:
                return await asyncio.to_thread(self._finish_capture, scope, intent, attempt, reference)
            # A duplicate read cannot distinguish an active send from a lost
            # response. Both already retain the reservation and forbid reissue;
            # only the sending attempt may record its interruption below.
            raise HeldUnknown("Unknown sent effect retains its reservation; no automatic retry")
        await self.before_send(scope, intent)
        authorization = self.send_authorization(execution_class)
        attempt = await asyncio.to_thread(self.store.mark_sending, scope, lease, intent["effect_id"],
            **({"send_authorization": authorization} if authorization is not None else {}))
        try:
            await asyncio.to_thread(self.store.validate_dispatch, scope, lease, intent["effect_id"], attempt["attempt_id"])
            result = await dispatch(attempt["attempt_id"], attempt["provider_idempotency_key"])
            if not isinstance(result, CapturedResult):
                raise TypeError("Dispatch must return a typed CapturedResult")
            raw_capture = None
            if isinstance(result.raw_payload, bytes):
                raw_capture = await asyncio.to_thread(self.blobs.put_at, attempt["raw_capture_locator"], result.raw_payload)
            envelope = self.envelope(scope, intent, attempt, result, raw_capture=raw_capture)
            reference = await asyncio.to_thread(self.blobs.put_at, attempt["capture_locator"], envelope)
            return await asyncio.to_thread(self._finish_capture, scope, intent, attempt, reference)
        except BaseException:
            # Preserve the original exception; a failed hold write also leaves
            # durable 'sending', which recovers conservatively as unknown.
            try:
                await asyncio.shield(asyncio.to_thread(self.store.hold_unknown, scope, intent["effect_id"], "dispatch_or_capture_interrupted"))
            except BaseException:
                pass
            raise


class SqlConnectStepStore:
    """The ten-method official journal protocol, bound to one job/agent scope.

    Message snapshots live in immutable blobs. This adapter does not schedule,
    dispatch, refund, or infer whether an external effect happened.
    """

    def __init__(self, store: ResearchStore, scope: DurabilityScope, blobs: ImmutableBlobs, *, agent_name: str):
        self.store, self.scope, self.blobs, self.agent_name = store, scope, blobs, agent_name

    @staticmethod
    def _adapter(kind: str):
        from pydantic import TypeAdapter
        from pydantic_ai_harness.step_persistence import ContinuableSnapshot, RunRecord, StepEvent, ToolEffectRecord
        return TypeAdapter({"run": RunRecord, "event": StepEvent, "snapshot": ContinuableSnapshot, "tool": ToolEffectRecord}[kind])

    def _encode(self, kind: str, value: Any) -> dict[str, Any]:
        return json.loads(self._adapter(kind).dump_json(value))

    def _decode(self, kind: str, value: dict[str, Any]) -> Any:
        return self._adapter(kind).validate_json(canonical(value))

    def _run(self, state: dict[str, Any], run_id: str) -> dict[str, Any]:
        self.store._job(state, self.scope)
        run = state["journal"].get(run_id)
        if not run or run["scope"] != self.scope.identity() or run["agent_name"] != self.agent_name:
            raise PermissionError("Journal run not available in bound job/agent scope")
        return run

    async def register_run(self, record: Any) -> None:
        value = self._encode("run", record)
        if record.agent_name != self.agent_name:
            raise PermissionError("Journal agent identity mismatch")
        def reduce(state, _):
            self.store._job(state, self.scope)
            old = state["journal"].get(record.run_id)
            if old:
                self._run(state, record.run_id)
                if old["record"] != value or not record.registration_id:
                    raise ValueError("Native run ID is already registered")
                return
            if record.parent_run_id is not None:
                parent = state["journal"].get(record.parent_run_id)
                if not parent or parent["scope"] != self.scope.identity():
                    raise PermissionError("Parent journal belongs to another job/generation")
            state["journal"][record.run_id] = {"scope": self.scope.identity(), "agent_name": self.agent_name,
                                               "record": value, "events": [], "snapshots": [], "tools": {}}
        await asyncio.to_thread(self.store._mutate, self.scope, reduce)

    async def get_run(self, *, run_id: str) -> Any:
        state = (await asyncio.to_thread(self.store._read, self.scope)).state
        if run_id not in state["journal"]:
            return None
        return self._decode("run", self._run(state, run_id)["record"])

    async def list_runs(self, *, parent_run_id: str | None = None, conversation_id: str | None = None) -> list[Any]:
        state = (await asyncio.to_thread(self.store._read, self.scope)).state
        self.store._job(state, self.scope)
        records = [entry["record"] for entry in state["journal"].values()
                   if entry["scope"] == self.scope.identity() and entry["agent_name"] == self.agent_name
                   and (parent_run_id is None or entry["record"]["parent_run_id"] == parent_run_id)
                   and (conversation_id is None or entry["record"]["conversation_id"] == conversation_id)]
        return [self._decode("run", value) for value in sorted(records, key=lambda r: r["started_at"])]

    async def append_event(self, event: Any) -> None:
        value = self._encode("event", event)
        def reduce(state, _):
            run = self._run(state, event.run_id)
            if event.idempotency_key:
                old = next((e for e in run["events"] if e["idempotency_key"] == event.idempotency_key), None)
                if old:
                    # Official retries regenerate timestamps. Preserve the first
                    # immutable boundary rather than appending or overwriting it.
                    return
            run["events"].append(value)
        await asyncio.to_thread(self.store._mutate, self.scope, reduce)

    async def list_events(self, *, run_id: str) -> list[Any]:
        state = (await asyncio.to_thread(self.store._read, self.scope)).state
        return [self._decode("event", e) for e in self._run(state, run_id)["events"]]

    async def save_snapshot(self, snapshot: Any) -> None:
        data = self._adapter("snapshot").dump_json(snapshot)
        locator = f"research-journal/{digest(self.scope.identity())}/{hashlib.sha256(data).hexdigest()}"
        reference = await asyncio.to_thread(self.blobs.put_at, locator, data)
        item = {"step_index": snapshot.step_index, "state": snapshot.state, "idempotency_key": snapshot.idempotency_key,
                "timestamp": snapshot.timestamp.isoformat(), "reference": asdict(reference)}
        def reduce(state, _):
            run = self._run(state, snapshot.run_id)
            if snapshot.idempotency_key:
                old = next((s for s in run["snapshots"] if s["idempotency_key"] == snapshot.idempotency_key), None)
                if old:
                    return
                # Harness uses snapshot_index:graph_step:state. Graph steps can
                # lag on error/frontier capture; they are not storage sequence.
                prefix = snapshot.idempotency_key.split(":", 1)[0]
                if ":" in snapshot.idempotency_key and prefix.isdigit():
                    sequence = int(prefix)
                    high_water = run.get("snapshot_key_high_water", -1)
                    if sequence < high_water:
                        return
                    run["snapshot_key_high_water"] = max(sequence, high_water)
            run["snapshots"].append({**item, "sequence": len(run["snapshots"]) + 1})
        await asyncio.to_thread(self.store._mutate, self.scope, reduce)

    async def latest_snapshot(self, *, run_id: str, include_interrupted: bool = False) -> Any:
        state = (await asyncio.to_thread(self.store._read, self.scope)).state
        run = self._run(state, run_id)
        if include_interrupted and any(e["job_key"] == self.scope.key and e["scope"] == self.scope.identity() and e["status"] in {"sending", "held_unknown"} for e in state["effects"].values()):
            raise HeldUnknown("Interrupted messages require application effect reconciliation")
        candidates = [s for s in run["snapshots"] if include_interrupted or s["state"] == "complete"]
        if not candidates:
            return None
        payload = await asyncio.to_thread(self.blobs.get, BlobRef(**candidates[-1]["reference"]))
        return self._adapter("snapshot").validate_json(payload)

    async def record_tool_effect(self, record: Any) -> None:
        value = self._encode("tool", record)
        def reduce(state, _):
            run = self._run(state, record.run_id)
            old = run["tools"].get(record.tool_call_id)
            if old and (old["tool_name"] != record.tool_name or old["idempotency_key"] != record.idempotency_key):
                raise ValueError("Native tool identity changed")
            if old and old["status"] in {"completed", "failed"} and old != value:
                raise ValueError("Terminal native tool journal record changed")
            run["tools"][record.tool_call_id] = value
        await asyncio.to_thread(self.store._mutate, self.scope, reduce)

    async def get_tool_effect(self, *, run_id: str, tool_call_id: str) -> Any:
        state = (await asyncio.to_thread(self.store._read, self.scope)).state
        value = self._run(state, run_id)["tools"].get(tool_call_id)
        return self._decode("tool", value) if value else None

    async def list_unresolved_tool_effects(self, *, run_id: str) -> list[Any]:
        state = (await asyncio.to_thread(self.store._read, self.scope)).state
        return [self._decode("tool", value) for value in self._run(state, run_id)["tools"].values() if value["status"] == "started"]


class GcsMediaStore:
    """Five-method media protocol using scoped SQL manifests and immutable blobs."""

    def __init__(self, store: ResearchStore, scope: DurabilityScope, blobs: ImmutableBlobs):
        self.store, self.scope, self.blobs = store, scope, blobs

    def _manifest(self, state: dict[str, Any], uri: str) -> dict[str, Any]:
        self.store._job(state, self.scope)
        key = digest({"scope": self.scope.identity(), "uri": uri})
        manifest = state["media"].get(key)
        if not manifest or manifest["scope"] != self.scope.identity():
            raise FileNotFoundError("Media is not available in bound scope")
        return manifest

    async def put(self, data: bytes, *, context: Any = None) -> str:
        uri = "media+sha256://" + hashlib.sha256(data).hexdigest()
        reference = await asyncio.to_thread(self.blobs.put_at, f"research-media/{digest(self.scope.identity())}/{hashlib.sha256(data).hexdigest()}", data)
        metadata = dict(context.metadata) if context is not None else {}
        def reduce(state, _):
            self.store._job(state, self.scope)
            key = digest({"scope": self.scope.identity(), "uri": uri})
            item = {"scope": self.scope.identity(), "uri": uri, "reference": asdict(reference), "metadata": metadata}
            if key in state["media"] and state["media"][key] != item:
                raise ValueError("Immutable media metadata changed")
            state["media"][key] = item
        await asyncio.to_thread(self.store._mutate, self.scope, reduce)
        return uri

    async def get(self, uri: str, *, context: Any = None) -> bytes:
        state = (await asyncio.to_thread(self.store._read, self.scope)).state
        manifest = self._manifest(state, uri)
        return await asyncio.to_thread(self.blobs.get, BlobRef(**manifest["reference"]))

    async def exists(self, uri: str, *, context: Any = None) -> bool:
        try:
            await self.get(uri, context=context)
        except FileNotFoundError:
            return False
        return True

    async def public_url(self, uri: str, *, context: Any = None) -> str | None:
        # This protocol does not grant publication of museum evidence.
        await self.get(uri, context=context)
        return None

    async def get_metadata(self, uri: str, *, context: Any = None) -> Mapping[str, str]:
        state = (await asyncio.to_thread(self.store._read, self.scope)).state
        return dict(self._manifest(state, uri)["metadata"])
