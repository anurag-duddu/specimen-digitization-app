"""Current host-verified checkpoint context; no extraction or model authority."""
from __future__ import annotations

from .contracts import DependencyPin, FieldCheckpoint, FieldKey, SettledFieldContext, SpecialistRole, WorkState, digest

CONTEXT_FIELDS = {
    SpecialistRole.GEOGRAPHY: (FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO, FieldKey.COLLECTORS),
    SpecialistRole.TEMPORAL: (FieldKey.DATE_VISITED_FROM,),
    SpecialistRole.MEASUREMENT: (FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M,
        FieldKey.ELEVATION_FROM_FT, FieldKey.ELEVATION_TO_FT),
    SpecialistRole.PARTIES: (FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO),
    SpecialistRole.COLLECTION: (FieldKey.COLLECTORS, FieldKey.DATE_VISITED_FROM, FieldKey.DATE_VISITED_TO),
    SpecialistRole.TAXONOMY: (),
}


def accepted_native_context(job, scope, *, checkpoint_proof_reader, proofs=None):
    """Read exact accepted current native originals, preserving full dependencies.

    Human/carried outcomes and unresolved checkpoints are never machine source
    pins. A context value establishes no cross-label event relationship.
    """
    from .accepted_output import AcceptedCheckpointProofV1
    from .native_materialization_inputs_v2 import _current_checkpoint
    from .persistence import StaleWork

    if checkpoint_proof_reader is None:
        return {}
    contexts={}
    for key in dict.fromkeys(key for keys in CONTEXT_FIELDS.values() for key in keys):
        field=job["fields"][str(key)]
        if field["locked"] or str(key) in job.get("preserved_human_outcomes", {}) or field.get("checkpoint") is None:
            continue
        checkpoint,pair=_current_checkpoint(job,str(key),scope)
        resolution=checkpoint.resolution
        if field["work_state"] != WorkState.RESOLVED or resolution.work_state != WorkState.RESOLVED or resolution.value.state != "supported":
            continue
        native=pair["original"]
        pointer=native.get("accepted_output_proof")
        if not isinstance(pointer,dict):
            continue
        proof=checkpoint_proof_reader(native["id"])
        if not isinstance(proof,AcceptedCheckpointProofV1):
            raise StaleWork("research_current_context_proof_unavailable")
        proof=AcceptedCheckpointProofV1.model_validate(proof.model_dump(mode="json"))
        original=FieldCheckpoint.model_validate(native["payload"])
        if ([row for row in proof.checkpoints if row.field_key==key] != [original]
                or pointer.get("proof_digest") != proof.proof_digest
                or pointer.get("request_digest") != digest(proof.acceptance.original_request)
                or proof.acceptance.original_request.scope != original.scope):
            raise StaleWork("research_current_context_proof_changed")
        if proofs is not None:
            proofs[key] = proof
        contexts[key]=SettledFieldContext(resolution=resolution,
            pin=DependencyPin(field_key=key,revision=checkpoint.revision,digest=digest(resolution)),
            accepted_proof_digest=proof.proof_digest)
    return contexts


def role_context(role, contexts):
    return tuple(contexts[key] for key in CONTEXT_FIELDS[role] if key in contexts)


def collecting_context_for_job(request, job, *, checkpoint_proof_reader):
    """Hydrate geography's host-only context from exact native accepted proofs.

    Reused original generations and distinct collecting events remain available
    as settled model context, but cannot be silently joined as one location's
    collecting event by this scope-exact geography adapter.
    """
    from .geography_context import CONTEXT_FIELDS as GEO_FIELDS, accepted_collecting_context
    from .persistence import StaleWork
    pins = {pin.field_key: pin for pin in request.dependencies if pin.field_key in GEO_FIELDS}
    if not pins:
        return None
    proofs = {}
    contexts = accepted_native_context(job, request.scope,
        checkpoint_proof_reader=checkpoint_proof_reader, proofs=proofs)
    if any(key not in contexts or contexts[key].pin != pin for key,pin in pins.items()):
        raise StaleWork("research_geography_current_context_changed")
    supplied = tuple({proofs[key].proof_digest:proofs[key] for key in pins}.values())
    try:
        return accepted_collecting_context(request, supplied)
    except ValueError as exc:
        if str(exc) in {"geography_context_scope_changed", "geography_context_competing_collecting_events"}:
            return None  # Explicitly unavailable; no cross-label or generation join.
        raise StaleWork("research_geography_collecting_context_unproved") from None
