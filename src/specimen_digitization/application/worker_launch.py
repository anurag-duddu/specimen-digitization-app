"""Private, digest-pinned admission contract for the ten-specimen pilot.

The data owner's frozen source manifest and this post-import binding are separate:
this contract never discovers, downloads, or imports cloud objects.
"""

from datetime import datetime, timezone, timedelta
import hashlib
import math
import re
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5, uuid4

from pydantic import Field, model_validator

from .domain import Record, Scope, StageCostReservations
from .storage import Missing, digest
from .workflow import OperationalBlock


class PilotSpecimen(Record):
    specimen_id: str = Field(min_length=1, max_length=100)
    asset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    blob_ref: str = Field(pattern=r"^[a-f0-9]{64}:[1-9][0-9]*$")

    @model_validator(mode="after")
    def immutable_reference(self):
        if self.blob_ref.split(":")[0] != self.asset_sha256:
            raise ValueError("Pilot asset/reference digest mismatch")
        return self


class PilotLaunch(Record):
    sensitive: bool = Field(
        default=True, strict=True, exclude_if=lambda value: value is True
    )
    version: str = "authorized-ten-v1"
    evidence_only: bool = False
    evidence_profile_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    sam3_checkpoint_files: dict[str, str] | None = None
    source_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    authorization_reference: str = Field(min_length=1, max_length=200)
    scope: Scope
    specimens: list[PilotSpecimen] = Field(min_length=10, max_length=10)
    expires_at: datetime
    total_cost_limit_micros: int = Field(gt=0)
    per_specimen_cost_limit_micros: int = Field(gt=0)
    per_specimen_call_limit: int = Field(gt=0, le=1000)
    per_specimen_token_limit: int = Field(gt=0)
    stage_cost_reservations: StageCostReservations | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    effect_timeout_seconds: float = Field(gt=0, le=120, allow_inf_nan=False)
    hf_secret_resource: str = Field(
        pattern=r"^projects/specimen-digitization/secrets/[a-zA-Z0-9_-]+/versions/[1-9][0-9]*$"
    )

    @model_validator(mode="after")
    def bounded_pilot(self):
        if self.version != "authorized-ten-v1":
            raise ValueError("Unsupported launch contract")
        if self.evidence_only != (self.evidence_profile_sha256 is not None):
            raise ValueError(
                "Evidence-only launches require exactly one pinned draft profile"
            )
        if self.expires_at.tzinfo is None:
            raise ValueError("Launch expiry requires timezone")
        if len({s.specimen_id for s in self.specimens}) != 10:
            raise ValueError("Pilot specimen IDs must be unique")
        if len({s.blob_ref for s in self.specimens}) != 10:
            raise ValueError("Pilot objects must be unique")
        if 10 * self.per_specimen_cost_limit_micros > self.total_cost_limit_micros:
            raise ValueError("Ten conservative allocations exceed launch budget")
        if self.stage_cost_reservations is not None:
            from ..model_gateway import INITIAL_HUGGINGFACE_ROUTES

            stages = {"segment"} | {
                "transcribe:" + route for route in INITIAL_HUGGINGFACE_ROUTES
            }
            if not self.evidence_only:
                stages |= {"classify", "parse"}
            if set(self.stage_cost_reservations.cost_micros) != stages:
                raise ValueError(
                    "Launch requires an exact complete model stage cost map"
                )
        if self.sam3_checkpoint_files is not None:
            import re

            if (
                not self.sam3_checkpoint_files
                or len(self.sam3_checkpoint_files) > 64
                or not any(
                    name.endswith(".safetensors") for name in self.sam3_checkpoint_files
                )
                or any(
                    not re.fullmatch(
                        r"[A-Za-z0-9][A-Za-z0-9._-]{0,200}\.(?:safetensors|json|txt)",
                        name,
                    )
                    or not re.fullmatch(r"[a-f0-9]{64}", value)
                    for name, value in self.sam3_checkpoint_files.items()
                )
            ):
                raise ValueError("Pinned SAM checkpoint file map required")
        return self


def read_launch(path: Path, expected_sha256: str) -> PilotLaunch:
    # Bound allocation and validate digest before parsing sensitive configuration.
    from .private_config import read_private

    try:
        raw = read_private(path)
    except (OSError, ValueError):
        raise OperationalBlock("pilot_private_configuration_required") from None
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise OperationalBlock("pilot_launch_digest_mismatch")
    try:
        return PilotLaunch.model_validate_json(raw)
    except ValueError:
        raise OperationalBlock("pilot_launch_contract_invalid") from None


class PilotAdmission:
    def __init__(self, repository, launch, *, clock=None):
        self.repository, self.launch = repository, launch
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.bindings = {item.specimen_id: item for item in launch.specimens}
        self.launch_digest = digest(launch.model_dump(mode="json"))
        # Stable across config changes and restarts. A revised config cannot reset
        # reservations for this source cohort. Different scope is not authorized.
        self.ledger_id = str(
            uuid5(NAMESPACE_URL, "pilot:" + launch.source_manifest_sha256)
        )
        self._dispatch_tokens = {}
        self.remaining_execution_seconds = None

    def bind_execution_window(self, max_seconds=1500, interval_seconds=1):
        """Retain the existing single execution's deadline; never refresh it."""
        if (
            type(max_seconds) not in (int, float)
            or not math.isfinite(max_seconds)
            or not 1 <= max_seconds <= 1500
            or type(interval_seconds) not in (int, float)
            or not math.isfinite(interval_seconds)
            or not 0.1 <= interval_seconds <= 60
        ):
            raise OperationalBlock("pilot_cohort_execution_time_invalid")
        ledger = self._ledger()
        current = self.clock().timestamp()
        window_exists = "execution_window" in ledger
        previous = ledger.get("execution_window")
        if window_exists and not isinstance(previous, dict):
            raise OperationalBlock("pilot_cohort_execution_time_changed")
        if not window_exists and (
            ledger.get("reading_cohort")
            or any(
                self.repository.get(self.launch.scope, ident).run.usage.external_calls
                for ident in ledger["runs"]
            )
        ):
            raise OperationalBlock("pilot_cohort_execution_time_unreconciled")
        window = {
            "started_at_unix": current,
            "deadline_unix": current + max_seconds,
            "interval_seconds": interval_seconds,
        }
        if window_exists:
            if (
                set(previous) != set(window)
                or any(
                    type(value) not in (int, float) or not math.isfinite(value)
                    for value in previous.values()
                )
                or not 0
                < previous["deadline_unix"] - previous["started_at_unix"]
                <= 1500
                or not 0.1 <= previous["interval_seconds"] <= 60
                or current < previous["started_at_unix"]
            ):
                raise OperationalBlock("pilot_cohort_execution_time_changed")
            window = dict(
                previous,
                deadline_unix=min(previous["deadline_unix"], window["deadline_unix"]),
                interval_seconds=max(previous["interval_seconds"], interval_seconds),
            )
        if window != previous:
            self._write(ledger, execution_window=window)
        if current >= window["deadline_unix"]:
            raise OperationalBlock("pilot_cohort_execution_time_exhausted")

    def _reading_time(self, ledger, records):
        window = ledger.get("execution_window")
        if not window:
            raise OperationalBlock("pilot_cohort_execution_time_required")
        current = self.clock()
        remaining = min(
            window["deadline_unix"] - current.timestamp(),
            (self.launch.expires_at - current).total_seconds(),
        )
        if self.remaining_execution_seconds is not None:
            remaining = min(remaining, self.remaining_execution_seconds())
        seconds = 5.0  # Retain the existing deadline safety margin.
        for ident, specimen in records.items():
            run, policy = specimen.run, specimen.run.profile.execution
            if run.blocker != "pilot_evidence_review_required":
                seconds += window["interval_seconds"]
            if run.next_retry_at:
                seconds += max(
                    0,
                    (
                        datetime.fromisoformat(run.next_retry_at) - current
                    ).total_seconds(),
                )
            for region in run.regions:
                for route in run.profile.routes:
                    step = "transcribe:" + region.id + ":" + route
                    if step in run.completed_steps:
                        continue
                    used = ledger.get("reader_claims", {}).get(ident, {}).get(step, 0)
                    attempts = policy.max_attempts - used
                    seconds += attempts * (
                        policy.external_timeout_seconds + window["interval_seconds"]
                    )
                    # Maximum local retry jitter. A later provider Retry-After
                    # is rechecked against the same unextended deadline.
                    seconds += sum(
                        2 * min(300, 2 ** min(attempt, 8))
                        for attempt in range(int(used) + 1, policy.max_attempts)
                    )
        return seconds, (
            "pilot_cohort_reading_time_insufficient" if seconds > remaining else None
        )

    def binding_matches(self, specimen):
        binding = self.bindings.get(specimen.id)
        return bool(
            binding is not None
            and specimen.scope == self.launch.scope
            and specimen.asset.sha256 == binding.asset_sha256
            and specimen.asset.blob_ref == binding.blob_ref
            and not specimen.run.profile.synthetic
            and (self.launch.sensitive or not specimen.asset.sensitive)
            and (
                not self.launch.evidence_only
                or specimen.asset.processing_derivative is None
            )
        )

    def _ledger(self):
        try:
            value = self.repository.document(
                self.launch.scope, "pilot_launch", self.ledger_id
            )
        except Missing:
            value = {"revision": 0, "launch_sha256": self.launch_digest, "runs": {}}
            if not self.launch.sensitive:
                value["sensitive"] = False
        if value["launch_sha256"] != self.launch_digest:
            raise OperationalBlock("pilot_launch_changed_requires_reconciliation")
        if value.get("sensitive", True) != self.launch.sensitive:
            raise OperationalBlock("pilot_launch_sensitivity_mismatch")
        return value

    def _write(self, ledger, **updates):
        payload = {key: value for key, value in ledger.items() if key != "revision"}
        payload.update(updates)
        self.repository.put_document(
            self.launch.scope,
            "pilot_launch",
            self.ledger_id,
            payload,
            ledger["revision"],
        )

    def admit(self, specimen):
        launch, run = self.launch, specimen.run
        if digest(launch.model_dump(mode="json")) != self.launch_digest:
            raise OperationalBlock("pilot_launch_changed_requires_reconciliation")
        if not self.binding_matches(specimen):
            raise OperationalBlock("pilot_specimen_binding_mismatch")
        policy = run.profile.execution
        if policy.stage_cost_reservations != launch.stage_cost_reservations:
            raise OperationalBlock("pilot_stage_cost_reservations_mismatch")
        if (
            self.clock() + timedelta(seconds=policy.external_timeout_seconds + 5)
            >= launch.expires_at
        ):
            raise OperationalBlock("pilot_launch_deadline_reached")
        if (
            policy.approved_cost_limit_micros is None
            or policy.approved_cost_limit_micros <= 0
            or policy.approved_cost_limit_micros > launch.per_specimen_cost_limit_micros
            or (
                launch.stage_cost_reservations is None
                and (
                    policy.request_cost_reservation_micros is None
                    or policy.request_cost_reservation_micros <= 0
                )
            )
            or policy.max_external_calls > launch.per_specimen_call_limit
            or policy.max_tokens > launch.per_specimen_token_limit
            or policy.external_timeout_seconds > launch.effect_timeout_seconds
        ):
            raise OperationalBlock("pilot_run_budget_not_approved")
        ledger = self._ledger()
        lock = ledger.get("dispatches", {}).get(specimen.id)
        if lock is not None and (
            lock.get("state") != "in_flight"
            or lock.get("token") != self._dispatch_tokens.get(specimen.id)
        ):
            raise OperationalBlock("pilot_dispatch_reconciliation_required")
        reservation = {
            "run_id": run.id,
            "policy_sha256": digest(policy.model_dump(mode="json")),
            "routes": list(run.profile.routes),
            "cost_micros": launch.per_specimen_cost_limit_micros,
        }
        previous = ledger["runs"].get(specimen.id)
        if previous is not None:
            if previous != reservation:
                raise OperationalBlock("pilot_run_changed_requires_reconciliation")
            return
        runs = dict(ledger["runs"], **{specimen.id: reservation})
        if (
            sum(item["cost_micros"] for item in runs.values())
            > launch.total_cost_limit_micros
        ):
            raise OperationalBlock("pilot_launch_budget_exhausted")
        self._write(ledger, runs=runs)

    def begin_step(self, specimen):
        """Reserve a durable dispatch fence before any workflow code can run."""
        self.admit(specimen)
        ledger = self._ledger()
        dispatches = dict(ledger.get("dispatches", {}))
        if specimen.id in dispatches:
            raise OperationalBlock("pilot_dispatch_reconciliation_required")
        token = str(uuid4())
        dispatches[specimen.id] = {
            "token": token,
            "state": "in_flight",
            "run_id": specimen.run.id,
            "specimen_revision": specimen.version,
            "started_at": self.clock().isoformat(),
        }
        self._write(ledger, dispatches=dispatches)
        self._dispatch_tokens[specimen.id] = token

    def abandon_dispatch(self, specimen_id):
        # Never clear the durable fence after an exception or unknown outcome.
        self._dispatch_tokens.pop(specimen_id, None)

    def note_outcome(self, specimen, *, completed_dispatch=False):
        """Retain status; clear only this instance's positively returned dispatch."""
        if not self.binding_matches(specimen):
            raise OperationalBlock("pilot_specimen_binding_mismatch")
        ledger = self._ledger()
        dispatches = dict(ledger.get("dispatches", {}))
        lock = dispatches.get(specimen.id)
        unknown = specimen.run.blocker == "external_outcome_unknown"
        owned = bool(
            lock and lock.get("token") == self._dispatch_tokens.get(specimen.id)
        )
        if unknown and lock is None:
            dispatches[specimen.id] = {
                "state": "outcome_unknown",
                "run_id": specimen.run.id,
                "specimen_revision": specimen.version,
                "observed_at": self.clock().isoformat(),
            }
        if completed_dispatch and not owned:
            raise OperationalBlock("pilot_dispatch_reconciliation_required")
        if lock and owned and completed_dispatch:
            if unknown:
                dispatches[specimen.id] = dict(lock, state="outcome_unknown")
            else:
                del dispatches[specimen.id]
        outcomes = dict(ledger.get("outcomes", {}))
        outcomes[specimen.id] = {
            "run_id": specimen.run.id,
            "revision": specimen.version,
            "stage": specimen.run.stage,
            "blocker": specimen.run.blocker,
            "recorded_at": self.clock().isoformat(),
        }
        self._write(ledger, dispatches=dispatches, outcomes=outcomes)
        if completed_dispatch:
            self._dispatch_tokens.pop(specimen.id, None)

    def save_summary(self, summary):
        ledger = self._ledger()
        if ledger.get("dispatches"):
            summary = dict(
                summary,
                status="incomplete",
                unresolved_dispatches=len(ledger["dispatches"]),
                blocker="pilot_dispatch_reconciliation_required",
            )
        self._write(ledger, summary=summary)
        return summary

    def cohort_blocker(self):
        ledger = self._ledger()
        if ledger.get("reading_time_blocker"):
            return ledger["reading_time_blocker"]
        cohort = ledger.get("reading_cohort", {})
        return cohort.get("reason") if cohort.get("state") == "blocked" else None

    def _reading_snapshot(self, ledger, *, in_flight=None):
        """Only retained metadata; neither source images nor model calls are read."""
        from ..model_gateway import INITIAL_HUGGINGFACE_ROUTES

        if not self.launch.evidence_only or set(ledger["runs"]) != set(self.bindings):
            raise OperationalBlock("pilot_cohort_prior_allocations_incomplete")
        snapshot, records = {}, {}
        profiles = set()
        for binding in self.launch.specimens:
            specimen = self.repository.get(self.launch.scope, binding.specimen_id)
            self.admit(specimen)  # Existing allocations only; never a second debit.
            run, policy = specimen.run, specimen.run.profile.execution
            if "segment" not in run.completed_steps:
                raise OperationalBlock("pilot_cohort_segmentation_incomplete")
            active = (
                in_flight is not None
                and specimen.id == in_flight.id
                and specimen == in_flight
            )
            if (
                run.blocker == "external_outcome_unknown" and not active
            ) or run.stage in {"paused", "cancelled", "finalized"}:
                raise OperationalBlock("pilot_cohort_unresolved_liability")
            if (
                run.stage == "processing_blocked"
                and run.blocker != "pilot_evidence_review_required"
            ):
                raise OperationalBlock("pilot_cohort_unresolved_liability")
            regions = run.regions
            if (
                not 0 < len(regions) <= 64
                or len({region.id for region in regions}) != len(regions)
                or any(
                    not region.id
                    or ":" in region.id
                    or region.asset_id != specimen.asset.id
                    or region.x + region.width > specimen.asset.width
                    or region.y + region.height > specimen.asset.height
                    for region in regions
                )
            ):
                raise OperationalBlock("pilot_cohort_regions_invalid")
            if tuple(run.profile.routes) != tuple(INITIAL_HUGGINGFACE_ROUTES):
                raise OperationalBlock("pilot_cohort_reader_routes_changed")
            marker = run.dependencies.get("evidence_pilot", {})
            retained_pins = {
                key: value
                for key, value in run.dependencies.items()
                if key != "evidence_pilot"
            }
            if (
                marker.get("version") != "evidence-pilot-v1"
                or marker.get("launch_sha256") != self.launch_digest
                or marker.get("source_manifest_sha256")
                != self.launch.source_manifest_sha256
                or marker.get("profile_sha256") != self.launch.evidence_profile_sha256
                or marker.get("runtime_pins_sha256") != digest(retained_pins)
                or run.profile_rules
                or run.risk_policy_snapshot.get("status") != "blocked"
                or run.profile.institutional_policy_approved
                or run.profile.semantics_confirmed
                or run.human_approved
                or run.disposition is not None
            ):
                raise OperationalBlock("pilot_cohort_provenance_mismatch")
            segmentation = run.segmentation
            settings = run.profile_snapshot.get("segmentation_settings", {})
            if (
                segmentation.get("validation") != "valid"
                or segmentation.get("input_sha256") != binding.asset_sha256
                or not segmentation.get("blob_ref")
                or not settings
                or segmentation.get("settings") != settings
                or segmentation.get("model_id") != settings.get("model_id")
                or segmentation.get("model_revision") != settings.get("model_revision")
                or any(
                    not re.fullmatch(r"[a-f0-9]{64}", segmentation.get(key, ""))
                    for key in ("sha256", "request_sha256")
                )
            ):
                raise OperationalBlock("pilot_cohort_segmentation_provenance_missing")
            prices = {
                route: (
                    policy.stage_cost_reservations.for_step(
                        "transcribe:region:" + route
                    )
                    if policy.stage_cost_reservations is not None
                    else policy.request_cost_reservation_micros
                )
                for route in run.profile.routes
            }
            if any(
                type(amount) is not int or amount <= 0 for amount in prices.values()
            ):
                raise OperationalBlock("pilot_cohort_reader_cost_unknown")
            profiles.add(digest(run.profile_snapshot))
            snapshot[specimen.id] = {
                "run_id": run.id,
                "asset_id": specimen.asset.id,
                "source_sha256": binding.asset_sha256,
                "blob_ref": binding.blob_ref,
                "policy_sha256": digest(policy.model_dump(mode="json")),
                "regions_sha256": digest([r.model_dump(mode="json") for r in regions]),
                "region_ids": [r.id for r in regions],
                "segmentation_sha256": digest(segmentation),
                "dependencies_sha256": digest(run.dependencies),
                "profile_sha256": digest(run.profile_snapshot),
                "reader_cost_micros": prices,
                "max_attempts": policy.max_attempts,
            }
            records[specimen.id] = specimen
        if len(profiles) != 1:
            raise OperationalBlock("pilot_cohort_profile_mismatch")
        return snapshot, records

    def reserve_cohort_readings(self, *, existing_only=False, in_flight=None):
        """One CAS allocates every reader attempt inside existing whole-run holds.

        This is a reservation subdivision, not another charge: runs.cost_micros
        remains the cumulative allocation. No consumed or unknown cost is freed.
        """
        ledger = self._ledger()
        if ledger.get("reading_time_blocker"):
            raise OperationalBlock(ledger["reading_time_blocker"])
        held = ledger.get("reading_cohort")
        if held and held.get("state") == "blocked":
            raise OperationalBlock(held["reason"])
        snapshot, records = self._reading_snapshot(ledger, in_flight=in_flight)
        identity = {
            "version": "cohort-reading-reservation/v1",
            "launch_sha256": self.launch_digest,
            "source_manifest_sha256": self.launch.source_manifest_sha256,
            "scope": self.launch.scope.model_dump(),
            "specimen_ids": list(self.bindings),
            "specimens": snapshot,
        }
        if held:
            if (
                held.get("identity_sha256") != digest(identity)
                or held.get("identity") != identity
                or held.get("state") != "reserved"
            ):
                raise OperationalBlock("pilot_cohort_snapshot_changed")
            for ident, specimen in records.items():
                allocation = held["allocations"][ident]
                prior = allocation["prior_cost_micros"]
                claims = ledger.get("reader_claims", {}).get(ident, {})
                claimed_cost, claimed_attempts = 0, 0
                for step, count in claims.items():
                    parts = step.split(":")
                    if (
                        len(parts) != 3
                        or parts[0] != "transcribe"
                        or parts[1] not in snapshot[ident]["region_ids"]
                        or parts[2] not in snapshot[ident]["reader_cost_micros"]
                        or type(count) not in (int, float)
                        or int(count) != count
                        or not 1 <= count <= snapshot[ident]["max_attempts"]
                        or specimen.run.attempts.get(step, 0) < count
                    ):
                        raise OperationalBlock("pilot_cohort_reader_liability_changed")
                    claimed_attempts += count
                    claimed_cost += (
                        count * snapshot[ident]["reader_cost_micros"][parts[2]]
                    )
                usage = specimen.run.usage
                if (
                    usage.reserved_cost_micros < prior + claimed_cost
                    or usage.reserved_cost_micros
                    > prior + allocation["reading_cost_micros"]
                    or usage.external_calls
                    < allocation["prior_calls"] + claimed_attempts * 2
                    or usage.reserved_tokens
                    < allocation["prior_tokens"] + claimed_attempts * 16000
                ):
                    raise OperationalBlock("pilot_cohort_prior_liability_changed")
            _, time_issue = self._reading_time(ledger, records)
            if time_issue:
                self._write(ledger, reading_time_blocker=time_issue)
                raise OperationalBlock(time_issue)
            return held
        if existing_only:
            raise OperationalBlock("pilot_cohort_reading_reservation_required")
        allocations, total, count, issue = {}, 0, 0, None
        for ident, specimen in records.items():
            run, policy = specimen.run, specimen.run.profile.execution
            item = snapshot[ident]
            # Work before the new barrier is never silently adopted or credited.
            if run.observations or any(
                key.startswith("transcribe:") for key in run.attempts
            ):
                raise OperationalBlock("pilot_cohort_prior_reader_work_unreconciled")
            reads = len(run.regions) * len(item["reader_cost_micros"])
            amount = (
                len(run.regions)
                * sum(item["reader_cost_micros"].values())
                * policy.max_attempts
            )
            prior = run.usage.reserved_cost_micros
            segment_price = (
                policy.stage_cost_reservations.for_step("segment")
                if policy.stage_cost_reservations is not None
                else policy.request_cost_reservation_micros
            )
            segment_attempts = run.attempts.get("segment", 0)
            if (
                not 1 <= segment_attempts <= policy.max_attempts
                or prior < segment_attempts * segment_price
                or run.usage.external_calls < segment_attempts
                or run.usage.reserved_tokens < segment_attempts * 16000
            ):
                raise OperationalBlock(
                    "pilot_cohort_prior_segmentation_liability_changed"
                )
            allocations[ident] = {
                "segmentation_revision": specimen.version,
                "prior_cost_micros": prior,
                "reading_cost_micros": amount,
                "prior_calls": run.usage.external_calls,
                "prior_tokens": run.usage.reserved_tokens,
            }
            total += amount
            count += reads
            if prior + amount > min(
                policy.approved_cost_limit_micros, ledger["runs"][ident]["cost_micros"]
            ):
                issue = "pilot_cohort_reading_budget_insufficient"
            if (
                run.usage.external_calls + reads * policy.max_attempts * 2
                > policy.max_external_calls
                or run.usage.reserved_tokens + reads * policy.max_attempts * 16000
                > policy.max_tokens
                or run.usage.steps + reads * policy.max_attempts > policy.max_steps
                or run.usage.active_seconds
                + run.usage.reserved_active_seconds
                + reads * policy.max_attempts * policy.external_timeout_seconds
                > policy.max_active_seconds
            ):
                issue = issue or "pilot_cohort_reading_capacity_insufficient"
        if (
            sum(row["cost_micros"] for row in ledger["runs"].values())
            > self.launch.total_cost_limit_micros
        ):
            issue = "pilot_cohort_reading_budget_insufficient"
        reading_seconds, time_issue = self._reading_time(ledger, records)
        issue = issue or time_issue
        held = {
            "state": "blocked" if issue else "reserved",
            "identity": identity,
            "identity_sha256": digest(identity),
            "allocations": allocations,
            "reserved_cost_micros": total,
            "reading_count": count,
            "reading_seconds": reading_seconds,
            "region_count": sum(len(s.run.regions) for s in records.values()),
        }
        if issue:
            held["reason"] = issue
        self._write(ledger, reading_cohort=held)
        if issue:
            raise OperationalBlock(issue)
        return held

    def assert_reader_reserved(self, specimen, region, route):
        held = self.reserve_cohort_readings(existing_only=True, in_flight=specimen)
        item = held["identity"]["specimens"][specimen.id]
        if (
            region.id not in item["region_ids"]
            or route not in item["reader_cost_micros"]
            or specimen.run.id != item["run_id"]
        ):
            raise OperationalBlock("pilot_cohort_reader_not_reserved")
        ledger = self._ledger()
        if ledger.get("reading_cohort") != held:
            raise OperationalBlock("pilot_cohort_snapshot_changed")
        step = "transcribe:" + region.id + ":" + route
        count = specimen.run.attempts.get(step, 0)
        claims = {
            ident: dict(values)
            for ident, values in ledger.get("reader_claims", {}).items()
        }
        prior = claims.setdefault(specimen.id, {}).get(step, 0)
        if not 1 <= count <= item["max_attempts"] or count != prior + 1:
            raise OperationalBlock("pilot_cohort_reader_attempt_unreconciled")
        claims[specimen.id][step] = count
        # Claim before the paid boundary. A lost response retains the claim and
        # the original full hold; neither can authorize a replay after restart.
        self._write(ledger, reader_claims=claims)


def verify_source_manifest(path: Path, launch: PilotLaunch):
    """Apply the same strict ready-ten schema at worker and SAM admission."""
    from .private_config import read_private
    from .sam3_server import PilotManifest

    try:
        raw = read_private(path)
        if hashlib.sha256(raw).hexdigest() != launch.source_manifest_sha256:
            raise OperationalBlock("pilot_source_manifest_digest_mismatch")
        manifest = PilotManifest.model_validate_json(raw)
        actual = [
            PilotSpecimen(
                specimen_id=item.specimen_id,
                asset_sha256=item.application_source.sha256,
                blob_ref=item.application_source.blob_ref,
            )
            for item in manifest.specimens
        ]
        if (
            actual != launch.specimens
            or manifest.authorization_reference != launch.authorization_reference
            or any(
                item.organization_id != launch.scope.organization_id
                or item.collection_id != launch.scope.collection_id
                for item in manifest.specimens
            )
        ):
            raise ValueError("Source binding mismatch")
        return manifest
    except (OSError, ValueError):
        raise OperationalBlock(
            "pilot_source_manifest_not_ready_or_mismatched"
        ) from None


def sam3_expectations(manifest, launch, output_bucket):
    if not launch.sam3_checkpoint_files:
        raise OperationalBlock("sam3_checkpoint_pins_required")
    return {
        item.specimen_id: {
            "manifest_sha256": launch.source_manifest_sha256,
            "source": item.source_objects[
                item.application_source.source_object_index
            ].model_dump(),
            "output_bucket": output_bucket,
            "checkpoint_files": launch.sam3_checkpoint_files,
        }
        for item in manifest.specimens
    }
