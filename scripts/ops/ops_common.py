"""Plumbing shared by the plain ops scripts in this directory (see README.md).

Every script takes PROJECT and REGION from the environment, defaulting to the committed runtime settings
(scripts/ci/runtime_settings.py), and with DRY_RUN=1 prints each command, reads included, instead of running it.
Nothing here prints a secret value: a secret is read into the running process only.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ci"))

import runtime_settings as settings  # noqa: E402  (the committed, non-secret runtime settings)

HEX64 = re.compile(r"[0-9a-f]{64}")
SHA = re.compile(r"[0-9a-f]{40}")


def dry_run() -> bool:
    return os.environ.get("DRY_RUN", "") == "1"


def param(name: str, default: str) -> str:
    """An operator parameter from the environment; empty means the default."""
    return os.environ.get(name) or default


def project() -> str:
    return param("PROJECT", settings.PROJECT)


def region() -> str:
    return param("REGION", settings.REGION)


def committed_project() -> str:
    """PROJECT, when the committed settings name it: their accounts, bucket and URLs are used verbatim."""
    if (project(), region()) != (settings.PROJECT, settings.REGION):
        raise SystemExit("PROJECT and REGION must match scripts/ci/runtime_settings.py, whose values name them")
    return project()


def registry() -> str:
    """The Artifact Registry Docker repository the runtime images live in."""
    return f"{region()}-docker.pkg.dev/{project()}/specimen-runtime"


def checkpoint_sha256() -> str:
    """SAM_CHECKPOINT_SHA256 from the environment, else the committed digest."""
    value = os.environ.get("SAM_CHECKPOINT_SHA256") or settings.SAM_CHECKPOINT_SHA256
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        raise SystemExit("SAM_CHECKPOINT_SHA256 must be 64 lowercase hex digits (run sam_checkpoint.py first)")
    return value


def source_sha() -> str:
    """SOURCE_SHA from the environment, else the checked-out commit."""
    value = os.environ.get("SOURCE_SHA") or subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if not SHA.fullmatch(value):
        raise SystemExit("SOURCE_SHA must be a full 40-character commit SHA")
    return value


def show(argv) -> None:
    print("+ " + shlex.join(argv), flush=True)


def note(text: str) -> None:
    print("# " + text, flush=True)


def run(argv) -> None:
    """A command that changes something: printed, then run unless DRY_RUN=1. A failure stops the script."""
    show(argv)
    if dry_run():
        return
    if subprocess.run(argv, cwd=ROOT).returncode != 0:
        raise SystemExit(f"command failed: {shlex.join(argv[:4])} ...")


def read(argv) -> str | None:
    """A read-only command's stdout; None when it fails (for example, absent) or under DRY_RUN=1."""
    show(argv)
    if dry_run():
        return None
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def secret_value(argv, *, exact: bool = False) -> str | None:
    """A secret's value, for this process only. The command is printed; its output never is. None under DRY_RUN=1.

    exact=True returns the output unstripped: `gcloud secrets versions access` prints the stored value with no
    terminator, as Cloud Run hands it to a job, so surrounding whitespace is part of the value.
    """
    show(argv)
    if dry_run():
        return None
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        raise SystemExit("could not read the secret; the command's output is withheld")
    return result.stdout if exact else result.stdout.strip()


def pinned_secret(name: str) -> str:
    """`name:version`, the version pinned in runtime_settings.SECRET_VERSIONS."""
    version = settings.SECRET_VERSIONS.get(name)
    if type(version) is not int or version < 1:
        raise SystemExit(f"runtime_settings.SECRET_VERSIONS must pin {name}")
    return f"{name}:{version}"
