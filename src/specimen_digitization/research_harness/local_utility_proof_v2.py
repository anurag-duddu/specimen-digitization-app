"""Replay accepted local utility outputs without inventing external effect receipts.

The CAS-linked acceptance proof retains the actual SourceResult. A utility has
no remote call, cost receipt or deciding source authority. Its sole authority is
an exact replay from the immutable request's evidenced assembly text, under the
same role/field and deterministic parser contract as SourceBroker.invoke_utility.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .accepted_output import VALIDATOR_SOURCE_SHA256
from .compatibility import PublicationUnavailable
from .contracts import (
    LookupStatus, SourceCoverageReceipt, SourceCoverageState, SourceResult,
    FieldKey, SpecialistRequest, SpecialistRole, digest,
)
from .evidence import catalog_literal, parse_measurement, validate_assembly
from .sources import SETTLEMENT_UTILITY_VERSION, canonical_json, local_settlement_result

UTILITY_VERSION = "deterministic-domain-v1"
UTILITY_ROLES = {"parse_measurement": SpecialistRole.MEASUREMENT,
    "parse_temporal": SpecialistRole.TEMPORAL, "catalog_number": SpecialistRole.COLLECTION,
    "settle_temporal": SpecialistRole.TEMPORAL, "settle_elevation": SpecialistRole.MEASUREMENT,
    "settle_collectors": SpecialistRole.PARTIES, "settle_collection": SpecialistRole.COLLECTION}


@dataclass(frozen=True)
class LocalUtilityReplayProofV2:
    contract_version: Literal["research-local-utility-replay/v2"]
    original_request_digest: str
    result_digest: str
    tool_id: str
    field_key: str
    text: str
    assembly_ids: tuple[str, ...]
    utility_version: str = UTILITY_VERSION
    parser_source_sha256: str = VALIDATOR_SOURCE_SHA256
    arguments: dict | None = None

    def as_receipt(self):
        # This is a policy replay proof, deliberately not a ToolReceipt/effect.
        return {"contract_version":self.contract_version,
            "original_request_digest":self.original_request_digest,
            "result_digest":self.result_digest, "tool_id":self.tool_id,
            "arguments":self.arguments if self.arguments is not None else
                {"field_key":self.field_key,"text":self.text},
            "assembly_ids":list(self.assembly_ids),"utility_version":self.utility_version,
            "parser_source_sha256":self.parser_source_sha256}


def verify_local_utility_v2(request: SpecialistRequest, result: SourceResult) -> LocalUtilityReplayProofV2:
    """Refuse unknown, altered or ambiguously sourced receiptless results."""
    def hold():
        raise PublicationUnavailable("canonical_local_utility_unproved")
    try:
        request = SpecialistRequest.model_validate(request.model_dump(mode="json"))
        result = SourceResult.model_validate(result.model_dump(mode="json"))
    except (ValueError, TypeError, AttributeError, KeyError):
        hold()
    tool_id, field_key = result.coverage.source_id, result.coverage.field_key
    if (result.receipt is not None or tool_id not in UTILITY_ROLES
            or request.role != UTILITY_ROLES[tool_id] or field_key not in request.field_keys):
        hold()
    if tool_id == "settle_collection":
        arguments = {"field_key": str(field_key)}
        try:
            expected = local_settlement_result(request, tool_id, arguments)
        except (ValueError, TypeError, KeyError):
            hold()
        if result != expected:
            hold()
        return LocalUtilityReplayProofV2("research-local-utility-replay/v2", digest(request),
            digest(result), tool_id, str(field_key), "",
            tuple(row.id for row in request.assemblies if row.field_key == field_key),
            utility_version=SETTLEMENT_UTILITY_VERSION, arguments=arguments)
    if tool_id in {"settle_temporal", "settle_elevation", "settle_collectors"}:
        return _verify_settlement(request, result)
    expected_coverage = SourceCoverageReceipt(source_id=tool_id,field_key=field_key,
        state=SourceCoverageState.SEARCHED,source_version=UTILITY_VERSION,
        coverage_limit="Deterministic local utility; settlement validates graph/G32",reason="exact_parse")
    if (result.status != LookupStatus.SUCCESS or result.evidence
            or result.coverage != expected_coverage or len(result.candidate_json) != 1):
        hold()
    matches = {}
    for assembly in request.assemblies:
        if tool_id == "catalog_number" and (
            assembly.field_key != field_key or field_key != FieldKey.FMNH_INS_NUMBER):
            continue
        try:
            validate_assembly(request, assembly)
            text = assembly.interpreted_text
            if tool_id == "catalog_number":
                parsed = {"field_key":str(field_key),"value":catalog_literal(text),"rule_version":"catalog-number-v1"}
            else:
                from .temporal_context import parse_temporal_text
                parsed = (parse_measurement(text) if tool_id == "parse_measurement"
                    else parse_temporal_text(request, text, field_key)).model_dump(mode="json")
            expected = SourceResult(status=LookupStatus.SUCCESS,coverage=expected_coverage,
                candidate_json=(canonical_json(parsed),))
        except (ValueError, TypeError, KeyError):
            continue
        if result == expected:
            matches.setdefault(text, []).append(assembly.id)
    # The recorded output lacks invocation arguments. Only one exact argument
    # text may be recovered; two equivalent catalog spellings are not guessed.
    if len(matches) != 1:
        hold()
    text, assembly_ids = next(iter(matches.items()))
    return LocalUtilityReplayProofV2("research-local-utility-replay/v2",digest(request),
        digest(result),tool_id,str(field_key),text,tuple(assembly_ids))


def _verify_settlement(request: SpecialistRequest, result: SourceResult) -> LocalUtilityReplayProofV2:
    """Recompute one exact settlement from immutable event/assembly identities."""
    def hold():
        raise PublicationUnavailable("canonical_local_utility_unproved")

    tool_id, field_key = result.coverage.source_id, result.coverage.field_key
    if result.receipt is not None or result.evidence or len(result.candidate_json) != 1:
        hold()
    matches = []
    event_ids = dict.fromkeys(item.event_id for item in request.assemblies)
    for event_id in event_ids:
        assemblies = tuple(item for item in request.assemblies if item.event_id == event_id
            and (tool_id != "settle_elevation" or str(item.field_key).startswith("elevation_")))
        if not assemblies:
            continue
        if tool_id in {"settle_temporal", "settle_collectors"}:
            arguments = {"field_key": str(field_key), "event_id": event_id}
        else:
            arguments = {"field_key": str(field_key), "event_id": event_id,
                         "assembly_ids": [item.id for item in assemblies]}
        try:
            expected = local_settlement_result(request, tool_id, arguments)
        except (ValueError, TypeError, KeyError):
            continue
        if expected == result:
            matches.append((arguments, tuple(item.id for item in assemblies)))
    if len(matches) != 1:
        hold()
    arguments, assembly_ids = matches[0]
    return LocalUtilityReplayProofV2("research-local-utility-replay/v2", digest(request),
        digest(result), tool_id, str(field_key), "", assembly_ids,
        utility_version=SETTLEMENT_UTILITY_VERSION, arguments=arguments)


def local_utility_replays_v2(request, results, *, accepted_checkpoint_proof):
    """Verify receiptless context; replay only actual deterministic utilities.

    SourceBroker can refuse an unqualified query before dispatch. That empty
    result remains in the exact accepted context, but supplies neither search
    authority nor a local utility proof for any field in the specialist batch.
    """
    local = tuple(row for row in results if row.receipt is None)
    if not local:
        return ()
    from .accepted_output import AcceptedCheckpointProofV1
    try:
        accepted = AcceptedCheckpointProofV1.model_validate(accepted_checkpoint_proof.model_dump(mode="json"))
    except (ValueError, TypeError, AttributeError, KeyError):
        raise PublicationUnavailable("canonical_local_utility_acceptance_unproved") from None
    if (accepted.acceptance.original_request != request
            or accepted.acceptance.source_results != tuple(results)):
        raise PublicationUnavailable("canonical_local_utility_acceptance_unproved")
    return tuple(verify_local_utility_v2(request, row) for row in local
        if not _unqualified_source_refusal(request, row))


def _unqualified_source_refusal(request: SpecialistRequest, result: SourceResult) -> bool:
    """Recognize only the empty, unsent SourceBroker._unavailable shape.

    Never admit candidate/evidence payloads, search/qualification claims or a
    failed effect through this exception. The caller first validates the entire
    accepted checkpoint proof and its exact request/results identity.
    """
    coverage = result.coverage
    if (coverage.source_id in UTILITY_ROLES or coverage.field_key not in request.field_keys
            or not all(item.strip() for item in
                (coverage.source_id, coverage.source_version, coverage.reason))):
        return False
    expected = SourceResult(status=LookupStatus.POLICY, coverage=SourceCoverageReceipt(
        source_id=coverage.source_id, field_key=coverage.field_key,
        state=SourceCoverageState.UNQUALIFIED, source_version=coverage.source_version,
        coverage_limit="No qualified exact scientific search completed", reason=coverage.reason))
    return result == expected
