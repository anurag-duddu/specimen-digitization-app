"""Actual original-save proof and fresh transition over named offline transport."""
import copy

import pytest

from specimen_digitization.application.domain import AuditEvent, FieldValue, Principal, Run
from specimen_digitization.application.human_field_carry import (
    KEY, INVALID, active_value, adapt_projection, install, manifests, prepare, verify,
)
from specimen_digitization.application.production import SqlConnectRepository, actor_uid
from specimen_digitization.application.storage import LocalBlobs, digest
from test_review_projection_provenance import CanonicalSession, Response, save, specimen


class CarrySession(CanonicalSession):
    def post(self, url, json, timeout):
        if json["operationName"] == "GetSpecimen":
            v = json["variables"]
            if v["actorUid"] not in self.active:
                return Response({}, status=403)
            row = self.snapshots[max(self.snapshots)]
            payload = row["snapshot"]
            if payload["id"] != v["id"] or payload["scope"] != {
                    "organization_id": v["organizationId"], "collection_id": v["collectionId"]}:
                return Response({"data": {}})
            return Response({"data": {"specimen": {"revision": row["revision"],
                "sensitive": payload["asset"].get("sensitive", True)}, "specimenSnapshots": [row]}})
        return super().post(url, json, timeout)


class CarryCase:
    def __init__(self, path):
        self.blobs = LocalBlobs(path / "source")
        self.session = CarrySession()
        self.repo = SqlConnectRepository(session=self.session, graph_blobs=self.blobs)
        self.principal = Principal(user_id="B", role="reviewer", scope=specimen(self.blobs).scope)
        original = specimen(self.blobs)
        self.principal.scope = original.scope
        self.current = self.repo.create(self.principal, original, "create", digest("create"))

    def review(self, key, actor="A", **values):
        value = self.current.model_copy(deep=True)
        field = FieldValue(**values)
        value.run.fields[key] = field
        value.run.dependencies.get(KEY, {}).pop(key, None)
        value.audit.append(AuditEvent(actor=actor, action="review_field", reason="checked original label",
            after={**field.model_dump(mode="json"), "field_key": key}))
        self.current = save(self.repo, value, actor, f"review-{value.version}")
        return self.current

    def reprocess(self):
        value = self.current.model_copy(deep=True)
        new = Run(profile=value.run.profile, classification_selection=value.run.classification_selection)
        event = AuditEvent(actor="B", action="reprocess", reason="fresh research, preserve saved decisions")
        carries = prepare(self.repo, value, new.id, event, self.blobs)
        value.previous_runs.append(value.run)
        value.run = new
        install(value, carries, self.blobs)
        value.audit.append(event)
        self.current = self.repo.save(self.principal, value, value.version, f"reprocess-{value.version}", digest(event.id))
        return verify(self.repo, self.current, self.blobs)


@pytest.fixture
def case(tmp_path):
    token = actor_uid.set("B")
    try:
        yield CarryCase(tmp_path)
    finally:
        actor_uid.reset(token)


def test_two_deliberate_unknowns_carry_and_real_transition_is_proved(case):
    case.review("elevation_from_m", state="unknown", reason="feet are not literal metres")
    old = case.review("city", state="unknown", reason="slope is not a city")
    old_bytes = old.model_dump(mode="json")
    proved = case.reprocess()
    assert set(proved.outcomes) == {"elevation_from_m", "city"}
    assert all(v.value.state == "unknown" for v in proved.outcomes.values())
    assert case.repo.version(old.scope, old.id, old.version).model_dump(mode="json") == old_bytes
    assert case.current.previous_runs == [] or case.current.previous_runs[-1] == old.run
    assert all(v.canonical_run_id == case.current.run.id and v.origin_run_id == old.run.id for v in proved.outcomes.values())
    assert {v.reason for v in proved.outcomes.values()} == {"checked original label"}
    assert all(v.value.source_observation_id is None for v in proved.outcomes.values())


def test_source_bytes_are_read_once_per_proof_pass_for_both_fields(case, monkeypatch):
    case.review("city", state="unknown")
    case.review("elevation_from_m", state="unknown")
    case.reprocess()
    calls = []
    read = case.blobs.get_bounded
    def counted(ref, bound):
        calls.append(ref)
        return read(ref, bound)
    monkeypatch.setattr(case.blobs, "get_bounded", counted)
    verified = verify(case.repo, case.current, case.blobs)
    assert len(verified.outcomes) == 2
    assert calls.count(case.current.asset.blob_ref) == 1


@pytest.mark.parametrize("blocker", ["temporary_provider_failure", "external_outcome_unknown"])
def test_due_retry_verifies_saved_base_before_clearing_mutable_fields(case, blocker):
    from datetime import datetime, timezone
    from specimen_digitization.application.workflow import Workflow
    case.review("city", state="unknown")
    case.reprocess()
    pending = case.current.model_copy(deep=True)
    pending.run.stage = "retry_scheduled"
    pending.run.blocker = blocker
    pending.run.next_retry_at = "2026-10-05T00:00:00+00:00"
    case.current = save(case.repo, pending, "B", "schedule-proved-retry")
    calls = []
    class PinOnly:
        def pin_dependencies(self, _run):
            calls.append("pin")
            return {"synthetic": True}
    workflow = Workflow(case.repo, case.blobs, PinOnly(),
        clock=lambda: datetime(2026, 10, 6, tzinfo=timezone.utc))
    result = workflow._step(case.principal, case.current.id)
    assert result.run.blocker != INVALID
    assert result.run.fields["city"] == case.current.run.fields["city"]
    if blocker == "external_outcome_unknown":
        assert not calls and result.run.stage == "processing_blocked"
        assert result.run.blocker == blocker
    else:
        assert calls == ["pin"] and "pin_dependencies" in result.run.completed_steps
        assert result.run.next_retry_at is None
    assert result.run.usage.actual_cost_micros == case.current.run.usage.actual_cost_micros


def _save_region_review(case):
    from specimen_digitization.application.domain import Region
    value = case.current.model_copy(deep=True)
    old = value.run
    value.previous_runs.append(old)
    value.run = Run(profile=old.profile, regions=[Region(asset_id=value.asset.id, x=0, y=0,
        width=1, height=1, order=0, method="human_review", version="synthetic-v1")])
    value.audit.append(AuditEvent(actor="A", action="review_regions", reason="Human corrected geometry",
        before={"run_id": old.id}, after={"run_id": value.run.id}))
    case.current = save(case.repo, value, "A", "actual-region-review")


def test_still_current_human_regions_hold_before_reprocess_cas(case):
    _save_region_review(case)
    revision = case.current.version
    with pytest.raises(ValueError, match=INVALID):
        case.reprocess()
    assert max(case.session.snapshots) == revision


def test_obsolete_historical_region_review_is_not_a_global_hold(case):
    _save_region_review(case)
    value = case.current.model_copy(deep=True)
    value.previous_runs.append(value.run)
    value.run = Run(profile=value.run.profile)
    value.audit.append(AuditEvent(actor="B", action="reprocess", reason="Synthetic prior historical supersession"))
    case.current = save(case.repo, value, "B", "historical-region-superseded")
    assert case.reprocess().outcomes == {}


@pytest.mark.parametrize("compact_native_id", [False, True])
def test_http_receipt_replay_does_not_scan_first_two_records_or_dispatch_twice(tmp_path, monkeypatch, compact_native_id):
    from test_human_field_carry_api import CarryApiCase, ACTORS
    from test_projection_writer import Response
    c = CarryApiCase(tmp_path)
    try:
        assert c.save_unknown("city", "Saved uncertainty").status_code == 200
        before = c.workspace().json()
        body = {"expected_revision": before["revision"], "action": "reprocess",
            "reason": "Reprocess while retaining saved uncertainty"}
        url = f"{c.prefix}/runs/{before['active_run_id']}/actions"
        headers = c.headers(ACTORS[0], "multi-record-replay")
        first = c.client.post(url, headers=headers, json=body)
        assert first.status_code == 200, first.text
        call = c.session.post
        def with_other_records(url, json, timeout):
            if json["operationName"] == "SearchSpecimens" and not json["variables"].get("specimenId") and not json["variables"].get("activeRunId"):
                # Target exists as third record, outside the former limit2 path.
                row = c.session._search_row()
                return Response({"data": {"items": [{**row, "id": "foreign-one"}, {**row, "id": "foreign-two"}]}})
            response = call(url, json, timeout)
            if compact_native_id and json["operationName"] == "GetReprocessActionReceiptsV1":
                raw = response.body
                for row in raw["data"]["requestReceipts"]:
                    row["specimenId"] = row["specimenId"].replace("-", "")
                return Response(raw)
            return response
        monkeypatch.setattr(c.session, "post", with_other_records)
        c.session.calls.clear()
        second = c.client.post(url, headers=headers, json=body)
        assert second.status_code == 200, second.text
        assert second.json() == first.json() and c.dispatcher.calls == 1
        assert sum(op == "GetReprocessActionReceiptsV1" for op, _ in c.session.calls) == 1
        assert not any(op == "SearchSpecimens" for op, _ in c.session.calls)
        assert c.client.post(url, headers=headers, json={**body, "reason": "different"}).status_code == 409
        assert c.dispatcher.calls == 1
    finally:
        c.client.close()


@pytest.mark.parametrize("refusal", ["actor", "key", "scope", "ambiguity", "sensitive"])
def test_http_receipt_replay_refuses_foreign_ambiguous_or_sensitive_targets(tmp_path, monkeypatch, refusal):
    from test_human_field_carry_api import CarryApiCase, ACTORS
    from test_projection_writer import Response
    c = CarryApiCase(tmp_path)
    try:
        assert c.save_unknown("city", "Saved uncertainty").status_code == 200
        before = c.workspace().json()
        body = {"expected_revision": before["revision"], "action": "reprocess",
            "reason": "Reprocess while retaining saved uncertainty"}
        url = f"{c.prefix}/runs/{before['active_run_id']}/actions"
        headers = c.headers(ACTORS[0], "bounded-replay")
        first = c.client.post(url, headers=headers, json=body)
        assert first.status_code == 200, first.text
        if refusal == "actor":
            headers = c.headers(ACTORS[1], "bounded-replay")
        elif refusal == "key":
            headers = c.headers(ACTORS[0], "different-key")
        elif refusal == "scope":
            url = url.replace(c.current.scope.organization_id, "00000000-0000-0000-0000-000000000001")
        elif refusal == "ambiguity":
            call = c.session.post
            def ambiguous(url, json, timeout):
                response = call(url, json, timeout)
                if json["operationName"] == "GetReprocessActionReceiptsV1":
                    row = response.body["data"]["requestReceipts"][0]
                    return Response({"data": {"requestReceipts": [row, dict(row)]}})
                return response
            monkeypatch.setattr(c.session, "post", ambiguous)
        else:
            token = actor_uid.set(ACTORS[0])
            try:
                current = c.repository.get(c.current.scope, c.current.id)
            finally:
                actor_uid.reset(token)
            changed = current.model_copy(deep=True)
            changed.asset.sensitive = True
            save(c.repository, changed, ACTORS[0], "mark-sensitive-after-original-response")
            c.sensitive_access[ACTORS[0]] = False
        response = c.client.post(url, headers=headers, json=body)
        assert response.status_code in {403, 404, 409}, response.text
        assert c.dispatcher.calls == 1
    finally:
        c.client.close()


def test_same_value_save_is_latest_origin_and_recarry_compares_active_projection(case):
    case.review("city", state="unknown", reason="same current decision")
    first = case.reprocess().outcomes["city"]
    second = case.reprocess().outcomes["city"]
    assert second.origin_event_id == first.origin_event_id
    assert second.value != first.value  # honest fresh evidence identity, same value
    case.review("city", actor="B", state="unknown", reason="same current decision")
    third = case.reprocess().outcomes["city"]
    assert third.origin_event_id != first.origin_event_id and third.actor == "B"


def test_supported_normalized_only_has_no_fake_current_reading(case):
    case.review("country", state="supported", normalized="Philippines", parsed="Philippines", reason="manual review")
    proved = case.reprocess()
    value = proved.outcomes["country"].value
    assert value.literal is None and value.normalized == "Philippines"
    assert value.input_source is None and value.source_region_id is None
    assert proved.outcomes["country"].original_value.evidence_ids == []


def test_changed_current_field_is_explicit_hold_not_silent_drop(case):
    case.review("city", state="unknown")
    changed = case.current.model_copy(deep=True)
    changed.run.fields["city"] = FieldValue(state="supported", literal="contrary automatic value")
    case.current = save(case.repo, changed, "B", "unexpected-overwrite")
    with pytest.raises(ValueError, match=INVALID):
        case.reprocess()


def test_forged_origin_event_body_refused_even_if_snapshot_field_same(case):
    case.review("city", state="unknown")
    case.reprocess()
    revision = manifests(case.current)["city"].origin_revision
    original = case.session.snapshots[revision]
    original["snapshot"]["audit"][-1]["after"]["state"] = "supported"
    original["sha256"] = digest(original["snapshot"])
    with pytest.raises(ValueError):
        verify(case.repo, case.current, case.blobs)


def test_incompatible_original_event_body_holds_before_reprocess_cas(case):
    original = case.current.model_copy(deep=True)
    original.run.fields["city"] = FieldValue(state="unknown")
    original.audit.append(AuditEvent(actor="A", action="review_field", reason="incompatible fixture",
        after={**FieldValue(state="supported").model_dump(mode="json"), "field_key": "city"}))
    case.current = save(case.repo, original, "A", "incompatible-original")
    revision = case.current.version
    with pytest.raises(ValueError, match=INVALID):
        case.reprocess()
    assert max(case.session.snapshots) == revision


@pytest.mark.parametrize("member", ["actorUid", "revision", "specimenId"])
def test_actual_reprocess_server_audit_required(case, member):
    case.review("city", state="unknown")
    case.reprocess()
    case.session.audit[-1][member] = "wrong"
    with pytest.raises(ValueError, match=INVALID):
        verify(case.repo, case.current, case.blobs)


def test_projection_adapter_recomputes_record_and_normalized_only_candidate(case):
    from specimen_digitization.application import projection
    case.review("country", state="supported", normalized="Philippines", parsed="Philippines")
    case.reprocess()
    value = case.current.model_copy(deep=True)
    old = case.repo.version(value.scope, value.id, 1)
    value.run.profile_snapshot = old.run.profile_snapshot
    value.run.profile_registry_version = old.run.profile_registry_version
    value.run.dependencies.update(profile_snapshot_sha256=digest(value.run.profile_snapshot), profile_registry_version=old.run.profile_registry_version)
    case.current = save(case.repo, value, "B", "fresh-profile")
    verified = verify(case.repo, case.current, case.blobs)
    rows = projection.writes(case.current, case.repo.locate, case.repo._sized, "B", base_record=True)
    adapted = adapt_projection(rows, case.current, verified)
    candidate = next(w.variables for w in adapted if w.operation == "AppendFieldCandidateV2" and w.variables["fieldKey"] == "country")
    field = next(w.variables for w in adapted if w.operation == "AppendResolvedFieldV2" and w.variables["fieldKey"] == "country")
    record = next(w.variables for w in adapted if w.operation == "AppendRecordVersionV2")
    assert candidate["normalizedValue"] == "Philippines" and candidate["sourceObservationId"] is None
    assert field["candidateId"] == candidate["id"] and field["recordVersionId"] == record["id"]
    assert all(w.variables["recordVersionId"] == record["id"] for w in adapted if w.operation in {"AppendResolvedFieldV2", "AppendValidationFindingV2"})


def test_missing_actual_transition_cannot_dispatch_or_become_proof(case):
    case.review("city", state="unknown")
    new = Run()
    event = AuditEvent(actor="B", action="reprocess", reason="pending intent")
    carries = prepare(case.repo, case.current, new.id, event, case.blobs)
    pending = case.current.model_copy(deep=True)
    pending.run = new
    install(pending, carries, case.blobs)
    with pytest.raises((ValueError, KeyError)):
        verify(case.repo, pending, case.blobs)


def test_missing_current_manifest_cannot_erase_previously_proved_decisions(case):
    case.review("city", state="unknown")
    case.reprocess()
    damaged = case.current.model_copy(deep=True)
    damaged.run.dependencies.pop(KEY)
    case.current = save(case.repo, damaged, "B", "invalid-worker-drop")
    with pytest.raises(ValueError, match=INVALID):
        verify(case.repo, case.current, case.blobs)


def test_precision_bearing_manual_choice_keeps_full_parsed_candidate(case):
    from specimen_digitization.application import projection
    case.review("date_visited_from", state="supported", parsed="2020-05", normalized="2020-05",
        precision="month", century_rule="exact written year")
    case.reprocess()
    value = case.current.model_copy(deep=True)
    original = case.repo.version(value.scope, value.id, 1)
    value.run.profile_snapshot = original.run.profile_snapshot
    value.run.profile_registry_version = original.run.profile_registry_version
    value.run.dependencies.update(profile_snapshot_sha256=digest(value.run.profile_snapshot),
        profile_registry_version=original.run.profile_registry_version)
    case.current = save(case.repo, value, "B", "precision-profile")
    proof = verify(case.repo, case.current, case.blobs)
    rows = adapt_projection(projection.writes(case.current, case.repo.locate, case.repo._sized, "B", base_record=True),
        case.current, proof)
    candidate = next(w.variables for w in rows if w.operation == "AppendFieldCandidateV2"
        and w.variables["fieldKey"] == "date_visited_from")
    assert candidate["parsedValue"] == {"value": "2020-05", "precision": "month", "century_rule": "exact written year"}


def test_changed_source_in_intermediate_transition_refused_after_current_restored(case):
    case.review("city", state="unknown")
    case.reprocess()
    case.reprocess()
    intermediate = case.session.snapshots[3]
    intermediate["snapshot"]["asset"]["pixel_basis"] = "changed_source_basis"
    intermediate["sha256"] = digest(intermediate["snapshot"])
    with pytest.raises(ValueError, match=INVALID):
        verify(case.repo, case.current, case.blobs)
