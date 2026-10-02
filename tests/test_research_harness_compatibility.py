"""Guarded publication cannot fall through to an ordinary snapshot save."""

import asyncio

import pytest

from specimen_digitization.application.domain import FieldValue, Principal, Scope
from specimen_digitization.research_harness.compatibility import (
    PublicationGuard, PublicationUnavailable, ResearchPublication, ResearchPublicationBridge,
)
from specimen_digitization.research_harness.contracts import FieldCheckpoint, FieldKey, FieldResolution, WorkState, digest
from test_research_harness_journal import setup


def test_unqualified_existing_writer_is_closed_even_when_save_available():
    class OrdinaryWriter:
        def save(self, *args):
            pytest.fail("Ordinary save bypassed generation and lease guard")
    with pytest.raises(PublicationUnavailable, match="guard_adapter_not_available"):
        ResearchPublicationBridge(OrdinaryWriter())


def test_forged_scope_or_checkpoint_digest_cannot_reach_canonical_writer(tmp_path):
    _, requests, _, settings_digest = setup(tmp_path)
    request = next(iter(requests.values()))
    checkpoint = FieldCheckpoint(scope=request.scope, field_key=FieldKey.TAXON, revision=1,
        resolution=FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.WAITING_SOURCE,
            value=FieldValue(), reason="source_prerequisite"), prompt_digest=request.prompt.digest,
        source_registry_digest=request.prompt.source_registry_digest, model_settings_digest=settings_digest)
    guard = PublicationGuard(scope=request.scope, binding_digest="f"*64,
        lease_owner="worker-test", lease_fence=1, lease_expires_at=1,
        expected_record_revision=1, checkpoint_revisions={"taxon":1},
        checkpoint_digests={"taxon":"e"*64}, dependency_revisions={}, receipt_ids=())
    publication = ResearchPublication(guard=guard, checkpoints=(checkpoint,), idempotency_key="publication-test")

    class Writer:
        research_contract_version = "research-publication-v1"
        async def publish_research(self, principal, publication):
            pytest.fail("Invalid command reached writer")
    bridge = ResearchPublicationBridge(Writer())
    principal = Principal(user_id="reviewer-test", scope=Scope(organization_id="org-test", collection_id="collection-test"), role="reviewer")
    with pytest.raises(ValueError, match="checkpoint_binding"):
        asyncio.run(bridge.publish(principal, publication))
    foreign = principal.model_copy(update={"scope":Scope(organization_id="other", collection_id="collection-test")})
    with pytest.raises(PermissionError, match="scope_not_authorized"):
        asyncio.run(bridge.publish(foreign, publication))
