"""Synthetic successor ledgers verify an approved increase cannot erase history."""
from copy import deepcopy
import hashlib
import json

import pytest
import test_release_admission as fixtures
import test_release_cost_ledger_v2 as accounting

admission = fixtures.MODULE
APPROVAL = "3303d129e5fde28d828729cd5b034a7981968c5cbbbad882a05367a5c361df2a"  # pragma: allowlist secret (approval record digest)


def successor(monkeypatch):
    old, packet = accounting.fixture()
    raw = json.dumps(old, sort_keys=True)
    predecessor_sha = hashlib.sha256(raw.encode()).hexdigest()
    import specimen_digitization.release_budget as policy
    monkeypatch.setattr(policy, "PREDECESSOR_LEDGER_SHA256", predecessor_sha)
    ledger = deepcopy(old)
    ledger.update(version="release-cost-ledger/v3", predecessor={"sha256": predecessor_sha, "json": raw})
    packet["budget"].update(version="shared-release-reservations/v2", approval_sha256=APPROVAL,
                            total_limit_micros=12000000, daily_limit_micros=12000000)
    accounting.change_snapshot(ledger, lambda s: s.update(
        schema="coordinator-cumulative-release-budget/v2", limit_micros=12000000,
        approval_sha256=APPROVAL, predecessor_snapshot_sha256=old["accounting"]["snapshot_sha256"]))
    return ledger, packet


def test_approved_successor_preserves_every_original_liability(monkeypatch):
    ledger, packet = successor(monkeypatch)
    old = json.loads(ledger["predecessor"]["json"])
    admission.validate_budget(packet["budget"], packet["pilot"]["manifest_sha256"])
    admission.validate_cost_ledger(ledger, packet)
    assert ledger["entries"] == old["entries"]
    assert ledger["operator_entries"] == old["operator_entries"]
    assert ledger["prior_uncertainty"] == old["prior_uncertainty"]


@pytest.mark.parametrize("field", ["total_limit_micros", "daily_limit_micros"])
@pytest.mark.parametrize("value", [True, 12000000.0, "12000000", 0, -1, 12000001])
def test_approved_limits_remain_strict_and_bounded(monkeypatch, field, value):
    ledger, packet = successor(monkeypatch)
    packet["budget"][field] = value
    with pytest.raises(ValueError):
        admission.validate_budget(packet["budget"], packet["pilot"]["manifest_sha256"])


@pytest.mark.parametrize("version", ["release-cost-ledger/v1", "release-cost-ledger/v2"])
def test_new_authority_cannot_use_ledger_without_original_history(monkeypatch, version):
    ledger, packet = successor(monkeypatch)
    ledger["version"] = version
    ledger.pop("predecessor")
    with pytest.raises(ValueError):
        admission.validate_cost_ledger(ledger, packet)


@pytest.mark.parametrize("change", [
    lambda l: l["entries"].pop(),
    lambda l: l["entries"][0].update(amount_micros=0),
    lambda l: l["operator_entries"].clear(),
    lambda l: l["prior_uncertainty"].update(state="settled", amount_micros=0),
    lambda l: l["accounting"].update(accounting_start_unix=l["accounting"]["accounting_start_unix"]+1),
    lambda l: l["predecessor"].update(sha256="0"*64),
    lambda l: accounting.change_snapshot(l, lambda s: s["entries"].pop()),
    lambda l: accounting.change_snapshot(l, lambda s: s.update(schema="coordinator-cumulative-release-budget/v1")),
    lambda l: accounting.change_snapshot(l, lambda s: s.update(approval_sha256="0"*64)),
])
def test_successor_cannot_rewrite_history_or_reuse_old_snapshot(monkeypatch, change):
    ledger, packet = successor(monkeypatch)
    change(ledger)
    with pytest.raises(ValueError):
        admission.validate_cost_ledger(ledger, packet)


def test_legacy_budget_remains_five_million():
    packet = fixtures.packet()
    packet["budget"].update(total_limit_micros=5000001)
    with pytest.raises(ValueError):
        admission.validate_budget(packet["budget"], packet["pilot"]["manifest_sha256"])


def test_increase_requires_exact_new_approval(monkeypatch):
    _, packet = successor(monkeypatch)
    packet["budget"]["approval_sha256"] = "0"*64
    with pytest.raises(ValueError):
        admission.validate_budget(packet["budget"], packet["pilot"]["manifest_sha256"])


def test_approved_ledger_accepts_real_increase_without_reset(monkeypatch):
    ledger, packet = successor(monkeypatch)
    ledger["entries"].append({**ledger["entries"][0], "operation_id":"new-independent-history",
        "run_id":999, "state":"reserved", "amount_micros":6000000})
    admission.validate_cost_ledger(ledger, packet)
    packet["budget"]["daily_limit_micros"] = 7500000
    with pytest.raises(ValueError, match="daily.*budget exhausted"):
        admission.validate_cost_ledger(ledger, packet)


def test_approved_aggregate_carry_applies_to_every_day(monkeypatch):
    ledger, packet = successor(monkeypatch)
    ledger["entries"].append({**ledger["entries"][0], "operation_id":"new-prior-day",
        "run_id":999, "day_utc":"2026-09-07", "state":"reserved", "amount_micros":6000000})
    packet["budget"]["daily_limit_micros"] = 6500000
    with pytest.raises(ValueError, match="daily.*budget exhausted"):
        admission.validate_cost_ledger(ledger, packet)
