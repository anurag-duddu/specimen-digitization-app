"""The owner's exact EBFC continuation consumes one attempt, never new limits."""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from specimen_digitization.application import api as app_api
from specimen_digitization.application.collection_profiles import published_registry
from specimen_digitization.application.domain import Scope
from specimen_digitization.application.history_restore import restored_specimen
from specimen_digitization.application.lane_allowance import LEDGER_KIND, ProgramLedger
from specimen_digitization.application.location_reassessment_authorization import (
    AUTHORIZATION_ID, COLLECTION_ID, ORGANIZATION_ID, RUN_ID, SPECIMEN_ID,
    authorization_for, authorized_queued_attempt,
)
from specimen_digitization.application.workflow import (
    FIELD_RESEARCH, OperationalBlock, SyntheticAdapters, can_reassess_locations, requeue_location_reassessment,
)
from specimen_digitization.field_research.contracts import FieldOutcome
from specimen_digitization.field_research.location_reassessment import FIELDS, KEY
from test_location_reassessment_api import case, change, saved  # noqa: F401
from test_step import Scripted, mounted


@pytest.fixture
def target(case, monkeypatch):
    record = saved(case).model_copy(deep=True)
    record.id, record.run.id = SPECIMEN_ID, RUN_ID
    record.scope = Scope(organization_id=ORGANIZATION_ID, collection_id=COLLECTION_ID)
    record.run.attempts[FIELD_RESEARCH] = 3
    record.run.profile.execution.approved_cost_limit_micros = 1_000_000
    record.run.profile.execution.program_ledger_collection = COLLECTION_ID
    record.run.classification_selection["collection_id"] = COLLECTION_ID
    case.principal.scope = record.scope
    case.specimen = case.repository.create(case.principal, record, "exact-target", "exact-target")
    case.ledger = ProgramLedger(case.repository, record.scope)
    case.repository.put_document(record.scope, LEDGER_KIND, case.ledger.ident,
        {"sensitive": False, "reserved_total_micros": 15_123_456,
            "prior_unknown_spend_micros": 99_999}, 0)
    monkeypatch.setattr(app_api, "application_registry",
        lambda synthetic: published_registry({COLLECTION_ID: "insects"}))
    case.client = client(case)
    return case


def client(case, role="reviewer"):
    return TestClient(app_api.create_app(mode="emulator", repository=case.repository,
        blobs=case.blobs, adapters=SyntheticAdapters(case.blobs, "synthetic"),
        identity_verifier=lambda token, check: "reviewer-1",
        memberships=lambda user: [{"organization_id": ORGANIZATION_ID,
            "collection_id": COLLECTION_ID, "role": role, "can_view_sensitive": False}]),
        raise_server_exceptions=False)


def post(case, **extra):
    current = saved(case)
    return case.client.post(f"/v1/organizations/{ORGANIZATION_ID}/runs/{current.run.id}/actions",
        headers={"Authorization": "Bearer reviewer", "Idempotency-Key": "fourth-location"},
        json={"expected_revision": current.version, "action": "reassess_locations",
            "reason": "One owner-authorized same-run location reassessment.", **extra})


def test_exact_target_offers_queues_audits_and_meters_one_fourth_attempt(target):
    before, ledger = saved(target), target.ledger.read()
    assert "reassess_locations" in app_api.summary(before, "reviewer")["available_actions"]
    assert not can_reassess_locations(before.run)  # Context-free callers get no exception.
    response = post(target)
    assert response.status_code == 200, response.text
    queued = saved(target)
    assert queued.run.dependencies[KEY] == {"attempt": 4, "fields": sorted(FIELDS),
        "protected": [], "authorization_id": AUTHORIZATION_ID}
    assert queued.audit[-1].after == {"run_id": RUN_ID, "attempt": 4,
        "fields": sorted(FIELDS), "authorization_id": AUTHORIZATION_ID}
    assert queued.audit[-1].before["attempt"] == 3
    for key in ("profile", "profile_snapshot", "usage", "paid_calls", "attempts", "observations",
            "regions", "transcripts", "fields", "evidence"):
        assert getattr(queued.run, key) == getattr(before.run, key)
    assert target.ledger.read() == ledger and target.dispatcher.calls == 1
    resolver = Scripted()
    state = mounted(target, resolver)
    after = target.workflow.step(target.principal, target.specimen.id)
    assert set(resolver.calls) == FIELDS
    assert after.run.attempts[FIELD_RESEARCH] == 4
    assert after.run.profile == before.run.profile
    assert after.run.observations == before.run.observations
    assert after.run.transcripts == before.run.transcripts
    assert after.run.paid_calls[:-1] == before.run.paid_calls
    paid = after.run.paid_calls[-1]
    assert paid["attempt"] == 4 and paid["reserved_micros"] == 1_000_000 - before.run.usage.reserved_cost_micros
    assert after.run.usage.reserved_cost_micros == before.run.usage.reserved_cost_micros + state.meters[0].spent_micros
    assert target.ledger.read()["reserved_total_micros"] == ledger["reserved_total_micros"] + state.meters[0].spent_micros
    assert not can_reassess_locations(after.run, specimen=after)
    assert "reassess_locations" not in app_api.summary(after, "reviewer")["available_actions"]


@pytest.mark.parametrize("wrong", ["organization", "collection", "specimen", "run", "max",
    "count2", "count4", "own_cap", "shared_cap", "ledger"])
def test_authorization_is_exact_and_does_not_repin(target, wrong):
    specimen = saved(target).model_copy(deep=True)
    run = specimen.run
    if wrong in {"organization", "collection"}:
        setattr(specimen.scope, wrong + "_id", "different")
    elif wrong == "specimen": specimen.id = "different"
    elif wrong == "run": run.id = "different"
    elif wrong == "max": run.profile.execution.max_attempts = 4
    elif wrong.startswith("count"): run.attempts[FIELD_RESEARCH] = int(wrong[-1])
    elif wrong == "own_cap": run.profile.execution.approved_cost_limit_micros = 1_000_001
    elif wrong == "shared_cap": run.profile.execution.program_allowance_micros = 16_000_001
    elif wrong == "ledger": run.profile.execution.program_ledger_collection = "different"
    before = specimen.model_dump()
    assert authorization_for(run, specimen) is None
    if wrong not in {"count2", "max"}:  # These may have ordinary pinned attempts left.
        assert not can_reassess_locations(run, specimen=specimen)
        assert requeue_location_reassessment(run, specimen=specimen) == []
    assert specimen.model_dump() == before


@pytest.mark.parametrize("extra", [{"max_attempts": 4}, {"authorization_id": AUTHORIZATION_ID},
    {"approved_cost_limit_micros": 2_000_000}, {"program_allowance_micros": 17_000_000}])
def test_request_cannot_supply_authorization_or_limits(target, extra):
    before, ledger = saved(target), target.ledger.read()
    response = post(target, **extra)
    assert response.status_code == 422, response.text
    assert saved(target) == before and target.ledger.read() == ledger
    assert target.dispatcher.calls == 0


def test_viewer_cannot_use_the_owner_authorization(target):
    target.client = client(target, "viewer")
    before = saved(target)
    assert "reassess_locations" not in app_api.summary(before, "viewer")["available_actions"]
    assert post(target).status_code == 403
    assert saved(target) == before and target.dispatcher.calls == 0


@pytest.mark.parametrize("bad", ["absent", "id", "attempt", "empty", "duplicate", "nonlocation",
    "protected", "all_locked", "pilot", "consumed"])
def test_exhausted_or_malformed_marker_never_reserves_or_sends(target, bad):
    before = saved(target)
    record = before.model_copy(deep=True)
    assert requeue_location_reassessment(record.run, specimen=record)
    marker = record.run.dependencies[KEY]
    if bad == "absent": record.run.dependencies.pop(KEY)
    elif bad == "id": marker["authorization_id"] = "caller-claimed"
    elif bad == "attempt": marker["attempt"] = 5
    elif bad == "empty": marker["fields"] = []
    elif bad == "duplicate": marker["fields"] = ["city", "city"]
    elif bad == "nonlocation": marker["fields"] = ["taxon"]
    elif bad == "protected": marker["protected"] = ["taxon"]
    elif bad == "all_locked": record.run.dependencies["human_review_field_locks"] = dict.fromkeys(FIELDS, {})
    elif bad == "pilot": record.run.dependencies["evidence_pilot"] = {}
    elif bad == "consumed":
        record.run.attempts[FIELD_RESEARCH] = 4
        marker["attempt"] = 5
    assert not authorized_queued_attempt(record)
    record.run.stage, record.run.disposition = "plan", None
    target.repository.save(target.principal, record, record.version, "invalid-marker", "invalid-marker")
    ledger, usage, calls = target.ledger.read(), record.run.usage.model_copy(deep=True), list(record.run.paid_calls)
    target.workflow.reserve_retained_cost = lambda *args: pytest.fail("Reserved before exhaustion guard")
    resolver = Scripted()
    state = mounted(target, resolver)
    if bad == "pilot":
        with pytest.raises(OperationalBlock, match="evidence_pilot_worker_required"):
            target.workflow.step(target.principal, record.id)
        done = saved(target)
    else:
        done = target.workflow.step(target.principal, record.id)
    assert not resolver.calls and not state.meters
    assert done.run.usage == usage and done.run.paid_calls == calls
    assert done.run.attempts == record.run.attempts
    assert target.ledger.read() == ledger
    for key in ("country", "city"):
        assert done.run.fields[key] == before.run.fields[key]


@pytest.mark.parametrize("failure", ["model_error", "source_unavailable"])
def test_fourth_failure_has_no_automatic_fifth_and_restore_cannot_replenish(target, failure):
    before = saved(target)
    assert post(target).status_code == 200
    queued = saved(target)
    async def broken(task, readings, tools):
        return FieldOutcome(task.key, None, failure=failure, model_calls=1)
    resolver = Scripted({key: broken for key in FIELDS})
    state = mounted(target, resolver)
    failed = target.workflow.step(target.principal, queued.id)
    assert failed.run.attempts[FIELD_RESEARCH] == 4 and failed.run.next_retry_at is None
    assert KEY not in failed.run.dependencies
    assert failed.run.fields == before.run.fields
    restored = restored_specimen(failed, queued)
    assert restored.run.attempts[FIELD_RESEARCH] == 4
    assert restored.run.usage == failed.run.usage
    assert restored.run.paid_calls == failed.run.paid_calls
    assert not authorized_queued_attempt(restored)
    assert not can_reassess_locations(restored.run, specimen=restored)
    # Even restoring the queued marker and manually retrying a failed handover
    # cannot replenish the consumed attempt or reserve a fresh call.
    restored.run.blocker = None
    restored.run.stage, restored.run.disposition = "plan", None
    target.repository.save(target.principal, restored, failed.version, "restore-for-retry", "restore-for-retry")
    resolver.calls.clear()
    usage, ledger = failed.run.usage.model_copy(deep=True), target.ledger.read()
    target.clock.now += timedelta(hours=1)
    done = target.workflow.step(target.principal, restored.id)
    assert not resolver.calls and len(state.meters) == 1
    assert done.run.attempts[FIELD_RESEARCH] == 4 and done.run.usage == usage
    assert target.ledger.read() == ledger


@pytest.mark.parametrize("restriction", ["lease", "blocker", "pilot", "incomplete", "running",
    "cleared", "settled", "human_locked"])
def test_owner_exception_preserves_existing_admission_conditions(target, restriction):
    from datetime import datetime, timezone
    from specimen_digitization.application.domain import Disposition, ValueState
    def restrict(run):
        if restriction == "lease": run.lease_until = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        elif restriction == "blocker": run.blocker = "external_outcome_unknown"
        elif restriction == "pilot": run.dependencies["evidence_pilot"] = {}
        elif restriction == "incomplete": run.completed_steps.remove(FIELD_RESEARCH)
        elif restriction == "running": run.stage = "running"
        elif restriction == "cleared": run.disposition = Disposition.CLEARED
        elif restriction == "settled":
            for key in FIELDS: run.fields[key].state = ValueState.SUPPORTED
        elif restriction == "human_locked": run.dependencies["human_review_field_locks"] = dict.fromkeys(FIELDS, {})
    change(target, restrict)
    before, ledger = saved(target), target.ledger.read()
    assert "reassess_locations" not in app_api.summary(before, "reviewer")["available_actions"]
    response = post(target)
    assert response.status_code == 409, response.text
    assert saved(target) == before and target.ledger.read() == ledger
    assert target.dispatcher.calls == 0


def test_new_human_protection_narrows_the_fourth_attempt(target):
    assert post(target).status_code == 200
    change(target, lambda run: run.dependencies.update({"human_review_field_locks": {"city": {"selection": "human"}}}))
    queued = saved(target)
    assert authorized_queued_attempt(queued)
    resolver = Scripted()
    mounted(target, resolver)
    done = target.workflow.step(target.principal, queued.id)
    assert set(resolver.calls) == FIELDS - {"city", "country"}
    assert done.run.fields["city"] == queued.run.fields["city"]
    assert done.run.fields["country"] == queued.run.fields["country"]
    assert done.run.attempts[FIELD_RESEARCH] == 4


@pytest.mark.parametrize("money", ["settings", "program"])
def test_exhaustion_keeps_money_priority_without_reserving(target, money):
    record = saved(target)
    record.run.completed_steps.remove(FIELD_RESEARCH)
    record.run.stage, record.run.disposition = "plan", None
    if money == "settings":
        record.run.profile.execution.approved_cost_limit_micros = None
    else:
        current = target.ledger.read()
        current["reserved_total_micros"] = 16_000_000
        target.repository.put_document(record.scope, LEDGER_KIND, target.ledger.ident, current, current["revision"])
    target.repository.save(target.principal, record, record.version, "money-limit", "money-limit")
    ledger = target.ledger.read()
    target.workflow.reserve_retained_cost = lambda *args: pytest.fail("Unexpected reservation")
    resolver = Scripted()
    state = mounted(target, resolver)
    done = target.workflow.step(target.principal, record.id)
    assert done.run.blocker == ("approved_cost_budget_unavailable" if money == "settings" else "program_allowance_exhausted")
    assert not resolver.calls and not state.meters
    assert done.run.attempts == record.run.attempts and done.run.usage == record.run.usage
    assert target.ledger.read() == ledger
