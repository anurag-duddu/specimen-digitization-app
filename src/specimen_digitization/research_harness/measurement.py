"""Measurement-specific use of exact native checkpoint dependencies."""
from __future__ import annotations

import re

from .contracts import (
    DependencyPin, FieldCheckpoint, FieldKey, FieldResolution, ResearchScope, SpecialistRequest,
    SpecialistRole, WorkState, digest,
)
from .evidence import EvidenceError, SettledMeasurement, elevation_resolutions


def settled_elevation_dependencies(
    job, scope: ResearchScope, *, checkpoint_proof_reader=None,
) -> tuple[DependencyPin, ...]:
    """Capture current written native checkpoints for a later narrowed request.

    Use the existing native-original/reuse verifier, rather than treating a
    field revision or an ordinary extracted value as a settled checkpoint.
    Human locks and carried human outcomes never supply native source pins.
    The utility still requires an exact reconstructed source-resolution digest;
    the engine and journal recheck current dependencies before use and commit.
    """
    from .native_materialization_inputs_v2 import _current_checkpoint
    from .accepted_output import AcceptedCheckpointProofV1
    from .persistence import StaleWork

    if checkpoint_proof_reader is None:
        return ()
    pins = []
    for key in (FieldKey.ELEVATION_FROM_M, FieldKey.ELEVATION_TO_M,
                FieldKey.ELEVATION_FROM_FT, FieldKey.ELEVATION_TO_FT):
        field = job["fields"][str(key)]
        if (field["locked"] or str(key) in job.get("preserved_human_outcomes", {})
            or field.get("checkpoint") is None):
            continue
        checkpoint, pair = _current_checkpoint(job, str(key), scope)
        resolution = checkpoint.resolution
        if (field.get("work_state") == WorkState.RESOLVED
            and resolution.work_state == WorkState.RESOLVED
            and resolution.value.state == "supported" and resolution.value_layer == "settled"
            and resolution.derivation is None and resolution.measurement is not None
            and checkpoint.prompt_digest == job["pins"]["prompts"][str(SpecialistRole.MEASUREMENT)]["digest"]
            and checkpoint.source_registry_digest == job["pins"]["sources"]["registry_digest"]
            and checkpoint.model_settings_digest == digest(job["pins"]["settings"])):
            native = pair["original"]
            pointer = native.get("accepted_output_proof")
            if not isinstance(pointer, dict):
                continue
            proof = checkpoint_proof_reader(native["id"])
            if not isinstance(proof, AcceptedCheckpointProofV1):
                raise StaleWork("research_elevation_accepted_source_unproved")
            proof = AcceptedCheckpointProofV1.model_validate(proof.model_dump(mode="json"))
            original = FieldCheckpoint.model_validate(native["payload"])
            matches = [item for item in proof.checkpoints if item.field_key == key]
            if (matches != [original] or pointer.get("proof_digest") != proof.proof_digest
                or pointer.get("request_digest") != digest(proof.acceptance.original_request)
                or proof.acceptance.original_request.scope != original.scope):
                raise StaleWork("research_elevation_accepted_source_unproved")
            pins.append(DependencyPin(field_key=key, revision=checkpoint.revision,
                digest=digest(resolution)))
    return tuple(pins)


def pinned_elevation_resolutions(
    request: SpecialistRequest, settled: SettledMeasurement,
) -> tuple[FieldResolution, ...]:
    """Replay a derived-only repair from an exactly pinned omitted source.

    A field revision alone does not establish a native source. The immutable
    request must carry a checkpoint pin whose digest equals the complete written
    settled source resolution reconstructed from this event. Optional verified
    settled context preserves that source's actual consumed dependencies; every
    scientific, event, evidence and measurement attribute must still equal the
    deterministic reconstruction. A context row never supplies new science.
    Missing or different pins leave the utility's original dependencies
    unchanged; the existing agent
    and checkpoint fences then refuse unavailable sources. Human outcomes never
    supply a substitute pin. Requested sources still use ordinary sibling CAS.
    """
    rows = elevation_resolutions(settled)
    written = {row.field_key: row for row in rows if row.derivation is None}
    pins = {pin.field_key: pin for pin in request.dependencies}
    if len(pins) != len(request.dependencies):
        raise EvidenceError("Elevation source checkpoint pins must be unambiguous")
    contexts = {}
    for context in getattr(request, "settled_context", ()):
        try:
            native = FieldResolution.model_validate(context.resolution.model_dump(mode="json"))
            pin = DependencyPin.model_validate(context.pin.model_dump(mode="json"))
            valid = (native.field_key == pin.field_key and native.work_state == WorkState.RESOLVED
                and native.value.state == "supported" and digest(native) == pin.digest
                and pins.get(pin.field_key) == pin
                and re.fullmatch(r"[a-f0-9]{64}", context.accepted_proof_digest) is not None)
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid or pin.field_key in contexts:
            raise EvidenceError("Elevation source context must be exact and unambiguous")
        contexts[pin.field_key] = native
    for key, source in tuple(written.items()):
        if key in request.field_keys or key not in contexts:
            continue
        native = contexts[key]
        reconstructed = FieldResolution.model_validate({**source.model_dump(mode="json"),
            "dependencies": native.dependencies})
        if reconstructed != native:
            raise EvidenceError("Elevation source context differs from deterministic written settlement")
        written[key] = reconstructed
    rebound = []
    for row in rows:
        if row.derivation is None:
            # Keep the full genuine omitted source in the retained utility
            # inventory; the model's final output remains scoped to requested
            # fields and cannot reopen or overwrite that native checkpoint.
            row = written[row.field_key]
        derivation = row.derivation
        if derivation is not None and derivation.source_field not in request.field_keys:
            source = written.get(derivation.source_field)
            pin = pins.get(derivation.source_field)
            if source is not None and pin is not None and pin.digest == digest(source):
                row = FieldResolution.model_validate({**row.model_dump(mode="json"),
                    "derivation": derivation.model_copy(update={
                        "source_revision": pin.revision}).model_dump(mode="json"),
                    "dependencies": (pin,)})
        rebound.append(row)
    return tuple(rebound)
