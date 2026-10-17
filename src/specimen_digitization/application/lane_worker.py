"""The production worker drains the queue (docs/execution/golive/LANE.md, T2).

One collection at a time, behind a fence: the oldest request first (G13), each
run stepped until it stops, short retries waited for, and no new run in the
last ten minutes before the task deadline. Work left at the end is handed to
the next execution, and so is work an unexpected error leaves behind.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from .domain import AuditEvent, Principal, Scope
from .storage import Conflict, Missing, digest
from .workflow import OperationalBlock

LOGGER = logging.getLogger(__name__)
LANE_ROLES = {"operator", "reviewer", "manager", "admin"}
# A run stops being stepped at any of these; the workflow waits on the rest.
STOPPED = {"finalized", "processing_blocked", "paused", "cancelled", "retry_scheduled"}
# Nothing is left to do for a run in these stages (storage.work_available_at).
FINISHED = {"finalized", "processing_blocked", "paused", "cancelled", "waiting_for_review"}
FENCE_KIND = "worker_cursor"  # The worker's own state documents, one actor only.
CLOSING_SECONDS = 600  # No new run starts this close to the task deadline.
QUEUE_CLOCK_MARGIN_SECONDS = 1  # Keep connector cutoffs behind its own clock.
# The continuation's own start call (lane_dispatch.CloudRunJobDispatcher's
# timeout). The exit handshake waits only when the wait and this call both fit
# before the deadline; otherwise it skips the wait and starts the call at once.
CONTINUATION_START_SECONDS = 10
MAX_CONFLICTS = 3  # Consecutive save conflicts on one run before moving on.
MAX_IDLE_HANDOVERS = 3  # Consecutive hand-overs without progress, then stop.
# Consecutive executions ended by an unexpected error, none saving a step, that
# still start the next one. A fourth such crash in a row starts none.
MAX_CRASH_HANDOVERS = 3
RUN_STALLED = "lane_run_not_progressing"
HANDOVER_STALLED = "lane_handover_without_progress"
# One record's own hold: the native worker's blocked outcome codes
# (native_worker.py) and the run's own refusals (workflow_bridge.RECORD_REFUSALS),
# each raised by the bridge (NativeResearchWorkflow.step). The drain blocks that
# run and moves on. A step's other errors, save conflicts aside, still end the
# execution, so an authorization, program budget, configuration or storage
# failure is not recorded against each record in turn. A run's own research
# allowance is one state document per run, so its exhaustion is that record's.
RECORD_HOLDS = frozenset(
    {
        "accepted_output_proof_unavailable",
        "native_publication_requires_reconciliation",
        "native_research_operational_hold",
        "research_committed_pins_changed",
        "research_live_admission_unqualified",
        "research_program_headroom_unavailable",
        "research_provision_registration_refused",
        "research_provision_run_unavailable",
        "research_provision_state_conflict",
        "research_retry_not_completed",
        "research_worker_custody_requires_reconciliation",
    }
)
EMULATOR_KEYS = (
    "SPECIMEN_SQL_EMULATOR_HOST",
    "DATA_CONNECT_EMULATOR_HOST",
    "FIREBASE_AUTH_EMULATOR_HOST",
    "FIREBASE_STORAGE_EMULATOR_HOST",
    "STORAGE_EMULATOR_HOST",
)


@dataclass(frozen=True)
class DrainSettings:
    actor_uid: str
    bindings: dict = field(default_factory=dict)
    worker_job: str = ""


def exact_uid(value) -> bool:
    """The bootstrap's rule for an explicit Firebase UID (bootstrap_admin.py).

    The drain takes the secret's value as given, never stripped, so a UID with
    surrounding whitespace or a control character would match no membership.
    """
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 128
        and value == value.strip()
        and not any(ord(character) < 32 for character in value)
    )


def drain_settings(env) -> DrainSettings:
    """Fail closed before any work is taken. Errors name settings, never values."""
    from ..hub_models import SAM3_MODEL
    from .lane_dispatch import JOB_NAME
    from .production import Sam3Service
    from .runtime_config import collection_bindings

    actor = env.get("SPECIMEN_WORKER_ACTOR_UID", "")
    if not exact_uid(actor):
        raise ValueError("SPECIMEN_WORKER_ACTOR_UID must be an exact Firebase UID for the drain")
    if env.get("SPECIMEN_APPROVED_INFERENCE") != "true":
        raise ValueError("SPECIMEN_APPROVED_INFERENCE must be true for the drain")
    if any(env.get(key) for key in EMULATOR_KEYS):
        raise ValueError("The production drain rejects emulator configuration")
    if env.get("SPECIMEN_SAM3_LAB") == "true":
        raise ValueError("The production drain rejects SAM 3 lab mode")
    try:
        Sam3Service(env.get("SPECIMEN_SAM3_ENDPOINT", ""), None)
    except ValueError:
        raise ValueError("SPECIMEN_SAM3_ENDPOINT must name the SAM 3 service") from None
    if env.get("SPECIMEN_SAM3_REVISION") != SAM3_MODEL.revision:
        raise ValueError("SPECIMEN_SAM3_REVISION must pin the reviewed SAM 3 revision")
    if not env.get("HF_TOKEN"):
        raise ValueError("HF_TOKEN is required for the readers")
    job = env.get("SPECIMEN_WORKER_JOB", "")
    if job and not JOB_NAME.fullmatch(job):
        raise ValueError("SPECIMEN_WORKER_JOB must be projects/*/locations/*/jobs/*")
    return DrainSettings(actor, dict(collection_bindings(env)), job)


def moment(value):
    return datetime.fromisoformat(value)


def stored_integer(value):
    """Keep a document's numbers exact integers, as the circuit store does: SQL
    Connect's Struct transport may return them as doubles."""
    if type(value) is float and math.isfinite(value) and value.is_integer():
        value = int(value)
    if type(value) is not int or not 0 <= value < 2**53:
        raise Conflict("A stored document number is not an exact integer")
    return value


class FenceLost(RuntimeError):
    """Another execution took the collection over; this one must stop."""


class CollectionFence:
    """One execution drains a collection at a time (G13).

    A compare-and-set document with a renewed lease. Two executions acting as
    the same actor replay each other's snapshot receipts, so a snapshot's own
    compare-and-set cannot keep them apart; this document can. It is marked
    not sensitive, so the worker's membership needs no sensitive access.
    """

    def __init__(self, repository, scope, actor_uid, holder, *, clock, lease_seconds=300):
        self.repository, self.scope = repository, scope
        self.actor_uid, self.holder = actor_uid, holder
        self.clock, self.lease_seconds = clock, lease_seconds
        self.ident = str(
            uuid5(
                NAMESPACE_URL,
                f"processing-lane-fence:{scope.organization_id}/{scope.collection_id}",
            )
        )
        self.revision = None
        self.specimen_id = None  # The run last held, for a crash to hand on.

    def read(self) -> dict:
        try:
            current = self.repository.document(self.scope, FENCE_KIND, self.ident)
        except Missing:
            return {"revision": 0, "holder": None}
        return dict(
            current,
            revision=stored_integer(current["revision"]),
            handovers_without_progress=stored_integer(
                current.get("handovers_without_progress", 0)
            ),
            crashes_without_progress=stored_integer(
                current.get("crashes_without_progress", 0)
            ),
        )

    def _write(
        self, revision, holder, specimen_id=None, run_id=None, retry_at=None, idle=0,
        crashes=0,
    ):
        lease = self.clock() + timedelta(seconds=self.lease_seconds)
        stored = self.repository.put_document(
            self.scope,
            FENCE_KIND,
            self.ident,
            {
                "sensitive": False,
                "actor_uid": self.actor_uid,
                "holder": holder,
                "specimen_id": specimen_id,
                "run_id": run_id,
                "lease_until": lease.isoformat(),
                # A retry this holder left for the next one to wait for.
                "retry_at": retry_at,
                "handovers_without_progress": idle,
                # Consecutive executions an unexpected error ended without progress.
                "crashes_without_progress": crashes,
            },
            revision,
        )
        self.revision = stored["revision"]

    def acquire(self) -> dict | None:
        """The previous record when the fence is taken; None while another holds it."""
        current = self.read()
        live = (
            current.get("holder") not in (None, self.holder)
            and moment(current["lease_until"]) > self.clock()
        )
        if live:
            return None
        try:
            self._write(current["revision"], self.holder)
        except Conflict:
            return None  # Another execution took it first.
        return current

    def hold(self, specimen_id, run_id=None):
        """Record the run being worked on and renew the lease."""
        self.specimen_id = specimen_id
        try:
            self._write(self.revision, self.holder, specimen_id, run_id)
        except Conflict as exc:
            raise FenceLost("collection fence taken over") from exc

    def release(self, retry=None, idle=0, crashes=0):
        """Free the fence, leaving `(specimen_id, retry_at)` for the next holder
        and the counts of consecutive hand-overs and crashes without progress."""
        specimen_id, retry_at = retry or (None, None)
        try:
            self._write(
                self.revision, None, specimen_id, retry_at=retry_at, idle=idle, crashes=crashes
            )
        except Conflict:
            pass  # Taken over after expiry; the new holder owns it now.


def blocked_ids(repository, scope):
    """Blocked, non-sensitive records with no disposition, by id, in pages.

    The production repository lists them from its metadata rows
    (SqlConnectRepository.blocked_ids). The local SQLite repository is read
    here, so storage.py, whose source digest the research harness pins
    (native_canonical), stays as it is. Any other repository lists none.
    """
    listing = getattr(repository, "blocked_ids", None)
    if callable(listing):
        yield from listing(scope)
        return
    from .lane import SQLITE_STATUS
    from .storage import SQLiteRepository

    if not isinstance(repository, SQLiteRepository):
        return
    with repository.connect() as db:
        rows = db.execute(
            "SELECT id FROM records WHERE org=? AND collection=? AND "
            "COALESCE(json_extract(payload,'$.asset.sensitive'),1)=0 AND "
            + SQLITE_STATUS
            + "='processing_blocked' ORDER BY id",
            (scope.organization_id, scope.collection_id),
        ).fetchall()
    yield [row[0] for row in rows]


def waiting_until(run):
    """When a run the workflow waits on becomes due again; None when it is due now."""
    if run.blocker == "external_outcome_unknown" and run.lease_until:
        return run.lease_until
    if run.stage == "retry_scheduled" and run.next_retry_at:
        return run.next_retry_at
    return None


@dataclass
class CollectionDrain:
    """One collection's drain within an execution."""

    principal: Principal
    progress: bool = False  # Some step saved a new revision.
    stalled: set = field(default_factory=set)  # Due runs whose step changed nothing.
    retries: dict = field(default_factory=dict)  # Specimen id to due time.


class DrainWorker:
    """Drains the actor's collections, one specimen at a time (LANE.md T2)."""

    def __init__(
        self,
        repository,
        workflow,
        user_id,
        membership_loader,
        *,
        execution_id,
        clock=None,
        sleep=None,
        continuation=None,
        deadline_seconds=3600,
        lease_seconds=None,
        max_steps_per_run=500,
    ):
        self.repository, self.workflow = repository, workflow
        self.user_id, self.membership_loader = user_id, membership_loader
        self.execution_id = execution_id
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleep = sleep
        # Starts the next execution of the job, with no overrides.
        self.continuation = continuation
        self.deadline_seconds = deadline_seconds
        self.window_seconds = deadline_seconds - CLOSING_SECONDS
        # A native research step spans multiple bounded role windows. The
        # collection fence must outlive the whole task, not only one window,
        # so a second execution cannot start another record while it runs.
        self.lease_seconds = deadline_seconds + 60 if lease_seconds is None else lease_seconds
        self.max_steps_per_run = max_steps_per_run

    @staticmethod
    def _stopped(stop):
        return stop is not None and stop.is_set()

    def _pause(self, seconds, stop):
        if self.sleep is not None:
            self.sleep(seconds)
        elif stop is not None:
            stop.wait(seconds)  # A stop signal ends the wait early.
        else:
            time.sleep(seconds)

    def run(self, stop=None) -> dict:
        started = self.clock()
        self.close_at = started + timedelta(seconds=self.window_seconds)
        self.deadline_at = started + timedelta(seconds=self.deadline_seconds)
        summary = {
            "status": "drained",
            "processed": [],
            "skipped_collections": [],
            "withheld_collections": [],
            "pending_retries": 0,
            "recovered": 0,
            "continuation": None,
        }
        wanted = False
        for member in self.membership_loader(self.user_id):
            if member["role"] not in LANE_ROLES:
                continue
            if summary["status"] == "stopped" or self._stopped(stop):
                summary["status"] = "stopped"
                # Collections not reached may hold requests whose own worker
                # found this execution's fence held and exited.
                wanted = True
                break
            scope = Scope(
                organization_id=member["organization_id"],
                collection_id=member["collection_id"],
            )
            principal = Principal(user_id=self.user_id, scope=scope, role=member["role"])
            if summary["status"] == "window_closed":
                # Past the window: only note whether requested work is waiting.
                wanted = wanted or self._next_due(principal) is not None
                continue
            fence = CollectionFence(
                self.repository,
                scope,
                self.user_id,
                self.execution_id,
                clock=self.clock,
                lease_seconds=self.lease_seconds,
            )
            previous = fence.acquire()
            if previous is None:
                summary["skipped_collections"].append(scope.collection_id)
                continue
            drain = CollectionDrain(principal)
            try:
                status = self._drain(drain, fence, previous, stop, summary)
            except FenceLost:
                # Another execution took over after this one stalled past its lease.
                summary["skipped_collections"].append(scope.collection_id)
                continue
            except Exception as exc:
                # The error still ends this execution, so the job records it.
                self._crashed(drain, fence, previous, exc)
                raise
            except BaseException:
                fence.release()
                raise
            wanted = self._release(drain, fence, previous, status, summary, stop) or wanted
            if self._stopped(stop):
                status = "stopped"
            if status != "drained":
                summary["status"] = status
        if self.continuation and wanted:
            summary["continuation"] = self.continuation().status
        return summary

    def _release(self, drain, fence, previous, status, summary, stop=None) -> bool:
        """Release the fence; whether the collection wants the next execution.

        It does when requested work remains after release, or a retry falls
        within the next execution's reach. A stop (SIGTERM: the task's timeout,
        a scale-down or a cancel) always wants one: it cannot finish the read
        below, and a request committed just before release may have lost its
        own worker to this fence. The next execution finds nothing and exits
        when nothing is due; a run paused or cancelled by its own action is
        never due. After
        MAX_IDLE_HANDOVERS in a row without progress, the waiting run is blocked
        where people can see it instead. The final read follows release and the
        cutoff margin, so a request cannot lose its wake-up to the old fence.
        """
        first = min(drain.retries.items(), key=lambda item: item[1], default=None)
        reach = self.clock() + timedelta(seconds=self.window_seconds)
        waiting = None
        if status == "window_closed":
            waiting = self._next_due(drain.principal, drain.stalled)
        if waiting is None and status != "stopped" and first and first[1] <= reach:
            waiting = first[0]
        idle = 0
        if waiting is not None and not drain.progress:
            idle = previous.get("handovers_without_progress", 0) + 1
            if idle >= MAX_IDLE_HANDOVERS:
                self._block(drain.principal, waiting, HANDOVER_STALLED)
                summary["withheld_collections"].append(drain.principal.scope.collection_id)
                waiting, idle = None, 0
        fence.release(first and (first[0], first[1].isoformat()), idle)
        summary["pending_retries"] += len(drain.retries)
        if status == "stopped" or self._stopped(stop):
            return True
        # Close the enqueue/exit race *after* freeing the fence. A request may
        # have committed after our last empty read, while its newly dispatched
        # worker found this fence held and exited. Waiting one cutoff margin
        # makes every request committed before release visible to this read.
        # Later arrivals can acquire the released fence through their normal
        # dispatch. This is one bounded check, never an idle polling loop.
        remaining = (self.deadline_at - self.clock()).total_seconds()
        if remaining < QUEUE_CLOCK_MARGIN_SECONDS + CONTINUATION_START_SECONDS:
            # A long final step used the task's grace window. Skip the wait and
            # hand off once with whatever time is left. If the step already ran
            # past the deadline the start is late and best effort: the platform
            # may stop it, but skipping it would strand the request for certain.
            # The next worker owns acquisition, deduplication and admission.
            return True
        self._pause(QUEUE_CLOCK_MARGIN_SECONDS, stop)
        if self._stopped(stop):
            return True
        return (
            waiting is not None
            or self._next_due(drain.principal, drain.stalled) is not None
        )

    def _crashed(self, drain, fence, previous, error) -> None:
        """Release the fence after an unexpected error and start the next execution.

        Nothing else starts one: the scheduled services are off, so due work
        would wait for a person's action (2026-10-17, execution
        specimen-worker-4fk49). The run in flight is left as a retry at its
        lease's end, or now, as a finished execution leaves one, so the next
        execution waits for it in request order. The next execution starts when
        that retry is within its reach or requested work is due; a failed read
        counts as work. After MAX_CRASH_HANDOVERS crashes in a row with no step
        saved, none starts. Each step here is best effort and never replaces
        the original error.
        """
        name = type(error).__name__
        crashes = 1 if drain.progress else previous.get("crashes_without_progress", 0) + 1
        idle = 0 if drain.progress else previous.get("handovers_without_progress", 0)
        retries = dict(drain.retries)
        try:
            if fence.specimen_id is not None:
                run = self.repository.get(drain.principal.scope, fence.specimen_id).run
                if not run.disposition and run.stage not in FINISHED:
                    until = waiting_until(run)
                    retries[fence.specimen_id] = moment(until) if until else self.clock()
        except Exception as exc:  # noqa: BLE001 - the release below still runs
            LOGGER.warning("drain crash: run in flight not read: %s", type(exc).__name__)
        first = min(retries.items(), key=lambda item: item[1], default=None)
        try:
            fence.release(first and (first[0], first[1].isoformat()), idle, crashes)
        except Exception as exc:  # noqa: BLE001 - still held, so no execution could take it
            LOGGER.warning("drain crash (%s): fence not released: %s", name, type(exc).__name__)
            return
        if crashes > MAX_CRASH_HANDOVERS:
            LOGGER.warning(
                "drain crash (%s): %d in a row without progress; no next execution", name, crashes
            )
            return
        wanted = first is not None and first[1] <= self.clock() + timedelta(
            seconds=self.window_seconds
        )
        if not wanted:
            try:
                self._pause(QUEUE_CLOCK_MARGIN_SECONDS, None)
                wanted = self._next_due(drain.principal, drain.stalled) is not None
            except Exception:  # noqa: BLE001 - the next execution reads again
                wanted = True
        if not wanted or not self.continuation:
            return
        try:
            status = self.continuation().status
        except Exception as exc:  # noqa: BLE001 - the original error still ends the execution
            status = "failed:" + type(exc).__name__
        LOGGER.warning("drain crash (%s): next execution %s", name, status)

    def _next_due(self, principal, skip=()):
        # A cutoff a second behind keeps it no later than the database's clock.
        cutoff = (self.clock() - timedelta(seconds=QUEUE_CLOCK_MARGIN_SECONDS)).isoformat()
        due = self.repository.oldest_due(
            principal.scope, cutoff, limit=min(100, len(skip) + 1)
        )
        return next((item.specimen_id for item in due if item.specimen_id not in skip), None)

    def _resume(self, drain, previous):
        """The run a dead execution left under the fence, when it is due now.

        A run still waiting (its step's lease can outlive the fence's) is waited
        for like a retry; so is a retry a finished execution handed over.
        """
        ident = previous.get("specimen_id")
        if ident is None:
            return None
        if not previous.get("holder"):
            if previous.get("retry_at"):
                drain.retries[ident] = moment(previous["retry_at"])
            return None
        try:
            run = self.repository.get(drain.principal.scope, ident).run
        except Missing:
            return None
        if run.disposition or run.stage in FINISHED:
            return None
        until = waiting_until(run)
        if until and moment(until) > self.clock():
            drain.retries[ident] = moment(until)
            return None
        return ident

    def _recover_blocked(self, drain, stop=None):
        """Make the collection's recoverable blocked runs due (Workflow.recover_blocked).

        Once per collection per execution, under its fence, before any run is
        stepped: a run blocked at an ordinary first pass by a transient cause
        goes on with the normal drain, with no action and no scheduled service.
        Each recovered run is waited for as a retry is, since the queue's cutoff
        stays a margin behind the clock. It reads the records' listing and makes
        no call. A failure here is logged by class and never stops the drain.
        The listing is read lazily and the scan ends at a stop or at the
        window's close, so a long collection never eats the time the drain
        needs to release its fence and hand the rest on; the next execution
        scans again.
        """
        principal = drain.principal
        recover = getattr(self.workflow, "recover_blocked", None)
        if not callable(recover):
            return 0
        recovered = 0
        try:
            for page in blocked_ids(self.repository, principal.scope):
                for ident in page:
                    if self._stopped(stop) or self.clock() >= self.close_at:
                        return recovered
                    try:
                        if recover(principal, ident):
                            recovered += 1
                            drain.retries[ident] = self.clock()
                    except (Conflict, Missing):
                        continue  # Changed meanwhile; the next execution looks again.
                if self._stopped(stop) or self.clock() >= self.close_at:
                    break  # Checked after every page, an empty one too.
        except Exception as exc:  # noqa: BLE001 - recovery never stops the drain
            LOGGER.warning("blocked-run recovery skipped: %s", type(exc).__name__)
        return recovered

    def _drain(self, drain, fence, previous, stop, summary):
        principal = drain.principal
        summary["recovered"] += self._recover_blocked(drain, stop)
        resume = self._resume(drain, previous)
        while True:
            if self._stopped(stop):
                return "stopped"
            if self.clock() >= self.close_at:
                return "window_closed"
            ident, resume = resume or self._next_due(principal, drain.stalled), None
            if ident is None:
                waitable = [at for at in drain.retries.values() if at <= self.close_at]
                if not waitable:
                    return "drained"
                # Nothing else would start the job for these retries.
                seconds = (min(waitable) - self.clock()).total_seconds() + 2
                self._pause(max(1.0, seconds), stop)
                for key in [k for k, at in drain.retries.items() if at <= self.clock()]:
                    del drain.retries[key]  # Due now, so the queue returns it.
                continue
            run, progressed = self._step_until_stopped(principal, fence, ident, stop)
            if ident not in summary["processed"]:
                summary["processed"].append(ident)
            if progressed:
                drain.progress = True
            else:
                # A due run whose step changes nothing would be taken again and
                # again; block it where people can see it and move on.
                drain.stalled.add(ident)
                self._block(principal, ident, RUN_STALLED)
            if run.stage == "retry_scheduled" and run.next_retry_at:
                drain.retries[ident] = moment(run.next_retry_at)
            else:
                drain.retries.pop(ident, None)

    def _step_until_stopped(self, principal, fence, ident, stop):
        """Step one run until it stops; the run and whether any step saved."""
        fence.hold(ident)
        progressed, conflicts = False, 0
        before = self.repository.get(principal.scope, ident)
        run = before.run
        for _ in range(self.max_steps_per_run):
            try:
                specimen = self.workflow.step(principal, ident)
            except Conflict:
                # Changed meanwhile, by a reviewer's edit for one: read it again.
                conflicts += 1
                if conflicts >= MAX_CONFLICTS:
                    return run, progressed
                before = self.repository.get(principal.scope, ident)
                run = before.run
                continue
            except OperationalBlock as exc:
                if str(exc) not in RECORD_HOLDS:
                    raise
                # Blocked where people can see it, so it is no longer due. The
                # code is logged with a short record suffix and nothing else.
                LOGGER.warning("record held by the drain: %s (record ...%s)", str(exc), str(ident)[-6:])
                self._block(principal, ident, str(exc), hold=True)
                return self.repository.get(principal.scope, ident).run, progressed
            conflicts = 0
            fence.hold(ident, specimen.run.id)
            run = specimen.run
            if specimen.version == before.version:
                completed = getattr(self.workflow, "completed_side_work", None)
                if callable(completed) and completed(specimen) is True:
                    return run, True  # Verified native queue retirement, no scientific save.
                return run, progressed  # Leased or otherwise waiting.
            progressed = True
            if run.disposition or run.stage in STOPPED or self._stopped(stop):
                return run, progressed
            before = specimen
        return run, progressed

    def _block(self, principal, ident, reason, *, hold=False):
        """A visible operational block; the run's resume action requests it again.

        A record's own hold (``hold``) is also recorded on a run that is already
        processing_blocked, as its blocker when it names none: a publication's
        save blocks the record first, so its later refusal would leave no trace.
        The stage stays, and a blocker already there (an unknown external
        outcome, or an earlier hold) is kept."""
        try:
            specimen = self.repository.get(principal.scope, ident)
            run = specimen.run
            if run.disposition:
                return
            if run.stage == "processing_blocked":
                if not hold or run.blocker:
                    return
                run.blocker = reason
            elif run.stage in FINISHED:
                return
            else:
                run.stage, run.blocker, run.next_retry_at = "processing_blocked", reason, None
            specimen.audit.append(
                AuditEvent(actor=principal.user_id, action="lane_block", reason=reason)
            )
            self.repository.save(
                principal,
                specimen,
                specimen.version,
                f"lane-block:{specimen.version}",
                digest({"lane_block": reason, "run": run.id}),
            )
        except (Conflict, Missing):
            pass  # Changed meanwhile; the next execution looks again.
