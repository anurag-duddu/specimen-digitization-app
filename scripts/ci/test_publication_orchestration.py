"""Private stage handoff and promotion tests; effects are explicit local fakes."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import release_publication_deadline as M
from test_release_admission import packet as admission_packet
from test_release_context import valid_context
from test_release_google import credential as synthetic_credential


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    packet = admission_packet("runtime-build")
    packet["identity"]["provider"] = packet["identity"]["provider"].replace("runtime-build-release", "runtime-build")
    packet["expires_at_unix"] = 150
    env = valid_context("runtime-build")
    env.update(RUNNER_TEMP=str(tmp_path), GITHUB_RUN_ID="456", GITHUB_RUN_ATTEMPT="1",
        ACTIONS_ID_TOKEN_REQUEST_URL="https://synthetic.actions.githubusercontent.com/token?api-version=2.0",
        ACTIONS_ID_TOKEN_REQUEST_TOKEN="synthetic-only", GITHUB_OUTPUT=str(tmp_path / "public-output"))
    (tmp_path / "public-output").write_text("")
    directory = tmp_path / "runtime-build"
    directory.mkdir()
    path = directory / "packet.json"
    raw = json.dumps(packet)
    path.write_text(raw)
    path.chmod(0o600)
    env["RELEASE_PACKET_SHA256"] = hashlib.sha256(raw.encode()).hexdigest()
    owned = tmp_path / "specimen-publication-test"
    owned.mkdir(mode=0o700)
    M.private_write(owned / "owner.json", json.dumps({"version": 1, "run_id": "456", "attempt": "1"}))
    args = SimpleNamespace(owned=owned, packet=path, role="api", output=tmp_path / "api.json", node="unused",
                           auth_source=tmp_path / "unused-auth-source")
    clock = [100.0]
    deadline = M.Deadline(150, wall=lambda: clock[0], mono=lambda: clock[0])
    monkeypatch.setattr(M, "Deadline", lambda expires: deadline)
    monkeypatch.setattr(M, "verify_bundles", lambda source: None)
    monkeypatch.setattr(M.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=(M.AUTH_SHA + "\n").encode()))
    calls = []
    hook = {"auth": lambda: None}
    def stage(self, command, *, env: dict, cwd, stage, limit):
        self.deadline.remaining()
        calls.append(stage)
        if stage == "auth":
            cred = owned / "auth/gha-creds-synthetic.json"
            M.private_write(cred, json.dumps(synthetic_credential(env, packet)))
            output = Path(env["GITHUB_OUTPUT"])
            values = {"credentials_file_path": str(cred), "project_id": "specimen-digitization", "auth_token": "synthetic-private-output"}
            output.write_text("".join(f"{k}<<fixed_{i}\n{v}\nfixed_{i}\n" for i, (k, v) in enumerate(values.items())))
            hook["auth"]()
        if stage == "publish":
            assert env["GOOGLE_GHA_CREDS_PATH"] == str(owned / "auth/gha-creds-synthetic.json")
            assert json.loads(env["RELEASE_PUBLICATION_GUARD"])["monotonic_end"] == deadline.end
            value = {"version": "runtime-image/v1", "role": "api", "source_sha": packet["source_sha"],
                     "run_id": 456, "run_attempt": 1, "reference": "us-east4-docker.pkg.dev/specimen-digitization/specimen-runtime/api@sha256:" + "a" * 64}
            M.private_write(owned / "candidate.json", json.dumps(value))
    monkeypatch.setattr(M.Supervisor, "run_owned", stage)
    cleanup = []
    monkeypatch.setattr(M, "dispose", lambda owned, env, node, source, credential: cleanup.append(credential))
    return args, env, clock, calls, hook, cleanup


def test_valid_private_auth_output_handoff_promotes_only_image_outputs(scenario):
    args, env, _, calls, _, cleanup = scenario
    M.run_release(args, env)
    assert calls == ["admission", "auth", "publish"]
    assert args.output.exists()
    public = Path(env["GITHUB_OUTPUT"]).read_text()
    assert public.startswith("image=us-east4-docker.pkg.dev/") and "digest=sha256:" in public
    assert "synthetic-private-output" not in public
    assert not (args.owned / "auth-output").exists()
    assert cleanup == [args.owned / "auth/gha-creds-synthetic.json"]


def test_late_auth_result_does_not_start_publisher(scenario):
    args, env, clock, calls, hook, cleanup = scenario
    hook["auth"] = lambda: clock.__setitem__(0, 145)
    with pytest.raises(M.PublicationStopped):
        M.run_release(args, env)
    assert calls == ["admission", "auth"]
    assert not args.output.exists() and Path(env["GITHUB_OUTPUT"]).read_text() == ""
    assert cleanup


def test_output_write_that_crosses_cutoff_is_not_a_success(scenario, monkeypatch):
    args, env, clock, _, _, _ = scenario
    original = M.private_write
    def delayed(path, value, **kwargs):
        original(path, value, **kwargs)
        if path == args.output:
            clock[0] = 155
    monkeypatch.setattr(M, "private_write", delayed)
    with pytest.raises(M.PublicationStopped):
        M.run_release(args, env)
    assert not args.output.exists()
    assert Path(env["GITHUB_OUTPUT"]).read_text() == ""


def test_endpoint_override_stops_before_all_stages(scenario):
    args, env, _, calls, _, _ = scenario
    env["GHA_ENDPOINT_OVERRIDE_sts"] = "https://not-permitted.invalid"
    with pytest.raises(ValueError, match="endpoint override"):
        M.run_release(args, env)
    assert calls == []


def test_failed_public_receipt_fsync_removes_only_the_created_file(scenario, monkeypatch):
    args, env, _, _, _, cleanup = scenario
    original = M.os.fsync
    def failed(fd):
        if args.output.exists() and M.os.fstat(fd).st_ino == args.output.stat().st_ino:
            raise OSError("synthetic receipt fsync failure")
        original(fd)
    monkeypatch.setattr(M.os, "fsync", failed)
    with pytest.raises(OSError, match="synthetic receipt"):
        M.run_release(args, env)
    assert not args.output.exists()
    assert Path(env["GITHUB_OUTPUT"]).read_text() == ""
    assert cleanup


def test_preexisting_public_receipt_is_preserved(scenario):
    args, env, _, _, _, cleanup = scenario
    args.output.write_text("existing independent receipt\n")
    prior_output = b"independent=value\n\xff\n"
    Path(env["GITHUB_OUTPUT"]).write_bytes(prior_output)
    with pytest.raises(FileExistsError):
        M.run_release(args, env)
    assert args.output.read_text() == "existing independent receipt\n"
    assert Path(env["GITHUB_OUTPUT"]).read_bytes() == prior_output
    assert cleanup


@pytest.mark.parametrize("fault", ["late_close", "failed_close", "partial_write"])
def test_failed_final_output_preserves_prior_bytes_and_remote_unknown(scenario, monkeypatch, fault):
    args, env, clock, _, _, cleanup = scenario
    output = Path(env["GITHUB_OUTPUT"])
    prior_output = b"independent=value\n\xff\n"
    output.write_bytes(prior_output)
    original = Path.open
    class FaultyOutput:
        def __enter__(self):
            self.handle = original(output, "a")
            return self
        def fileno(self):
            return self.handle.fileno()
        def write(self, value):
            if fault == "partial_write":
                self.handle.write(value[:19])
                self.handle.flush()
                raise OSError("synthetic partial output failure")
            return self.handle.write(value)
        def __exit__(self, *exc):
            self.handle.close()
            if fault == "late_close":
                clock[0] = 155
            elif fault == "failed_close":
                raise OSError("synthetic output close failure")
    def opening(path, mode="r", *args, **kwargs):
        if path == output and mode == "a":
            return FaultyOutput()
        return original(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", opening)
    with pytest.raises(M.PublicationStopped if fault == "late_close" else OSError):
        M.run_release(args, env)
    assert output.read_bytes() == prior_output
    assert not args.output.exists()
    record = json.loads((args.output.parent / "runtime-publication-api.json").read_text())
    assert record["outcome"] == "unknown"
    assert cleanup


@pytest.mark.parametrize("substitute", ["file", "symlink"])
def test_replaced_append_descriptor_preserves_independent_files(scenario, monkeypatch, substitute):
    args, env, _, _, _, cleanup = scenario
    output = Path(env["GITHUB_OUTPUT"])
    prior, foreign = b"independent-original\n", b"independent-replacement\n"
    output.write_bytes(prior)
    saved, other = output.with_name("saved-original"), output.with_name("foreign")
    other.write_bytes(foreign)
    actual = Path.open
    def opening(path, mode="r", *args, **kwargs):
        if path == output and mode == "a":
            path.rename(saved)
            if substitute == "symlink":
                path.symlink_to(other)
            else:
                path.write_bytes(foreign)
        return actual(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", opening)
    with pytest.raises((OSError, ValueError)):
        M.run_release(args, env)
    assert saved.read_bytes() == prior
    assert other.read_bytes() == foreign and output.read_bytes() == foreign
    assert not args.output.exists()
    record = json.loads((args.output.parent / "runtime-publication-api.json").read_text())
    assert record["outcome"] == "unknown" and cleanup
