#!/usr/bin/env python3
"""Classify whether a pull request needs the complete Python test collection.

Focused execution is disabled until transitive contract closure is proved.
Even with that proof, only recognized Flutter source additions/modifications
and the append-only session log could qualify. Unsafe statuses, lockfiles,
unknown paths, malformed diffs and non-PR events require the complete suite.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import NamedTuple

from python_contract_closure import focused_contracts_qualified


FRONTEND_PREFIX = "apps/specimen_digitization/"
FRONTEND_COMPANION_FILES = frozenset({"docs/SESSION_LEARNINGS.md"})
SHA = re.compile(r"[0-9a-f]{40}")


class Change(NamedTuple):
    status: str
    paths: tuple[str, ...]


def _safe_path(path: str) -> bool:
    # Check the raw spelling: PurePosixPath normalizes away '.' and '//'.
    return (bool(path) and "\\" not in path
            and all(ord(char) >= 32 and ord(char) != 127 for char in path)
            and all(part not in {"", ".", ".."} for part in path.split("/")))


def _lockfile(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return (".lock" in name or "-lock" in name or name.startswith("lock.")
            or name in {"lock", "npm-shrinkwrap.json", "package.resolved", "go.sum"})


def _known_frontend_source(path: str) -> bool:
    if not path.startswith(FRONTEND_PREFIX) or not path.endswith(".dart"):
        return False
    parts = PurePosixPath(path.removeprefix(FRONTEND_PREFIX)).parts
    return ((len(parts) >= 2 and parts[0] in {"lib", "test", "integration_test"})
            or (len(parts) >= 4 and parts[0] == "packages"
                and parts[2] in {"lib", "test", "integration_test"}))


def requires_full_python(paths: list[str]) -> tuple[bool, list[str]]:
    """Return a fail-closed decision and the paths that require the full suite."""
    if not paths:
        return True, ["<empty-diff>"]
    unsafe = [path for path in paths if not _safe_path(path)]
    if unsafe:
        return True, unsafe
    full = [path for path in paths if _lockfile(path)
            or (not _known_frontend_source(path) and path not in FRONTEND_COMPANION_FILES)]
    if full:
        return True, full
    if not focused_contracts_qualified():
        return True, ["<focused-contract-closure-unproven>"]
    return False, []


def parse_name_status(data: bytes) -> list[Change]:
    """Parse Git's NUL name/status format without discarding status or move sides."""
    if not data:
        return []
    if not data.endswith(b"\0"):
        raise ValueError("truncated name/status diff")
    fields = data[:-1].split(b"\0")
    entries = []
    index = 0
    while index < len(fields):
        status = fields[index].decode("ascii", errors="strict")
        index += 1
        if status in {"A", "M", "D", "T", "U", "X", "B"}:
            count = 1
        elif re.fullmatch(r"[RC][0-9]{3}", status) and int(status[1:]) <= 100:
            count = 2
        else:
            raise ValueError(f"unrecognized diff status: {status!r}")
        if index + count > len(fields):
            raise ValueError("truncated name/status record")
        paths = tuple(field.decode("utf-8", errors="strict") for field in fields[index:index + count])
        if not all(_safe_path(path) for path in paths):
            raise ValueError("unsafe name/status path")
        entries.append(Change(status, paths))
        index += count
    return entries


def changed_entries(base: str, head: str) -> list[Change]:
    """Keep D+A moves visible; also validate both sides of any R/C record."""
    if (not SHA.fullmatch(base) or not SHA.fullmatch(head)
            or base == "0" * 40 or head == "0" * 40):
        raise ValueError("pull-request base and head must be full commit SHAs")
    result = subprocess.run(
        ["git", "diff", "--name-status", "--no-renames", "-z", base, head],
        check=True,
        capture_output=True,
    )
    return parse_name_status(result.stdout)


def classify(event: str, base: str, head: str) -> tuple[bool, list[str]]:
    if event != "pull_request":
        return True, [f"<{event or 'missing-event'}>"]
    try:
        entries = changed_entries(base, head)
    except (OSError, UnicodeError, ValueError, subprocess.SubprocessError) as error:
        # The optimization is optional. An unreadable identity or comparison
        # must select the complete suite, not turn the classifier into a gate
        # failure whose safe intent is only implicit.
        return True, [f"<comparison-failed:{type(error).__name__}>"]
    unsafe = [path for entry in entries if entry.status not in {"A", "M"} for path in entry.paths]
    if unsafe:
        return True, unsafe
    return requires_full_python([path for entry in entries for path in entry.paths])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event", required=True)
    parser.add_argument("--base", default="")
    parser.add_argument("--head", default="")
    parser.add_argument("--output", type=Path,
                        default=Path(os.environ["GITHUB_OUTPUT"]) if os.environ.get("GITHUB_OUTPUT") else None)
    args = parser.parse_args(argv)

    full, reasons = classify(args.event, args.base, args.head)
    decision = "true" if full else "false"
    print(f"Python test scope: {'full collection' if full else 'focused frontend contracts'}")
    for reason in reasons:
        print(f"  {reason}")
    if args.output is not None:
        with args.output.open("a", encoding="utf-8") as stream:
            stream.write(f"full={decision}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
