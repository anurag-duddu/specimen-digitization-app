"""Persisted runtime admission must precede every research effect."""

import asyncio
from dataclasses import replace

import pytest

from specimen_digitization.application.domain import FieldValue
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, FieldProfile, FieldResolution,
    ResearchScope, SpecialistRequest, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.engine import ResearchEngine
from specimen_digitization.research_harness.journal import DurableResearchJournal
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, DurabilityScope, ResearchStore, SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.runtime import runtime_pins


def setup(tmp_path, alter=None):
    profile = CollectionProfile(id="insects", version="2", organization_id="org-test",
        collection_id="collection-test", ancestry=("org-test", "collection-test"),
        fields=tuple(FieldProfile(field_key=key) for key in ALL_FIELDS), knowledge_version="test")
    scope = ResearchScope(organization_id="org-test", collection_id="collection-test",
        specimen_id="specimen-test", job_id="job-test", generation=1,
        input_digest="a"*64, profile_digest=digest(profile), sensitive=False)
    requests = {role:SpecialistRequest(scope=scope, role=role, field_keys=keys,
        prompt=resolve_prompt(role, profile_digest=scope.profile_digest,
            source_registry_digest="b"*64, toolset_digest="c"*64,
            model_route="harness-deepseek", output_schema_digest="d"*64))
        for role,keys in ROLE_FIELDS.items()}
    settings = {"max_tokens":128}
    pins = runtime_pins(profile, requests,
        model={role:{"route":"harness-deepseek"} for role in requests}, settings=settings)
    if alter:
        pins = alter(pins)
    durable = DurabilityScope(scope.organization_id, scope.collection_id, scope.specimen_id,
        scope.job_id, scope.generation, "operator-test", False)
    backend = SqliteStateBackend(tmp_path / "journal.sqlite")
    backend.grant(durable)
    store = ResearchStore(backend, "same-existing-program")
    store.initialize(durable, BudgetPolicy(100))
    store.create_job(durable, pins, list(ALL_FIELDS))
    journal = DurableResearchJournal(store, durable, store.claim(durable, "worker-test"))
    return profile, requests, journal, digest(settings)


def test_exact_persisted_generation_accepts_checkpoint_and_restart(tmp_path):
    _, requests, journal, settings_digest = setup(tmp_path)
    request = requests[SpecialistRole.GEOGRAPHY]
    asyncio.run(journal.validate_request(request, model_settings_digest=settings_digest))
    resolution = FieldResolution(field_key=request.field_keys[0], work_state=WorkState.WAITING_SOURCE,
        value=FieldValue(), reason="source_not_qualified")
    saved = asyncio.run(journal.commit(request, (resolution,), receipt_ids=(),
        model_settings_digest=settings_digest))
    reopened = DurableResearchJournal(journal.store, journal.scope, journal.lease)
    assert asyncio.run(reopened.load(request.scope)) == saved


@pytest.mark.parametrize("alter", [
    lambda p:replace(p, profile={**p.profile, "version":"changed"}),
    lambda p:replace(p, prompts={}),
    lambda p:replace(p, sources={"registry_digest":"f"*64}),
    lambda p:replace(p, model={str(role):{"route":"different"} for role in SpecialistRole}),
    lambda p:replace(p, settings={"max_tokens":4096}),
])
def test_persisted_pin_drift_blocks_before_harness_construction(tmp_path, alter):
    profile, requests, journal, settings_digest = setup(tmp_path, alter)
    calls = []
    engine = ResearchEngine(profile=profile, requests=requests, journal=journal,
        harness_factory=lambda selected:calls.append(selected), model_settings_digest=settings_digest)
    with pytest.raises((StaleWork, PermissionError), match="binding_mismatch"):
        asyncio.run(engine.run())
    assert calls == []
