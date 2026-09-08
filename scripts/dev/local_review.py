#!/usr/bin/env python3
"""macOS supervised, loopback-only synthetic review. Never deploys resources."""

import argparse
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def review_root(value):
    root = Path(value).expanduser().resolve()
    if root == REPO or REPO in root.parents:
        raise ValueError("Review state and credentials must be outside the repository")
    return root


def labels(root):
    suffix = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    return {
        role: f"org.fieldmuseum.specimen-review-{suffix}-{role}"
        for role in ("api", "web")
    }


def job(root, role):
    result = subprocess.run(
        ["launchctl", "list", labels(root)[role]], capture_output=True, text=True
    )
    if result.returncode:
        return None
    if str(SCRIPT) not in result.stdout or str(root) not in result.stdout:
        raise ValueError("Refusing to change a supervisor job with a different owner")
    return result.stdout


def private_token(root):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / "token"
    if path.is_symlink():
        raise ValueError("Token file must not be a symlink")
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(fd, "w") as stream:
            stream.write(secrets.token_urlsafe(24))
    token = path.read_text().strip()
    if not token:
        raise ValueError("Existing token is empty; it was not replaced")
    if path.stat().st_mode & 0o077:
        raise ValueError("Existing token permissions must be private (chmod 600)")
    return token


def config(root):
    return json.loads((root / "runner.json").read_text())


def write_access(root, info):
    token = private_token(root)
    note = (
        "# Private local synthetic review\n\n"
        f"URL: http://localhost:{info['web_port']}\n"
        f"API: http://127.0.0.1:{info['api_port']}\n"
        f"Source: {info['source_sha']}\n"
        "Email: reviewer@example.test\n"
        f"Fixture token: {token}\n\n"
        "This local fixture bearer is not a Firebase or provider credential. "
        "Do not put it in a URL, Git, or chat.\n\n"
        f"Clipboard shortcut for the operator: `pbcopy < {root / 'token'}`\n\n"
        f"Runner: {SCRIPT}\n"
        f"Review directory: {root}\n"
        "Actions: start, status, stop, rebuild; pass --review-dir with the directory above.\n"
        "launchd jobs survive task completion within this login session. "
        "No reboot/login installation or backup is configured. stop preserves data.\n"
    )
    path = root / "ACCESS.md"
    if path.is_symlink():
        raise ValueError("Access note must not be a symlink")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(note)
    path.chmod(0o600)


def build(root, api_port, web_port):
    private_token(root)
    python = REPO / ".venv/bin/python"
    if not python.exists():
        raise ValueError("Run uv sync --frozen in the repository first")
    app = REPO / "apps/specimen_digitization"
    target = app / "lib/firebase_options.dart"
    placeholder = (app / "lib/firebase_options.ci.dart").read_bytes()
    if target.is_symlink() or (target.exists() and target.read_bytes() != placeholder):
        raise ValueError("Refusing to overwrite existing Firebase configuration")
    created = not target.exists()
    if created:
        with target.open("xb") as stream:
            stream.write(placeholder)
    try:
        defines = {
            "SPECIMEN_API_BASE_URL": f"http://127.0.0.1:{api_port}",
            "SPECIMEN_LOCAL_SYNTHETIC": "true",
        }
        with (root / "build.log").open("w") as log:
            run(
                [
                    "flutter",
                    "build",
                    "web",
                    "--release",
                    "--pwa-strategy=none",
                    *[f"--dart-define={key}={value}" for key, value in defines.items()],
                ],
                cwd=app,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
    finally:
        if created and target.exists() and target.read_bytes() == placeholder:
            target.unlink()
    artifact = Path(tempfile.mkdtemp(prefix="web-", dir=root))
    shutil.copytree(app / "build/web", artifact, dirs_exist_ok=True)
    sha = run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    dirty = bool(
        run(
            ["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True
        ).stdout
    )
    info = {
        "source_sha": sha,
        "worktree_dirty_at_build": dirty,
        "mode": "synthetic",
        "api_port": api_port,
        "web_port": web_port,
        "api_base_url": f"http://127.0.0.1:{api_port}",
        "artifact": str(artifact),
        "main_js_sha256": hashlib.sha256(
            (artifact / "main.dart.js").read_bytes()
        ).hexdigest(),
        "production": False,
    }
    (artifact / "local-review.json").write_text(json.dumps(info, indent=2) + "\n")
    (root / "runner.json").write_text(json.dumps(info, indent=2) + "\n")
    write_access(root, info)
    return info


def stop(root):
    for role in ("web", "api"):
        if job(root, role) is not None:
            run(["launchctl", "remove", labels(root)[role]])
            print(f"{role}: removed owned job; retained state unchanged")


def start(root, info):
    for role in ("api", "web"):
        if job(root, role) is not None:
            print(f"{role}: already registered; unchanged")
            continue
        for attempt in range(25):
            try:
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", info[f"{role}_port"]))
                break
            except OSError:
                if attempt == 24:
                    raise
                time.sleep(0.2)
        run(
            [
                "launchctl",
                "submit",
                "-l",
                labels(root)[role],
                "-o",
                str(root / f"{role}.log"),
                "-e",
                str(root / f"{role}-error.log"),
                "--",
                str(REPO / ".venv/bin/python"),
                str(SCRIPT),
                f"_serve-{role}",
                "--review-dir",
                str(root),
            ]
        )
        print(f"{role}: registered with launchd")
    print(f"Local synthetic review: http://localhost:{info['web_port']}")
    print(f"Private login instructions: {root / 'ACCESS.md'}")


def status(root):
    info = config(root)
    for role in ("api", "web"):
        print(f"{role} supervisor registered: {job(root, role) is not None}")
    with urllib.request.urlopen(
        f"http://localhost:{info['web_port']}/local-review.json", timeout=5
    ) as response:
        marker = json.load(response)
        if marker != info:
            raise ValueError("Served marker differs from prepared artifact")
        print(
            f"web: {response.status}; source: {marker['source_sha']}; mode: {marker['mode']}"
        )
    request = urllib.request.Request(
        info["api_base_url"] + "/v1/session",
        headers={"Authorization": "Bearer " + private_token(root)},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        session = json.load(response)
        if session.get("mode") != "synthetic":
            raise ValueError("Expected explicit synthetic API")
        print(f"authorized API: {response.status}; synthetic")


def serve(root, role):
    info = config(root)
    if role == "api":
        import uvicorn
        from specimen_digitization.application.api import create_app, SYNTHETIC_TEXT
        from specimen_digitization.application.storage import (
            LocalBlobs,
            SQLiteRepository,
        )
        from specimen_digitization.application.workflow import SyntheticAdapters
        from specimen_digitization.observability import (
            configure_observability,
            CaptureMode,
        )

        configure_observability(
            send_to_logfire=False, capture_mode=CaptureMode.METADATA
        )
        state = root / "state"
        blobs = LocalBlobs(state / "blobs")
        app = create_app(
            mode="synthetic",
            repository=SQLiteRepository(state / "state.sqlite3"),
            blobs=blobs,
            adapters=SyntheticAdapters(blobs, SYNTHETIC_TEXT),
            token=private_token(root),
            origins=[
                f"http://localhost:{info['web_port']}",
                f"http://127.0.0.1:{info['web_port']}",
            ],
        )
        uvicorn.run(app, host="127.0.0.1", port=info["api_port"], access_log=False)
    else:

        class NoCacheHandler(SimpleHTTPRequestHandler):
            def end_headers(self):
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                super().end_headers()

            def log_message(self, *args):
                pass

        ThreadingHTTPServer(
            ("127.0.0.1", info["web_port"]),
            partial(NoCacheHandler, directory=info["artifact"]),
        ).serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["start", "status", "stop", "rebuild", "_serve-api", "_serve-web"],
    )
    parser.add_argument("--review-dir", required=True)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--web-port", type=int, default=3000)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error(
            "This supervised runner requires macOS launchd; see HANDOFF.md for manual commands"
        )
    if (
        not (1024 <= args.api_port <= 65535 and 1024 <= args.web_port <= 65535)
        or args.api_port == args.web_port
    ):
        parser.error("Choose distinct unprivileged loopback ports")
    root = review_root(args.review_dir)
    if args.action.startswith("_serve-"):
        serve(root, args.action.removeprefix("_serve-"))
    elif args.action == "stop":
        stop(root)
    elif args.action == "status":
        status(root)
    else:
        existing = (root / "runner.json").exists()
        if args.action == "rebuild" or not existing:
            info = build(root, args.api_port, args.web_port)
            if args.action == "rebuild":
                stop(root)
        else:
            info = config(root)
        start(root, info)


if __name__ == "__main__":
    main()
