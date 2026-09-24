"""The production worker drains the queue (docs/execution/golive/LANE.md, T2).

One collection at a time, behind a fence: the oldest request first (G13), each
run stepped until it stops, short retries waited for, and no new run in the
last ten minutes before the task deadline.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from .domain import AuditEvent, Principal, Scope
from .storage import Conflict, Missing, digest

LANE_ROLES = {"operator", "reviewer", "manager", "admin"}
# A run stops being stepped at any of these; the workflow waits on the rest.
STOPPED = {"finalized", "processing_blocked", "paused", "cancelled", "retry_scheduled"}
# Nothing is left to do for a run in these stages (storage.work_available_at).
FINISHED = {"finalized", "processing_blocked", "paused", "cancelled", "waiting_for_review"}
FENCE_KIND = "worker_cursor"  # The worker's own state documents, one actor only.
CLOSING_SECONDS = 600  # No new run starts this close to the task deadline.
MAX_CONFLICTS = 3  # Consecutive save conflicts on one run before moving on.
RUN_STALLED = "lane_run_not_progressing"
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


def drain_settings(env) -> DrainSettings:
    """Fail closed before any work is taken. Errors name settings, never values."""
    from ..hub_models import SAM3_MODEL
    from .lane_dispatch import JOB_NAME
    from .production import Sam3Service
    from .runtime_config import collection_bindings

    actor = env.get("SPECIMEN_WORKER_ACTOR_UID", "")
    if not 1 <= len(actor) <= 128:
        raise ValueError("SPECIMEN_WORKER_ACTOR_UID is required for the drain")
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

    def read(self) -> dict:
        try:
            current = self.repository.document(self.scope, FENCE_KIND, self.ident)
        except Missing:
            return {"revision": 0, "holder": None}
        return dict(current, revision=stored_integer(current["revision"]))

    def _write(self, revision, holder, specimen_id=None, run_id=None):
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
        try:
            self._write(self.revision, self.holder, specimen_id, run_id)
        except Conflict as exc:
            raise FenceLost("collection fence taken over") from exc

    def release(self):
        """Free the fence for the next holder."""
        try:
            self._write(self.revision, None)
        except Conflict:
            pass  # Taken over after expiry; the new holder owns it now.


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
        deadline_seconds=3600,
        lease_seconds=300,
        max_steps_per_run=500,
    ):
        self.repository, self.workflow = repository, workflow
        self.user_id, self.membership_loader = user_id, membership_loader
        self.execution_id = execution_id
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleep = sleep
        self.window_seconds = deadline_seconds - CLOSING_SECONDS
        self.lease_seconds = lease_seconds
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
        self.close_at = self.clock() + timedelta(seconds=self.window_seconds)
        summary = {
            "status": "drained",
            "processed": [],
            "skipped_collections": [],
            "pending_retries": 0,
        }
        for member in self.membership_loader(self.user_id):
            if member["role"] not in LANE_ROLES:
                continue
            if self._stopped(stop):
                summary["status"] = "stopped"
                break
            scope = Scope(
                organization_id=member["organization_id"],
                collection_id=member["collection_id"],
            )
            principal = Principal(user_id=self.user_id, scope=scope, role=member["role"])
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
            finally:
                fence.release()
            summary["pending_retries"] += len(drain.retries)
            if status != "drained":
                summary["status"] = status
                break
        return summary

    def _next_due(self, principal, skip=()):
        # A cutoff a second behind keeps it no later than the database's clock.
        cutoff = (self.clock() - timedelta(seconds=1)).isoformat()
        due = self.repository.oldest_due(
            principal.scope, cutoff, limit=min(100, len(skip) + 1)
        )
        return next((item.specimen_id for item in due if item.specimen_id not in skip), None)

    def _resume(self, drain, previous):
        """The run a dead execution left under the fence, when it is due now.

        A run still waiting (its step's lease can outlive the fence's) is waited
        for like a retry.
        """
        ident = previous.get("specimen_id")
        if ident is None or not previous.get("holder"):
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

    def _drain(self, drain, fence, previous, stop, summary):
        principal = drain.principal
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
            conflicts = 0
            fence.hold(ident, specimen.run.id)
            run = specimen.run
            if specimen.version == before.version:
                return run, progressed  # Leased or otherwise waiting.
            progressed = True
            if run.disposition or run.stage in STOPPED or self._stopped(stop):
                return run, progressed
            before = specimen
        return run, progressed

    def _block(self, principal, ident, reason):
        """A visible operational block; the run's resume action requests it again."""
        try:
            specimen = self.repository.get(principal.scope, ident)
            run = specimen.run
            if run.disposition or run.stage in FINISHED:
                return
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
