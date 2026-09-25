"""The bootstrap's three secrets never reach a child process (RELEASE.md 4.5, T3e).

The release step reads DATA_BOOTSTRAP_ARTIFACT_B64, DATA_BOOTSTRAP_APPROVED_SHA256 and DATA_WORKER_ACTOR_UID exactly once,
before any child process starts, keeps the values in memory and removes all three from its environment together: gh
(admission's GitHub reads, deploy_runtime.checked) and the Node SQL connector (first_catalog, gate_sql) inherit the rest.
Synthetic secrets, artifacts and replies only; never network, credentials or cloud.
"""
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

import deploy_data as D
from release_diagnostics import HTTPFailure
from test_data_apply import CLONED, SECRETS, earlier, released, visible  # noqa: F401 (a fixture)
from test_data_bootstrap import Plane, exact, prepare, seed
from test_data_released_deploy import (EMPTY, MERGED, RULES, command_line, record, release,  # noqa: F401 (fixtures)
                                       state)


def secrets(monkeypatch, raw=b"not base64: canary-bootstrap-row\n"):
    """The owner's three secrets, set as the workflow sets them on the release step."""
    values = {SECRETS[0]: base64.b64encode(raw).decode("ascii"), SECRETS[1]: hashlib.sha256(raw).hexdigest(),
              SECRETS[2]: "canary-worker-uid-9c41"}
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return values


def test_the_secrets_are_read_once_and_removed_together(monkeypatch):
    monkeypatch.setenv(SECRETS[0], "canary-artifact")
    monkeypatch.delenv(SECRETS[1], raising=False)
    monkeypatch.setenv(SECRETS[2], "canary-uid")
    assert D.BOOTSTRAP_SECRETS == SECRETS
    assert D.take_bootstrap_secrets() == {SECRETS[0]: "canary-artifact", SECRETS[1]: "", SECRETS[2]: "canary-uid"}
    # Gone from the environment, so a second read finds nothing and no child process can inherit them.
    assert not visible(os.environ) and D.take_bootstrap_secrets() == dict.fromkeys(SECRETS, "")


def test_after_the_release_starts_no_request_or_child_process_sees_a_secret_and_the_bootstrap_still_runs(
        released, tmp_path, monkeypatch):
    """Verify, then the bootstrap over rows that already match: the values reached it from memory alone."""
    payload = prepare()
    plane = Plane(tmp_path / "release", payload, MERGED, rules=RULES)
    seed(plane, payload)
    secrets(monkeypatch, exact(payload))
    value, outputs = released(plane)
    assert plane.error is None and value["bootstrap"] == "verified" and outputs.startswith("phase=verify\n")
    # Google was built after the secrets left, and the Node connector ran for verify's reads; none saw one.
    assert plane.environments and not any(plane.environments)
    assert [kind for kind, _ in plane.children] and not any(names for _, names in plane.children)
    assert not visible(os.environ)


def test_gh_and_the_node_connector_never_inherit_a_secret_on_a_first_apply(released, tmp_path, monkeypatch):
    """A first apply after an earlier attempt's checked restore lists and downloads that attempt's receipt with gh
    (deploy_runtime.checked), runs the migration through the Node connector (gate_sql), then bootstraps."""
    payload = prepare()
    plane = Plane(tmp_path / "release", payload, label=None)
    plane.earlier = earlier()
    plane.live["sql", CLONED] = HTTPFailure(403)  # the clone is never read: the earlier attempt proved the restore
    seed(plane, payload)
    secrets(monkeypatch, exact(payload))
    value, _ = released(plane)
    assert plane.error is None and value["first_restore"] == "proven" and value["bootstrap"] == "verified"
    assert {"gh api", "gh run download", "node"} <= {kind for kind, _ in plane.children}
    assert not any(names for _, names in plane.children) and not any(plane.environments)


def test_initialize_leaves_the_secrets_unread_but_removes_them_before_the_catalog_summary_runs(release, monkeypatch):
    values = secrets(monkeypatch)
    for module, name in ((base64, "b64decode"), (base64, "standard_b64decode"), (base64, "urlsafe_b64decode"),
                         (base64, "decodebytes"), (binascii, "a2b_base64")):
        monkeypatch.setattr(module, name, lambda *args, **kwargs: pytest.fail("the artifact stays unread"))
    seen = []

    def summary(command, **kwargs):
        """release_sql.mjs summary, the Node connector's first run on initialize."""
        seen.append(visible(kwargs["env"]))
        Path(command[4]).parent.mkdir(parents=True, exist_ok=True)  # the release fixture's packet directory
        Path(command[4]).write_text(json.dumps(EMPTY))
        Path(command[4]).chmod(0o600)
        return subprocess.CompletedProcess(command, 0, b"", b"")
    monkeypatch.setattr(D.subprocess, "run", summary)
    google, value, outputs = release(state(rules=None), summary=None)
    assert google.error is None and outputs == "phase=initialize\ninit_step=initialize\n"
    assert value["bootstrap"] == "deferred" and seen == [[]] and not visible(os.environ)
    assert not any(secret in google.log + json.dumps(value) for secret in values.values())


def test_the_command_line_takes_the_secrets_before_admission_runs_gh_and_hands_them_to_the_release(
        command_line, monkeypatch):
    values = secrets(monkeypatch)
    admitted, received = [], []

    def admit(path, plane):
        admitted.append(visible(os.environ))  # admission re-reads GitHub with gh, which inherits the environment
        return record(plane)

    def deploy(path, output, **kwargs):
        received.append(kwargs)
        output.write_text("{}\n")
    monkeypatch.setattr(D, "admit", admit)
    monkeypatch.setattr(D, "deploy_released_data", deploy)
    command_line("--deploy")
    assert admitted == [[]] and received == [{"secrets": values}] and not visible(os.environ)


def test_the_deployment_contract_says_no_child_process_inherits_them():
    contract = (Path(__file__).resolve().parents[2] / "docs/DEPLOYMENT.md").read_text()
    section = " ".join(contract.split("## Data release on merge (go-live program)")[1].split("\n## ")[0].split())
    assert ("takes them out of its environment before any child process starts, so neither `gh` nor the Node SQL "
            "connector inherits them") in section
