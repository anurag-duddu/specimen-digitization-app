"""Independent offline release-admission regression probes; no remote calls."""

import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import release_admission as admission
import test_release_admission as fixtures


def encode(value):
    return json.dumps(value, sort_keys=True).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def test_accounting_uses_exact_verified_ledger_bytes(tmp_path, monkeypatch):
    packet = fixtures.packet()
    original_ledger = fixtures.ledger(packet)
    original_ledger["entries"].append({
        "operation_id": "prior-pending-data-cost", "plane": "data", "run_id": 100,
        "run_attempt": 1, "category": "restore", "state": "unknown",
        "amount_micros": 4500000, "day_utc": "2026-09-07",
    })
    approved_ledger = encode(original_ledger)
    replacement_ledger = encode(fixtures.ledger(packet))
    evidence = {
        "authorization": b'{"authorization":"synthetic-approved"}',
        "independent_review": b'{"review":"synthetic-pass"}',
        "shared_budget_ledger": approved_ledger,
    }
    packet["authorization_sha256"] = digest(evidence["authorization"])
    packet["independent_review"]["report_sha256"] = digest(evidence["independent_review"])
    packet["budget"]["ledger_sha256"] = digest(approved_ledger)
    packet["evidence"] = {name: digest(value) for name, value in evidence.items()}
    plan = b'{"synthetic_plan":true}'
    packet["plan_sha256"] = digest(plan)
    evidence_path = tmp_path / "evidence"
    evidence_path.mkdir(mode=0o700)
    packet_raw = encode(packet)
    file_bytes = {
        tmp_path / "packet.json": packet_raw,
        tmp_path / "plan.json": plan,
        **{evidence_path / (name + ".json"): value for name, value in evidence.items()},
    }
    for path, value in file_bytes.items():
        path.write_bytes(value)
        path.chmod(0o600)
    environment = fixtures.environment(packet)
    environment["RELEASE_PACKET_SHA256"] = digest(packet_raw)
    environment["RELEASE_BUDGET_LEDGER_SHA256"] = digest(approved_ledger)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(admission, "github_snapshot", lambda _: fixtures.snapshot())
    original_reader = admission.private_bytes
    ledger_reads = []

    def swap_after_read(path, limit=1048576):
        result = original_reader(path, limit)
        if path.name == "shared_budget_ledger.json":
            ledger_reads.append(digest(result))
            if len(ledger_reads) == 1:
                path.write_bytes(replacement_ledger)
        return result

    monkeypatch.setattr(admission, "private_bytes", swap_after_read)
    with pytest.raises(ValueError, match="cumulative"):
        admission.admit(tmp_path / "packet.json", "runtime", now=fixtures.NOW)
    assert ledger_reads == [digest(approved_ledger)]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_strict_json_rejects_nonstandard_nonfinite_literals(value):
    with pytest.raises(ValueError):
        admission.strict_json('{"value":' + value + '}')
