"""Bounded polling worker over retained runs. Engine selection remains separate."""

import argparse
import os
import json
import time
import threading
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5
from dataclasses import dataclass, field
import logfire
from pathlib import Path
from .api import SYNTHETIC_TEXT, SYNTHETIC_COLLECTION, SYNTHETIC_ORG
from .domain import AuditEvent, Principal, Scope, now
from .production import (
    sql_emulator_host,
    SqlConnectRepository,
    GcsBlobs,
    ProductionAdapters,
    actor_uid,
)
from .storage import SQLiteRepository, LocalBlobs, Conflict, Missing, digest
from .workflow import Workflow, SyntheticAdapters, OperationalBlock


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

    def tick(self, stop=None):
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
            if stop is not None and stop.is_set():
                break
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
                    if stop is not None and stop.is_set():
                        return self.health
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

    def run(self, stop: threading.Event, interval_seconds: float = 1, max_seconds=None):
        if not 0.1 <= interval_seconds <= 60:
            raise ValueError("Worker interval must be .1..60 seconds")
        started = time.monotonic()
        while not stop.is_set():
            if max_seconds is not None and time.monotonic() - started >= max_seconds:
                return
            self.tick(stop)
            stop.wait(interval_seconds)


class PilotWorker(PollingWorker):
    """Exactly ten explicit IDs; no collection-wide discovery or mutable denominator."""

    def __init__(self, repository, workflow, user_id, membership_loader, admission):
        super().__init__(repository, workflow, user_id, membership_loader)
        self.admission = admission

    def _persist_blocker(self, principal, specimen_id, reason):
        specimen = self.repository.get(principal.scope, specimen_id)
        # A mismatched record is not authorized for mutation, even when its ID
        # appears in the launch file. Keep that problem only in launch health.
        if not self.admission.binding_matches(specimen):
            return
        if specimen.run.stage in {"finalized", "cancelled", "paused"}:
            return
        if specimen.run.blocker != "external_outcome_unknown":
            specimen.run.blocker = reason
        specimen.run.stage = "processing_blocked"
        specimen.run.disposition = None
        specimen.audit.append(
            AuditEvent(
                actor=principal.user_id,
                action="pilot_admission_blocked",
                reason=reason,
            )
        )
        self.repository.save(
            principal,
            specimen,
            specimen.version,
            f"pilot-block:{specimen.version}",
            digest({"reason": reason, "run_id": specimen.run.id}),
        )

    def run(self, stop, interval_seconds=1, max_seconds=None):
        if not 0.1 <= interval_seconds <= 60:
            raise ValueError("Worker interval must be .1..60 seconds")
        started = time.monotonic()
        while not stop.is_set():
            if max_seconds is not None and time.monotonic() - started >= max_seconds:
                return
            self.tick(stop)
            if self.rotation and self.rotation % 10 == 0:
                summary = self.result_summary()
                counts = summary["counts"]
                if (
                    sum(counts.values()) == 10
                    and not counts.get("pending")
                    and not counts.get("unavailable")
                ):
                    return  # Terminal/review/blocked batch never waits for human input.
            stop.wait(interval_seconds)

    def result_summary(self):
        """Read every authorized record, not only records attempted this process."""
        launch = self.admission.launch
        summary = {
            "status": "incomplete",
            "authorized": 10,
            "counts": {},
            "specimens": {},
        }
        actor_uid.set(self.user_id)
        try:
            memberships = self.membership_loader(self.user_id)
            if not any(
                m["organization_id"] == launch.scope.organization_id
                and m["collection_id"] == launch.scope.collection_id
                and m["role"] in {"operator", "reviewer", "manager", "admin"}
                for m in memberships
            ):
                return dict(
                    summary, status="blocked", blocker="pilot_membership_required"
                )
            for binding in launch.specimens:
                try:
                    specimen = self.repository.get(launch.scope, binding.specimen_id)
                    if not self.admission.binding_matches(specimen):
                        state, reason = "blocked", "pilot_specimen_binding_mismatch"
                    elif specimen.run.stage == "finalized":
                        state, reason = (
                            ("blocked", "pilot_clearance_forbidden")
                            if launch.evidence_only
                            else ("finalized", None)
                        )
                    elif specimen.run.blocker == "pilot_evidence_review_required":
                        state, reason = "review_required", specimen.run.blocker
                    elif specimen.run.stage in {
                        "processing_blocked",
                        "paused",
                        "cancelled",
                    }:
                        state, reason = specimen.run.stage, specimen.run.blocker
                    else:
                        state, reason = "pending", specimen.run.blocker
                except Exception:
                    state, reason = "unavailable", "pilot_record_unavailable"
                summary["counts"][state] = summary["counts"].get(state, 0) + 1
                summary["specimens"][binding.specimen_id] = {
                    "state": state,
                    "blocker": reason,
                }
            if summary["counts"].get("finalized") == 10:
                summary["status"] = "completed"
            elif summary["counts"].get("review_required") == 10:
                summary["status"] = "evidence_review_required"
            summary = self.admission.save_summary(summary)
        except Exception:
            summary["status"] = "blocked"
            summary["blocker"] = "pilot_summary_persistence_unavailable"
        return summary

    def tick(self, stop=None):
        actor_uid.set(self.user_id)
        self.health.ticks += 1
        if stop is not None and stop.is_set():
            return self.health
        launch = self.admission.launch
        try:
            memberships = self.membership_loader(self.user_id)
        except Exception:
            self.health.membership_errors += 1
            return self.health
        member = next(
            (
                m
                for m in memberships
                if m["organization_id"] == launch.scope.organization_id
                and m["collection_id"] == launch.scope.collection_id
                and m["role"] in {"operator", "reviewer", "manager", "admin"}
            ),
            None,
        )
        if member is None:
            self.health.blocked_scopes["pilot"] = "pilot_membership_required"
            return self.health
        self.health.blocked_scopes.pop("pilot", None)
        principal = Principal(
            user_id=self.user_id, scope=launch.scope, role=member["role"]
        )
        binding = launch.specimens[self.rotation % 10]
        self.rotation += 1
        try:
            specimen = self.repository.get(launch.scope, binding.specimen_id)
            if specimen.run.stage in {
                "finalized",
                "paused",
                "cancelled",
                "processing_blocked",
            }:
                self.admission.note_outcome(specimen)
                if specimen.run.stage != "finalized":
                    self.health.blocked_scopes[binding.specimen_id] = (
                        specimen.run.blocker or specimen.run.stage
                    )
                return self.health
            if stop is not None and stop.is_set():
                return self.health
            self.admission.begin_step(specimen)
            if stop is not None and stop.is_set():
                # This instance positively knows dispatch has not begun.
                self.admission.note_outcome(specimen, completed_dispatch=True)
                return self.health
            result = self.workflow.step(principal, binding.specimen_id)
            retained = self.repository.get(launch.scope, binding.specimen_id)
            # Only a real returned, retained checkpoint closes a dispatch. The
            # API may have mutated the current revision while an effect ran.
            if (
                result is None
                or retained.version != result.version
                or retained.run != result.run
            ):
                raise Conflict("Pilot result changed before dispatch acknowledgement")
            self.admission.note_outcome(retained, completed_dispatch=True)
            self.health.attempted += 1
            self.health.last_success_at = self.clock()
            if retained.run.stage == "processing_blocked":
                self.health.blocked_scopes[binding.specimen_id] = (
                    retained.run.blocker or "processing_blocked"
                )
            else:
                self.health.blocked_scopes.pop(binding.specimen_id, None)
        except OperationalBlock as exc:
            self.health.blocked_scopes[binding.specimen_id] = str(exc)
            try:
                self._persist_blocker(principal, binding.specimen_id, str(exc))
            except Exception:
                self.health.record_errors += 1
        except Conflict:
            self.health.conflicts += 1
        except Exception:
            self.health.record_errors += 1
            self.health.blocked_scopes[binding.specimen_id] = "pilot_record_unavailable"
        finally:
            self.admission.abandon_dispatch(binding.specimen_id)
        return self.health


def production_launch(args):
    from .worker_launch import read_launch, verify_source_manifest
    from ..hub_models import SAM3_MODEL

    if not args.launch_policy or not args.source_manifest:
        raise OperationalBlock("pilot_launch_and_source_manifest_required")
    launch = read_launch(
        args.launch_policy, os.getenv("SPECIMEN_LAUNCH_POLICY_SHA256", "")
    )
    verify_source_manifest(args.source_manifest, launch)
    from datetime import timezone

    if (
        datetime.now(timezone.utc)
        + timedelta(seconds=launch.effect_timeout_seconds + 5)
        >= launch.expires_at
    ):
        raise OperationalBlock("pilot_launch_deadline_reached")
    if bool(getattr(args, "evidence_only", False)) != launch.evidence_only:
        raise OperationalBlock("pilot_evidence_mode_mismatch")
    if launch.evidence_only and os.getenv("SPECIMEN_APPROVED_EVIDENCE_PILOT") != "true":
        raise OperationalBlock("pilot_evidence_approval_required")
    if os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true":
        raise OperationalBlock("provider_data_policy_and_spending_approval_required")
    if (
        not os.getenv("HF_TOKEN")
        or os.getenv("SPECIMEN_HF_SECRET_RESOURCE") != launch.hf_secret_resource
    ):
        raise OperationalBlock("pinned_hf_secret_required")
    if os.getenv("SPECIMEN_SAM3_REVISION") != SAM3_MODEL.revision:
        raise OperationalBlock("pinned_sam3_revision_required")
    from .production import Sam3Service

    try:
        Sam3Service(os.getenv("SPECIMEN_SAM3_ENDPOINT", ""), None)
    except ValueError:
        raise OperationalBlock("sam3_service_required") from None
    if not os.getenv("SPECIMEN_WORKER_ACTOR_UID"):
        raise OperationalBlock("worker_actor_required")
    if any(
        os.getenv(key)
        for key in (
            "FIREBASE_AUTH_EMULATOR_HOST",
            "FIREBASE_STORAGE_EMULATOR_HOST",
            "DATA_CONNECT_EMULATOR_HOST",
            "SPECIMEN_SQL_EMULATOR_HOST",
        )
    ):
        raise OperationalBlock("production_emulator_configuration_forbidden")
    return launch


def main():
    from .worker_version import version

    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=json.dumps(version()))
    parser.add_argument("--mode", choices=["synthetic", "production"], required=True)
    parser.add_argument(
        "--state-dir", type=Path, default=Path("/tmp/specimen-synthetic")
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--launch-policy", type=Path)
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--evidence-only", action="store_true")
    parser.add_argument("--evidence-profile", type=Path)
    parser.add_argument("--max-seconds", type=int, default=1500)
    parser.add_argument(
        "--persistence", choices=["sqlite", "sql-emulator"], default="sqlite"
    )
    args = parser.parse_args()
    if not 1 <= args.max_seconds <= 1500:
        parser.error("max-seconds must be 1..1500")
    launch = None
    evidence_profile = None
    if args.mode == "production":
        try:
            launch = production_launch(args)
            if args.evidence_only:
                from .evidence_pilot import read_evidence_profile

                if not args.evidence_profile:
                    raise OperationalBlock("pilot_evidence_profile_required")
                evidence_profile = read_evidence_profile(
                    args.evidence_profile, launch.evidence_profile_sha256
                )
        except OperationalBlock as exc:
            print(json.dumps({"status": "blocked", "reason": str(exc)}))
            raise SystemExit(2) from None
    if args.check_config:
        print(json.dumps({"status": "configured", "live_services_verified": False}))
        return
    from ..observability import configure_observability, CaptureMode

    configure_observability(
        send_to_logfire=False if args.mode == "synthetic" else None,
        capture_mode=CaptureMode.METADATA,
    )
    stop = threading.Event()
    import signal

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda signum, frame: stop.set())
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
        worker = PollingWorker(
            repository,
            Workflow(repository, blobs, adapters),
            user,
            lambda user: memberships,
        )
    else:
        from .worker_launch import PilotAdmission

        user = os.environ["SPECIMEN_WORKER_ACTOR_UID"]
        actor_uid.set(user)
        repository = SqlConnectRepository()
        blobs = GcsBlobs()
        adapters = ProductionAdapters(blobs)
        admission = PilotAdmission(repository, launch)
        if args.evidence_only:
            from .evidence_pilot import EvidencePilotWorkflow

            workflow = EvidencePilotWorkflow(
                repository, blobs, admission, evidence_profile, production=adapters
            )
        else:
            workflow = Workflow(repository, blobs, adapters, admission=admission)
        worker = PilotWorker(
            repository, workflow, user, repository.memberships, admission
        )
    if args.once:
        worker.tick(stop)
    else:
        worker.run(stop, max_seconds=args.max_seconds)
    if isinstance(worker, PilotWorker):
        summary = worker.result_summary()
        print(json.dumps(summary))
        if summary["status"] != "completed":
            raise SystemExit(2)
    print(
        json.dumps(
            {
                "status": "stopped",
                "ticks": worker.health.ticks,
                "attempted": worker.health.attempted,
                "record_errors": worker.health.record_errors,
                "blockers": sorted(set(worker.health.blocked_scopes.values())),
            }
        )
    )
    if (
        worker.health.record_errors
        or worker.health.membership_errors
        or worker.health.blocked_scopes
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
