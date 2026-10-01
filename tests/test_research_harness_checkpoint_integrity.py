"""Independent local reader parity probes, authored outside the repository.

All content is synthetic. Native checkpoint writes use the real scoped store;
the injected adapter mistakes are accepted only if the writer fails to reject
them. This does not claim an external actor can edit persisted SQL state.
"""
import asyncio

import pytest

from specimen_digitization.research_harness.contracts import (
    DependencyPin, FieldCheckpoint, FieldKey, SpecialistRole, digest,
)
from specimen_digitization.research_harness.persistence import StaleWork
from specimen_digitization.research_harness.thread_view import ResearchThreadReader
from test_research_harness_boundaries import admitted, resolved, waiting


def reject_write_or_read(journal, scope, field, payload, **kwargs):
    try:
        journal.store.checkpoint(journal.scope, journal.lease, str(field), payload,
            **kwargs)
    except (ValueError, StaleWork):
        return
    with pytest.raises((ValueError, StaleWork)):
        asyncio.run(journal.load(scope))
    with pytest.raises((ValueError, StaleWork)):
        asyncio.run(ResearchThreadReader(journal).read(scope))


@pytest.mark.parametrize("mismatch", ["revision", "receipt_ids", "host_command"])
def test_native_and_typed_checkpoint_pins_must_agree_before_read(tmp_path, mismatch):
    _, scope, requests, journal, settings = admitted(tmp_path)
    first, = asyncio.run(journal.commit(requests[SpecialistRole.TAXONOMY],
        (waiting(FieldKey.TAXON),), receipt_ids=(), model_settings_digest=settings))
    payload = first.model_dump(mode="json")
    payload["revision"] = 2
    if mismatch == "revision":
        payload["revision"] = 1
    elif mismatch == "receipt_ids":
        payload["effect_receipt_ids"] = ["f"*64]
    else:
        payload["retry_command_id"] = "f"*64
    reject_write_or_read(journal, scope, FieldKey.TAXON, payload,
        expected_revision=1)


def test_native_field_key_cannot_relabel_a_typed_sibling_checkpoint(tmp_path):
    _, scope, requests, journal, settings = admitted(tmp_path)
    request = requests[SpecialistRole.GEOGRAPHY]
    country, = asyncio.run(journal.commit(request,
        (waiting(FieldKey.COUNTRY),), receipt_ids=(), model_settings_digest=settings))
    # Country and City legitimately share their prompt, but not field identity.
    reject_write_or_read(journal, scope, FieldKey.CITY,
        country.model_dump(mode="json"), expected_revision=0)


def test_native_dependency_maps_cannot_omit_typed_consumed_dependencies(tmp_path):
    _, scope, requests, journal, settings = admitted(tmp_path)
    country, = asyncio.run(journal.commit(requests[SpecialistRole.GEOGRAPHY],
        (resolved(FieldKey.COUNTRY, "Synthetic-country-one"),), receipt_ids=(),
        model_settings_digest=settings))
    dependency = DependencyPin(field_key=FieldKey.COUNTRY, revision=country.revision,
        digest=digest(country.resolution))
    taxon = FieldCheckpoint(scope=scope, field_key=FieldKey.TAXON, revision=1,
        resolution=resolved(FieldKey.TAXON, "Synthetic-dependent-taxon").model_copy(
            update={"dependencies":(dependency,)}),
        prompt_digest=requests[SpecialistRole.TAXONOMY].prompt.digest,
        model_settings_digest=settings, source_registry_digest="2"*64)
    reject_write_or_read(journal, scope, FieldKey.TAXON,
        taxon.model_dump(mode="json"), expected_revision=0,
        dependencies={}, dependency_digests={})


@pytest.mark.parametrize("mismatch", ["scope", "binding_digest", "revision", "id",
    "field_key", "receipt_ids", "dependencies", "dependency_digests", "retry_command_id"])
def test_current_reader_rejects_corrupted_native_wrapper_even_with_valid_typed_payload(tmp_path, mismatch):
    _, scope, requests, journal, settings = admitted(tmp_path)
    country, = asyncio.run(journal.commit(requests[SpecialistRole.GEOGRAPHY],
        (waiting(FieldKey.COUNTRY),), receipt_ids=(), model_settings_digest=settings))
    asyncio.run(journal.commit(requests[SpecialistRole.TAXONOMY],
        (waiting(FieldKey.TAXON),), receipt_ids=(), model_settings_digest=settings))
    def corrupt(state, _now):
        # Fault only the native current wrapper. Typed payload/profile/prompt/
        # source/settings and lifecycle field row remain otherwise valid.
        checkpoint = state["jobs"][journal.scope.key]["fields"]["taxon"]["checkpoint"]
        if mismatch == "scope":
            checkpoint["scope"]["specimen_id"] = "other-synthetic-specimen"
        elif mismatch == "revision":
            checkpoint["revision"] = 2
        elif mismatch == "field_key":
            checkpoint["field_key"] = "city"
        elif mismatch == "receipt_ids":
            checkpoint["receipt_ids"] = ["f"*64]
        elif mismatch == "dependencies":
            # A valid current native dependency closure omitted from the typed
            # scientific payload must also be detected as a mismatch.
            checkpoint["dependencies"] = {"country":country.revision}
            checkpoint["dependency_digests"] = {"country":digest(country.resolution)}
        elif mismatch == "dependency_digests":
            checkpoint["dependency_digests"] = {"country":"f"*64}
        else:
            checkpoint[mismatch] = "f"*64
    journal.store._mutate(journal.scope, corrupt)
    with pytest.raises((ValueError, StaleWork)):
        asyncio.run(journal.load(scope))


def test_current_and_verified_reused_positive_checkpoint_controls(tmp_path):
    from test_research_harness_reuse_integrity import linked_fields, reuse_after_unrelated_correction
    scope, _, journal, _, _ = linked_fields(tmp_path)
    current = asyncio.run(journal.load(scope))
    assert {item.field_key for item in current} == {FieldKey.COUNTRY, FieldKey.TAXON}
    reused_scope, reopened = reuse_after_unrelated_correction(scope, journal)
    reused = asyncio.run(reopened.load(reused_scope))
    assert {item.field_key for item in reused} == {FieldKey.COUNTRY, FieldKey.TAXON}
    assert all(item.scope == reused_scope and item.reused_from_checkpoint_digest for item in reused)
