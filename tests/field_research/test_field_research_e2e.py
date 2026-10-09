"""One specimen through the production composer with SPECIMEN_RESEARCH_HARNESS=fields.

The same production-like rig as tests/research_harness/test_production_e2e.py:
a real SqlConnectRepository over the in-memory connector (FakeDataConnect, which
records every operation it receives), the ordinary Workflow with its synthetic
readers, and the run's pinned published profile. Only the field experts and the
approved sources are stand-ins, injected at the composition seam
(compose_production_research_workflow(..., field_research=...)).
"""

from __future__ import annotations

import logging
import sys
import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import ExecutionPolicy
from specimen_digitization.application.native_drain import (
    RegisteredNativeDrainWorkflow, compose_registered_native_drain,
)
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.worker_deadline import WorkerDeadline
from specimen_digitization.application.workflow import FIELD_RESEARCH, SyntheticAdapters, Workflow
from specimen_digitization.field_research import step as field_step
from specimen_digitization.field_research.contracts import FieldAnswer, FieldOutcome
from specimen_digitization.field_research.step import FieldResearchStep
from specimen_digitization.research_harness.persistence import DurabilityScope, SqliteStateBackend
from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research_harness"))
from production_e2e_support import (  # noqa: E402
    COLLECTION, LABEL_TEXT, LABEL_VALUES, ORG, WORKER, FakeDataConnect, GenerationBlobs,
    published_profile, specimen_before_adjudication, worker_principal,
)
from test_step import GBIF_NAME, FakeSources, Scripted, failing, resolved  # noqa: E402

FIELDS = {"SPECIMEN_RESEARCH_HARNESS": "fields"}
CAP = 1_000_000
NATIVE_OPERATIONS = {"GetCanonicalResearchBindingV2", "RegisterCanonicalResearchBindingV2",
    "GetCanonicalResearchMaterializationInputsV2", "PublishCanonicalResearchV2"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import httpx

    def refuse(*args, **kwargs):
        raise AssertionError("the offline e2e test performs no HTTP")
    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)
    monkeypatch.setattr(httpx.Client, "send", refuse)


@pytest.fixture
def rig(tmp_path):
    backend = SqliteStateBackend(tmp_path / "research-state.sqlite")
    backend.grant(DurabilityScope(ORG, COLLECTION, "membership", "membership", 1, WORKER, False))
    fake = FakeDataConnect(backend, members={WORKER: [{"organization_id": ORG, "collection_id": COLLECTION,
        "role": "operator", "can_view_sensitive": False}]})
    blobs = GenerationBlobs(tmp_path / "blobs")
    repository = SqlConnectRepository(session=fake, graph_blobs=blobs)
    ordinary = Workflow(repository, blobs, SyntheticAdapters(blobs, LABEL_TEXT))
    token = actor_uid.set(WORKER)
    try:
        principal = worker_principal()
        specimen = specimen_before_adjudication(blobs)
        # As the lane queues a run: the profile's ceiling and prices (lane.py
        # 112-120), and the label coverage its automatic check confirms (G15).
        processing = published_profile().processing
        specimen.run.profile.execution = ExecutionPolicy(approved_cost_limit_micros=processing.run_cost_limit_micros,
            price_list=processing.price_list.model_dump(mode="json"))
        specimen.run.coverage_confirmed = True
        created = repository.create(principal, specimen, "e2e-intake", "e2e-intake")
        yield SimpleNamespace(fake=fake, backend=backend, repository=repository, ordinary=ordinary,
            principal=principal, specimen_id=created.id, blobs=blobs)
    finally:
        actor_uid.reset(token)


def supervised():
    return WorkerDeadline(time.monotonic() + 600).scope()


# The synthetic label writes "elevation_from_m: 180 to 181 m": the experts name each
# end's number alone; the feet and the collection's end date are left to derivation.
SCRIPTS = {
    "elevation_from_m": lambda: resolved("180"),
    "elevation_to_m": lambda: resolved("181"),
    **{key: lambda: FieldAnswer(outcome="label_lacks_value", explanation="No reading states it.")
        for key in ("elevation_from_ft", "elevation_to_ft", "date_visited_to")},
}


def _fixed(make):
    async def script(task, readings, tools):
        return FieldOutcome(task.key, make(), model_calls=1)
    return script


def scripted():
    """test_step's experts (GBIF for the taxon, GEOLocate for the places), with SCRIPTS."""
    return Scripted({key: _fixed(make) for key, make in SCRIPTS.items()})


def mount(rig, resolver):
    state = SimpleNamespace(meters=[])

    def meter_factory(cap, price):
        meter = field_step.cost_meter(cap, price)
        state.meters.append(meter)
        resolver.meter = meter
        return meter

    @asynccontextmanager
    async def tools_factory(run, profile, blobs):
        yield FakeSources(blobs)

    step = FieldResearchStep(resolver_factory=lambda run, profile, meter: resolver,
        tools_factory=tools_factory, meter_factory=meter_factory)
    workflow = compose_production_research_workflow(rig.ordinary, repository=rig.repository, environ=FIELDS,
        state_backend=rig.backend, field_research=step)
    return workflow, step, state


def test_field_research_reaches_the_final_queue_in_one_step(rig, caplog):
    resolver = scripted()
    workflow, step, state = mount(rig, resolver)
    assert workflow is rig.ordinary and workflow.field_research is step
    with supervised():
        workflow.step(rig.principal, rig.specimen_id)  # adjudicate
        parsed = workflow.step(rig.principal, rig.specimen_id)  # parse
    assert workflow.next_step(parsed.run) == "plan" and parsed.version == 3
    before = len(rig.fake.calls)
    with caplog.at_level(logging.WARNING), supervised():
        done = workflow.step(rig.principal, rig.specimen_id)
    sequence = rig.fake.calls[before:]
    calls = Counter(sequence)

    # One step: researched, applied and finalized in memory, then saved once.
    run = done.run
    assert (run.stage, run.disposition, run.blocker, run.reasons) == ("finalized", "cleared", None, [])
    assert run.completed_steps[-1] == FIELD_RESEARCH and "plan" not in run.completed_steps
    assert done.version == parsed.version + 2  # The workflow's intent save, then the one result save.
    # Every connector call of the step, as observed: the read of the run, the
    # intent save (nothing new to project), the result save, then the result's
    # projection rows. No research-state, circuit or ledger document call.
    assert sequence[:8] == ["GetSpecimen", "GetSnapshot", "GetReceipt", "GetSnapshot", "SaveSpecimenV3",
        "GetReceipt", "GetSnapshot", "SaveSpecimenV3"]
    assert all(name.startswith("Append") for name in sequence[8:])
    assert dict(calls) == {"GetSpecimen": 1, "GetSnapshot": 3, "GetReceipt": 2, "SaveSpecimenV3": 2,
        "AppendSourceAssetV2": 14, "AppendEvidenceItemV2": 15, "AppendToolCallV1": 9,
        "AppendFieldCandidateV2": 16, "AppendCandidateEvidenceV2": 22, "AppendRecordVersionV2": 1,
        "AppendResolvedFieldV2": 20}
    assert len(sequence) == 6 + 2 + 97
    assert not NATIVE_OPERATIONS & set(calls)
    assert not [r for r in caplog.records if "Projection" in r.getMessage()]

    # Every model call was paid from the run's ceiling and settled to the meter.
    [meter] = state.meters
    [paid] = run.paid_calls
    assert meter.cap_micros == CAP == paid["reserved_micros"]
    assert paid["cost_micros"] == meter.spent_micros == 50 * len(resolver.calls) <= CAP
    assert run.usage.reserved_cost_micros == meter.spent_micros <= run.profile.execution.approved_cost_limit_micros
    assert sorted(resolver.calls) == sorted(key for key, tools in field_step.FIELD_TOOLS.items() if tools)

    # The record as the connector holds it: one record version for the final queue.
    saved = rig.repository.get(rig.principal.scope, rig.specimen_id)
    assert saved.run == run
    final = [row for row in rig.fake.tables["record_version"].values() if row["disposition"] == "cleared"]
    assert len(final) == 1 and final[0]["runId"] == run.id
    resolved_fields = {row["fieldKey"]: row for row in rig.fake.tables["resolved_field"].values()
        if row["recordVersionId"] == final[0]["id"]}
    assert len(resolved_fields) == 20 and resolved_fields["taxon"]["state"] == "supported"
    candidate = rig.fake.tables["field_candidate"][resolved_fields["taxon"]["candidateId"]]
    assert (candidate["normalizedValue"], candidate["derivation"]) == (GBIF_NAME, "lookup")
    gbif = [row for row in rig.fake.tables["evidence_item"].values() if row["source"] == "gbif"]
    tool_calls = [row for row in rig.fake.tables["tool_call"].values() if row["source"] == "gbif"]
    assert gbif and [row["fieldKeys"] for row in tool_calls] == [["taxon"]]
    fields = run.fields
    assert (fields["elevation_from_ft"].parsed, fields["elevation_to_ft"].parsed) == ("590.55", "593.83")
    assert fields["date_visited_to"].parsed == LABEL_VALUES["date_visited_from"]
    assert fields["identified_by_irn"].state == "unknown"


def test_the_drain_mounts_field_research_with_fields(rig):
    drain = compose_registered_native_drain(rig.ordinary, repository=rig.repository, environ=FIELDS)
    assert isinstance(drain, RegisteredNativeDrainWorkflow) and drain.workflow is rig.ordinary
    mounted = rig.ordinary.field_research
    assert isinstance(mounted, FieldResearchStep)
    assert mounted.resolver_factory is field_step._production_resolver
    assert mounted.tools_factory is field_step._production_tools and mounted.concurrency == 20
    specimen = rig.repository.get(rig.principal.scope, rig.specimen_id)
    assert mounted.handles(specimen.run)


def test_an_outage_saves_once_with_a_retry_and_the_retry_researches_only_what_failed(rig):
    first = scripted()
    first.scripts["country"] = failing("source_unavailable")
    workflow, _, state = mount(rig, first)
    with supervised():
        workflow.step(rig.principal, rig.specimen_id)
        parsed = workflow.step(rig.principal, rig.specimen_id)
        before = len(rig.fake.calls)
        held = workflow.step(rig.principal, rig.specimen_id)
    run = held.run
    assert (run.stage, run.blocker, run.disposition) == ("retry_scheduled", "lookup_operational_failure", None)
    assert run.reasons[0] == "lookup_operational_failure:country" and run.next_retry_at
    assert held.version == parsed.version + 2 and rig.fake.calls[before:].count("SaveSpecimenV3") == 2
    assert rig.fake.specimens[rig.specimen_id]["work_available_at"] is not None
    assert run.fields["taxon"].normalized == GBIF_NAME and run.fields["country"].state == "unresolved"
    assert run.usage.reserved_cost_micros == state.meters[0].spent_micros

    second = scripted()
    workflow, _, state = mount(rig, second)
    later = datetime.fromisoformat(run.next_retry_at) + timedelta(seconds=1)
    rig.ordinary.clock = lambda: later.astimezone(timezone.utc)
    with supervised():
        done = workflow.step(rig.principal, rig.specimen_id)
    assert second.calls == ["country"]
    assert (done.run.stage, done.run.disposition, done.run.reasons) == ("finalized", "cleared", [])
    assert done.run.usage.reserved_cost_micros == sum(call["cost_micros"] for call in done.run.paid_calls) <= CAP
