"""Operator proof reads: source ACL contract plus real backend proof machinery.

The named transport below supplies explicit synthetic authorization outcomes;
it does not evaluate CEL or prove deployed/native SQL behavior. Snapshot,
save-audit and human-choice validation use the real repository and projector.
"""

from copy import deepcopy
from pathlib import Path
import re
from types import SimpleNamespace
from uuid import uuid4

import pytest

from specimen_digitization.application.domain import (
    AuditEvent, Disposition, Evidence, FieldValue, Principal, Scope,
)
from specimen_digitization.application.production import (
    SqlConnectRepository, actor_uid, verified_actor_context,
)
from specimen_digitization.application.storage import LocalBlobs, ProjectionResult, digest
from test_projection_writer import Response
from test_review_projection_provenance import CanonicalSession, specimen


SOURCE = Path(__file__).parents[1] / "dataconnect/connector/projection.gql"


def operation(source, name):
    match = re.search(
        rf"^(?:query|mutation) {name}\b.*?(?=^(?:query|mutation) |\Z)",
        source, re.MULTILINE | re.DOTALL,
    )
    assert match is not None
    return match.group()


def roles(block):
    return set(re.findall(r"'([^']+)'", re.search(r"this\.role in \[([^]]+)\]", block)[1]))


def test_source_proof_read_adds_operator_without_review_mutation_authority():
    source = SOURCE.read_text()
    proof = operation(source, "GetReviewSaveProofV1")
    assert proof.startswith("query ")
    assert roles(proof) == {"operator", "reviewer", "manager", "admin"}
    assert "organizationMember(key: {organizationId: $organizationId, uid: $actorUid}) @check(expr: \"this.active\")" in proof
    assert "collectionMember(key: {organizationId: $organizationId, collectionId: $collectionId, uid: $actorUid}) @check(expr: \"this.active &&" in proof
    assert "specimen(key: {organizationId: $organizationId, collectionId: $collectionId, id: $specimenId})" in proof
    assert "this != null && this.revision >= vars.resultingRevision" in proof
    assert "(!this.sensitive || response.collectionMember.canViewSensitive)" in proof
    assert "vars.baseRevision >= 1 && vars.resultingRevision == vars.baseRevision + 1" in proof
    assert "actorUid: {eq: $decisionActorUid}" in proof
    assert "specimenId: {eq: $specimenId}" in proof
    assert "revision: {eq: $resultingRevision}" in proof
    assert not re.search(r"\b\w+_(?:insert|update|updateMany|delete|deleteMany)\s*\(", proof)
    for name in ("AppendReviewDecisionV1", "AppendReviewDecisionV2"):
        assert roles(operation(source, name)) == {"reviewer", "manager", "admin"}


class ScopedProofSession(CanonicalSession):
    """A named synthetic transport with one exact fixture grant for proof reads."""

    def __init__(self, value):
        super().__init__()
        self.active.add("worker-uid")
        self.scope = value.scope
        self.specimen_id = value.id
        self.sensitive = value.asset.sensitive
        self.org_member = True
        self.collection_member = True
        self.role = "operator"
        self.can_view_sensitive = True
        self.proof_attempts = []

    def post(self, url, json, timeout):
        name, variables = json["operationName"], json["variables"]
        if name == "GetReviewSaveProofV1" and variables["actorUid"] == "worker-uid":
            self.proof_attempts.append((url, deepcopy(variables)))
            authorized = (
                self.org_member and self.collection_member
                and self.role in {"operator", "reviewer", "manager", "admin"}
                and (not self.sensitive or self.can_view_sensitive)
                and variables["organizationId"] == self.scope.organization_id
                and variables["collectionId"] == self.scope.collection_id
                and variables["specimenId"] == self.specimen_id
            )
            if not authorized:
                self.calls.append((name, deepcopy(variables)))
                return Response({}, status=403)
        return super().post(url, json, timeout)


@pytest.fixture
def retained(tmp_path):
    blobs = LocalBlobs(tmp_path / "blobs")
    value = specimen(blobs)
    value.asset.sensitive = True
    session = ScopedProofSession(value)
    repository = SqlConnectRepository(session=session, graph_blobs=blobs)
    reviewer = Principal(user_id="A", scope=value.scope, role="reviewer")
    with verified_actor_context("A"):
        value = repository.create(reviewer, value, "create", digest("create"))
        selection = digest("offline retained candidate")
        raw_ref = blobs.put(b'{"kind":"offline-human-research-choice"}')
        evidence = Evidence(kind="authority_selection", source="geolocate",
            locator="research-candidate:" + selection, excerpt="Philippines",
            raw_ref=raw_ref, digest=raw_ref)
        value.run.evidence.append(evidence)
        value.run.fields["country"] = FieldValue(state="supported", literal="P.I.",
            parsed="Philippines", normalized="Philippines",
            authority_id="geolocate:a863d52e6ff08fe2", evidence_ids=[evidence.id],
            evidence_relations={evidence.id: "decides"})
        value.run.dependencies["human_review_field_locks"] = {
            "country": {"selection_id": selection, "evidence_id": evidence.id}}
        value.run.disposition = Disposition.REVIEW
        value.run.stage = "finalized"
        value.audit.append(AuditEvent(actor="A", action="review_research_candidate",
            reason="Offline original reviewer choice", after={
                "field_key": "country", "selection_id": selection, "value": "Philippines",
                "authority_id": value.run.fields["country"].authority_id,
                "source_id": "geolocate", "evidence_ids": [evidence.id],
                "precision": None, "century_rule": None}))
        value = repository.save(reviewer, value, 1, "human-choice", digest("human-choice"))
    assert value.audit[-1].id in session.decisions
    # The current operator authenticates the read; the original author need not
    # remain active. Restart the repository to exercise proof reads and projection.
    session.active.remove("A")
    session.calls.clear()
    return SimpleNamespace(value=value, session=session,
        repository=SqlConnectRepository(session=session, graph_blobs=blobs))


def test_active_operator_projects_proved_choice_with_exact_scope_and_no_review_mutation(retained):
    value, session, repository = retained.value, retained.session, retained.repository
    original_decisions = deepcopy(session.decisions)
    with verified_actor_context("worker-uid"):
        result = repository.write_projection(value.scope, value, reviewer=False)
    assert result == ProjectionResult(True)
    [request] = session.proof_attempts
    url, variables = request
    assert url.endswith(":impersonateQuery")
    assert variables == {
        "organizationId": value.scope.organization_id,
        "collectionId": value.scope.collection_id, "actorUid": "worker-uid",
        "specimenId": value.id, "decisionId": value.audit[-1].id,
        "decisionActorUid": "A", "baseRevision": 1, "resultingRevision": 2,
    }
    assert any(name == "AppendResolvedFieldV2" for name, _ in session.calls)
    assert not any(name.startswith("AppendReviewDecision") for name, _ in session.calls)
    assert session.decisions == original_decisions


@pytest.mark.parametrize("denial", [
    "missing_org_member", "inactive_org_member", "missing_collection_member",
    "inactive_collection_member", "inactive_actor", "viewer", "sensitive",
    "wrong_organization", "wrong_collection", "wrong_specimen",
])
def test_denied_operator_proof_read_stops_before_normalized_mutations(retained, denial):
    value, session, repository = retained.value, retained.session, retained.repository
    scope = value.scope
    if denial == "missing_org_member":
        session.org_member = None
    elif denial == "inactive_org_member":
        session.org_member = False
    elif denial == "missing_collection_member":
        session.collection_member = None
    elif denial == "inactive_collection_member":
        session.collection_member = False
    elif denial == "inactive_actor":
        session.active.remove("worker-uid")
    elif denial == "viewer":
        session.role = "viewer"
    elif denial == "sensitive":
        session.can_view_sensitive = False
    elif denial == "wrong_specimen":
        session.specimen_id = str(uuid4())
    else:
        scope = Scope(organization_id=str(uuid4()) if denial == "wrong_organization" else scope.organization_id,
                      collection_id=str(uuid4()) if denial == "wrong_collection" else scope.collection_id)
    with verified_actor_context("worker-uid"):
        result = repository.write_projection(scope, value, reviewer=False)
    assert result == ProjectionResult(False, "not_computed")
    # The globally inactive actor is refused at its first snapshot read;
    # the other fixture denials exercise the named proof read itself.
    assert len(session.proof_attempts) == (0 if denial == "inactive_actor" else 1)
    assert not any(name.startswith(("Append", "Register", "Record")) for name, _ in session.calls)


def test_no_verified_actor_cannot_dispatch_a_proof_read(retained):
    token = actor_uid.set(None)
    try:
        result = retained.repository.write_projection(retained.value.scope, retained.value, reviewer=False)
    finally:
        actor_uid.reset(token)
    assert result == ProjectionResult(False, "not_computed")
    assert retained.session.calls == []
