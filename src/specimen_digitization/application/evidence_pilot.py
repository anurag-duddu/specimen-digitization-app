"""Explicit evidence-only lane; never publishes draft policy or calls finalize.

Admission, source identity, bounded effects, SQL CAS and reservations are shared
with the production worker. Only orchestration is narrower: SAM and two blind
readings, followed by a durable review block. No classification/risk authority is
invented to make an institutional workflow pass.
"""

import hashlib
import os
from pathlib import Path

from .collection_profiles import CollectionProfile
from .domain import AuditEvent, Profile, Transcript
from .production import ProductionAdapters, Sam3Service
from .storage import digest
from .workflow import OperationalBlock, Workflow
from ..model_gateway import INITIAL_HUGGINGFACE_ROUTES


def read_evidence_profile(path: Path, expected_sha256: str) -> CollectionProfile:
    from .private_config import read_private

    try:
        raw = read_private(path)
    except (OSError, ValueError):
        raise OperationalBlock("pilot_private_profile_required") from None
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise OperationalBlock("pilot_profile_digest_mismatch")
    try:
        profile = CollectionProfile.model_validate_json(raw)
    except ValueError:
        raise OperationalBlock("pilot_profile_invalid") from None
    if (
        profile.state != "draft"
        or profile.synthetic
        or profile.institutional_policy_approved
        or profile.semantics_confirmed
        or profile.segmentation_settings is None
        or tuple(profile.model_routes) != tuple(INITIAL_HUGGINGFACE_ROUTES)
    ):
        raise OperationalBlock("pilot_requires_explicit_unapproved_draft_profile")
    return profile


class EvidencePilotAdapters:
    """Expose only SAM and independent transcription, never extraction/tools."""

    def __init__(self, production, settings):
        self.production, self.settings = production, settings
        self.blobs = production.blobs
        self.classifier = None
        self.authority_tools = {}
        self.authority_cost_reservations = {}

    def pin_dependencies(self, run):
        return self.production.pin_dependencies(run)

    def segment(self, specimen):
        if (
            os.getenv("SPECIMEN_APPROVED_EVIDENCE_PILOT") != "true"
            or os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true"
        ):
            raise OperationalBlock("evidence_pilot_approval_required")
        if not specimen.run.dependencies.get("evidence_pilot"):
            raise OperationalBlock("evidence_pilot_binding_required")
        endpoint = specimen.run.dependencies["segmentation"]["endpoint"]
        return Sam3Service(
            endpoint,
            self.blobs,
            expected=self.production.sam3_expected.get(specimen.id),
        )._segment_with_settings(specimen, self.settings)

    def transcribe(self, specimen, region, route):
        return self.production.transcribe(specimen, region, route)


class EvidencePilotWorkflow(Workflow):
    evidence_pilot = True

    def __init__(
        self, repository, blobs, admission, profile, *, production=None, **kwargs
    ):
        if not admission.launch.evidence_only:
            raise OperationalBlock("evidence_pilot_not_authorized_in_launch")
        self.pilot_profile = profile
        adapters = EvidencePilotAdapters(
            production or ProductionAdapters(blobs), profile.segmentation_settings
        )
        super().__init__(repository, blobs, adapters, admission=admission, **kwargs)

    @staticmethod
    def next_step(run):
        for step in ("quality_check", "segment"):
            if step not in run.completed_steps:
                return step
        for region in run.regions:
            for route in run.profile.routes:
                step = f"transcribe:{region.id}:{route}"
                if step not in run.completed_steps:
                    return step
        return "pilot_review"

    def step(self, principal, specimen_id):
        if (
            os.getenv("SPECIMEN_APPROVED_EVIDENCE_PILOT") != "true"
            or os.getenv("SPECIMEN_APPROVED_INFERENCE") != "true"
        ):
            raise OperationalBlock("evidence_pilot_approval_required")
        specimen = self.repository.get(principal.scope, specimen_id)
        self.admission.admit(specimen)
        run = specimen.run
        profile = self.pilot_profile
        if specimen.asset.processing_derivative is not None:
            raise OperationalBlock("pilot_original_pixels_required")
        if profile.collection_id != principal.scope.collection_id:
            raise OperationalBlock("pilot_profile_scope_mismatch")
        marker = run.dependencies.get("evidence_pilot")
        if "evidence_pilot" not in run.dependencies:
            if (
                run.completed_steps
                or run.observations
                or run.regions
                or run.usage.external_calls
                or run.stage != "ingested"
            ):
                raise OperationalBlock("pilot_requires_pristine_authorized_run")
            run.profile_snapshot = profile.model_dump(mode="json")
            run.profile_registry_version = "evidence-pilot-unpublished"
            run.profile = Profile(
                **dict(
                    run.profile.model_dump(),
                    id=profile.id,
                    version=profile.version,
                    schema_version=profile.schema_version,
                    mandatory_fields=profile.mandatory_fields,
                    routes=profile.model_routes,
                    institutional_policy_approved=False,
                    semantics_confirmed=False,
                    language_handling=profile.language_handling.model_dump(),
                ),
            )
            # This records settings, not resolved profile rules or active risk policy.
            run.profile_rules = {}
            run.risk_policy_snapshot = {
                "status": "blocked",
                "reference": None,
                "registry_version": "unconfigured-risk-registry",
                "reason": "pilot_risk_unmeasured",
            }
            run.review_risk = {
                "status": "unmeasured",
                "reason": "pilot_risk_unmeasured",
            }
            run.dependencies = self.adapters.pin_dependencies(run)
            marker = {
                "version": "evidence-pilot-v1",
                "launch_sha256": self.admission.launch_digest,
                "source_manifest_sha256": self.admission.launch.source_manifest_sha256,
                "profile_sha256": self.admission.launch.evidence_profile_sha256,
                "runtime_pins_sha256": digest(run.dependencies),
            }
            run.dependencies["evidence_pilot"] = marker
            run.completed_steps = ["pin_dependencies"]
            run.human_approved = False
            run.disposition = None
            specimen.audit.append(
                AuditEvent(
                    actor=principal.user_id,
                    action="begin_evidence_pilot",
                    reason="Authorized ten-specimen evidence capture; risk unmeasured and clearance disabled",
                )
            )
            return self.repository.save(
                principal,
                specimen,
                specimen.version,
                "pilot-init:" + run.id,
                digest(marker),
            )
        expected = {
            "version": "evidence-pilot-v1",
            "launch_sha256": self.admission.launch_digest,
            "source_manifest_sha256": self.admission.launch.source_manifest_sha256,
            "profile_sha256": self.admission.launch.evidence_profile_sha256,
            "runtime_pins_sha256": digest(self.adapters.pin_dependencies(run)),
        }
        retained_pins = {
            k: v for k, v in run.dependencies.items() if k != "evidence_pilot"
        }
        if (
            run.stage == "finalized"
            or marker != expected
            or digest(retained_pins) != marker["runtime_pins_sha256"]
            or run.profile_snapshot != profile.model_dump(mode="json")
            or run.profile_rules
            or run.risk_policy_snapshot.get("status") != "blocked"
            or run.profile.institutional_policy_approved
            or run.profile.semantics_confirmed
            or run.human_approved
            or run.disposition is not None
        ):
            raise OperationalBlock("pilot_pinned_evidence_configuration_changed")
        if run.stage in {"processing_blocked", "paused", "cancelled"}:
            return specimen
        if self.next_step(run) == "pilot_review":
            run.stage = "processing_blocked"
            run.blocker = "pilot_evidence_review_required"
            run.disposition = None
            run.transcripts = [
                Transcript(
                    region_id=region.id,
                    text=None,
                    resolved=False,
                    observation_ids=[
                        o.id for o in run.observations if o.region_id == region.id
                    ],
                    alternatives=list(
                        dict.fromkeys(
                            o.literal_text
                            for o in run.observations
                            if o.region_id == region.id
                        )
                    ),
                    alignment_status="policy_blocked",
                    alignment_reasons=["pilot_risk_unmeasured"],
                )
                for region in run.regions
            ]
            run.coverage_confirmed = False
            run.human_approved = False
            run.reasons = ["pilot_risk_unmeasured", "institutional_policy_not_approved"]
            specimen.audit.append(
                AuditEvent(
                    actor=principal.user_id,
                    action="evidence_pilot_review_required",
                    reason="Raw segmentation and independent readings retained; no parsed or cleared result",
                )
            )
            return self.repository.save(
                principal,
                specimen,
                specimen.version,
                "pilot-review:" + run.id,
                digest(marker),
            )
        return super().step(principal, specimen_id)
