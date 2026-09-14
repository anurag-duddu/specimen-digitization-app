"""Approved scope selection must never reinterpret an old review receipt."""
from copy import deepcopy

import pytest
import acceptance
import human_review
from specimen_digitization.release_budget import APPROVAL_SHA256
from test_acceptance import budget, MANIFEST_SHA, CANDIDATE, manifest


def test_legacy_scope_bytes_remain_frozen():
    assert human_review.APPROVED_SCOPE_SHA256 == "14f6b1140f7d45e46c022e4a1c4f60cd775bafbef73ca363a677f278e0eafd1a"  # pragma: allowlist secret (scope digest)


def test_new_scope_selects_matching_skeleton_and_preserves_cohort():
    scope = deepcopy(human_review.APPROVED_SCOPE_V2)
    human_review.validate_scope(scope)
    report = human_review.skeleton(CANDIDATE, MANIFEST_SHA, scope)
    assert report["scope_sha256"] == human_review.APPROVED_SCOPE_V2_SHA256
    assert scope["specimen_count"] == 10
    assert scope["approval_sha256"] == APPROVAL_SHA256
    assert scope["predecessor_scope_sha256"] == human_review.APPROVED_SCOPE_SHA256


@pytest.mark.parametrize("key,value", [("total_limit_micros",12000001),("total_limit_micros",12000000.0),
    ("approval_sha256","0"*64),("specimen_count",11),("initial_admin_sensitive_access",True)])
def test_new_scope_cannot_expand_or_forge_approval(key, value):
    scope = deepcopy(human_review.APPROVED_SCOPE_V2)
    scope[key] = value
    with pytest.raises(acceptance.InvalidEvidence):
        human_review.validate_scope(scope)


def test_new_budget_requires_explicit_matching_scope(tmp_path):
    value = budget(tmp_path)
    value.update(schema_version="cohort-budget/v2", approval_sha256=APPROVAL_SHA256,
                 total_limit_microusd=12000000,daily_limit_microusd=12000000,release_ledger={})
    with pytest.raises(ValueError):
        acceptance.cohort_budget(value,MANIFEST_SHA,tmp_path)


def test_new_scope_cannot_reuse_legacy_budget_report(tmp_path):
    scope = deepcopy(human_review.APPROVED_SCOPE_V2)
    report = human_review.skeleton(CANDIDATE,MANIFEST_SHA,scope)
    report["budget"] = budget(tmp_path)
    with pytest.raises(acceptance.InvalidEvidence):
        human_review.evaluate(manifest(),MANIFEST_SHA,report,tmp_path,CANDIDATE,scope)


def projected_budget(tmp_path, monkeypatch):
    import json, hashlib
    import specimen_digitization.release_budget as policy
    b = budget(tmp_path)
    def digest(raw): return hashlib.sha256(raw.encode()).hexdigest()
    from datetime import datetime, timezone
    start = int(datetime(2026,9,7,tzinfo=timezone.utc).timestamp())
    owner = "11111111-1111-4111-8111-111111111111"
    prior_entry = {"operation_id":"prior-unknown", "owner_kind":"coordinator",
                   "owner_task":owner,"state":"unknown","held_micros":1000000,"coverage":"synthetic uncertainty"}
    snapshot = dict(schema="coordinator-cumulative-release-budget/v1", limit_micros=5000000,
        currency="USD", scope=b["scope"], accounting_start_unix=start, resets_allowed=False,
        coordinator_task=owner, frozen_metadata_sha256="a"*64,
        prior_evidence={"path":"synthetic","sha256":"b"*64}, actual_prior_total_micros=None,
        available_for_further_workloads_micros=None,entries=[prior_entry],
        total_held_micros=1000000,authorized_next_operation="synthetic only",
        production_admission_compatible=False,notes=["synthetic"],created_at="2026-09-07T00:00:00+00:00")
    raw_snapshot=json.dumps(snapshot)
    prior=dict(version="release-cost-ledger/v2",currency="USD",manifest_sha256=MANIFEST_SHA,
        scope=b["scope"],entries=[{**{k:v for k,v in r.items() if k!='amount_microusd'},
        "amount_micros":r['amount_microusd']} for r in b['entries']],operator_entries=[],
        prior_uncertainty={"operation_id":"prior-unknown","state":"unknown","amount_micros":1000000,
        "day_utc":"2026-09-07","task_id":owner,"evidence_sha256":"b"*64},
        accounting={"accounting_start_unix":start,"coordinator_task":owner,
        "manifest_sha256":MANIFEST_SHA,"snapshot_json":raw_snapshot,"snapshot_sha256":digest(raw_snapshot)})
    raw_prior=json.dumps(prior)
    monkeypatch.setattr(policy,'PREDECESSOR_LEDGER_SHA256',digest(raw_prior))
    ledger=deepcopy(prior)
    ledger.update(version="release-cost-ledger/v3",predecessor={"sha256":digest(raw_prior),"json":raw_prior})
    snapshot.update(schema="coordinator-cumulative-release-budget/v2",limit_micros=12000000,
        approval_sha256=APPROVAL_SHA256,predecessor_snapshot_sha256=digest(raw_snapshot))
    new_snapshot=json.dumps(snapshot)
    ledger['accounting'].update(snapshot_json=new_snapshot,snapshot_sha256=digest(new_snapshot))
    new_row={"operation_id":"new-provider","category":"provider","state":"reserved",
        "amount_micros":6000000,"day_utc":"2026-09-09"}
    ledger['entries'].append(new_row)
    b['entries'].append({k:v for k,v in new_row.items() if k!='amount_micros'}|{'amount_microusd':6000000})
    raw=json.dumps(ledger)
    p=tmp_path/'release-ledger.json';p.write_text(raw)
    b.update(schema_version='cohort-budget/v2',approval_sha256=APPROVAL_SHA256,
        total_limit_microusd=12000000,daily_limit_microusd=12000000,
        release_ledger={'path':p.name,'sha256':digest(raw)})
    return b


def test_projection_counts_prior_once_and_all_new_rows(tmp_path,monkeypatch):
    b=projected_budget(tmp_path,monkeypatch)
    assert acceptance.cohort_budget(b,MANIFEST_SHA,tmp_path,approval_sha256=APPROVAL_SHA256)==10000000


def test_projection_carries_prior_against_every_day(tmp_path,monkeypatch):
    b=projected_budget(tmp_path,monkeypatch)
    b['daily_limit_microusd']=6500000
    with pytest.raises(acceptance.InvalidEvidence,match='Daily budget'):
        acceptance.cohort_budget(b,MANIFEST_SHA,tmp_path,approval_sha256=APPROVAL_SHA256)


def test_projection_cannot_omit_a_charged_row(tmp_path,monkeypatch):
    b=projected_budget(tmp_path,monkeypatch)
    b['entries'].pop()
    with pytest.raises(acceptance.InvalidEvidence,match='omitted or changed'):
        acceptance.cohort_budget(b,MANIFEST_SHA,tmp_path,approval_sha256=APPROVAL_SHA256)
