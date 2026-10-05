"""Resolve a human choice from a current, own-field retained source capture."""

import json
import re

from specimen_digitization.application.domain import LookupStatus

from .contracts import FieldCheckpoint, FieldKey, SourceResult, digest
from .persistence import StaleWork
from .thread_view import (REVIEW_STATES, candidate_selection_id, candidate_selection_value,
                          candidate_selection_evidence)


def retained_candidate(document, job_key: str, field_key: FieldKey, selection_id: str) -> dict:
    """No caller-supplied value or authority is used to materialize a choice."""
    if not isinstance(selection_id, str) or not re.fullmatch(r"[a-f0-9]{64}", selection_id):
        raise ValueError("A retained research selection_id is required")
    job = document.state["jobs"][job_key]
    field = job["fields"][str(field_key)]
    stored = field.get("checkpoint")
    if field.get("locked") or stored is None or job.get("paused"):
        raise StaleWork("research_candidate_no_longer_reviewable")
    checkpoint = FieldCheckpoint.model_validate(stored["payload"])
    if (checkpoint.field_key != field_key or checkpoint.revision != field["revision"]
            or checkpoint.resolution.work_state not in REVIEW_STATES
            or field.get("work_state") != checkpoint.resolution.work_state
            or any(getattr(checkpoint.scope, key) != value for key, value in job["identity"].items())
            or checkpoint.scope.generation != job["generation"]
            or checkpoint.scope.input_digest != job["pins"]["input_digest"]
            or checkpoint.scope.profile_digest != digest(job["pins"]["profile"])
            or checkpoint.scope.sensitive is not job["sensitive"]
            or stored.get("id") != digest({"scope": stored.get("scope"), "field": str(field_key),
                "revision": checkpoint.revision, "payload": stored["payload"]})
            or stored.get("field_key") != str(field_key)
            or stored.get("revision") != field["revision"]
            or stored.get("scope") != {**job["identity"], "generation": job["generation"]}
            or stored.get("binding_digest") != job["binding_digest"]
            or field.get("retry_command_id") is not None):
        raise StaleWork("research_candidate_no_longer_reviewable")
    found = {}
    for effect_id in dict.fromkeys(checkpoint.effect_receipt_ids):
        effect = document.state["effects"].get(effect_id)
        if (not effect or effect.get("status") != "completed" or effect.get("job_key") != job_key
                or effect.get("effect_id") != effect_id
                or effect.get("binding_digest") != stored.get("binding_digest")
                or effect.get("field_keys") != [str(field_key)]
                or not effect.get("operation_key", "").startswith("source_lookup:")
                or not effect.get("receipt")):
            continue
        if effect["receipt"].get("effect_id") != effect_id:
            continue
        result = SourceResult.model_validate(effect["receipt"]["typed_payload"])
        if result.coverage.field_key != field_key or result.status not in {LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS}:
            continue
        evidence_id = candidate_selection_evidence(result, checkpoint)
        if evidence_id is None:
            continue
        if (effect.get("scope") != stored.get("scope")
                or effect_id not in stored.get("receipt_ids", ())):
            continue
        for raw in result.candidate_json:
            item = json.loads(raw)
            value = candidate_selection_value(item)
            if value is None or candidate_selection_id(job_key, field_key, effect_id, item) != selection_id:
                continue
            authority = item.get("authority_id")
            if authority is not None and (not isinstance(authority, str) or not authority.strip()):
                continue
            if result.coverage.source_id == "geolocate" and not re.fullmatch(r"geolocate:[a-f0-9]{16}", authority or ""):
                continue
            found[selection_id] = {"selection_id": selection_id, "field_key": str(field_key),
                "value": value, "authority_id": item.get("authority_id"),
                "source_id": result.coverage.source_id, "effect_id": effect_id,
                "evidence_id": evidence_id, "checkpoint_id": stored["id"],
                "checkpoint_digest": digest(stored),
                "source_candidate": item, "source_result": result.model_dump(mode="json"),
                "capture": effect["receipt"]["capture"]}
    if len(found) != 1:
        raise ValueError("Select one retained research candidate")
    return found[selection_id]
