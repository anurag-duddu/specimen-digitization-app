"""Service-owned capture before the ordinary source broker discards bytes.

SOURCE ONLY, UNRUN. Construction confers no live spending or native admission.
The request envelope is not the original response body. Native V1 must HOLD.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from typing import Literal

from pydantic import Field, ValidationError, model_validator

from .compatibility import PublicationUnavailable
from .contracts import Digest, FrozenRecord, SourceQuery, SourceResult, SpecialistRequest, ToolReceipt, digest
from .persistence import BlobRef, CapturedResult, HeldUnknown, StaleWork
from .publication import NativeCapture
from .sources import (
    BoundedHTTPTransport, FixtureSourceTransport, PUBLIC_METADATA_POLICY,
    SourceBroker, SourcePolicy, SourceRegistry, canonical_json, result_envelope,
    validate_destination,
)

CAPTURE_VERSION = "research-source-request-envelope/v2"
OPERATION_PREFIX = "source_capture_v2:"
MAX_REQUEST_BYTES = 512_000
MAX_ENVELOPE_BYTES = 1_000_000


def unavailable(code="research_source_capture_unavailable"):
    raise PublicationUnavailable(code)


def typed(model, value):
    """No persisted input or validation details escape a failure boundary."""
    try:
        return model.model_validate(value)
    except (ValidationError, ValueError, TypeError):
        unavailable()


class RegisteredCapturePolicyV2(FrozenRecord):
    contract_version: Literal["source-capture-retention/v2"] = "source-capture-retention/v2"
    source_id: str = Field(min_length=1)
    source_policy_digest: Digest
    kind: Literal["full_response", "pinned_dataset", "computed", "denied"]
    owner_registration_digest: Digest
    owner_registration_origin: str = Field(min_length=1)
    maximum_responses: int = Field(strict=True, ge=1, le=3)


class CapturedTransportResponseV2(FrozenRecord):
    ordinal: int = Field(strict=True, ge=1, le=3)
    url: str = Field(min_length=1, max_length=8192)
    status_code: int = Field(strict=True, ge=100, le=599)
    source_policy_digest: Digest
    response_fingerprint: Digest
    body: NativeCapture

    @model_validator(mode="after")
    def body_fingerprint(self):
        if self.body.sha256 != self.response_fingerprint:
            raise ValueError("response_body_fingerprint_changed")
        return self


def logical_request_v2(request, query, policy, *, command_digest=None):
    logical = {
        "contract_version": CAPTURE_VERSION, "tool_id": "source_lookup",
        "arguments": query.model_dump(mode="json"), "scope": request.scope.model_dump(mode="json"),
        "field_revision": request.field_revisions.get(query.field_key, 0),
        "prompt_digest": request.prompt.digest, "source_registry_digest": request.prompt.source_registry_digest,
        "original_request_digest": digest(request), "capture_policy_digest": digest(policy),
        "source_policy_digest": policy.source_policy_digest,
        "purpose_policy": PUBLIC_METADATA_POLICY if query.source_id == "field_museum_ipt" else "insects-research-v1",
    }
    if command_digest is not None:
        logical["trusted_derivation_command_digest"] = command_digest
    return logical


class SourceRequestEnvelopeV2(FrozenRecord):
    contract_version: Literal["research-source-request-envelope/v2"] = CAPTURE_VERSION
    original_request: SpecialistRequest
    query: SourceQuery
    policy: RegisteredCapturePolicyV2
    trusted_command_digest: Digest | None = None
    logical_request: dict
    effect_id: Digest
    attempt_id: str = Field(min_length=1)
    binding_digest: Digest
    semantic_result_digest: Digest
    responses: tuple[CapturedTransportResponseV2, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def original_context(self):
        if (self.policy.kind != "full_response" or self.policy.source_id != self.query.source_id
            or self.query.field_key not in self.original_request.field_keys
            or self.logical_request != logical_request_v2(self.original_request, self.query, self.policy,
                command_digest=self.trusted_command_digest)
            or len(self.responses) > self.policy.maximum_responses
            or tuple(item.ordinal for item in self.responses) != tuple(range(1, len(self.responses) + 1))
            or any(item.source_policy_digest != self.policy.source_policy_digest for item in self.responses)):
            raise ValueError("source_request_capture_context_changed")
        return self


@dataclass
class _CaptureSession:
    request: SpecialistRequest
    query: SourceQuery
    policy: RegisteredCapturePolicyV2
    binding_digest: str
    effect_id: str
    attempt_id: str
    validate: object
    transport: object
    responses: list = field(default_factory=list)


_session: ContextVar[_CaptureSession | None] = ContextVar("research_source_capture_v2", default=None)


@dataclass(frozen=True)
class _TrustedLockedRead:
    effects: object
    request_digest: str
    query_digest: str
    anchor: object
    command_digest: str


_trusted_locked_read: ContextVar[_TrustedLockedRead | None] = ContextVar(
    "research_trusted_locked_anchor_read", default=None)


class CapturedSourceTransportV2:
    """One exact underlying transport and one admitted sending effect per GET."""
    def __init__(self, transport, blobs, *, execution_class):
        expected = FixtureSourceTransport if execution_class == "offline" else BoundedHTTPTransport
        if execution_class not in {"offline", "live"} or type(transport) is not expected:
            unavailable("source_capture_transport_class_denied")
        self.transport, self.blobs, self.execution_class = transport, blobs, execution_class
        self.original_transport = transport

    async def get(self, url, *, policy):
        session = _session.get()
        expected = FixtureSourceTransport if self.execution_class == "offline" else BoundedHTTPTransport
        if (session is None or session.transport is not self or self.transport is not self.original_transport
            or type(self.transport) is not expected or session.policy.source_id != policy.id
            or session.policy.source_policy_digest != digest(policy)
            or session.policy.kind != "full_response" or not policy.ready
            or policy.paid or policy.credentials_required
            or len(session.responses) >= session.policy.maximum_responses):
            unavailable("source_capture_transport_not_admitted")
        session.validate()
        validate_destination(policy, url)
        code, body = await self.transport.get(url, policy=policy)
        if type(code) is not int or not isinstance(body, bytes) or len(body) > policy.max_response_bytes:
            unavailable("source_capture_transport_bound_changed")
        ordinal = len(session.responses) + 1
        locator = (f"research-capture/{digest(session.request.scope.model_dump(mode='json'))}/"
                   f"{session.effect_id}/{session.attempt_id}/source-body/{ordinal}")
        reference = await asyncio.to_thread(self.blobs.put_at, locator, body)
        if reference.sha256 != hashlib.sha256(body).hexdigest() or reference.byte_size != len(body):
            unavailable("source_capture_body_write_unproved")
        session.responses.append(CapturedTransportResponseV2(
            ordinal=ordinal, url=url, status_code=code, source_policy_digest=digest(policy),
            response_fingerprint=reference.sha256, body=NativeCapture(**asdict(reference))))
        return code, body


class SourceCaptureEffectsV2:
    """Durable source-effect gates with actual original-request/body retention."""
    def __init__(self, broker, scope, lease, registry, policies, transport, *, reservation_micro_usd=1,
                 derivation_context=None):
        if type(reservation_micro_usd) is not int or reservation_micro_usd <= 0:
            unavailable("source_capture_reservation_invalid")
        if type(scope.generation) is not int or scope.generation < 1 or type(scope.sensitive) is not bool:
            unavailable("source_capture_scope_type_invalid")
        self.broker, self.scope, self.lease = broker, scope, lease
        self.registry, self.transport = registry, transport
        self.derivation_context = derivation_context
        self.original_transport, self.execution_class = transport.transport, transport.execution_class
        self.policies = {key: typed(RegisteredCapturePolicyV2, value.model_dump(mode="json")) for key, value in policies.items()}
        if any(key != value.source_id for key, value in self.policies.items()):
            unavailable("source_capture_policy_key_changed")
        self.reservation_micro_usd = reservation_micro_usd

    def _locked_anchor(self, request, query):
        proof = _trusted_locked_read.get()
        if (proof is None or proof.effects is not self or self.derivation_context is None
            or proof.request_digest != digest(request) or proof.query_digest != digest(query)):
            return None
        self.derivation_context.verify_locked_anchor(
            request, query, proof.anchor, proof.command_digest)
        return proof

    async def _execute_source_effect(self, request, query, logical, operation_key, dispatch, trusted):
        if trusted is None:
            return await self.broker.execute(self.scope, self.lease, operation_key, logical,
                self.reservation_micro_usd, dispatch, execution_class=self.transport.execution_class,
                field_keys=(str(query.field_key),))
        # The store owns the last locked-field gate. Astra's private context
        # rechecks the same immutable command before reserve, send and dispatch;
        # a model cannot set it by adding a JSON flag.
        from .persistence import _trusted_locked_source_read

        def verify_current():
            self.derivation_context.verify_locked_anchor(
                request, query, trusted.anchor, trusted.command_digest)

        with _trusted_locked_source_read(self.broker, self.scope, operation_key, logical,
                field_key=str(query.field_key), source_id=query.source_id,
                command_digest=trusted.command_digest, verify_current=verify_current):
            return await self.broker.execute(self.scope, self.lease, operation_key, logical,
                self.reservation_micro_usd, dispatch, execution_class=self.transport.execution_class,
                field_keys=(str(query.field_key),))

    def validate_transport(self, transport):
        expected = FixtureSourceTransport if self.execution_class == "offline" else BoundedHTTPTransport
        if (transport is not self.transport or transport.transport is not self.original_transport
            or transport.execution_class != self.execution_class or type(transport.transport) is not expected):
            unavailable("source_capture_transport_changed")

    async def __call__(self, request, tool_id, arguments, invoke):
        request = typed(SpecialistRequest, request.model_dump(mode="json"))
        query = typed(SourceQuery, arguments)
        policy = self.policies.get(query.source_id)
        source = self.registry.get(query.source_id)
        if (tool_id != "source_lookup" or query.field_key not in request.field_keys
            or policy is None or policy.kind != "full_response"
            or policy.source_policy_digest != digest(source) or not source.ready
            or source.paid or source.credentials_required or request.scope.sensitive):
            unavailable("source_capture_retention_not_registered")
        if any(value != getattr(request.scope, key) for key, value in self.scope.identity().items()) or self.scope.sensitive != request.scope.sensitive:
            raise PermissionError("source_capture_scope_denied")
        if request.prompt.source_registry_digest != self.registry.digest or len(canonical_json(request.model_dump(mode="json")).encode()) > MAX_REQUEST_BYTES:
            unavailable("source_capture_request_pin_changed")
        trusted = self._locked_anchor(request, query)
        logical = logical_request_v2(request, query, policy,
            command_digest=trusted.command_digest if trusted is not None else None)
        operation_key = OPERATION_PREFIX + digest(logical)
        policy_pins = {key: item.model_dump(mode="json") for key, item in self.policies.items()}
        field_revision = request.field_revisions.get(query.field_key, 0)

        def validate_current():
            self.validate_transport(self.transport)
            document = self.broker.store._read(self.scope)
            job = self.broker.store._lease(document.state, self.scope, self.lease, document.server_time)
            pins = job["pins"]
            if (digest(pins) != job["binding_digest"]
                or pins["input_digest"] != request.scope.input_digest or digest(pins["profile"]) != request.scope.profile_digest
                or pins["prompts"].get(str(request.role)) != request.prompt.model_dump(mode="json")
                or pins["sources"].get("registry_digest") != self.registry.digest
                or pins["sources"].get("capture_policies") != policy_pins):
                raise PermissionError("source_capture_immutable_pins_changed")
            if query.join is not None and pins["sources"].get("exact_specimen_joins", {}).get(query.source_id) != query.join.model_dump(mode="json"):
                raise PermissionError("source_capture_exact_specimen_join_unproved")
            current = job["fields"].get(str(query.field_key))
            locked_read = self._locked_anchor(request, query)
            if (not current or current["revision"] != field_revision
                or current["locked"] and locked_read is None):
                raise StaleWork("source_capture_field_revision_or_lock_changed")
            for effect in document.state["effects"].values():
                if effect["job_key"] != self.scope.key or str(query.field_key) not in effect["field_keys"]:
                    continue
                if effect["scope"] == self.scope.identity() and effect["operation_key"] == operation_key:
                    continue
                if effect["status"] in {"sending", "held_unknown"} or effect["receipt"] is not None and effect["actual_micro_usd"] is None:
                    raise HeldUnknown("source_capture_field_has_unreconciled_effect")
            return job["binding_digest"]

        validate_current()

        async def dispatch(attempt_id, effect_id):
            binding_digest = validate_current()
            effect = self.broker.store.effect(self.scope, effect_id)
            attempts = [row for row in effect["attempts"] if row["attempt_id"] == attempt_id]
            if (effect["status"] != "sending" or effect["operation_key"] != operation_key
                or effect["request_digest"] != digest(logical) or effect["binding_digest"] != binding_digest
                or effect["scope"] != self.scope.identity() or len(attempts) != 1
                or attempts[0]["status"] != "sending" or attempts[0]["provider_idempotency_key"] != effect_id):
                unavailable("source_capture_sending_attempt_unproved")
            def validate_session():
                if validate_current() != binding_digest:
                    unavailable("source_capture_sending_binding_changed")
                self.broker.store.validate_dispatch(self.scope, self.lease, effect_id, attempt_id)
            session = _CaptureSession(request, query, policy, binding_digest, effect_id, attempt_id, validate_session, self.transport)
            token = _session.set(session)
            try:
                raw = await invoke()
                if not isinstance(raw, str) or len(raw.encode()) > 32768:
                    unavailable("source_capture_semantic_bound_changed")
                result = typed(SourceResult, json.loads(raw))
                if (result.coverage.source_id != query.source_id or result.coverage.field_key != query.field_key
                    or result.coverage.qualification_digest != policy.source_policy_digest):
                    unavailable("source_capture_semantic_context_changed")
                envelope = SourceRequestEnvelopeV2(
                    original_request=request, query=query, policy=policy, logical_request=logical,
                    trusted_command_digest=trusted.command_digest if trusted is not None else None,
                    effect_id=effect_id, attempt_id=attempt_id, binding_digest=binding_digest,
                    semantic_result_digest=hashlib.sha256(result_envelope(result).encode()).hexdigest(),
                    responses=tuple(session.responses))
                captured = canonical_json(envelope.model_dump(mode="json")).encode()
                if len(captured) > MAX_ENVELOPE_BYTES:
                    unavailable("source_capture_envelope_bound_changed")
                return CapturedResult(typed_payload=result.model_dump(mode="json"), raw_payload=captured,
                    actual_micro_usd=0, usage={"source_requests": len(session.responses), "semantic_bytes": len(raw.encode())})
            finally:
                _session.reset(token)

        durable = await self._execute_source_effect(
            request, query, logical, operation_key, dispatch, trusted)
        effect = self.broker.store.effect(self.scope, durable.effect_id)
        result = typed(SourceResult, durable.typed_payload)
        return tool_receipt_v2(request, query, effect, result)

    async def local_lookup(self, request, query, invoke):
        """Durably retain a pinned-dataset lookup without pretending it sent HTTP.

        The adapter checks the original object bytes against the manifest; the
        capture keeps the exact original request, result, and dataset evidence
        IDs. A missing object stays an operational failed source result.
        """
        request = typed(SpecialistRequest, request.model_dump(mode="json"))
        query = typed(SourceQuery, query.model_dump(mode="json"))
        source = self.registry.get(query.source_id)
        policy = self.policies.get(query.source_id)
        if (query.source_id != "georeference_history" or source.source_type != "local_dataset"
            or policy is None or policy.kind != "pinned_dataset"
            or policy.source_policy_digest != digest(source) or not source.ready
            or request.scope.sensitive or query.field_key not in request.field_keys
            or request.prompt.source_registry_digest != self.registry.digest
            or len(canonical_json(request.model_dump(mode="json")).encode()) > MAX_REQUEST_BYTES):
            unavailable("source_capture_pinned_dataset_not_registered")
        if (any(value != getattr(request.scope, key) for key, value in self.scope.identity().items())
            or self.scope.sensitive != request.scope.sensitive):
            raise PermissionError("source_capture_scope_denied")
        trusted = self._locked_anchor(request, query)
        if trusted is None:
            raise PermissionError("Pinned historical lookup requires a trusted locked anchor")
        logical = {"contract_version": "research-pinned-dataset-request/v1",
                   "tool_id": "source_lookup", "query": query.model_dump(mode="json"),
                   "scope": request.scope.model_dump(mode="json"), "original_request_digest": digest(request),
                   "field_revision": request.field_revisions.get(query.field_key, 0),
                   "prompt_digest": request.prompt.digest,
                   "source_registry_digest": request.prompt.source_registry_digest,
                   "source_policy_digest": digest(source), "capture_policy_digest": digest(policy)}
        if trusted is not None:
            logical["trusted_derivation_command_digest"] = trusted.command_digest
        operation_key = OPERATION_PREFIX + digest(logical)
        field_revision = request.field_revisions.get(query.field_key, 0)
        policy_pins = {key: item.model_dump(mode="json") for key, item in self.policies.items()}

        def validate_current():
            document = self.broker.store._read(self.scope)
            job = self.broker.store._lease(document.state, self.scope, self.lease, document.server_time)
            pins = job["pins"]
            if (digest(pins) != job["binding_digest"]
                or pins["input_digest"] != request.scope.input_digest
                or digest(pins["profile"]) != request.scope.profile_digest
                or pins["prompts"].get(str(request.role)) != request.prompt.model_dump(mode="json")
                or pins["sources"].get("registry_digest") != self.registry.digest
                or pins["sources"].get("capture_policies") != policy_pins):
                raise PermissionError("source_capture_immutable_pins_changed")
            current = job["fields"].get(str(query.field_key))
            locked_read = self._locked_anchor(request, query)
            if (not current or current["revision"] != field_revision
                or current["locked"] and locked_read is None):
                raise StaleWork("source_capture_field_revision_or_lock_changed")
            for effect in document.state["effects"].values():
                if effect["job_key"] != self.scope.key or str(query.field_key) not in effect["field_keys"]:
                    continue
                if effect["scope"] == self.scope.identity() and effect["operation_key"] == operation_key:
                    continue
                if effect["status"] in {"sending", "held_unknown"} or (
                    effect["receipt"] is not None and effect["actual_micro_usd"] is None):
                    raise HeldUnknown("source_capture_field_has_unreconciled_effect")
            return job["binding_digest"]

        validate_current()

        async def dispatch(attempt_id, effect_id):
            binding_digest = validate_current()
            self.broker.store.validate_dispatch(self.scope, self.lease, effect_id, attempt_id)
            raw = await invoke()
            validate_current()
            if not isinstance(raw, str) or len(raw.encode()) > 32768:
                unavailable("source_capture_semantic_bound_changed")
            result = typed(SourceResult, json.loads(raw))
            if (result.coverage.source_id != query.source_id or result.coverage.field_key != query.field_key
                or result.coverage.source_version != source.source_release
                or result.coverage.qualification_digest != digest(source.source_release)):
                unavailable("source_capture_pinned_dataset_result_changed")
            envelope = canonical_json({"contract_version": "research-pinned-dataset-capture/v1",
                "original_request": request.model_dump(mode="json"), "query": query.model_dump(mode="json"),
                "logical_request": logical, "effect_id": effect_id, "attempt_id": attempt_id,
                "binding_digest": binding_digest, "semantic_result": result.model_dump(mode="json"),
                "dataset_evidence": [item.model_dump(mode="json") for item in result.evidence]})
            if len(envelope.encode()) > MAX_ENVELOPE_BYTES:
                unavailable("source_capture_envelope_bound_changed")
            return CapturedResult(typed_payload=result.model_dump(mode="json"), raw_payload=envelope.encode(),
                actual_micro_usd=0, usage={"pinned_dataset_reads": 1, "semantic_bytes": len(raw.encode())})

        durable = await self._execute_source_effect(
            request, query, logical, operation_key, dispatch, trusted)
        effect = self.broker.store.effect(self.scope, durable.effect_id)
        result = typed(SourceResult, durable.typed_payload)
        return tool_receipt_v2(request, query, effect, result)


def tool_receipt_v2(request, query, effect, result):
    saved = effect["receipt"]
    if (effect["status"] != "completed" or saved is None or saved["actual_micro_usd"] is None
        or type(saved["actual_micro_usd"]) is not int or saved["actual_micro_usd"] < 0
        or saved["held_micro_usd"] != 0 or saved["outcome"] != "completed"):
        raise HeldUnknown("source_capture_receipt_cost_unreconciled")
    raw = result_envelope(result)
    return ToolReceipt(id="effect:" + effect["effect_id"], scope=request.scope,
        tool_id="source_lookup", source_id=query.source_id, field_keys=(query.field_key,),
        effect_id=effect["effect_id"], attempt_ids=tuple(item["attempt_id"] for item in effect["attempts"]),
        request_digest=effect["request_digest"], binding_digest=effect["binding_digest"],
        outcome=result.status, effect_status="completed", evidence_ids=tuple(item.id for item in result.evidence),
        capture_locator=saved["capture"]["locator"], response_digest=saved["capture"]["sha256"],
        reservation_micro_usd=effect["reservation_micro_usd"], settled_micro_usd=saved["actual_micro_usd"],
        held_micro_usd=saved["held_micro_usd"], result_json=raw, result_digest=hashlib.sha256(raw.encode()).hexdigest())


def verify_spatial_derivation_result(document, job_key, field_key, command, effect_id, blobs) -> SourceResult:
    """Prove every G38 result from original immutable computation and validator.

    This is a read-only predicate for the API and worker. The caller separately
    checks current canonical Q, source revision and review rights. Both the
    semantic effect envelope and original raw computation/GEOLocate captures
    are read by generation and SHA. Successful proposals and honest failed or
    empty lookups use the same proof boundary.
    """
    from .contracts import FieldKey
    from .persistence import CONTRACT_VERSION
    from .sources import geolocate_interpretation
    from specimen_digitization.application.domain import LookupStatus

    def refuse():
        raise ValueError("retained_spatial_derivation_capture_unproved")

    def read(reference):
        try:
            ref = BlobRef(**reference)
            if (not ref.locator.startswith("research-capture/") or not ref.generation
                or not 0 < ref.byte_size <= MAX_ENVELOPE_BYTES):
                refuse()
            body = blobs.get(ref)
            if len(body) != ref.byte_size or hashlib.sha256(body).hexdigest() != ref.sha256:
                refuse()
            return body
        except (TypeError, ValueError, OSError, KeyError):
            refuse()

    def parsed(body):
        try:
            value = json.loads(body)
            if canonical_json(value).encode() != body:
                refuse()
            return value
        except (TypeError, ValueError, UnicodeError):
            refuse()

    def predeclared_capture(effect, receipt):
        attempt = next((item for item in effect["attempts"]
            if item["attempt_id"] == receipt["attempt_id"]), None)
        if (attempt is None or attempt["status"] != "completed"
            or attempt["capture_locator"] != receipt["capture"]["locator"]
            or attempt["raw_capture_locator"] != receipt["raw_capture"]["locator"]
            or attempt.get("capture") != receipt["capture"]):
            refuse()

    try:
        field_key = FieldKey(field_key)
        state = document.state if hasattr(document, "state") else document["state"]
        effects = state["effects"]
        effect = effects[effect_id]
        saved = effect["receipt"]
        job = state["jobs"][job_key]
        if (effect["job_key"] != job_key or effect["status"] != "completed"
            or effect["field_keys"] != [str(field_key)] or not saved
            or saved["actual_micro_usd"] is None or saved["held_micro_usd"] != 0
            or not saved.get("raw_capture") or saved["outcome"] != "completed"):
            refuse()
        predeclared_capture(effect, saved)
        semantic = parsed(read(saved["capture"]))
        original = parsed(read(saved["raw_capture"]))
        request = SpecialistRequest.model_validate(original["original_request"])
        logical = original["logical_request"]
        result = SourceResult.model_validate(original["semantic_result"])
        command_digest = digest(command)
        settled = tuple({"field_key": str(item.field_key), "value": item.value,
            "evidence_ids": list(item.evidence_ids), "revision": item.revision,
            "authority_id": item.authority_id} for item in command.inputs)
        from specimen_digitization.application.georef_locality import comparison_key
        countries = [{"ph": "PH", "philippines": "PH", "gt": "GT", "guatemala": "GT"}.get(
            comparison_key(item.value)) for item in command.inputs
            if item.field_key == FieldKey.COUNTRY]
        validation_receipt = ToolReceipt.model_validate(original["validation_receipt"])
        scope_identity = {key: getattr(request.scope, key) for key in
            ("organization_id", "collection_id", "specimen_id", "job_id", "generation")}
        job_identity = {key: value for key, value in scope_identity.items() if key != "generation"}
        pins = job["pins"]
        source_policies = {row["id"]: row for row in pins["sources"]["registry_policies"]}
        spatial_policy = source_policies["georeference_spatial"]
        spatial_capture_policy = pins["sources"]["capture_policies"]["georeference_spatial"]
        current_field = job["fields"][str(field_key)]
        original_revision = request.field_revisions[field_key]
        checkpoint = current_field["checkpoint"]
        if current_field["revision"] == original_revision:
            if checkpoint is not None and checkpoint["revision"] != original_revision:
                refuse()
        elif current_field["revision"] == original_revision + 1:
            if (checkpoint is None or checkpoint["revision"] != original_revision + 1
                or checkpoint["field_key"] != str(field_key)
                or checkpoint["binding_digest"] != job["binding_digest"]
                or checkpoint["scope"] != scope_identity
                or effect_id not in checkpoint["receipt_ids"]):
                refuse()
        else:
            refuse()
    except (KeyError, TypeError, ValueError, ValidationError, AttributeError):
        refuse()
    if (semantic.get("contract_version") != CONTRACT_VERSION
        or digest(pins) != job["binding_digest"]
        or job["binding_digest"] != effect["binding_digest"]
        or job["identity"] != job_identity
        or job["generation"] != request.scope.generation
        or job["sensitive"] != request.scope.sensitive
        or digest(job_identity) != job_key
        or pins["input_digest"] != request.scope.input_digest
        or digest(pins["profile"]) != request.scope.profile_digest
        or pins["prompts"].get(str(request.role)) != request.prompt.model_dump(mode="json")
        or pins["sources"]["registry_digest"] != request.prompt.source_registry_digest
        or logical.get("source_policy_digest") != digest(spatial_policy)
        or logical.get("capture_policy_digest") != digest(spatial_capture_policy)
        or spatial_capture_policy["kind"] != "computed"
        or spatial_capture_policy["source_policy_digest"] != digest(spatial_policy)
        or result.coverage.source_version != spatial_policy["source_release"]
        or result.coverage.qualification_digest != digest(spatial_policy["source_release"])
        or semantic.get("effect_id") != effect_id
        or semantic.get("scope") != scope_identity
        or semantic.get("attempt_id") != saved["attempt_id"]
        or semantic.get("request_digest") != effect["request_digest"]
        or semantic.get("binding_digest") != effect["binding_digest"]
        or semantic.get("raw_capture") != saved["raw_capture"]
        or semantic.get("result", {}).get("typed_payload") != saved["typed_payload"]
        or original.get("contract_version") != "research-computed-spatial-capture/v1"
        or original.get("effect_id") != effect_id
        or original.get("attempt_id") != saved["attempt_id"]
        or original.get("binding_digest") != effect["binding_digest"]
        or original.get("semantic_result") != saved["typed_payload"]
        or result.model_dump(mode="json") != saved["typed_payload"]
        or logical.get("contract_version") != "research-computed-spatial-request/v1"
        or logical.get("tool_id") != "source_lookup"
        or logical.get("source_id") != "georeference_spatial"
        or logical.get("trusted_derivation_command_digest") != command_digest
        or logical.get("original_request_digest") != digest(request)
        or logical.get("scope") != request.scope.model_dump(mode="json")
        or logical.get("field_key") != str(field_key)
        or logical.get("field_revision") != request.field_revisions.get(field_key, 0)
        or logical.get("requested_fields") != [str(key) for key in command.requested_fields]
        or len(countries) != 1 or countries[0] is None
        or logical.get("country") != countries[0]
        or not isinstance(logical.get("verbatim_locality"), str)
        or hashlib.sha256(logical["verbatim_locality"].encode()).hexdigest()
            != logical.get("verbatim_locality_digest")
        or type(logical.get("label_has_elevation")) not in (bool, type(None))
        or logical.get("settled_inputs") != list(settled)
        or original.get("settled_inputs") != list(settled)
        or logical.get("validation_receipt_id") != validation_receipt.id
        or logical.get("validation_result_digest") != validation_receipt.result_digest
        or logical.get("prompt_digest") != request.prompt.digest
        or logical.get("source_registry_digest") != request.prompt.source_registry_digest
        or effect["request_digest"] != digest(logical)
        or effect["operation_key"] != OPERATION_PREFIX + digest(logical)
        or request.scope.sensitive
        or result.coverage.source_id != "georeference_spatial"
        or result.coverage.field_key != field_key
        or request.field_keys != (field_key,)
        or field_key not in command.requested_fields):
            refuse()
    try:
        validation_id = validation_receipt.effect_id
        validation_effect = effects[validation_id]
        validation_saved = validation_effect["receipt"]
        predeclared_capture(validation_effect, validation_saved)
        validation_semantic = parsed(read(validation_saved["capture"]))
        validation_raw = parsed(read(validation_saved["raw_capture"]))
        source_envelope = SourceRequestEnvelopeV2.model_validate(validation_raw)
        validation = SourceResult.model_validate(validation_saved["typed_payload"])
        anchor = next(item for item in command.inputs
            if item.field_key == source_envelope.query.field_key)
        place = geolocate_interpretation(source_envelope.query.query_text,
                                        source_envelope.query.field_key)
    except (KeyError, TypeError, ValueError, ValidationError, StopIteration, AttributeError):
        refuse()
    if (validation_effect["job_key"] != job_key
        or validation_effect["status"] != "completed"
        or validation_effect["field_keys"] != [str(anchor.field_key)]
        or validation_effect["scope"] != scope_identity
        or effect["scope"] != scope_identity
        or validation_effect["binding_digest"] != job["binding_digest"]
        or not validation_effect["operation_key"].startswith(OPERATION_PREFIX)
        or validation_effect["request_digest"] != digest(source_envelope.logical_request)
        or validation_effect["operation_key"] != OPERATION_PREFIX + digest(source_envelope.logical_request)
        or validation_saved["actual_micro_usd"] is None
        or validation_saved["held_micro_usd"] != 0
        or validation_saved["typed_payload"] != validation.model_dump(mode="json")
        or validation_saved["outcome"] != "completed"
        or validation_semantic.get("contract_version") != CONTRACT_VERSION
        or validation_semantic.get("effect_id") != validation_id
        or validation_semantic.get("scope") != scope_identity
        or validation_semantic.get("attempt_id") != validation_saved["attempt_id"]
        or validation_semantic.get("request_digest") != validation_effect["request_digest"]
        or validation_semantic.get("binding_digest") != validation_effect["binding_digest"]
        or validation_semantic.get("raw_capture") != validation_saved["raw_capture"]
        or validation_semantic.get("result", {}).get("typed_payload") != validation_saved["typed_payload"]
        or source_envelope.effect_id != validation_id
        or source_envelope.attempt_id != validation_saved["attempt_id"]
        or source_envelope.binding_digest != validation_effect["binding_digest"]
        or source_envelope.semantic_result_digest != hashlib.sha256(
            result_envelope(validation).encode()).hexdigest()
        or source_envelope.trusted_command_digest != command_digest
        or source_envelope.original_request.scope != request.scope
        or pins["prompts"].get(str(source_envelope.original_request.role))
            != source_envelope.original_request.prompt.model_dump(mode="json")
        or source_envelope.policy.model_dump(mode="json")
            != pins["sources"]["capture_policies"]["geolocate"]
        or source_envelope.policy.source_policy_digest
            != digest(source_policies["geolocate"])
        or source_envelope.query.field_key not in source_envelope.original_request.field_keys
        or source_envelope.original_request.field_revisions.get(anchor.field_key)
            != job["fields"][str(anchor.field_key)]["revision"]
        or source_envelope.query.source_id != "geolocate"
        or place.value != anchor.value
        or validation.coverage.source_id != "geolocate"
        or validation.coverage.field_key != anchor.field_key
        or validation.status != LookupStatus.SUCCESS
        or validation_receipt.id != "effect:" + validation_id
        or validation_receipt.scope != request.scope
        or validation_receipt.request_digest != validation_effect["request_digest"]
        or validation_receipt.binding_digest != validation_effect["binding_digest"]
        or validation_receipt.capture_locator != validation_saved["capture"]["locator"]
        or validation_receipt.effect_status != "completed"
        or validation_receipt.outcome != validation.status
        or validation_receipt.held_micro_usd != 0
        or validation_receipt.settled_micro_usd != validation_saved["actual_micro_usd"]
        or validation_receipt.source_id != "geolocate"
        or validation_receipt.field_keys != (anchor.field_key,)
        or validation_receipt.result_json != result_envelope(validation)
        or validation_receipt.result_digest != hashlib.sha256(
            validation_receipt.result_json.encode()).hexdigest()
        or validation_receipt.response_digest != validation_saved["capture"]["sha256"]
        or validation_receipt != tool_receipt_v2(source_envelope.original_request,
            source_envelope.query, validation_effect, validation)):
        refuse()
    if result.status == LookupStatus.SUCCESS:
        try:
            candidates = [json.loads(raw) for raw in result.candidate_json]
            if any(item.get("tool_call_id") != validation_receipt.id for item in candidates):
                refuse()
        except (TypeError, ValueError, AttributeError):
            refuse()
    # The original provider response bytes remain separately captured. Reading
    # each one also proves its immutable generation and SHA, beyond SQL metadata.
    for response in source_envelope.responses:
        if response.body.locator != (f"research-capture/{digest(source_envelope.original_request.scope.model_dump(mode='json'))}/"
                                    f"{validation_id}/{validation_saved['attempt_id']}/source-body/{response.ordinal}"):
            refuse()
        read(response.body.model_dump(mode="json"))
    return result


def verify_spatial_derivation_capture(document, job_key, field_key, command, choice, blobs) -> dict:
    """Prove a selectable proposal after verifying its full retained source chain."""
    from .contracts import FieldKey, SourceCoverageState
    from specimen_digitization.application.domain import LookupStatus

    try:
        result = verify_spatial_derivation_result(document, job_key, field_key,
            command, choice["effect_id"], blobs)
        candidate = choice["source_candidate"]
        state = document.state if hasattr(document, "state") else document["state"]
        saved = state["effects"][choice["effect_id"]]["receipt"]
        checkpoint = state["jobs"][job_key]["fields"][str(field_key)]["checkpoint"]
        choice_result = SourceResult.model_validate(choice["source_result"])
        field_key = FieldKey(field_key)
        computed = [item for item in result.evidence
            if item.kind == "computed_derivation_result"
            and item.source_id == "georeference_spatial"
            and item.id in candidate.get("evidence_ids", ())]
        expected_inputs = [str(item.field_key) for item in command.inputs]
        expected_revisions = [[str(item.field_key), item.revision] for item in command.inputs]
        georeference = candidate.get("georeference")
        if (type(candidate) is not dict
            or choice.get("capture", saved["capture"]) != saved["capture"]
            or checkpoint is None
            or checkpoint["field_key"] != str(field_key)
            or choice.get("checkpoint_id") != checkpoint["id"]
            or choice.get("checkpoint_digest") != digest(checkpoint)
            or choice["effect_id"] not in checkpoint["receipt_ids"]
            or choice.get("selection_id") != digest({"version": "research-candidate-choice/v1",
                "job_key": job_key, "field_key": str(field_key), "effect_id": choice["effect_id"],
                "candidate": candidate})
            or choice.get("source_id") != "georeference_spatial"
            or choice.get("field_key") != str(field_key)
            or choice.get("value") != candidate.get("value")
            or choice.get("authority_id") != candidate.get("authority_id")
            or choice.get("evidence_id") not in {item.id for item in computed}
            or result.model_dump(mode="json") != choice_result.model_dump(mode="json")
            or result.status != LookupStatus.SUCCESS
            or result.coverage.state != SourceCoverageState.SEARCHED
            or result.coverage.reason != "computed_proposal"
            or len(result.candidate_json) != 1
            or result.coverage.candidate_count != 1
            or candidate not in [json.loads(raw) for raw in result.candidate_json]
            or candidate.get("field_key") != str(field_key)
            or candidate.get("rule_version") != result.coverage.source_version
            or candidate.get("input_fields") != expected_inputs
            or candidate.get("input_revisions") != expected_revisions
            or type(georeference) is not dict
            or georeference.get("input_fields") != expected_inputs
            or georeference.get("tool_call_id") != candidate.get("tool_call_id")
            or georeference.get("version") != candidate.get("rule_version")
            or candidate.get("value_layer") != "derived"
            or candidate.get("human_review_required") is not True
            or candidate.get("automatic_settlement_allowed") is not False
            or not candidate.get("value")
            or not candidate.get("authority_id")
            or not candidate.get("dataset_ids")
            or not set(candidate.get("evidence_ids", ())) <= {item.id for item in result.evidence}
                | {eid for item in command.inputs for eid in item.evidence_ids}
            or len(computed) != 1):
            raise ValueError("retained_spatial_derivation_capture_unproved")
        return candidate
    except (KeyError, TypeError, ValueError, ValidationError, AttributeError):
        raise ValueError("retained_spatial_derivation_capture_unproved") from None


class CaptureSourceBrokerV2:
    """Concrete service composition; existing source policy/selection stays intact."""
    def __init__(self, registry: SourceRegistry, policies, effect_broker, scope, lease, *, transport,
                 execution_class="live", reservation_micro_usd=1, georeferencing_adapter=None,
                 derivation_context=None):
        self.transport = CapturedSourceTransportV2(transport, effect_broker.blobs, execution_class=execution_class)
        self.effects = SourceCaptureEffectsV2(effect_broker, scope, lease, registry, policies, self.transport,
            reservation_micro_usd=reservation_micro_usd, derivation_context=derivation_context)
        self.broker = SourceBroker(registry, transport=self.transport, effect_dispatch=self.effects,
            georeferencing_adapter=georeferencing_adapter)
        # The worker supplies this private proof service. It is never part of
        # the role tool roster or a model-authored SourceQuery.
        self.derivation_context = derivation_context

    @property
    def trusted_results(self):
        return self.broker.trusted_results

    def available_sources(self, request):
        return tuple(source_id for source_id in self.broker.available_sources(request)
            if source_id in self.effects.policies
            and self.effects.policies[source_id].kind in {"full_response", "pinned_dataset"}
            and (self.effects.policies[source_id].kind != "pinned_dataset"
                 or self.broker.georeferencing_adapter is not None)
            and self.effects.policies[source_id].source_policy_digest == digest(self.broker.registry.get(source_id))
            and self.broker.registry.get(source_id).ready
            and not self.broker.registry.get(source_id).paid
            and not self.broker.registry.get(source_id).credentials_required)

    async def query_source(self, request, query):
        return await self.broker.query_source(request, query)

    async def query(self, request, query):
        return await self.query_source(request, query)

    async def dispatch(self, request, tool_id, arguments):
        return await self.broker.dispatch(request, tool_id, arguments)

    async def invoke_utility(self, request, tool_id, arguments):
        return await self.broker.invoke_utility(request, tool_id, arguments)

    async def validate_locked_anchor(self, request: SpecialistRequest, query: SourceQuery, *,
                                     anchor, command_digest: str) -> SourceResult:
        """Fresh captured worker read of one current human-locked place anchor.

        This entry is deliberately absent from the model toolset. Only the
        runtime's immutable derivation-command proof can authorize the narrow
        lock exemption; the effect remains charged, scoped and captured under
        that command digest.
        """
        from .sources import geolocate_interpretation

        if (self.derivation_context is None or query.source_id not in {
                "georeference_history", "geolocate"}
            or query.field_key != anchor.field_key or query.field_key not in request.field_keys
            or request.scope.sensitive or not isinstance(command_digest, str)
            or len(command_digest) != 64 or any(c not in "0123456789abcdef" for c in command_digest)):
            raise PermissionError("Trusted locked-anchor source read is unavailable")
        if query.source_id == "georeference_history":
            try:
                arguments = json.loads(query.query_text)
            except (ValueError, TypeError):
                raise ValueError("Historical anchor query must be typed JSON") from None
            if (type(arguments) is not dict or set(arguments) - {"country", "name", "collected_on"}
                or arguments.get("name") != anchor.value):
                raise PermissionError("Historical query differs from locked anchor")
        else:
            if geolocate_interpretation(query.query_text, query.field_key).value != anchor.value:
                raise PermissionError("GEOLocate validation differs from locked anchor")
        self.derivation_context.verify_locked_anchor(request, query, anchor, command_digest)
        token = _trusted_locked_read.set(_TrustedLockedRead(
            self.effects, digest(request), digest(query), anchor, command_digest))
        try:
            result = await self.broker.query_source(request, query, trusted_anchor=True)
        finally:
            _trusted_locked_read.reset(token)
        if (result.receipt is None or result.receipt.scope != request.scope
            or result.receipt.source_id != query.source_id
            or result.receipt.field_keys != (query.field_key,)):
            raise ValueError("Locked anchor validation has no matching durable receipt")
        return result

    async def derive_spatial_from_trusted_inputs(self, request: SpecialistRequest, *, field_key,
            country: str, validation: SourceResult, settled_inputs: tuple,
            requested_fields: tuple, verbatim_locality: str,
            label_has_elevation: bool | None, tool_call_id: str,
            command_digest: str) -> SourceResult:
        """Durably capture one computed proposal for human review under a command.

        This is a worker-only route, not a model tool. The proof callback reads
        the immutable derivation command and current canonical Q before and
        during the effect. Successful proposals are candidates, never automatic
        publication or a bypass of the review decision.
        """
        from .contracts import FieldKey

        field_key = FieldKey(field_key)
        requested_fields = tuple(FieldKey(key) for key in requested_fields)
        source = self.broker.registry.get("georeference_spatial")
        policy = self.effects.policies.get("georeference_spatial")
        if (self.derivation_context is None or self.broker.georeferencing_adapter is None
            or policy is None or policy.kind != "computed" or not source.ready
            or policy.source_policy_digest != digest(source)
            or request.scope.sensitive or field_key not in request.field_keys
            or field_key not in requested_fields or len(set(requested_fields)) != len(requested_fields)
            or not isinstance(command_digest, str) or len(command_digest) != 64
            or any(c not in "0123456789abcdef" for c in command_digest)
            or validation.receipt is None or validation.receipt.id != tool_call_id):
            raise PermissionError("Trusted spatial derivation is unavailable")
        if (not isinstance(verbatim_locality, str) or len(verbatim_locality.encode()) > 8192
            or type(label_has_elevation) not in (bool, type(None))):
            raise PermissionError("Trusted spatial locality is outside the capture bound")
        if (any(value != getattr(request.scope, key) for key, value in self.effects.scope.identity().items())
            or self.effects.scope.sensitive != request.scope.sensitive
            or request.prompt.source_registry_digest != self.broker.registry.digest):
            raise PermissionError("Spatial derivation escaped pinned scope or registry")
        self.derivation_context.verify_current(
            request, command_digest, settled_inputs, requested_fields)
        field_revision = request.field_revisions.get(field_key, 0)
        inputs = tuple(asdict(item) for item in settled_inputs)
        logical = {"contract_version": "research-computed-spatial-request/v1",
                   "tool_id": "source_lookup", "source_id": "georeference_spatial",
                   "scope": request.scope.model_dump(mode="json"),
                   "original_request_digest": digest(request),
                   "field_key": str(field_key), "field_revision": field_revision,
                   "requested_fields": [str(key) for key in requested_fields],
                   "country": country, "verbatim_locality": verbatim_locality,
                   "verbatim_locality_digest": hashlib.sha256(
                       verbatim_locality.encode()).hexdigest(),
                   "label_has_elevation": label_has_elevation,
                   "settled_inputs": inputs,
                   "validation_receipt_id": validation.receipt.id,
                   "validation_result_digest": validation.receipt.result_digest,
                   "trusted_derivation_command_digest": command_digest,
                   "prompt_digest": request.prompt.digest,
                   "source_registry_digest": request.prompt.source_registry_digest,
                   "source_policy_digest": digest(source), "capture_policy_digest": digest(policy)}
        operation_key = OPERATION_PREFIX + digest(logical)
        policy_pins = {key: item.model_dump(mode="json") for key, item in self.effects.policies.items()}

        def validate_current():
            self.derivation_context.verify_current(
                request, command_digest, settled_inputs, requested_fields)
            document = self.effects.broker.store._read(self.effects.scope)
            job = self.effects.broker.store._lease(
                document.state, self.effects.scope, self.effects.lease, document.server_time)
            pins = job["pins"]
            if (digest(pins) != job["binding_digest"]
                or pins["input_digest"] != request.scope.input_digest
                or digest(pins["profile"]) != request.scope.profile_digest
                or pins["prompts"].get(str(request.role)) != request.prompt.model_dump(mode="json")
                or pins["sources"].get("registry_digest") != self.broker.registry.digest
                or pins["sources"].get("capture_policies") != policy_pins):
                raise PermissionError("spatial_capture_immutable_pins_changed")
            current = job["fields"].get(str(field_key))
            if not current or current["locked"] or current["revision"] != field_revision:
                raise StaleWork("spatial_capture_target_revision_or_lock_changed")
            for effect in document.state["effects"].values():
                if effect["job_key"] != self.effects.scope.key or str(field_key) not in effect["field_keys"]:
                    continue
                if effect["scope"] == self.effects.scope.identity() and effect["operation_key"] == operation_key:
                    continue
                if effect["status"] in {"sending", "held_unknown"} or (
                    effect["receipt"] is not None and effect["actual_micro_usd"] is None):
                    raise HeldUnknown("spatial_capture_target_has_unreconciled_effect")
            return job["binding_digest"]

        validate_current()

        async def dispatch(attempt_id, effect_id):
            binding_digest = validate_current()
            self.effects.broker.store.validate_dispatch(
                self.effects.scope, self.effects.lease, effect_id, attempt_id)
            result = self.broker.derive_spatial_from_trusted_inputs(request,
                field_key=field_key, country=country, validation=validation,
                settled_inputs=settled_inputs, requested_fields=requested_fields,
                verbatim_locality=verbatim_locality,
                label_has_elevation=label_has_elevation, tool_call_id=tool_call_id)
            validate_current()
            raw = result_envelope(result)
            if (len(raw.encode()) > 32768 or result.coverage.source_id != "georeference_spatial"
                or result.coverage.field_key != field_key
                or result.coverage.source_version != source.source_release
                or result.coverage.qualification_digest != digest(source.source_release)):
                unavailable("spatial_capture_result_context_changed")
            envelope = canonical_json({"contract_version": "research-computed-spatial-capture/v1",
                "original_request": request.model_dump(mode="json"), "logical_request": logical,
                "effect_id": effect_id, "attempt_id": attempt_id, "binding_digest": binding_digest,
                "validation_receipt": validation.receipt.model_dump(mode="json"),
                "settled_inputs": inputs, "semantic_result": result.model_dump(mode="json")})
            if len(envelope.encode()) > MAX_ENVELOPE_BYTES:
                unavailable("spatial_capture_envelope_bound_changed")
            return CapturedResult(typed_payload=result.model_dump(mode="json"),
                raw_payload=envelope.encode(), actual_micro_usd=0,
                usage={"computed_dataset_reads": 1, "semantic_bytes": len(raw.encode())})

        durable = await self.effects.broker.execute(self.effects.scope, self.effects.lease,
            operation_key, logical, self.effects.reservation_micro_usd, dispatch,
            execution_class=self.transport.execution_class, field_keys=(str(field_key),))
        effect = self.effects.broker.store.effect(self.effects.scope, durable.effect_id)
        result = typed(SourceResult, durable.typed_payload)
        query = SourceQuery(source_id="georeference_spatial", field_key=field_key,
            query_text="trusted_derivation_command:" + command_digest)
        receipt = tool_receipt_v2(request, query, effect, result)
        return SourceResult.model_validate({**result.model_dump(mode="json"), "receipt": receipt.model_dump(mode="json")})
