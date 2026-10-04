"""Authorized persisted field progress, independent of package message internals."""

import asyncio
import json
import math
import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field

from specimen_digitization.application.domain import FieldValue

from .contracts import (
    ALL_FIELDS, FieldCheckpoint, FieldKey, FrozenRecord, ResearchScope, SourceResult, WorkState, digest,
)
from .journal import DurableResearchJournal
from .persistence import StaleWork

# The fields a person decides: the harness stopped without a settled value (a question, a missing
# source or a missing rule). Resolved, exception and operational states carry no review.
REVIEW_STATES = frozenset({WorkState.WAITING_HUMAN, WorkState.WAITING_SOURCE, WorkState.WAITING_POLICY})
MAX_REVIEW_ITEMS = 8
MAX_REVIEW_TEXT = 240
MAX_REVIEW_DETAIL = 80
MAX_REVIEW_REASON = 600
MAX_DISTANCE_KM = 20_100  # no two points on Earth lie further apart
MAX_REVIEW_RANK = 1_000_000
_ELLIPSIS = "\N{HORIZONTAL ELLIPSIS}"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")


def _bounded(value: object, limit: int) -> str | None:
    """Plain, single-line text of at most ``limit`` characters, or None when there is none."""
    if not isinstance(value, str):
        return None
    text = _CONTROL.sub(" ", value).strip()
    if not text:
        return None
    return text if len(text) <= limit else text[:limit - 1].rstrip() + _ELLIPSIS


class ReviewCandidate(FrozenRecord):
    """One possibility a source returned, as the source named it. Never a value the harness chose.

    ``details`` holds only words the source supplied (an administrative unit, a taxonomic rank, a
    status); the wording around them belongs to the client. ``distance_km`` is GEOLocate's own figure:
    how far the match lies from the placement the geography specialist estimated for the named place.
    """

    label: str = Field(max_length=MAX_REVIEW_TEXT)
    details: tuple[Annotated[str, Field(max_length=MAX_REVIEW_DETAIL)], ...] = Field(default=(), max_length=4)
    distance_km: int | None = Field(default=None, strict=True, ge=0)
    authority_id: str | None = Field(default=None, max_length=MAX_REVIEW_TEXT)
    rank: int | None = Field(default=None, strict=True, ge=1)
    source_id: str = Field(max_length=MAX_REVIEW_TEXT)
    evidence_id: str | None = Field(default=None, max_length=MAX_REVIEW_TEXT)


class ReviewEvidence(FrozenRecord):
    """One captured source lookup for the field: what was asked and what the source answered."""

    evidence_id: str = Field(max_length=MAX_REVIEW_TEXT)
    source_id: str = Field(max_length=MAX_REVIEW_TEXT)
    kind: str = Field(max_length=MAX_REVIEW_TEXT)
    quote: str | None = Field(default=None, max_length=MAX_REVIEW_TEXT)
    searched_text: str | None = Field(default=None, max_length=MAX_REVIEW_TEXT)
    outcome: str | None = Field(default=None, max_length=MAX_REVIEW_TEXT)
    note: str | None = Field(default=None, max_length=MAX_REVIEW_TEXT)


class FieldReview(FrozenRecord):
    """What the harness found for a field that waits for a person (read-only, bounded).

    ``question_reason`` is the harness's own code for why it asked. ``evidence`` and ``candidates``
    come from the source lookups this field's checkpoint cites; ``*_not_shown`` counts what the
    bounds or the journal could not show, so a short list never reads as a complete one.
    """

    question_reason: Literal["evidence_conflict", "scoped_absence", "semantic_ambiguity"] | None = None
    reason: str | None = Field(default=None, max_length=MAX_REVIEW_REASON)
    evidence: tuple[ReviewEvidence, ...] = Field(default=(), max_length=MAX_REVIEW_ITEMS)
    candidates: tuple[ReviewCandidate, ...] = Field(default=(), max_length=MAX_REVIEW_ITEMS)
    evidence_not_shown: int = Field(default=0, strict=True, ge=0)
    candidates_not_shown: int = Field(default=0, strict=True, ge=0)


def _text(value: object, limit: int = MAX_REVIEW_TEXT) -> str:
    """``_bounded`` for a required string: empty when there is nothing to show."""
    return _bounded(value, limit) or ""


def _candidate(item: Mapping[str, Any], source_id: str, evidence_id: str | None) -> ReviewCandidate | None:
    label = _bounded(item.get("match_name"), MAX_REVIEW_TEXT) or _bounded(item.get("value"), MAX_REVIEW_TEXT)
    if label is None:
        return None
    # A source's own words, in a fixed order: GEOLocate's unit; Catalogue of Life's rank and status;
    # Global Names' underlying source. The source's order is ``rank`` only where it is an integer.
    details = tuple(filter(None, (_bounded(item.get(key), MAX_REVIEW_DETAIL) for key in (
        "match_admin", "rank", "status", "underlying_source_title") if isinstance(item.get(key), str))))
    # A number the source sent is shown only when it is a plausible one: JSON allows Infinity and NaN,
    # and an enormous integer is no distance or rank.
    distance, rank = item.get("distance_km"), item.get("rank")
    plausible = (type(distance) is int or type(distance) is float and math.isfinite(distance)) and 0 <= distance <= MAX_DISTANCE_KM
    return ReviewCandidate(
        label=label, details=details[:4], distance_km=round(distance) if plausible else None,
        authority_id=_bounded(item.get("authority_id"), MAX_REVIEW_TEXT) or None,
        rank=rank if type(rank) is int and 1 <= rank <= MAX_REVIEW_RANK else None,
        source_id=_text(source_id), evidence_id=_bounded(evidence_id, MAX_REVIEW_TEXT))


def _cited_evidence(checkpoint: FieldCheckpoint) -> set[str]:
    resolution, question = checkpoint.resolution, checkpoint.resolution.question
    cited = set(resolution.evidence_ids) | set(resolution.value.evidence_ids)
    receipts = list(resolution.source_coverage) + (list(question.coverage) if question else [])
    cited.update(identifier for receipt in receipts for identifier in receipt.receipt_ids)
    if question:
        cited.update(question.evidence_ids)
    return cited


def _reason_only(checkpoint: FieldCheckpoint) -> FieldReview:
    """What the checkpoint itself says, with every cited reference counted as not shown."""
    question = checkpoint.resolution.question
    return FieldReview(
        question_reason=question.reason if question else None,
        reason=_bounded(checkpoint.resolution.reason, MAX_REVIEW_REASON),
        evidence_not_shown=len(_cited_evidence(checkpoint)))


def _field_review(effects: Mapping[str, Any], job_key: str, key: FieldKey, checkpoint: FieldCheckpoint) -> FieldReview:
    """Resolve what a waiting checkpoint cites from the durable source-lookup captures of its own field.

    Only completed ``source_lookup`` effects of this job and this field are read, and only the typed
    SourceResult is kept: model captures, other fields' captures and raw response bodies never appear.

    The review decorates a read that also finalizes runs (the worker reads the thread after publishing),
    so it never raises. A capture that does not validate or that cannot be shown is skipped as a whole;
    if the review itself cannot be built the field keeps what its checkpoint says (``_reason_only``).
    """
    question, resolution = checkpoint.resolution.question, checkpoint.resolution
    cited = _cited_evidence(checkpoint)
    evidence, candidates, resolved, seen = [], [], set(), set()
    for effect_id in checkpoint.effect_receipt_ids:
        effect = effects.get(effect_id)
        try:
            if (effect is None or effect["job_key"] != job_key or effect["field_keys"] != [str(key)]
                    or not effect["operation_key"].startswith("source_lookup:") or not effect["receipt"]):
                continue
            result = SourceResult.model_validate(effect["receipt"]["typed_payload"])
            if result.coverage.field_key != key:
                continue
            items = [json.loads(item) for item in result.candidate_json]
            searched = next((_bounded(item.get("input_literal"), MAX_REVIEW_TEXT) for item in items
                             if isinstance(item.get("input_literal"), str)), None)
            found = [ReviewEvidence(
                evidence_id=_text(item.id), source_id=_text(item.source_id), kind=_text(item.kind),
                quote=_bounded(item.excerpt, MAX_REVIEW_TEXT), searched_text=searched,
                outcome=result.status.value, note=_bounded(result.coverage.reason, MAX_REVIEW_TEXT))
                for item in result.evidence if item.id not in resolved]
            anchor = result.evidence[0].id if result.evidence else None
            options = [_candidate(item, result.coverage.source_id, anchor) for item in items]
        except Exception:  # noqa: BLE001 - one unreadable capture must not fail the read
            continue
        resolved.update(item.id for item in result.evidence)
        evidence.extend(found)
        for option in filter(None, options):
            if (identity := option.model_dump_json()) not in seen:
                seen.add(identity)
                candidates.append(option)
    try:
        return FieldReview(
            question_reason=question.reason if question else None,
            reason=_bounded(resolution.reason, MAX_REVIEW_REASON),
            evidence=tuple(evidence[:MAX_REVIEW_ITEMS]), candidates=tuple(candidates[:MAX_REVIEW_ITEMS]),
            evidence_not_shown=len(cited - resolved) + max(0, len(evidence) - MAX_REVIEW_ITEMS),
            candidates_not_shown=max(0, len(candidates) - MAX_REVIEW_ITEMS))
    except Exception:  # noqa: BLE001 - see the docstring
        return _reason_only(checkpoint)


class FieldThread(FrozenRecord):
    field_key: FieldKey
    work_state: WorkState
    value: FieldValue
    checkpoint: FieldCheckpoint | None = None
    blocker_code: str | None = None
    actions: tuple[Literal["retry_field", "supply_information", "review_proposal"], ...] = ()
    review: FieldReview | None = None


class EffectThread(FrozenRecord):
    effect_id: str
    generation: int = Field(strict=True, ge=1)
    kind: Literal["model", "tool"]
    status: Literal["reserved", "sending", "held_unknown", "completed"]
    attempt_ids: tuple[str, ...]
    actual_micro_usd: int | None = Field(default=None, strict=True, ge=0)
    held_micro_usd: int = Field(strict=True, ge=0)
    capture_locator: str | None = None


class ResearchThread(FrozenRecord):
    contract_version: Literal["research-thread-v1"] = "research-thread-v1"
    scope: ResearchScope
    paused: bool
    fields: tuple[FieldThread, ...]
    effects: tuple[EffectThread, ...]
    resolved_count: int
    exception_count: int
    trace_ids: tuple[str, ...] = ()


class ResearchThreadReader:
    """Re-check membership on every read; never returns raw models or credentials."""

    def __init__(self, journal: DurableResearchJournal):
        self.journal = journal

    async def read(self, scope: ResearchScope) -> ResearchThread:
        checkpoints = {item.field_key:item for item in await self.journal.load(scope)}
        document = await asyncio.to_thread(self.journal.store._read, self.journal.scope)
        job = self.journal.store._job(document.state, self.journal.scope)
        fields = []
        for key in ALL_FIELDS:
            checkpoint = checkpoints.get(key)
            work_state = checkpoint.resolution.work_state if checkpoint else WorkState.PENDING
            stored = job["fields"].get(str(key), {})
            if stored.get("locked") and checkpoint is None:
                work_state = WorkState.WAITING_POLICY
            command_id = stored.get("retry_command_id")
            if command_id is not None:
                command = document.state["outbox"].get("retry/" + command_id, {}).get("command", {})
                if (command.get("scope") != self.journal.scope.identity() or command.get("field_key") != str(key)
                    or command.get("binding_digest") != job["binding_digest"]
                    or command.get("expected_field_revision") != stored.get("revision")
                    or checkpoint is None or checkpoint.revision != stored.get("revision")
                    or command.get("checkpoint_digest") != digest(stored["checkpoint"])):
                    raise StaleWork("thread_retry_command_binding_mismatch")
                if command.get("status") == "queued":
                    work_state = WorkState.RETRY_SCHEDULED
                elif command.get("status") == "running":
                    work_state = WorkState.RESEARCHING
            blocked_retry = False
            if checkpoint is not None and command_id is None:
                for event in document.state["outbox"].values():
                    command = event.get("command", {})
                    if (event.get("kind") == "research_field_retry"
                        and command.get("status") == "blocked"
                        and command.get("scope") == self.journal.scope.identity()
                        and command.get("field_key") == str(key)
                        and command.get("expected_field_revision") == stored.get("revision")
                        and command.get("binding_digest") == job["binding_digest"]
                        and command.get("checkpoint_digest") == digest(stored["checkpoint"])):
                        blocked_retry = True
                        break
            actions = []
            if not job["paused"] and not stored.get("locked"):
                if command_id is None and not blocked_retry and work_state in {WorkState.OPERATIONAL_FAILED, WorkState.RETRY_SCHEDULED}:
                    if await self.journal.retry_eligible(scope, key):
                        actions.append("retry_field")
                if checkpoint and work_state == WorkState.WAITING_HUMAN and checkpoint.resolution.question:
                    actions.append("supply_information")
            blocker = {
                WorkState.WAITING_SOURCE:"source_prerequisite",
                WorkState.WAITING_POLICY:"policy_prerequisite",
                WorkState.OPERATIONAL_FAILED:"research_operational_failure",
                WorkState.WAITING_HUMAN:"human_decision_required",
            }.get(work_state)
            if blocked_retry:
                blocker = "research_retry_blocked"
            review = None
            if checkpoint is not None and checkpoint.resolution.work_state in REVIEW_STATES:
                review = _field_review(document.state["effects"], self.journal.scope.key, key, checkpoint)
            fields.append(FieldThread(field_key=key, work_state=work_state,
                value=checkpoint.resolution.value if checkpoint else FieldValue(),
                checkpoint=checkpoint, blocker_code=blocker, actions=tuple(actions), review=review))
        used = {effect for checkpoint in checkpoints.values() for effect in checkpoint.effect_receipt_ids}
        effects = []
        for effect in document.state["effects"].values():
            if effect["job_key"] != self.journal.scope.key:
                continue
            if effect["scope"]["generation"] != scope.generation and effect["effect_id"] not in used:
                continue
            receipt = effect["receipt"]
            effects.append(EffectThread(effect_id=effect["effect_id"],
                generation=effect["scope"]["generation"],
                kind="model" if effect["operation_key"].startswith("model:") else "tool",
                status=effect["status"], attempt_ids=tuple(item["attempt_id"] for item in effect["attempts"]),
                actual_micro_usd=effect["actual_micro_usd"], held_micro_usd=effect["held_micro_usd"],
                capture_locator=receipt["capture"]["locator"] if receipt else None))
        saved_trace = job.get("trace_context")
        trace_ids = tuple(dict.fromkeys(
            tuple(cp.trace_id for cp in checkpoints.values() if cp.trace_id)
            + ((saved_trace["trace_id"],) if saved_trace else ())))
        return ResearchThread(scope=scope, paused=job["paused"], fields=tuple(fields),
            effects=tuple(effects), trace_ids=trace_ids,
            resolved_count=sum(item.work_state == WorkState.RESOLVED for item in fields),
            exception_count=sum(item.work_state == WorkState.NONBLOCKING_EXCEPTION for item in fields))
