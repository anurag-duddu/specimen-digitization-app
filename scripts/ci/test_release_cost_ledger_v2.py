"""Generated accounting fixtures only; no private ledger copies or cloud effects."""

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

import pytest

import test_release_admission as fixtures

admission = fixtures.MODULE


def sha(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def fixture():
    packet = fixtures.packet()
    task = str(uuid4())
    packet["independent_review"]["coordinator_session"] = task
    start = fixtures.NOW - 3600
    day = datetime.fromtimestamp(start, timezone.utc).date().isoformat()
    snapshot = {
        "schema": "coordinator-cumulative-release-budget/v1",
        "currency": "USD",
        "scope": packet["budget"]["scope"],
        "accounting_start_unix": start,
        "resets_allowed": False,
        "limit_micros": 5000000,
        "coordinator_task": task,
        "frozen_metadata_sha256": sha("generated metadata"),
        "prior_evidence": {
            "path": "generated-prior-evidence.json",
            "sha256": sha("generated prior evidence"),
        },
        "entries": [
            {
                "operation_id": "generated-prior-uncertainty",
                "owner_kind": "coordinator",
                "owner_task": task,
                "state": "unknown",
                "held_micros": 1000000,
                "coverage": "Generated unknown prior liability",
            },
            {
                "operation_id": "generated-metering",
                "owner_kind": "coordinator",
                "owner_task": task,
                "category": "telemetry",
                "state": "reserved",
                "held_micros": 1000,
                "plan_sha256": sha("generated bounded operator plan"),
            },
        ],
        "total_held_micros": 1001000,
        "actual_prior_total_micros": None,
        "available_for_further_workloads_micros": None,
        "authorized_next_operation": "generated-metering only",
        "production_admission_compatible": False,
        "notes": ["Generated fixture, not actual charges"],
        "created_at": datetime.fromtimestamp(start + 1, timezone.utc).isoformat(),
    }
    raw = json.dumps(snapshot, indent=2)
    ledger = fixtures.ledger(packet)
    ledger.update(
        version="release-cost-ledger/v2",
        accounting={
            "accounting_start_unix": start,
            "coordinator_task": task,
            "manifest_sha256": packet["pilot"]["manifest_sha256"],
            "snapshot_sha256": sha(raw),
            "snapshot_json": raw,
        },
        operator_entries=[
            {
                "operation_id": "generated-metering",
                "task_id": task,
                "category": "telemetry",
                "state": "reserved",
                "amount_micros": 1000,
                "day_utc": day,
                "evidence_sha256": snapshot["entries"][1]["plan_sha256"],
            }
        ],
        prior_uncertainty={
            "operation_id": "generated-prior-uncertainty",
            "task_id": task,
            "state": "unknown",
            "amount_micros": 1000000,
            "day_utc": day,
            "evidence_sha256": snapshot["prior_evidence"]["sha256"],
        },
    )
    return ledger, packet


def test_v1_workflow_ledger_remains_compatible():
    p = fixtures.packet()
    admission.validate_cost_ledger(fixtures.ledger(p), p)


def test_v2_represents_operator_and_prior_holds_without_fictitious_workflow_ids():
    ledger, packet = fixture()
    original_workflow_entries = deepcopy(ledger["entries"])
    admission.validate_cost_ledger(ledger, packet)
    assert ledger["entries"] == original_workflow_entries
    assert all(
        "run_id" not in entry and "plane" not in entry
        for entry in ledger["operator_entries"]
    )
    assert ledger["prior_uncertainty"]["state"] == "unknown"
    assert (
        json.loads(ledger["accounting"]["snapshot_json"])[
            "production_admission_compatible"
        ]
        is False
    )


@pytest.mark.parametrize("owner", ["operator_entries", "prior_uncertainty"])
@pytest.mark.parametrize("amount", [True, False, 1.0, 1000000.0, "1000000", -1, None])
def test_new_liabilities_require_strict_integer_costs(owner, amount):
    ledger, packet = fixture()
    entry = ledger[owner][0] if owner == "operator_entries" else ledger[owner]
    entry["amount_micros"] = amount
    with pytest.raises(ValueError):
        admission.validate_cost_ledger(ledger, packet)


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value["operator_entries"].clear(),
        lambda value: value.update(prior_uncertainty=None),
        lambda value: value["operator_entries"][0].update(amount_micros=0),
        lambda value: value["prior_uncertainty"].update(amount_micros=0),
        lambda value: value["prior_uncertainty"].update(amount_micros=999999),
        lambda value: value["operator_entries"][0].update(state="settled"),
        lambda value: value["prior_uncertainty"].update(state="settled"),
        lambda value: value["operator_entries"][0].update(category="provider"),
        lambda value: value["operator_entries"][0].update(task_id="not-a-uuid"),
        lambda value: value["operator_entries"][0].update(task_id=str(uuid4())),
        lambda value: value["operator_entries"][0].update(evidence_sha256="0" * 64),
        lambda value: value["prior_uncertainty"].update(evidence_sha256="0" * 64),
        lambda value: value["operator_entries"][0].update(day_utc="2026-09-07"),
        lambda value: value["prior_uncertainty"].update(day_utc="2026-09-07"),
        lambda value: value["accounting"].update(accounting_start_unix=fixtures.NOW),
        lambda value: value["accounting"].update(manifest_sha256="0" * 64),
        lambda value: value["accounting"].update(coordinator_task=str(uuid4())),
        lambda value: value["accounting"].update(snapshot_sha256="0" * 64),
        lambda value: value["accounting"].update(
            snapshot_json=value["accounting"]["snapshot_json"] + " "
        ),
        lambda value: value["operator_entries"].append(
            deepcopy(value["operator_entries"][0])
        ),
        lambda value: value["operator_entries"][0].update(
            operation_id=value["entries"][0]["operation_id"]
        ),
        lambda value: value["prior_uncertainty"].update(
            operation_id=value["operator_entries"][0]["operation_id"]
        ),
        lambda value: value["operator_entries"][0].update(run_id=456, plane="runtime"),
        lambda value: value["prior_uncertainty"].update(unrecognized=True),
        lambda value: value["accounting"].update(resets_allowed=True),
    ],
)
def test_pinned_accounting_cannot_omit_reset_reclassify_or_duplicate_liabilities(
    change,
):
    ledger, packet = fixture()
    change(ledger)
    with pytest.raises(ValueError):
        admission.validate_cost_ledger(ledger, packet)


@pytest.mark.parametrize("limit", ["total_limit_micros", "daily_limit_micros"])
def test_operator_and_prior_holds_count_against_both_caps(limit):
    ledger, packet = fixture()
    # Existing workflow reservations alone fit; the cumulative non-workflow holds do not.
    packet["budget"][limit] = 2000000
    with pytest.raises(ValueError, match="budget exhausted"):
        admission.validate_cost_ledger(ledger, packet)


def test_operator_holds_cannot_satisfy_a_workflow_category():
    ledger, packet = fixture()
    ledger["entries"] = [
        entry for entry in ledger["entries"] if entry["category"] != "telemetry"
    ]
    ledger["operator_entries"][0]["amount_micros"] = 100000
    with pytest.raises(ValueError, match="exact existing reservations"):
        admission.validate_cost_ledger(ledger, packet)


def test_operator_entries_do_not_hide_workflow_replay():
    ledger, packet = fixture()
    ledger["entries"][0]["state"] = "unknown"
    with pytest.raises(ValueError, match="replay"):
        admission.validate_cost_ledger(ledger, packet)


def change_snapshot(ledger, transform):
    snapshot = json.loads(ledger["accounting"]["snapshot_json"])
    transform(snapshot)
    raw = json.dumps(snapshot, indent=2)
    ledger["accounting"].update(snapshot_json=raw, snapshot_sha256=sha(raw))


def test_separate_operator_task_is_preserved_from_coordinator_snapshot():
    ledger, packet = fixture()
    operator = str(uuid4())
    change_snapshot(
        ledger,
        lambda value: value["entries"][1].update(
            owner_kind="operator", owner_task=operator
        ),
    )
    ledger["operator_entries"][0]["task_id"] = operator
    admission.validate_cost_ledger(ledger, packet)


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(resets_allowed=True),
        lambda value: value.update(total_held_micros=1000),
        lambda value: value.update(actual_prior_total_micros=1000000),
        lambda value: value.update(available_for_further_workloads_micros=3999000),
        lambda value: value.update(production_admission_compatible="true"),
        lambda value: value.update(accounting_start_unix=True),
        lambda value: value.update(limit_micros=5000000.0),
        lambda value: value.update(currency="EUR"),
        lambda value: value.update(unrecognized=True),
        lambda value: value["entries"][0].update(state="settled"),
        lambda value: value["entries"][0].update(held_micros=True),
        lambda value: value["entries"][1].update(held_micros=1000.0),
        lambda value: value["entries"][1].update(owner_kind="unrecognized"),
        lambda value: value["entries"][1].update(category="unrecognized"),
        lambda value: value["entries"].append(deepcopy(value["entries"][0])),
        lambda value: value["entries"].pop(0),
    ],
)
def test_snapshot_schema_and_original_liabilities_fail_closed(change):
    ledger, packet = fixture()
    change_snapshot(ledger, change)
    with pytest.raises(ValueError):
        admission.validate_cost_ledger(ledger, packet)


def test_unknown_aggregate_cannot_be_moved_to_another_day_to_evade_daily_cap():
    ledger, packet = fixture()
    for entry in ledger["entries"]:
        entry["day_utc"] = "2026-09-07"
    packet["budget"]["daily_limit_micros"] = 2000000
    with pytest.raises(ValueError, match="daily.*budget exhausted"):
        admission.validate_cost_ledger(ledger, packet)


@pytest.mark.parametrize("tamper", [None, "omit", "reduce", "downgrade"])
def test_real_admission_checks_exact_pinned_v2_bytes_without_promoting_unknown(
    tmp_path, monkeypatch, tamper
):
    ledger, packet = fixture()
    encode = lambda value: json.dumps(value, sort_keys=True)
    raw = encode(ledger)
    evidence = {
        "authorization": '{"fixture":"authorization"}',
        "independent_review": '{"fixture":"independent-review"}',
        "shared_budget_ledger": raw,
    }
    packet["authorization_sha256"] = sha(evidence["authorization"])
    packet["independent_review"]["report_sha256"] = sha(evidence["independent_review"])
    packet["budget"]["ledger_sha256"] = sha(raw)
    packet["evidence"] = {key: sha(value) for key, value in evidence.items()}
    plan = '{"fixture":"no-effects-plan"}'
    packet["plan_sha256"] = sha(plan)
    packet_raw = encode(packet)
    (tmp_path / "evidence").mkdir(mode=0o700)
    for path, value in {
        tmp_path / "packet.json": packet_raw,
        tmp_path / "plan.json": plan,
        **{
            tmp_path / "evidence" / (key + ".json"): value
            for key, value in evidence.items()
        },
    }.items():
        path.write_text(value)
        path.chmod(0o600)
    env = fixtures.environment(packet)
    env.update(
        RELEASE_PACKET_SHA256=sha(packet_raw), RELEASE_BUDGET_LEDGER_SHA256=sha(raw)
    )
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(admission, "github_snapshot", lambda _: fixtures.snapshot())
    if tamper:
        if tamper == "omit":
            ledger["operator_entries"].clear()
        elif tamper == "reduce":
            ledger["prior_uncertainty"]["amount_micros"] = 0
        else:
            ledger = fixtures.ledger(packet)
        (tmp_path / "evidence" / "shared_budget_ledger.json").write_text(encode(ledger))
        with pytest.raises(ValueError, match="evidence digest mismatch"):
            admission.admit(tmp_path / "packet.json", "runtime", now=fixtures.NOW)
    else:
        assert (
            admission.admit(tmp_path / "packet.json", "runtime", now=fixtures.NOW)
            == packet
        )
        retained = json.loads(
            (tmp_path / "evidence" / "shared_budget_ledger.json").read_text()
        )
        assert retained["prior_uncertainty"]["state"] == "unknown"
        assert (
            json.loads(retained["accounting"]["snapshot_json"])[
                "production_admission_compatible"
            ]
            is False
        )
