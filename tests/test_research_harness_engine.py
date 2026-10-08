"""Scheduler controls and field coverage without live provider effects."""

import asyncio
from dataclasses import dataclass

import pytest

from specimen_digitization.application.domain import FieldValue
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, FieldKey, FieldProfile,
    FieldResolution, ResearchScope, SpecialistRequest, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.engine import ResearchEngine, RunStatus
from specimen_digitization.research_harness.prompts import resolve_prompt


class Journal:
    def __init__(self):
        self.checkpoints = {}
        self.executed = []

    async def validate_request(self, request, *, model_settings_digest):
        pass

    async def field_revisions(self, scope):
        return {key:self.checkpoints[key].revision if key in self.checkpoints else 0 for key in ALL_FIELDS}

    async def protected_fields(self, scope):
        return ()

    async def trace_context(self, scope):
        return getattr(self, "trace_parent", None)

    async def bind_trace(self, scope, parent):
        self.trace_parent = parent

    async def load(self, scope):
        return tuple(self.checkpoints.values())

    async def commit(self, request, resolutions, *, receipt_ids, model_settings_digest):
        from specimen_digitization.research_harness.contracts import FieldCheckpoint
        result = []
        for item in resolutions:
            previous = self.checkpoints.get(item.field_key)
            checkpoint = FieldCheckpoint(
                scope=request.scope, field_key=item.field_key,
                revision=1 if previous is None else previous.revision + 1,
                resolution=item, prompt_digest=request.prompt.digest,
                model_settings_digest=model_settings_digest,
                source_registry_digest=request.prompt.source_registry_digest,
                effect_receipt_ids=tuple(receipt_ids),
            )
            self.checkpoints[item.field_key] = checkpoint
            result.append(checkpoint)
        self.executed.append(request.role)
        return tuple(result)

    async def retry_eligible(self, scope, field_key):
        return False


@dataclass
class Run:
    resolutions: tuple
    tool_receipts: tuple = ()
    source_results: tuple = ()
    model_effect_ids: tuple = ()


class Harness:
    def __init__(self, requests, seen, failure=None):
        self.requests, self.seen, self.failure = requests, seen, failure

    async def run_specialist(self, role):
        self.seen.append(role)
        if role == self.failure:
            raise RuntimeError("PRIVATE_PROVIDER_CANARY")
        request = self.requests[role]
        return Run(tuple(FieldResolution(
            field_key=key, work_state=WorkState.WAITING_SOURCE,
            value=FieldValue(), reason="qualified_source_prerequisite",
        ) for key in request.field_keys))


def inputs():
    profile = CollectionProfile(
        id="insects", version="2", organization_id="org-test", collection_id="collection-test",
        ancestry=("org-test", "collection-test"),
        fields=tuple(FieldProfile(field_key=k) for k in ALL_FIELDS), knowledge_version="test-v1",
    )
    scope = ResearchScope(
        organization_id="org-test", collection_id="collection-test", specimen_id="specimen-test",
        job_id="job-test", generation=0, input_digest="a"*64,
        profile_digest=digest(profile), sensitive=False,
    )
    requests = {role: SpecialistRequest(
        scope=scope, role=role, field_keys=keys,
        prompt=resolve_prompt(role, profile_digest=scope.profile_digest,
            source_registry_digest="b"*64, toolset_digest="c"*64,
            model_route="harness-deepseek", output_schema_digest="d"*64),
    ) for role,keys in ROLE_FIELDS.items()}
    return profile, scope, requests


def test_failure_preserves_every_sibling_checkpoint_and_has_no_human_review():
    profile, scope, requests = inputs()
    journal, seen = Journal(), []
    engine = ResearchEngine(
        profile=profile, requests=requests, journal=journal,
        harness_factory=lambda req: Harness(req, seen, SpecialistRole.TAXONOMY),
        validate=lambda request, resolution, sources: resolution,
        model_settings_digest="e"*64, max_concurrency=2,
    )
    result = asyncio.run(engine.run())
    assert len(result.fields) == 20 and set(result.fields) == set(ALL_FIELDS)
    assert result.fields[FieldKey.TAXON].work_state == WorkState.OPERATIONAL_FAILED
    assert result.fields[FieldKey.COUNTRY].work_state == WorkState.WAITING_SOURCE
    assert result.status == RunStatus.BLOCKED and not result.clearance_eligible
    assert all(x.question is None for x in result.fields.values())
    assert "PRIVATE_PROVIDER_CANARY" not in str(result)
    assert set(seen) == set(SpecialistRole)
    assert len(journal.checkpoints) == 20
    seen.clear()
    replayed = asyncio.run(engine.run())
    assert replayed.fields == result.fields and not seen


def test_narrow_taxonomy_slice_does_not_hide_other_pending_mandatory_fields():
    profile, scope, requests = inputs()
    journal, seen = Journal(), []
    engine = ResearchEngine(
        profile=profile, requests={SpecialistRole.TAXONOMY:requests[SpecialistRole.TAXONOMY]},
        journal=journal, harness_factory=lambda req: Harness(req, seen),
        validate=lambda request, resolution, sources: resolution,
        model_settings_digest="e"*64,
    )
    result = asyncio.run(engine.run())
    assert len(result.fields) == 20
    assert result.fields[FieldKey.COUNTRY].work_state == WorkState.PENDING
    assert not result.clearance_eligible


def test_sensitive_context_and_changed_pin_block_before_any_model_request():
    profile, scope, requests = inputs()
    sensitive_scope = scope.model_copy(update={"sensitive":True})
    sensitive = {role:req.model_copy(update={"scope":sensitive_scope}) for role,req in requests.items()}
    seen = []
    with pytest.raises(ValueError, match="sensitive"):
        ResearchEngine(profile=profile, requests=sensitive, journal=Journal(),
            harness_factory=lambda req: Harness(req, seen), model_settings_digest="e"*64)
    assert not seen


def test_persisted_binding_failure_precedes_agent_construction():
    class StaleJournal(Journal):
        async def validate_request(self, request, *, model_settings_digest):
            raise ValueError("stale_persisted_prompt")

    profile, _, requests = inputs()
    seen = []
    engine = ResearchEngine(profile=profile, requests=requests, journal=StaleJournal(),
        harness_factory=lambda req: seen.append("constructed"), model_settings_digest="e"*64)
    with pytest.raises(ValueError, match="stale_persisted_prompt"):
        asyncio.run(engine.run())
    assert seen == []


def test_explicit_retry_investigates_only_requested_failure_keeps_other_pending_fields():
    class RetryJournal(Journal):
        async def retry_eligible(self, scope, field_key):
            return True

    profile, scope, requests = inputs()
    journal, seen = RetryJournal(), []
    failure = FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.OPERATIONAL_FAILED,
        value=FieldValue(), reason="specialist_operational_failure")
    asyncio.run(journal.commit(requests[SpecialistRole.TAXONOMY], (failure,),
        receipt_ids=(), model_settings_digest="e"*64))
    engine = ResearchEngine(profile=profile, requests=requests, journal=journal,
        harness_factory=lambda selected:Harness(selected, seen),
        validate=lambda request, resolution, sources:resolution,
        model_settings_digest="e"*64)
    result = asyncio.run(engine.run(retry_fields=(FieldKey.TAXON,)))
    assert seen == [SpecialistRole.TAXONOMY]
    assert set(journal.checkpoints) == {FieldKey.TAXON}
    assert result.fields[FieldKey.COUNTRY].work_state == WorkState.PENDING
    assert result.fields[FieldKey.HABITAT].work_state == WorkState.PENDING


def test_retry_cannot_turn_source_prerequisite_into_new_investigation():
    # This unsent prerequisite has no captured completed source failure. The
    # journal must refuse retry eligibility rather than grant a new investigation.
    profile, scope, requests = inputs()
    journal, seen = Journal(), []
    prerequisite = FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.WAITING_SOURCE,
        value=FieldValue(), reason="qualified_source_prerequisite")
    asyncio.run(journal.commit(requests[SpecialistRole.TAXONOMY], (prerequisite,),
        receipt_ids=(), model_settings_digest="e"*64))
    before = dict(journal.checkpoints)
    def construct(selected):
        seen.append("constructed")
        return Harness(selected, seen)
    engine = ResearchEngine(profile=profile, requests=requests, journal=journal,
        harness_factory=construct, model_settings_digest="e"*64)
    with pytest.raises(ValueError, match="field_retry_requires_safe_current_effect_state"):
        asyncio.run(engine.run(retry_fields=(FieldKey.TAXON,)))
    assert seen == [] and journal.checkpoints == before
