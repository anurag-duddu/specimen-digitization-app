"""Fixed protected publisher supervisor; no cloud credentials in the parent.

The packet's original deadline covers admission, pinned auth (including all
upstream retries/redirects), and publication. Unknown outcomes are never replayed.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
import faulthandler
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time

from release_admission import private_bytes, read_packet, require, strict_json
from release_context import PROJECT, validate_context

ROOT = Path(__file__).resolve().parents[2]
AUTH_SHA = "7c6bc770dae815cd3e89ee6cdf493a5fab2cc093"  # pragma: allowlist secret (public upstream commit)
BUNDLE_HASHES = {
    "main": "9f4584c50974e46628292feacae77eaa4bf4b49bb529a154a9321fcefe0c226f",  # pragma: allowlist secret (public bundle hash)
    "post": "6b49c062009deebaaec487cfafd706c1838c2b6bb549398ca34c218831752647",  # pragma: allowlist secret (public bundle hash)
}
STOP_RESERVE = 10.0
TERM_GRACE = 2.0
OBSERVE_GRACE = 2.0
POLL = .02
PREFIX = "specimen-publication-"
CURRENT = None
BOUND_PACKET = None


class PublicationStopped(ValueError):
    """A terminal local failure; remote outcome may still be unknown."""


class Deadline:
    def __init__(self, expires, *, wall=time.time, mono=time.monotonic, end=None):
        require(type(expires) in (int, float) and math.isfinite(expires), "invalid publication deadline")
        self.expires, self.wall, self.mono = expires, wall, mono
        self.end = mono() + (expires - wall()) if end is None else end
        require(type(self.end) in (int, float) and math.isfinite(self.end), "invalid monotonic deadline")

    def remaining(self, cap=None):
        remaining = min(self.expires - self.wall(), self.end - self.mono()) - STOP_RESERVE
        if remaining <= 0:
            raise PublicationStopped("original publication work deadline reached")
        return remaining if cap is None else min(cap, remaining)


def frozen_packet(path, env):
    packet = read_packet(path, env)
    require(packet.get("plane") == "runtime-build", "only the fixed publisher is supervised")
    validate_context(env, "runtime-build", packet.get("source_sha", ""))
    require(type(packet.get("expires_at_unix")) is int, "integer packet deadline required")
    for field, key in (("release_run_id", "GITHUB_RUN_ID"), ("release_run_attempt", "GITHUB_RUN_ATTEMPT")):
        value = packet.get(field)
        require(type(value) is int and 1 <= value <= 2**53 and str(value) == env.get(key),
                "publisher run identity changed")
    return packet


def bind_child(packet):
    global CURRENT, BOUND_PACKET
    raw = os.environ.get("RELEASE_PUBLICATION_GUARD", "")
    control = strict_json(raw)
    require(set(control) == {"parent_pid", "packet_sha256", "expires_at_unix", "monotonic_end"}, "invalid publisher control")
    require(os.getppid() == control["parent_pid"] and os.getpgrp() == os.getpid()
            and os.getsid(0) == os.getpid(), "publisher has no owned supervisor group")
    require(control["packet_sha256"] == os.environ.get("RELEASE_PACKET_SHA256")
            and control["expires_at_unix"] == packet["expires_at_unix"], "original publisher packet changed")
    deadline = Deadline(packet["expires_at_unix"], end=control["monotonic_end"])
    deadline.remaining()
    CURRENT, BOUND_PACKET = deadline, packet
    return deadline


def publication_budget(packet=None, cap=None):
    require(CURRENT is not None, "publisher requires the original deadline supervisor")
    if packet is not None:
        require(packet == BOUND_PACKET, "original publisher packet changed")
    return CURRENT.remaining(cap)


class RequestExpired(RuntimeError):
    pass


@contextmanager
def total_request(seconds):
    """Soft interrupt plus C hard exit; the outside parent still owns children."""
    require(threading.current_thread() is threading.main_thread() and 0 < seconds <= 30,
            "invalid publisher request budget")
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
            and signal.SIGALRM not in signal.pthread_sigmask(signal.SIG_BLOCK, [])
            and signal.SIGALRM not in signal.sigpending(), "publisher cannot replace a foreign alarm")
    end, previous = time.monotonic() + seconds, signal.getsignal(signal.SIGALRM)
    margin = min(1, seconds / 10)
    def expired(*_):
        raise RequestExpired("publisher request deadline reached")
    with open(os.devnull, "w") as sink:
        signal.signal(signal.SIGALRM, expired)
        try:
            remaining = end - time.monotonic()
            require(remaining > margin, "publisher request budget exhausted")
            faulthandler.dump_traceback_later(remaining, file=sink, exit=True)
            signal.setitimer(signal.ITIMER_REAL, remaining - margin)
            yield
            if time.monotonic() >= end - margin:
                raise RequestExpired("publisher request completed too late")
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            faulthandler.cancel_dump_traceback_later()
            signal.signal(signal.SIGALRM, previous)


def process_group_alive(group):
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False


def become_subreaper():
    # Adopt/reap orphaned fixed descendants on the Linux protected runner.
    if sys.platform == "linux":
        require(ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0, "cannot own orphaned publisher children")


class Supervisor:
    def __init__(self, deadline, record=None):
        self.deadline, self.record = deadline, record
        self.events, self.last_group = [], None
        self.cancelled = False
        become_subreaper()

    def event(self, event, stage, *, persist=True, **facts):
        self.events.append({"event": event, "stage": stage, "at_unix": time.time(), **facts})
        if self.record and persist:
            self.record(self.events)

    def cancel(self, *_):
        self.cancelled = True

    def reap(self, proc):
        proc.poll()
        if sys.platform == "linux" and proc.returncode is not None:
            while True:
                try:
                    pid, _ = os.waitpid(-proc.pid, os.WNOHANG)
                    if not pid:
                        break
                except ChildProcessError:
                    break

    def stop(self, proc, stage):
        self.reap(proc)
        if process_group_alive(proc.pid):
            self.event("signal_term", stage, group=proc.pid, persist=False)
            os.killpg(proc.pid, signal.SIGTERM)
        end = time.monotonic() + TERM_GRACE
        while process_group_alive(proc.pid) and time.monotonic() < end:
            self.reap(proc)
            time.sleep(POLL)
        if process_group_alive(proc.pid):
            self.event("signal_kill", stage, group=proc.pid, persist=False)
            os.killpg(proc.pid, signal.SIGKILL)
        end = time.monotonic() + OBSERVE_GRACE
        while process_group_alive(proc.pid) and time.monotonic() < end:
            self.reap(proc)
            time.sleep(POLL)
        self.reap(proc)
        gone = not process_group_alive(proc.pid)
        self.event("group_observed", stage, group=proc.pid, terminated=gone, persist=False)
        return gone

    def run_owned(self, command, *, env, cwd, stage, limit):
        budget = self.deadline.remaining(limit)
        if self.cancelled:
            raise PublicationStopped("publisher cancelled before launch")
        self.event("intent", stage)
        # No credential-capable code executes until its ownership is durable.
        read_gate, write_gate = os.pipe()
        try:
            launch = ["/bin/sh", "-c", 'IFS= read -r publication_gate <&"$PUBLICATION_GATE_FD" || exit 1; exec "$@"',
                      "publication-child", *command]
            proc = subprocess.Popen(launch, env={**env, "PUBLICATION_GATE_FD": str(read_gate)}, cwd=cwd,
                start_new_session=True, pass_fds=(read_gate,), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except BaseException:
            os.close(write_gate)
            raise
        finally:
            os.close(read_gate)
        self.last_group = proc.pid
        end = time.monotonic() + budget
        try:
            self.event("started", stage, group=proc.pid)
            self.deadline.remaining()
            if self.cancelled:
                raise PublicationStopped("publisher cancelled before execution")
            os.write(write_gate, b"go\n")
            os.close(write_gate)
            write_gate = None
            while True:
                self.deadline.remaining()
                if self.cancelled or time.monotonic() >= end:
                    raise PublicationStopped("publisher stage cancelled or expired")
                status = proc.poll()
                if status is not None:
                    if status != 0 or process_group_alive(proc.pid):
                        raise PublicationStopped("publisher failed or left an owned descendant")
                    self.event("completed", stage, group=proc.pid)
                    return
                time.sleep(POLL)
        except BaseException:
            self.stop(proc, stage)
            if self.record:
                self.record(self.events)
            raise
        finally:
            if write_gate is not None:
                os.close(write_gate)


def private_write(path, value, *, exclusive=True):
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_EXCL if exclusive else os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        # O_EXCL above establishes ownership; never unlink an existing receipt.
        if exclusive:
            path.unlink(missing_ok=True)
        raise


def finalize_outputs(path, value, deadline):
    """Append through close under the cutoff; undo only our known suffix."""
    identity = None
    def existing(name, flags):
        fd = os.open(name, (flags & ~os.O_CREAT) | os.O_NOFOLLOW)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or identity is not None and (info.st_dev, info.st_ino) != identity:
            os.close(fd)
            raise PublicationStopped("runner output file identity changed")
        return fd
    with open(path, "rb", opener=existing) as handle:
        info = os.fstat(handle.fileno())
        identity = (info.st_dev, info.st_ino)
        before = handle.read(1048577)
    require(len(before) <= 1048576, "runner output file exceeds bound")
    suffix = value.encode("utf-8")
    try:
        deadline.remaining()
        info = path.lstat()
        require((info.st_dev, info.st_ino) == identity, "runner output file identity changed")
        with path.open("a", encoding="utf-8") as handle:
            info = os.fstat(handle.fileno())
            require(stat.S_ISREG(info.st_mode) and (info.st_dev, info.st_ino) == identity,
                    "runner append descriptor changed")
            require(handle.write(value) == len(value), "incomplete runner output append")
        deadline.remaining()
    except BaseException:
        # Preserve all original bytes, and fail closed if another writer changed
        # the file. Never unlink or overwrite an independent output or receipt.
        with open(path, "r+b", opener=existing) as handle:
            current = handle.read(len(before) + len(suffix) + 1)
            require(current.startswith(before) and suffix.startswith(current[len(before):]),
                    "runner output changed outside the owned append")
            handle.truncate(len(before))
        raise


def auth_outputs(path):
    try:
        raw = private_bytes(path, 65536).decode("utf-8")
        lines, result, at = raw.splitlines(), {}, 0
        while at < len(lines):
            line = lines[at]
            at += 1
            match = re.fullmatch(r"([a-z_]+)<<([A-Za-z0-9_-]+)", line)
            require(match is not None, "invalid private auth output command")
            key, delimiter = match.groups()
            require(key in {"credentials_file_path", "project_id", "auth_token"} and key not in result,
                    "unexpected or duplicate private auth output")
            start = at
            while at < len(lines) and lines[at] != delimiter:
                at += 1
            require(at == start + 1 and at < len(lines) and lines[start], "invalid private auth output value")
            result[key] = lines[start]
            at += 1
        require(set(result) == {"credentials_file_path", "project_id", "auth_token"}, "incomplete private auth output")
        result.pop("auth_token")  # Never export this normal upstream intermediate token.
        return result
    finally:
        path.unlink(missing_ok=True)


def auth_environment(env, packet, owned):
    require(not any(key.startswith("GHA_ENDPOINT_OVERRIDE_") for key in env), "inherited auth endpoint override rejected")
    result = {key: value for key, value in env.items() if not key.startswith("INPUT_")}
    for key in ("NODE_OPTIONS", "NODE_PATH", "GOOGLE_GHA_CREDS_PATH", "GOOGLE_APPLICATION_CREDENTIALS",
                "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE", "GITHUB_STATE"):
        result.pop(key, None)
    defaults = {
        "project_id": PROJECT, "workload_identity_provider": packet["identity"]["provider"],
        "service_account": f"specimen-runtime-build@{PROJECT}.iam.gserviceaccount.com", "audience": "",
        "credentials_json": "", "create_credentials_file": "true", "export_environment_variables": "false",
        "token_format": "", "delegates": "", "universe": "googleapis.com", "request_reason": "",
        "cleanup_credentials": "true", "access_token_lifetime": "3600s",
        "access_token_scopes": "https://www.googleapis.com/auth/cloud-platform", "access_token_subject": "",
        "id_token_audience": "", "id_token_include_email": "false",
    }
    result.update({"INPUT_" + key.upper(): value for key, value in defaults.items()})
    result.update(GITHUB_WORKSPACE=str(owned / "auth"), GITHUB_OUTPUT=str(owned / "auth-output"),
                  GITHUB_ENV=str(owned / "auth-env"), GITHUB_PATH=str(owned / "auth-path"))
    return result


def validate_owned(path, env):
    temp = Path(env["RUNNER_TEMP"]).resolve(strict=True)
    require(path.parent == temp and path.name.startswith(PREFIX) and not path.is_symlink(), "foreign owned directory")
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
            "unsafe owned directory")
    owner = strict_json(private_bytes(path / "owner.json", 4096))
    require(owner == {"version": 1, "run_id": env["GITHUB_RUN_ID"], "attempt": env["GITHUB_RUN_ATTEMPT"]},
            "owned directory belongs to another invocation")
    return path


def verify_bundles(source):
    require(source.resolve() == ROOT / ".release-tools/google-auth" and not source.is_symlink(), "foreign auth source")
    for part, expected in BUNDLE_HASHES.items():
        path = source / "dist" / part / "index.js"
        require(path.resolve().is_relative_to(source) and not path.is_symlink()
                and hashlib.sha256(path.read_bytes()).hexdigest() == expected, "pinned auth bundle changed")


def dispose(owned, env, node, source, credential=None):
    validate_owned(owned, env)
    if credential is not None:
        require(credential.parent == owned / "auth" and not credential.is_symlink()
                and re.fullmatch(r"gha-creds-[a-zA-Z0-9-]+\.json", credential.name), "foreign local cleanup target")
        post_env = auth_environment(env, {"identity": {"provider": "unused-local-cleanup"}}, owned)
        post_env["GOOGLE_GHA_CREDS_PATH"] = str(credential)
        # Exact pinned post performs only local deletion. It never exchanges tokens.
        proc = subprocess.Popen([node, str(source / "dist/post/index.js")], env=post_env,
                                start_new_session=True, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=2)
    shutil.rmtree(owned)


def run_release(args, env):
    owned = validate_owned(args.owned, env)
    packet = frozen_packet(args.packet, env)
    deadline = Deadline(packet["expires_at_unix"])
    deadline.remaining()
    require(args.role in {"api", "worker", "sam"}, "unknown publisher role")
    temp = Path(env["RUNNER_TEMP"]).resolve()
    require(args.packet.resolve() == temp / "runtime-build/packet.json"
            and args.output == temp / f"{args.role}.json", "foreign publisher paths")
    verify_bundles(args.auth_source)
    child_env = auth_environment(env, packet, owned)  # Reject overrides BEFORE any upstream code.
    child_env.update(RELEASE_PUBLICATION_GUARD=json.dumps({"parent_pid": os.getpid(),
        "packet_sha256": env["RELEASE_PACKET_SHA256"], "expires_at_unix": packet["expires_at_unix"],
        "monotonic_end": deadline.end}))
    for name in ("auth", "docker"):
        (owned / name).mkdir(mode=0o700)
    for name in ("auth-output", "auth-env", "auth-path", "admission-output", "source-output", "publisher-output"):
        private_write(owned / name, "")
    private_write(owned / "docker/config.json", "{}\n")
    receipt_path = temp / f"runtime-publication-{args.role}.json"
    record = {"version": "runtime-publication-attempt/v1", "packet_sha256": env["RELEASE_PACKET_SHA256"],
              "source_sha": packet["source_sha"], "run_id": packet["release_run_id"],
              "run_attempt": packet["release_run_attempt"], "role": args.role,
              "tag": f"sha-{packet['source_sha']}-{packet['release_run_id']}-{packet['release_run_attempt']}",
              "expires_at_unix": packet["expires_at_unix"], "outcome": "not_started", "events": [],
              "request_counts": "not_observed_do_not_assume_one_exchange",
              "upstream_retry_configuration": {"oidc_internal_max_retries": 10, "oidc_outer_retries": 3,
                  "google_max_retries": 3, "google_max_redirects": 5}}
    private_write(receipt_path, json.dumps(record, sort_keys=True) + "\n")
    def retain(events):
        record["events"] = events
        private_write(receipt_path, json.dumps(record, sort_keys=True) + "\n", exclusive=False)
    supervisor = Supervisor(deadline, retain)
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in previous:
        signal.signal(sig, supervisor.cancel)
    credential = None
    promoted = False
    try:
        # The existing full live GitHub/source/budget admission runs without Google credentials.
        admission_env = {**env, "GITHUB_OUTPUT": str(owned / "admission-output")}
        for key in ("GOOGLE_GHA_CREDS_PATH", "GOOGLE_APPLICATION_CREDENTIALS", "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE"):
            admission_env.pop(key, None)
        supervisor.run_owned([sys.executable, str(ROOT / "scripts/ci/deploy_runtime.py"), "--plane", "runtime-build",
            "--admit", "--packet", str(args.packet)], env=admission_env, cwd=ROOT, stage="admission", limit=180)
        require(frozen_packet(args.packet, env) == packet, "original publisher packet changed")
        # Verify the exact upstream checkout, without invoking arbitrary source helpers.
        result = subprocess.run(["git", "-C", str(args.auth_source), "rev-parse", "HEAD"],
                                capture_output=True, timeout=deadline.remaining(5), check=True)
        require(result.stdout.decode().strip() == AUTH_SHA, "upstream auth commit changed")
        record["outcome"] = "unknown"
        retain(supervisor.events)
        supervisor.run_owned([args.node, str(args.auth_source / "dist/main/index.js")],
                             env=child_env, cwd=ROOT, stage="auth", limit=120)
        values = auth_outputs(owned / "auth-output")
        require(values["project_id"] == PROJECT, "upstream project changed")
        candidate_credential = Path(values["credentials_file_path"])
        require(candidate_credential.parent == owned / "auth"
                and re.fullmatch(r"gha-creds-[a-zA-Z0-9-]+\.json", candidate_credential.name)
                and not candidate_credential.is_symlink(), "foreign upstream credential path")
        credential = candidate_credential
        from release_google import github_credential_bytes, validate_credentials
        validate_credentials(strict_json(github_credential_bytes(credential)), packet, env)
        publisher_env = {**env, "RELEASE_PUBLICATION_GUARD": child_env["RELEASE_PUBLICATION_GUARD"],
                         "DOCKER_CONFIG": str(owned / "docker"), "GITHUB_OUTPUT": str(owned / "publisher-output")}
        for key in ("NODE_OPTIONS", "NODE_PATH", "DOCKER_AUTH_CONFIG", "DOCKER_CONTEXT", "DOCKER_HOST"):
            publisher_env.pop(key, None)
        publisher_env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
        for key in ("GOOGLE_GHA_CREDS_PATH", "GOOGLE_APPLICATION_CREDENTIALS", "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE"):
            publisher_env[key] = str(credential)
        supervisor.run_owned([sys.executable, str(ROOT / "scripts/ci/deploy_runtime.py"), "--plane", "runtime-build",
            "--publish-role", args.role, "--packet", str(args.packet), "--output", str(owned / "candidate.json")],
            env=publisher_env, cwd=ROOT, stage="publish", limit=3600)
        deadline.remaining()
        require(frozen_packet(args.packet, env) == packet, "original publisher packet changed")
        candidate = strict_json(private_bytes(owned / "candidate.json", 8192))
        expected = {"version": "runtime-image/v1", "role": args.role, "source_sha": packet["source_sha"],
                    "run_id": packet["release_run_id"], "run_attempt": packet["release_run_attempt"]}
        require(set(candidate) == set(expected) | {"reference"}
                and all(candidate[k] == v for k, v in expected.items()), "image receipt identity changed")
        image = f"us-east4-docker.pkg.dev/{PROJECT}/specimen-runtime/{args.role}"
        require(re.fullmatch(re.escape(image) + r"@sha256:[a-f0-9]{64}", candidate["reference"]), "foreign image digest")
        deadline.remaining()
        private_write(args.output, json.dumps(candidate, sort_keys=True) + "\n")
        promoted = True
        deadline.remaining()
        finalize_outputs(Path(env["GITHUB_OUTPUT"]),
                         f"image={image}\ndigest={candidate['reference'].split('@')[1]}\n", deadline)
        record["outcome"] = "published"
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if promoted and record["outcome"] != "published":
            args.output.unlink(missing_ok=True)
        try:
            retain(supervisor.events)
        finally:
            dispose(owned, env, args.node, args.auth_source, credential)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", required=True)
    parser.add_argument("--auth-source", required=True, type=Path)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--owned", required=True, type=Path)
    parser.add_argument("--role", required=True, choices=["api", "worker", "sam"])
    try:
        run_release(parser.parse_args(), dict(os.environ))
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError):
        raise SystemExit("Publication stopped; reconcile the retained non-secret attempt without replay.") from None


if __name__ == "__main__":
    main()
