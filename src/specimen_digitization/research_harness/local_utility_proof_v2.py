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
    SpecialistRequest, SpecialistRole, digest,
)
from .evidence import catalog_literal, parse_measurement, parse_temporal, validate_assembly
from .sources import canonical_json

UTILITY_VERSION = "deterministic-domain-v1"
UTILITY_ROLES = {"parse_measurement": SpecialistRole.MEASUREMENT,
    "parse_temporal": SpecialistRole.TEMPORAL, "catalog_number": SpecialistRole.COLLECTION}


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

    def as_receipt(self):
        # This is a policy replay proof, deliberately not a ToolReceipt/effect.
        return {"contract_version":self.contract_version,
            "original_request_digest":self.original_request_digest,
            "result_digest":self.result_digest, "tool_id":self.tool_id,
            "arguments":{"field_key":self.field_key,"text":self.text},
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
    expected_coverage = SourceCoverageReceipt(source_id=tool_id,field_key=field_key,
        state=SourceCoverageState.SEARCHED,source_version=UTILITY_VERSION,
        coverage_limit="Deterministic local utility; settlement validates graph/G32",reason="exact_parse")
    if (result.status != LookupStatus.SUCCESS or result.evidence
            or result.coverage != expected_coverage or len(result.candidate_json) != 1):
        hold()
    matches = {}
    for assembly in request.assemblies:
        try:
            validate_assembly(request, assembly)
            text = assembly.interpreted_text
            if tool_id == "catalog_number":
                parsed = {"field_key":str(field_key),"value":catalog_literal(text),"rule_version":"catalog-number-v1"}
            else:
                parsed = (parse_measurement(text) if tool_id == "parse_measurement"
                    else parse_temporal(text)).model_dump(mode="json")
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


def local_utility_replays_v2(request, results, *, accepted_checkpoint_proof):
    """Require forward acceptance provenance for every local output admission."""
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
    return tuple(verify_local_utility_v2(request, row) for row in local)
