"""Private, digest-pinned admission contract for the ten-specimen pilot.

The data owner's frozen source manifest and this post-import binding are separate:
this contract never discovers, downloads, or imports cloud objects.
"""

from datetime import datetime, timezone, timedelta
import hashlib
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5, uuid4

from pydantic import Field, model_validator

from .domain import Record, Scope
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

    def binding_matches(self, specimen):
        binding = self.bindings.get(specimen.id)
        return bool(
            binding is not None
            and specimen.scope == self.launch.scope
            and specimen.asset.sha256 == binding.asset_sha256
            and specimen.asset.blob_ref == binding.blob_ref
            and not specimen.run.profile.synthetic
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
        if value["launch_sha256"] != self.launch_digest:
            raise OperationalBlock("pilot_launch_changed_requires_reconciliation")
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
        if not self.binding_matches(specimen):
            raise OperationalBlock("pilot_specimen_binding_mismatch")
        policy = run.profile.execution
        if (
            self.clock() + timedelta(seconds=policy.external_timeout_seconds + 5)
            >= launch.expires_at
        ):
            raise OperationalBlock("pilot_launch_deadline_reached")
        if (
            policy.approved_cost_limit_micros is None
            or policy.approved_cost_limit_micros <= 0
            or policy.approved_cost_limit_micros > launch.per_specimen_cost_limit_micros
            or policy.request_cost_reservation_micros is None
            or policy.request_cost_reservation_micros <= 0
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
