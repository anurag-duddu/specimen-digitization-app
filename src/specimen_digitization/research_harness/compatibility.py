"""Versioned boundary into the existing canonical RecordVersion writer."""

from collections.abc import Mapping
from typing import Literal, Protocol

from pydantic import Field

from specimen_digitization.application.domain import Principal

from .contracts import FieldCheckpoint, FrozenRecord, ResearchScope, digest
from .telemetry import ResearchTrace, TraceIdentity


class PublicationUnavailable(RuntimeError):
    pass


class PublicationGuard(FrozenRecord):
    scope: ResearchScope
    binding_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    lease_owner: str
    lease_fence: int = Field(strict=True, gt=0)
    lease_expires_at: float = Field(gt=0, allow_inf_nan=False)
    expected_record_revision: int = Field(strict=True, ge=0)
    checkpoint_revisions: Mapping[str, int]
    checkpoint_digests: Mapping[str, str]
    dependency_revisions: Mapping[str, int]
    dependency_digests: Mapping[str, str] = Field(default_factory=dict)
    receipt_ids: tuple[str, ...]


class ResearchPublication(FrozenRecord):
    contract_version: Literal["research-publication-v1"] = "research-publication-v1"
    guard: PublicationGuard
    checkpoints: tuple[FieldCheckpoint, ...] = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=128)


class PublishedResearch(FrozenRecord):
    contract_version: Literal["research-publication-v1"] = "research-publication-v1"
    scope: ResearchScope
    record_revision: int = Field(strict=True, gt=0)
    publication_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class CanonicalResearchWriter(Protocol):
    """Implement against the sole snapshot/CAS and insert-only projection writer.

    The native transaction must check current membership, specimen sensitivity,
    generation/input/binding, lease fence/server expiry, checkpoint/consumed
    dependency revisions, human locks, receipts and RecordVersion revision. It
    atomically writes canonical layers, projection and research outbox. Sibling
    contention can rebase only SQL after those same guards still match; it
    never calls a model or source. Ordinary repository.save is insufficient.
    """

    research_contract_version: Literal["research-publication-v1"]

    async def publish_research(self, principal: Principal, publication: ResearchPublication) -> PublishedResearch: ...


class ResearchPublicationBridge:
    def __init__(self, writer: CanonicalResearchWriter):
        if getattr(writer, "research_contract_version", None) != "research-publication-v1":
            raise PublicationUnavailable("canonical_research_guard_adapter_not_available")
        self.writer = writer

    async def publish(self, principal: Principal, publication: ResearchPublication) -> PublishedResearch:
        # This adapter cannot manufacture a supported canonical FieldValue or
        # declare a policy exception cleared. The existing writer consumes the
        # validated checkpoint and owns queue disposition/derived graph rules.
        publication = ResearchPublication.model_validate(publication.model_dump(mode="json"))
        scope = publication.guard.scope
        if (principal.scope.organization_id != scope.organization_id
            or principal.scope.collection_id != scope.collection_id or scope.sensitive):
            raise PermissionError("publication_scope_not_authorized")
        fields = set()
        receipts = set()
        for checkpoint in publication.checkpoints:
            key = str(checkpoint.field_key)
            if (checkpoint.scope != scope or key in fields
                or publication.guard.checkpoint_revisions.get(key) != checkpoint.revision
                or publication.guard.checkpoint_digests.get(key) != digest(checkpoint)):
                raise ValueError("publication_checkpoint_binding_mismatch")
            fields.add(key)
            receipts.update(checkpoint.effect_receipt_ids)
            if any(publication.guard.dependency_revisions.get(str(pin.field_key)) != pin.revision
                   or publication.guard.dependency_digests.get(str(pin.field_key)) != pin.digest
                   for pin in checkpoint.resolution.dependencies):
                raise ValueError("publication_dependency_binding_mismatch")
        if receipts != set(publication.guard.receipt_ids):
            raise ValueError("publication_receipt_binding_mismatch")
        if (set(publication.guard.checkpoint_revisions) != fields
            or set(publication.guard.checkpoint_digests) != fields):
            raise ValueError("publication_field_scope_mismatch")
        with ResearchTrace(TraceIdentity(scope.specimen_id, scope.job_id, scope.generation)).span("writer"):
            result = await self.writer.publish_research(principal, publication)
        result = PublishedResearch.model_validate(result.model_dump(mode="json"))
        if (result.scope != scope or result.publication_digest != digest(publication)
            or result.record_revision <= publication.guard.expected_record_revision):
            raise ValueError("canonical_publication_receipt_mismatch")
        return result
