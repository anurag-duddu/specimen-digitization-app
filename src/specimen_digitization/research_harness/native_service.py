"""Production facade for the sole native V2 canonical writer.

Authentication is supplied by the ordinary host. This facade creates neither
program allowance, registered job nor mutable publication result.
"""

from __future__ import annotations

from .publication import PreparedNativePublication


class SqlConnectNativeCanonicalServiceV2:
    def __init__(self, repository, journal, *, blobs, materializer,
                 evidence_provider, projection_services, operation_client=None):
        from .native_canonical_v2 import SqlConnectCanonicalResearchWriterV2

        self.repository, self.journal, self.blobs = repository, journal, blobs
        self.writer = SqlConnectCanonicalResearchWriterV2(
            repository, journal, blobs=blobs, materializer=materializer,
            evidence_provider=evidence_provider, projection_services=projection_services,
            operation_client=operation_client,
        )

    async def list_retained_publication_locators(self, principal, specimen_id):
        return await self.writer.list_retained_publication_locators(principal, specimen_id)

    async def get_materialization_bundle_v2(self, principal, specimen_id, *,
                                           idempotency_key, request_identity_digest,
                                           preparation_id):
        # The writer reads retained intent/winning receipt before mutable input.
        return await self.writer.get_materialization_bundle_v2(
            principal, specimen_id, idempotency_key=idempotency_key,
            request_identity_digest=request_identity_digest,
            preparation_id=preparation_id,
        )

    async def publish_checkpoint(self, principal, prepared: PreparedNativePublication, *,
                                 server_request_identity_digest):
        prepared = PreparedNativePublication.model_validate(prepared.model_dump(mode="json"))
        from .telemetry import ResearchTrace, TraceIdentity
        scope = prepared.basis.scope
        trace = ResearchTrace(TraceIdentity(scope.specimen_id, scope.job_id, scope.generation))
        with trace.span("writer", field_key=str(prepared.basis.field_key),
                checkpoint_id=prepared.basis.checkpoint_id, binding_digest=prepared.basis.binding_digest) as span:
            result = await self.writer.publish_checkpoint(principal, prepared,
                server_request_identity_digest=server_request_identity_digest)
            try:
                trace.annotate(span, terminal_state="replayed" if result.replayed else "published",
                    publication_count=1, revision=result.published.record_revision,
                    publication_digest=result.published.publication_digest)
            except Exception:
                pass  # Diagnostics cannot turn a committed result into a failure.
        try:
            with trace.span("finalization", terminal_state=result.causal.progress_receipt.wire_status,
                    publication_count=1, revision=result.published.record_revision):
                pass
        except Exception:
            pass
        return result

    async def publish_preparation(self, principal, intent, preparation):
        return await self.writer.publish_preparation(principal, intent, preparation)

    async def establish_intent(self, principal, prepared, *, server_request_identity_digest):
        return await self.writer.establish_intent(
            principal, prepared, server_request_identity_digest=server_request_identity_digest,
        )

    async def append_preparation(self, principal, intent, prepared, *, mode="NEW_AFTER_PROGRESS"):
        return await self.writer.append_preparation(principal, intent, prepared, mode=mode)

    async def read_current_binding(self, principal, specimen_id):
        return await self.writer.read_current_binding(principal, specimen_id)

    async def winning_receipt(self, principal, specimen_id, *, idempotency_key,
                              request_identity_digest):
        retained = await self.writer.read_same_operation_intent(
            principal, specimen_id, idempotency_key, request_identity_digest)
        if retained is None:
            return None
        from .compatibility import PublicationUnavailable
        from .persistence import HeldUnknown
        try:
            return await self.writer.read_winning_receipt(principal, specimen_id,
                idempotency_key, request_identity_digest)
        except PublicationUnavailable:
            raise HeldUnknown("native_publication_receipt_requires_reconciliation") from None

    async def resume_same_operation(self, principal, specimen_id, *, idempotency_key,
                                    request_identity_digest):
        return await self.writer.resume_same_operation(
            principal, specimen_id, idempotency_key, request_identity_digest)
