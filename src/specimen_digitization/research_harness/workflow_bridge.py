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

    def __getattr__(self, name):
        return getattr(self.ordinary, name)

    def step(self, principal, specimen_id):
        specimen = self.ordinary.repository.get(principal.scope, specimen_id)
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

    async def _research(self, principal, specimen):
        if self.provision is not None:
            # Program state, job and canonical binding for this run; idempotent.
            await self.provision(principal, specimen)
        return await self.native_worker.run_registered(principal, specimen.id, owner=self.owner)


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
    verify_access = membership_verifier(repository)
    from .program_budget import research_liability_micros

    def retained_cost(principal, specimen):
        if committed_harness_route(specimen.run.profile_snapshot) is None:
            return 0
        return research_liability_micros(repository, principal, specimen,
            state_backend=state_backend)

    ordinary.retained_cost = retained_cost

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
