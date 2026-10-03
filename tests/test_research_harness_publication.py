"""SQLite translator qualification only; canonical native operation unadmitted."""

import asyncio
from dataclasses import replace

import pytest

from specimen_digitization.application.domain import FieldValue, Principal, Scope, ValueState
from specimen_digitization.research_harness.compatibility import PublicationUnavailable
from specimen_digitization.research_harness.contracts import DependencyPin, FieldKey, FieldResolution, SpecialistRole, WorkState, digest
from specimen_digitization.research_harness.journal import DurableResearchJournal
from specimen_digitization.research_harness.persistence import (
    CapturedResult, DurableEffectBroker, ImmutableFileBlobs, PinnedRuntime, StaleWork,
)
from specimen_digitization.research_harness.publication import (
    PreparedNativePublication, prepare_native_publication, publish_native_publication, validate_native_publication,
)
from test_research_harness_journal import setup


def fixture(tmp_path, *, receipt=True, raw=False):
    _, requests, journal, settings = setup(tmp_path)
    req = requests[SpecialistRole.GEOGRAPHY]
    principal = Principal(user_id=journal.scope.actor_uid, scope=Scope(
        organization_id=req.scope.organization_id, collection_id=req.scope.collection_id), role="operator")
    blobs = ImmutableFileBlobs(tmp_path / "publication-blobs")
    effect_id = None
    if receipt:
        async def dispatch(attempt, idempotency):
            return CapturedResult(typed_payload={"field_key": "country", "literal": "Peru"},
                actual_micro_usd=3, raw_payload=b"synthetic raw bytes" if raw else None,
                usage={"synthetic_source_requests": 1})
        effect = asyncio.run(DurableEffectBroker(journal.store, blobs).execute(
            journal.scope, journal.lease, "synthetic-country-evidence", {"query": "independent-fixture-label"},
            5, dispatch, field_keys=(str(FieldKey.COUNTRY),)))
        effect_id = effect.effect_id
    resolution = FieldResolution(field_key=FieldKey.COUNTRY, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal="Peru", parsed="Peru", evidence_ids=["fixture-label"]),
        evidence_ids=("fixture-label",), reason="Independent synthetic expected label")
    cp, = asyncio.run(journal.commit(req, (resolution,), receipt_ids=(effect_id,) if effect_id else (),
                                    model_settings_digest=settings))
    return req, journal, principal, blobs, cp


def prepare(req, journal, principal, blobs):
    return asyncio.run(prepare_native_publication(journal, req.scope, FieldKey.COUNTRY,
        principal=principal, expected_record_revision=0, blobs=blobs))


def corrupt(journal, change):
    def reducer(state, now):
        change(state)
    journal.store._mutate(journal.scope, reducer)


def test_actual_journal_guard_translation_keeps_distinct_native_and_typed_digests(tmp_path):
    req, journal, principal, blobs, cp = fixture(tmp_path, raw=True)
    prepared = prepare(req, journal, principal, blobs)
    basis = prepared.basis
    document = journal.store._read(journal.scope)
    native = journal.store.job(journal.scope)["fields"]["country"]["checkpoint"]
    assert prepared.publication.checkpoints == (cp,)
    assert basis.checkpoint_id == native["id"] and basis.checkpoint_digest == digest(native)
    assert basis.typed_checkpoint_digest == digest(cp) != basis.checkpoint_digest
    assert basis.original_typed_checkpoint_digest == digest(cp) and not basis.reused
    assert basis.state_revision == document.revision and basis.state_digest == digest(document.state)
    assert basis.publication_outbox_digest == digest(document.state["outbox"][basis.publication_outbox_key])
    assert basis.receipts[0].raw_capture is not None and journal.store.budget(journal.scope)["settled_micro_usd"] == 3
    assert PreparedNativePublication.model_validate_json(prepared.model_dump_json()) == prepared
    asyncio.run(validate_native_publication(journal, prepared, principal=principal, blobs=blobs))
    refreshed = prepare(req, journal, principal, blobs)
    assert refreshed.publication == prepared.publication
    assert refreshed.basis.native_guard_json == prepared.basis.native_guard_json
    # A lease-bearing no-op still performs the store's authoritative CAS.
    assert refreshed.basis.state_revision == document.revision + 1
    assert refreshed.basis.state_digest == prepared.basis.state_digest


def test_verified_prior_generation_reuse_retains_original_capture_and_native_checkpoint(tmp_path):
    req, journal, principal, blobs, original = fixture(tmp_path)
    journal.store.backend.grant(journal.scope, role="reviewer")
    old_job = journal.store.job(journal.scope)
    pins = PinnedRuntime(**{**old_job["pins"], "input_digest": "e" * 64})
    next_scope = journal.store.correct_fields(journal.scope, ["taxon"], expected_generation=1, new_pins=pins)
    reopened = DurableResearchJournal(journal.store, next_scope, journal.store.claim(next_scope, "worker-generation-two"))
    corrected_req = req.model_copy(update={"scope": req.scope.model_copy(update={"generation": 2, "input_digest": "e" * 64})})
    prepared = prepare(corrected_req, reopened, principal, blobs)
    typed = prepared.publication.checkpoints[0]
    assert typed.scope == corrected_req.scope and prepared.basis.reused
    assert typed.reused_from_checkpoint_digest == digest(original)
    assert prepared.basis.original_scope == original.scope and prepared.basis.history_digest
    assert prepared.basis.source_binding_digest == old_job["binding_digest"] != prepared.basis.binding_digest
    assert prepared.basis.checkpoint_digest == digest(old_job["fields"]["country"]["checkpoint"])
    assert prepared.basis.original_typed_checkpoint_digest == digest(original) != prepared.basis.typed_checkpoint_digest
    asyncio.run(validate_native_publication(reopened, prepared, principal=principal, blobs=blobs))
    corrupt(reopened, lambda state: state["jobs"][next_scope.key]["fields"]["country"]["reuse"].update(history_digest="f" * 64))
    with pytest.raises(StaleWork, match="reuse proof changed"):
        asyncio.run(validate_native_publication(reopened, prepared, principal=principal, blobs=blobs))


def test_current_dependency_revision_and_resolution_digest_are_bound_to_native_checkpoint(tmp_path):
    req, journal, principal, blobs, country = fixture(tmp_path, receipt=False)
    pin = DependencyPin(field_key=FieldKey.COUNTRY, revision=country.revision, digest=digest(country.resolution))
    city_request = req.model_copy(update={"field_keys": (FieldKey.CITY,), "dependencies": (pin,)})
    city = FieldResolution(field_key=FieldKey.CITY, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, parsed="Lima"), evidence_ids=("city-fixture",), reason="Independent city fixture")
    asyncio.run(journal.commit(city_request, (city,), receipt_ids=(), model_settings_digest=country.model_settings_digest))
    prepared = asyncio.run(prepare_native_publication(journal, req.scope, FieldKey.CITY,
        principal=principal, expected_record_revision=0, blobs=blobs))
    dependency, = prepared.basis.dependencies
    stored = journal.store.job(journal.scope)["fields"]["country"]["checkpoint"]
    assert dependency.revision == 1 and dependency.resolution_digest == digest(country.resolution)
    assert dependency.checkpoint_id == stored["id"] and dependency.checkpoint_digest == digest(stored)
    assert prepared.publication.guard.dependency_digests == {"country": digest(country.resolution)}


@pytest.mark.parametrize("change", (
    lambda state, key: state["outbox"].pop(key),
    lambda state, key: state["outbox"][key].update(delivered=True),
    lambda state, key: state["outbox"][key]["guard"].update(checkpoint_digest="f" * 64),
))
def test_missing_completed_or_corrupt_persisted_publication_outbox_denies(tmp_path, change):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    prepared = prepare(req, journal, principal, blobs)
    corrupt(journal, lambda state: change(state, prepared.basis.publication_outbox_key))
    before = journal.store._read(journal.scope).state
    with pytest.raises(StaleWork):
        asyncio.run(validate_native_publication(journal, prepared, principal=principal, blobs=blobs))
    assert journal.store._read(journal.scope).state == before


def test_delivered_publication_is_never_reset_by_preparation(tmp_path):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    prepared = prepare(req, journal, principal, blobs)
    corrupt(journal, lambda state: state["outbox"][prepared.basis.publication_outbox_key].update(delivered=True))
    before = journal.store._read(journal.scope).state
    with pytest.raises(StaleWork, match="already_delivered"):
        prepare(req, journal, principal, blobs)
    assert journal.store._read(journal.scope).state == before


def test_changed_native_whole_checkpoint_is_rejected_even_if_typed_payload_is_same(tmp_path):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    prepared = prepare(req, journal, principal, blobs)
    def change(state):
        state["jobs"][journal.scope.key]["fields"]["country"]["checkpoint"]["sequence"] += 1
    corrupt(journal, change)
    with pytest.raises(StaleWork):
        asyncio.run(validate_native_publication(journal, prepared, principal=principal, blobs=blobs))


def test_persisted_state_revision_must_stay_exact_even_when_other_field_changed(tmp_path):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    prepared = prepare(req, journal, principal, blobs)
    unrelated = FieldResolution(field_key=FieldKey.CITY, work_state=WorkState.WAITING_SOURCE,
                               value=FieldValue(), reason="Not relevant to country")
    city_request = req.model_copy(update={"field_keys": (FieldKey.CITY,)})
    asyncio.run(journal.commit(city_request, (unrelated,), receipt_ids=(), model_settings_digest=prepared.publication.checkpoints[0].model_settings_digest))
    with pytest.raises(StaleWork, match="prepared_basis_changed"):
        asyncio.run(validate_native_publication(journal, prepared, principal=principal, blobs=blobs))


@pytest.mark.parametrize("change", (
    lambda principal: principal.model_copy(update={"user_id": "forged-actor"}),
    lambda principal: principal.model_copy(update={"scope": Scope(organization_id="foreign", collection_id=principal.scope.collection_id)}),
    lambda principal: principal.model_copy(update={"role": "viewer"}),
))
def test_actor_and_scope_controls_fail_before_outbox_preparation(tmp_path, change):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    before = journal.store._read(journal.scope).state
    with pytest.raises(PermissionError, match="actor_scope_denied"):
        prepare(req, journal, change(principal), blobs)
    assert journal.store._read(journal.scope).state == before


def test_current_membership_revocation_and_exact_lease_are_enforced(tmp_path):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    bad_lease = DurableResearchJournal(journal.store, journal.scope, replace(journal.lease, fence=journal.lease.fence + 1))
    with pytest.raises(StaleWork, match="lease fence"):
        prepare(req, bad_lease, principal, blobs)
    journal.store.backend.revoke(journal.scope)
    with pytest.raises(PermissionError, match="membership"):
        prepare(req, journal, principal, blobs)


def test_stored_lease_server_expiry_is_checked_again_after_capture_read(tmp_path, monkeypatch):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    get = blobs.get
    def expired_after_read(reference):
        data = get(reference)
        monkeypatch.setattr(journal.store.backend, "_time", lambda db: journal.lease.expires_at)
        return data
    monkeypatch.setattr(blobs, "get", expired_after_read)
    with pytest.raises(StaleWork, match="lease fence"):
        prepare(req, journal, principal, blobs)


def test_current_database_viewer_role_cannot_prepare_existing_authorization(tmp_path):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    prepare(req, journal, principal, blobs)
    journal.store.backend.grant(journal.scope, role="viewer")
    # Principal's earlier role cannot bypass the authoritative lease-bearing CAS.
    with pytest.raises(PermissionError, match="membership"):
        prepare(req, journal, principal, blobs)


@pytest.mark.parametrize("name,value", (("input_digest", "e" * 64), ("profile_digest", "f" * 64)))
def test_full_input_and_profile_bindings_are_checked(tmp_path, name, value):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    changed = req.model_copy(update={"scope": req.scope.model_copy(update={name: value})})
    with pytest.raises(PermissionError, match="binding_mismatch"):
        prepare(changed, journal, principal, blobs)


def test_every_specialist_prompt_is_validated_even_for_another_published_field(tmp_path):
    req, journal, principal, blobs, _ = fixture(tmp_path, receipt=False)
    def change(state):
        job = state["jobs"][journal.scope.key]
        job["pins"]["prompts"][str(SpecialistRole.TAXONOMY)]["text"] += "tampered content"
        job["binding_digest"] = digest(job["pins"])
    corrupt(journal, change)
    before = journal.store._read(journal.scope).state
    with pytest.raises(StaleWork, match="runtime_pin_contract_changed"):
        prepare(req, journal, principal, blobs)
    assert journal.store._read(journal.scope).state == before


def test_capture_reader_required_and_corrupt_immutable_capture_denied(tmp_path):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    with pytest.raises(PublicationUnavailable, match="capture_reader_required"):
        prepare(req, journal, principal, None)
    prepared = prepare(req, journal, principal, blobs)
    capture_path = blobs._path(prepared.basis.receipts[0].capture.locator)
    original = capture_path.read_bytes()
    # Keep the declared byte size so this explicitly exercises the checksum
    # guard, rather than the separate pre-allocation size guard.
    capture_path.write_bytes(bytes([original[0]^1])+original[1:])
    with pytest.raises(ValueError, match="checksum"):
        asyncio.run(validate_native_publication(journal, prepared, principal=principal, blobs=blobs))


def test_native_adapter_absence_and_ordinary_save_remain_closed(tmp_path):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    prepared = prepare(req, journal, principal, blobs)
    class OrdinaryWriter:
        def save(self, *args):
            pytest.fail("An ordinary save must never receive research publication")
    for adapter in (None, OrdinaryWriter()):
        with pytest.raises(PublicationUnavailable, match="adapter_not_admitted"):
            asyncio.run(publish_native_publication(journal, prepared, principal=principal, blobs=blobs, adapter=adapter))


def geography_run(tmp_path, other_field_keys):
    """One geography run: a country capture and a second capture with the given
    recorded fields. The engine pins both receipts on the run's checkpoints."""
    _, requests, journal, settings = setup(tmp_path)
    req = requests[SpecialistRole.GEOGRAPHY]
    principal = Principal(user_id=journal.scope.actor_uid, scope=Scope(
        organization_id=req.scope.organization_id, collection_id=req.scope.collection_id), role="operator")
    blobs = ImmutableFileBlobs(tmp_path / "publication-blobs")

    def capture(name, field_keys):
        async def dispatch(attempt, idempotency):
            return CapturedResult(typed_payload={"query": name}, actual_micro_usd=3,
                                  usage={"synthetic_source_requests": 1})
        return asyncio.run(DurableEffectBroker(journal.store, blobs).execute(
            journal.scope, journal.lease, f"synthetic-{name}-evidence", {"query": name},
            5, dispatch, field_keys=field_keys)).effect_id
    effect_ids = (capture("country", (str(FieldKey.COUNTRY),)), capture("other", other_field_keys))
    resolutions = tuple(FieldResolution(field_key=key, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal=text, parsed=text, evidence_ids=[f"{key}-label"]),
        evidence_ids=(f"{key}-label",), reason="Independent synthetic expected label")
        for key, text in ((FieldKey.COUNTRY, "Peru"), (FieldKey.CITY, "Lima")))
    asyncio.run(journal.commit(req, resolutions, receipt_ids=effect_ids, model_settings_digest=settings))
    return req, journal, principal, blobs, effect_ids


def test_each_field_publishes_with_its_specialist_runs_sibling_field_receipts(tmp_path):
    req, journal, principal, blobs, effect_ids = geography_run(tmp_path, (str(FieldKey.CITY),))
    for field_key in (FieldKey.COUNTRY, FieldKey.CITY):
        prepared = asyncio.run(prepare_native_publication(journal, req.scope, field_key,
            principal=principal, expected_record_revision=0, blobs=blobs))
        assert prepared.publication.checkpoints[0].effect_receipt_ids == effect_ids
        assert tuple(item.effect_id for item in prepared.basis.receipts) == effect_ids
        asyncio.run(validate_native_publication(journal, prepared, principal=principal, blobs=blobs))


@pytest.mark.parametrize("other_field_keys", (
    (str(FieldKey.TAXON),), (), (str(FieldKey.CITY), str(FieldKey.TAXON)),
))
def test_a_receipt_recorded_for_another_specialists_field_or_none_is_refused(tmp_path, other_field_keys):
    req, journal, principal, blobs, _ = geography_run(tmp_path, other_field_keys)
    with pytest.raises(StaleWork, match="native_publication_receipt_binding_changed"):
        asyncio.run(prepare_native_publication(journal, req.scope, FieldKey.COUNTRY,
            principal=principal, expected_record_revision=0, blobs=blobs))


def test_wrong_canonical_record_revision_fails_existing_store_guard(tmp_path):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    with pytest.raises(StaleWork, match="publication revision"):
        asyncio.run(prepare_native_publication(journal, req.scope, FieldKey.COUNTRY,
            principal=principal, expected_record_revision=1, blobs=blobs))
