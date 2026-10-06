"""Server-proven ordinary field decisions, preserved across fresh runs.

These are human outcomes, never native resolutions/checkpoints. The manifest
names intended transitions; only authoritative immutable reads prove a save.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

from pydantic import Field

from .domain import AuditEvent, Evidence, FieldValue, MANDATORY, ValueState
from .storage import ReviewDecisionProof, canonical_json, digest
from ..research_harness.contracts import FieldKey, FrozenRecord

KEY = "preserved_human_fields"
INVALID = "preserved_human_field_provenance_unavailable"
LIMIT = 1024 * 1024


class _ReadPass:
    """Bound/cache our scoped reads; ReviewProofReader separately caps its reads."""
    def __init__(self, repository, blobs):
        self.repository, self.blobs = repository, blobs
        self.cache, self.raw, self.byte_size = {}, {}, 0
        self.checksums = {}

    def __getattr__(self, key):
        return getattr(self.repository, key)

    def _read(self, key, callback):
        if key not in self.cache:
            if len(self.cache) >= 50:
                _fail()
            self.cache[key] = callback()
        return self.cache[key]

    def version(self, scope, ident, revision):
        return self._read(("version", revision), lambda: self.repository.version(scope, ident, revision))

    def version_info(self, scope, ident, revision):
        return self._read(("info", revision), lambda: self.repository.version_info(scope, ident, revision))

    def execute(self, operation, variables):
        return self._read((operation, canonical_json(variables)), lambda: self.repository.execute(operation, variables))

    def locate(self, ref):
        return self._read(("location", ref), lambda: self.repository.locate(ref))

    def get_bounded(self, ref, bound):
        if ref not in self.raw:
            if len(self.raw) >= 50:
                _fail()
            value = self.blobs.get_bounded(ref, bound)
            self.byte_size += len(value)
            if self.byte_size > 32 * LIMIT:
                _fail()
            self.raw[ref] = value
        if len(self.raw[ref]) > bound:
            _fail()
        return self.raw[ref]

    def sha256(self, ref, bound):
        raw = self.get_bounded(ref, bound)
        if ref not in self.checksums:
            self.checksums[ref] = hashlib.sha256(raw).hexdigest()
        return self.checksums[ref]


def _pass(repository, blobs):
    reader = repository if isinstance(repository, _ReadPass) else _ReadPass(repository, blobs)
    return reader, reader


class CarryTransition(FrozenRecord):
    event_id: str
    actor: str
    reason: str = Field(min_length=1)
    source_run_id: str
    source_revision: int = Field(strict=True, ge=1)
    target_run_id: str


class HumanFieldCarryV1(FrozenRecord):
    contract_version: Literal["ordinary-human-field-carry/v1"] = "ordinary-human-field-carry/v1"
    organization_id: str
    collection_id: str
    specimen_id: str
    field_key: FieldKey
    origin_run_id: str
    origin_event_id: str
    origin_revision: int = Field(strict=True, ge=2)
    origin_field: FieldValue
    source_identity: dict
    transitions: tuple[CarryTransition, ...]


class PreservedHumanFieldOutcome(FrozenRecord):
    """A separately proved human outcome, with no native question or effect."""
    contract_version: Literal["preserved-human-field/v1"] = "preserved-human-field/v1"
    field_key: FieldKey
    value: FieldValue
    original_value: FieldValue
    organization_id: str
    collection_id: str
    specimen_id: str
    canonical_run_id: str
    fresh_run_revision: int = Field(strict=True, ge=2, le=9007199254740991)
    origin_run_id: str
    origin_event_id: str
    origin_revision: int = Field(strict=True, ge=2, le=9007199254740991)
    actor: str
    reason: str
    created_at: str
    original_evidence_ids: tuple[str, ...]
    carry_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    proof_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class VerifiedHumanCarries:
    specimen_id: str
    run_id: str
    revision: int
    snapshot_sha256: str
    outcomes: Mapping[str, PreservedHumanFieldOutcome]

    def matches(self, specimen):
        return (specimen.id == self.specimen_id and specimen.run.id == self.run_id
                and specimen.version == self.revision
                and digest(specimen.model_dump(mode="json")) == self.snapshot_sha256
                and all(specimen.run.fields.get(k) == v.value
                    and (v.organization_id, v.collection_id, v.specimen_id) == (
                        specimen.scope.organization_id, specimen.scope.collection_id, specimen.id)
                    and v.canonical_run_id == specimen.run.id and v.source_sha256 == specimen.asset.sha256
                    and v.fresh_run_revision <= specimen.version for k, v in self.outcomes.items()))


def contract_pin():
    return {"contract_version": "ordinary-human-field-carry/v1",
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def _fail():
    raise ValueError(INVALID)


def manifests(specimen):
    raw = specimen.run.dependencies.get(KEY, {})
    if not isinstance(raw, dict) or not set(raw) <= set(MANDATORY) or len(canonical_json(raw).encode()) > LIMIT:
        _fail()
    result = {k: HumanFieldCarryV1.model_validate(v) for k, v in raw.items()}
    if any(str(v.field_key) != k or not v.transitions or len(v.transitions) > 20 for k, v in result.items()):
        _fail()
    return result


def _proofs(repository, specimen, supplied=None):
    if supplied is None:
        if not specimen.audit_offset and not any(e.action.startswith("review_") for e in specimen.audit):
            if specimen.run.dependencies.get(KEY):
                _fail()
            return ()
        reader = getattr(repository, "_review_proofs", None)
        if not callable(reader):
            _fail()  # A local event alone is not an atomic server save audit.
        supplied, _ = reader(specimen.scope, specimen)
    result = tuple(supplied)
    if (any(not isinstance(p, ReviewDecisionProof) or p.specimen_id != specimen.id for p in result)
            or len({p.event.id for p in result}) != len(result)):
        _fail()
    return result


def _latest(repository, specimen, proofs):
    latest, snapshots = {}, {}
    for p in proofs:
        event = p.event
        if p.resulting_revision not in snapshots:
            snapshots[p.resulting_revision] = repository.version(specimen.scope, specimen.id, p.resulting_revision)
        original = snapshots[p.resulting_revision]
        if event.action == "review_regions":
            # This field-only carry has no authority to recreate a still-current
            # human geometry decision as a fresh default/model segmentation.
            if (original.run.id == specimen.run.id
                    and event.after.get("run_id") == original.run.id
                    and original.run.regions == specimen.run.regions):
                _fail()
            continue
        if event.action == "review_transcription":
            # Only a still-current correction would be erased. An obsolete
            # historical transcript from another run is not a present choice.
            if original.run.id == specimen.run.id and any(
                    t.actor is not None and t in original.run.transcripts for t in specimen.run.transcripts):
                _fail()
            continue
        key = event.after.get("field_key") if isinstance(event.after, dict) else None
        if event.action == "review_taxonomy_resolution":
            key = "taxon"
        if key not in MANDATORY:
            continue
        found = [(i, e) for i, e in enumerate(original.audit) if e.id == event.id]
        if len(found) != 1 or found[0][1] != event:
            _fail()
        order = (p.resulting_revision, found[0][0])
        if key not in latest or order > latest[key][0]:
            latest[key] = (order, p, original)
    return latest


def _source(repository, specimen, blobs):
    asset = specimen.asset
    locator = getattr(repository, "locate", None)
    if not callable(locator):
        _fail()
    location = locator(asset.blob_ref)
    if not location.generation or (location.bucket != "local" and location.generation == "0"):
        _fail()
    raw = blobs.get_bounded(asset.blob_ref, 25_000_000)
    if len(raw) != asset.size_bytes or blobs.sha256(asset.blob_ref, 25_000_000) != asset.sha256:
        _fail()
    return {"asset_id": asset.id, "sha256": asset.sha256, "blob_ref": asset.blob_ref,
            "bucket": location.bucket, "object_name": location.object_name,
            "generation": location.generation, "size_bytes": asset.size_bytes,
            "width": asset.width, "height": asset.height, "pixel_basis": asset.pixel_basis}


def _evidence(original, field, blobs):
    by_id = {e.id: e for e in original.run.evidence}
    if len(by_id) != len(original.run.evidence) or len(set(field.evidence_ids)) != len(field.evidence_ids):
        _fail()
    for ident in field.evidence_ids:
        item = by_id.get(ident)
        if item is None:
            _fail()
        if item.asset_id is not None and item.asset_id != original.asset.id:
            _fail()
        if item.region_id is not None and item.region_id not in {r.id for r in original.run.regions}:
            _fail()
        observations = {o.id: o for o in original.run.observations}
        if any(i not in observations or observations[i].region_id != item.region_id for i in item.observation_ids):
            _fail()
        if item.raw_ref or item.digest:
            if not item.raw_ref or not item.digest:
                _fail()
            raw = blobs.get_bounded(item.raw_ref, LIMIT)
            if len(raw) > LIMIT or blobs.sha256(item.raw_ref, LIMIT) != item.digest:
                _fail()
        for ident in item.observation_ids:
            obs = observations[ident]
            raw = blobs.get_bounded(obs.raw_ref, 4 * LIMIT)
            if blobs.sha256(obs.raw_ref, 4 * LIMIT) != obs.raw_sha256:
                _fail()


def evidence_id(carry):
    from .projection import derived_id
    return derived_id("ordinary-human-field-carry", carry.organization_id, carry.collection_id,
        carry.specimen_id, carry.transitions[-1].target_run_id, str(carry.field_key), digest(carry.model_dump(mode="json")))


def active_value(carry):
    # The value members remain exact. Current ancestry honestly names the human
    # carry evidence, not an old reading presented as a new-run observation.
    ident = evidence_id(carry)
    return carry.origin_field.model_copy(deep=True, update={"evidence_ids": [ident],
        "evidence_relations": {ident: "decides"}, "input_source": None,
        "source_region_id": None, "source_observation_id": None,
        "verbatim_by_observation": {}, "input_source_by_observation": {},
        "settled_observation_ids": []})


def install(specimen, carries, blobs):
    if not carries:
        return
    specimen.run.dependencies[KEY] = {k: c.model_dump(mode="json") for k, c in sorted(carries.items())}
    for k, carry in carries.items():
        raw = canonical_json(carry.model_dump(mode="json")).encode()
        item = Evidence(id=evidence_id(carry), kind="ordinary_human_field_carry",
            asset_id=specimen.asset.id, source="ordinary-human-review",
            locator=f"review-decision:{carry.origin_event_id}", excerpt=carry.origin_field.reason,
            raw_ref=blobs.put(raw), digest=hashlib.sha256(raw).hexdigest(),
            created_at=specimen.run.created_at)
        specimen.run.evidence.append(item)
        specimen.run.fields[k] = active_value(carry)


def prepare(repository, specimen, target_run_id, event, blobs):
    repository, blobs = _pass(repository, blobs)
    proofs = _proofs(repository, specimen)
    latest = _latest(repository, specimen, proofs)
    existing = manifests(specimen)
    if existing:
        verify(repository, specimen, blobs, proofs=proofs)
    source = _source(repository, specimen, blobs) if latest or existing else None
    result = {}
    for key, (_, proof, original) in latest.items():
        # Choose the latest event FIRST; equality must never revive an older one.
        if proof.event.action != "review_field":
            if key in existing:
                _fail()
            continue
        field = original.run.fields.get(key)
        if field is None or not proof.event.reason.strip():
            _fail()
        declared = {k: proof.event.after[k] for k in FieldValue.model_fields if k in proof.event.after}
        if FieldValue.model_validate(declared) != field:
            _fail()  # Reject an incompatible source decision before the action CAS.
        if key in existing:
            old = existing[key]
            if old.origin_event_id != proof.event.id or specimen.run.fields.get(key) != active_value(old):
                _fail()
            carry = old
        else:
            if original.run.id != specimen.run.id or specimen.run.fields.get(key) != field:
                if original.run.id == specimen.run.id:
                    _fail()  # Current human decision became incompatible; never drop it silently.
                continue  # A different historical run cannot revive an old decision.
            if _source(repository, original, blobs) != source:
                _fail()
            _evidence(original, field, blobs)
            carry = HumanFieldCarryV1(organization_id=specimen.scope.organization_id,
                collection_id=specimen.scope.collection_id, specimen_id=specimen.id,
                field_key=key, origin_run_id=original.run.id, origin_event_id=proof.event.id,
                origin_revision=proof.resulting_revision, origin_field=field.model_copy(deep=True),
                source_identity=source, transitions=())
        transition = CarryTransition(event_id=event.id, actor=event.actor, reason=event.reason,
            source_run_id=specimen.run.id, source_revision=specimen.version, target_run_id=target_run_id)
        result[key] = carry.model_copy(update={"transitions": (*carry.transitions, transition)})
    if result and set(result) == set(specimen.run.fields):
        raise ValueError("preserved_human_fields_no_new_research_work")
    event.before = {"source_run_id": specimen.run.id, "source_revision": specimen.version}
    event.after = {"target_run_id": target_run_id,
        "preserved_human_fields": {k: digest(v.model_dump(mode="json")) for k, v in sorted(result.items())}}
    return result


def _transition(repository, specimen, carry, t, index):
    before = repository.version(specimen.scope, specimen.id, t.source_revision)
    after = repository.version(specimen.scope, specimen.id, t.source_revision + 1)
    expected = carry.model_copy(update={"transitions": carry.transitions[:index + 1]})
    target = manifests(after).get(str(carry.field_key))
    if (_source(repository, before, repository) != carry.source_identity
            or _source(repository, after, repository) != carry.source_identity):
        _fail()
    events = [e for e in after.audit if e.id == t.event_id]
    if (before.run.id != t.source_run_id or after.run.id != t.target_run_id or target != expected
            or len(events) != 1 or events[0].action != "reprocess" or events[0].actor != t.actor
            or events[0].reason != t.reason or events[0].before != {
                "source_run_id": t.source_run_id, "source_revision": t.source_revision}
            or events[0].after.get("target_run_id") != t.target_run_id
            or events[0].after.get(KEY, {}).get(str(carry.field_key)) != digest(expected.model_dump(mode="json"))
            or after.run.fields.get(str(carry.field_key)) != active_value(expected)):
        _fail()
    source_field = carry.origin_field if index == 0 else active_value(
        carry.model_copy(update={"transitions": carry.transitions[:index]}))
    if before.run.fields.get(str(carry.field_key)) != source_field:
        _fail()
    # Actual immutable server audit is read AFTER CAS. Nothing is appended to or
    # rewritten in the already committed target snapshot to remember this proof.
    response = repository.execute("GetReviewSaveProofV1", dict(repository.variables(specimen.scope),
        specimenId=specimen.id, decisionId=t.event_id, decisionActorUid=t.actor,
        baseRevision=t.source_revision, resultingRevision=t.source_revision + 1))
    for name, value in (("prior", before), ("target", after)):
        row = response.get(name)
        if not row or repository._snapshot(row) != value or row.get("sha256") != repository.version_info(
                specimen.scope, specimen.id, value.version)["sha256"]:
            _fail()
    audits = response.get("saveAudits", [])
    if len(audits) != 1:
        _fail()
    audit = audits[0]
    def same_id(left, right):
        return isinstance(left, str) and left.replace("-", "").lower() == right.replace("-", "").lower()
    if (not same_id(audit.get("organizationId"), specimen.scope.organization_id)
            or not same_id(audit.get("collectionId"), specimen.scope.collection_id)
            or not same_id(audit.get("specimenId"), specimen.id) or audit.get("actorUid") != t.actor
            or audit.get("revision") != t.source_revision + 1 or audit.get("action") != "checkpoint_or_review"
            or not audit.get("id")):
        _fail()
    return {"snapshot": response["target"]["sha256"], "save_audit": audit["id"]}


def verify(repository, specimen, blobs, *, proofs=None):
    repository, blobs = _pass(repository, blobs)
    carries = manifests(specimen)
    hints = any(e.kind == "ordinary_human_field_carry" for e in specimen.run.evidence)
    if not carries and not hints:
        return VerifiedHumanCarries(specimen.id, specimen.run.id, specimen.version,
            digest(specimen.model_dump(mode="json")), {})
    proved = _proofs(repository, specimen, proofs)
    latest = _latest(repository, specimen, proved)
    # A pin/model writer cannot make an installed carry disappear merely by
    # deleting dependencies. Only a later actual same-field human save may
    # supersede it. Retained evidence is immutable even after that supersession.
    for item in specimen.run.evidence:
        if item.kind != "ordinary_human_field_carry":
            continue
        raw = blobs.get_bounded(item.raw_ref, LIMIT)
        if blobs.sha256(item.raw_ref, LIMIT) != item.digest:
            _fail()
        old = HumanFieldCarryV1.model_validate_json(raw)
        key = str(old.field_key)
        if old.transitions[-1].target_run_id != specimen.run.id:
            _fail()
        if key not in carries:
            replacement = latest.get(key)
            if (replacement is None or replacement[2].run.id != specimen.run.id
                    or replacement[1].resulting_revision <= old.transitions[-1].source_revision + 1
                    or replacement[2].run.fields.get(key) != specimen.run.fields.get(key)):
                _fail()
    source = _source(repository, specimen, blobs)
    outcomes = {}
    for key, carry in carries.items():
        current = latest.get(key)
        if (current is None or current[1].event.action != "review_field"
                or current[1].event.id != carry.origin_event_id or carry.source_identity != source
                or carry.specimen_id != specimen.id or carry.organization_id != specimen.scope.organization_id
                or carry.collection_id != specimen.scope.collection_id
                or carry.transitions[-1].target_run_id != specimen.run.id):
            _fail()
        _, proof, original = current
        after = proof.event.after
        declared = {k: after[k] for k in FieldValue.model_fields if k in after}
        if FieldValue.model_validate(declared) != carry.origin_field:
            _fail()
        if (original.run.id != carry.origin_run_id or proof.resulting_revision != carry.origin_revision
                or original.run.fields.get(key) != carry.origin_field or _source(repository, original, blobs) != source
                or specimen.run.fields.get(key) != active_value(carry)):
            _fail()
        _evidence(original, carry.origin_field, blobs)
        if len({t.target_run_id for t in carry.transitions}) != len(carry.transitions):
            _fail()
        transition_proofs = [_transition(repository, specimen, carry, t, i) for i, t in enumerate(carry.transitions)]
        expected_raw = canonical_json(carry.model_dump(mode="json")).encode()
        evidence = [e for e in specimen.run.evidence if e.id == evidence_id(carry)]
        if len(evidence) != 1 or evidence[0].kind != "ordinary_human_field_carry" or evidence[0].source != "ordinary-human-review":
            _fail()
        raw = blobs.get_bounded(evidence[0].raw_ref, LIMIT)
        if raw != expected_raw or blobs.sha256(evidence[0].raw_ref, LIMIT) != evidence[0].digest:
            _fail()
        event = proof.event
        outcomes[key] = PreservedHumanFieldOutcome(field_key=key, value=active_value(carry),
            original_value=carry.origin_field.model_copy(deep=True),
            organization_id=specimen.scope.organization_id, collection_id=specimen.scope.collection_id,
            specimen_id=specimen.id,
            canonical_run_id=specimen.run.id, fresh_run_revision=carry.transitions[-1].source_revision + 1,
            origin_run_id=carry.origin_run_id, origin_event_id=event.id, origin_revision=proof.resulting_revision,
            actor=event.actor, reason=event.reason, created_at=event.created_at,
            original_evidence_ids=tuple(carry.origin_field.evidence_ids), carry_digest=digest(carry.model_dump(mode="json")),
            proof_digest=digest({"origin": {"event": event.model_dump(mode="json"),
                "prior": proof.prior_sha256, "result": proof.snapshot_sha256, "audit": proof.server_audit_id},
                "transitions": transition_proofs, "carry": carry.model_dump(mode="json")}), source_sha256=specimen.asset.sha256)
    return VerifiedHumanCarries(specimen.id, specimen.run.id, specimen.version,
        digest(specimen.model_dump(mode="json")), outcomes)


def job_outcomes(job):
    raw = job.get("preserved_human_outcomes", {})
    if not raw:
        return {}
    if job["pins"]["sources"].get("human_field_carry") != contract_pin():
        _fail()
    result = {k: PreservedHumanFieldOutcome.model_validate(v) for k, v in raw.items()}
    if any(str(v.field_key) != k or not job["fields"][k]["locked"]
            or job["fields"][k]["checkpoint"] is not None
            or job.get("human_lock_proofs", {}).get(k) != v.proof_digest
            or job["fields"][k]["work_state"] != "waiting_human" for k, v in result.items()):
        _fail()
    return result


def replay_reprocess(repository, scope, run_id, request_key, expected_revision, request_digest, blobs):
    """Read an exact committed action receipt; never save or redispatch a replay."""
    if not callable(getattr(repository, "execute", None)):
        return None
    response = repository.execute("GetReprocessActionReceiptsV1", dict(repository.variables(scope),
        idempotencyKey="action:" + request_key, resultingRevision=expected_revision + 1))
    receipts = response.get("requestReceipts")
    if not isinstance(receipts, list) or len(receipts) > 2:
        _fail()
    if not receipts:
        return None
    from .storage import Conflict
    if len(receipts) != 1:
        raise Conflict("Committed reprocess receipt is ambiguous")
    receipt = receipts[0]
    if receipt.get("requestSha256") != request_digest:
        raise Conflict("Idempotency key reused")
    ident = receipt.get("specimenId")
    from uuid import UUID
    try:
        ident = str(UUID(ident)) if isinstance(ident, str) else None
    except ValueError:
        ident = None
    if (ident is None or receipt.get("operation") != "save:" + ident
            or receipt.get("revision") != expected_revision + 1):
        raise Conflict("Committed reprocess receipt does not match the requested base")
    saved = repository.version(scope, ident, receipt["revision"])
    if saved.id != ident or saved.scope != scope:
        _fail()
    events = [e for e in saved.audit if e.action == "reprocess"
        and e.before == {"source_run_id": run_id, "source_revision": expected_revision}
        and e.after.get("target_run_id") == saved.run.id]
    if len(events) != 1:
        raise Conflict("Committed action does not match this run")
    verify(repository, saved, blobs)
    # The canonical save might already have dispatched before its response was
    # lost. A receipt grants no second jobs:run effect. Return the same result.
    return saved


def adapt_projection(rows, specimen, verified):
    """Compose genuine human candidates and their record IDs, not fake readings."""
    from . import projection as p
    if not verified.matches(specimen):
        _fail()
    if not verified.outcomes:
        return rows
    if not any(w.operation == "AppendPipelineRunV2" or w.operation == "AppendPipelineRunV1" for w in rows):
        # Before classify binds the fresh published profile there is no current
        # normalized run row. Snapshot values are already protected; plan writes
        # the complete carry-aware canonical base once that parent exists.
        return rows
    keys = set(verified.outcomes)
    old_candidates = {w.variables["id"] for w in rows if w.operation == "AppendFieldCandidateV2" and w.variables["fieldKey"] in keys}
    record_rows = [w for w in rows if w.operation == "AppendRecordVersionV2"]
    candidates = {w.variables["fieldKey"]: w.variables.get("candidateId") for w in rows if w.operation == "AppendResolvedFieldV2"}
    result = [w for w in rows if not (w.operation == "AppendFieldCandidateV2" and w.variables["fieldKey"] in keys)
        and not (w.operation == "AppendCandidateEvidenceV2" and w.variables["candidateId"] in old_candidates)
        and w.operation not in {"AppendRecordVersionV2", "AppendResolvedFieldV2", "AppendValidationFindingV2"}]
    for key, outcome in verified.outcomes.items():
        value = outcome.value
        candidate = p.derived_id("preserved-human-candidate", specimen.run.id, key, outcome.carry_digest)
        candidates[key] = candidate
        result.append(p._write("AppendFieldCandidateV2", {"id": candidate, "runId": specimen.run.id,
            "fieldKey": key, "state": str(value.state), "literalValue": value.literal,
            "parsedValue": {"value": value.parsed, "precision": value.precision, "century_rule": value.century_rule}
                if value.precision or value.century_rule else value.parsed,
            "normalizedValue": value.normalized, "authorityId": value.authority_id,
            "derivation": "ordinary_human_field_carry", "inputSource": None,
            "sourceTranscriptionId": None, "sourceObservationId": None}))
        for ident in value.evidence_ids:
            result.append(p._write("AppendCandidateEvidenceV2", {"id": p.derived_id("candidate-evidence", candidate, ident),
                "candidateId": candidate, "evidenceId": ident, "relation": "decides"}))
    if record_rows:
        recorded = {w.variables["id"] for w in result if w.operation == "AppendEvidenceItemV2"}
        result.extend(p._record(specimen.run, candidates, recorded))
    return result
