"""Synthetic SAM startup input copies; no model or cloud initialization."""

import hashlib
import json
import sys

import pytest

from specimen_digitization.application import runtime_input_materialization
from specimen_digitization.application import sam3_server
from test_pilot_manifest import pilot_payload


def fixture(tmp_path, monkeypatch):
    source = tmp_path / "manifest"
    raw = json.dumps(pilot_payload()).encode()
    source.write_bytes(raw)
    source.chmod(0o444)
    monkeypatch.setenv("SPECIMEN_PILOT_MANIFEST_PATH", str(source))
    monkeypatch.setenv("SPECIMEN_PILOT_MANIFEST_SHA256", hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(runtime_input_materialization.tempfile, "gettempdir", lambda: str(tmp_path))
    return source


def test_sam_opt_in_accepts_mount_through_strict_reader_and_cleans(tmp_path, monkeypatch):
    source = fixture(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match="sam3_private_manifest_unavailable"):
        sam3_server.read_runtime_manifest()
    assert len(sam3_server.read_runtime_manifest(materialize=True).specimens) == 10
    assert list(tmp_path.iterdir()) == [source]
    assert source.stat().st_mode & 0o777 == 0o444


@pytest.mark.parametrize("kind", ["hash", "missing", "symlink", "malformed", "oversized", "missing_pin"])
def test_sam_bad_inputs_never_reach_consumer_or_leave_copies(tmp_path, monkeypatch, kind):
    source = fixture(tmp_path, monkeypatch)
    if kind == "hash":
        monkeypatch.setenv("SPECIMEN_PILOT_MANIFEST_SHA256", "0" * 64)
    elif kind == "missing_pin":
        monkeypatch.delenv("SPECIMEN_PILOT_MANIFEST_SHA256")
    elif kind == "missing":
        source.unlink()
    elif kind == "symlink":
        link = tmp_path / "link"
        link.symlink_to(source)
        monkeypatch.setenv("SPECIMEN_PILOT_MANIFEST_PATH", str(link))
    else:
        raw = b'DO_NOT_PRINT_PRIVATE_CONTENT' if kind == "malformed" else b" " * (1024 * 1024 + 1)
        source.chmod(0o600)
        source.write_bytes(raw)
        source.chmod(0o444)
        monkeypatch.setenv("SPECIMEN_PILOT_MANIFEST_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(RuntimeError) as caught:
        sam3_server.read_runtime_manifest(materialize=True)
    assert str(caught.value) == "sam3_private_manifest_unavailable"
    assert not list(tmp_path.glob("specimen-runtime-*"))


def test_cli_opt_in_does_not_bypass_launch_authorization(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["sam3", "--materialize-config"])
    monkeypatch.delenv("SPECIMEN_SAM3_ENABLE", raising=False)
    monkeypatch.setattr(sam3_server, "read_runtime_manifest", lambda **kwargs: pytest.fail("Read before authorization"))
    with pytest.raises(RuntimeError, match="sam3_requires_authorized_cloud_run_launch"):
        sam3_server.main()
