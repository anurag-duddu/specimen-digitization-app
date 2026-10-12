#!/usr/bin/env python3
"""Classify whether a pull request needs the complete Python test collection.

The optimization is deliberately narrow. Only Flutter application files and
the append-only session log may use the focused Python contract gate. Every
other path, an empty diff, an unrecognized event, or a failed diff requires the
complete suite. Pushes to ``main`` and manual workflow runs are therefore full
by construction.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import re
import subprocess


FRONTEND_PREFIX = "apps/specimen_digitization/"
FRONTEND_COMPANION_FILES = frozenset({"docs/SESSION_LEARNINGS.md"})
SHA = re.compile(r"[0-9a-f]{40}")


def _safe_path(path: str) -> bool:
    parsed = PurePosixPath(path)
    return bool(path) and not parsed.is_absolute() and ".." not in parsed.parts


def requires_full_python(paths: list[str]) -> tuple[bool, list[str]]:
    """Return a fail-closed decision and the paths that require the full suite."""
    if not paths:
        return True, ["<empty-diff>"]
    unsafe = [path for path in paths if not _safe_path(path)]
    if unsafe:
        return True, unsafe
    full = [path for path in paths
            if not path.startswith(FRONTEND_PREFIX)
            and path not in FRONTEND_COMPANION_FILES]
    return bool(full), full


def changed_paths(base: str, head: str) -> list[str]:
    """Read both sides of renames so moving a backend file cannot look frontend-only."""
    if not SHA.fullmatch(base) or not SHA.fullmatch(head):
        raise ValueError("pull-request base and head must be full commit SHAs")
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", base, head],
        check=True,
        capture_output=True,
    )
    return [item.decode("utf-8", errors="strict")
            for item in result.stdout.split(b"\0") if item]


def classify(event: str, base: str, head: str) -> tuple[bool, list[str]]:
    if event != "pull_request":
        return True, [f"<{event or 'missing-event'}>"]
    paths = changed_paths(base, head)
    return requires_full_python(paths)


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
