"""Resolve a human choice from a current, own-field retained source capture."""

import json
import re

from pydantic import Field, model_validator

from specimen_digitization.application.domain import LookupStatus

from .contracts import FieldCheckpoint, FieldKey, FrozenRecord, SourceResult, digest
from .derivation_contracts import DERIVABLE_FIELDS, GEOGRAPHY_FIELDS, Revision
from .persistence import StaleWork
from .thread_view import (REVIEW_STATES, candidate_selection_id, candidate_selection_value,
                          candidate_selection_evidence, candidate_source_capture)


class _GeoreferenceMetadata(FrozenRecord):
    """Retained tool trace only; these coordinates never become record fields."""
    latitude: float = Field(strict=True, ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(strict=True, ge=-180, le=180, allow_inf_nan=False)
    uncertainty_m: float = Field(strict=True, gt=0, allow_inf_nan=False)
    footprint_dataset: str = Field(min_length=1)
    footprint_id: str = Field(min_length=1)
    authority_ids: tuple[str, ...] = Field(min_length=1)
    input_fields: tuple[FieldKey, ...] = Field(min_length=1, max_length=5)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    tool_call_id: str = Field(min_length=1)
    simplification_margin_m: float = Field(strict=True, ge=0, allow_inf_nan=False)
    method: str = Field(min_length=1)
    geodetic_datum: str = Field(min_length=1)
    version: str = Field(min_length=1)


class DerivedCandidateMetadata(FrozenRecord):
    """Exact adapter envelope, without invented checkpoint or model provenance."""
    field_key: FieldKey
    value: str = Field(min_length=1)
    input_fields: tuple[FieldKey, ...] = Field(min_length=1, max_length=5)
    input_revisions: tuple[tuple[FieldKey, Revision], ...] = Field(min_length=1, max_length=5)
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    authority_id: str = Field(min_length=1)
    dataset_ids: tuple[str, ...] = Field(min_length=1)
    tool_call_id: str = Field(min_length=1)
    value_layer: str
    human_review_required: bool = Field(strict=True)
    automatic_settlement_allowed: bool = Field(strict=True)
    rule_version: str = Field(min_length=1)
    georeference: _GeoreferenceMetadata

    @model_validator(mode="after")
    def exact_dependencies(self):
        revisions = tuple(key for key, _ in self.input_revisions)
        if (self.value_layer != "derived" or not self.human_review_required
                or self.automatic_settlement_allowed or self.field_key not in DERIVABLE_FIELDS
                or not set(self.input_fields) <= GEOGRAPHY_FIELDS
                or len(set(self.input_fields)) != len(self.input_fields)
                or revisions != self.input_fields or self.field_key in self.input_fields
                or self.georeference.input_fields != self.input_fields
                or self.georeference.tool_call_id != self.tool_call_id
                or self.georeference.version != self.rule_version
                or not set(self.georeference.evidence_ids) <= set(self.evidence_ids)
                or any(not value.strip() for value in (
                    self.value, self.authority_id, self.tool_call_id, self.rule_version,
                    *self.evidence_ids, *self.dataset_ids, *self.georeference.authority_ids,
                    *self.georeference.evidence_ids))):
            raise ValueError("Derived candidate metadata does not match its retained computation")
        return self


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
                or not effect.get("receipt")):
            continue
        operation = effect.get("operation_key")
        if not isinstance(operation, str) or not operation.startswith(("source_lookup:", "source_capture_v2:")):
            continue
        if effect["receipt"].get("effect_id") != effect_id:
            continue
        result = SourceResult.model_validate(effect["receipt"]["typed_payload"])
        if (result.coverage.field_key != field_key or result.status not in {LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS}
                or not candidate_source_capture(effect, result, job)):
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
            if result.coverage.source_id == "georeference_spatial":
                metadata = DerivedCandidateMetadata.model_validate(item)
                computed = next(entry for entry in result.evidence if entry.id == evidence_id)
                if (metadata.field_key != field_key or metadata.value != value
                        or result.status != LookupStatus.SUCCESS
                        or metadata.rule_version != result.coverage.source_version
                        or result.coverage.qualification_digest != digest(metadata.rule_version)
                        or evidence_id not in metadata.evidence_ids
                        or computed.kind != "computed_derivation_result"
                        or computed.id != "computed:" + computed.response_digest
                        or computed.locator != "computed://georeference_spatial/" + computed.response_digest):
                    raise ValueError("Derived candidate is not a complete retained computation")
            elif item.get("value_layer") == "derived" or item.get("derived_from") or item.get("input_fields"):
                raise ValueError("Only the georeferencing source can offer a derived candidate")
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
