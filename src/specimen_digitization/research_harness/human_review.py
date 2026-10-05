"""Canonical human choices and an immutable, explicitly historical research report.

Research captures live under worker-only storage. This bridge copies the SQL
retained typed source provenance into ordinary application evidence storage; it
never needs worker capture IAM or issues source/model calls.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from specimen_digitization.application.domain import Evidence, ValueState
from specimen_digitization.application.storage import Conflict, canonical_json, digest
from .candidate_selection import retained_candidate
from .canonical_binding import BindingUnavailable, CanonicalIdentity
from .compatibility import PublicationUnavailable
from .contracts import FieldKey, FrozenRecord, ResearchScope
from .discovery import DiscoveryCapabilities
from .journal import DurableResearchJournal
from .persistence import Lease, StaleWork
from .thread_view import ResearchThread, ResearchThreadReader

REPORT_KEY = "human_review_research_report"
REPORT_LIMIT = 8 * 1024 * 1024


@dataclass
class CandidateReviewContext:
    binding: object
    document: object
    thread: ResearchThread
    selections: dict[str, dict]

    @classmethod
    async def load(cls, discovery, principal, specimen, decisions):
        if principal.role not in {"reviewer", "manager", "admin"}:
            raise PermissionError("research_access_denied")
        try:
            binding, store, scope, document, _ = await discovery.bound_state(principal, specimen.id)
        except (BindingUnavailable, PublicationUnavailable, StaleWork):
            raise Conflict("Research choices require a current binding; reopen the record") from None
        if (binding.canonical.record_revision != specimen.version
                or str(binding.canonical.canonical_run_id) != specimen.run.id):
            raise Conflict("Research candidates belong to another record revision")
        selections = {}
        selected_fields = {item.target_id for item in decisions if item.kind == "research_candidate"}
        if any(item.kind not in {"research_candidate", "field", "approve", "coverage"} for item in decisions):
            raise ValueError("Save source or transcription changes before choosing research candidates")
        if any(item.kind != "research_candidate" and item.target_id in selected_fields for item in decisions):
            raise ValueError("Choose one pending change per research field")
        for decision in decisions:
            if decision.kind != "research_candidate":
                continue
            if set(decision.after) != {"selection_id"} or decision.evidence_ids or decision.before:
                raise ValueError("Research choices accept only the retained selection_id")
            keys = [key for key, canonical in binding.field_mapping.items() if canonical == decision.target_id]
            if len(keys) != 1 or decision.target_id in selections:
                raise ValueError("Select one candidate per canonical field")
            field_key = FieldKey(keys[0])
            if field_key in binding.research_locks:
                raise Conflict("A human decision already locks this field")
            try:
                selections[decision.target_id] = retained_candidate(
                    document, scope.key, field_key, decision.after["selection_id"])
            except StaleWork:
                raise Conflict("Research candidate state changed; reopen the record") from None
        journal = DurableResearchJournal(store, scope, Lease(scope.key, "human-review-read", 0, scope.generation, 0))
        thread = await ResearchThreadReader(journal).read(binding.research_scope())
        return cls(binding, document, thread, selections)

    async def recheck(self, discovery, principal, specimen_id):
        current = await discovery.binding(principal, specimen_id)
        if not self.binding.same_snapshot(current):
            raise Conflict("Research state changed; reopen the record")

    def apply(self, specimen, field_key, blobs, reason):
        choice = self.selections[field_key]
        # This is a copy of retained SQL provenance, not the provider raw response.
        raw = canonical_json({"kind": "human_research_candidate", **choice}).encode()
        evidence = Evidence(kind="authority_selection", source=choice["source_id"],
            locator="research-candidate:" + choice["selection_id"],
            excerpt=choice["value"] + (" | " + choice["authority_id"] if choice["authority_id"] else ""),
            raw_ref=blobs.put(raw), digest=hashlib.sha256(raw).hexdigest())
        specimen.run.evidence.append(evidence)
        field = specimen.run.fields[field_key]
        # Preserve literal, source observations and every reader's own verbatim.
        field.state = ValueState.SUPPORTED
        field.parsed = field.normalized = choice["value"]
        field.authority_id = choice["authority_id"]
        field.authority_identity = None
        field.layer = "settled"
        field.derived_from = []
        field.settled_observation_ids = []
        field.precision = choice["source_candidate"].get("precision") if choice["source_candidate"].get("precision") in {"day", "month", "year"} else None
        century_rule = choice["source_candidate"].get("century_rule")
        field.century_rule = century_rule if isinstance(century_rule, str) else None
        field.evidence_ids = list(dict.fromkeys([*field.evidence_ids, evidence.id]))
        field.evidence_relations[evidence.id] = "decides"
        field.reason = "Human selected retained research candidate: " + reason
        specimen.run.human_approved = False
        # Explicit saved lock accompanies the genuine review audit. Provisioning
        # must import it when a later job is requested; old V2 binding goes stale.
        locks = specimen.run.dependencies.setdefault("human_review_field_locks", {})
        locks[field_key] = {"selection_id": choice["selection_id"], "evidence_id": evidence.id}
        return {"field_key": field_key, "selection_id": choice["selection_id"],
            "value": choice["value"], "authority_id": choice["authority_id"],
            "source_id": choice["source_id"], "effect_id": choice["effect_id"],
            "checkpoint_id": choice["checkpoint_id"], "evidence_ids": [evidence.id],
            "precision": field.precision, "century_rule": field.century_rule}

    def retain_report(self, specimen, blobs, *, request_key, request_digest, actor):
        fields = []
        for field in self.thread.fields:
            review = field.review
            if review is not None:
                review = review.model_copy(update={"candidates": tuple(candidate.model_copy(
                    update={"selection_id": None, "selection_value": None}) for candidate in review.candidates)})
            fields.append(field.model_copy(update={"actions": (), "review": review}))
        report = self.thread.model_copy(update={"fields": tuple(fields), "historical": True,
            "canonical_revision": specimen.version, "review_saved_revision": specimen.version + 1})
        payload = {"thread": report.model_dump(mode="json"),
            "canonical": self.binding.canonical.model_dump(mode="json"),
            "run_id": specimen.run.id, "review_saved_revision": specimen.version + 1}
        raw = canonical_json(payload).encode()
        if len(raw) > REPORT_LIMIT:
            raise ValueError("Research review report exceeds retained artifact limit")
        specimen.run.dependencies[REPORT_KEY] = {"blob_ref": blobs.put(raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw),
            "run_id": specimen.run.id, "source_revision": specimen.version,
            "review_saved_revision": specimen.version + 1,
            "request_key": request_key, "request_digest": request_digest, "actor": actor}


class HistoricalResearchDiscovery(FrozenRecord):
    contract_version: Literal["canonical-binding/v2", "canonical-binding/v1"]
    canonical: CanonicalIdentity
    scope: ResearchScope
    human_locked_fields: tuple[FieldKey, ...]
    capabilities: DiscoveryCapabilities
    historical: Literal[True] = True
    canonical_revision: int
    review_saved_revision: int
    retry_blocked_reason: str = "historical_after_human_review"
    review_blocked_reason: str = "historical_after_human_review"


class HistoricalReviewDiscovery:
    """Fallback reads are from a canonical saved report, never a relaxed binding."""
    def __init__(self, discovery, *, load_specimen, blobs, contract_version):
        self.current = discovery
        self.load_specimen = load_specimen
        self.blobs = blobs
        self.contract_version = contract_version

    def __getattr__(self, name):
        return getattr(self.current, name)

    async def report(self, principal, specimen_id):
        specimen = await asyncio.to_thread(self.load_specimen, principal, specimen_id)
        metadata = specimen.run.dependencies.get(REPORT_KEY)
        if (not isinstance(metadata, dict) or metadata.get("run_id") != specimen.run.id
                or metadata.get("review_saved_revision", specimen.version + 1) > specimen.version):
            raise BindingUnavailable("historical_research_report_unavailable")
        raw = await asyncio.to_thread(self.blobs.get_bounded, metadata["blob_ref"], REPORT_LIMIT)
        if len(raw) != metadata["size_bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
            raise BindingUnavailable("historical_research_report_integrity")
        payload = json.loads(raw)
        thread = ResearchThread.model_validate(payload["thread"])
        canonical = CanonicalIdentity.model_validate(payload["canonical"])
        if (thread.scope.organization_id != principal.scope.organization_id
                or thread.scope.collection_id != principal.scope.collection_id
                or thread.scope.specimen_id != specimen.id or payload["run_id"] != specimen.run.id
                or not thread.historical or thread.canonical_revision != metadata["source_revision"]
                or thread.review_saved_revision != metadata["review_saved_revision"]):
            raise BindingUnavailable("historical_research_report_scope")
        return specimen, thread, canonical

    async def discover(self, principal, specimen_id):
        try:
            return await self.current.discover(principal, specimen_id)
        except (BindingUnavailable, PublicationUnavailable):
            specimen, thread, canonical = await self.report(principal, specimen_id)
            locks = specimen.run.dependencies.get("human_review_field_locks", {})
            return HistoricalResearchDiscovery(contract_version=self.contract_version,
                canonical=canonical, scope=thread.scope,
                human_locked_fields=tuple(key for key in FieldKey if str(key) in locks),
                capabilities=DiscoveryCapabilities(read=True, retry=False, review=False),
                canonical_revision=thread.canonical_revision, review_saved_revision=thread.review_saved_revision)

    async def service(self, principal, locator):
        try:
            return await self.current.service(principal, locator)
        except (BindingUnavailable, PublicationUnavailable):
            _, thread, _ = await self.report(principal, locator.specimen_id)
            if (thread.scope.job_id, thread.scope.generation) != (locator.job_id, locator.generation):
                raise StaleWork("research_state_changed")
            return self

    async def thread(self, principal, locator):
        _, thread, _ = await self.report(principal, locator.specimen_id)
        if (thread.scope.job_id, thread.scope.generation) != (locator.job_id, locator.generation):
            raise StaleWork("research_state_changed")
        return thread

    async def retry_field(self, *_):
        raise StaleWork("historical_research_read_only")
