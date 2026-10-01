"""Independent retained-dependency proof checks through real local journal APIs."""
import asyncio
from dataclasses import replace

import pytest

from specimen_digitization.research_harness.contracts import DependencyPin, FieldKey, SpecialistRole, WorkState, digest
from specimen_digitization.research_harness.journal import DurableResearchJournal
from specimen_digitization.research_harness.persistence import PinnedRuntime, StaleWork
from test_research_harness_boundaries import admitted, resolved


def linked_fields(tmp_path):
    _, scope, requests, journal, settings = admitted(tmp_path)
    country_request = requests[SpecialistRole.GEOGRAPHY].model_copy(update={"field_keys":(FieldKey.COUNTRY,)})
    country, = asyncio.run(journal.commit(country_request,
        (resolved(FieldKey.COUNTRY, "Country-one"),), receipt_ids=(), model_settings_digest=settings))
    dependency = DependencyPin(field_key=FieldKey.COUNTRY,
        revision=country.revision, digest=digest(country.resolution))
    taxonomy = requests[SpecialistRole.TAXONOMY].model_copy(update={"dependencies":(dependency,)})
    asyncio.run(journal.commit(taxonomy, (resolved(FieldKey.TAXON, "Dependent-taxon"),),
        receipt_ids=(), model_settings_digest=settings))
    return scope, requests, journal, settings, country


def reuse_after_unrelated_correction(scope, journal):
    journal.store.backend.grant(journal.scope, role="reviewer")
    current = PinnedRuntime(**journal.store.job(journal.scope)["pins"])
    new_pins = replace(current, input_digest="e"*64)
    corrected = journal.store.correct_fields(journal.scope, [str(FieldKey.FMNH_INS_NUMBER)],
        expected_generation=scope.generation, new_pins=new_pins)
    current_scope = scope.model_copy(update={"generation":corrected.generation,
        "input_digest":new_pins.input_digest})
    reopened = DurableResearchJournal(journal.store, corrected,
        journal.store.claim(corrected, "reuse-review-worker", ttl_seconds=120))
    return current_scope, reopened


def test_retained_dependency_digest_receipt_must_match_stored_checkpoint(tmp_path):
    scope, _, journal, _, _ = linked_fields(tmp_path)
    current_scope, reopened = reuse_after_unrelated_correction(scope, journal)
    receipt = reopened.store.job(reopened.scope)["fields"]["taxon"]["reuse"]
    assert "country" in receipt["retained_dependency_digests"]
    # Fault injection is deliberately only the new proof metadata. Source
    # checkpoint, history, revision and both binding digests remain unchanged.
    def corrupt_receipt(state, _now):
        state["jobs"][reopened.scope.key]["fields"]["taxon"]["reuse"]["retained_dependency_digests"]["country"] = "f"*64
    reopened.store._mutate(reopened.scope, corrupt_receipt)
    with pytest.raises(StaleWork, match="reuse|dependency|binding"):
        asyncio.run(reopened.load(current_scope))


def test_reused_consumer_cannot_stay_resolved_after_dependency_checkpoint_changed(tmp_path):
    scope, requests, journal, settings, country = linked_fields(tmp_path)
    request = requests[SpecialistRole.GEOGRAPHY].model_copy(update={
        "field_keys":(FieldKey.COUNTRY,), "field_revisions":{FieldKey.COUNTRY:country.revision}})
    # A fresh, scoped accepted checkpoint update, not database/payload tampering.
    current_country, = asyncio.run(journal.commit(request,
        (resolved(FieldKey.COUNTRY, "Country-two"),), receipt_ids=(), model_settings_digest=settings))
    assert current_country.revision == 2
    try:
        current_scope, reopened = reuse_after_unrelated_correction(scope, journal)
        checkpoints = {cp.field_key:cp for cp in asyncio.run(reopened.load(current_scope))}
    except StaleWork:
        return  # Explicit refusal of the stale closure is an acceptable repair.
    except ValueError as error:
        assert "dependency closure" in str(error)
        return
    taxon = checkpoints.get(FieldKey.TAXON)
    if taxon is None or taxon.resolution.work_state != WorkState.RESOLVED:
        return  # Explicit invalidation/blocked lifecycle is also acceptable.
    for pin in taxon.resolution.dependencies:
        source = checkpoints[pin.field_key]
        assert pin.revision == source.revision and pin.digest == digest(source.resolution)


def test_current_generation_read_rejects_stale_consumed_dependency(tmp_path):
    scope, requests, journal, settings, country = linked_fields(tmp_path)
    request = requests[SpecialistRole.GEOGRAPHY].model_copy(update={
        "field_keys":(FieldKey.COUNTRY,), "field_revisions":{FieldKey.COUNTRY:country.revision}})
    asyncio.run(journal.commit(request, (resolved(FieldKey.COUNTRY, "Country-two"),),
        receipt_ids=(), model_settings_digest=settings))
    with pytest.raises(StaleWork, match="dependency|Consumed|binding"):
        asyncio.run(journal.load(scope))
