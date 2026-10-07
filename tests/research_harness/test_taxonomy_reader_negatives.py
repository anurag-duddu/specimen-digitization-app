"""Offline G20/G32 tests; deciding names and identities are synthetic."""
import hashlib

import pytest

from specimen_digitization.application.domain import LookupStatus
from specimen_digitization.research_harness.contracts import (
    FieldKey, SourceCoverageState, SourceQuery, digest,
)
from specimen_digitization.research_harness.evidence import EvidenceError, validate_resolution
from specimen_digitization.research_harness.sources import result_envelope

from test_taxon_input_reconciliation import request_for, resolution_for, result_for


def negative_for(request, literal, *, status=LookupStatus.NO_MATCH, north_american=False):
    result = result_for(request, literal)
    query = SourceQuery(source_id="gbif", field_key=FieldKey.TAXON, query_text=literal, north_american=north_american)
    coverage = result.coverage.model_copy(update={
        "query_digest": digest(query), "qualification_digest": digest("fixture-policy"),
        "receipt_ids": tuple(item.id for item in result.evidence), "candidate_count": 0,
        "state": SourceCoverageState.SEARCHED, "reason": str(status),
    })
    result = result.model_copy(update={"status": status, "coverage": coverage, "candidate_json": ()})
    payload = result_envelope(result)
    return result.model_copy(update={"receipt": result.receipt.model_copy(update={
        "outcome": status, "result_json": payload,
        "result_digest": hashlib.sha256(payload.encode()).hexdigest(),
    })})


def test_confirmed_reader_and_captured_no_match_of_same_label_can_settle():
    request = request_for((("raw", "Epipocus", "raw_reading"),
                           ("decided", "Epipsocus", "decided_transcript")))
    confirmed = result_for(request, "Epipocus")
    negative = negative_for(request, "Epipsocus")
    resolution = resolution_for(request, (confirmed,))
    before = request.model_dump(mode="json")
    assert validate_resolution(request, resolution, (confirmed, negative)) == resolution
    assert request.model_dump(mode="json") == before  # Neither transcript is rewritten.


@pytest.mark.parametrize("status", [LookupStatus.TIMEOUT, LookupStatus.PROVIDER,
    LookupStatus.MALFORMED, LookupStatus.AMBIGUOUS, LookupStatus.POLICY,
    LookupStatus.RATE_LIMITED, LookupStatus.AUTHENTICATION, LookupStatus.AUTHORIZATION])
def test_failed_refused_or_tied_alternative_does_not_count_as_a_negative(status):
    request = request_for((("raw", "Epipocus", "raw_reading"),
                           ("other", "Epipsocus", "raw_reading")))
    confirmed = result_for(request, "Epipocus")
    with pytest.raises(EvidenceError, match="each independent taxon assertion"):
        validate_resolution(request, resolution_for(request, (confirmed,)),
                            (confirmed, negative_for(request, "Epipsocus", status=status)))


@pytest.mark.parametrize("mutation", ["unreceipted", "scope", "field", "source", "effect",
    "query", "qualification", "semantic", "digest", "evidence", "outcome", "coverage"])
def test_incomplete_or_tampered_negative_cannot_settle(mutation):
    request = request_for((("raw", "Epipocus", "raw_reading"),
                           ("other", "Epipsocus", "raw_reading")))
    confirmed = result_for(request, "Epipocus")
    negative = negative_for(request, "Epipsocus")
    if mutation == "unreceipted":
        negative = negative.model_copy(update={"receipt": None})
    elif mutation == "scope":
        negative = negative.model_copy(update={"receipt": negative.receipt.model_copy(update={
            "scope": request.scope.model_copy(update={"specimen_id": "foreign"})})})
    elif mutation in {"field", "source", "effect", "semantic", "digest", "evidence", "outcome"}:
        updates = {"field": {"field_keys": (FieldKey.COUNTRY,)}, "source": {"source_id": "catalogue_of_life"},
            "effect": {"effect_status": "held_unknown"}, "semantic": {"result_json": "{}"},
            "digest": {"result_digest": digest("changed")}, "evidence": {"evidence_ids": ()},
            "outcome": {"outcome": LookupStatus.SUCCESS}}[mutation]
        negative = negative.model_copy(update={"receipt": negative.receipt.model_copy(update=updates)})
    else:
        updates = {"query": {"query_digest": digest("unrelated-name")},
            "qualification": {"qualification_digest": None},
            "coverage": {"state": SourceCoverageState.FAILED}}[mutation]
        negative = negative.model_copy(update={"coverage": negative.coverage.model_copy(update=updates)})
        payload = result_envelope(negative)
        negative = negative.model_copy(update={"receipt": negative.receipt.model_copy(update={
            "result_json": payload, "result_digest": hashlib.sha256(payload.encode()).hexdigest()})})
    with pytest.raises(EvidenceError, match="each independent taxon assertion"):
        validate_resolution(request, resolution_for(request, (confirmed,)), (confirmed, negative))


def test_no_match_on_a_separate_label_cannot_waive_g32():
    request = request_for((("raw", "Epipocus", "raw_reading"),
                           ("other", "Epipsocus", "raw_reading")))
    request = request.model_copy(update={"fragments": tuple(item.model_copy(update={
        "region_id": "other-label", "label_id": "other-label"}) if item.observation_id == "other" else item
        for item in request.fragments), "organiser_candidates": ()})
    # Explicit located field span qualifies the independent second label.
    from specimen_digitization.research_harness.contracts import OrganiserCandidate
    request = request.model_copy(update={"organiser_candidates": (OrganiserCandidate(
        id="second-label", field_key=FieldKey.TAXON, literal="Epipsocus", source="extractor",
        status="located", reason="fixture", region_id="other-label", observation_id="other", start=0, end=9),)})
    confirmed = result_for(request, "Epipocus")
    with pytest.raises(EvidenceError, match="each independent taxon assertion"):
        validate_resolution(request, resolution_for(request, (confirmed,)),
                            (confirmed, negative_for(request, "Epipsocus")))


def test_another_accepted_genus_cannot_be_erased_by_a_negative():
    request = request_for((("raw", "Epipocus", "raw_reading"),
                           ("other", "Epipsocus", "raw_reading")))
    confirmed = result_for(request, "Epipocus")
    conflicting = result_for(request, "Epipsocus", authority="gbif:another-genus", value="Epipsocus")
    with pytest.raises(EvidenceError, match="each independent taxon assertion"):
        validate_resolution(request, resolution_for(request, (confirmed,)),
                            (confirmed, conflicting, negative_for(request, "Epipsocus")))


def test_unused_regional_flag_preserves_exact_negative_query_binding():
    request = request_for((("raw", "Epipocus", "raw_reading"),
                           ("other", "Epipsocus", "raw_reading")))
    positive = result_for(request, "Epipocus")
    negative = negative_for(request, "Epipsocus", north_american=True)
    assert validate_resolution(request, resolution_for(request, (positive,)), (positive, negative))


def test_a_second_accepted_identity_of_the_same_assertion_cannot_be_ignored():
    request = request_for()
    positive = result_for(request, "Epipocus")
    conflict = result_for(request, "Epipocus", authority="gbif:other-accepted", value="Othergenus")
    with pytest.raises(EvidenceError, match="each independent taxon assertion"):
        validate_resolution(request, resolution_for(request, (positive,)), (positive, conflict))


@pytest.mark.parametrize("same_line", [False, True])
def test_two_names_by_the_same_reader_are_independent_assertions(same_line):
    from specimen_digitization.research_harness.contracts import OrganiserCandidate
    text = "Epipocus Epipsocus" if same_line else "Epipocus\nEpipsocus"
    request = request_for((("raw", text, "raw_reading"),))
    request = request.model_copy(update={"organiser_candidates": tuple(OrganiserCandidate(
        id="assertion:" + name, field_key=FieldKey.TAXON, literal=name, source="extractor",
        status="located", reason="independently_printed_name", region_id="label", observation_id="raw",
        start=text.index(name), end=text.index(name) + len(name)) for name in ("Epipocus", "Epipsocus"))})
    # These are two printed assertions, not competing readings of one name.
    confirmed = result_for(request, "Epipocus")
    if same_line:
        from specimen_digitization.application.domain import FieldValue, ValueState
        from specimen_digitization.research_harness.contracts import FieldResolution, WorkState
        ids = tuple(item.id for item in confirmed.evidence)
        resolution = FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.RESOLVED,
            value=FieldValue(state=ValueState.SUPPORTED, parsed="Epipocus", authority_id="gbif:synthetic-same-authority",
                evidence_ids=list(ids), evidence_relations=dict.fromkeys(ids, "decides")),
            evidence_ids=ids, reason="synthetic assertion")
    else:
        resolution = resolution_for(request, (confirmed,))
    with pytest.raises(EvidenceError, match="each independent taxon assertion"):
        validate_resolution(request, resolution, (confirmed, negative_for(request, "Epipsocus")))


def test_a_query_failure_is_cleared_only_by_the_same_query_completion():
    from specimen_digitization.application.domain import FieldValue, ValueState
    from specimen_digitization.research_harness.agents import masked_outages
    from specimen_digitization.research_harness.contracts import FieldResolution, WorkState
    request = request_for()
    answer = FieldResolution(field_key=FieldKey.TAXON, work_state=WorkState.WAITING_POLICY,
        value=FieldValue(state=ValueState.UNRESOLVED), reason="missing_policy:fixture")
    failed = negative_for(request, "Epipocus", status=LookupStatus.TIMEOUT)
    other = negative_for(request, "Epipsocus")
    recovered = negative_for(request, "Epipocus")
    assert masked_outages((answer,), (failed, other)) == (FieldKey.TAXON,)
    assert masked_outages((answer,), (failed, other, recovered)) == ()
