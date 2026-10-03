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
    kind: Literal["full_response", "denied"]
    owner_registration_digest: Digest
    owner_registration_origin: str = Field(min_length=1)
    maximum_responses: int = Field(strict=True, ge=1, le=2)


class CapturedTransportResponseV2(FrozenRecord):
    ordinal: int = Field(strict=True, ge=1, le=2)
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


def logical_request_v2(request, query, policy):
    return {
        "contract_version": CAPTURE_VERSION, "tool_id": "source_lookup",
        "arguments": query.model_dump(mode="json"), "scope": request.scope.model_dump(mode="json"),
        "field_revision": request.field_revisions.get(query.field_key, 0),
        "prompt_digest": request.prompt.digest, "source_registry_digest": request.prompt.source_registry_digest,
        "original_request_digest": digest(request), "capture_policy_digest": digest(policy),
        "source_policy_digest": policy.source_policy_digest,
        "purpose_policy": PUBLIC_METADATA_POLICY if query.source_id == "field_museum_ipt" else "insects-research-v1",
    }


class SourceRequestEnvelopeV2(FrozenRecord):
    contract_version: Literal["research-source-request-envelope/v2"] = CAPTURE_VERSION
    original_request: SpecialistRequest
    query: SourceQuery
    policy: RegisteredCapturePolicyV2
    logical_request: dict
    effect_id: Digest
    attempt_id: str = Field(min_length=1)
    binding_digest: Digest
    semantic_result_digest: Digest
    responses: tuple[CapturedTransportResponseV2, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def original_context(self):
        if (self.policy.kind != "full_response" or self.policy.source_id != self.query.source_id
            or self.query.field_key not in self.original_request.field_keys
            or self.logical_request != logical_request_v2(self.original_request, self.query, self.policy)
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
    def __init__(self, broker, scope, lease, registry, policies, transport, *, reservation_micro_usd=1):
        if type(reservation_micro_usd) is not int or reservation_micro_usd <= 0:
            unavailable("source_capture_reservation_invalid")
        if type(scope.generation) is not int or scope.generation < 1 or type(scope.sensitive) is not bool:
            unavailable("source_capture_scope_type_invalid")
        self.broker, self.scope, self.lease = broker, scope, lease
        self.registry, self.transport = registry, transport
        self.original_transport, self.execution_class = transport.transport, transport.execution_class
        self.policies = {key: typed(RegisteredCapturePolicyV2, value.model_dump(mode="json")) for key, value in policies.items()}
        if any(key != value.source_id for key, value in self.policies.items()):
            unavailable("source_capture_policy_key_changed")
        self.reservation_micro_usd = reservation_micro_usd

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
        logical = logical_request_v2(request, query, policy)
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
            if not current or current["locked"] or current["revision"] != field_revision:
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

        durable = await self.broker.execute(self.scope, self.lease, operation_key, logical,
            self.reservation_micro_usd, dispatch, execution_class=self.transport.execution_class,
            field_keys=(str(query.field_key),))
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


class CaptureSourceBrokerV2:
    """Concrete service composition; existing source policy/selection stays intact."""
    def __init__(self, registry: SourceRegistry, policies, effect_broker, scope, lease, *, transport,
                 execution_class="live", reservation_micro_usd=1):
        self.transport = CapturedSourceTransportV2(transport, effect_broker.blobs, execution_class=execution_class)
        self.effects = SourceCaptureEffectsV2(effect_broker, scope, lease, registry, policies, self.transport,
            reservation_micro_usd=reservation_micro_usd)
        self.broker = SourceBroker(registry, transport=self.transport, effect_dispatch=self.effects)

    @property
    def trusted_results(self):
        return self.broker.trusted_results

    def available_sources(self, request):
        return tuple(source_id for source_id in self.broker.available_sources(request)
            if source_id in self.effects.policies
            and self.effects.policies[source_id].kind == "full_response"
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
