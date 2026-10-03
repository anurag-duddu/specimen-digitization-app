"""Registered native post-parse drain, using the existing canonical writer.

The drain CLI mounts it only when SPECIMEN_RESEARCH_HARNESS is on. The CLI
currently has no protected installed original-ten/program admission. It
therefore refuses before fencing or any ordinary paid effect. An existing
admission object is not enough by itself: each actual native binding must also
pass the current ResearchStore protected authority gate before an ordinary step.
No new launch file, registration, allowance, import proof or price is invented.
"""
from __future__ import annotations

import asyncio

from .workflow import OperationalBlock
from .worker_deadline import current_deadline, deadline_call
from ..research_harness.persistence import HeldUnknown, StaleWork
from ..research_harness.workflow_bridge import compose_registered_native_workflow


class RegisteredNativeDrainWorkflow:
    def __init__(self, workflow):
        self.workflow = workflow
        self.admission = workflow.ordinary.admission
        self.repository = workflow.ordinary.repository

    def __getattr__(self, name):
        return getattr(self.workflow, name)

    def step(self, principal, specimen_id):
        deadline = current_deadline()
        if deadline is None:
            raise OperationalBlock("native_research_worker_supervisor_required")
        deadline.check()
        if specimen_id not in self.workflow.approved_specimen_ids:
            raise PermissionError("native_research_outside_approved_cohort")
        specimen = deadline_call(self.repository.get, principal.scope, specimen_id)
        # Original immutable image/run identity and expiry, not newest row order.
        self.admission.admit(specimen)
        try:
            asyncio.run(self._admit_native(principal, specimen_id))
        except (PermissionError, HeldUnknown, StaleWork):
            raise OperationalBlock("native_drain_protected_admission_unavailable") from None
        deadline.check()
        # NativeResearchWorkflow keeps genuine ordinary segmentation/readings/
        # parsing; only its existing plan boundary enters the registered Harness.
        return self.workflow.step(principal, specimen_id)

    async def _admit_native(self, principal, specimen_id):
        factory = self.workflow.native_worker.runtime_factory
        binding = await factory.discovery.binding(principal, specimen_id)
        bound = binding.durability_scope(principal)
        store = factory.discovery.mutable_store(binding)
        await asyncio.to_thread(store.require_live_authority, bound)
        budget = await asyncio.to_thread(store.budget, bound)
        remaining = budget.get("remaining_micro_usd")
        if type(remaining) is not int or remaining <= 0:
            raise HeldUnknown("research_program_headroom_unavailable")


def compose_registered_native_drain(ordinary, *, repository):
    """Mount the actual factory only with protected existing-ten admission.

    No such admission is currently installed in the direct drain. Hold before
    any collection fence or paid step. The legacy balance reader is not this
    admission, and BudgetPolicy.live_authorized is not installation proof.
    """
    admission = ordinary.admission
    if admission is None:
        raise OperationalBlock("legacy_import_protected_authority_origin_unavailable")
    if len(admission.bindings) != 10 or admission.launch.evidence_only:
        raise OperationalBlock("native_drain_original_ten_admission_required")
    workflow = compose_registered_native_workflow(
        ordinary, repository=repository, admission=admission)
    return RegisteredNativeDrainWorkflow(workflow)
