"""Consume a queued G38 command into retained, editable proposal checkpoints.

The canonical command is immutable. Only the scoped research job records worker
progress, and no path in this module runs a model or publishes canonical values.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Literal

from pydantic import Field

from specimen_digitization.application.domain import FieldValue, LookupStatus, Principal, ValueState
from specimen_digitization.application.georef_locality import comparison_key, read_locality
from specimen_digitization.application.georef_boundaries import extent
from specimen_digitization.application.georef_geometry import inside
from .contracts import (
    ROLE_FIELDS, FieldCheckpoint, FieldKey, FieldResolution, FrozenRecord, HumanQuestion, SourceQuery, SourceResult,
    SpecialistRequest, SpecialistRole, ToolReceipt, WorkState, digest,
)
from .georeferencing import ELEVATION_FIELDS, VERSION, SettledLocationInput
from .persistence import BlobRef, HeldUnknown, StaleWork
from .source_capture_v2 import OPERATION_PREFIX

COMMAND_KEY = "research_derivation_request"
RESULT_KEY = "derivation_result"
WORKER_ROLES = frozenset({"operator", "reviewer", "manager", "admin"})
MAX_INPUT_PROVENANCE_BYTES = 1024 * 1024


class _DerivationBlocked(Exception):
    """Known scientific/prerequisite gap; no uncertain provider outcome."""


def _source_receipt(runtime, request, result, source_id, field_key):
    """Use a genuine completed result and its same-scope durable tool receipt."""
    result = SourceResult.model_validate(result.model_dump(mode="json"))
    receipt = result.receipt
    if (receipt is None or receipt.scope != request.scope or receipt.source_id != source_id
            or receipt.field_keys != (field_key,) or receipt.effect_status != "completed"
            or receipt.outcome != result.status or receipt.held_micro_usd != 0
            or receipt.settled_micro_usd is None or result.coverage.source_id != source_id
            or result.coverage.field_key != field_key):
        raise StaleWork("derivation_source_receipt_unproved")
    effect = runtime.store.effect(runtime.scope, receipt.effect_id)
    saved = effect.get("receipt")
    payload = result.model_copy(update={"receipt": None}).model_dump(mode="json")
    if (effect["field_keys"] != [str(field_key)] or effect["status"] != "completed"
            or not effect.get("operation_key", "").startswith(OPERATION_PREFIX)
            or not saved or saved["typed_payload"] != payload
            or effect["binding_digest"] != receipt.binding_digest
            or effect["request_digest"] != receipt.request_digest
            or saved["capture"]["sha256"] != receipt.response_digest
            or saved["capture"]["locator"] != receipt.capture_locator
            or saved["actual_micro_usd"] is None or saved["held_micro_usd"] != 0):
        raise StaleWork("derivation_source_receipt_unproved")
    return receipt.effect_id


def _spatial_capture(runtime, command, effect_id):
    """Read the core broker's immutable computed-spatial capture, including its command."""
    effect = runtime.store.effect(runtime.scope, effect_id)
    saved = effect.get("receipt")
    if not saved or not saved.get("raw_capture"):
        raise StaleWork("derivation_spatial_capture_unproved")
    reference = BlobRef(**saved["raw_capture"])
    if (not reference.generation or not 0 < reference.byte_size <= 1_000_000):
        raise StaleWork("derivation_spatial_capture_unproved")
    raw = runtime.blobs.get(reference)
    if len(raw) != reference.byte_size or hashlib.sha256(raw).hexdigest() != reference.sha256:
        raise StaleWork("derivation_spatial_capture_unproved")
    envelope = json.loads(raw)
    expected_keys = {"contract_version", "original_request", "logical_request", "effect_id",
        "attempt_id", "binding_digest", "validation_receipt", "settled_inputs", "semantic_result"}
    if not isinstance(envelope, dict) or set(envelope) != expected_keys:
        raise StaleWork("derivation_spatial_capture_unproved")
    request = SpecialistRequest.model_validate(envelope["original_request"])
    logical = envelope["logical_request"]
    inputs = [asdict(SettledLocationInput(item.field_key, item.value, item.evidence_ids,
        item.revision, item.authority_id)) for item in command.inputs]
    receipt = ToolReceipt.model_validate(envelope["validation_receipt"])
    if (envelope["contract_version"] != "research-computed-spatial-capture/v1"
            or envelope["effect_id"] != effect_id or envelope["binding_digest"] != effect["binding_digest"]
            or envelope["attempt_id"] != saved["attempt_id"]
            or envelope["semantic_result"] != saved["typed_payload"]
            or digest(envelope["settled_inputs"]) != digest(inputs)
            or logical.get("contract_version") != "research-computed-spatial-request/v1"
            or logical.get("tool_id") != "source_lookup" or logical.get("source_id") != "georeference_spatial"
            or logical.get("trusted_derivation_command_digest") != digest(command)
            or logical.get("original_request_digest") != digest(request)
            or logical.get("scope") != request.scope.model_dump(mode="json")
            or logical.get("requested_fields") != [str(key) for key in command.requested_fields]
            or digest(logical.get("settled_inputs")) != digest(inputs)
            or logical.get("validation_receipt_id") != receipt.id
            or logical.get("validation_result_digest") != receipt.result_digest
            or logical.get("prompt_digest") != request.prompt.digest
            or logical.get("source_registry_digest") != request.prompt.source_registry_digest
            or effect["request_digest"] != digest(logical)
            or effect["operation_key"] != OPERATION_PREFIX + digest(logical)
            or request.scope.sensitive
            or any(getattr(request.scope, key) != value for key, value in runtime.scope.identity().items())
            or request.field_keys != (FieldKey(logical.get("field_key")),)
            or effect["field_keys"] != [logical.get("field_key")]
            or logical.get("field_revision") != request.field_revisions.get(request.field_keys[0])
            or request.field_keys[0] not in command.requested_fields):
        raise StaleWork("derivation_spatial_capture_unproved")
    validation = SourceResult.model_validate(json.loads(receipt.result_json or "null"))
    validation = validation.model_copy(update={"receipt": receipt})
    _source_receipt(runtime, request, validation, "geolocate", validation.coverage.field_key)
    if (receipt.id != "effect:" + receipt.effect_id or validation.status != LookupStatus.SUCCESS
            or len(validation.candidate_json) != 1
            or not any(item.field_key == validation.coverage.field_key
                and json.loads(validation.candidate_json[0]).get("value") == item.value for item in command.inputs)):
        raise StaleWork("derivation_validation_tool_unproved")
    return request, receipt.id


def _request(runtime, field_key):
    services = runtime.derivation_services
    role = next(role for role, keys in ROLE_FIELDS.items() if field_key in keys)
    original = services.requests.get(role)
    if original is None or original.role != role or field_key not in original.field_keys:
        raise StaleWork("derivation_specialist_request_unavailable")
    job = runtime.store.job(runtime.scope)
    revision = job["fields"][str(field_key)]["revision"]
    return SpecialistRequest.model_validate({**original.model_dump(mode="json"),
        "field_keys": [str(field_key)], "field_revisions": {str(field_key): revision},
        "dependencies": [], "retry_command_id": None})


def _resolution(command, field_key, result, *, validation_tool_id=None):
    """The value stays unresolved; the captured candidate is editable evidence."""
    proposals = [json.loads(raw) for raw in result.candidate_json]
    proposals = [item for item in proposals if item.get("value")
                 and item.get("settlement_allowed") is not False]
    reason = "derivation_request:" + command.id
    evidence_ids = tuple(item.id for item in result.evidence)
    if result.status == LookupStatus.SUCCESS and len(proposals) == 1:
        candidate = proposals[0]
        inputs = {str(item.field_key): item.revision for item in command.inputs}
        if (candidate.get("field_key") != str(field_key)
                or candidate.get("value_layer") != "derived"
                or validation_tool_id is None or candidate.get("tool_call_id") != validation_tool_id
                or candidate.get("rule_version") != VERSION
                or candidate.get("human_review_required") is not True
                or candidate.get("automatic_settlement_allowed") is not False
                or result.coverage.reason != "computed_proposal"
                or not any(item.kind == "computed_derivation_result"
                    and item.source_id == "georeference_spatial" and item.source_version == VERSION
                    and item.id in candidate.get("evidence_ids", ())
                    and item.id in result.coverage.receipt_ids for item in result.evidence)
                or candidate.get("input_fields") != list(inputs)
                or dict(candidate.get("input_revisions", ())) != inputs
                or not set(candidate.get("evidence_ids", ())) <= set(evidence_ids)
                    | {eid for item in command.inputs for eid in item.evidence_ids}):
            raise StaleWork("derivation_proposal_inputs_changed")
        return FieldResolution(field_key=field_key, work_state=WorkState.WAITING_HUMAN,
            value=FieldValue(state=ValueState.UNKNOWN, reason="Derived proposal requires human review"),
            evidence_ids=evidence_ids, source_coverage=(result.coverage,),
            question=HumanQuestion(field_key=field_key,
                question="Review the derived proposal and its settled inputs before choosing a value.",
                reason="derived_proposal", coverage=(result.coverage,), evidence_ids=evidence_ids),
            reason=reason)
    operational = result.status in {LookupStatus.PROVIDER, LookupStatus.MALFORMED,
        LookupStatus.AUTHENTICATION, LookupStatus.AUTHORIZATION, LookupStatus.TIMEOUT,
        LookupStatus.RATE_LIMITED, LookupStatus.EMPTY}
    return FieldResolution(field_key=field_key,
        work_state=WorkState.OPERATIONAL_FAILED if operational else WorkState.WAITING_SOURCE,
        value=FieldValue(reason=result.coverage.reason), evidence_ids=evidence_ids,
        source_coverage=(result.coverage,), reason=reason)


def _validation_tool(runtime, command, result):
    """Proposal tool IDs name an actual same-scope successful GEOLocate effect."""
    candidates = [json.loads(raw) for raw in result.candidate_json]
    identifiers = {identifier for item in candidates
        for identifier in (item.get("tool_call_id"), (item.get("georeference") or {}).get("tool_call_id"))
        if identifier is not None}
    if not identifiers and result.status != LookupStatus.SUCCESS:
        return None
    if len(identifiers) != 1:
        raise StaleWork("derivation_validation_tool_unproved")
    identifier, = identifiers
    if not isinstance(identifier, str) or not identifier.startswith("effect:"):
        raise StaleWork("derivation_validation_tool_unproved")
    effect = runtime.store.effect(runtime.scope, identifier.removeprefix("effect:"))
    saved = effect.get("receipt")
    if (effect["status"] != "completed" or not saved or saved["actual_micro_usd"] is None
            or saved["held_micro_usd"] != 0 or not effect["operation_key"].startswith(OPERATION_PREFIX)):
        raise StaleWork("derivation_validation_tool_unproved")
    validation = SourceResult.model_validate(saved["typed_payload"])
    if (validation.status != LookupStatus.SUCCESS or validation.coverage.source_id != "geolocate"
            or effect["field_keys"] != [str(validation.coverage.field_key)]
            or validation.coverage.field_key not in {item.field_key for item in command.inputs}):
        raise StaleWork("derivation_validation_tool_unproved")
    return identifier


def _country(context):
    names = {"ph": "PH", "philippines": "PH", "gt": "GT", "guatemala": "GT"}
    values = [names.get(comparison_key(item.value)) for item in context.settled_inputs
              if item.field_key == FieldKey.COUNTRY]
    if len(values) != 1 or values[0] is None:
        raise _DerivationBlocked("derivation_country_unavailable")
    return values[0]


def _anchor(context, adapter, country):
    levels = adapter.field_levels.get(country, {})
    candidates = [(levels[item.field_key], item) for item in context.settled_inputs
                  if item.field_key in levels]
    if not candidates:
        raise _DerivationBlocked("derivation_footprint_anchor_unavailable")
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
        raise _DerivationBlocked("derivation_footprint_anchor_ambiguous")
    return candidates[0][1]


def _label_elevation(specimen):
    fields = [specimen.run.fields.get(key) for key in ELEVATION_FIELDS]
    if any(field and (field.literal or field.verbatim_by_observation) for field in fields):
        return True
    raw = _raw_locality(specimen)
    raw += tuple(item.literal_text for item in getattr(specimen.run, "observations", ()))
    if any(read_locality(text).elevations for text in raw):
        return True
    if all(field is not None and field.state == ValueState.NOT_PRESENT for field in fields):
        return False
    return None


def _raw_locality(specimen):
    texts = []
    for key in ROLE_FIELDS[SpecialistRole.GEOGRAPHY]:
        value = specimen.run.fields.get(key)
        if value is not None:
            texts.extend(text for text in (value.literal, *value.verbatim_by_observation.values()) if text)
    return tuple(dict.fromkeys(texts))


class DerivationWorkerOutcome(FrozenRecord):
    request_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["running", "completed", "blocked"]
    checkpoint_ids: tuple[str, ...] = ()
    blocked_reason: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,79}$")


@dataclass(frozen=True)
class DerivationContext:
    """Verified input context supplied to the model-free runtime composition."""

    command: object
    specimen: object
    settled_inputs: tuple[SettledLocationInput, ...]
    _worker: object = field(repr=False, compare=False)
    _principal: Principal = field(repr=False, compare=False)
    _anchor_queries: dict = field(default_factory=dict, repr=False, compare=False)

    def verify_current(self, request, command_digest, settled_inputs, requested_fields):
        if (command_digest != digest(self.command) or tuple(settled_inputs) != self.settled_inputs
                or tuple(requested_fields) != self.command.requested_fields
                or request.scope.sensitive or request.scope.specimen_id != self.specimen.id
                or request.scope.organization_id != self._principal.scope.organization_id
                or request.scope.collection_id != self._principal.scope.collection_id):
            raise StaleWork("derivation_context_changed")
        current = self._worker._verify(self._principal, self.specimen.id, self.command)
        if current.settled_inputs != self.settled_inputs:
            raise StaleWork("derivation_inputs_changed")

    def verify_locked_anchor(self, request, query, anchor, command_digest):
        from .sources import geolocate_interpretation

        self.verify_current(request, command_digest, self.settled_inputs, self.command.requested_fields)
        if (query.source_id not in {"geolocate", "georeference_history"} or query.field_key != anchor.field_key
                or anchor not in self.settled_inputs or anchor.field_key not in self.command.human_locked_fields
                or request.role != SpecialistRole.GEOGRAPHY or request.field_keys != (anchor.field_key,)
                or self._anchor_queries.get((query.source_id, anchor.field_key)) != query):
            raise StaleWork("derivation_locked_anchor_unproved")
        if query.source_id == "georeference_history":
            if json.loads(query.query_text) != {"country": _country(self), "name": anchor.value}:
                raise StaleWork("derivation_locked_anchor_unproved")
        elif geolocate_interpretation(query.query_text, query.field_key).value != anchor.value:
            raise StaleWork("derivation_locked_anchor_unproved")


def _typed_command(specimen, supplied=None):
    from .derivation_contracts import DerivationCommand

    saved = specimen.run.dependencies.get(COMMAND_KEY)
    if saved is None:
        raise StaleWork("derivation_command_missing")
    command = DerivationCommand.model_validate(saved)
    if supplied is not None:
        supplied = DerivationCommand.model_validate(
            supplied.model_dump(mode="json") if isinstance(supplied, DerivationCommand) else supplied)
        if supplied != command:
            raise StaleWork("derivation_command_changed")
    if (command.status != "queued" or command.blocked_reason is not None
            or specimen.version != command.queued_revision
            or specimen.run.id != command.canonical_run_id
            or any(item.revision != command.source_revision for item in command.inputs)):
        raise StaleWork("derivation_input_revision_changed")
    return command


def _progress(runtime, command, *, status=None, checkpoint_ids=(), blocked_reason=None):
    """One lease-fenced CAS owns progress; a terminal result is immutable."""
    def reduce(state, now):
        job = runtime.store._lease(state, runtime.scope, runtime.lease, now)
        if (job["record_revision"] != command.queued_revision
                or job["binding_digest"] != digest(job["pins"])):
            raise StaleWork("derivation_job_binding_changed")
        dependencies = job["dependencies"]
        previous_id = dependencies.get("derivation_request_id")
        if previous_id not in {None, command.id}:
            raise StaleWork("derivation_command_changed")
        previous = dependencies.get(RESULT_KEY)
        if previous is not None and (not isinstance(previous, dict)
                or set(previous) != {"request_id", "status", "checkpoint_ids", "blocked_reason"}
                or previous["request_id"] != command.id
                or previous["status"] not in {"running", "completed", "blocked"}
                or not isinstance(previous["checkpoint_ids"], list)):
            raise StaleWork("derivation_result_unproved")
        current = {job["fields"][str(key)]["checkpoint"]["id"]: (key, job["fields"][str(key)]["checkpoint"])
                   for key in command.requested_fields
                   if job["fields"].get(str(key), {}).get("checkpoint") is not None}

        def validate_ids(ids):
            if len(set(ids)) != len(ids) or not set(ids) <= set(current):
                raise StaleWork("derivation_checkpoint_unproved")
            for identifier in ids:
                key, checkpoint = current[identifier]
                if (checkpoint.get("scope") != runtime.scope.identity()
                        or checkpoint["payload"].get("resolution", {}).get("reason")
                            != "derivation_request:" + command.id
                        or not checkpoint.get("receipt_ids")):
                    raise StaleWork("derivation_checkpoint_unproved")
                captures = [state["effects"].get(effect_id, {}) for effect_id in checkpoint["receipt_ids"]]
                if not any(effect.get("scope") == runtime.scope.identity()
                        and effect.get("field_keys") == [str(key)] and effect.get("status") == "completed"
                        and effect.get("operation_key", "").startswith(OPERATION_PREFIX)
                        and (effect.get("receipt") or {}).get("typed_payload", {}).get("coverage", {}).get("source_id")
                            == "georeference_spatial"
                        and effect["receipt"]["typed_payload"]["coverage"].get("field_key") == str(key)
                        for effect in captures):
                    raise StaleWork("derivation_checkpoint_unproved")

        if previous is not None:
            validate_ids(previous["checkpoint_ids"])
        if previous is not None and previous["status"] in {"completed", "blocked"}:
            if status is not None and previous != {
                    "request_id": command.id, "status": status,
                    "checkpoint_ids": list(checkpoint_ids), "blocked_reason": blocked_reason}:
                raise StaleWork("derivation_terminal_result_changed")
            return copy.deepcopy(previous)
        selected = status or "running"
        ids = tuple(previous["checkpoint_ids"]) if status is None and previous is not None else tuple(checkpoint_ids)
        if previous is not None and not set(previous["checkpoint_ids"]) <= set(ids):
            raise StaleWork("derivation_progress_cannot_forget_checkpoints")
        validate_ids(ids)
        outcome = DerivationWorkerOutcome(request_id=command.id, status=selected,
            checkpoint_ids=ids, blocked_reason=blocked_reason)
        result = outcome.model_dump(mode="json")
        dependencies["derivation_request_id"] = command.id
        dependencies[RESULT_KEY] = result
        return copy.deepcopy(result)
    return runtime.store._mutate(runtime.scope, reduce, lease=runtime.lease)


class ResearchDerivationWorker:
    def __init__(self, runtime_factory, *, input_blobs):
        self.runtime_factory = runtime_factory
        self.repository = runtime_factory.repository
        self.input_blobs = input_blobs

    def _selected_seed(self, command, anchor):
        """A retained selection only seeds a new lookup; its outcome is unchanged."""
        item = next(item for item in command.inputs if item.field_key == anchor.field_key)
        raw = self.input_blobs.get_bounded(item.provenance_blob_ref, MAX_INPUT_PROVENANCE_BYTES)
        if hashlib.sha256(raw).hexdigest() != item.provenance_sha256:
            raise StaleWork("derivation_input_provenance_changed")
        selection = json.loads(raw).get("source_selection")
        if not selection or selection.get("source_id") != "geolocate":
            return None
        result = SourceResult.model_validate(selection["source_result"])
        candidate = selection["source_candidate"]
        if (result.status not in {LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS}
                or result.coverage.field_key != anchor.field_key
                or result.coverage.source_id != "geolocate"
                or candidate.get("value") != anchor.value
                or candidate.get("field_key") != str(anchor.field_key)
                or candidate.get("authority_id") != anchor.authority_id
                or (anchor.field_key == FieldKey.CITY
                    and comparison_key(candidate.get("match_name", "")) != comparison_key(anchor.value))
                or (anchor.field_key == FieldKey.PROVINCE_STATE
                    and comparison_key(candidate.get("match_admin", "")) != comparison_key(anchor.value))
                or any(type(candidate.get(key)) not in {int, float}
                    or not math.isfinite(candidate[key]) for key in ("decimal_latitude", "decimal_longitude"))
                or not any(json.loads(value) == candidate for value in result.candidate_json)):
            raise StaleWork("derivation_validation_seed_unproved")
        return {"place": candidate["match_name"],
            "latitude": candidate["decimal_latitude"], "longitude": candidate["decimal_longitude"]}

    async def _validation_query(self, runtime, context, request, anchor, country):
        adapter = runtime.derivation_services.adapter
        seed = self._selected_seed(context.command, anchor)
        if seed is None:
            history_query = SourceQuery(source_id="georeference_history",
                field_key=anchor.field_key,
                query_text=json.dumps({"country": country, "name": anchor.value}))
            context._anchor_queries[("georeference_history", anchor.field_key)] = history_query
            history = await runtime.derivation_services.broker.validate_locked_anchor(request, history_query,
                anchor=anchor, command_digest=digest(context.command))
            await asyncio.to_thread(_source_receipt, runtime, request, history, "georeference_history", anchor.field_key)
            if history.status != LookupStatus.SUCCESS:
                raise _DerivationBlocked("derivation_history_" + str(history.status))
            if len(history.candidate_json) != 1:
                raise StaleWork("derivation_validation_seed_unproved")
            candidate = json.loads(history.candidate_json[0])
            if candidate.get("confirmed") is True or "hypothesis" in candidate:
                raise _DerivationBlocked("derivation_curated_seed_requires_modern_source")
            if candidate.get("match_type") == "near_spelling":
                raise _DerivationBlocked("derivation_history_exact_seed_unavailable")
            point = candidate.get("point")
            kinds = [item.get("id", "") for item in candidate.get("kinds", ())]
            if (candidate.get("match_type") != "exact" or not isinstance(point, list) or len(point) != 2
                    or any(type(value) not in {int, float} or not math.isfinite(value) for value in point)
                    or candidate.get("source") != "geonames"
                    or candidate.get("authority_id") != "geonames:" + str(candidate.get("record_id", ""))
                    or (candidate.get("country") or {}).get("id") != country
                    or not any(item.kind == "qualified_dataset"
                        and item.source_version == candidate.get("dataset_id")
                        and item.response_digest == candidate.get("source_digest") for item in history.evidence)):
                raise StaleWork("derivation_validation_seed_unproved")
            if (not any(kind.startswith("P.") for kind in kinds)
                    or (anchor.field_key == FieldKey.PROVINCE_STATE
                        and not any(comparison_key(parent.get("name") or "") == comparison_key(anchor.value)
                            for parent in candidate.get("parents", ())))):
                raise _DerivationBlocked("derivation_history_seed_unqualified")
            seed = {"place": candidate["name"], "latitude": point[0], "longitude": point[1]}
        point = (seed["latitude"], seed["longitude"])
        level = adapter.field_levels[country][anchor.field_key]
        try:
            boundaries = await asyncio.to_thread(adapter._boundaries, country)
        except (OSError, ValueError, KeyError):
            raise _DerivationBlocked("derivation_qualified_boundary_unavailable") from None
        units = [unit for unit in boundaries if unit.level == level
                 and comparison_key(unit.name) == comparison_key(anchor.value) and inside(unit.shape, point)]
        if len(units) != 1:
            raise _DerivationBlocked("derivation_validation_footprint_unavailable")
        for item in context.settled_inputs:
            item_level = adapter.field_levels[country].get(item.field_key)
            if item_level is not None and len([unit for unit in boundaries if unit.level == item_level
                    and comparison_key(unit.name) == comparison_key(item.value) and inside(unit.shape, point)]) != 1:
                raise _DerivationBlocked("derivation_validation_footprint_conflict")
        # This bound controls only the validator's search around a real seed.
        # The final uncertainty is computed separately from the complete pinned
        # footprint and is never truncated to this provider search limit.
        try:
            radius_km = min(50.0, max(1.0, extent(units[0]).radial_m / 1000))
        except (ValueError, TypeError, KeyError):
            raise _DerivationBlocked("derivation_qualified_boundary_invalid") from None
        fields = {item.field_key: item.value for item in context.settled_inputs}
        country_name = {"PH": "Philippines", "GT": "Guatemala"}[country]
        arguments = {**seed, "country": country_name, "state": fields.get(FieldKey.PROVINCE_STATE, ""),
            "county": fields.get(FieldKey.COUNTY, ""), "locality": seed["place"],
            "value": anchor.value, "radius_km": radius_km}
        query = SourceQuery(source_id="geolocate", field_key=anchor.field_key,
            query_text=json.dumps(arguments, sort_keys=True, separators=(",", ":")))
        context._anchor_queries[("geolocate", anchor.field_key)] = query
        return query

    def _verify(self, principal, specimen_id, command=None):
        from .derivation_contracts import DERIVATION_RULE_VERSION, DerivationRequest

        specimen = self.repository.get(principal.scope, specimen_id)
        if (principal.role not in WORKER_ROLES or not principal.user_id
                or specimen.scope != principal.scope or specimen.id != specimen_id
                or specimen.asset.sensitive is not False):
            raise PermissionError("derivation_access_denied")
        command = _typed_command(specimen, command)
        if DERIVATION_RULE_VERSION != VERSION:
            raise StaleWork("derivation_rule_version_changed")
        request = DerivationRequest(expected_record_revision=command.source_revision,
            base_record_version_id=f"{command.canonical_run_id}:{command.source_revision}",
            requested_fields=command.requested_fields, reason=command.reason)
        if digest(request) != command.request_digest:
            raise StaleWork("derivation_request_digest_changed")
        source = self.repository.version_info(principal.scope, specimen_id, command.source_revision)
        if (source.get("revision") != command.source_revision
                or source.get("sha256") != command.source_snapshot_sha256
                or source.get("run_id") != command.canonical_run_id):
            raise StaleWork("derivation_source_snapshot_changed")
        expected_id = digest({"actor": command.actor_uid,
            "scope": principal.scope.model_dump(mode="json"), "specimen_id": specimen_id,
            "run_id": command.canonical_run_id, "revision": command.source_revision,
            "snapshot_sha256": command.source_snapshot_sha256, "key": command.idempotency_key,
            "request": command.request_digest})
        if expected_id != command.id:
            raise StaleWork("derivation_command_identity_changed")
        from .derivation_inputs import genuine_human_locked_fields, verify_settled_inputs

        verify_settled_inputs(self.repository, specimen, self.input_blobs, command.inputs)
        locks = set(genuine_human_locked_fields(self.repository, specimen))
        if (set(command.human_locked_fields) != locks | {item.field_key for item in command.inputs}
                or any(key not in specimen.run.fields
                    or specimen.run.fields[key].state == ValueState.SUPPORTED
                    for key in command.requested_fields)):
            raise StaleWork("derivation_targets_changed")
        settled = tuple(SettledLocationInput(item.field_key, item.value, item.evidence_ids,
            item.revision, item.authority_id) for item in command.inputs)
        return DerivationContext(command, specimen, settled, self, principal)

    async def run_registered(self, principal, specimen_id, *, owner, command=None):
        principal = Principal.model_validate(principal.model_dump(mode="json"))
        context = await asyncio.to_thread(self._verify, principal, specimen_id, command)
        runtime = await self.runtime_factory.open(principal, specimen_id, owner=owner,
            derivation_context=context)
        outcome, known_failure = None, False
        try:
            outcome = await self.consume(runtime, principal, context)
            return outcome
        except StaleWork:
            known_failure = True
            raise
        finally:
            # Cancellation or an uncertain send retains custody. The store also
            # refuses release when any effect outcome or actual cost is unknown.
            if outcome is not None or known_failure:
                try:
                    await asyncio.to_thread(runtime.store.release, runtime.scope, runtime.lease)
                except (HeldUnknown, StaleWork):
                    pass

    async def consume(self, runtime, principal, context):
        """Consume only the exact freshly verified command using this existing lease."""
        try:
            return await self._consume(runtime, principal, context)
        except _DerivationBlocked as error:
            previous = await asyncio.to_thread(_progress, runtime, context.command)
            return DerivationWorkerOutcome.model_validate(await asyncio.to_thread(_progress,
                runtime, context.command, status="blocked", checkpoint_ids=previous["checkpoint_ids"],
                blocked_reason=str(error)))

    async def _validate_retained(self, runtime, command, progress):
        request = await asyncio.to_thread(_request, runtime, command.requested_fields[0])
        loaded = {item.field_key: item for item in await runtime.journal.load(request.scope)}
        document = await asyncio.to_thread(runtime.store._read, runtime.scope)
        job = runtime.store._job(document.state, runtime.scope)
        for key in command.requested_fields:
            native = job["fields"][str(key)]["checkpoint"]
            if native is None or native["id"] not in progress["checkpoint_ids"]:
                continue
            typed = loaded.get(key)
            if typed is None or typed.model_dump(mode="json") != native["payload"]:
                raise StaleWork("derivation_checkpoint_unproved")
            matching = [(effect_id, effect["receipt"]["typed_payload"]) for effect_id in native["receipt_ids"]
                if (effect := document.state["effects"].get(effect_id, {})).get("receipt")
                and effect["receipt"]["typed_payload"].get("coverage", {}).get("source_id") == "georeference_spatial"]
            if len(matching) != 1:
                raise StaleWork("derivation_checkpoint_unproved")
            effect_id, payload = matching[0]
            retained_request, validation_id = await asyncio.to_thread(_spatial_capture, runtime, command, effect_id)
            if retained_request.field_revisions.get(key) != typed.revision - 1:
                raise StaleWork("derivation_checkpoint_unproved")
            result = SourceResult.model_validate(payload)
            tool_id = await asyncio.to_thread(_validation_tool, runtime, command, result)
            if tool_id is not None and tool_id != validation_id:
                raise StaleWork("derivation_validation_tool_unproved")
            if _resolution(command, key, result, validation_tool_id=tool_id) != typed.resolution:
                raise StaleWork("derivation_checkpoint_unproved")

    async def _consume(self, runtime, principal, context):
        command = context.command
        current = await asyncio.to_thread(self._verify, principal, context.specimen.id, command)
        services = getattr(runtime, "derivation_services", None)
        binding = runtime.binding
        if (services is None or services.context is not context
                or runtime.scope.sensitive or runtime.scope.actor_uid != principal.user_id
                or runtime.scope.specimen_id != context.specimen.id
                or runtime.scope.organization_id != principal.scope.organization_id
                or runtime.scope.collection_id != principal.scope.collection_id
                or binding.canonical.record_revision != command.queued_revision
                or str(binding.canonical.canonical_run_id) != command.canonical_run_id
                or current.settled_inputs != context.settled_inputs):
            raise StaleWork("derivation_runtime_binding_changed")
        progress = await asyncio.to_thread(_progress, runtime, command)
        if progress["status"] in {"completed", "blocked"}:
            await self._validate_retained(runtime, command, progress)
            return DerivationWorkerOutcome.model_validate(progress)
        checkpoint_ids = list(progress["checkpoint_ids"])
        job = await asyncio.to_thread(runtime.store.job, runtime.scope)
        remaining = []
        for key in command.requested_fields:
            state = job["fields"].get(str(key))
            if state is None or state["locked"] or state.get("retry_command_id"):
                raise StaleWork("derivation_target_locked_or_unavailable")
            native = state["checkpoint"]
            if native is not None and native["payload"].get("resolution", {}).get("reason") == "derivation_request:" + command.id:
                # A prior commit may have lost its acknowledgment. The native
                # typed journal and progress CAS prove it before acknowledging.
                typed = FieldCheckpoint.model_validate(native["payload"])
                loaded = await runtime.journal.load(typed.scope)
                if typed not in loaded:
                    raise StaleWork("derivation_checkpoint_unproved")
                if native["id"] not in checkpoint_ids:
                    checkpoint_ids.append(native["id"])
            else:
                remaining.append(key)
        if checkpoint_ids:
            await self._validate_retained(runtime, command, {"checkpoint_ids": checkpoint_ids})
        if not remaining:
            return DerivationWorkerOutcome.model_validate(await asyncio.to_thread(_progress,
                runtime, command, status="completed", checkpoint_ids=checkpoint_ids))
        country = _country(context)
        anchor = _anchor(context, services.adapter, country)
        request = await asyncio.to_thread(_request, runtime, anchor.field_key)
        query = await self._validation_query(runtime, context, request, anchor, country)
        command_digest = digest(command)
        validation = await services.broker.validate_locked_anchor(request, query,
            anchor=anchor, command_digest=command_digest)
        await asyncio.to_thread(_source_receipt, runtime, request, validation, "geolocate", anchor.field_key)
        if validation.status != LookupStatus.SUCCESS:
            return DerivationWorkerOutcome.model_validate(await asyncio.to_thread(_progress,
                runtime, command, status="blocked", checkpoint_ids=checkpoint_ids,
                blocked_reason="derivation_geolocate_not_successful"))
        fields = {item.field_key: item.value for item in context.settled_inputs}
        locality = "; ".join(_raw_locality(context.specimen)
            or (fields.get(FieldKey.PRECISE_LOCATION, anchor.value),))
        for key in remaining:
            request = await asyncio.to_thread(_request, runtime, key)
            context.verify_current(request, command_digest, context.settled_inputs, command.requested_fields)
            result = await services.broker.derive_spatial_from_trusted_inputs(request, field_key=key,
                country=country, validation=validation, settled_inputs=context.settled_inputs,
                requested_fields=command.requested_fields, verbatim_locality=locality,
                label_has_elevation=_label_elevation(context.specimen),
                tool_call_id=validation.receipt.id, command_digest=command_digest)
            effect_id = await asyncio.to_thread(_source_receipt, runtime, request, result, "georeference_spatial", key)
            captured_request, validation_id = await asyncio.to_thread(_spatial_capture, runtime, command, effect_id)
            if captured_request != request or validation_id != validation.receipt.id:
                raise StaleWork("derivation_spatial_capture_unproved")
            tool_id = await asyncio.to_thread(_validation_tool, runtime, command, result)
            if tool_id is not None and tool_id != validation.receipt.id:
                raise StaleWork("derivation_validation_tool_unproved")
            resolution = _resolution(command, key, result, validation_tool_id=tool_id)
            context.verify_current(request, command_digest, context.settled_inputs, command.requested_fields)
            await runtime.journal.commit(request, (resolution,), receipt_ids=(effect_id,),
                model_settings_digest=digest(job["pins"]["settings"]))
            saved = await asyncio.to_thread(runtime.store.job, runtime.scope)
            checkpoint_ids.append(saved["fields"][str(key)]["checkpoint"]["id"])
            await asyncio.to_thread(_progress, runtime, command,
                status="running", checkpoint_ids=checkpoint_ids)
        return DerivationWorkerOutcome.model_validate(await asyncio.to_thread(_progress,
            runtime, command, status="completed", checkpoint_ids=checkpoint_ids))


DerivationWorker = ResearchDerivationWorker
