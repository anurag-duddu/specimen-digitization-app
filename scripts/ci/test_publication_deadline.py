"""Synthetic clocks, credentials and real owned processes; never cloud calls."""
import importlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def guard():
    return importlib.import_module("release_publication_deadline")


def test_absolute_cutoff_survives_clock_changes_and_never_restarts(guard):
    now = [100.0, 50.0]
    deadline = guard.Deadline(140, wall=lambda: now[0], mono=lambda: now[1])
    assert deadline.remaining() == 30
    now[:] = [90, 65]
    assert deadline.remaining() == 15
    now[:] = [139, 66]
    with pytest.raises(guard.PublicationStopped):
        deadline.remaining()


def test_late_start_never_launches_a_child(guard, tmp_path):
    marker = tmp_path / "unexpected"
    with pytest.raises(guard.PublicationStopped):
        guard.Supervisor(guard.Deadline(time.time() + 5)).run_owned(
            [sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"],
            env=dict(os.environ), cwd=tmp_path, stage="auth", limit=30)
    assert not marker.exists()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux subreaper ownership is qualified in the local Linux test")
@pytest.mark.parametrize("leader_dies", [False, True])
def test_cutoff_kills_inherited_grandchild_even_after_leader_death(guard, tmp_path, leader_dies):
    marker = tmp_path / "child.pid"
    grandchild = ("import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                  f"open({str(marker)!r},'w').write(str(os.getpid())); time.sleep(30)")
    script = ("import os,signal,subprocess,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
              f"subprocess.Popen([sys.executable,'-c',{grandchild!r}]); time.sleep(.15); "
              + ("os._exit(3)" if leader_dies else "time.sleep(30)"))
    end = time.time() + guard.STOP_RESERVE + .4
    supervisor = guard.Supervisor(guard.Deadline(end))
    with pytest.raises(guard.PublicationStopped):
        supervisor.run_owned([sys.executable, "-c", script], env=dict(os.environ), cwd=tmp_path,
                             stage="push", limit=30)
    assert marker.exists()
    assert not guard.process_group_alive(supervisor.last_group)
    assert any(event["event"] == "signal_kill" for event in supervisor.events)
    assert all(event["at_unix"] < end for event in supervisor.events if event["event"].startswith("signal_"))


def test_success_with_surviving_descendant_is_not_promoted(guard, tmp_path):
    child = "import time; time.sleep(30)"
    script = f"import subprocess,sys; subprocess.Popen([sys.executable,'-c',{child!r}])"
    supervisor = guard.Supervisor(guard.Deadline(time.time() + 30))
    with pytest.raises(guard.PublicationStopped):
        supervisor.run_owned([sys.executable, "-c", script], env=dict(os.environ), cwd=tmp_path,
                             stage="publish", limit=10)
    assert not guard.process_group_alive(supervisor.last_group)


def output_file(path, pairs):
    path.write_text("".join(f"{key}<<unique_{i}\n{value}\nunique_{i}\n" for i, (key, value) in enumerate(pairs)))
    path.chmod(0o600)


def test_normal_auth_token_output_is_accepted_but_discarded(guard, tmp_path):
    path = tmp_path / "auth-output"
    credential = tmp_path / "gha-creds-synthetic.json"
    output_file(path, [("credentials_file_path", str(credential)), ("project_id", "specimen-digitization"),
                       ("auth_token", "synthetic-token-never-export")])
    value = guard.auth_outputs(path)
    assert value == {"credentials_file_path": str(credential), "project_id": "specimen-digitization"}
    assert not path.exists()
    assert "synthetic-token" not in repr(value)


@pytest.mark.parametrize("extra", ["access_token", "unexpected", "credentials_file_path"])
def test_auth_output_rejects_extra_or_duplicate_keys_and_disposes_file(guard, tmp_path, extra):
    path = tmp_path / "auth-output"
    output_file(path, [("credentials_file_path", "/synthetic"), ("project_id", "specimen-digitization"),
                       ("auth_token", "synthetic"), (extra, "unexpected")])
    with pytest.raises(ValueError):
        guard.auth_outputs(path)
    assert not path.exists()


def auth_packet():
    return {"identity": {"provider": "projects/123/locations/global/workloadIdentityPools/test/providers/specimen-runtime-build"}}


def test_auth_uses_all_fixed_defaults_and_no_inherited_inputs(guard, tmp_path):
    env = {"INPUT_TOKEN_FORMAT": "access_token", "INPUT_CREDENTIALS_JSON": "forbidden", "NODE_OPTIONS": "forbidden"}
    actual = guard.auth_environment(env, auth_packet(), tmp_path)
    assert {key: value for key, value in actual.items() if key.startswith("INPUT_")} == {
        "INPUT_PROJECT_ID": "specimen-digitization",
        "INPUT_WORKLOAD_IDENTITY_PROVIDER": auth_packet()["identity"]["provider"],
        "INPUT_SERVICE_ACCOUNT": "specimen-runtime-build@specimen-digitization.iam.gserviceaccount.com",
        "INPUT_AUDIENCE": "", "INPUT_CREDENTIALS_JSON": "", "INPUT_CREATE_CREDENTIALS_FILE": "true",
        "INPUT_EXPORT_ENVIRONMENT_VARIABLES": "false", "INPUT_TOKEN_FORMAT": "", "INPUT_DELEGATES": "",
        "INPUT_UNIVERSE": "googleapis.com", "INPUT_REQUEST_REASON": "", "INPUT_CLEANUP_CREDENTIALS": "true",
        "INPUT_ACCESS_TOKEN_LIFETIME": "3600s", "INPUT_ACCESS_TOKEN_SCOPES": "https://www.googleapis.com/auth/cloud-platform",
        "INPUT_ACCESS_TOKEN_SUBJECT": "", "INPUT_ID_TOKEN_AUDIENCE": "", "INPUT_ID_TOKEN_INCLUDE_EMAIL": "false",
    }
    assert "NODE_OPTIONS" not in actual
    assert actual["GITHUB_WORKSPACE"] == str(tmp_path / "auth")


@pytest.mark.parametrize("name", ["GHA_ENDPOINT_OVERRIDE_sts", "GHA_ENDPOINT_OVERRIDE_iamcredentials", "GHA_ENDPOINT_OVERRIDE_any"])
def test_endpoint_override_is_rejected_before_auth(guard, tmp_path, name):
    with pytest.raises(ValueError, match="endpoint override"):
        guard.auth_environment({name: "https://synthetic.invalid"}, auth_packet(), tmp_path)


def test_original_packet_substitution_is_rejected(guard, tmp_path):
    packet = tmp_path / "packet.json"
    packet.write_text('{"expires_at_unix": 123}')
    packet.chmod(0o600)
    with pytest.raises(ValueError):
        guard.frozen_packet(packet, {"RELEASE_PACKET_SHA256": "0" * 64})


def test_workflow_auth_is_inside_one_guard_and_keeps_provenance():
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/runtime-release.yml").read_text()
    build = workflow.split("  build:", 1)[1].split("  release:", 1)[0]
    assert "uses: ./.github/actions/runtime-publication" in build
    assert "uses: google-github-actions/auth@" not in build
    assert "ref: 7c6bc770dae815cd3e89ee6cdf493a5fab2cc093" in build
    assert "fail-fast: false" in build
    assert "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6" in build
    action = (root / ".github/actions/runtime-publication/action.yml").read_text()
    assert "post:" in action and "node24" in action


def test_failed_started_evidence_still_terminates_the_owned_group(guard, tmp_path):
    def fail_started(events):
        if events[-1]["event"] == "started":
            raise OSError("synthetic storage failure")
    supervisor = guard.Supervisor(guard.Deadline(time.time() + 30), fail_started)
    try:
        with pytest.raises(OSError):
            supervisor.run_owned([sys.executable, "-c", "import time; time.sleep(30)"],
                                 env=dict(os.environ), cwd=tmp_path, stage="auth", limit=10)
        assert not guard.process_group_alive(supervisor.last_group)
    finally:
        if supervisor.last_group and guard.process_group_alive(supervisor.last_group):
            os.killpg(supervisor.last_group, signal.SIGKILL)


def test_unvalidated_path_never_reaches_upstream_post(guard, tmp_path, monkeypatch):
    owned = tmp_path / "specimen-publication-owned"
    owned.mkdir(mode=0o700)
    marker = owned / "owner.json"
    marker.write_text(json.dumps({"version": 1, "run_id": "123", "attempt": "1"}))
    marker.chmod(0o600)
    foreign = tmp_path / "keep.json"
    foreign.write_text("public synthetic")
    env = {"RUNNER_TEMP": str(tmp_path), "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
    monkeypatch.setattr(guard.subprocess, "Popen", lambda *a, **kw: pytest.fail("foreign cleanup target reached upstream"))
    with pytest.raises(ValueError):
        guard.dispose(owned, env, "unused", tmp_path, foreign)
    assert foreign.read_text() == "public synthetic"
