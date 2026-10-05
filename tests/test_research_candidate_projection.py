"""A proved human research choice projects its value without inventing a reader selection."""

from dataclasses import replace

import pytest

from specimen_digitization.application.domain import AuditEvent, Disposition, Evidence, FieldValue, ValueState
from specimen_digitization.application.projection import derived_id, writes
from specimen_digitization.application.storage import ReviewProofReader, ReviewSnapshot, digest
from test_projection import locate, size
from test_projection_decisions import base, rows


def selected_specimen(origin, *, field_key="country", selected_value="Philippines",
                      authority="geolocate:a863d52e6ff08fe2", source="geolocate", precision=None):
    specimen = base()
    specimen.version = 3
    field = FieldValue(state=ValueState.UNRESOLVED)
    if origin == "single":
        field.literal = "P.I."
    elif origin == "readers":
        field.verbatim_by_observation = {item.id: text for item, text in
                                         zip(specimen.run.observations[:2], ("P.I.", "P. I."), strict=True)}
        field.input_source_by_observation = {key: "raw_reading" for key in field.verbatim_by_observation}
    specimen.run.fields = {field_key: field}
    specimen.run.disposition = Disposition.REVIEW
    prior = specimen.model_copy(deep=True)
    selection = "a" * 64
    evidence = Evidence(kind="authority_selection", source=source, locator="research-candidate:" + selection,
                        excerpt=selected_value, raw_ref="b" * 64 + ":1", digest="b" * 64)
    specimen.run.evidence = [evidence]
    field.state = ValueState.SUPPORTED
    field.parsed = field.normalized = selected_value
    field.authority_id = authority
    field.precision = precision
    field.layer = "settled"
    field.evidence_ids = [evidence.id]
    field.evidence_relations = {evidence.id: "decides"}
    specimen.run.dependencies["human_review_field_locks"] = {
        field_key: {"selection_id": selection, "evidence_id": evidence.id}}
    event = AuditEvent(actor="reviewer-uid", action="review_research_candidate", reason="Examined retained source candidates",
        before={}, after={"field_key": field_key, "selection_id": selection, "value": selected_value,
            "authority_id": field.authority_id, "source_id": source, "effect_id": "effect",
            "precision": precision, "century_rule": None,
            "checkpoint_id": "checkpoint", "evidence_ids": [evidence.id]},
        base_revision=3, resulting_revision=4)
    specimen.audit.append(event)
    specimen.version = 4
    snapshots = {}
    for value in (prior, specimen):
        payload = value.model_dump(mode="json")
        snapshots[value.version] = ReviewSnapshot(payload, digest(payload), value.model_copy(deep=True))

    def read_save_audits(base_revision, resulting_revision, original, before, after):
        assert (base_revision, resulting_revision) == (3, 4)
        assert original["id"] == event.id
        return {"saveAudits": [{"id": derived_id("human-choice-save", specimen.id, 4),
            "organizationId": specimen.scope.organization_id, "collectionId": specimen.scope.collection_id,
            "specimenId": specimen.id, "actorUid": event.actor, "revision": 4, "action": "checkpoint_or_review"}]}

    proofs = ReviewProofReader(specimen, snapshots.__getitem__, read_save_audits).prove()
    return specimen, proofs


@pytest.mark.parametrize("origin", ["missing", "single", "readers"])
def test_human_choice_has_a_distinct_canonical_candidate_and_preserves_every_verbatim(origin):
    specimen, proofs = selected_specimen(origin)
    before = specimen.model_dump(mode="json")
    result = writes(specimen, locate, size, "reviewer-uid", reviewer=True, review_proofs=proofs)
    candidates = rows(result, "AppendFieldCandidateV2")
    human = [item for item in candidates if item["literalValue"] is None]
    assert len(human) == 1
    [human] = human
    assert human["normalizedValue"] == human["parsedValue"] == "Philippines"
    assert human["authorityId"] == "geolocate:a863d52e6ff08fe2"
    assert human["inputSource"] is human["sourceObservationId"] is human["sourceTranscriptionId"] is None
    literals = [item for item in candidates if item["literalValue"] is not None]
    assert [item["literalValue"] for item in literals] == {
        "missing": [], "single": ["P.I."], "readers": ["P.I.", "P. I."]}[origin]
    assert all(item["normalizedValue"] is item["parsedValue"] is item["authorityId"] is None for item in literals)
    assert rows(result, "AppendResolvedFieldV2")[0]["candidateId"] == human["id"]
    links = rows(result, "AppendCandidateEvidenceV2")
    assert [(item["candidateId"], item["evidenceId"], item["relation"]) for item in links] == [
        (human["id"], specimen.run.evidence[0].id, "decides")]
    assert len(rows(result, "AppendReviewDecisionV2")) == 1
    assert specimen.model_dump(mode="json") == before


def test_human_selected_published_date_keeps_its_proved_precision_without_inventing_a_day():
    specimen, proofs = selected_specimen("missing", field_key="date_visited_from", selected_value="1948",
        authority="occurrence:publisher-date", source="museum_published", precision="year")
    result = writes(specimen, locate, size, "reviewer-uid", reviewer=True, review_proofs=proofs)
    [candidate] = rows(result, "AppendFieldCandidateV2")
    assert candidate["literalValue"] is None
    assert candidate["normalizedValue"] == "1948"
    assert candidate["parsedValue"] == {"value": "1948", "precision": "year", "century_rule": None}
    specimen.run.fields["date_visited_from"].precision = "day"
    with pytest.raises(ValueError, match="human_research_candidate_provenance_invalid"):
        writes(specimen, locate, size, "reviewer-uid", reviewer=True, review_proofs=proofs)


@pytest.mark.parametrize("change", [
    "missing_proof", "action", "field", "selection", "value", "authority", "evidence", "specimen",
    "marker", "stored_value", "stored_authority", "source", "locator", "raw_capture", "relation",
])
def test_a_marker_or_mismatching_audit_never_manufactures_accepted_science(change):
    specimen, proofs = selected_specimen("readers")
    if change == "missing_proof":
        proofs = None
    elif change in {"action", "field", "selection", "value", "authority", "evidence", "specimen"}:
        proof = proofs[0]
        event = proof.event.model_copy(deep=True)
        if change == "action":
            event.action = "review_field"
        elif change == "specimen":
            proof = replace(proof, specimen_id="another-specimen")
        else:
            key = {"field": "field_key", "selection": "selection_id", "authority": "authority_id",
                   "evidence": "evidence_ids"}.get(change, change)
            event.after[key] = ["other-evidence"] if change == "evidence" else "mismatch"
        proofs = [replace(proof, event=event)]
    elif change == "marker":
        specimen.run.dependencies["human_review_field_locks"]["country"]["selection_id"] = "forged"
    elif change == "stored_value":
        specimen.run.fields["country"].normalized = "other country"
    elif change == "stored_authority":
        specimen.run.fields["country"].authority_id = "other authority"
    elif change == "source":
        specimen.run.evidence[0].source = "another-source"
    elif change == "locator":
        specimen.run.evidence[0].locator = "research-candidate:" + "c" * 64
    elif change == "raw_capture":
        specimen.run.evidence[0].raw_ref = None
    else:
        specimen.run.fields["country"].evidence_relations = {}
    with pytest.raises(ValueError, match="human_research_candidate_provenance_invalid"):
        writes(specimen, locate, size, "reviewer-uid", reviewer=True, review_proofs=proofs)


def test_a_worker_cannot_silently_drop_a_saved_human_choice_or_infer_acceptance_from_a_marker():
    specimen, _ = selected_specimen("readers")
    with pytest.raises(ValueError, match="human_research_candidate_provenance_invalid"):
        writes(specimen, locate, size, "worker-uid", reviewer=False)


def test_proved_future_projection_reuses_the_human_candidate_without_emitting_a_reviewer_audit_as_worker():
    specimen, proofs = selected_specimen("readers")
    original = writes(specimen, locate, size, "reviewer-uid", reviewer=True, review_proofs=proofs)
    future = writes(specimen, locate, size, "worker-uid", reviewer=False, review_proofs=proofs)
    assert rows(future, "AppendFieldCandidateV2") == rows(original, "AppendFieldCandidateV2")
    assert rows(future, "AppendResolvedFieldV2") == rows(original, "AppendResolvedFieldV2")
    assert rows(future, "AppendReviewDecisionV2") == []


def test_authenticated_worker_projection_fetches_original_human_proofs(monkeypatch):
    from specimen_digitization.application.production import SqlConnectRepository, verified_actor_context
    from specimen_digitization.application.storage import ProjectionResult
    from test_projection_writer import Session

    specimen, proofs = selected_specimen("readers")
    session = Session()
    repository = SqlConnectRepository(session=session)
    monkeypatch.setattr(repository, "locate", locate)
    monkeypatch.setattr(repository, "_sized", size)
    seen = []

    def retained(scope, value):
        seen.append((scope, value.id))
        return proofs, lambda _: None

    monkeypatch.setattr(repository, "_review_proofs", retained)
    with verified_actor_context("worker-uid"):
        result = repository.write_projection(specimen.scope, specimen, reviewer=False)
    assert result == ProjectionResult(True)
    assert seen == [(specimen.scope, specimen.id)]
    assert not any(operation == "AppendReviewDecisionV2" for operation, _ in session.calls)
    human = [variables for operation, variables in session.calls
             if operation == "AppendFieldCandidateV2" and variables["literalValue"] is None]
    assert len(human) == 1 and human[0]["normalizedValue"] == "Philippines"


def test_worker_projection_recovers_transient_candidate_write_with_the_same_human_proof(monkeypatch):
    from specimen_digitization.application.production import SqlConnectRepository, verified_actor_context
    from specimen_digitization.application.storage import ProjectionResult
    from test_projection_writer import Session, Response

    specimen, proofs = selected_specimen("readers")
    failures = []

    def transport(operation):
        if operation == "AppendFieldCandidateV2" and not failures:
            failures.append(operation)
            return Response({}, status=503)
        return None

    session = Session(transport)
    repository = SqlConnectRepository(session=session)
    monkeypatch.setattr(repository, "locate", locate)
    monkeypatch.setattr(repository, "_sized", size)
    monkeypatch.setattr(repository, "_review_proofs", lambda *_: (proofs, lambda _: None))
    with verified_actor_context("worker-uid"):
        first = repository.write_projection(specimen.scope, specimen, reviewer=False)
        second = repository.write_projection(specimen.scope, specimen, reviewer=False)
    assert first == ProjectionResult(False, "AppendFieldCandidateV2")
    assert second == ProjectionResult(True)
    assert any(operation == "AppendResolvedFieldV2" for operation, _ in session.calls)
