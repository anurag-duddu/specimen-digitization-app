"""Independent synthetic/offline adversarial checks for ROOT-owned boundaries.

No application source is changed. Real local SQLite lifecycle writes are used;
provider, source, canonical writer and validation are deterministic fakes.
"""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from specimen_digitization.application.domain import FieldValue, Principal, Scope, ValueState
from specimen_digitization.research_harness.compatibility import (
    PublicationGuard, PublishedResearch, ResearchPublication, ResearchPublicationBridge,
)
from specimen_digitization.research_harness.contracts import (
    ALL_FIELDS, ROLE_FIELDS, CollectionProfile, DependencyPin, FieldCheckpoint,
    FieldKey, FieldProfile, FieldResolution, ResearchScope, SpecialistRequest,
    SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.engine import ResearchEngine
from specimen_digitization.research_harness.journal import DurableResearchJournal
from specimen_digitization.research_harness.persistence import (
    BudgetPolicy, DurabilityScope, PinnedRuntime, ResearchStore, SqliteStateBackend, StaleWork,
)
from specimen_digitization.research_harness.prompts import resolve_prompt
from specimen_digitization.research_harness.runtime import runtime_pins
from specimen_digitization.research_harness.thread_view import ResearchThreadReader


def admitted(tmp_path):
    profile = CollectionProfile(id="steward-synthetic", version="review-1",
        organization_id="review-org", collection_id="review-collection",
        ancestry=("review-org", "review-collection"),
        fields=tuple(FieldProfile(field_key=key) for key in ALL_FIELDS),
        knowledge_version="independent-review-1")
    scope = ResearchScope(organization_id=profile.organization_id,
        collection_id=profile.collection_id, specimen_id="review-specimen",
        job_id="review-job", generation=1, input_digest="1"*64,
        profile_digest=digest(profile), sensitive=False)
    requests = {role:SpecialistRequest(scope=scope, role=role, field_keys=keys,
        prompt=resolve_prompt(role, profile_digest=scope.profile_digest,
            source_registry_digest="2"*64, toolset_digest="3"*64,
            model_route="harness-deepseek", output_schema_digest="4"*64))
        for role, keys in ROLE_FIELDS.items()}
    settings = {"max_tokens":128}
    pins = runtime_pins(profile, requests,
        model={role:{"route":"harness-deepseek"} for role in requests}, settings=settings)
    durable = DurabilityScope(scope.organization_id, scope.collection_id,
        scope.specimen_id, scope.job_id, scope.generation, "review-actor", False)
    backend = SqliteStateBackend(tmp_path / "state.sqlite")
    backend.grant(durable)
    store = ResearchStore(backend, "steward-shared-program")
    store.initialize(durable, BudgetPolicy(100))
    store.create_job(durable, pins, list(ALL_FIELDS))
    lease = store.claim(durable, "review-worker", ttl_seconds=120)
    journal = DurableResearchJournal(store, durable, lease)
    return profile, scope, requests, journal, digest(settings)


def waiting(key, reason="synthetic_required_source_unqualified"):
    return FieldResolution(field_key=key, work_state=WorkState.WAITING_SOURCE,
        value=FieldValue(), reason=reason)


def resolved(key, text):
    return FieldResolution(field_key=key, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, normalized=text),
        evidence_ids=("synthetic-independent-evidence",), reason="synthetic_fixture")


def test_journal_rejects_resolution_outside_the_request_owned_fields(tmp_path):
    _, _, requests, journal, settings = admitted(tmp_path)
    request = requests[SpecialistRole.TAXONOMY]
    with pytest.raises((ValueError, PermissionError), match="field|coverage|scope|role"):
        asyncio.run(journal.commit(request, (waiting(FieldKey.COUNTRY),),
            receipt_ids=(), model_settings_digest=settings))


def test_journal_rejects_duplicate_results_for_one_requested_field(tmp_path):
    _, _, requests, journal, settings = admitted(tmp_path)
    request = requests[SpecialistRole.TAXONOMY]
    with pytest.raises((ValueError, PermissionError), match="duplicate|coverage|field"):
        asyncio.run(journal.commit(request,
            (waiting(FieldKey.TAXON, "first"), waiting(FieldKey.TAXON, "second")),
            receipt_ids=(), model_settings_digest=settings))


def test_engine_return_retains_checkpoint_committed_before_sibling_field_failure(tmp_path):
    profile, scope, requests, journal, settings = admitted(tmp_path)
    request = requests[SpecialistRole.GEOGRAPHY].model_copy(
        update={"field_keys":(FieldKey.COUNTRY, FieldKey.CITY)})
    original_checkpoint = journal.store.checkpoint

    def fail_city(*args, **kwargs):
        if (args[2] if len(args) > 2 else kwargs["field_key"]) == "city":
            raise RuntimeError("injected_local_sql_failure")
        return original_checkpoint(*args, **kwargs)

    journal.store.checkpoint = fail_city

    class Harness:
        async def run_specialist(self, role):
            return SimpleNamespace(resolutions=(resolved(FieldKey.COUNTRY, "Syntheticland"),
                                                waiting(FieldKey.CITY)), source_results=(),
                                   model_effect_ids=())

    engine = ResearchEngine(profile=profile, requests={request.role:request},
        journal=journal, harness_factory=lambda _:Harness(), model_settings_digest=settings,
        validate=lambda _request, resolution, _sources:resolution)
    result = asyncio.run(engine.run())
    persisted = asyncio.run(journal.load(scope))
    assert len(persisted) == 1 and persisted[0].field_key == FieldKey.COUNTRY
    assert persisted[0].resolution.work_state == WorkState.RESOLVED
    assert result.fields[FieldKey.COUNTRY] == persisted[0].resolution
    assert persisted[0] in result.checkpoints


def test_journal_validates_consumed_dependency_digest_against_current_checkpoint(tmp_path):
    _, _, requests, journal, settings = admitted(tmp_path)
    country, = asyncio.run(journal.commit(requests[SpecialistRole.GEOGRAPHY],
        (resolved(FieldKey.COUNTRY, "Syntheticland"),), receipt_ids=(), model_settings_digest=settings))
    # Admission revision map is a data-owned interface. Set its existing revision
    # through a pure local state transaction to expose ROOT's missing digest check.
    journal.store._mutate(journal.scope,
        lambda state, _now: state["jobs"][journal.scope.key]["dependencies"].update(country=country.revision))
    forged = DependencyPin(field_key=FieldKey.COUNTRY, revision=country.revision, digest="f"*64)
    request = requests[SpecialistRole.TAXONOMY].model_copy(update={"dependencies":(forged,)})
    resolution = resolved(FieldKey.TAXON, "Syntheticus").model_copy(update={"dependencies":(forged,)})
    with pytest.raises((ValueError, PermissionError, StaleWork), match="dependency|Consumed|binding"):
        asyncio.run(journal.commit(request, (resolution,), receipt_ids=(), model_settings_digest=settings))


def test_journal_does_not_drop_a_consumed_request_dependency_from_checkpoint(tmp_path):
    _, _, requests, journal, settings = admitted(tmp_path)
    country, = asyncio.run(journal.commit(requests[SpecialistRole.GEOGRAPHY],
        (resolved(FieldKey.COUNTRY, "Syntheticland"),), receipt_ids=(), model_settings_digest=settings))
    dependency = DependencyPin(field_key=FieldKey.COUNTRY, revision=country.revision,
        digest=digest(country.resolution))
    request = requests[SpecialistRole.TAXONOMY].model_copy(update={"dependencies":(dependency,)})
    taxon, = asyncio.run(journal.commit(request, (resolved(FieldKey.TAXON, "Syntheticus"),),
        receipt_ids=(), model_settings_digest=settings))
    assert taxon.resolution.dependencies == request.dependencies


def test_thread_can_read_retained_neighbor_after_unrelated_human_correction(tmp_path):
    _, scope, requests, journal, settings = admitted(tmp_path)
    country, = asyncio.run(journal.commit(requests[SpecialistRole.GEOGRAPHY],
        (resolved(FieldKey.COUNTRY, "Syntheticland"),), receipt_ids=(), model_settings_digest=settings))
    journal.store.backend.grant(journal.scope, role="reviewer")
    current_pins = PinnedRuntime(**journal.store.job(journal.scope)["pins"])
    new_pins = replace(current_pins, input_digest="e"*64)
    corrected = journal.store.correct_fields(journal.scope, ["taxon"],
        expected_generation=1, new_pins=new_pins)
    reopened_scope = scope.model_copy(update={"generation":corrected.generation,
                                              "input_digest":new_pins.input_digest})
    reopened = DurableResearchJournal(journal.store, corrected,
        journal.store.claim(corrected, "next-worker", ttl_seconds=120))
    thread = asyncio.run(ResearchThreadReader(reopened).read(reopened_scope))
    retained = next(field for field in thread.fields if field.field_key == FieldKey.COUNTRY)
    assert retained.value == country.resolution.value
    assert retained.work_state == WorkState.RESOLVED


def test_publication_rejects_receipt_with_record_revision_below_expected(tmp_path):
    _, scope, requests, journal, settings = admitted(tmp_path)
    checkpoint, = asyncio.run(journal.commit(requests[SpecialistRole.TAXONOMY],
        (waiting(FieldKey.TAXON),), receipt_ids=(), model_settings_digest=settings))
    guard = PublicationGuard(scope=scope, binding_digest="a"*64,
        lease_owner=journal.lease.owner, lease_fence=journal.lease.fence,
        lease_expires_at=journal.lease.expires_at, expected_record_revision=10,
        checkpoint_revisions={"taxon":checkpoint.revision},
        checkpoint_digests={"taxon":digest(checkpoint)}, dependency_revisions={}, receipt_ids=())
    publication = ResearchPublication(guard=guard, checkpoints=(checkpoint,), idempotency_key="steward-publication")

    class WrongRevisionWriter:
        research_contract_version = "research-publication-v1"
        async def publish_research(self, _principal, publication):
            return PublishedResearch(scope=scope, record_revision=1,
                                     publication_digest=digest(publication))

    principal = Principal(user_id="review-actor", role="reviewer",
        scope=Scope(organization_id=scope.organization_id, collection_id=scope.collection_id))
    with pytest.raises(ValueError, match="revision|receipt"):
        asyncio.run(ResearchPublicationBridge(WrongRevisionWriter()).publish(principal, publication))


def test_thread_reads_the_trace_context_retained_by_the_durable_job(tmp_path):
    _, scope, requests, journal, settings = admitted(tmp_path)
    saved = {"trace_id":"1"*32, "span_id":"2"*16, "trace_flags":1}
    journal.store.bind_trace(journal.scope, journal.lease, saved)
    asyncio.run(journal.commit(requests[SpecialistRole.TAXONOMY],
        (waiting(FieldKey.TAXON),), receipt_ids=(), model_settings_digest=settings))
    thread = asyncio.run(ResearchThreadReader(journal).read(scope))
    assert thread.trace_ids == (saved["trace_id"],)


def test_revoked_membership_denies_journal_load_and_commit(tmp_path):
    _, scope, requests, journal, settings = admitted(tmp_path)
    journal.store.backend.revoke(journal.scope)
    with pytest.raises(PermissionError):
        asyncio.run(journal.load(scope))
    with pytest.raises(PermissionError):
        asyncio.run(journal.commit(requests[SpecialistRole.TAXONOMY],
            (waiting(FieldKey.TAXON),), receipt_ids=(), model_settings_digest=settings))


def test_changed_input_digest_denies_read_before_returning_private_values(tmp_path):
    _, scope, _, journal, _ = admitted(tmp_path)
    changed = scope.model_copy(update={"input_digest":"e"*64})
    with pytest.raises(PermissionError, match="input_binding"):
        asyncio.run(journal.load(changed))


def test_expired_or_stale_lease_cannot_commit(tmp_path):
    _, _, requests, journal, settings = admitted(tmp_path)
    journal.lease = replace(journal.lease, expires_at=1)
    with pytest.raises(StaleWork, match="lease"):
        asyncio.run(journal.commit(requests[SpecialistRole.TAXONOMY],
            (waiting(FieldKey.TAXON),), receipt_ids=(), model_settings_digest=settings))
