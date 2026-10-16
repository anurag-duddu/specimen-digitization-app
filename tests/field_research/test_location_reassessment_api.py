"""Location reassessment is a paid, scoped continuation of the retained run."""

from datetime import datetime, timedelta, timezone
import hashlib

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application import api as app_api
from specimen_digitization.application.authority_registry import AuthorityCandidate, AuthorityResult
from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Disposition, FieldValue, LookupStatus, ValueState
from specimen_digitization.application.lane_allowance import LEDGER_KIND, ProgramLedger
from specimen_digitization.application.storage import ReviewDecisionProof, digest
from specimen_digitization.application.workflow import FIELD_RESEARCH, SyntheticAdapters

from test_step import (
    COLLECTION, ORG, Scripted, build_rig, decide, label_with, mounted, review_client,
)
from test_lane_trigger import RecordingDispatcher


FAMILY = {"country", "province_state", "county", "city", "precise_location"}
HEADERS = {"Authorization": "Bearer reviewer", "Idempotency-Key": "reassess-locations"}


@pytest.fixture
def case(tmp_path, monkeypatch):
    rig = build_rig(tmp_path, label_with(country=None, province_state="Illinois",
        county="Clark County", city=None))
    run = rig.specimen.run
    run.fields["country"] = FieldValue(state=ValueState.SUPPORTED, parsed="Philippines",
        authority_id="wikidata:Q928", layer="derived", derived_from=["city"])
    run.fields["city"] = FieldValue(state=ValueState.SUPPORTED, literal="Illinois",
        layer="settled", reason="An older machine assignment")
    run.fields["province_state"] = FieldValue(state=ValueState.UNRESOLVED, literal="Illinois")
    run.fields["county"] = FieldValue(state=ValueState.UNRESOLVED, literal="Clark County")
    run.fields["precise_location"] = FieldValue(state=ValueState.AMBIGUOUS)
    run.stage, run.disposition = "finalized", Disposition.REVIEW
    run.completed_steps.append(FIELD_RESEARCH)
    run.attempts = {"segment": 1, **{step: 1 for step in run.completed_steps if step.startswith("transcribe:")},
        FIELD_RESEARCH: 2}
    run.classification_selection = {"collection_id": COLLECTION,
        "actor_id": rig.principal.user_id, "reason": "Retained intake classification"}
    run.profile.execution = run.profile.execution.model_copy(update={
        "approved_cost_limit_micros": 777_777, "max_external_calls": 71,
        "program_allowance_micros": 16_000_000, "program_ledger_collection": COLLECTION})
    run.usage.reserved_cost_micros = 314_159
    run.usage.external_calls = 7
    run.usage.reserved_tokens = 1_234
    retained_calls = [("segment", 1, "completed", 164_121),
        *[(step, 1, "completed", cost) for step, cost in zip(
            (step for step in run.completed_steps if step.startswith("transcribe:")), (550, 900), strict=True)],
        (FIELD_RESEARCH, 1, "failed", 100_000), (FIELD_RESEARCH, 2, "completed", 48_588)]
    run.paid_calls = [{"step": step, "attempt": attempt, "outcome": outcome,
        "reserved_micros": cost, "cost_micros": cost, "cost_basis": "reserved"}
        for step, attempt, outcome, cost in retained_calls]
    rig.specimen = rig.repository.save(rig.principal, rig.specimen, rig.specimen.version,
        "historical-location-run", digest("historical-location-run"))
    rig.ledger = ProgramLedger(rig.repository, rig.principal.scope)
    rig.repository.put_document(rig.principal.scope, LEDGER_KIND, rig.ledger.ident,
        {"sensitive": False, "reserved_total_micros": 15_123_456,
            "prior_unknown_spend_micros": 99_999}, 0)
    # Supply real published queue policy/bindings; do not replace lane.queue.
    monkeypatch.setattr(app_api, "application_registry",
        lambda synthetic: published_registry({COLLECTION: "insects"}))
    rig.dispatcher = RecordingDispatcher()
    create_app = app_api.create_app
    monkeypatch.setattr(app_api, "create_app",
        lambda **kwargs: create_app(**kwargs, worker_dispatcher=rig.dispatcher))
    rig.client = review_client(rig)
    return rig


def saved(case):
    return case.repository.get(case.principal.scope, case.specimen.id)


def change(case, modify):
    record = saved(case)
    modify(record.run)
    case.specimen = case.repository.save(case.principal, record, record.version,
        "admission-case", digest(record.run.model_dump(mode="json")))


def post(case, *, action="reassess_locations", revision=None, reason="Recheck the retained location hierarchy."):
    current = saved(case)
    return case.client.post(f"/v1/organizations/{ORG}/runs/{current.run.id}/actions",
        headers=HEADERS, json={"expected_revision": current.version if revision is None else revision,
            "action": action, "reason": reason})


def test_explicit_action_reuses_readings_and_accounting_then_runs_only_locations(case):
    before = saved(case)
    ledger = case.ledger.read()
    response = post(case)
    assert response.status_code == 200, response.text
    queued = saved(case)
    assert (queued.run.id, queued.run.stage, queued.run.disposition) == (before.run.id, "pending", None)
    assert queued.run.dependencies["location_reassessment"] == {
        "attempt": 3, "fields": sorted(FAMILY), "protected": []}
    assert queued.run.completed_steps == [s for s in before.run.completed_steps if s != FIELD_RESEARCH]
    for key in ("profile", "profile_snapshot", "classification_selection", "attempts", "paid_calls",
            "usage", "regions", "observations", "transcripts", "evidence", "fields"):
        assert queued.run.model_dump(mode="json")[key] == before.run.model_dump(mode="json")[key]
    assert case.ledger.read() == ledger
    assert case.dispatcher.calls == 1
    event = queued.audit[-1]
    assert (event.action, event.reason) == ("reassess_locations", "Recheck the retained location hierarchy.")
    assert event.before == {"run_id": before.run.id, "attempt": 2,
        "fields": {key: before.run.fields[key].model_dump(mode="json") for key in FAMILY}}
    assert event.after == {"run_id": before.run.id, "attempt": 3, "fields": sorted(FAMILY)}

    resolver = Scripted()
    state = mounted(case, resolver)
    after = case.workflow.step(case.principal, case.specimen.id).run
    assert set(resolver.calls) == FAMILY
    assert after.id == before.run.id and after.attempts[FIELD_RESEARCH] == 3
    for step, count in before.run.attempts.items():
        if step != FIELD_RESEARCH:
            assert after.attempts[step] == count
    assert after.observations == before.run.observations and after.regions == before.run.regions
    assert after.paid_calls[:len(before.run.paid_calls)] == before.run.paid_calls
    assert len(after.paid_calls) == len(before.run.paid_calls) + 1
    assert {key: value for key, value in after.fields.items() if key not in FAMILY} == {
        key: value for key, value in before.run.fields.items() if key not in FAMILY}
    assert case.ledger.read()["reserved_total_micros"] == ledger["reserved_total_micros"] + state.meters[0].spent_micros
    assert case.ledger.read()["prior_unknown_spend_micros"] == 99_999


def test_ordinary_retry_does_not_request_supported_location_reassessment(case):
    before = saved(case)
    response = post(case, action="retry")
    assert response.status_code == 200, response.text
    assert "location_reassessment" not in saved(case).run.dependencies
    resolver = Scripted()
    mounted(case, resolver)
    after = case.workflow.step(case.principal, case.specimen.id).run
    assert "country" not in resolver.calls and "city" not in resolver.calls
    assert after.fields["country"] == before.run.fields["country"]
    assert after.fields["city"] == before.run.fields["city"]


def test_native_locked_location_is_not_queued_or_replaced(case):
    dependency = "human_review_field_locks"
    change(case, lambda run: run.dependencies.update({dependency: {"city": {"selection_id": "retained-human"}}}))
    before = saved(case)
    response = post(case)
    assert response.status_code == 200, response.text
    queued = saved(case)
    assert "city" not in queued.run.dependencies["location_reassessment"]["fields"]
    assert queued.run.dependencies[dependency] == before.run.dependencies[dependency]
    assert queued.run.fields["city"] == before.run.fields["city"]
    assert "city" not in queued.audit[-1].before["fields"]


def test_an_unproved_human_carry_is_refused_without_changing_anything(case):
    change(case, lambda run: run.dependencies.update({"preserved_human_fields": {"city": {}}}))
    before, ledger = saved(case), case.ledger.read()
    response = post(case)
    assert response.status_code == 422, response.text
    assert saved(case).model_dump() == before.model_dump()
    assert case.ledger.read() == ledger and case.dispatcher.calls == 0


def review_city(case, kind="field"):
    if kind == "field":
        after = {"state": "unknown", "reason": "A reviewer deliberately left the city unknown."}
    else:
        # A real retained candidate artifact, selected through the existing API.
        source = b"Synthetic gazetteer city choice"
        response_sha = hashlib.sha256(source).hexdigest()
        result = AuthorityResult(source_id="tgn", source_version="fixture-1", adapter_version="fixture-1",
            operation="lookup", status=LookupStatus.SUCCESS, literal="Illinois", evidence_ids=(),
            query_json='{"literal":"Illinois"}', input_sha256="0" * 64,
            retrieved_at=datetime.now(timezone.utc).isoformat(), raw_ref=case.blobs.put(source),
            response_sha256=response_sha, candidates=(AuthorityCandidate(identifier="tgn:reviewer-city",
                name="Illinois", source_version="fixture-1", relation="supports",
                reason="Synthetic retained city candidate", evidence_ids=()),))
        raw = result.model_dump_json().encode()
        metadata = {"tool_id": "geography_lookup", "field_key": "city",
            "blob_ref": case.blobs.put(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        change(case, lambda run: run.authority_results.update({"retained-city-choice": metadata}))
        after = {"tool_id": "geography_lookup", "identifier": "tgn:reviewer-city"}
    decide(case.client, case, "human-city-" + kind, kind,
        target_id="city", after=after, evidence_ids=[])
    return saved(case)


def prove_review(case, monkeypatch, original):
    """Stand in only for the trusted proof transport; event/version saves are real."""
    event = original.audit[-1]
    prior = case.repository.version_info(original.scope, original.id, original.version - 1)
    current = case.repository.version_info(original.scope, original.id, original.version)
    proof = ReviewDecisionProof(original.id, event, original.version - 1, original.version,
        prior["sha256"], current["sha256"], "synthetic-server-save-audit")
    monkeypatch.setattr(case.repository, "_review_proofs", lambda scope, specimen: ((proof,), {}), raising=False)


@pytest.mark.parametrize("kind", ["field", "authority_resolution"])
def test_a_proved_ordinary_human_city_choice_is_not_researched_or_replaced(case, monkeypatch, kind):
    reviewed = review_city(case, kind)
    prove_review(case, monkeypatch, reviewed)
    assert reviewed.audit[-1].action == "review_" + kind
    assert "city" not in reviewed.run.dependencies.get("preserved_human_fields", {})
    assert "city" not in reviewed.run.dependencies.get("human_review_field_locks", {})
    response = post(case)
    assert response.status_code == 200, response.text
    queued = saved(case)
    assert queued.run.dependencies["location_reassessment"]["protected"] == ["city"]
    assert "city" not in queued.run.dependencies["location_reassessment"]["fields"]
    assert "city" not in queued.audit[-1].before["fields"]
    resolver = Scripted()
    mounted(case, resolver)
    after = case.workflow.step(case.principal, case.specimen.id).run
    # The retained country is derived from this human-selected city, so its
    # existing ancestry remains a constraint rather than being detached.
    assert set(resolver.calls) == FAMILY - {"city", "country"}
    assert after.fields["city"] == reviewed.run.fields["city"]
    assert after.fields["country"] == reviewed.run.fields["country"]
    assert after.id == reviewed.run.id and after.profile == reviewed.run.profile


@pytest.mark.parametrize("failure", ["proof_unavailable", "current_value_changed"])
def test_unverifiable_human_history_cannot_queue_or_spend(case, monkeypatch, failure):
    reviewed = review_city(case)
    if failure == "current_value_changed":
        prove_review(case, monkeypatch, reviewed)
        change(case, lambda run: run.fields.update({"city": FieldValue(
            state=ValueState.SUPPORTED, literal="Different machine city", layer="settled")}))
    before, ledger, starts = saved(case), case.ledger.read(), case.dispatcher.calls
    response = post(case)
    assert response.status_code == 422, response.text
    assert saved(case).model_dump() == before.model_dump()
    assert case.ledger.read() == ledger and case.dispatcher.calls == starts


@pytest.mark.parametrize("kind", ["field", "authority_resolution"])
def test_a_human_choice_saved_while_pending_is_removed_from_the_paid_scope(case, kind):
    response = post(case)
    assert response.status_code == 200, response.text
    reviewed = review_city(case, kind)
    marker = reviewed.run.dependencies["location_reassessment"]
    assert marker == {"attempt": 3, "fields": sorted(FAMILY - {"city"}), "protected": ["city"]}
    assert reviewed.run.stage == "pending" and reviewed.run.attempts[FIELD_RESEARCH] == 2
    resolver = Scripted()
    mounted(case, resolver)
    after = case.workflow.step(case.principal, case.specimen.id).run
    assert set(resolver.calls) == FAMILY - {"city", "country"}
    assert after.fields["city"] == reviewed.run.fields["city"]
    assert after.fields["country"] == reviewed.run.fields["country"]


@pytest.mark.parametrize("restriction", ["lease", "unknown", "attempts", "pilot", "incomplete",
    "running", "cleared", "all_locations_settled", "only_nonlocation_unsettled"])
def test_ineligible_action_is_hidden_and_cannot_change_or_dispatch_the_run(case, restriction):
    def restrict(run):
        if restriction == "lease":
            run.lease_until = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        elif restriction == "unknown":
            run.blocker = "external_outcome_unknown"
        elif restriction == "attempts":
            run.attempts[FIELD_RESEARCH] = run.profile.execution.max_attempts
        elif restriction == "pilot":
            run.dependencies["evidence_pilot"] = {"retained": True}
        elif restriction == "incomplete":
            run.completed_steps.remove(FIELD_RESEARCH)
        elif restriction == "running":
            run.stage = "running"
        elif restriction == "cleared":
            run.disposition = Disposition.CLEARED
        else:
            for key in FAMILY:
                run.fields[key] = FieldValue(state=ValueState.SUPPORTED, literal="retained", layer="settled")
            if restriction == "only_nonlocation_unsettled":
                run.fields["taxon"] = FieldValue(state=ValueState.UNRESOLVED)
    change(case, restrict)
    before, ledger = saved(case), case.ledger.read()
    assert "reassess_locations" not in app_api.summary(before, "reviewer")["available_actions"]
    response = post(case)
    assert response.status_code == 409, response.text
    assert saved(case).model_dump() == before.model_dump()
    assert case.ledger.read() == ledger and case.dispatcher.calls == 0


def test_stale_revision_and_repeated_command_do_not_enqueue_another_pass(case):
    before = saved(case)
    response = post(case, revision=before.version - 1)
    assert response.status_code == 409, response.text
    assert saved(case).model_dump() == before.model_dump()
    assert case.dispatcher.calls == 0
    response = post(case)
    assert response.status_code == 200, response.text
    queued, ledger = saved(case), case.ledger.read()
    replay = post(case, revision=before.version)
    assert replay.status_code == 409, replay.text
    assert saved(case).model_dump() == queued.model_dump()
    assert case.ledger.read() == ledger and case.dispatcher.calls == 1


def test_viewer_cannot_request_location_reassessment(case):
    app = app_api.create_app(mode="emulator", repository=case.repository, blobs=case.blobs,
        adapters=SyntheticAdapters(case.blobs, "synthetic"), identity_verifier=lambda token, check: "viewer",
        memberships=lambda user: [{"organization_id": ORG, "collection_id": COLLECTION,
            "role": "viewer", "can_view_sensitive": False}])
    before, ledger = saved(case), case.ledger.read()
    assert "reassess_locations" not in app_api.summary(before, "viewer")["available_actions"]
    case.client = TestClient(app, raise_server_exceptions=False)
    response = post(case)
    assert response.status_code == 403, response.text
    assert saved(case).model_dump() == before.model_dump() and case.ledger.read() == ledger
    assert case.dispatcher.calls == 0


def test_reassessment_requires_an_audit_reason(case):
    before = saved(case)
    response = post(case, reason=" ")
    assert response.status_code == 422, response.text
    assert saved(case).model_dump() == before.model_dump()
    assert case.dispatcher.calls == 0
