"""Use the native registered research lane at the ordinary post-parse boundary.

SPECIMEN_RESEARCH_HARNESS=on mounts the research harness over the ordinary
chain. A run whose pinned profile names a harness route then replaces the
ordinary plan/lookup chain with the six research roles; any other run, and every
run while the switch is off, keeps the ordinary chain.
"""
from __future__ import annotations

import asyncio
import functools
import os
from uuid import uuid4

from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.application.storage import ReviewDecisionProof, digest as snapshot_digest
from .committed_pins import committed_harness_route
from .enablement import research_harness_enabled
from .native_worker import NativeResearchWorker
from .persistence import HeldUnknown, LiveResearchAuthority, StaleWork
from .production_runtime import NativeResearchRuntimeFactory

WORKER_ROLES = {"operator", "reviewer", "manager", "admin"}
# Refusals that concern this run alone: its job was pinned before the committed
# pins changed (a job is never re-pinned), provisioning refused the run, the
# run's research state or job exists with other pins or allowance, the
# connector refused this specimen's binding row, or the run's own research
# allowance (one state document per run) is halted or spent. Each keeps its own
# code, which the drain holds as that record's (lane_worker.RECORD_HOLDS).
# Every other refusal (switch, worker actor, membership, configuration, storage)
# is one code that ends the drain's execution.
RECORD_REFUSALS = frozenset({
    "research_committed_pins_changed",
    "research_live_admission_unqualified",
    "research_program_headroom_unavailable",
    "research_provision_registration_refused",
    "research_provision_run_unavailable",
    "research_provision_state_conflict",
})


class NativeResearchWorkflow:
    def __init__(self, ordinary, native_worker, *, provision=None):
        self.ordinary, self.native_worker, self.provision = ordinary, native_worker, provision
        self.owner = "native-research-worker:" + uuid4().hex
        self._completed_side_work = None

    def __getattr__(self, name):
        return getattr(self.ordinary, name)

    def step(self, principal, specimen_id):
        self._completed_side_work = None
        specimen = self.ordinary.repository.get(principal.scope, specimen_id)
        if "research_derivation_request" in specimen.run.dependencies:
            from .derivation_contracts import DerivationCommand
            try:
                command = DerivationCommand.model_validate(specimen.run.dependencies["research_derivation_request"])
            except ValueError:
                raise OperationalBlock("research_derivation_requires_reconciliation") from None
            # A later ordinary human save retires the old scheduling metadata.
            # Retained historical commands cannot intercept that later work.
            if command.queued_revision == specimen.version and command.canonical_run_id == specimen.run.id:
                return self._derivation_step(principal, specimen)
        if (specimen.run.stage == "processing_blocked" and self.ordinary.next_step(specimen.run) == "plan"
                and committed_harness_route(specimen.run.profile_snapshot) is not None):
            try:
                command = asyncio.run(self._retry_command_for_step(principal, specimen))
            except (PermissionError, HeldUnknown, StaleWork):
                raise OperationalBlock("research_retry_requires_reconciliation") from None
            if command is not None:
                return self._retry_step(principal, specimen, command["id"])
        if specimen.run.stage in {"finalized", "paused", "cancelled", "processing_blocked"}:
            return specimen
        if "evidence_pilot" in specimen.run.dependencies:
            raise OperationalBlock("native_research_evidence_pilot_not_composed")
        # Intake, classifier, SAM, transcription and parsing stay on the
        # ordinary path, and so does a run whose profile names no harness route.
        # Native research replaces the plan/lookup chain for the others.
        if (self.ordinary.next_step(specimen.run) != "plan"
                or committed_harness_route(specimen.run.profile_snapshot) is None):
            return self.ordinary.step(principal, specimen_id)
        from specimen_digitization.application.worker_deadline import current_deadline
        deadline = current_deadline()
        if deadline is None:
            raise OperationalBlock("native_research_worker_supervisor_required")
        deadline.check()
        try:
            outcome = asyncio.run(self._research(principal, specimen))
            if (outcome.status == "blocked" and outcome.reason_code is None
                    and outcome.publication_receipt_ids):
                published = asyncio.run(self._published_field_hold(principal, specimen, outcome))
                if published is not None:
                    deadline.check()
                    return published
        except (PermissionError, HeldUnknown, StaleWork) as error:
            if str(error) in RECORD_REFUSALS:
                raise OperationalBlock(str(error)) from None
            raise OperationalBlock("native_research_admission_or_binding_unavailable") from None
        deadline.check()
        if outcome.status == "blocked":
            raise OperationalBlock(outcome.reason_code or "native_research_operational_hold")
        # Each publication saves the specimen through the native writer; the
        # research layer never manufactures a second Specimen/save writer.
        return self.ordinary.repository.get(principal.scope, specimen_id)

    async def _retry_command_for_step(self, principal, specimen):
        from .retry_work_queue import queued_retry_command, START_RECEIPT_ATTEMPTS, START_RECEIPT_INTERVAL_SECONDS
        from specimen_digitization.application.worker_deadline import current_deadline
        # A fast worker may read before the API stores the actual start receipt.
        # Wait only for that receipt; elapsed time never grants send authority.
        for attempt in range(START_RECEIPT_ATTEMPTS):
            binding = await self.native_worker.runtime_factory.discovery.binding(principal, specimen.id)
            sending = any(event.get("kind") == "research_field_retry" and event.get("delivered") is False
                and event.get("command", {}).get("scope") == binding.durability_scope(principal).identity()
                and event["command"].get("dispatch_status") == "sending"
                for event in binding.read_bundle.outbox.values())
            deadline = current_deadline()
            if sending and attempt < START_RECEIPT_ATTEMPTS - 1 and deadline is not None:
                deadline.check()
                await asyncio.sleep(START_RECEIPT_INTERVAL_SECONDS)
                continue
            return queued_retry_command(binding, principal, specimen, consuming=True)

    def _retry_step(self, principal, specimen, command_id):
        from specimen_digitization.application.worker_deadline import current_deadline
        deadline = current_deadline()
        if deadline is None:
            raise OperationalBlock("native_research_worker_supervisor_required")
        deadline.check()
        try:
            outcome = asyncio.run(self._research(principal, specimen, retry_command_id=command_id))
            current = self.ordinary.repository.get(principal.scope, specimen.id)
            if outcome.reason_code is not None:
                binding = asyncio.run(self.native_worker.runtime_factory.discovery.binding(principal, specimen.id))
                from .retry_work_queue import park_research_retry
                current = park_research_retry(self.ordinary.repository, principal, binding, command_id, outcome)
                self._completed_side_work = snapshot_digest(current.model_dump(mode="json"))
            elif current.run.stage in {"finalized", "processing_blocked"}:
                binding = asyncio.run(self.native_worker.runtime_factory.discovery.binding(principal, specimen.id))
                from .retry_work_queue import finish_research_retry
                current = finish_research_retry(self.ordinary.repository, principal, binding, command_id, outcome)
                self._completed_side_work = snapshot_digest(current.model_dump(mode="json"))
        except Exception:
            # Retry custody, source cost and publication uncertainty cannot be
            # erased by the drain's administrative lane_block snapshot writer.
            raise OperationalBlock("research_retry_requires_reconciliation") from None
        deadline.check()
        return current

    async def _published_field_hold(self, principal, before, outcome):
        """Keep a proved native blocked save current, without an administrative save.

        Field/source/policy holds are already in that publication's progress.
        An extra lane_block would advance Q outside its native receipt chain and
        make the report unavailable. A status string alone is not this proof.
        Explicit operational failures still take the existing exception path.
        """
        from .canonical_binding import BindingUnavailable
        from .compatibility import PublicationUnavailable
        from .discovery_v2 import CanonicalReadBindingV2

        try:
            binding = await self.native_worker.runtime_factory.discovery.binding(principal, before.id)
        except (BindingUnavailable, PublicationUnavailable):
            raise StaleWork("research_published_hold_unproved") from None
        if not isinstance(binding, CanonicalReadBindingV2):
            return None
        native, bundle = binding.native, binding.read_bundle
        # These blocked states are failures or unfinished retries, not source
        # or policy questions. The current job can be newer than its last save.
        operational_states = {"operational_failed", "cancelled", "retry_scheduled"}
        if (binding.research_scope() != outcome.scope or not native.causal_chain
                or str(native.head_receipt_id) not in outcome.publication_receipt_ids
                or str(native.canonical.canonical_run_id) != before.run.id
                or bundle.halted or bundle.paused or bundle.hold_reasons
                or bundle.job.get("lease") is not None
                or any(field.get("work_state") in operational_states
                    for field in bundle.job["fields"].values())
                or any(effect.get("status") in {"reserved", "sending", "held_unknown"}
                    or effect.get("actual_micro_usd") is None for effect in bundle.effects.values())):
            return None
        head = native.causal_chain[-1]
        progress = head.progress_receipt
        # Progress calls even scientific field waits "operational" reasons.
        # Allow only those exact waits; retain real lookup/grounding failures.
        field_holds = {f"research_work:{key}:{state}"
            for key, state in progress.canonical_field_work.items()
            if state in {"waiting_source", "waiting_policy"}}
        if (set(progress.operational_reason_codes) - field_holds
                or operational_states.intersection(progress.research_field_work.values())
                or operational_states.intersection(progress.canonical_field_work.values())):
            return None
        current = await asyncio.to_thread(self.ordinary.repository.get, principal.scope, before.id)
        info = await asyncio.to_thread(self.ordinary.repository.version_info,
            principal.scope, current.id, current.version)
        if (current.id != before.id or current.scope != principal.scope
                or current.run.id != before.run.id or current.version <= before.version
                or current.version != native.canonical.record_revision
                or current.asset.sha256 != binding.source_sha256 or current.asset.sensitive is not native.sensitive
                or current.run.stage != "processing_blocked" or current.run.disposition is not None
                or current.run.blocker is not None or head.receipt_id != native.head_receipt_id
                or head.actor_uid != principal.user_id
                or head.resulting != native.canonical or progress.run_stage != "processing_blocked"
                or progress.wire_status != "processing_blocked" or progress.disposition is not None
                or progress.exportable or info.get("revision") != current.version
                or info.get("run_id") != current.run.id
                or info.get("sha256") != native.canonical.snapshot_sha256
                or info.get("run_sha256") != snapshot_digest(current.run.model_dump(mode="json"))):
            return None
        # The actual native save advanced Q, so the drain already sees progress.
        # No metadata-only completion or queue retirement needs to be invented.
        return current

    def completed_side_work(self, specimen):
        """Only this step's proved metadata completion counts without a save."""
        return self._completed_side_work == snapshot_digest(specimen.model_dump(mode="json"))

    def _derivation_step(self, principal, specimen):
        from specimen_digitization.application.worker_deadline import current_deadline
        deadline = current_deadline()
        if deadline is None:
            raise OperationalBlock("native_research_worker_supervisor_required")
        deadline.check()
        try:
            if (specimen.run.stage in {"paused", "cancelled", "processing_blocked"}
                or "evidence_pilot" in specimen.run.dependencies):
                raise StaleWork("derivation_lifecycle_unavailable")
            completed = asyncio.run(self._derive(principal, specimen))
        except Exception:
            # This is deliberately outside RECORD_HOLDS: neither an unknown
            # side-work outcome nor its queue status may cause a canonical
            # lane-block save that would invalidate Q or erase its custody.
            raise OperationalBlock("research_derivation_requires_reconciliation") from None
        deadline.check()
        self._completed_side_work = snapshot_digest(completed.model_dump(mode="json"))
        return self.ordinary.repository.get(principal.scope, specimen.id)

    @staticmethod
    def _prove_derivation_enqueue(repository, principal, specimen, command):
        """Require the original authenticated reviewer save, not audit text."""
        proofs, _ = repository._review_proofs(principal.scope, specimen)
        info = repository.version_info(principal.scope, specimen.id, command.queued_revision)
        expected_before = {"revision": command.source_revision, "run_id": command.canonical_run_id}
        expected_after = {"request_id": command.id, "input_digest": command.input_digest,
            "requested_fields": [str(key) for key in command.requested_fields]}
        matches = [proof for proof in proofs if isinstance(proof, ReviewDecisionProof)
            and proof.specimen_id == specimen.id and proof.base_revision == command.source_revision
            and proof.resulting_revision == command.queued_revision
            and proof.prior_sha256 == command.source_snapshot_sha256
            and proof.snapshot_sha256 == info.get("sha256") and proof.server_audit_id
            and proof.event.action == "review_derive_rest" and proof.event.actor == command.actor_uid
            and proof.event.reason == command.reason and proof.event.before == expected_before
            and proof.event.after == expected_after]
        if (info.get("revision") != command.queued_revision
            or info.get("run_id") != command.canonical_run_id or len(matches) != 1):
            raise StaleWork("derivation_enqueue_provenance_unproved")

    async def _derive(self, principal, specimen):
        from .derivation_worker import ResearchDerivationWorker
        from .derivation_work_queue import finish_derivation
        from .contracts import digest

        repository = self.ordinary.repository
        factory = self.native_worker.runtime_factory
        worker = ResearchDerivationWorker(factory, input_blobs=repository.graph_blobs)
        # Fresh typed command/Q/run/input proof verification happens before
        # provisioning, and again inside the worker before each captured send.
        context = await asyncio.to_thread(worker._verify, principal, specimen.id)
        command, current = context.command, context.specimen
        await asyncio.to_thread(self._prove_derivation_enqueue, repository, principal, current, command)
        if self.provision is None:
            raise StaleWork("derivation_provisioner_unavailable")
        await self.provision(principal, current)
        outcome = await worker.run_registered(principal, current.id, owner=self.owner, command=command)
        if outcome.request_id != command.id or outcome.status not in {"completed", "blocked"}:
            raise HeldUnknown("derivation_completion_unproved")
        binding, store, scope, _, job = await factory.discovery.bound_state(principal, current.id)
        if (binding.canonical.record_revision != command.queued_revision
            or str(binding.canonical.canonical_run_id) != command.canonical_run_id
            or job["dependencies"].get("derivation_request_id") != command.id
            or digest(job["dependencies"].get("derivation_result")) != digest(outcome.model_dump(mode="json"))):
            raise StaleWork("derivation_completion_unproved")
        # The helper verifies affected-count=1 and native readback of the same
        # Q/run with completed metadata and no due time. No scientific save.
        await asyncio.to_thread(finish_derivation, repository, principal, current, command, scope, store.program_key)
        return current

    async def _research(self, principal, specimen, *, retry_command_id=None):
        if self.provision is not None:
            # Program state, job and canonical binding for this run; idempotent.
            await self.provision(principal, specimen)
        return await self.native_worker.run_registered(principal, specimen.id, owner=self.owner,
            **({"retry_command_id": retry_command_id} if retry_command_id is not None else {}))


def membership_verifier(repository):
    """Fresh membership check: one active operator+ row in the principal's scope."""
    async def verify_access(principal, sensitive):
        memberships = await asyncio.to_thread(repository.memberships, principal.user_id)
        matching = [row for row in memberships
            if row.get("organization_id") == principal.scope.organization_id
            and row.get("collection_id") == principal.scope.collection_id]
        if (len(matching) != 1 or matching[0].get("role") != principal.role
            or principal.role not in WORKER_ROLES
            or sensitive is not False and matching[0].get("can_view_sensitive") is not True):
            raise PermissionError("research_worker_access_denied")
    return verify_access


def worker_actor(actor_uid=None):
    """The worker actor: the configured one, else the verified actor context."""
    from specimen_digitization.application.production import actor_uid as verified
    expected = actor_uid if actor_uid is not None else verified.get()
    if not isinstance(expected, str) or not expected or verified.get() != expected:
        raise PermissionError("research_worker_actor_required")
    return expected


async def authorize_live_research(principal, specimen, binding, *, actor_uid, environ,
                                  verify_access) -> LiveResearchAuthority:
    """The only builder of a live research authority, rechecked at every open."""
    if not research_harness_enabled(environ):
        raise PermissionError("research_harness_switch_off")
    if principal.user_id != worker_actor(actor_uid):
        raise PermissionError("research_worker_actor_required")
    route = committed_harness_route(specimen.run.profile_snapshot)
    if route is None:
        raise PermissionError("research_profile_harness_disabled")
    if (binding.canonical.sensitive is not False or specimen.asset.sensitive is not False
            or specimen.id != binding.canonical.specimen_id
            or specimen.run.id != str(binding.base_canonical.canonical_run_id)):
        raise PermissionError("research_binding_scope_denied")
    await verify_access(principal, False)
    return LiveResearchAuthority(principal.scope.organization_id, principal.scope.collection_id,
        specimen.id, principal.user_id, route, switch_on=True)


def compose_production_research_workflow(ordinary, *, repository, environ, actor_uid=None,
        provision=None, state_backend=None, model_factory=None, source_transport=None,
        blobs=None, request_factory=None, registry=None, limits=None):
    """Mount the research harness over the ordinary workflow.

    The switch must be on. The actor is ``actor_uid``, else the verified actor
    context the worker sets. ``provision`` defaults to the production
    provisioner; the remaining keywords replace production services in tests.
    """
    if not research_harness_enabled(environ):
        raise ValueError("research_harness_switch_off")
    if limits is None:
        from .agents import HarnessLimits
        # The observed geography role reached its third model turn 87.7s in,
        # but the generic 120s wall clock cancelled it before validation.
        # The final call settled 3.5s after cancellation. 240s admits one
        # full 120s provider call after that observed start plus a finite
        # validation/journal margin, below the existing 900s lease and
        # 3300s worker drain.
        # This production-only bound leaves per-model, tool, request, cost,
        # lease and outer worker deadlines unchanged. Explicit fixture limits
        # and direct harness defaults retain their existing values.
        limits = HarnessLimits(run_timeout_seconds=240)
    verify_access = membership_verifier(repository)
    from .program_budget import (
        research_liability_micros, reserve_ordinary_liability, settle_ordinary_liability,
    )
    from .persistence import BudgetExceeded

    def retained_cost(principal, specimen):
        if committed_harness_route(specimen.run.profile_snapshot) is None:
            return 0
        return research_liability_micros(repository, principal, specimen,
            state_backend=state_backend)

    ordinary.retained_cost = retained_cost

    def reserve_retained_cost(principal, specimen, step, cost):
        if committed_harness_route(specimen.run.profile_snapshot) is None:
            return
        try:
            reserve_ordinary_liability(repository, principal, specimen, step, cost,
                state_backend=state_backend)
        except BudgetExceeded:
            raise OperationalBlock("cost_budget_exhausted") from None
        except HeldUnknown:
            raise OperationalBlock("research_budget_state_unavailable") from None

    ordinary.reserve_retained_cost = reserve_retained_cost

    def settle_retained_cost(principal, specimen, step):
        if committed_harness_route(specimen.run.profile_snapshot) is None:
            return
        settle_ordinary_liability(repository, principal, specimen, step,
            state_backend=state_backend)

    ordinary.settle_retained_cost = settle_retained_cost

    async def authorize(principal, specimen, binding):
        return await authorize_live_research(principal, specimen, binding,
            actor_uid=actor_uid, environ=environ, verify_access=verify_access)

    factory = NativeResearchRuntimeFactory(repository, verify_access=verify_access,
        authorize=authorize, state_backend=state_backend, model_factory=model_factory,
        source_transport=source_transport, blobs=blobs, request_factory=request_factory,
        registry=registry, limits=limits)
    if provision is None:
        from .provisioning import provision as provision_run
        provision = functools.partial(provision_run, repository, actor_uid=actor_uid,
            verify_access=verify_access, state_backend=state_backend)
    return NativeResearchWorkflow(ordinary, NativeResearchWorker(factory), provision=provision)


def compose_registered_native_workflow(ordinary, *, repository, admission=None, environ=None):
    """The pilot worker's mount: the ordinary workflow unless the switch is on.

    ``admission`` is accepted for the existing call and not used: the research
    harness has no admission of its own.
    """
    environ = os.environ if environ is None else environ
    if not research_harness_enabled(environ):
        return ordinary
    return compose_production_research_workflow(ordinary, repository=repository, environ=environ)
