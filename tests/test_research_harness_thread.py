"""Readback uses committed lifecycle and fresh access, never in-memory progress."""

import asyncio

import pytest

from specimen_digitization.research_harness.contracts import FieldKey, WorkState
from specimen_digitization.research_harness.thread_view import ResearchThreadReader
from test_research_harness_journal import setup


def test_thread_retains_twenty_pending_fields_and_revocation_denies_cached_reader(tmp_path):
    _, requests, journal, _ = setup(tmp_path)
    scope = next(iter(requests.values())).scope
    reader = ResearchThreadReader(journal)
    thread = asyncio.run(reader.read(scope))
    assert len(thread.fields) == 20
    assert all(field.work_state == WorkState.PENDING and not field.actions for field in thread.fields)
    assert thread.resolved_count == thread.exception_count == 0
    journal.store.backend.revoke(journal.scope)
    with pytest.raises(PermissionError):
        asyncio.run(reader.read(scope))


def test_thread_ignores_other_specimens_and_never_exposes_capture_payloads(tmp_path):
    from specimen_digitization.research_harness.persistence import CapturedResult, DurableEffectBroker, ImmutableFileBlobs

    _, requests, journal, _ = setup(tmp_path)
    scope = next(iter(requests.values())).scope
    broker = DurableEffectBroker(journal.store, ImmutableFileBlobs(tmp_path / "blobs"))

    async def provider(*_):
        return CapturedResult({"secret":"PRIVATE_CAPTURE_CANARY"}, 3)

    receipt = asyncio.run(broker.execute(journal.scope, journal.lease, "model:specimen_taxonomy", {}, 10, provider))
    thread = asyncio.run(ResearchThreadReader(journal).read(scope))
    assert [effect.effect_id for effect in thread.effects] == [receipt.effect_id]
    assert thread.effects[0].actual_micro_usd == 3
    assert "PRIVATE_CAPTURE_CANARY" not in thread.model_dump_json()
    assert next(field for field in thread.fields if field.field_key == FieldKey.TAXON).work_state == WorkState.PENDING


def test_queued_retry_shows_durable_phase_keeps_failure_checkpoint_and_neighbor(tmp_path):
    from specimen_digitization.application.domain import FieldValue
    from specimen_digitization.research_harness.contracts import FieldResolution, SpecialistRole

    _, requests, journal, settings = setup(tmp_path)
    request = requests[SpecialistRole.TAXONOMY]
    failed, = asyncio.run(journal.commit(request, (FieldResolution(field_key=FieldKey.TAXON,
        work_state=WorkState.OPERATIONAL_FAILED, value=FieldValue(), reason="specialist_operational_failure"),),
        receipt_ids=(), model_settings_digest=settings))
    before = asyncio.run(ResearchThreadReader(journal).read(request.scope))
    command = journal.store.admit_retry(journal.scope, str(FieldKey.TAXON),
        expected_generation=journal.scope.generation, expected_field_revision=failed.revision,
        idempotency_key="single-retry", execution_class="offline")
    after = asyncio.run(ResearchThreadReader(journal).read(request.scope))
    field = next(item for item in after.fields if item.field_key == FieldKey.TAXON)
    assert command["status"] == "queued" and field.work_state == WorkState.RETRY_SCHEDULED
    assert field.checkpoint == failed and field.actions == ()
    assert [item for item in after.fields if item.field_key != FieldKey.TAXON] == [
        item for item in before.fields if item.field_key != FieldKey.TAXON]
    journal.store.claim_retry_command(journal.scope, journal.lease, command["id"])
    journal.store.complete_retry_command(journal.scope, journal.lease, command["id"],
        blocked_reason="retry_checkpoint_missing")
    blocked = asyncio.run(ResearchThreadReader(journal).read(request.scope))
    field = next(item for item in blocked.fields if item.field_key == FieldKey.TAXON)
    assert field.work_state == WorkState.OPERATIONAL_FAILED and field.checkpoint == failed
    assert field.blocker_code == "research_retry_blocked" and field.actions == ()
    assert [item for item in blocked.fields if item.field_key != FieldKey.TAXON] == [
        item for item in before.fields if item.field_key != FieldKey.TAXON]
