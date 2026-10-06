"""A proved native field hold keeps its canonical binding through the drain.

The connector, model and source transport use the existing offline production
fixture. Publication, the bridge, drain, binding validation and report reads are
production code. No native database or live scientific outcome is claimed.
"""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from specimen_digitization.application.lane_worker import DrainWorker
from specimen_digitization.application.native_drain import RegisteredNativeDrainWorkflow
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.discovery_v2 import CanonicalReadBindingV2
from specimen_digitization.research_harness.persistence import HeldUnknown, ResearchStore, StaleWork
from specimen_digitization.research_harness.service import ResearchLocator
from specimen_digitization.research_harness.workflow_bridge import NativeResearchWorkflow

from production_e2e_support import WORKER
from test_production_e2e import NoFence, build_rig, compose, supervised, to_plan


def deny_http(monkeypatch):
    import httpx

    def refuse(*args, **kwargs):
        raise AssertionError("This regression performs no HTTP")

    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    deny_http(monkeypatch)


@pytest.fixture
def rig(tmp_path):
    yield from build_rig(tmp_path)


def drain(rig, workflow):
    worker = DrainWorker(rig.repository, RegisteredNativeDrainWorkflow(workflow),
        WORKER, lambda user: [], execution_id="published-hold-regression")
    with supervised():
        return worker._step_until_stopped(rig.principal, NoFence(), rig.specimen_id, None)


def test_published_source_hold_keeps_current_binding_and_report_after_drain(rig):
    workflow = compose(rig, geolocate=False)
    parsed = to_plan(workflow, rig)
    run, progressed = drain(rig, workflow)
    current = rig.repository.get(rig.principal.scope, rig.specimen_id)
    binding = rig.fake.bindings[rig.specimen_id]
    assert current.version == binding["current_canonical_revision"]
    assert current.version == parsed.version + len(rig.fake.receipts)
    assert progressed and run.stage == "processing_blocked"
    assert run.blocker is None and run.disposition is None
    assert "research_work:country:waiting_source" in run.reasons
    assert not any(event.action == "lane_block" for event in current.audit)

    async def report():
        discovery = workflow.native_worker.runtime_factory.discovery
        # The existing fixture's research state is SQLite, while its connector
        # implements native canonical queries. Keep that explicit offline seam.
        discovery.mutable_store = lambda bound: ResearchStore(rig.backend, bound.program_key)
        found = await discovery.discover(rig.principal, rig.specimen_id)
        locator = ResearchLocator(**{key: getattr(found.scope, key) for key in
            ("organization_id", "collection_id", "specimen_id", "job_id", "generation")})
        service = await discovery.service(rig.principal, locator)
        return await service.thread(rig.principal, locator)

    thread = asyncio.run(report())
    assert not thread.historical and len(thread.fields) == 20
    assert next(field for field in thread.fields if field.field_key == "country").work_state == "waiting_source"


@pytest.fixture(scope="module")
def publication(tmp_path_factory):
    """One real offline native publication chain shared by read-only negatives."""
    with pytest.MonkeyPatch.context() as patch:
        deny_http(patch)
        setup = build_rig(tmp_path_factory.mktemp("published-hold-proof"))
        rig = next(setup)
        try:
            workflow = compose(rig, geolocate=False)
            before = to_plan(workflow, rig)
            with supervised():
                outcome = asyncio.run(workflow._research(rig.principal, before))
            current = rig.repository.get(rig.principal.scope, rig.specimen_id)
            binding = asyncio.run(workflow.native_worker.runtime_factory.discovery.binding(
                rig.principal, rig.specimen_id))
            info = rig.repository.version_info(rig.principal.scope, current.id, current.version)
            assert outcome.status == "blocked" and outcome.reason_code is None
            yield SimpleNamespace(before=before, current=current, binding=binding,
                outcome=outcome, info=info, principal=rig.principal)
        finally:
            setup.close()


def observed_step(publication, *, change=None, error=None):
    """Alter one read/result around a genuine immutable native proof.

    The state is copied per case. The fixture cannot save, dispatch or supply a
    replacement source value; these negatives exercise the bridge's admission.
    """
    case = SimpleNamespace(before=publication.before.model_copy(deep=True),
        current=publication.current.model_copy(deep=True),
        binding=CanonicalReadBindingV2(publication.binding.native),
        outcome=publication.outcome.model_copy(deep=True), info=dict(publication.info), reads=0)
    if change is not None:
        change(case)

    async def read_binding(principal, ident):
        case.reads += 1
        if error is not None:
            raise error
        return case.binding

    async def run_registered(*args, **kwargs):
        return case.outcome

    values = iter((case.before, case.current))
    ordinary = SimpleNamespace(repository=SimpleNamespace(get=lambda *args: next(values),
        version_info=lambda *args: case.info), next_step=lambda run: "plan")
    native = SimpleNamespace(run_registered=run_registered,
        runtime_factory=SimpleNamespace(discovery=SimpleNamespace(binding=read_binding)))
    return NativeResearchWorkflow(ordinary, native), case


def test_only_the_exact_current_native_blocked_snapshot_can_return(publication):
    workflow, case = observed_step(publication)
    with supervised():
        assert workflow.step(publication.principal, case.before.id) == case.current
    assert case.reads == 1
    assert not workflow.completed_side_work(case.current)


@pytest.mark.parametrize("state", ["operational_failed", "cancelled", "retry_scheduled"])
def test_a_later_current_field_failure_is_not_hidden_by_an_earlier_publication(publication, state):
    # The actual head and its current saved snapshot still prove the earlier
    # source hold. A later role failure need not have published another field.
    def later_failure(case):
        case.binding.read_bundle.job["fields"]["city"]["work_state"] = state

    workflow, case = observed_step(publication, change=later_failure)
    head = case.binding.native.causal_chain[-1].progress_receipt
    assert "operational_failed" not in head.research_field_work.values()
    assert case.outcome.reason_code is None and case.outcome.publication_receipt_ids
    with supervised(), pytest.raises(OperationalBlock, match="^native_research_operational_hold$"):
        workflow.step(publication.principal, case.before.id)


@pytest.mark.parametrize("change", [
    {"operational_reason_codes": ("source_operational_failure:retained-lookup:unavailable",)},
    {"research_field_work": {"city": "operational_failed"}},
    {"canonical_field_work": {"city": "operational_failed"}},
], ids=["source-failure-reason", "research-failure-state", "canonical-failure-state"])
def test_a_head_operational_failure_is_not_a_scientific_field_hold(publication, change):
    def failed_head(case):
        native = case.binding.native
        head = native.causal_chain[-1]
        progress = head.progress_receipt
        updates = {key: ({**getattr(progress, key), **value} if isinstance(value, dict) else value)
            for key, value in change.items()}
        # A controlled bad proof read exercises rejection without creating a
        # replacement receipt, source capture, scientific value or valid chain.
        head = head.model_copy(update={"progress_receipt": progress.model_copy(update=updates)})
        case.binding.native = native.model_copy(update={"causal_chain": (*native.causal_chain[:-1], head)})

    workflow, case = observed_step(publication, change=failed_head)
    with supervised(), pytest.raises(OperationalBlock, match="^native_research_operational_hold$"):
        workflow.step(publication.principal, case.before.id)


@pytest.mark.parametrize("code", [
    "accepted_output_proof_unavailable", "native_publication_requires_reconciliation",
    "research_worker_custody_requires_reconciliation", "research_program_headroom_unavailable",
])
def test_explicit_operational_failures_are_never_hidden_by_prior_publications(publication, code):
    workflow, case = observed_step(publication, change=lambda c: setattr(c, "outcome",
        c.outcome.model_copy(update={"reason_code": code})))
    with supervised(), pytest.raises(OperationalBlock, match=f"^{code}$"):
        workflow.step(publication.principal, case.before.id)
    assert case.reads == 0


@pytest.mark.parametrize("change", [
    lambda c: setattr(c, "outcome", c.outcome.model_copy(update={"publication_receipt_ids": ()})),
    lambda c: setattr(c, "outcome", c.outcome.model_copy(update={"publication_receipt_ids": (str(uuid4()),)})),
    lambda c: setattr(c, "outcome", c.outcome.model_copy(update={"scope":
        c.outcome.scope.model_copy(update={"specimen_id": str(uuid4())})})),
    lambda c: setattr(c.current, "version", c.current.version + 1),
    lambda c: setattr(c.before, "version", c.current.version),
    lambda c: setattr(c.current.run, "id", str(uuid4())),
    lambda c: setattr(c.current.run, "stage", "pending"),
    lambda c: setattr(c.current.run, "blocker", "external_outcome_unknown"),
    lambda c: setattr(c.current.run.fields["city"], "reason", "A later human correction"),
    lambda c: setattr(c.current.asset, "sha256", "f" * 64),
    lambda c: c.current.run.profile_snapshot.update({"changed": True}),
    lambda c: c.info.update(sha256="e" * 64),
    lambda c: setattr(c.binding, "read_bundle", c.binding.read_bundle.model_copy(
        update={"hold_reasons": ("unknown_effect",)})),
    lambda c: c.binding.read_bundle.job.update(lease={"owner": "another-worker"}),
    lambda c: next(iter(c.binding.read_bundle.effects.values())).update(
        status="held_unknown", actual_micro_usd=None),
], ids=["no-publication", "wrong-receipt", "foreign-scope", "later-revision", "no-advance",
    "changed-run", "pending-stage", "existing-unknown-blocker", "human-edit", "changed-source",
    "changed-profile", "snapshot-mismatch", "scoped-unknown-hold", "new-lease", "unknown-effect"])
def test_missing_or_stale_or_uncertain_publication_cannot_retire_the_run(publication, change):
    workflow, case = observed_step(publication, change=change)
    with supervised(), pytest.raises(OperationalBlock, match="^native_research_operational_hold$"):
        workflow.step(publication.principal, case.before.id)


@pytest.mark.parametrize("error", [
    PublicationUnavailable("native_v2_binding_unavailable"),
    StaleWork("research_state_changed"), HeldUnknown("research_budget_state_unavailable"),
    PermissionError("research_access_denied"),
])
def test_unavailable_or_denied_proof_remains_an_admission_failure(publication, error):
    workflow, case = observed_step(publication, error=error)
    with supervised(), pytest.raises(OperationalBlock, match="^native_research_admission_or_binding_unavailable$"):
        workflow.step(publication.principal, case.before.id)


def test_unexpected_storage_error_is_not_a_successful_hold(publication):
    workflow, case = observed_step(publication, error=OSError("offline storage failure"))
    with supervised(), pytest.raises(OSError, match="offline storage failure"):
        workflow.step(publication.principal, case.before.id)
