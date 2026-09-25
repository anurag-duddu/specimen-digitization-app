"""The owner's summarize command (RELEASE.md 4.5): a value-free summary, then the approval files only on APPROVE.

Synthetic artifacts prepared from the committed collection tree, in private temporary directories; no network.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import stat
from uuid import UUID

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


admin = load("approval_test_bootstrap_admin", "scripts/data/bootstrap_admin.py")
TREE = (ROOT / admin.TREE_PATH).read_bytes()
IDENTITY = {"uid": "canary-admin-uid-5e1d", "email": "canary-admin-5e1d@example.invalid", "emailVerified": True,
            "disabled": False}
ORGANIZATION, NAME = "5e1d0000-7f3a-4b1c-8d2e-0000000000aa", "Canary Museum 5e1d"


def approval():
    """The summarize command's module, loaded where a test needs it."""
    return load("hierarchy_approval", "scripts/data/hierarchy_approval.py")


def prepared(change=None):
    collections = [{**entry, "id": f"5e1d0000-7f3a-4b1c-8d2e-{index:012x}"}
                   for index, entry in enumerate(admin.tree_entries(TREE), start=1)]
    artifact = admin.prepare_first_scope_hierarchy(
        auth_record=IDENTITY, requested_email=IDENTITY["email"], requested_uid=IDENTITY["uid"],
        organization_id=ORGANIZATION, organization_name=NAME, collections=collections, admin_collection_key="insects",
        tree=TREE)
    if change:
        change(artifact)
    return artifact


def private_values(artifact, raw):
    values = {ORGANIZATION, NAME, IDENTITY["uid"], IDENTITY["email"], artifact["artifact_sha256"],
              hashlib.sha256(raw).hexdigest(), *(entry["id"] for entry in artifact["hierarchy"]["collections"])}
    return values | {UUID(value).hex for value in values if len(value) == 36 and value.count("-") == 4}


@pytest.fixture
def owner(tmp_path, monkeypatch, capsys):
    """A private directory holding the artifact as bootstrap_admin.py --hierarchy writes it; run() answers the prompt."""
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)

    def run(artifact=None, answer="APPROVE\n", raw=None, before=None):
        artifact = prepared() if artifact is None else artifact
        path = directory / "hierarchy-artifact.json"
        if raw is None:
            admin.write_private_artifact(path, artifact)
        else:
            path.write_bytes(raw)
            path.chmod(0o600)
        raw = path.read_bytes()
        if before is not None:
            before(path)
        stdin = io.StringIO(answer)
        monkeypatch.setattr("sys.stdin", stdin)
        code = approval().main(["summarize", str(path)])
        out = capsys.readouterr()
        text = out.out + out.err
        assert not [value for value in private_values(artifact, raw) if value in text], "a value reached the terminal"
        return code, text, raw, stdin
    run.directory = directory
    return run


def files(directory):
    return sorted(path.name for path in directory.iterdir() if path.name.startswith("hierarchy-approval"))


def test_the_summary_holds_no_value_from_the_artifact_and_approve_writes_both_files_mode_600(owner):
    code, text, raw, _ = owner()
    assert code == 0 and files(owner.directory) == ["hierarchy-approval.json", "hierarchy-approval.sha256"]
    for line in ("Mode: first-scope-hierarchy-bootstrap/v1.", "Collections: 18,", "The administrator's collection: insects.",
                 "The worker's collections: insects.", "Sensitive access: false.", "Type APPROVE"):
        assert line in text
    digest = owner.directory / "hierarchy-approval.sha256"
    assert digest.read_bytes() == hashlib.sha256(raw).hexdigest().encode() + b"\n"
    record = json.loads((owner.directory / "hierarchy-approval.json").read_bytes())
    assert set(record) == {"version", "approved_at"} and record["version"] == "hierarchy-approval/v1"
    assert record["approved_at"].endswith("Z") and len(record["approved_at"]) == len("2026-09-24T00:00:00Z")
    for path in (digest, owner.directory / "hierarchy-approval.json"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("answer", ["approve\n", " APPROVE\n", "APPROVE \n", "APPROVED\n", "YES\n", "\n", ""],
                         ids=["lowercase", "leading-space", "trailing-space", "approved", "yes", "empty", "end-of-input"])
def test_anything_but_exactly_approve_writes_nothing(owner, answer):
    code, text, _, _ = owner(answer=answer)
    assert code == 1 and "Not approved: nothing was written." in text and files(owner.directory) == []


@pytest.mark.parametrize("existing", ["hierarchy-approval.sha256", "hierarchy-approval.json"])
def test_an_existing_approval_file_is_never_overwritten_and_nothing_is_asked(owner, existing):
    kept = owner.directory / existing
    kept.write_bytes(b"an earlier approval\n")
    kept.chmod(0o600)
    code, text, _, stdin = owner()
    assert code == 2 and "never overwritten" in text and "Type APPROVE" not in text
    assert kept.read_bytes() == b"an earlier approval\n" and files(owner.directory) == [existing]
    assert stdin.tell() == 0  # the prompt was never read


def test_an_existing_approval_symlink_is_refused_too(owner, tmp_path):
    (owner.directory / "hierarchy-approval.sha256").symlink_to(tmp_path / "elsewhere")
    code, text, _, _ = owner()
    assert code == 2 and not (tmp_path / "elsewhere").exists()


def edited(change):
    return prepared(change)


@pytest.mark.parametrize("artifact,raw,reason", [
    (None, b"not json\n", "the artifact is not JSON"),
    (None, b'{"schema_version": "a", "schema_version": "b"}\n', "the artifact is not JSON"),
    (edited(lambda a: a.update(schema_version="first-scope-owner-bootstrap/v1")), None,
     "the artifact is not a hierarchy artifact"),
    (edited(lambda a: a["request"]["variables"].update(organizationName="Edited")), None,
     "the artifact does not regenerate from its own values against this checkout's collection tree"),
    (edited(lambda a: a["hierarchy"]["collections"][1].update(id="5e1d0000-7f3a-4b1c-8d2e-0000000000dd")), None,
     "the artifact does not regenerate from its own values against this checkout's collection tree"),
    (edited(lambda a: a["hierarchy"].update(tree_sha256="0" * 64)), None,
     "the artifact does not regenerate from its own values against this checkout's collection tree"),
], ids=["not-json", "repeated-key", "first-scope", "edited-name", "edited-identifier", "another-tree"])
def test_an_artifact_the_release_would_refuse_is_never_offered_for_approval(owner, artifact, raw, reason):
    code, text, _, stdin = owner(artifact=artifact or prepared(), raw=raw)
    assert code == 2 and f"Approval refused: {reason}." in text and "Type APPROVE" not in text
    assert files(owner.directory) == [] and stdin.tell() == 0


@pytest.mark.parametrize("change", [lambda path: path.parent.chmod(0o755), lambda path: path.chmod(0o644)],
                         ids=["public-directory", "readable-artifact"])
def test_the_artifact_and_its_directory_must_be_private(owner, change):
    code, text, _, stdin = owner(before=change)
    assert code == 2 and "Approval refused" in text and files(owner.directory) == [] and stdin.tell() == 0


def test_it_never_opens_a_connection(owner, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the summarize command sends nothing anywhere")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    assert owner()[0] == 0


def test_the_summarize_command_is_the_only_command():
    with pytest.raises(SystemExit):
        approval().main([])
    with pytest.raises(SystemExit):
        approval().main(["approve", "artifact.json"])
