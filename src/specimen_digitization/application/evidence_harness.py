"""One-phase, evidence-preserving harness; the outer workflow owns persistence/retries."""

from __future__ import annotations

import time
from typing import Callable, Literal, Protocol

from pydantic import Field, model_validator

from .authority_registry import (
    AuthorityQuery,
    AuthorityResult,
    Frozen,
    canonical,
    digest,
)

PhaseName = Literal[
    "parse", "plan", "lookup", "resolve", "normalize", "validate", "finalize"
]


class HarnessBudget(Frozen):
    max_tool_calls: int = Field(default=10, ge=0, le=100)
    max_elapsed_seconds: float = Field(default=120, gt=0, le=600)
    max_cost_microunits: int = Field(default=0, ge=0)
    max_tokens: int = Field(default=0, ge=0)


class BudgetUsage(Frozen):
    tool_calls: int = Field(default=0, ge=0)
    elapsed_seconds: float = Field(default=0, ge=0, allow_inf_nan=False)
    cost_microunits: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)


class PhaseSpec(Frozen):
    name: PhaseName
    version: str = Field(min_length=1)
    allowed_tools: tuple[str, ...] = ()
    not_applicable_reason: str | None = None


class HarnessSpec(Frozen):
    profile_id: str
    profile_version: str
    phases: tuple[PhaseSpec, ...]
    budgets: HarnessBudget = HarnessBudget()

    @model_validator(mode="after")
    def unique_phases(self):
        if len({p.name for p in self.phases}) != len(self.phases):
            raise ValueError("Duplicate harness phase")
        return self


class SourceLiteral(Frozen):
    field_key: str
    literal: str = Field(min_length=1, max_length=2000)
    source_excerpt: str = Field(min_length=1, max_length=4000)
    asset_id: str = Field(min_length=1)
    region_id: str = Field(min_length=1)
    observation_ids: tuple[str, ...] = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class FieldProposal(Frozen):
    field_key: str
    literal: str
    candidate: str
    relation: Literal["supports", "contradicts", "unresolved"]
    evidence_ids: tuple[str, ...]
    source_id: str | None = None
    authority_identifier: str | None = None
    reason: str


class SourceComparison(Frozen):
    field_key: str
    left_source: str
    right_source: str
    left_value: str
    right_value: str
    relation: Literal["supports", "contradicts"]
    evidence_ids: tuple[str, ...]
    reason: str = "Exact normalized-value comparison; differing values require review, not automatic source precedence"


def compare_normalized_sources(
    proposals: tuple[FieldProposal, ...],
) -> tuple[SourceComparison, ...]:
    """Compare source-labelled normalized proposals, never infer synonym equivalence."""
    comparisons = []
    for index, left in enumerate(proposals):
        for right in proposals[index + 1 :]:
            if (
                left.field_key == right.field_key
                and left.source_id
                and right.source_id
                and left.source_id != right.source_id
            ):
                comparisons.append(
                    SourceComparison(
                        field_key=left.field_key,
                        left_source=left.source_id,
                        right_source=right.source_id,
                        left_value=left.candidate,
                        right_value=right.candidate,
                        relation="supports"
                        if left.candidate == right.candidate
                        else "contradicts",
                        evidence_ids=tuple(
                            dict.fromkeys((*left.evidence_ids, *right.evidence_ids))
                        ),
                    )
                )
    return tuple(comparisons)


class Finding(Frozen):
    code: str
    field_key: str | None = None
    severity: Literal["hard", "warning", "operational"]
    evidence_ids: tuple[str, ...] = ()


class PhaseInput(Frozen):
    phase: PhaseName
    literals: tuple[SourceLiteral, ...] = Field(default=(), max_length=100)
    proposals: tuple[FieldProposal, ...] = Field(default=(), max_length=100)
    lookups: tuple[AuthorityResult, ...] = Field(default=(), max_length=100)
    required_fields: tuple[str, ...] = ()
    semantics_confirmed: bool = False
    findings: tuple[Finding, ...] = ()
    usage: BudgetUsage = BudgetUsage()


class PhaseResult(Frozen):
    phase: PhaseName
    version: str
    profile_id: str
    profile_version: str
    applicability: Literal["applied", "not_applicable", "blocked"]
    reason: str
    proposals: tuple[FieldProposal, ...] = ()
    findings: tuple[Finding, ...] = ()
    lookups: tuple[AuthorityResult, ...] = ()
    planned_tools: tuple[str, ...] = ()
    comparisons: tuple[SourceComparison, ...] = ()
    input_sha256: str
    output_sha256: str
    usage: BudgetUsage


def run_phase(spec: HarnessSpec, inputs: PhaseInput) -> PhaseResult:
    """Deterministic proposals only: no mutation, model request or final queue assignment.

    SourceLiteral must come from retained adjudicated evidence, never direct model
    arguments. Existing extraction's transcript containment check remains upstream.
    """
    phase = next((p for p in spec.phases if p.name == inputs.phase), None)
    findings = list(inputs.findings)
    proposals = list(inputs.proposals)
    applicability, reason, planned = "applied", "evidence_phase_completed", ()
    if phase is None:
        applicability, reason = "blocked", "phase_not_in_profile"
    elif phase.not_applicable_reason:
        applicability, reason = "not_applicable", phase.not_applicable_reason
    elif inputs.usage.elapsed_seconds >= spec.budgets.max_elapsed_seconds:
        applicability, reason = "blocked", "elapsed_budget_exhausted"
    elif inputs.phase == "parse":
        for item in inputs.literals:
            if item.literal not in item.source_excerpt:
                findings.append(
                    Finding(
                        code="literal_not_in_source_excerpt",
                        field_key=item.field_key,
                        severity="hard",
                        evidence_ids=item.evidence_ids,
                    )
                )
                continue
            proposals.append(
                FieldProposal(
                    field_key=item.field_key,
                    literal=item.literal,
                    candidate=item.literal,
                    relation="supports",
                    evidence_ids=item.evidence_ids,
                    reason="Literal candidate from retained source; not normalized",
                )
            )
    elif inputs.phase == "plan":
        planned = phase.allowed_tools
        if not planned:
            reason = "no_external_tools_configured"
    elif inputs.phase in {"lookup", "normalize"}:
        for lookup in inputs.lookups:
            matching = [
                item
                for item in inputs.literals
                if item.literal == lookup.literal
                and set(item.evidence_ids) & set(lookup.evidence_ids)
            ]
            if lookup.operationally_blocked:
                findings.append(
                    Finding(
                        code=lookup.status.value,
                        severity="operational",
                        evidence_ids=lookup.evidence_ids,
                    )
                )
            if not matching:
                findings.append(
                    Finding(
                        code="lookup_source_lineage_missing",
                        severity="hard",
                        evidence_ids=lookup.evidence_ids,
                    )
                )
            if lookup.candidates and (
                not lookup.raw_ref
                or not lookup.response_sha256
                or lookup.source_version == "unconfigured"
            ):
                findings.append(
                    Finding(
                        code="authority_capture_missing",
                        severity="hard",
                        evidence_ids=lookup.evidence_ids,
                    )
                )
                continue
            for item in matching:
                for candidate in lookup.candidates:
                    proposals.append(
                        FieldProposal(
                            field_key=item.field_key,
                            literal=item.literal,
                            candidate=candidate.name,
                            relation=candidate.relation,
                            evidence_ids=tuple(
                                dict.fromkeys(
                                    (*item.evidence_ids, *candidate.evidence_ids)
                                )
                            ),
                            source_id=lookup.source_id,
                            authority_identifier=candidate.identifier,
                            reason=candidate.reason,
                        )
                    )
        if not inputs.lookups:
            findings.append(Finding(code="lookup_evidence_missing", severity="hard"))
    elif inputs.phase == "resolve":
        for key in {p.field_key for p in proposals}:
            values = {p.candidate for p in proposals if p.field_key == key}
            if len(values) > 1 or any(
                p.relation != "supports" for p in proposals if p.field_key == key
            ):
                findings.append(
                    Finding(
                        code="candidate_resolution_requires_review",
                        field_key=key,
                        severity="hard",
                        evidence_ids=tuple(
                            dict.fromkeys(
                                e
                                for p in proposals
                                if p.field_key == key
                                for e in p.evidence_ids
                            )
                        ),
                    )
                )
        reason = "alternatives_retained_no_automatic_authority_selection"
    elif inputs.phase in {"validate", "finalize"}:
        if not inputs.semantics_confirmed:
            findings.append(
                Finding(code="field_semantics_unconfirmed", severity="hard")
            )
        for key in inputs.required_fields:
            values = [p for p in proposals if p.field_key == key]
            if not values or any(
                not p.candidate.strip()
                or not p.evidence_ids
                or p.relation != "supports"
                for p in values
            ):
                findings.append(
                    Finding(
                        code="mandatory_evidence_unresolved",
                        field_key=key,
                        severity="hard",
                    )
                )
            if len({p.candidate for p in values}) > 1:
                findings.append(
                    Finding(
                        code="competing_mandatory_candidates",
                        field_key=key,
                        severity="hard",
                    )
                )
        reason = "evidence_gates_only_core_policy_must_apply_remaining_validators"
    if any(f.severity == "operational" for f in findings):
        applicability = "blocked"
    output = dict(
        phase=inputs.phase,
        version=phase.version if phase else "unconfigured",
        profile_id=spec.profile_id,
        profile_version=spec.profile_version,
        applicability=applicability,
        reason=reason,
        proposals=tuple(proposals),
        findings=tuple(dict.fromkeys(findings)),
        lookups=inputs.lookups,
        planned_tools=planned,
        comparisons=compare_normalized_sources(tuple(proposals))
        if inputs.phase == "resolve"
        else (),
        input_sha256=digest(
            canonical(
                {
                    "spec": spec.model_dump(mode="json"),
                    "input": inputs.model_dump(mode="json"),
                }
            ).encode()
        ),
        usage=inputs.usage,
    )
    result = PhaseResult(**output, output_sha256="")
    return result.model_copy(
        update={
            "output_sha256": digest(
                canonical(
                    result.model_dump(mode="json", exclude={"output_sha256"})
                ).encode()
            )
        }
    )


class AuthorityTool(Protocol):
    version: str

    def lookup(self, query: AuthorityQuery) -> AuthorityResult: ...


class ToolCall(Frozen):
    call_id: str = Field(min_length=1)
    phase: PhaseName
    tool_id: str
    tool_version: str
    # Unknown pricing is not zero. Only known-free authority calls are supported.
    reserved_cost_microunits: int | None = None


class ToolReceipt(Frozen):
    call_id: str
    input_sha256: str
    state: Literal["intent", "completed", "blocked"]
    reason: str | None = None
    result: AuthorityResult | None = None
    output_sha256: str | None = None
    usage: BudgetUsage


class HarnessRunner:
    def __init__(self, tools: dict[str, AuthorityTool]):
        self._tools = dict(tools)

    def execute_one(
        self,
        spec: HarnessSpec,
        call: ToolCall,
        query: AuthorityQuery,
        usage: BudgetUsage,
        checkpoint: Callable[[ToolReceipt], None],
        previous: ToolReceipt | None = None,
    ) -> ToolReceipt:
        """Checkpoint intent before ONE effect and completion after it; never retry.

        Caller must supply durable, CAS-protected checkpoint and current run usage.
        A prior intent is outcome-unknown. Explicit outer recovery starts a new call.
        """
        key = digest(
            canonical(
                {
                    "spec": spec.model_dump(mode="json"),
                    "call": call.model_dump(mode="json"),
                    "query": query.model_dump(mode="json"),
                }
            ).encode()
        )
        if previous:
            if previous.input_sha256 != key or previous.call_id != call.call_id:
                raise ValueError("Receipt input mismatch")
            if previous.state == "completed":
                if previous.result is None or previous.output_sha256 != digest(
                    canonical(previous.result.model_dump(mode="json")).encode()
                ):
                    raise ValueError("Receipt output digest mismatch")
                return previous
            return ToolReceipt(
                call_id=call.call_id,
                input_sha256=key,
                state="blocked",
                reason="external_outcome_unknown"
                if previous.state == "intent"
                else previous.reason,
                usage=previous.usage,
            )
        phase = next((p for p in spec.phases if p.name == call.phase), None)
        tool = self._tools.get(call.tool_id)
        reason = None
        if (
            not phase
            or phase.not_applicable_reason
            or call.tool_id not in phase.allowed_tools
            or not tool
            or tool.version != call.tool_version
        ):
            reason = "tool_not_allowlisted_or_version_mismatch"
        elif call.reserved_cost_microunits != 0:
            reason = "only_known_free_authority_tools_supported"
        elif (
            usage.tool_calls >= spec.budgets.max_tool_calls
            or usage.elapsed_seconds >= spec.budgets.max_elapsed_seconds
            or usage.tokens > spec.budgets.max_tokens
            or usage.cost_microunits > spec.budgets.max_cost_microunits
        ):
            reason = "harness_budget_exhausted"
        if reason:
            receipt = ToolReceipt(
                call_id=call.call_id,
                input_sha256=key,
                state="blocked",
                reason=reason,
                usage=usage,
            )
            checkpoint(receipt)
            return receipt
        reserved = usage.model_copy(update={"tool_calls": usage.tool_calls + 1})
        checkpoint(
            ToolReceipt(
                call_id=call.call_id, input_sha256=key, state="intent", usage=reserved
            )
        )
        started = time.monotonic()
        result = tool.lookup(query)
        if (
            result.literal != query.literal
            or result.evidence_ids != query.evidence_ids
            or result.input_sha256 != digest(result.query_json.encode())
        ):
            raise ValueError("Authority tool result input lineage mismatch")
        measured = reserved.model_copy(
            update={
                "elapsed_seconds": usage.elapsed_seconds + time.monotonic() - started
            }
        )
        receipt = ToolReceipt(
            call_id=call.call_id,
            input_sha256=key,
            state="completed",
            result=result,
            output_sha256=digest(canonical(result.model_dump(mode="json")).encode()),
            usage=measured,
        )
        checkpoint(receipt)
        return receipt
