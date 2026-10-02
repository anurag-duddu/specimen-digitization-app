"""Actual authenticated route and canonical SQLite CAS/replay; no live claims."""
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from specimen_digitization.application.api import create_app, SYNTHETIC_ORG, SYNTHETIC_COLLECTION
from specimen_digitization.application.domain import Asset, AuditEvent, Disposition, FieldValue, Principal, Run, Scope, Specimen
from specimen_digitization.application.storage import SQLiteRepository, LocalBlobs, digest, work_available_at
from specimen_digitization.application.workflow import SyntheticAdapters


def fixture(tmp_path, *, initial_actual_cost=None, prices=None):
    scope = Scope(organization_id=SYNTHETIC_ORG,collection_id=SYNTHETIC_COLLECTION)
    principal = Principal(user_id="A",scope=scope,role="reviewer")
    repository = SQLiteRepository(tmp_path/"state.sqlite3")
    blobs = LocalBlobs(tmp_path/"blobs")
    specimen = Specimen(scope=scope,asset=Asset(sha256="a"*64,blob_ref="immutable-fixture",
        filename="fixture.png",media_type="image/png",size_bytes=1,width=1,height=1,uploader="A"),
        run=Run(stage="finalized",disposition=Disposition.REVIEW))
    specimen.run.usage.actual_cost_micros = initial_actual_cost
    if prices is not None:
        specimen.run.profile.execution.price_list = prices
        specimen.run.profile.execution.request_cost_reservation_micros = 900
    first = repository.create(principal,specimen,"create",digest({"create":1}))
    edited = first.model_copy(deep=True)
    edited.run.fields["country"] = FieldValue(literal="Kenya",parsed="Kenya")
    edited.run.human_approved = True
    edited.run.usage.tokens = 100
    edited.run.usage.reserved_tokens = 16000
    edited.run.usage.reserved_cost_micros = 123
    edited.run.usage.actual_cost_micros = 41
    edited.run.attempts = {"extract":2}
    edited.audit.append(AuditEvent(actor="A",action="review_field",reason="fixture review"))
    second = repository.save(principal,edited,1,"edit",digest({"edit":1}))
    roles = {"A":"reviewer","viewer":"viewer","operator":"operator"}
    http = TestClient(create_app(mode="emulator",repository=repository,blobs=blobs,
        adapters=SyntheticAdapters(blobs,""),identity_verifier=lambda bearer,appcheck:bearer,
        memberships=lambda user:[{"organization_id":scope.organization_id,"collection_id":scope.collection_id,
            "role":roles[user],"can_view_sensitive":True}]),raise_server_exceptions=False)
    return http,repository,principal,first,second


def request_body(base, source=1, reset=True):
    return {"expected_revision":base.version,"base_record_version_id":f"{base.run.id}:{base.version}",
        "source_revision":source,"reset_to_initial":reset,"reason":"Restore retained original"}


def submit(http,base,body=None,key="restore",actor="A"):
    return http.post(f"/v1/organizations/{SYNTHETIC_ORG}/specimens/{base.id}/history:restore",
        headers={"Authorization":"Bearer "+actor,"Idempotency-Key":key},json=body or request_body(base))


def test_restore_current_plus_one_preserves_history_accounting_and_reopens(tmp_path):
    http,repo,p,first,second = fixture(tmp_path)
    before = [repo.version(p.scope,second.id,n).model_dump(mode="json") for n in (1,2)]
    result = submit(http,second)
    assert result.status_code == 200,result.text
    restored = repo.get(p.scope,second.id)
    assert result.json()["revision"] == restored.version == second.version+1
    assert result.json()["specimen_id"] == second.id
    assert restored.run.fields == first.run.fields
    assert restored.asset == second.asset and restored.scope == second.scope
    assert restored.run.usage == second.run.usage and restored.run.attempts == second.run.attempts
    assert not restored.run.human_approved and restored.run.disposition == Disposition.REVIEW
    assert restored.run.history_restore_human_locks is True
    assert work_available_at(restored) is None
    assert restored.audit[:-1] == second.audit
    event = restored.audit[-1]
    assert (event.actor,event.action,event.base_revision,event.resulting_revision) == ("A","review_restore_version",2,3)
    assert event.after["source_revision"] == 1 and event.after["reset_to_initial"] is True
    assert [repo.version(p.scope,second.id,n).model_dump(mode="json") for n in (1,2)] == before
    restarted = SQLiteRepository(tmp_path/"state.sqlite3")
    assert restarted.get(p.scope,second.id) == restored
    workspace = http.get(f"/v1/organizations/{SYNTHETIC_ORG}/specimens/{second.id}/workspace",
        headers={"Authorization":"Bearer A"}).json()
    assert "restore_version" in workspace["available_actions"]


def test_same_request_replays_after_later_review_without_another_revision(tmp_path):
    http,repo,p,_,second = fixture(tmp_path)
    first = submit(http,second)
    assert first.status_code == 200,first.text
    saved = repo.get(p.scope,second.id)
    saved.audit.append(AuditEvent(actor="A",action="review_field",reason="later review"))
    repo.save(p,saved,3,"later",digest({"later":1}))
    replay = submit(http,second)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert repo.get(p.scope,second.id).version == 4
    assert submit(http,second,key="different").status_code == 409
    changed = request_body(second);changed["reason"] = "Different request"
    assert submit(http,second,changed).status_code == 409


@pytest.mark.parametrize("actor",["viewer","operator"])
def test_unreviewed_identity_cannot_restore_or_advertise_capability(tmp_path,actor):
    http,repo,p,_,second = fixture(tmp_path)
    assert submit(http,second,actor=actor).status_code == 403
    assert repo.get(p.scope,second.id).version == 2
    workspace = http.get(f"/v1/organizations/{SYNTHETIC_ORG}/specimens/{second.id}/workspace",
        headers={"Authorization":"Bearer "+actor}).json()
    assert "restore_version" not in workspace["available_actions"]


@pytest.mark.parametrize("change",[
    {"source_revision":3},{"source_revision":2,"reset_to_initial":True},
    {"source_revision":True},{"expected_revision":True},{"reset_to_initial":1},
    {"reason":" "},{"base_record_version_id":"wrong"},
])
def test_invalid_restore_never_commits(tmp_path,change):
    http,repo,p,_,second = fixture(tmp_path)
    body = request_body(second);body.update(change)
    response = submit(http,second,body)
    assert response.status_code in {409,422},response.text
    assert repo.get(p.scope,second.id).version == 2


def test_restore_retained_noninitial_revision_is_distinct_from_reset(tmp_path):
    http,repo,p,_,second = fixture(tmp_path)
    response = submit(http,second,request_body(second,source=2,reset=False))
    assert response.status_code == 200,response.text
    restored = repo.get(p.scope,second.id)
    assert restored.run.fields == second.run.fields and restored.version == 3
    assert restored.audit[-1].after["reset_to_initial"] is False


def test_compacted_prior_run_recovers_latest_immutable_accounting(tmp_path):
    http,repo,p,first,second = fixture(tmp_path)
    next_run = second.model_copy(deep=True)
    next_run.run = Run(stage="finalized",disposition=Disposition.REVIEW)
    next_run.run.reasons = ["retained-content:" + "x"*(129*1024)]
    next_run.previous_runs = [second.run.model_copy(deep=True)]
    # The retained accounting is in revision 2, not the original revision 1
    # and not an inline previous_runs cache in the new current run.
    current = repo.save(p,next_run,2,"new-run",digest({"new-run":1}))
    assert current.previous_runs == [] and current.history_through_revision == 2
    result = submit(http,current)
    assert result.status_code == 200,result.text
    restored = repo.get(p.scope,first.id)
    assert restored.version == 4 and restored.run.id == first.run.id
    assert restored.run.usage == second.run.usage
    assert restored.run.attempts == second.run.attempts
    assert not restored.run.human_approved and restored.run.history_restore_human_locks
    # Compaction intentionally retires the oversized inline run cache; its
    # exact immutable snapshot remains the accounting/content authority.
    assert repo.version(p.scope,first.id,current.version) == current
    assert repo.latest_run_version(p.scope,first.id,current.run.id,restored.version) == current
    assert restored.history_through_revision == current.version
    assert work_available_at(restored) is None
    assert repo.version(p.scope,first.id,1) == first
    assert repo.version(p.scope,first.id,2) == second


def test_restore_lock_marker_strict_and_legacy_snapshot_bytes_unchanged():
    legacy = Run()
    assert "history_restore_human_locks" not in legacy.model_dump(mode="json")
    with pytest.raises(ValueError):
        Run(history_restore_human_locks=1)
    assert Run(history_restore_human_locks=True).model_dump()["history_restore_human_locks"] is True


@pytest.mark.parametrize("condition",["unknown","lease","pilot"])
def test_effect_and_pilot_boundary_refuses_restore(tmp_path,condition):
    http,repo,p,_,second = fixture(tmp_path)
    changed = second.model_copy(deep=True)
    if condition == "unknown":
        changed.run.blocker = "external_outcome_unknown"
    elif condition == "lease":
        changed.run.lease_until = (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    else:
        changed.run.dependencies["evidence_pilot"] = "fixture"
    current = repo.save(p,changed,2,"boundary",digest({"condition":condition}))
    response = submit(http,current)
    assert response.status_code == 409,response.text
    assert repo.get(p.scope,second.id).version == 3


def test_latest_unknown_accounting_is_not_replaced_by_older_known_cost(tmp_path):
    http,repo,p,first,second = fixture(tmp_path,initial_actual_cost=17)
    latest = second.model_copy(deep=True)
    latest.run.usage.actual_cost_micros = None
    current = repo.save(p,latest,second.version,"unknown-latest",digest({"unknown-latest":1}))
    response = submit(http,current)
    assert response.status_code == 200,response.text
    restored = repo.get(p.scope,current.id)
    assert first.run.usage.actual_cost_micros == 17
    assert restored.run.usage == latest.run.usage
    assert restored.run.usage.actual_cost_micros is None
    assert restored.run.attempts == latest.run.attempts
    assert work_available_at(restored) is None


def test_inline_history_cache_cannot_override_latest_immutable_accounting(tmp_path):
    http,repo,p,first,second = fixture(tmp_path)
    later = second.model_copy(deep=True)
    later.run = Run(stage="finalized",disposition=Disposition.REVIEW)
    stale = second.run.model_copy(deep=True)
    stale.usage.actual_cost_micros = None
    stale.usage.reserved_cost_micros = 999
    stale.usage.reserved_tokens = 999999
    stale.attempts = {"extract":999}
    later.previous_runs = [stale]
    current = repo.save(p,later,second.version,"new-active-run",digest({"new-active-run":1}))
    assert current.previous_runs[0].usage != second.run.usage
    response = submit(http,current)
    assert response.status_code == 200,response.text
    restored = repo.get(p.scope,first.id)
    assert restored.run.usage == second.run.usage
    assert restored.run.attempts == second.run.attempts
    assert repo.version(p.scope,first.id,1) == first
    assert repo.version(p.scope,first.id,2) == second
    assert work_available_at(restored) is None


@pytest.mark.parametrize("historical_run", [False, True])
def test_restore_retains_reserved_calls_and_allowance_before_later_measured_usage(tmp_path, historical_run):
    from specimen_digitization.application.lane_costs import record_reserved, record_tool_usage

    prices = {
        "version": "restore-offline-prices-1", "as_of": "2026-10-01",
        "tools": {"geography_lookup": 7},
    }
    http, repo, principal, first, second = fixture(tmp_path, initial_actual_cost=17, prices=prices)
    latest = second.model_copy(deep=True)
    latest.run.program_allowance = {"reserved_total_micros": 900, "revision": 2}
    record_reserved(latest.run, "parse", "tool", outcome="completed", tool_id="geography_lookup")
    authoritative = repo.save(principal, latest, second.version, "reserved-call", digest({"reserved-call": 1}))
    current = authoritative
    if historical_run:
        next_run = authoritative.model_copy(deep=True)
        next_run.run = Run(stage="finalized", disposition=Disposition.REVIEW)
        next_run.run.reasons = ["retained-content:" + "x" * (129 * 1024)]
        next_run.previous_runs = [authoritative.run.model_copy(deep=True)]
        current = repo.save(principal, next_run, authoritative.version, "next-run", digest({"next-run": 1}))
        assert current.previous_runs == []
    response = submit(http, current)
    assert response.status_code == 200, response.text
    restored = repo.get(principal.scope, first.id)
    assert restored.run.paid_calls == authoritative.run.paid_calls
    assert restored.run.program_allowance == authoritative.run.program_allowance
    assert restored.run.usage.actual_cost_micros is None
    # The next measured receipt must leave the earlier unmeasured liability held.
    record_tool_usage(restored.run, "parse", "geography_lookup", requests=1)
    assert restored.run.paid_calls[-1]["cost_micros"] == 7
    assert restored.run.paid_calls[0]["cost_basis"] == "reserved"
    assert restored.run.usage.actual_cost_micros is None
    saved = repo.save(principal, restored, restored.version, "later-known-call", digest({"later-known-call": 1}))
    assert saved.run.usage.actual_cost_micros is None
    assert saved.run.program_allowance == authoritative.run.program_allowance
    assert repo.version(principal.scope, first.id, authoritative.version) == authoritative
    assert repo.version(principal.scope, first.id, 1) == first


def test_restore_copies_nested_authoritative_accounting_without_aliases(tmp_path):
    from specimen_digitization.application.history_restore import restored_specimen

    _, _, _, first, latest = fixture(tmp_path)
    latest.run.paid_calls = [{"cost_basis": "reserved", "usage": {"observed": None}}]
    latest.run.program_allowance = {"position": {"reserved_total_micros": 900}}
    restored = restored_specimen(latest, first)
    assert restored.run.paid_calls == latest.run.paid_calls
    assert restored.run.program_allowance == latest.run.program_allowance
    restored.run.paid_calls[0]["usage"]["observed"] = 1
    restored.run.program_allowance["position"]["reserved_total_micros"] = 0
    assert latest.run.paid_calls[0]["usage"]["observed"] is None
    assert latest.run.program_allowance["position"]["reserved_total_micros"] == 900
