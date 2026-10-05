"""Bind derivation inputs to immutable original human saves, without provider calls.

The optional ``proofs`` argument is for callers that already obtained genuine
repository proofs (and offline tests). An audit event alone is never a proof.
Manual authority strings confer no provider outcome or coordinate authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from specimen_digitization.application.domain import LookupStatus, ValueState
from specimen_digitization.application.projection import _human_research_choices
from specimen_digitization.application.storage import ReviewDecisionProof, canonical_json

from .contracts import FieldKey, SourceResult, digest
from .derivation_contracts import GEOGRAPHY_FIELDS, SettledDerivationInput
from .thread_view import candidate_selection_value

PROVENANCE_LIMIT = 1024 * 1024
INVALID = "derivation_input_provenance_invalid"
_ACTIONS = frozenset({"review_field", "review_research_candidate",
                      "review_authority_resolution", "review_taxonomy_resolution"})


def _proofs(repository, specimen, supplied):
    if supplied is None:
        reader = getattr(repository, "_review_proofs", None)
        if reader is None:
            if specimen.audit_offset or any(e.action.startswith("review_") for e in specimen.audit):
                raise ValueError(INVALID)
            return ()
        supplied, _ = reader(specimen.scope, specimen)
    result = tuple(supplied)
    if (any(not isinstance(p, ReviewDecisionProof) or p.specimen_id != specimen.id
            or not 0 <= p.base_revision < p.resulting_revision <= specimen.version
            for p in result) or len({p.event.id for p in result}) != len(result)):
        raise ValueError(INVALID)
    return result


def _version(repository, specimen, revision):
    original = repository.version(specimen.scope, specimen.id, revision)
    if (original.id != specimen.id or original.scope != specimen.scope
            or original.version != revision):
        raise ValueError(INVALID)
    return original


def _reviewed(repository, specimen, proofs):
    """Latest field-specific decision, still exactly present in this run."""
    snapshots, latest = {}, {}
    choices = _human_research_choices(specimen, list(proofs))
    for proof in proofs:
        event = proof.event
        if event.action not in _ACTIONS or not isinstance(event.after, dict):
            continue
        try:
            key = FieldKey(event.after.get("field_key"))
        except (TypeError, ValueError):
            continue  # Older unscoped audit text cannot establish a field input.
        if proof.resulting_revision not in snapshots:
            snapshots[proof.resulting_revision] = _version(repository, specimen, proof.resulting_revision)
        original = snapshots[proof.resulting_revision]
        found = [(index, item) for index, item in enumerate(original.audit) if item.id == event.id]
        if len(found) != 1 or found[0][1] != event:
            raise ValueError(INVALID)
        if original.run.id != specimen.run.id:
            continue
        order = (proof.resulting_revision, found[0][0])
        if key not in latest or order > latest[key][0]:
            latest[key] = (order, proof, original)
    result = {}
    for key, (_, proof, original) in latest.items():
        field, previous = specimen.run.fields.get(key), original.run.fields.get(key)
        if field is None or previous is None or digest(field) != digest(previous):
            continue
        if proof.event.action == "review_research_candidate" and choices.get(key) != proof.event.after:
            continue  # Explicitly superseded selections cannot become inputs again.
        result[key] = (proof, original)
    return result


def genuine_human_locked_fields(repository, specimen, *, proofs=None) -> tuple[FieldKey, ...]:
    """Protect proved human fields, including deliberately unresolved fields."""
    return tuple(sorted(_reviewed(repository, specimen, _proofs(repository, specimen, proofs))))


def _evidence(specimen, original, field):
    retained = []
    for identifier in dict.fromkeys(field.evidence_ids):
        before = [e for e in original.run.evidence if e.id == identifier]
        current = [e for e in specimen.run.evidence if e.id == identifier]
        if not before and not current:
            continue  # Do not promote a dangling identifier to real evidence.
        if len(before) != 1 or len(current) != 1 or digest(before[0]) != digest(current[0]):
            raise ValueError(INVALID)
        retained.append(identifier)
    return tuple(retained)


def _read(blobs, reference, sha256):
    raw = blobs.get_bounded(reference, PROVENANCE_LIMIT)
    if len(raw) > PROVENANCE_LIMIT or hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError(INVALID)
    return raw


def _source_selection(specimen, original, proof, blobs):
    after = proof.event.after
    identifier, = after["evidence_ids"]
    evidence, = [e for e in original.run.evidence if e.id == identifier]
    current, = [e for e in specimen.run.evidence if e.id == identifier]
    if digest(evidence) != digest(current):
        raise ValueError(INVALID)
    raw = _read(blobs, evidence.raw_ref, evidence.digest)
    payload = json.loads(raw)
    required = {"kind", "selection_id", "field_key", "value", "authority_id", "source_id",
                "effect_id", "evidence_id", "checkpoint_id", "checkpoint_digest",
                "source_candidate", "source_result", "capture"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError(INVALID)
    if (payload["kind"] != "human_research_candidate"
            or any(payload[key] != after.get(key) for key in (
                "selection_id", "field_key", "value", "authority_id", "source_id", "effect_id", "checkpoint_id"))
            or any(not isinstance(payload[key], str) or not re.fullmatch(r"[a-f0-9]{64}", payload[key])
                   for key in ("selection_id", "checkpoint_id", "checkpoint_digest", "effect_id"))):
        raise ValueError(INVALID)
    result = SourceResult.model_validate(payload["source_result"])
    candidate = payload["source_candidate"]
    if (result.status not in {LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS}
            or result.coverage.field_key != payload["field_key"]
            or result.coverage.source_id != payload["source_id"]
            or not isinstance(candidate, dict)
            or candidate_selection_value(candidate) != payload["value"]
            or candidate.get("authority_id") != payload["authority_id"]
            or candidate.get("field_key", payload["field_key"]) != payload["field_key"]
            # Ordinary evidence uses canonical_json (46.0 serializes as 46).
            # Compare that exact representation, without losing other keys.
            or not any(canonical_json(json.loads(item)) == canonical_json(candidate)
                       for item in result.candidate_json)):
        raise ValueError(INVALID)
    cited = [e for e in result.evidence if e.id == payload["evidence_id"]]
    if (len(cited) != 1 or cited[0].id not in result.coverage.receipt_ids
            or cited[0].source_id != result.coverage.source_id
            or cited[0].source_version != result.coverage.source_version):
        raise ValueError(INVALID)
    capture = payload["capture"]
    if (not isinstance(capture, dict) or set(capture) != {"locator", "generation", "sha256", "byte_size"}
            or not all(isinstance(capture[key], str) and capture[key] for key in ("locator", "generation"))
            or not isinstance(capture["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", capture["sha256"])
            or type(capture["byte_size"]) is not int or capture["byte_size"] < 1):
        raise ValueError(INVALID)
    if payload["source_id"] == "geolocate" and not re.fullmatch(r"geolocate:[a-f0-9]{16}", payload["authority_id"] or ""):
        raise ValueError(INVALID)
    # Keep the original outcome, all candidate coordinates, and complete capture.
    # The worker qualifies the retained source; this never relabels AMBIGUOUS.
    return payload


@dataclass(frozen=True)
class _Prepared:
    fields: dict
    raw: bytes


def _prepare(repository, specimen, blobs, proofs):
    prepared = {}
    for key, (proof, original) in sorted(_reviewed(repository, specimen, proofs).items()):
        if key not in GEOGRAPHY_FIELDS:
            continue
        field = specimen.run.fields[key]
        value = next((v for v in (field.normalized, field.parsed, field.literal) if v is not None), None)
        if field.state != ValueState.SUPPORTED or not isinstance(value, str) or not value.strip():
            continue
        evidence_ids = _evidence(specimen, original, field)
        decision_id = "review-decision:" + proof.event.id
        source = (_source_selection(specimen, original, proof, blobs)
                  if proof.event.action == "review_research_candidate" else None)
        field_digest = digest(field)
        payload = {"kind": "human_derivation_input", "field_key": str(key),
                   "canonical_run_id": specimen.run.id, "canonical_revision": specimen.version,
                   "field_digest": field_digest, "review_decision": proof.event.model_dump(mode="json"),
                   "original_review_revision": proof.resulting_revision, "source_selection": source}
        raw = canonical_json(payload).encode()
        if len(raw) > PROVENANCE_LIMIT:
            raise ValueError(INVALID)
        prepared[key] = _Prepared({"field_key": key, "value": value,
            "evidence_ids": tuple(dict.fromkeys((*evidence_ids, decision_id))), "revision": specimen.version,
            "authority_id": field.authority_id if field.authority_id and field.authority_id.strip() else decision_id,
            "field_digest": field_digest, "review_decision_id": proof.event.id,
            "provenance_sha256": hashlib.sha256(raw).hexdigest(),
            "selection_id": source["selection_id"] if source else None,
            "original_review_revision": proof.resulting_revision}, raw)
    return prepared


def inspect_settled_inputs(repository, specimen, blobs, *, proofs=None) -> tuple[FieldKey, ...]:
    """Read-only eligibility using the same complete verification as collection."""
    return tuple(_prepare(repository, specimen, blobs, _proofs(repository, specimen, proofs)))


def collect_settled_inputs(repository, specimen, blobs, *, proofs=None) -> tuple[SettledDerivationInput, ...]:
    """Copy verified original human provenance into immutable ordinary blobs."""
    prepared = _prepare(repository, specimen, blobs, _proofs(repository, specimen, proofs))
    return tuple(SettledDerivationInput(**item.fields, provenance_blob_ref=blobs.put(item.raw))
                 for item in prepared.values())


def verify_settled_inputs(repository, specimen, blobs, inputs, *, proofs=None) -> None:
    """Recheck saved source revisions, immutable artifacts, and unchanged current fields.

    An unrelated revision may advance (including queueing R+1); the caller must
    separately enforce its command's canonical queue revision and run binding.
    This function performs no writes, source calls, or model calls.
    """
    inputs = tuple(SettledDerivationInput.model_validate(item) for item in inputs)
    if not 1 <= len(inputs) <= 5 or len({i.field_key for i in inputs}) != len(inputs):
        raise ValueError(INVALID)
    proofs = _proofs(repository, specimen, proofs)
    current = _prepare(repository, specimen, blobs, proofs)
    sources = {}
    for item in inputs:
        if item.revision > specimen.version or item.original_review_revision > item.revision:
            raise ValueError(INVALID)
        if item.revision not in sources:
            source = _version(repository, specimen, item.revision)
            if source.run.id != specimen.run.id:
                raise ValueError(INVALID)
            sources[item.revision] = _prepare(repository, source, blobs,
                tuple(p for p in proofs if p.resulting_revision <= source.version))
        saved = sources[item.revision].get(item.field_key)
        latest = current.get(item.field_key)
        fields = item.model_dump(mode="python", exclude={"provenance_blob_ref"})
        if (saved is None or latest is None or fields != saved.fields
                or _read(blobs, item.provenance_blob_ref, item.provenance_sha256) != saved.raw):
            raise ValueError(INVALID)
        # Revision and artifact hash may change solely because of queueing.
        ignored = {"revision", "provenance_sha256"}
        if ({k: v for k, v in saved.fields.items() if k not in ignored}
                != {k: v for k, v in latest.fields.items() if k not in ignored}):
            raise ValueError(INVALID)
