"""People settlement through the production composer with offline seams.

Scripted models, fixture sources, SQLite and the fake native connector establish
composed source acceptance only; this is not live EMu or native SQL proof.
"""

import asyncio
import json

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

import production_e2e_support as support
from test_production_e2e import no_network, rig, supervised, to_plan  # noqa: F401

from specimen_digitization.application.domain import ValueState
from specimen_digitization.application.workflow import OperationalBlock
from specimen_digitization.research_harness.agents import SpecialistOutput
from specimen_digitization.research_harness.contracts import FieldKey, FieldResolution, SpecialistRole
from specimen_digitization.research_harness.evidence import missing_irn_resolution
from specimen_digitization.research_harness.native_worker import NativeResearchWorkerOutcomeV2
from specimen_digitization.research_harness.people import collector_resolution
from specimen_digitization.research_harness.workflow_bridge import compose_production_research_workflow


def people_composer(rig, people_calls):
    ordinary = support.scripted_model_factory(rig.model_calls, geolocate=False)

    def models(request, binding):
        if request.role != SpecialistRole.PARTIES:
            return ordinary(request, binding)

        def respond(messages, info):
            people_calls.append(request)
            assembly = next(item for item in request.assemblies
                if item.field_key == FieldKey.COLLECTORS)
            results = [part.content for message in messages for part in message.parts
                if isinstance(part, ToolReturnPart) and part.tool_name == "invoke_utility"]
            if not results:
                return ModelResponse(parts=[ToolCallPart("invoke_utility", {"tool_id": "settle_collectors",
                    "arguments": {"field_key": "collectors", "event_id": assembly.event_id}},
                    tool_call_id="offline-people-settlement")], usage=support.USAGE)
            [collector] = [FieldResolution.model_validate(item)
                for item in json.loads(results[-1].candidate_json[0])["resolutions"]]
            assert collector == collector_resolution(request, assembly_id=assembly.id)
            output = SpecialistOutput(role=request.role, resolutions=(
                collector,
                missing_irn_resolution(),
            ))
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                output.model_dump(mode="json"), tool_call_id="offline-people-output")], usage=support.USAGE)

        return FunctionModel(respond)

    return compose_production_research_workflow(rig.ordinary, repository=rig.repository,
        environ={"SPECIMEN_RESEARCH_HARNESS": "on"}, actor_uid=support.WORKER,
        state_backend=rig.backend, model_factory=models,
        source_transport=support.fixture_source_transport(rig.source_urls), blobs=rig.research_blobs)


@pytest.mark.parametrize("interrupted", (False, True))
def test_people_publish_automatically_and_resume_committed_work_without_save(rig, interrupted):
    people_calls = []
    workflow = people_composer(rig, people_calls)
    parsed = to_plan(workflow, rig)
    start = len(rig.fake.calls)

    if interrupted:
        publish = workflow.native_worker._publish_committed
        interruptions = []

        async def stop_after_people_commit(runtime, principal, specimen_id, *, publication_progress=None):
            job = runtime.store.job(runtime.scope)
            if job["fields"]["collectors"]["work_state"] == "resolved":
                # A controlled offline stop occurs after durable acceptance and
                # before preparing or sending either people publication. All
                # effects are known complete, so ordinary lease release applies.
                interruptions.append(job["fields"]["collectors"]["checkpoint"]["id"])
                return NativeResearchWorkerOutcomeV2(scope=runtime.binding.research_scope(),
                    status="blocked", reason_code="offline_stop_after_people_checkpoint")
            return await publish(runtime, principal, specimen_id,
                publication_progress=publication_progress)

        workflow.native_worker._publish_committed = stop_after_people_commit
        with supervised(), pytest.raises(OperationalBlock, match="offline_stop_after_people_checkpoint"):
            workflow.step(rig.principal, rig.specimen_id)
        assert len(interruptions) == 1
        assert not any(row["causal_proof"]["changed_field"] in {"collectors", "identified_by_irn"}
            for row in rig.fake.receipts.values())
        _, state = support.research_state(rig.fake, rig.specimen_id)
        [job] = list(state["jobs"].values())
        assert job["lease"] is None
        assert job["fields"]["collectors"]["work_state"] == "resolved"
        assert job["fields"]["identified_by_irn"]["work_state"] == "nonblocking_exception"
        assert all(effect["status"] == "completed" for effect in state["effects"].values())
        restarted = people_composer(rig, people_calls)
        with supervised():
            asyncio.run(restarted.native_worker.run_registered(rig.principal, rig.specimen_id,
                owner=restarted.owner))
    else:
        with supervised():
            workflow.step(rig.principal, rig.specimen_id)

    published = rig.repository.get(rig.principal.scope, rig.specimen_id)
    collector = published.run.fields["collectors"]
    assert collector.state == ValueState.SUPPORTED
    assert collector.literal == collector.normalized == support.LABEL_VALUES["collectors"]
    assert collector.verbatim_by_observation and collector.settled_observation_ids
    assert collector.evidence_ids
    determiner = published.run.fields["identified_by_irn"]
    assert determiner.state == ValueState.UNKNOWN and determiner.authority_id is None
    assert "mandatory_unresolved:identified_by_irn" not in published.run.reasons
    changed = [row["causal_proof"]["changed_field"] for row in rig.fake.receipts.values()]
    assert changed.count("collectors") == changed.count("identified_by_irn") == 1
    assert len(people_calls) == 2
    assert published.version == parsed.version + len(rig.fake.receipts)
    assert "SaveSpecimenV3" not in rig.fake.calls[start:]

    # A fresh workflow observes the committed canonical record without another
    # people model call, duplicate native receipt or administrative save.
    before = (published.version, len(rig.fake.receipts), len(rig.model_calls), len(rig.source_urls))
    with supervised():
        again = people_composer(rig, people_calls).step(rig.principal, rig.specimen_id)
    assert (again.version, len(rig.fake.receipts), len(rig.model_calls), len(rig.source_urls)) == before
    assert len(people_calls) == 2 and not rig.fake.duplicates
    assert "SaveSpecimenV3" not in rig.fake.calls[start:]
