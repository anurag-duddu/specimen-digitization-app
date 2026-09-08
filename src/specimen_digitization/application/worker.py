"""Bounded polling worker over retained runs. Engine selection remains separate."""

import argparse
import os
import threading
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5
from dataclasses import dataclass, field
import logfire
from pathlib import Path
from .api import SYNTHETIC_TEXT, SYNTHETIC_COLLECTION, SYNTHETIC_ORG
from .domain import Principal, Scope, now
from .production import (
    sql_emulator_host,
    SqlConnectRepository,
    GcsBlobs,
    ProductionAdapters,
    actor_uid,
)
from .storage import SQLiteRepository, LocalBlobs, Conflict, Missing
from .workflow import Workflow, SyntheticAdapters


@dataclass
class WorkerHealth:
    ticks: int = 0
    attempted: int = 0
    conflicts: int = 0
    record_errors: int = 0
    scope_errors: int = 0
    membership_errors: int = 0
    last_success_at: str | None = None
    oldest_due_at: str | None = None
    blocked_scopes: dict[str, str] = field(default_factory=dict)


class PollingWorker:
    """Bounded round-robin discovery; persisted keyset cursors survive restarts."""

    def __init__(
        self,
        repository,
        workflow,
        user_id,
        membership_loader,
        *,
        page_size=25,
        steps_per_scope=1,
        max_scopes=8,
        clock=now,
    ):
        if not 1 <= steps_per_scope <= page_size <= 100:
            raise ValueError("Invalid bounded worker page settings")
        if not 1 <= max_scopes <= 100:
            raise ValueError("Invalid scope budget")
        self.max_scopes = max_scopes
        self.repository = repository
        self.workflow = workflow
        self.user_id = user_id
        self.membership_loader = membership_loader
        self.page_size = page_size
        self.steps_per_scope = steps_per_scope
        self.clock = clock
        self.health = WorkerHealth()
        self.failures = {}
        self.retry_at = {}
        self.rotation = 0

    def _backoff(self, key, reason):
        count = self.failures.get(key, 0) + 1
        self.failures[key] = count
        delay = min(60, 2 ** min(count, 6))
        self.retry_at[key] = (
            datetime.fromisoformat(self.clock()) + timedelta(seconds=delay)
        ).isoformat()
        self.health.blocked_scopes[key] = reason

    def tick(self):
        actor_uid.set(self.user_id)
        self.health.ticks += 1
        self.health.oldest_due_at = None
        current = self.clock()
        if self.retry_at.get("memberships", "") > current:
            return self.health
        try:
            memberships = self.membership_loader(self.user_id)
        except Exception:
            self.health.membership_errors += 1
            self._backoff("memberships", "membership_unavailable")
            return self.health
        self.failures.pop("memberships", None)
        self.retry_at.pop("memberships", None)
        self.health.blocked_scopes.pop("memberships", None)
        allowed = [
            m
            for m in memberships
            if m["role"] in {"operator", "reviewer", "manager", "admin"}
        ]
        if not allowed:
            return self.health
        start = self.rotation % len(allowed)
        self.rotation += self.max_scopes
        for membership in (allowed[start:] + allowed[:start])[: self.max_scopes]:
            scope = Scope(
                organization_id=membership["organization_id"],
                collection_id=membership["collection_id"],
            )
            principal = Principal(
                user_id=self.user_id, scope=scope, role=membership["role"]
            )
            scope_key = scope.model_dump_json()
            if self.retry_at.get(scope_key, "") > current:
                continue
            cursor_id = str(
                uuid5(NAMESPACE_URL, "worker-cursor:" + self.user_id + scope_key)
            )
            try:
                try:
                    cursor = self.repository.document(scope, "worker_cursor", cursor_id)
                except Missing:
                    cursor = {"revision": 0, "cutoff": current, "after_id": None}
                page = self.repository.due_page(
                    scope, cursor["cutoff"], cursor.get("after_id"), self.page_size
                )
                considered = page.items[: self.steps_per_scope]
                for item in considered:
                    self.health.oldest_due_at = min(
                        self.health.oldest_due_at or item.work_available_at,
                        item.work_available_at,
                    )
                    record_key = scope_key + ":" + item.specimen_id
                    if self.retry_at.get(record_key, "") > current:
                        continue
                    try:
                        self.workflow.step(principal, item.specimen_id)
                        self.failures.pop(record_key, None)
                        self.retry_at.pop(record_key, None)
                        self.health.blocked_scopes.pop(record_key, None)
                        self.health.attempted += 1
                        self.health.last_success_at = self.clock()
                    except Conflict:
                        self.health.conflicts += 1
                    except PermissionError:
                        # A membership can be revoked after discovery. Do not try later items.
                        self._backoff(scope_key, "authorization_recheck_required")
                        raise
                    except Exception:
                        self.health.record_errors += 1
                        self._backoff(record_key, "record_unavailable")
                        logfire.warning(
                            "Worker record failed", specimen_id=item.specimen_id
                        )
                exhausted = (
                    len(considered) == len(page.items) and page.next_cursor is None
                )
                payload = {
                    "cutoff": self.clock() if exhausted else cursor["cutoff"],
                    "after_id": None if exhausted else considered[-1].specimen_id,
                    "actor_uid": self.user_id,
                }
                self.repository.put_document(
                    scope, "worker_cursor", cursor_id, payload, cursor["revision"]
                )
                self.failures.pop(scope_key, None)
                self.retry_at.pop(scope_key, None)
                self.health.blocked_scopes.pop(scope_key, None)
            except Conflict:
                self.health.conflicts += 1
            except Exception:
                self.health.scope_errors += 1
                self._backoff(scope_key, "scope_control_plane_unavailable")
        return self.health

    def run(self, stop: threading.Event, interval_seconds: float = 1):
        if not 0.1 <= interval_seconds <= 60:
            raise ValueError("Worker interval must be .1..60 seconds")
        while not stop.is_set():
            self.tick()
            stop.wait(interval_seconds)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["synthetic", "production"], required=True)
    parser.add_argument(
        "--state-dir", type=Path, default=Path("/tmp/specimen-synthetic")
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--persistence", choices=["sqlite", "sql-emulator"], default="sqlite"
    )
    args = parser.parse_args()
    from ..observability import configure_observability, CaptureMode

    configure_observability(
        send_to_logfire=False if args.mode == "synthetic" else None,
        capture_mode=CaptureMode.METADATA,
    )
    if args.mode == "synthetic":
        repository = (
            SqlConnectRepository(
                project="demo-specimen-data", emulator_host=sql_emulator_host()
            )
            if args.persistence == "sql-emulator"
            else SQLiteRepository(args.state_dir / "state.sqlite3")
        )
        blobs = LocalBlobs(args.state_dir / "blobs")
        adapters = SyntheticAdapters(blobs, SYNTHETIC_TEXT)
        user = "synthetic-reviewer"
        memberships = [
            {
                "organization_id": SYNTHETIC_ORG,
                "collection_id": SYNTHETIC_COLLECTION,
                "role": "reviewer",
            }
        ]
    else:
        user = os.environ["SPECIMEN_WORKER_ACTOR_UID"]
        repository = SqlConnectRepository()
        blobs = GcsBlobs()
        adapters = ProductionAdapters(blobs)
        memberships = repository.memberships(user)
    workflow = Workflow(repository, blobs, adapters)
    loader = (
        repository.memberships
        if args.mode == "production"
        else lambda user: memberships
    )
    worker = PollingWorker(repository, workflow, user, loader)
    if args.once:
        worker.tick()
        return
    stop = threading.Event()
    import signal

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda signum, frame: stop.set())
    worker.run(stop)


if __name__ == "__main__":
    main()
