"""Authorized persisted field progress, independent of package message internals."""

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from specimen_digitization.application.domain import FieldValue, LookupStatus

from .contracts import (
    ALL_FIELDS, FieldCheckpoint, FieldKey, FrozenRecord, ResearchScope, SourceResult, WorkState, digest,
)
from .journal import DurableResearchJournal
from .persistence import StaleWork
from .source_capture_v2 import OPERATION_PREFIX, RegisteredCapturePolicyV2

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


class _ReviewCapturePolicyV2(RegisteredCapturePolicyV2):
    """Current read contract for registered HTTP, dataset and computed captures.

    Computed command/envelope proof is a separate core verifier. This bounded
    reader also works while the older full-response capture writer is loaded.
    """
    kind: Literal["full_response", "pinned_dataset", "computed", "denied"]
    maximum_responses: int = Field(strict=True, ge=1, le=3)


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
    selection_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    selection_value: str | None = Field(default=None, max_length=MAX_REVIEW_TEXT)


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

    question_reason: Literal["evidence_conflict", "scoped_absence", "semantic_ambiguity", "derived_proposal"] | None = None
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


def candidate_selection_id(job_key: str, field_key: FieldKey, effect_id: str, item: Mapping[str, Any]) -> str:
    """Bind a choice to the entire retained candidate, including hidden placement details."""
    return digest({"version": "research-candidate-choice/v1", "job_key": job_key,
        "field_key": str(field_key), "effect_id": effect_id, "candidate": dict(item)})


def candidate_selection_value(item: Mapping[str, Any]) -> str | None:
    # Historical candidates remain visible context until the required validator
    # produces its own selectable result. A computed proposal's separate
    # automatic_settlement_allowed=False still permits an explicit human choice.
    if item.get("settlement_allowed") is False or item.get("validation_required") == "geolocate":
        return None
    value = item.get("value")
    # Never select a shortened display label or silently truncate the stored value.
    if (not isinstance(value, str) or not value.strip() or len(value) > MAX_REVIEW_TEXT
            or _CONTROL.search(value)):
        return None
    return value


def _cited_evidence(checkpoint: FieldCheckpoint) -> set[str]:
    resolution, question = checkpoint.resolution, checkpoint.resolution.question
    cited = set(resolution.evidence_ids) | set(resolution.value.evidence_ids)
    receipts = list(resolution.source_coverage) + (list(question.coverage) if question else [])
    cited.update(identifier for receipt in receipts for identifier in receipt.receipt_ids)
    if question:
        cited.update(question.evidence_ids)
    return cited


def candidate_selection_evidence(result: SourceResult, checkpoint: FieldCheckpoint) -> str | None:
    """Return a source-matching retained receipt that this field's checkpoint actually cites."""
    cited = _cited_evidence(checkpoint)
    question = checkpoint.resolution.question
    coverage = (*checkpoint.resolution.source_coverage, *(question.coverage if question else ()))
    source_citations = {identifier for receipt in coverage
                       if receipt.field_key == checkpoint.field_key
                       and receipt.source_id == result.coverage.source_id
                       and receipt.source_version == result.coverage.source_version
                       for identifier in receipt.receipt_ids}
    return next((item.id for item in result.evidence
                 if item.id in cited and item.id in result.coverage.receipt_ids and item.id in source_citations
                 and item.source_id == result.coverage.source_id
                 and item.source_version == result.coverage.source_version
                 and (result.coverage.source_id != "georeference_spatial" or (
                     item.kind == "computed_derivation_result"
                     and item.id == "computed:" + item.response_digest
                     and item.locator == "computed://georeference_spatial/" + item.response_digest))), None)


def _reason_only(checkpoint: FieldCheckpoint) -> FieldReview:
    """What the checkpoint itself says, with every cited reference counted as not shown."""
    question = checkpoint.resolution.question
    return FieldReview(
        question_reason=question.reason if question else None,
        reason=_bounded(checkpoint.resolution.reason, MAX_REVIEW_REASON),
        evidence_not_shown=len(_cited_evidence(checkpoint)))


def candidate_source_capture(effect: Mapping[str, Any], result: SourceResult, job: Mapping[str, Any] | None) -> bool:
    """Accept legacy lookups or V2 captures bound to their registered source policy.

    This filter reads retained SQL metadata. Derived proposal consumers also
    verify the immutable computation envelope before exposing or saving a choice.
    """
    operation = effect.get("operation_key", "")
    if not isinstance(operation, str):
        return False
    if operation.startswith("source_lookup:"):
        return True  # DurableSourceEffects still emits this genuine legacy form.
    from .publication import NativeCapture

    if not operation.startswith(OPERATION_PREFIX) or job is None:
        return False
    try:
        policy = _ReviewCapturePolicyV2.model_validate(
            job["pins"]["sources"]["capture_policies"][result.coverage.source_id])
        qualification = policy.source_policy_digest
        if policy.kind in {"computed", "pinned_dataset"}:
            from .derivation_contracts import DERIVATION_RULE_VERSION

            expected_source = "georeference_spatial" if policy.kind == "computed" else "georeference_history"
            if policy.source_id != expected_source or result.coverage.source_version != DERIVATION_RULE_VERSION:
                return False
            qualification = digest(DERIVATION_RULE_VERSION)
        saved = effect["receipt"]
        raw = NativeCapture.model_validate(saved["raw_capture"])
        attempt, = [item for item in effect["attempts"] if item["attempt_id"] == saved["attempt_id"]]
        return (operation == OPERATION_PREFIX + effect["request_digest"]
            and policy.kind != "denied" and policy.source_id == result.coverage.source_id
            and qualification == result.coverage.qualification_digest
            and digest(job["pins"]) == job["binding_digest"] == effect["binding_digest"]
            and raw.byte_size > 0 and attempt["status"] == "completed"
            and attempt["raw_capture_locator"] == raw.locator
            and effect["effect_id"] == digest({"scope": effect["scope"], "operation_key": operation,
                "request_digest": effect["request_digest"], "binding_digest": effect["binding_digest"]}))
    except (KeyError, TypeError, ValueError):
        return False


def _field_review(effects: Mapping[str, Any], job_key: str, key: FieldKey, checkpoint: FieldCheckpoint,
                  *, job: Mapping[str, Any] | None = None) -> FieldReview:
    """Resolve what a waiting checkpoint cites from the durable source-lookup captures of its own field.

    Only completed source lookup/capture effects of this job and this field are read, and only the typed
    SourceResult is kept: model captures, other fields' captures and raw response bodies never appear.

    The review decorates a read that also finalizes runs (the worker reads the thread after publishing),
    so it never raises. A capture that does not validate or that cannot be shown is skipped as a whole;
    if the review itself cannot be built the field keeps what its checkpoint says (``_reason_only``).
    """
    question, resolution = checkpoint.resolution.question, checkpoint.resolution
    cited = _cited_evidence(checkpoint)
    evidence, candidates, resolved, seen = [], [], set(), {}
    for effect_id in checkpoint.effect_receipt_ids:
        effect = effects.get(effect_id)
        try:
            if (effect is None or effect["status"] != "completed" or effect["job_key"] != job_key or effect["field_keys"] != [str(key)]
                    or not effect["receipt"]):
                continue
            result = SourceResult.model_validate(effect["receipt"]["typed_payload"])
            if result.coverage.field_key != key or not candidate_source_capture(effect, result, job):
                continue
            items = [json.loads(item) for item in result.candidate_json]
            searched = next((_bounded(item.get("input_literal"), MAX_REVIEW_TEXT) for item in items
                             if isinstance(item.get("input_literal"), str)), None)
            found = [ReviewEvidence(
                evidence_id=_text(item.id), source_id=_text(item.source_id), kind=_text(item.kind),
                quote=_bounded(item.excerpt, MAX_REVIEW_TEXT), searched_text=searched,
                outcome=result.status.value, note=_bounded(result.coverage.reason, MAX_REVIEW_TEXT))
                for item in result.evidence if item.id not in resolved]
            selectable_evidence = candidate_selection_evidence(result, checkpoint)
            anchor = selectable_evidence or (result.evidence[0].id if result.evidence else None)
            options = [_candidate(item, result.coverage.source_id, anchor) for item in items]
            options = [option.model_copy(update={
                "selection_id": candidate_selection_id(job_key, key, effect_id, item),
                "selection_value": value})
                if option is not None and selectable_evidence is not None
                and result.status in {LookupStatus.SUCCESS, LookupStatus.AMBIGUOUS}
                and (value := candidate_selection_value(item)) is not None else option
                for item, option in zip(items, options, strict=True)]
            # An effect-scoped selection token is deliberately not a display identity. A repeated
            # capture of the same source candidate shows one choice, with one real retained token.
            # Hash the entire candidate, not its bounded projection: two places may share every
            # displayed word while differing in hidden coordinates or other authority metadata.
            options = [(digest({"source_id": result.coverage.source_id, "candidate": item}), option)
                       for item, option in zip(items, options, strict=True) if option is not None]
        except Exception:  # noqa: BLE001 - one unreadable capture must not fail the read
            continue
        resolved.update(item.id for item in result.evidence)
        evidence.extend(found)
        for identity, option in options:
            if identity not in seen:
                seen[identity] = len(candidates)
                candidates.append(option)
            elif candidates[seen[identity]].selection_id is None and option.selection_id is not None:
                # A failed lookup cannot hide a later successful, selectable capture of the same
                # candidate. Its evidence remains visible, and the choice cites the successful one.
                candidates[seen[identity]] = option
    try:
        return FieldReview(
            question_reason=question.reason if question else None,
            reason=_bounded(resolution.reason, MAX_REVIEW_REASON),
            evidence=tuple(evidence[:MAX_REVIEW_ITEMS]), candidates=tuple(candidates[:MAX_REVIEW_ITEMS]),
            evidence_not_shown=len(cited - resolved) + max(0, len(evidence) - MAX_REVIEW_ITEMS),
            candidates_not_shown=max(0, len(candidates) - MAX_REVIEW_ITEMS))
    except Exception:  # noqa: BLE001 - see the docstring
        return _reason_only(checkpoint)


from specimen_digitization.application.human_field_carry import PreservedHumanFieldOutcome


class PreservedHumanBase(FrozenRecord):
    contract_version: Literal["preserved-human-base/v2"] = "preserved-human-base/v2"
    canonical_run_id: str
    registration_record_revision: int = Field(strict=True, ge=1, le=9007199254740991)
    registration_snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    outcome_count: int = Field(strict=True, ge=1, le=20)
    outcome_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    # Clients hash these exact UTF-8 bytes; JS-decoded numeric projections are
    # never reserialized to establish lossless provenance.
    outcomes_json: str = Field(min_length=2, max_length=4 * 1024 * 1024)


def preserved_outcomes_json(outcomes):
    def finite(item):
        if isinstance(item, float) and not math.isfinite(item):
            raise ValueError("nonfinite")
        if isinstance(item, dict):
            if any(not isinstance(k, str) for k in item):
                raise ValueError("nonstring_json_key")
            for value in item.values():
                finite(value)
        elif isinstance(item, (list, tuple)):
            for value in item:
                finite(value)
    try:
        for outcome in outcomes.values():
            finite(outcome.model_dump(mode="python"))
        text = json.dumps({k: v.model_dump(mode="json") for k, v in sorted(outcomes.items())},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        if len(text.encode("utf-8")) > 4 * 1024 * 1024:
            raise ValueError("oversized")
        return text
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("preserved_human_outcome_json_invalid") from None


def preserved_base_matches(base, outcomes):
    text = preserved_outcomes_json(outcomes)
    return (base is not None and base.outcomes_json == text
        and base.outcome_count == len(outcomes)
        and base.outcome_digest == hashlib.sha256(text.encode("utf-8")).hexdigest())


class FieldThread(FrozenRecord):
    field_key: FieldKey
    work_state: WorkState
    value: FieldValue
    checkpoint: FieldCheckpoint | None = None
    blocker_code: str | None = None
    actions: tuple[Literal["retry_field", "supply_information", "review_proposal"], ...] = ()
    review: FieldReview | None = None
    preserved_human: PreservedHumanFieldOutcome | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def valid_preserved_human(self):
        carry = self.preserved_human
        if carry is not None and (carry.field_key != self.field_key or carry.value != self.value
                or self.work_state != WorkState.WAITING_HUMAN or self.checkpoint is not None
                or self.actions or self.review is not None or self.blocker_code != "preserved_human_decision"):
            raise ValueError("preserved_human_thread_field_mismatch")
        return self


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
    preserved_human_count: int = Field(default=0, strict=True, ge=0, le=20, exclude_if=lambda value: value == 0)
    preserved_human_base: PreservedHumanBase | None = Field(default=None, exclude_if=lambda value: value is None)
    trace_ids: tuple[str, ...] = ()
    historical: bool = Field(default=False, exclude_if=lambda value: not value)
    canonical_revision: int | None = Field(default=None, strict=True, ge=0, exclude_if=lambda value: value is None)
    review_saved_revision: int | None = Field(default=None, strict=True, ge=0, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def valid_preserved_base(self):
        carries = {str(f.field_key): f.preserved_human for f in self.fields if f.preserved_human is not None}
        if not carries:
            if self.preserved_human_count or self.preserved_human_base is not None:
                raise ValueError("preserved_human_thread_base_mismatch")
            return self
        base = self.preserved_human_base
        if (base is None or len(self.fields) != 20 or {f.field_key for f in self.fields} != set(ALL_FIELDS)
                or self.preserved_human_count != len(carries) or base.outcome_count != len(carries)
                or base.registration_snapshot_sha256 != self.scope.input_digest
                or not preserved_base_matches(base, carries)
                or any((v.organization_id, v.collection_id, v.specimen_id) != (
                    self.scope.organization_id, self.scope.collection_id, self.scope.specimen_id)
                    or v.canonical_run_id != base.canonical_run_id or v.source_sha256 != base.source_sha256
                    or v.fresh_run_revision > base.registration_record_revision for v in carries.values())
                or self.resolved_count != sum(f.checkpoint is not None and f.work_state == WorkState.RESOLVED for f in self.fields)
                or self.exception_count != sum(f.checkpoint is not None and f.work_state == WorkState.NONBLOCKING_EXCEPTION for f in self.fields)):
            raise ValueError("preserved_human_thread_base_mismatch")
        return self


class ResearchThreadReader:
    """Re-check membership on every read; never returns raw models or credentials."""

    def __init__(self, journal: DurableResearchJournal):
        self.journal = journal

    async def read(self, scope: ResearchScope) -> ResearchThread:
        checkpoints = {item.field_key:item for item in await self.journal.load(scope)}
        document = await asyncio.to_thread(self.journal.store._read, self.journal.scope)
        job = self.journal.store._job(document.state, self.journal.scope)
        from specimen_digitization.application.human_field_carry import job_outcomes
        preserved_reader = getattr(self.journal, "preserved_human_outcomes", None)
        if preserved_reader is None and job.get("preserved_human_outcomes"):
            raise StaleWork("preserved_human_server_reader_unavailable")
        preserved = {} if preserved_reader is None else await preserved_reader(scope)
        if preserved != job_outcomes(job):
            raise StaleWork("preserved_human_thread_state_changed")
        carry_base = None
        if preserved:
            runs = {v.canonical_run_id for v in preserved.values()}
            sources = {v.source_sha256 for v in preserved.values()}
            if len(runs) != 1 or len(sources) != 1 or any(
                    (v.organization_id, v.collection_id, v.specimen_id) != (
                        scope.organization_id, scope.collection_id, scope.specimen_id)
                    or v.fresh_run_revision > job["record_revision"] for v in preserved.values()):
                raise StaleWork("preserved_human_thread_base_mismatch")
            carry_base = PreservedHumanBase(canonical_run_id=next(iter(runs)),
                registration_record_revision=job["record_revision"],
                registration_snapshot_sha256=scope.input_digest,
                source_sha256=next(iter(sources)), outcome_count=len(preserved),
                outcome_digest=digest({k: v.model_dump(mode="json") for k, v in sorted(preserved.items())}),
                outcomes_json=preserved_outcomes_json(preserved))
        fields = []
        for key in ALL_FIELDS:
            checkpoint = checkpoints.get(key)
            work_state = checkpoint.resolution.work_state if checkpoint else WorkState.PENDING
            stored = job["fields"].get(str(key), {})
            if stored.get("locked") and checkpoint is None:
                work_state = WorkState.WAITING_HUMAN if str(key) in preserved else WorkState.WAITING_POLICY
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
                if command_id is None and not blocked_retry and work_state in {WorkState.OPERATIONAL_FAILED, WorkState.RETRY_SCHEDULED, WorkState.WAITING_SOURCE}:
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
            if str(key) in preserved:
                blocker = "preserved_human_decision"
            review = None
            if checkpoint is not None and checkpoint.resolution.work_state in REVIEW_STATES:
                review = _field_review(document.state["effects"], self.journal.scope.key, key, checkpoint, job=job)
                if job["paused"] or stored.get("locked") or command_id is not None:
                    review = review.model_copy(update={"candidates": tuple(
                        candidate.model_copy(update={"selection_id": None, "selection_value": None})
                        for candidate in review.candidates)})
            fields.append(FieldThread(field_key=key, work_state=work_state,
                value=preserved[str(key)].value if str(key) in preserved else checkpoint.resolution.value if checkpoint else FieldValue(),
                checkpoint=checkpoint, blocker_code=blocker, actions=tuple(actions), review=review,
                preserved_human=preserved.get(str(key))))
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
            resolved_count=sum(item.checkpoint is not None and item.work_state == WorkState.RESOLVED for item in fields),
            exception_count=sum(item.checkpoint is not None and item.work_state == WorkState.NONBLOCKING_EXCEPTION for item in fields),
            preserved_human_count=len(preserved), preserved_human_base=carry_base)
