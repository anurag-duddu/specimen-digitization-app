"""Restore retained content as a new audited canonical revision, without effects."""
from __future__ import annotations

from .domain import Disposition
from .storage import Conflict


def restored_specimen(base, source, *, accounting=None):
    """Keep immutable history and cumulative accounting outside restored content.

    This is a human correction, not acceptance of an old processing lease,
    scientific clearance, allowance or research generation. Native publication
    human-lock rows are not rewritten by the ordinary canonical save.
    """
    if (source.id != base.id or source.scope != base.scope
        or any(getattr(source.asset,key) != getattr(base.asset,key) for key in
            ("id","sha256","blob_ref","media_type","size_bytes","width","height"))):
        raise Conflict("Historical source identity changed")
    result = base.model_copy(deep=True)
    result.run = source.run.model_copy(deep=True)
    matching = [run for run in (base.run,*base.previous_runs) if run.id == result.run.id]
    if accounting is not None:
        if (accounting.id != base.id or accounting.scope != base.scope
            or accounting.run.id != result.run.id or not 1 <= accounting.version <= base.version):
            raise Conflict("Historical run accounting identity mismatch")
        matching.append(accounting.run)
    if not matching:
        # Compacted historical runs remain recoverable through their immutable
        # versions. Do not treat an absent inline accounting prefix as zero.
        raise Conflict("Historical run accounting must be recovered before restore")
    # The immutable latest same-run revision is the accounting authority.
    # Older content and inline history caches cannot replace its cumulative
    # totals, clear an unknown latest cost, or count an earlier reservation twice.
    authoritative = base.run if base.run.id == result.run.id else (
        accounting.run if accounting is not None else None
    )
    if authoritative is None:
        raise Conflict("Latest immutable historical run accounting is required")
    matching.append(source.run)
    result.run.usage = authoritative.usage.model_copy(deep=True)
    result.run.attempts = dict(authoritative.attempts)
    result.run.dead_letter = any(run.dead_letter for run in matching)
    # A restoration does not retire the previous active run or erase its actual
    # effects/costs. Exact originals also remain in repository version history.
    if base.run.id != result.run.id and not any(run == base.run for run in result.previous_runs):
        result.previous_runs.append(base.run.model_copy(deep=True))
    blockers = [run.blocker for run in matching if run.blocker]
    result.run.blocker = blockers[0] if blockers else None
    result.run.human_approved = False
    result.run.history_restore_human_locks = any(
        run.human_approved or run.history_restore_human_locks
        for run in (base.run,*matching)
    )
    result.run.lease_until = None
    result.run.next_retry_at = None
    result.run.queued_at = None
    if result.run.blocker:
        result.run.stage = "processing_blocked"
        result.run.disposition = None
        result.run.reasons = list(dict.fromkeys((*result.run.reasons,result.run.blocker)))
    else:
        result.run.stage = "finalized"
        result.run.disposition = Disposition.REVIEW
        result.run.reasons = list(dict.fromkeys((*result.run.reasons,"history_restored_requires_review")))
    return result
