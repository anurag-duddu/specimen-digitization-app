"""Real proof reader and immutable saves over named synthetic transport, not native SQL.

GEOLocate inputs use the recorded adapter fixture and actual retained candidate
selection machinery. Every operation is offline; no source/model dispatch occurs.
"""

import json

import pytest

from specimen_digitization.application.domain import AuditEvent, Evidence, FieldValue, Principal, ValueState
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import LocalBlobs, canonical_json, digest as snapshot_digest
from specimen_digitization.research_harness.contracts import FieldKey, digest
from specimen_digitization.research_harness.derivation_inputs import (
    PROVENANCE_LIMIT, collect_settled_inputs, genuine_human_locked_fields,
    inspect_settled_inputs, verify_settled_inputs,
)
from specimen_digitization.research_harness.human_review import CandidateReviewContext
from test_candidate_selection import Retained
from test_review_projection_provenance import CanonicalSession, save, specimen


class Case:
    def __init__(self, tmp_path):
        self.path = tmp_path
        self.blobs = LocalBlobs(tmp_path / "ordinary")
        self.session = CanonicalSession()
        self.repo = SqlConnectRepository(session=self.session, graph_blobs=self.blobs)
        value = specimen(self.blobs)
        value.run.fields = {"country": FieldValue(literal="Philippines", state="ambiguous")}
        self.current = self.repo.create(Principal(user_id="B", role="reviewer", scope=value.scope),
                                       value, "create", snapshot_digest("create"))
        self.count = 0

    def save(self, value, actor="A"):
        self.count += 1
        self.current = save(self.repo, value, actor, "save-" + str(self.count))
        return self.current

    def manual(self, key="country", action="review_field", **changes):
        value = self.current.model_copy(deep=True)
        field = FieldValue(state="supported", literal="Philippines", normalized="Philippines",
                           **changes)
        value.run.fields[key] = field
        value.audit.append(AuditEvent(actor="A", action=action, reason="human checked label",
                                     after={**field.model_dump(mode="json"), "field_key": key}))
        return self.save(value)

    def selected(self, change=None):
        (self.path / "research").mkdir()
        choice = Retained(self.path / "research").choose()
        if change:
            change(choice)
        value = self.current.model_copy(deep=True)
        context = CandidateReviewContext(None, None, None, {"country": choice})
        after = context.apply(value, "country", self.blobs, "checked original source")
        value.audit.append(AuditEvent(actor="A", action="review_research_candidate", reason="checked", after=after))
        return self.save(value)

    def collect(self, **kwargs):
        return collect_settled_inputs(self.repo, self.current, self.blobs, **kwargs)

    def artifact(self, item):
        return json.loads(self.blobs.get_bounded(item.provenance_blob_ref, PROVENANCE_LIMIT))


@pytest.fixture
def case(tmp_path):
    token = actor_uid.set("B")
    try:
        yield Case(tmp_path)
    finally:
        actor_uid.reset(token)


def test_manual_input_has_exact_field_original_review_and_no_provider_claim(case):
    current = case.manual()
    before = current.model_dump(mode="json")
    item, = case.collect()
    event = current.audit[-1]
    assert item.value == "Philippines" and item.field_key == FieldKey.COUNTRY
    assert item.revision == item.original_review_revision == 2
    assert item.authority_id == "review-decision:" + event.id
    assert item.evidence_ids == (item.authority_id,)
    assert item.selection_id is None and item.field_digest == digest(current.run.fields["country"])
    assert case.artifact(item) == {
        "kind": "human_derivation_input", "field_key": "country", "canonical_run_id": current.run.id,
        "canonical_revision": 2, "field_digest": item.field_digest,
        "review_decision": event.model_dump(mode="json"), "original_review_revision": 2,
        "source_selection": None,
    }
    assert current.model_dump(mode="json") == before
    verify_settled_inputs(case.repo, current, case.blobs, [item])


def test_manual_authority_and_coordinate_text_do_not_become_trusted_provider_capture(case):
    evidence = Evidence(kind="authority_selection", source="geolocate", locator="manual:coords",
                        excerpt="7.0, 125.0", raw_ref=case.blobs.put(b"manual"), digest=snapshot_digest("manual"))
    case.current.run.evidence.append(evidence)
    case.manual(authority_id="geolocate:a863d52e6ff08fe2", evidence_ids=[evidence.id])
    item, = case.collect()
    assert item.authority_id == "geolocate:a863d52e6ff08fe2"
    assert item.evidence_ids == (evidence.id, "review-decision:" + item.review_decision_id)
    assert case.artifact(item)["source_selection"] is None


def test_retained_source_choice_keeps_exact_ambiguous_result_and_hidden_coordinates(case):
    current = case.selected()
    item, = case.collect()
    event = current.audit[-1]
    evidence, = [e for e in current.run.evidence if e.id == event.after["evidence_ids"][0]]
    original = json.loads(case.blobs.get(evidence.raw_ref))
    source = case.artifact(item)["source_selection"]
    assert source == original
    assert source["source_result"]["status"] == "ambiguous"
    assert source["source_candidate"]["decimal_latitude"] == 6.9833
    assert source["source_candidate"]["decimal_longitude"] == 125.2667
    assert item.selection_id == event.after["selection_id"]
    assert current.run.fields["country"].literal == "Philippines"
    verify_settled_inputs(case.repo, current, case.blobs, (item,))


def test_capability_and_worker_verification_are_read_only(case):
    case.selected()
    items = case.collect()

    class ReadOnly:
        def get_bounded(self, ref, limit):
            return case.blobs.get_bounded(ref, limit)

        def put(self, data):
            pytest.fail("read-only validation attempted artifact write")

    start = len(case.session.calls)
    assert inspect_settled_inputs(case.repo, case.current, ReadOnly()) == (FieldKey.COUNTRY,)
    verify_settled_inputs(case.repo, case.current, ReadOnly(), items)
    assert all(op in {"GetSnapshot", "GetReviewSaveProofV1"} for op, _ in case.session.calls[start:])


def test_queued_revision_can_advance_without_rewriting_original_input_revision(case):
    case.selected()
    items = case.collect()
    value = case.current.model_copy(deep=True)
    value.audit.append(AuditEvent(actor="B", action="review_derive_rest", reason="derive", after={"request": "x"}))
    case.save(value, actor="B")
    verify_settled_inputs(case.repo, case.current, case.blobs, items)
    assert items[0].revision == 2 and case.current.version == 3
    assert genuine_human_locked_fields(case.repo, case.current) == (FieldKey.COUNTRY,)


@pytest.mark.parametrize("attribute,value", [
    ("literal", "edited verbatim"), ("normalized", "Indonesia"), ("reason", "different reason"),
    ("authority_id", "other"), ("source_observation_id", "new-observation"),
    ("layer", "derived"), ("evidence_ids", ["invented-evidence"]), ("state", "ambiguous"),
])
def test_any_field_change_invalidates_old_input_even_when_display_value_is_unchanged(case, attribute, value):
    case.manual()
    items = case.collect()
    current = case.current.model_copy(deep=True)
    setattr(current.run.fields["country"], attribute, ValueState(value) if attribute == "state" else value)
    case.save(current, actor="B")
    assert case.collect() == ()
    assert genuine_human_locked_fields(case.repo, case.current) == ()
    with pytest.raises(ValueError):
        verify_settled_inputs(case.repo, case.current, case.blobs, items)


def test_supported_unreviewed_and_non_geographic_values_are_not_derivation_inputs(case):
    value = case.current.model_copy(deep=True)
    value.run.fields["country"].state = ValueState.SUPPORTED
    value.run.fields["country"].normalized = "Philippines"
    case.save(value, actor="B")
    assert case.collect() == ()
    case.manual(key="elevation_from_m")
    assert case.collect() == ()
    assert genuine_human_locked_fields(case.repo, case.current) == (FieldKey.ELEVATION_FROM_M,)


def test_intentionally_unresolved_human_field_is_still_locked(case):
    current = case.current.model_copy(deep=True)
    current.run.fields["elevation_from_m"] = FieldValue(state="unresolved", reason="human cannot read")
    current.audit.append(AuditEvent(actor="A", action="review_field", reason="human cannot read",
                                   after={"field_key": "elevation_from_m", "state": "unresolved"}))
    case.save(current)
    assert case.collect() == ()
    assert genuine_human_locked_fields(case.repo, case.current) == (FieldKey.ELEVATION_FROM_M,)


@pytest.mark.parametrize("action,key", [("review_authority_resolution", "country"),
                                         ("review_taxonomy_resolution", "taxon")])
def test_original_authority_and_taxonomy_decisions_establish_current_locks(case, action, key):
    case.manual(key=key, action=action, authority_id="retained-authority")
    assert genuine_human_locked_fields(case.repo, case.current) == (FieldKey(key),)
    assert len(case.collect()) == (1 if key == "country" else 0)


def test_latest_decision_prevents_old_proof_revival_after_automatic_revert(case):
    case.manual()
    old = case.current.run.fields["country"].model_copy(deep=True)
    value = case.current.model_copy(deep=True)
    value.run.fields["country"].normalized = "Indonesia"
    value.audit.append(AuditEvent(actor="A", action="review_field", reason="new review",
                                   after={"field_key": "country", "normalized": "Indonesia"}))
    case.save(value)
    value = case.current.model_copy(deep=True)
    value.run.fields["country"] = old
    case.save(value, actor="B")
    assert case.collect() == ()


def test_newest_matching_review_is_the_actual_input_provenance(case):
    case.manual()
    first = case.collect()[0]
    case.manual()
    latest = case.collect()[0]
    assert latest.review_decision_id == case.current.audit[-1].id
    assert latest.original_review_revision == 3
    with pytest.raises(ValueError):
        verify_settled_inputs(case.repo, case.current, case.blobs, [first])


@pytest.mark.parametrize("damage", ["missing_audit", "wrong_actor", "original_digest"])
def test_real_repository_proof_reader_rejects_absent_or_inconsistent_original_save(case, damage):
    case.manual()
    if damage == "missing_audit":
        case.session.audit.clear()
    elif damage == "wrong_actor":
        case.session.audit[-1]["actorUid"] = "B"
    else:
        case.session.snapshots[2]["sha256"] = "f" * 64
    with pytest.raises(ValueError):
        case.collect()


def test_explicit_proofs_are_reused_but_original_snapshot_is_still_required(case):
    case.manual()
    proofs, _ = case.repo._review_proofs(case.current.scope, case.current)
    expected = case.collect()
    start = len(case.session.calls)
    assert case.collect(proofs=proofs) == expected
    assert not any(op == "GetReviewSaveProofV1" for op, _ in case.session.calls[start:])
    case.session.snapshots.pop(2)
    with pytest.raises(Exception):
        case.collect(proofs=proofs)


def test_replaced_evidence_with_same_id_cannot_supply_new_coordinates(case):
    case.selected()
    current = case.current.model_copy(deep=True)
    evidence = current.run.evidence[-1]
    payload = json.loads(case.blobs.get(evidence.raw_ref))
    payload["source_candidate"]["decimal_latitude"] = 8.0
    raw = canonical_json(payload).encode()
    evidence.raw_ref = case.blobs.put(raw)
    evidence.digest = evidence.raw_ref
    case.save(current, actor="B")
    with pytest.raises(ValueError):
        case.collect()


@pytest.mark.parametrize("damage", ["value", "coordinates", "source", "status", "missing_capture", "missing_receipt"])
def test_invalid_original_source_payload_is_not_promoted(case, damage):
    def mutate(choice):
        if damage == "value":
            choice["source_candidate"]["value"] = "wrong value"
        elif damage == "coordinates":
            choice["source_candidate"]["decimal_latitude"] = 8.0
        elif damage == "source":
            choice["source_result"]["coverage"]["source_id"] = "another-provider"
        elif damage == "status":
            choice["source_result"]["status"] = "failed"
        elif damage == "missing_capture":
            choice["capture"] = {}
        else:
            choice["source_result"]["coverage"]["receipt_ids"] = []
    case.selected(mutate)
    with pytest.raises(ValueError):
        case.collect()


def test_superseded_research_marker_does_not_restore_historical_source_choice(case):
    case.selected()
    items = case.collect()
    value = case.current.model_copy(deep=True)
    value.run.dependencies.pop("human_review_field_locks")
    value.audit.append(AuditEvent(actor="B", action="review_transcription", reason="corrected source"))
    case.save(value, actor="B")
    assert case.collect() == ()
    with pytest.raises(ValueError):
        verify_settled_inputs(case.repo, case.current, case.blobs, items)


@pytest.mark.parametrize("damage", ["value", "revision", "sha", "artifact", "duplicate"])
def test_saved_input_or_artifact_tampering_is_rejected(case, damage):
    case.manual()
    item, = case.collect()
    items = [item]
    if damage == "value":
        items = [item.model_copy(update={"value": "Indonesia"})]
    elif damage == "revision":
        items = [item.model_copy(update={"revision": 100})]
    elif damage == "sha":
        items = [item.model_copy(update={"provenance_sha256": "f" * 64})]
    elif damage == "artifact":
        ref = case.blobs.put(b"{}")
        items = [item.model_copy(update={"provenance_blob_ref": ref, "provenance_sha256": ref})]
    else:
        items *= 2
    with pytest.raises(ValueError):
        verify_settled_inputs(case.repo, case.current, case.blobs, items)
