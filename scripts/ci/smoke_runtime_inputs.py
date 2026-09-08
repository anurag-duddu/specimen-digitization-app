"""Synthetic-only AMD64 container proof for mounted private-input startup.

Preparation is a separate root process; verification uses the image's configured
nonroot user with the input volume mounted read-only and network disabled.
"""

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
from uuid import UUID


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def prepare(directory):
    assert os.getuid() == 0
    directory.mkdir(exist_ok=True)
    specimens = []
    for i in range(1, 11):
        sha = hashlib.sha256(f"synthetic-runtime-{i}".encode()).hexdigest()
        specimens.append({
            "ordinal": i,
            "specimen_id": str(UUID(int=i)),
            "organization_id": str(UUID(int=101)),
            "collection_id": str(UUID(int=102)),
            "source_objects": [{
                "bucket": "demo-specimen-source", "object_name": f"synthetic/{i}.png",
                "generation": str(100 + i), "sha256": sha, "size_bytes": 10,
            }],
            "application_source": {
                "blob_ref": sha + ":200", "sha256": sha,
                "size_bytes": 10, "source_object_index": 0,
            },
        })
    manifest = {
        "schema_version": "specimen-pilot/v1", "status": "ready",
        "project_id": "specimen-digitization",
        "authorization_reference": "synthetic-offline-container-test",
        "selection": {"order": "explicit_source_order", "source_inventory_sha256": "a" * 64},
        "specimens": specimens,
    }
    manifest_raw = encode(manifest)
    launch = {
        "source_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "authorization_reference": manifest["authorization_reference"],
        "scope": {"organization_id": str(UUID(int=101)), "collection_id": str(UUID(int=102))},
        "specimens": [{
            "specimen_id": item["specimen_id"],
            "asset_sha256": item["application_source"]["sha256"],
            "blob_ref": item["application_source"]["blob_ref"],
        } for item in specimens],
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
        "total_cost_limit_micros": 10,
        "per_specimen_cost_limit_micros": 1,
        "per_specimen_call_limit": 1,
        "per_specimen_token_limit": 1,
        "effect_timeout_seconds": 1,
        "hf_secret_resource": "projects/specimen-digitization/secrets/synthetic-only/versions/1",  # pragma: allowlist secret - synthetic resource name, no credential
    }
    for name, raw in {"manifest": manifest_raw, "launch": encode(launch)}.items():
        path = directory / name
        with path.open("xb") as stream:
            stream.write(raw)
        path.chmod(0o444)
    directory.chmod(0o755)


def verify(directory, target):
    from specimen_digitization.application.runtime_input_materialization import (
        MANIFEST_MAX_BYTES, RuntimeInputError, materialize_inputs,
    )
    from specimen_digitization.application.private_config import read_private

    assert os.getuid() == 10001
    source = directory / "manifest"
    for path in directory.iterdir():
        assert path.stat().st_uid == 0
        assert stat.S_IMODE(path.stat().st_mode) == 0o444
        try:
            with path.open("ab"):
                pass
        except OSError:
            pass
        else:
            raise AssertionError("Input mount is writable")
    pin = hashlib.sha256(source.read_bytes()).hexdigest()
    try:
        read_private(source)
    except ValueError:
        pass
    else:
        raise AssertionError("Strict reader accepted root-owned public mount")
    with materialize_inputs({"manifest": (source, pin, MANIFEST_MAX_BYTES)}) as paths:
        copy = paths["manifest"]
        parent = copy.parent
        assert copy.stat().st_uid == 10001
        assert stat.S_IMODE(copy.stat().st_mode) == 0o600
        assert parent.stat().st_uid == 10001
        assert stat.S_IMODE(parent.stat().st_mode) == 0o700
        assert read_private(copy) == source.read_bytes()
    assert not parent.exists()
    before = set(Path("/tmp").glob("specimen-runtime-*"))
    try:
        with materialize_inputs({"manifest": (source, "0" * 64, MANIFEST_MAX_BYTES)}):
            raise AssertionError("Bad digest accepted")
    except RuntimeInputError:
        pass
    assert set(Path("/tmp").glob("specimen-runtime-*")) == before

    if target == "worker":
        from specimen_digitization.application.worker import materialized_worker_args
        from specimen_digitization.application.worker_launch import read_launch, verify_source_manifest

        launch_path = directory / "launch"
        os.environ["SPECIMEN_LAUNCH_POLICY_SHA256"] = hashlib.sha256(launch_path.read_bytes()).hexdigest()
        args = SimpleNamespace(mode="production", materialize_config=True,
                               launch_policy=launch_path, source_manifest=source,
                               evidence_only=False, evidence_profile=None)
        with materialized_worker_args(args) as private_args:
            launch = read_launch(private_args.launch_policy, os.environ["SPECIMEN_LAUNCH_POLICY_SHA256"])
            verify_source_manifest(private_args.source_manifest, launch)
            copies = [private_args.launch_policy, private_args.source_manifest]
            assert all(path.stat().st_uid == 10001 for path in copies)
            assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in copies)
        assert all(not path.exists() for path in copies)
    else:
        from specimen_digitization.application.sam3_server import read_runtime_manifest

        os.environ["SPECIMEN_PILOT_MANIFEST_PATH"] = str(source)
        os.environ["SPECIMEN_PILOT_MANIFEST_SHA256"] = pin
        assert len(read_runtime_manifest(materialize=True).specimens) == 10
    assert set(Path("/tmp").glob("specimen-runtime-*")) == before
    print(json.dumps({"status": "passed", "target": target, "runtime_uid": os.getuid(),
                      "root_readonly_mount": True, "strict_readers": True, "cleanup": True,
                      "synthetic_only": True, "live_services_verified": False}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--target", choices=["worker", "sam"])
    args = parser.parse_args()
    if args.prepare:
        prepare(Path("/inputs"))
    else:
        verify(Path("/inputs"), args.target)
