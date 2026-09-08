import copy
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from specimen_digitization.application.pilot_manifest import (
    PilotManifest,
    PrivateManifestError,
    load_ready_manifest,
    write_private,
)


def pilot_payload():
    specimens = []
    for i in range(1, 11):
        sha = hashlib.sha256(f"synthetic-only-{i}".encode()).hexdigest()
        specimens.append({
            "ordinal": i,
            "specimen_id": str(UUID(int=i)),
            "organization_id": str(UUID(int=101)),
            "collection_id": str(UUID(int=102)),
            "source_objects": [{
                "bucket": "demo-specimen-source",
                "object_name": f"synthetic/{i}.png",
                "generation": str(100 + i), "sha256": sha, "size_bytes": 10,
            }],
            "application_source": {
                "blob_ref": sha + ":200", "sha256": sha,
                "size_bytes": 10, "source_object_index": 0,
            },
        })
    return {
        "schema_version": "specimen-pilot/v1", "status": "ready",
        "project_id": "specimen-digitization",
        "authorization_reference": "synthetic-test-authorization",
        "selection": {"order": "explicit_source_order", "source_inventory_sha256": "a" * 64},
        "specimens": specimens,
    }


def test_exact_ten_multi_object_source_binding(tmp_path):
    payload = pilot_payload()
    second = copy.deepcopy(payload["specimens"][0]["source_objects"][0])
    second["object_name"] = "synthetic/second.png"
    payload["specimens"][0]["source_objects"].append(second)
    target = tmp_path / "private.json"
    digest = write_private(target, payload)
    assert len(load_ready_manifest(target, digest).specimens) == 10
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(PrivateManifestError, match="already exists"):
        write_private(target, payload)


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(status="metadata_frozen"),
    lambda p: p["specimens"].pop(),
    lambda p: p["specimens"].append(copy.deepcopy(p["specimens"][0])),
    lambda p: p["specimens"].reverse(),
    lambda p: p["specimens"][1].update(specimen_id=p["specimens"][0]["specimen_id"]),
    lambda p: p["specimens"][1].update(collection_id=str(UUID(int=999))),
    lambda p: p["specimens"][0]["source_objects"][0].update(generation="latest"),
    lambda p: p["specimens"][0]["source_objects"][0].update(sha256=None),
    lambda p: p["specimens"][0]["source_objects"][0].update(size_bytes=True),
    lambda p: p["specimens"][0]["application_source"].update(source_object_index=1),
    lambda p: p["specimens"][0]["application_source"].update(size_bytes=11),
    lambda p: p["specimens"][0]["application_source"].update(blob_ref="f" * 64 + ":200"),
    lambda p: p["specimens"][0]["source_objects"][0].update(object_name="bad\nobject"),
    lambda p: p.update(denominator=100),
])
def test_reject_changed_or_incomplete_scope(mutation):
    payload = pilot_payload()
    mutation(payload)
    with pytest.raises(ValidationError):
        PilotManifest.model_validate(payload)


def test_loader_checks_external_pin_privacy_and_redacts_errors(tmp_path):
    path = tmp_path / "private.json"
    pin = write_private(path, pilot_payload())
    with pytest.raises(PrivateManifestError, match="hash mismatch"):
        load_ready_manifest(path, "0" * 64)
    os.chmod(path, 0o644)
    with pytest.raises(PrivateManifestError, match="0600"):
        load_ready_manifest(path, pin)
    os.chmod(path, 0o600)
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(PrivateManifestError, match="unavailable"):
        load_ready_manifest(link, pin)
    raw = json.dumps({"private_name": "DO_NOT_PRINT_ME"}).encode()
    path.write_bytes(raw)
    with pytest.raises(PrivateManifestError) as caught:
        load_ready_manifest(path, hashlib.sha256(raw).hexdigest())
    assert "DO_NOT_PRINT_ME" not in str(caught.value)


def test_private_file_rejected_inside_git_worktree(tmp_path):
    (tmp_path / ".git").write_text("gitdir: synthetic-only")
    with pytest.raises(PrivateManifestError, match="outside Git"):
        write_private(tmp_path / "private.json", pilot_payload())


def test_private_file_size_bounded(tmp_path):
    path = tmp_path / "large.json"
    path.write_bytes(b" " * (1024 * 1024 + 1))
    path.chmod(0o600)
    with pytest.raises(PrivateManifestError, match="too large"):
        load_ready_manifest(path, "a" * 64)


@pytest.mark.parametrize("missing_pin", [None, "", False, 123, "a" * 63])
def test_external_pin_cannot_be_omitted(tmp_path, missing_pin):
    path = tmp_path / "private.json"
    write_private(path, pilot_payload())
    with pytest.raises(PrivateManifestError, match="hash required"):
        load_ready_manifest(path, missing_pin)


def test_fifo_cannot_block_startup(tmp_path):
    # NONBLOCK open allows fstat to reject a FIFO even when no writer exists.
    import subprocess
    import sys

    path = tmp_path / "fifo"
    os.mkfifo(path, 0o600)
    command = (
        "from pathlib import Path; "
        "from specimen_digitization.application.pilot_manifest import load_ready_manifest; "
        "load_ready_manifest(Path(__import__('sys').argv[1]), 'a'*64)"
    )
    result = subprocess.run([sys.executable, "-c", command, str(path)], capture_output=True, timeout=5)
    assert result.returncode != 0
    assert b"regular file" in result.stderr
