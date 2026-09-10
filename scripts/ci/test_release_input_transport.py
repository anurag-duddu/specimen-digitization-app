"""Synthetic exact-byte transport probes; no private ledgers or native effects."""

import base64
from copy import deepcopy
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import random
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
M = importlib.import_module("release_admission")
RAW_LIMIT = 1048576
SECRET_LIMIT = 48000


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def raw_bundle():
    return json.dumps(
        {
            "packet": '{ "synthetic" : true }\n',
            "plan": '{ "preserve" : "whitespace" }\n',
            "evidence": {
                name: '  { "synthetic" : true }\n'
                for name in (
                    "independent_review",
                    "authorization",
                    "shared_budget_ledger",
                )
            },
        },
        ensure_ascii=False,
    ).encode()


def env(raw, wire=None):
    return {
        "RELEASE_INPUTS_B64": base64.b64encode(raw).decode() if wire is None else wire,
        "RELEASE_INPUTS_SHA256": sha(raw),
    }


def compressed(raw):
    return base64.b64encode(gzip.compress(raw, mtime=0)).decode()


def test_legacy_raw_bundle_preserves_exact_evidence_and_private_permissions(tmp_path):
    raw = raw_bundle()
    destination = tmp_path / "inputs"
    M.materialize_inputs(destination, env(raw))
    bundle = json.loads(raw)
    for name, original in {
        "packet.json": bundle["packet"],
        "plan.json": bundle["plan"],
        **{f"evidence/{k}.json": v for k, v in bundle["evidence"].items()},
    }.items():
        assert (destination / name).read_bytes() == original.encode()
        assert (destination / name).stat().st_mode & 0o777 == 0o600
    assert destination.stat().st_mode & 0o777 == 0o700


def test_single_gzip_stream_restores_the_original_bundle_hash_and_bytes(tmp_path):
    raw = raw_bundle() + b" " * 60000
    wire = compressed(raw)
    assert len(wire) < SECRET_LIMIT < len(base64.b64encode(raw))
    assert M.decode_release_inputs(wire) == raw
    destination = tmp_path / "inputs"
    M.materialize_inputs(destination, env(raw, wire))
    assert (destination / "plan.json").read_bytes() == json.loads(raw)["plan"].encode()


def test_encoder_is_deterministic_uses_legacy_when_small_and_gzip_when_needed():
    small = raw_bundle()
    large = small + b" " * 60000
    assert M.encode_release_inputs(small) == base64.b64encode(small).decode()
    first = M.encode_release_inputs(large)
    assert first == M.encode_release_inputs(large) and len(first) <= SECRET_LIMIT
    stream = base64.b64decode(first)
    assert stream[:3] == b"\x1f\x8b\x08" and stream[3] == 0
    assert stream[4:8] == b"\x00" * 4 and stream[9] == 255
    assert M.decode_release_inputs(first) == large


@pytest.mark.parametrize("size", [RAW_LIMIT - 1, RAW_LIMIT])
def test_compressed_raw_byte_bound_accepts_exact_complete_limit(tmp_path, size):
    raw = raw_bundle()
    raw += b" " * (size - len(raw))
    wire = M.encode_release_inputs(raw)
    assert M.decode_release_inputs(wire) == raw
    M.materialize_inputs(tmp_path / "inputs", env(raw, wire))


def test_oversized_expansion_never_uses_unbounded_decompress_or_flush(
    tmp_path, monkeypatch
):
    raw = raw_bundle() + b" " * (RAW_LIMIT * 16)
    wire = compressed(raw)
    import zlib

    original = zlib.decompressobj
    limits = []

    class Limited:
        def __init__(self, *a, **kw):
            self.inner = original(*a, **kw)

        def decompress(self, data, max_length=0):
            limits.append(max_length)
            assert 0 < max_length <= RAW_LIMIT + 1
            return self.inner.decompress(data, max_length)

        def flush(self, *_, **__):
            pytest.fail("decompression flush has no hard output ceiling")

        def __getattr__(self, name):
            return getattr(self.inner, name)

    monkeypatch.setattr(zlib, "decompressobj", Limited)
    destination = tmp_path / "inputs"
    with pytest.raises(ValueError):
        M.materialize_inputs(destination, env(raw, wire))
    assert limits == [RAW_LIMIT + 1] and not destination.exists()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data + b" ",
        lambda data: data + b"\x00",
        lambda data: data + b"unexpected",
        lambda data: data + gzip.compress(b"another member", mtime=0),
        lambda data: data[:-1],
        lambda data: data[:-4],
        lambda data: data[:-8],
        lambda data: data[:10],
        lambda data: data[:-8] + bytes([data[-8] ^ 1]) + data[-7:],
        lambda data: data[:-4] + bytes([data[-4] ^ 1]) + data[-3:],
        lambda data: data[:2] + b"\x09" + data[3:],
    ],
)
def test_bad_gzip_crc_size_truncation_trailing_and_multiple_members_leave_no_files(
    tmp_path, mutate
):
    raw = raw_bundle()
    wire = base64.b64encode(mutate(gzip.compress(raw, mtime=0))).decode()
    destination = tmp_path / "inputs"
    with pytest.raises(ValueError):
        M.materialize_inputs(destination, env(raw, wire))
    assert not destination.exists()


@pytest.mark.parametrize(
    "wire",
    [
        "",
        "!not-base64",
        "é",
        "AA==\n",
        "A" * (SECRET_LIMIT + 1),
        base64.b64encode(b"gzip-v1:unrecognized").decode(),
        base64.b64encode(b"\x1f\x8b").decode(),
    ],
)
def test_invalid_or_oversized_transport_is_rejected_before_files(tmp_path, wire):
    destination = tmp_path / "inputs"
    with pytest.raises(ValueError):
        M.materialize_inputs(destination, env(raw_bundle(), wire))
    assert not destination.exists()


def test_secret_limit_is_inclusive_before_base64_allocation(tmp_path):
    raw = raw_bundle()
    raw += b" " * (36000 - len(raw))
    wire = base64.b64encode(raw).decode()
    assert len(wire) == SECRET_LIMIT
    M.materialize_inputs(tmp_path / "inputs", env(raw, wire))
    assert len(M.encode_release_inputs(raw + b" ")) <= SECRET_LIMIT


def test_wrong_compressed_or_restored_hash_is_rejected_before_files(tmp_path):
    raw = raw_bundle()
    wire = compressed(raw)
    for i, digest in enumerate((sha(base64.b64decode(wire)), "0" * 64)):
        destination = tmp_path / str(i)
        with pytest.raises(ValueError):
            M.materialize_inputs(
                destination, {**env(raw, wire), "RELEASE_INPUTS_SHA256": digest}
            )
        assert not destination.exists()


@pytest.mark.parametrize(
    "name",
    ["packet", "plan", "independent_review", "authorization", "shared_budget_ledger"],
)
@pytest.mark.parametrize("compress", [False, True])
def test_every_payload_type_is_validated_before_any_directory_creation(
    tmp_path, name, compress
):
    value = json.loads(raw_bundle())
    (value if name in ("packet", "plan") else value["evidence"])[name] = {
        "invalid": "not an original string"
    }
    raw = json.dumps(value).encode()
    wire = compressed(raw) if compress else base64.b64encode(raw).decode()
    destination = tmp_path / "inputs"
    with pytest.raises(ValueError):
        M.materialize_inputs(destination, env(raw, wire))
    assert not destination.exists()


def test_invalid_utf8_evidence_is_rejected_before_any_directory_creation(tmp_path):
    value = json.loads(raw_bundle())
    value["evidence"]["authorization"] = "\ud800"
    raw = json.dumps(value).encode()
    destination = tmp_path / "inputs"
    with pytest.raises(ValueError):
        M.materialize_inputs(destination, env(raw, compressed(raw)))
    assert not destination.exists()


def test_encoder_refuses_oversized_or_incompressible_input():
    for raw in (b"", b"x" * (RAW_LIMIT + 1), random.Random(1729).randbytes(50000)):
        with pytest.raises(ValueError):
            M.encode_release_inputs(raw)


def test_compressed_transport_does_not_weaken_existing_admission_or_full_ledger(
    tmp_path, monkeypatch
):
    import test_release_admission as F
    import test_release_cost_ledger_v2 as L
    import test_runtime_release as R

    ledger, packet = L.fixture()
    # Keep all original liabilities and add a complete synthetic legacy history.
    for i in range(44):
        ledger["entries"].append(
            {
                "operation_id": f"synthetic-prior-{i}",
                "plane": "data",
                "run_id": 1000 + i,
                "run_attempt": 1,
                "category": "restore",
                "state": "unknown",
                "amount_micros": 100,
                "day_utc": ledger["prior_uncertainty"]["day_utc"],
            }
        )
    snapshot = json.loads(ledger["accounting"]["snapshot_json"])
    for i in range(10):
        entry = deepcopy(ledger["operator_entries"][0])
        entry["operation_id"] = f"synthetic-operator-{i}"
        ledger["operator_entries"].append(entry)
        source = deepcopy(snapshot["entries"][1])
        source["operation_id"] = entry["operation_id"]
        snapshot["entries"].append(source)
        snapshot["total_held_micros"] += source["held_micros"]
    original_snapshot = json.dumps(snapshot, indent=2)
    ledger["accounting"].update(
        snapshot_json=original_snapshot, snapshot_sha256=sha(original_snapshot.encode())
    )
    original_ledger = (json.dumps(ledger, indent=2) + "\n").encode()
    plan, _ = R.activation_fixture(monkeypatch)
    packet["expires_at_unix"] = F.NOW + 2000
    originals = {
        "authorization": b'  { "synthetic authorization" : true }\n',
        "independent_review": b'{ "synthetic independent review" : true }  \n',
        "shared_budget_ledger": original_ledger,
    }
    packet["authorization_sha256"] = sha(originals["authorization"])
    packet["independent_review"]["report_sha256"] = sha(originals["independent_review"])
    packet["budget"]["ledger_sha256"] = sha(original_ledger)
    packet["evidence"] = {k: sha(v) for k, v in originals.items()}
    plan_raw = json.dumps(plan).encode()
    packet["plan_sha256"] = sha(plan_raw)
    packet_raw = json.dumps(packet).encode()
    raw = json.dumps(
        {
            "packet": packet_raw.decode(),
            "plan": plan_raw.decode(),
            "evidence": {k: v.decode() for k, v in originals.items()},
        }
    ).encode()
    assert len(ledger["entries"]) == 55 and len(ledger["operator_entries"]) == 11
    assert len(base64.b64encode(raw)) > SECRET_LIMIT
    wire = M.encode_release_inputs(raw)
    assert len(wire) <= SECRET_LIMIT
    destination = tmp_path / "inputs"
    M.materialize_inputs(destination, env(raw, wire))
    restored_packet = M.read_packet(
        destination / "packet.json", {"RELEASE_PACKET_SHA256": sha(packet_raw)}
    )
    evidence = M.verify_evidence(restored_packet, destination / "evidence")
    assert evidence == originals
    restored_ledger = M.strict_json(evidence["shared_budget_ledger"])
    assert (
        restored_ledger == ledger
        and restored_ledger["accounting"]["snapshot_json"] == original_snapshot
    )
    M.validate_admission(
        restored_packet, F.environment(packet), F.snapshot(), now=F.NOW
    )
    M.validate_cost_ledger(restored_ledger, restored_packet)
    restored_plan = M.read_bound_plan(destination / "plan.json", restored_packet)
    R.M.validate_plan(restored_plan, restored_packet, now=F.NOW)
    stale = deepcopy(restored_packet)
    stale["source_sha"] = "b" * 40
    with pytest.raises(ValueError):
        M.validate_admission(stale, F.environment(packet), F.snapshot(), now=F.NOW)


def test_existing_large_raw_json_contract_is_backward_compatible(tmp_path):
    raw = raw_bundle()
    raw += b" " * (RAW_LIMIT - len(raw))
    legacy = base64.b64encode(raw).decode()
    assert len(legacy) > SECRET_LIMIT
    M.materialize_inputs(tmp_path / "legacy", env(raw, legacy))
    assert M.decode_release_inputs(legacy) == raw
    with pytest.raises(ValueError):
        M.decode_release_inputs(base64.b64encode(raw + b" ").decode())
    # Producers still cannot emit an oversized secret; they select gzip.
    assert len(M.encode_release_inputs(raw)) <= SECRET_LIMIT


def test_compressed_input_over_secret_cap_is_refused_without_inflation(
    tmp_path, monkeypatch
):
    import zlib

    wire = compressed(random.Random(42).randbytes(50000))
    assert len(wire) > SECRET_LIMIT
    monkeypatch.setattr(
        zlib,
        "decompressobj",
        lambda *a, **kw: pytest.fail("oversized compressed input must not be inflated"),
    )
    destination = tmp_path / "inputs"
    with pytest.raises(ValueError):
        M.materialize_inputs(destination, env(raw_bundle(), wire))
    assert not destination.exists()
