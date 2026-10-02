"""Prepared during CPU hold; do not execute until root explicitly releases it.

Independent exact-77ca006 source-corruption probes. These call the actual SQLite
store, journal and translator. No canonical adapter, compiler or provider runs.
"""

import asyncio
from copy import deepcopy

import pytest

from specimen_digitization.application.domain import FieldValue, ValueState
from specimen_digitization.research_harness.contracts import (
    FieldKey, FieldResolution, SpecialistRole, WorkState, digest,
)
from specimen_digitization.research_harness.persistence import StaleWork
from specimen_digitization.research_harness.publication import (
    _native_checkpoint, prepare_native_publication,
)
from test_research_harness_publication import corrupt, fixture


def _same_native_rows(journal, field_key, mutate):
    def change(state):
        job = state["jobs"][journal.scope.key]
        original = deepcopy(job["fields"][field_key]["checkpoint"])
        replacement = deepcopy(original)
        mutate(replacement)
        job["fields"][field_key]["checkpoint"] = replacement
        job["checkpoints"] = [deepcopy(replacement) if cp == original else cp for cp in job["checkpoints"]]
    corrupt(journal, change)


def _prepare(req, journal, principal, blobs, field_key=FieldKey.COUNTRY):
    return asyncio.run(prepare_native_publication(journal, req.scope, field_key,
        principal=principal, expected_record_revision=0, blobs=blobs))


@pytest.mark.parametrize("key,value", [("field_key", "taxon"), ("revision", 99)])
def test_whole_native_wrapper_field_and_revision_must_match_typed_checkpoint(tmp_path, key, value):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    _same_native_rows(journal, "country", lambda cp:cp.update({key:value}))
    with pytest.raises(StaleWork):
        _prepare(req, journal, principal, blobs)


def test_untagged_typed_checkpoint_cannot_have_native_retry_command_tag(tmp_path):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    _same_native_rows(journal, "country", lambda cp:cp.update(retry_command_id="e"*64))
    with pytest.raises(StaleWork):
        _prepare(req, journal, principal, blobs)


def test_actual_claimed_retry_checkpoint_native_tag_must_match_typed_tag(tmp_path):
    req, journal, principal, blobs, previous = fixture(tmp_path, receipt=False)
    # Install an actual failed field revision, admit and claim through the host
    # reducers, then commit the command-bound typed/native result through journal.
    failed_request = req.model_copy(update={"field_keys":(FieldKey.COUNTRY,),
        "field_revisions":{FieldKey.COUNTRY:previous.revision}})
    failure = FieldResolution(field_key=FieldKey.COUNTRY, work_state=WorkState.OPERATIONAL_FAILED,
        value=FieldValue(), reason="offline_failure_fixture")
    failed, = asyncio.run(journal.commit(failed_request, (failure,), receipt_ids=(),
        model_settings_digest=previous.model_settings_digest))
    queued = journal.store.admit_retry(journal.scope, "country", expected_generation=1,
        expected_field_revision=failed.revision, idempotency_key="f"*64, execution_class="offline")
    claimed = journal.store.claim_retry_command(journal.scope, journal.lease, queued["id"])
    result_request = req.model_copy(update={"field_keys":(FieldKey.COUNTRY,),
        "field_revisions":{FieldKey.COUNTRY:failed.revision}, "retry_command_id":claimed["id"]})
    result = FieldResolution(field_key=FieldKey.COUNTRY, work_state=WorkState.RESOLVED,
        value=FieldValue(state=ValueState.SUPPORTED, literal="Synthetic country"),
        evidence_ids=("synthetic-fixture",), reason="offline_accepted_result_fixture")
    saved, = asyncio.run(journal.commit(result_request, (result,), receipt_ids=(),
        model_settings_digest=previous.model_settings_digest))
    native = journal.store.job(journal.scope)["fields"]["country"]["checkpoint"]
    journal.store.complete_retry_command(journal.scope, journal.lease, claimed["id"], checkpoint_id=native["id"])
    assert saved.retry_command_id == native["retry_command_id"] == claimed["id"]
    _same_native_rows(journal, "country", lambda cp:cp.update(retry_command_id="e"*64))
    with pytest.raises(StaleWork):
        _prepare(req, journal, principal, blobs)


def test_native_scope_helper_must_bind_complete_durability_identity(tmp_path):
    req, journal, _, _, typed = fixture(tmp_path, receipt=False)
    def partial(cp):
        cp["scope"].pop("organization_id")
        cp["id"] = digest({"scope":cp["scope"], "field":"country",
            "revision":typed.revision, "payload":cp["payload"]})
    _same_native_rows(journal, "country", partial)
    job = journal.store.job(journal.scope)
    with pytest.raises(StaleWork):
        _native_checkpoint(job, typed, req.scope)


def test_whole_translation_rejects_partial_scope_even_before_helper_hardening(tmp_path):
    req, journal, principal, blobs, typed = fixture(tmp_path, receipt=False)
    def partial(cp):
        cp["scope"].pop("organization_id")
        cp["id"] = digest({"scope":cp["scope"], "field":"country",
            "revision":typed.revision, "payload":cp["payload"]})
    _same_native_rows(journal, "country", partial)
    with pytest.raises(StaleWork):
        _prepare(req, journal, principal, blobs)


def test_delivered_marker_race_cannot_reopen_prepared_outbox(tmp_path, monkeypatch):
    req, journal, principal, blobs, _ = fixture(tmp_path)
    prepared = _prepare(req, journal, principal, blobs)
    original = journal.store.prepare_publication
    def concurrent_delivery(*args, **kwargs):
        # This probes the documented delivered-marker invariant. A future real
        # atomic native completion would also advance record revision, which
        # independently prevents this race. No native writer is installed here.
        corrupt(journal, lambda state:state["outbox"][prepared.basis.publication_outbox_key].update(delivered=True))
        return original(*args, **kwargs)
    monkeypatch.setattr(journal.store, "prepare_publication", concurrent_delivery)
    with pytest.raises(StaleWork):
        _prepare(req, journal, principal, blobs)
    assert journal.store._read(journal.scope).state["outbox"][prepared.basis.publication_outbox_key]["delivered"] is True
