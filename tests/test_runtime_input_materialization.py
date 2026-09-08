"""Synthetic-only mounted-input lifecycle and strict-reader compatibility."""

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from uuid import UUID

import pytest

from specimen_digitization.application.pilot_manifest import load_ready_manifest
from specimen_digitization.application import runtime_input_materialization as materializer
from specimen_digitization.application.runtime_input_materialization import (
    MANIFEST_MAX_BYTES,
    POLICY_MAX_BYTES,
    RuntimeInputError,
    materialize_inputs,
)


def mounted(tmp_path, raw=b"synthetic-private-fixture", name="mount"):
    source = tmp_path / name
    source.write_bytes(raw)
    source.chmod(0o444)
    return source, hashlib.sha256(raw).hexdigest(), POLICY_MAX_BYTES


def test_readonly_mount_copies_to_private_owned_files_and_cleans(tmp_path):
    spec = mounted(tmp_path)
    with materialize_inputs({"launch.json": spec}, temp_parent=tmp_path) as paths:
        copy = paths["launch.json"]
        assert copy.read_bytes() == spec[0].read_bytes()
        assert copy != spec[0]
        assert stat.S_IMODE(copy.stat().st_mode) == 0o600
        assert stat.S_ISREG(copy.stat().st_mode)
        assert copy.stat().st_uid == os.getuid()
        assert copy.stat().st_nlink == 1
        assert stat.S_IMODE(copy.parent.stat().st_mode) == 0o700
        assert copy.parent.stat().st_uid == os.getuid()
        parent = copy.parent
    assert not parent.exists()
    assert spec[0].read_bytes() == b"synthetic-private-fixture"
    assert stat.S_IMODE(spec[0].stat().st_mode) == 0o444


def test_cleanup_when_consumer_raises_preserves_consumer_exception(tmp_path):
    spec = mounted(tmp_path)
    with pytest.raises(OSError, match="consumer failure"):
        with materialize_inputs({"manifest": spec}, temp_parent=tmp_path) as paths:
            parent = paths["manifest"].parent
            raise OSError("consumer failure")
    assert not parent.exists()


def test_wrong_second_digest_leaves_no_partial_copy(tmp_path):
    first = mounted(tmp_path, name="first")
    second = mounted(tmp_path, name="second")
    with pytest.raises(RuntimeInputError, match="digest mismatch"):
        with materialize_inputs({"manifest": first, "launch": (second[0], "0" * 64, 64)}, temp_parent=tmp_path):
            pytest.fail("Invalid input yielded")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["first", "second"]


@pytest.mark.parametrize("maximum", [1, POLICY_MAX_BYTES, MANIFEST_MAX_BYTES])
def test_bound_exactly_accepted_and_one_byte_over_rejected(tmp_path, maximum):
    raw = b"a" * maximum
    source, digest, _ = mounted(tmp_path, raw)
    with materialize_inputs({"input": (source, digest, maximum)}, temp_parent=tmp_path) as paths:
        assert paths["input"].stat().st_size == maximum
    source.chmod(0o600)
    source.write_bytes(raw + b"a")
    source.chmod(0o444)
    with pytest.raises(RuntimeInputError, match="size bound"):
        with materialize_inputs({"input": (source, digest, maximum)}, temp_parent=tmp_path):
            pytest.fail("Oversize input yielded")


@pytest.mark.parametrize("kind", ["symlink", "directory", "missing"])
def test_nonregular_or_missing_source_rejected_without_residue(tmp_path, kind):
    source, digest, maximum = mounted(tmp_path)
    bad = tmp_path / kind
    if kind == "symlink":
        bad.symlink_to(source)
    elif kind == "directory":
        bad.mkdir()
    with pytest.raises(RuntimeInputError):
        with materialize_inputs({"input": (bad, digest, maximum)}, temp_parent=tmp_path):
            pytest.fail("Invalid input yielded")
    assert not list(tmp_path.glob("specimen-runtime-*"))


def test_fifo_rejected_without_blocking(tmp_path):
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo, 0o444)
    script = (
        "from pathlib import Path\n"
        "import sys\n"
        "from specimen_digitization.application.runtime_input_materialization import materialize_inputs\n"
        "with materialize_inputs({'input': (Path(sys.argv[1]), 'a'*64, 65536)}, temp_parent=Path(sys.argv[2])):\n"
        "    raise AssertionError('unexpected success')\n"
    )
    result = subprocess.run([sys.executable, "-c", script, str(fifo), str(tmp_path)], capture_output=True, timeout=5)
    assert result.returncode != 0
    assert b"regular file" in result.stderr
    assert not list(tmp_path.glob("specimen-runtime-*"))


@pytest.mark.parametrize("name", ["../escape", "/absolute", ".", "..", "a/b", "", "secret\nname", "a" * 65])
def test_names_cannot_escape_private_directory(tmp_path, name):
    spec = mounted(tmp_path)
    with pytest.raises(RuntimeInputError, match="input name"):
        with materialize_inputs({name: spec}, temp_parent=tmp_path):
            pytest.fail("Invalid input yielded")
    assert not list(tmp_path.glob("specimen-runtime-*"))


@pytest.mark.parametrize("digest", [None, "", False, 123, "a" * 63, "A" * 64, "g" * 64, "a" * 64 + "\n"])
def test_external_digest_required_and_strict(tmp_path, digest):
    source, _, maximum = mounted(tmp_path)
    with pytest.raises(RuntimeInputError, match="digest required"):
        with materialize_inputs({"input": (source, digest, maximum)}, temp_parent=tmp_path):
            pytest.fail("Invalid input yielded")


@pytest.mark.parametrize("maximum", [None, True, 0, -1, 1.5, "65536", MANIFEST_MAX_BYTES + 1])
def test_invalid_bound_rejected_before_copy(tmp_path, maximum):
    source, digest, _ = mounted(tmp_path)
    with pytest.raises(RuntimeInputError, match="size bound"):
        with materialize_inputs({"input": (source, digest, maximum)}, temp_parent=tmp_path):
            pytest.fail("Invalid input yielded")


def test_exclusive_creation_never_overwrites_existing_file(tmp_path):
    target = tmp_path / "manifest"
    target.write_bytes(b"existing-authority")
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(FileExistsError):
            materializer._write_private(fd, "manifest", b"replacement", hashlib.sha256(b"replacement").hexdigest())
    finally:
        os.close(fd)
    assert target.read_bytes() == b"existing-authority"


def test_write_failure_cleans_directory_and_sanitizes_error(tmp_path, monkeypatch):
    source, digest, maximum = mounted(tmp_path)

    def fail(*args):
        raise OSError("DO_NOT_PRINT_PRIVATE_PATH_OR_CONTENT")

    monkeypatch.setattr(materializer, "_write_private", fail)
    with pytest.raises(RuntimeInputError) as caught:
        with materialize_inputs({"input": (source, digest, maximum)}, temp_parent=tmp_path):
            pytest.fail("Invalid input yielded")
    assert "DO_NOT_PRINT" not in str(caught.value)
    assert str(source) not in str(caught.value)
    assert not list(tmp_path.glob("specimen-runtime-*"))


def test_private_directory_cannot_be_inside_git(tmp_path):
    spec = mounted(tmp_path)
    (tmp_path / ".git").write_text("gitdir: synthetic-fixture")
    with pytest.raises(RuntimeInputError, match="outside Git"):
        with materialize_inputs({"manifest": spec}, temp_parent=tmp_path):
            pytest.fail("Invalid input yielded")
    assert not list(tmp_path.glob("specimen-runtime-*"))


def test_copy_cannot_launder_private_input_from_git(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    spec = mounted(checkout)
    with pytest.raises(RuntimeInputError, match="outside Git"):
        with materialize_inputs({"manifest": spec}, temp_parent=tmp_path):
            pytest.fail("Invalid input yielded")
    assert not list(tmp_path.glob("specimen-runtime-*"))


@pytest.mark.parametrize("corruption", ["mode", "bytes"])
def test_postcreation_validation_detects_corruption_and_cleans(tmp_path, monkeypatch, corruption):
    spec = mounted(tmp_path)
    original_fsync = os.fsync

    def corrupt(fd):
        original_fsync(fd)
        if corruption == "mode":
            os.fchmod(fd, 0o644)
        else:
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, b"X")

    monkeypatch.setattr(os, "fsync", corrupt)
    with pytest.raises(RuntimeInputError, match="validation failed"):
        with materialize_inputs({"manifest": spec}, temp_parent=tmp_path):
            pytest.fail("Corrupted input yielded")
    assert not list(tmp_path.glob("specimen-runtime-*"))


def test_destination_owner_mismatch_rejected(tmp_path, monkeypatch):
    current_uid = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: current_uid + 1)
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(RuntimeInputError, match="privacy validation failed"):
            materializer._write_private(directory_fd, "manifest", b"fixture", hashlib.sha256(b"fixture").hexdigest())
    finally:
        os.close(directory_fd)


def test_materialized_synthetic_ten_works_with_unchanged_strict_reader(tmp_path):
    specimens = []
    for index in range(1, 11):
        digest = hashlib.sha256(f"synthetic-only-{index}".encode()).hexdigest()
        specimens.append({
            "ordinal": index, "specimen_id": str(UUID(int=index)),
            "organization_id": str(UUID(int=101)), "collection_id": str(UUID(int=102)),
            "source_objects": [{"bucket": "demo-synthetic", "object_name": f"fixture/{index}",
                                "generation": "1", "sha256": digest, "size_bytes": 10}],
            "application_source": {"blob_ref": digest + ":1", "sha256": digest,
                                   "size_bytes": 10, "source_object_index": 0},
        })
    raw = json.dumps({
        "schema_version": "specimen-pilot/v1", "status": "ready",
        "project_id": "specimen-digitization", "authorization_reference": "synthetic-only",
        "selection": {"order": "explicit_source_order", "source_inventory_sha256": "a" * 64},
        "specimens": specimens,
    }).encode()
    source, digest, _ = mounted(tmp_path, raw)
    with materialize_inputs({"manifest": (source, digest, MANIFEST_MAX_BYTES)}, temp_parent=tmp_path) as paths:
        ready = load_ready_manifest(paths["manifest"], digest)
        assert len(ready.specimens) == 10
        assert ready.authorization_reference == "synthetic-only"
