"""Bounded admission of independent fields after the existing output correction.

This creates no scientific value and performs no effect or checkpoint operation.
Every retained sibling passes the original strict validator again.
"""
from __future__ import annotations

import re

from pydantic_ai import ModelRetry

from specimen_digitization.application.domain import FieldValue, ValueState
from .contracts import FieldKey, FieldResolution, WorkState

FAILURE_REASON = "research_output_validation_exhausted"


def validation_failure(field_key: FieldKey) -> FieldResolution:
    return FieldResolution(field_key=field_key, work_state=WorkState.OPERATIONAL_FAILED,
        value=FieldValue(state=ValueState.UNRESOLVED), reason=FAILURE_REASON)


def is_validation_failure(resolution: FieldResolution) -> bool:
    """Only the canonical bare failure passes deterministic revalidation."""
    return resolution == validation_failure(resolution.field_key)


def _identified_field(error: ModelRetry, requested) -> FieldKey | None:
    # Only trusted validator feedback supplies this marker; model reasons are
    # never parsed. Ambiguous/unidentified feedback preserves whole-output failure.
    matches = re.findall(r"(?:^|[;:]\s*)field=([a-z_]+)(?=;|$)", error.message)
    if len(matches) != 1:
        return None
    try:
        key = FieldKey(matches[0])
    except ValueError:
        return None
    return key if key in requested else None


def _context_is_safe(request, output, results) -> bool:
    if request.scope.sensitive or any(row.scope != request.scope for roster in (
        request.fragments, request.events, request.assemblies, request.relations) for row in roster):
        return False
    if any(row.receipt is not None and (row.receipt.scope != request.scope
        or row.receipt.effect_status != "completed"
        or row.receipt.field_keys != (row.coverage.field_key,)
        or row.receipt.source_id != row.coverage.source_id) for row in results):
        return False  # Never hide a foreign scope or an unknown send.
    consumed = {pin.field_key: pin for pin in request.dependencies}
    for resolution in output.resolutions:
        for pin in resolution.dependencies:
            if pin.field_key in consumed and pin != consumed[pin.field_key]:
                return False  # A stale consumed checkpoint is a request fence.
            if pin.field_key not in consumed and pin.field_key not in request.field_keys:
                return False
    return True


def _cascade(original, failed):
    """Fail original dependents transitively; do not substitute new source pins."""
    while True:
        added = {item.field_key for item in original.resolutions if item.field_key not in failed
            and (any(pin.field_key in failed for pin in item.dependencies)
                or item.derivation is not None and item.derivation.source_field in failed
                or any(str(key) in item.value.derived_from for key in failed))}
        if not added:
            return
        failed.update(added)


def admit_output(ctx, output, strict):
    """Preserve one correction, then replace only identified invalid fields.

    Structural failures remain ModelRetry. At least one original independent
    sibling must survive; otherwise the existing whole-role failure path runs.
    Replacement and dependency propagation are bounded by requested fields.
    """
    try:
        return strict(ctx, output)
    except ModelRetry as first:
        if (ctx.retry < 1 or ctx.retry < ctx.max_retries
            or getattr(ctx, "partial_output", False)):
            raise
        request = ctx.deps.for_agent(ctx.agent.name)
        results = tuple(ctx.deps.tool_results.get(request.role, ()))
        if not _context_is_safe(request, output, results):
            raise
        failed = set()
        error = first
        for _ in request.field_keys:
            key = _identified_field(error, request.field_keys)
            if key is None or key in failed:
                raise first
            failed.add(key)
            _cascade(output, failed)
            if len(failed) == len(request.field_keys):
                raise first
            narrowed = output.model_copy(update={"resolutions": tuple(
                validation_failure(item.field_key) if item.field_key in failed else item
                for item in output.resolutions)})
            try:
                return strict(ctx, narrowed, controller_fields=frozenset(failed))
            except ModelRetry as next_error:
                error = next_error
        raise first
