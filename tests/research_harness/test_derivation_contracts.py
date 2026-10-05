"""G38 request shapes cannot accept client-provided source values or target human inputs."""

import pytest
from pydantic import ValidationError

from specimen_digitization.research_harness.contracts import FieldKey
from specimen_digitization.research_harness.derivation_contracts import (
    DerivationAccepted, DerivationCapability, DerivationCommand, DerivationProposal,
    DerivationRequest, DerivationResultRead, DerivationScheduleReceipt, SettledDerivationInput, derivation_input_digest,
)


def input_proof(**changes):
    return SettledDerivationInput.model_validate({
        "field_key": "country", "value": "Philippines", "evidence_ids": ["evidence"], "revision": 5,
        "authority_id": "geolocate:0123456789abcdef", "field_digest": "a" * 64,
        "review_decision_id": "review", "provenance_blob_ref": "retained-proof",
        "provenance_sha256": "b" * 64, "original_review_revision": 5, **changes})


def command_data():
    inputs = (input_proof(),)
    return {"id": "c" * 64, "actor_uid": "reviewer", "reason": "Fill missing geography",
        "source_revision": 5, "queued_revision": 6, "canonical_run_id": "run",
        "source_snapshot_sha256": "d" * 64, "inputs": inputs,
        "input_digest": derivation_input_digest(inputs), "human_locked_fields": ("country",),
        "requested_fields": ("city",), "idempotency_key": "request", "request_digest": "e" * 64}


def proposal_data():
    return {"field_key": "city", "value": "A named municipality", "input_fields": ("country",),
        "input_revisions": (("country", 5),), "evidence_ids": ("source-proof",),
        "authority_id": "boundary:place", "dataset_ids": ("qualified-boundary",),
        "tool_call_id": "tool-call", "rule_version": "retrospective-georeferencing-v1",
        "checkpoint_id": "a" * 64, "checkpoint_revision": 1, "effect_id": "b" * 64}


def test_request_contains_only_review_context_and_targets():
    body = {"expected_record_revision": 5, "base_record_version_id": "run:5", "reason": "Fill missing fields",
            "requested_fields": ("city", "elevation_from_m")}
    request = DerivationRequest.model_validate(body)
    assert request.requested_fields == (FieldKey.CITY, FieldKey.ELEVATION_FROM_M)
    for injected in ({"validation": {"latitude": 5}}, {"inputs": ["caller value"]}, {"budget": 500}):
        with pytest.raises(ValidationError):
            DerivationRequest.model_validate(body | injected)


@pytest.mark.parametrize("change", [
    {"expected_record_revision": True}, {"expected_record_revision": 0}, {"reason": " "},
    {"reason": "x" * 1001}, {"requested_fields": ()}, {"requested_fields": ("city", "city")},
    {"requested_fields": ("taxon",)}, {"requested_fields": ("date_visited_from",)},
])
def test_invalid_request_context_and_targets_are_rejected(change):
    with pytest.raises(ValidationError):
        DerivationRequest.model_validate({"expected_record_revision": 5, "base_record_version_id": "run:5",
            "reason": "Fill missing fields", "requested_fields": ("city",), **change})


def test_ordinary_human_input_needs_provenance_but_not_a_candidate_selection_token():
    ordinary = input_proof()
    selected = input_proof(selection_id="f" * 64)
    assert ordinary.selection_id is None and selected.selection_id == "f" * 64
    assert derivation_input_digest((ordinary,)) != derivation_input_digest((selected,))
    command = DerivationCommand.model_validate(command_data())
    assert DerivationCommand.model_validate_json(command.model_dump_json()) == command


@pytest.mark.parametrize("change", [
    {"review_decision_id": ""}, {"provenance_blob_ref": ""}, {"evidence_ids": ()},
    {"field_key": "elevation_from_m"}, {"authority_id": " "}, {"revision": 0},
    {"selection_id": "unknown"}, {"provenance_sha256": "wrong"},
])
def test_input_without_genuine_proof_fields_is_invalid(change):
    with pytest.raises(ValidationError):
        input_proof(**change)


@pytest.mark.parametrize("change", [
    {"queued_revision": 5}, {"queued_revision": 7}, {"input_digest": "f" * 64},
    {"requested_fields": ("country",)}, {"human_locked_fields": ("country", "city")},
    {"human_locked_fields": ("country", "country")}, {"status": "accepted"},
    {"blocked_reason": "Private lookup failed!"}, {"reason": " "},
    {"human_locked_fields": ()},
])
def test_command_is_one_save_with_exact_input_digest_and_unlocked_targets(change):
    with pytest.raises(ValidationError):
        DerivationCommand.model_validate(command_data() | change)


def test_duplicate_inputs_and_future_review_proof_are_rejected_even_with_matching_digest():
    for inputs in ((input_proof(), input_proof()), (input_proof(original_review_revision=6),),
                   (input_proof(revision=4),), (input_proof(revision=6),)):
        with pytest.raises(ValidationError):
            DerivationCommand.model_validate(command_data() | {"inputs": inputs, "input_digest": derivation_input_digest(inputs)})


def test_scheduling_requires_an_exact_versioned_durable_receipt():
    receipt = DerivationScheduleReceipt(request_id="a" * 64, queued_revision=6, canonical_run_id="run")
    assert receipt.status == "scheduled"
    assert DerivationScheduleReceipt.model_validate_json(receipt.model_dump_json()) == receipt
    for change in ({"request_id": "invented"}, {"queued_revision": 0}, {"queued_revision": True},
                   {"status": "queued"}, {"budget": 1}):
        with pytest.raises(ValidationError):
            DerivationScheduleReceipt.model_validate(receipt.model_dump(mode="json") | change)


def test_proposals_preserve_durable_metadata_and_remain_derived():
    proposal = DerivationProposal.model_validate(proposal_data())
    assert proposal.value_layer == "derived" and proposal.source_id == "georeference_spatial"
    assert proposal.selection_id is None
    read = DerivationResultRead(request_id="c" * 64, status="completed", source_revision=5,
        queued_revision=6, canonical_revision=6, stale=False, proposals=(proposal,))
    assert DerivationResultRead.model_validate_json(read.model_dump_json()) == read


@pytest.mark.parametrize("change", [
    {"value_layer": "settled"}, {"input_revisions": (("province_state", 5),)},
    {"field_key": "country"}, {"field_key": "taxon"}, {"checkpoint_revision": 0},
    {"effect_id": "invented"}, {"source_id": "client-source"},
])
def test_a_proposal_cannot_change_layer_source_or_dependency_identity(change):
    with pytest.raises(ValidationError):
        DerivationProposal.model_validate(proposal_data() | change)


def test_accepted_and_capability_responses_are_versioned_and_bounded():
    accepted = DerivationAccepted(request_id="c" * 64, source_revision=5, queued_revision=6, canonical_run_id="run")
    capability = DerivationCapability(available=False, blocked_reason="validation_unavailable",
        canonical_revision=5, eligible_fields=())
    assert accepted.status == "queued" and accepted.contract_version == "research-derivation-accepted/v1"
    assert capability.contract_version == "research-derivation-capability/v1"
    with pytest.raises(ValidationError):
        DerivationCapability(available=True, canonical_revision=5, eligible_fields=("city", "city"))
