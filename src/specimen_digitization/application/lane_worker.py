"""The production worker drains the queue (docs/execution/golive/LANE.md, T2).

Its settings, and the collection fence that keeps two executions of the job
from draining one collection at once (G13).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5

from .storage import Conflict, Missing

FENCE_KIND = "worker_cursor"  # The worker's own state documents, one actor only.
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
