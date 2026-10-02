"""Use the native registered research lane at the ordinary post-parse boundary."""
from __future__ import annotations

import asyncio
from uuid import uuid4

from specimen_digitization.application.workflow import OperationalBlock
from .native_worker import NativeResearchWorker
from .production_runtime import NativeResearchRuntimeFactory
from .persistence import HeldUnknown, StaleWork


class NativeResearchWorkflow:
    def __init__(self, ordinary, native_worker, *, approved_specimen_ids):
        self.ordinary, self.native_worker = ordinary, native_worker
        self.approved_specimen_ids = frozenset(approved_specimen_ids)
        if len(self.approved_specimen_ids) != 10:
            raise ValueError("native_research_requires_exact_existing_ten")
        self.owner = "native-research-worker:" + uuid4().hex

    def __getattr__(self, name):
        return getattr(self.ordinary, name)

    def step(self, principal, specimen_id):
        specimen = self.ordinary.repository.get(principal.scope, specimen_id)
        if specimen_id not in self.approved_specimen_ids:
            raise PermissionError("native_research_outside_approved_cohort")
        if specimen.run.stage in {"finalized", "paused", "cancelled", "processing_blocked"}:
            return specimen
        if "evidence_pilot" in specimen.run.dependencies:
            raise OperationalBlock("native_research_evidence_pilot_not_composed")
        # Intake, classifier, SAM and original transcription remain the exact
        # ordinary producer path. Ordinary narrow parsing also retains genuine native literal Evidence.
        # Native research replaces the legacy plan/lookup chain only after
        # that immutable source graph and canonical base are registered.
        if self.ordinary.next_step(specimen.run) != "plan":
            return self.ordinary.step(principal, specimen_id)
        if self.ordinary.admission is None:
            raise OperationalBlock("native_research_launch_admission_required")
        self.ordinary.admission.admit(specimen)
        from specimen_digitization.application.worker_deadline import current_deadline
        deadline = current_deadline()
        if deadline is None:
            raise OperationalBlock("native_research_worker_supervisor_required")
        deadline.check()
        try:
            outcome = asyncio.run(self.native_worker.run_registered(
                principal, specimen_id, owner=self.owner))
        except (PermissionError, HeldUnknown, StaleWork):
            raise OperationalBlock("native_research_admission_or_binding_unavailable") from None
        deadline.check()
        if outcome.status == "blocked":
            raise OperationalBlock(outcome.reason_code or "native_research_operational_hold")
        # Canonical save/reopen uses the existing repository and native pointer;
        # the research layer never manufactures a second Specimen/save writer.
        return self.ordinary.repository.get(principal.scope, specimen_id)


def compose_native_research_workflow(ordinary, *, repository, admission,
                                    registry, request_factory, materializer,
                                    evidence_provider, projection_services, verify_access,
                                    actual_cost, blobs=None, limits=None):
    if admission is not ordinary.admission:
        raise ValueError("ordinary_launch_admission_mismatch")
    factory = NativeResearchRuntimeFactory(repository, registry=registry,
        request_factory=request_factory, materializer=materializer,
        evidence_provider=evidence_provider, projection_services=projection_services,
        verify_access=verify_access, actual_cost=actual_cost, blobs=blobs, limits=limits)
    return NativeResearchWorkflow(ordinary, NativeResearchWorker(factory),
        approved_specimen_ids=tuple(admission.bindings))


def compose_registered_native_workflow(ordinary, *, repository, admission):
    """Mount the concrete native factory in the ordinary supervised worker.

    Fresh membership and sensitivity are rechecked by the same native authority
    used for API reads. The existing admission, ten IDs and deadline remain.
    """
    if admission is not ordinary.admission or admission.launch.evidence_only:
        raise ValueError("native_research_requires_ordinary_live_admission")

    async def verify_access(principal, sensitive):
        memberships = await asyncio.to_thread(repository.memberships, principal.user_id)
        matching = [row for row in memberships
            if row.get("organization_id") == principal.scope.organization_id
            and row.get("collection_id") == principal.scope.collection_id]
        if (len(matching) != 1 or matching[0].get("role") != principal.role
            or principal.role not in {"operator", "reviewer", "manager", "admin"}
            or sensitive is not False and matching[0].get("can_view_sensitive") is not True):
            raise PermissionError("research_worker_access_denied")

    factory = NativeResearchRuntimeFactory(repository, verify_access=verify_access)
    return NativeResearchWorkflow(ordinary, NativeResearchWorker(factory),
        approved_specimen_ids=tuple(admission.bindings))
