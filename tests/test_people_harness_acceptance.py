"""Previously accepted people work survives an invalid pending sibling."""
import asyncio

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness.contracts import (
    FieldCheckpoint, FieldKey, FieldResolution, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.people import collector_resolution
from specimen_digitization.research_harness.sources import SourceBroker
from test_research_harness_acceptance import _integrated, _run_engine, _with_literals


def test_a_committed_collector_survives_two_invalid_irn_results_and_restart(tmp_path):
    role = SpecialistRole.PARTIES
    ctx = _integrated(tmp_path, (role,))
    request = _with_literals(ctx, role, {"collectors": ("Jane Smith", "collecting")})
    collector = collector_resolution(request, assembly_id=request.assemblies[0].id)
    accepted = FieldCheckpoint(scope=ctx.scope, field_key=FieldKey.COLLECTORS, revision=1,
        resolution=collector, prompt_digest=request.prompt.digest,
        model_settings_digest=digest({"max_tokens": 128}), source_registry_digest=request.prompt.source_registry_digest)
    ctx.store.checkpoint(ctx.durable_scope, ctx.lease, "collectors", accepted.model_dump(mode="json"),
        expected_revision=0, receipt_ids=())
    bad_irn = FieldResolution(field_key=FieldKey.IDENTIFIED_BY_IRN, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, parsed="123", authority_id="123",
            evidence_ids=["invented-biography"]), evidence_ids=("invented-biography",),
        reason="A deliberately invalid pending sibling")
    engine, result = _run_engine(ctx, {role: (bad_irn,)}, SourceBroker(ctx.registry), {})
    assert len(ctx.provider_calls) == 2
    assert result.fields[FieldKey.COLLECTORS] == collector
    assert result.fields[FieldKey.IDENTIFIED_BY_IRN].work_state == WorkState.OPERATIONAL_FAILED
    saved = ctx.store.job(ctx.durable_scope)["fields"]["collectors"]
    assert saved["revision"] == 1 and FieldCheckpoint.model_validate(saved["checkpoint"]["payload"]) == accepted
    again = asyncio.run(engine.run())
    assert again.fields == result.fields and len(ctx.provider_calls) == 2
    assert ctx.store.budget(ctx.durable_scope)["held_micro_usd"] == 0
