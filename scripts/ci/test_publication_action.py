"""Local wrapper state/output tests; no real credentials or network."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / ".github/actions/runtime-publication"
NODE = shutil.which("node")


def node(script, env):
    return subprocess.run([NODE, "-e", script], env=env, capture_output=True, text=True, timeout=5)


@pytest.mark.parametrize("state", [None, "", "/foreign/owned"])
def test_post_missing_or_foreign_state_never_runs_main(tmp_path, state):
    env = {**os.environ, "RUNNER_TEMP": str(tmp_path), "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}
    env.pop("STATE_owned_directory", None)
    if state is not None:
        env["STATE_owned_directory"] = state
    result = subprocess.run([NODE, str(ACTION / "post.cjs")], env=env, capture_output=True, text=True, timeout=5)
    assert "Cannot find module" not in result.stderr
    assert result.returncode == (1 if state else 0)
    assert list(tmp_path.iterdir()) == []
    assert "auth" not in result.stdout.lower()


def test_owned_state_is_durable_before_any_auth_and_post_deletes_partial_files(tmp_path):
    state = tmp_path / "state"
    state.write_text("")
    env = {**os.environ, "RUNNER_TEMP": str(tmp_path), "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_STATE": str(state)}
    script = f"const m=require({str(ACTION / 'index.cjs')!r}); const p=m.createOwned(process.env); console.log(p);"
    result = node(script, env)
    assert result.returncode == 0, result.stderr
    owned = Path(result.stdout.strip())
    assert state.read_text() == f"owned_directory={owned}\n"
    assert (owned / "owner.json").is_file()
    auth = owned / "auth"
    auth.mkdir()
    (auth / "gha-creds-partial.json").write_text("synthetic-only")
    env["STATE_owned_directory"] = str(owned)
    result = subprocess.run([NODE, str(ACTION / "post.cjs")], env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert not owned.exists()


def test_post_refuses_other_run_and_root_symlink_but_does_not_follow_child_symlinks(tmp_path):
    state = tmp_path / "state"
    state.write_text("")
    env = {**os.environ, "RUNNER_TEMP": str(tmp_path), "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_STATE": str(state)}
    result = node(f"console.log(require({str(ACTION / 'index.cjs')!r}).createOwned(process.env));", env)
    assert result.returncode == 0, result.stderr
    owned = Path(result.stdout.strip())
    foreign = tmp_path / "must-stay"
    foreign.write_text("public synthetic")
    (owned / "link").symlink_to(foreign)
    env.update(STATE_owned_directory=str(owned), GITHUB_RUN_ATTEMPT="2")
    bad = subprocess.run([NODE, str(ACTION / "post.cjs")], env=env, capture_output=True, timeout=5)
    assert bad.returncode == 1 and owned.exists()
    env["GITHUB_RUN_ATTEMPT"] = "1"
    good = subprocess.run([NODE, str(ACTION / "post.cjs")], env=env, capture_output=True, timeout=5)
    assert good.returncode == 0
    assert foreign.read_text() == "public synthetic"


@pytest.mark.skipif(subprocess.check_output([NODE, "--version"], text=True).split('.')[0] != "v24",
                    reason="the actual wrapper entrypoint is exercised with Linux Node24")
@pytest.mark.parametrize("failure", [False, True])
def test_real_node24_main_uses_its_runtime_and_cleans_partial_state(tmp_path, failure):
    root = tmp_path / "source"
    action = root / ".github/actions/runtime-publication"
    action.mkdir(parents=True)
    for name in ("index.cjs", "post.cjs"):
        shutil.copyfile(ACTION / name, action / name)
    python = root / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text('''#!/bin/sh
set -eu
test -s "$GITHUB_STATE"
printf '%s\\n' "$@" > "$PROBE_MARKER"
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--owned" ]; then
    mkdir "$2/auth"
    printf 'synthetic partial only\\n' > "$2/auth/gha-creds-partial.json"
    break
  fi
  shift
done
exit ''' + ("1" if failure else "0") + "\n")
    python.chmod(0o700)
    temp = tmp_path / "runner"
    temp.mkdir()
    state, probe = temp / "state", temp / "probe"
    state.write_text("")
    env = {"PATH": os.environ["PATH"], "GITHUB_WORKSPACE": str(root), "RUNNER_TEMP": str(temp),
           "GITHUB_STATE": str(state), "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
           "INPUT_ROLE": "api", "INPUT_PACKET": str(temp / "packet.json"), "INPUT_OUTPUT": str(temp / "api.json"),
           "PROBE_MARKER": str(probe)}
    result = subprocess.run([NODE, str(action / "index.cjs")], env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode == int(failure), result.stderr
    args = probe.read_text().splitlines()
    assert args[0] == str(root / "scripts/ci/release_publication_deadline.py")
    assert Path(args[args.index("--node") + 1]).resolve() == Path(NODE).resolve()
    owned = Path(state.read_text().strip().split("=", 1)[1])
    assert not owned.exists()
    env["STATE_owned_directory"] = str(owned)
    prior = probe.read_bytes()
    post = subprocess.run([NODE, str(action / "post.cjs")], env=env, capture_output=True, timeout=5)
    assert post.returncode == 0 and probe.read_bytes() == prior
