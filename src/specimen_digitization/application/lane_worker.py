"""The production worker drains the queue (docs/execution/golive/LANE.md, T2).

One collection at a time, behind a fence: the oldest request first (G13), each
run stepped until it stops, short retries waited for, and no new run in the
last ten minutes before the task deadline. Work left at the end is handed to
the next execution.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from .domain import Principal, Scope
from .storage import Conflict, Missing

LANE_ROLES = {"operator", "reviewer", "manager", "admin"}
# A run stops being stepped at any of these; the workflow waits on the rest.
STOPPED = {"finalized", "processing_blocked", "paused", "cancelled", "retry_scheduled"}
FENCE_KIND = "worker_cursor"  # The worker's own state documents, one actor only.
CLOSING_SECONDS = 600  # No new run starts this close to the task deadline.
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
            return self.repository.document(self.scope, FENCE_KIND, self.ident)
        except Missing:
            return {"revision": 0, "holder": None}

    def _write(self, revision, holder, specimen_id=None, run_id=None, retry_at=None):
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

    def release(self, retry=None):
        """Free the fence, leaving `(specimen_id, retry_at)` for the next holder."""
        specimen_id, retry_at = retry or (None, None)
        try:
            self._write(self.revision, None, specimen_id, retry_at=retry_at)
        except Conflict:
            pass  # Taken over after expiry; the new holder owns it now.


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
        lease_seconds=300,
        max_steps_per_run=500,
    ):
        self.repository, self.workflow = repository, workflow
        self.user_id, self.membership_loader = user_id, membership_loader
        self.execution_id = execution_id
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleep = sleep
        # Starts the next execution for work left at the end.
        self.continuation = continuation
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
            "continuation": None,
        }
        earliest = None
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
            retries = {}
            try:
                status = self._drain(principal, fence, previous, retries, stop, summary)
            except FenceLost:
                # Another execution took over after this one stalled past its lease.
                summary["skipped_collections"].append(scope.collection_id)
                continue
            finally:
                first = min(retries.items(), key=lambda item: item[1], default=None)
                fence.release(first and (first[0], first[1].isoformat()))
            if first:
                summary["pending_retries"] += len(retries)
                earliest = min(earliest or first[1], first[1])
            if status != "drained":
                summary["status"] = status
                break
        if self.continuation and self._hand_over(summary["status"], earliest):
            summary["continuation"] = self.continuation().status
        return summary

    def _hand_over(self, status, earliest):
        """Whether the next execution has work: the rest of the queue, or a retry
        it can reach. A stop signal is left to whoever stopped the job."""
        if status == "window_closed":
            return True
        reach = self.clock() + timedelta(seconds=self.window_seconds)
        return status == "drained" and earliest is not None and earliest <= reach

    def _next_due(self, principal):
        # A cutoff a second behind keeps it no later than the database's clock.
        cutoff = (self.clock() - timedelta(seconds=1)).isoformat()
        due = self.repository.oldest_due(principal.scope, cutoff, limit=1)
        return due[0].specimen_id if due else None

    def _drain(self, principal, fence, previous, retries, stop, summary):
        # The run a dead execution left under the fence is finished first, and a
        # retry a finished execution handed over is waited for like this one's own.
        resume = previous.get("specimen_id") if previous.get("holder") else None
        if not previous.get("holder") and previous.get("retry_at"):
            retries[previous["specimen_id"]] = moment(previous["retry_at"])
        while True:
            if self._stopped(stop):
                return "stopped"
            if self.clock() >= self.close_at:
                return "window_closed"
            ident, resume = resume or self._next_due(principal), None
            if ident is None:
                waitable = [at for at in retries.values() if at <= self.close_at]
                if not waitable:
                    return "drained"
                # Nothing else would start the job for these retries.
                seconds = (min(waitable) - self.clock()).total_seconds() + 2
                self._pause(max(1.0, seconds), stop)
                for key in [key for key, at in retries.items() if at <= self.clock()]:
                    del retries[key]  # Due now, so the queue returns it.
                continue
            run = self._step_until_stopped(principal, fence, ident, stop)
            if ident not in summary["processed"]:
                summary["processed"].append(ident)
            if run.stage == "retry_scheduled" and run.next_retry_at:
                retries[ident] = moment(run.next_retry_at)
            else:
                retries.pop(ident, None)

    def _step_until_stopped(self, principal, fence, ident, stop):
        fence.hold(ident)
        for _ in range(self.max_steps_per_run):
            before = self.repository.get(principal.scope, ident).version
            specimen = self.workflow.step(principal, ident)
            fence.hold(ident, specimen.run.id)
            run = specimen.run
            if (
                run.disposition
                or run.stage in STOPPED
                or specimen.version == before  # Leased or otherwise waiting.
                or self._stopped(stop)
            ):
                return run
        return run
