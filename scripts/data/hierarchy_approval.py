"""Record the owner's approval of a prepared hierarchy artifact, offline (docs/execution/golive/RELEASE.md 4.5).

`summarize ARTIFACT` reads the private artifact that `bootstrap_admin.py --hierarchy` wrote and checks it as the
protected data release will: the hierarchy mode, this checkout's committed collection tree, exact regeneration from its
own values, and the worker's allow-listed collections. It prints a summary that holds no value from the artifact. Only
after the owner types APPROVE does it write two files beside the artifact, both mode 0600 and never overwritten:

- `hierarchy-approval.sha256`, the SHA-256 of the artifact's exact bytes: 64 hex digits and a newline. The owner sets
  the data-production secret DATA_BOOTSTRAP_APPROVED_SHA256 from it, and DATA_BOOTSTRAP_ARTIFACT_B64 from those bytes.
- `hierarchy-approval.json`, the time of the approval.

The release compares the artifact's digest with the approved one and never recomputes the approval. This makes no
network call, reads no credential and writes nothing else.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys

from specimen_digitization.application.pilot_manifest import read_private

_spec = importlib.util.spec_from_file_location("approval_bootstrap_admin", Path(__file__).with_name("bootstrap_admin.py"))
_admin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_admin)

MODE = "first-scope-hierarchy-bootstrap/v1"
DIGEST, RECORD = "hierarchy-approval.sha256", "hierarchy-approval.json"


class Refused(ValueError):
    """A fixed reason the approval is refused; never a value from the artifact or a path."""


def _strict(raw: bytes):
    """JSON as the release parses it: a repeated key or a non-finite number is refused."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("repeated key")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("non-finite number")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def summary(raw: bytes) -> list[str]:
    """The summary of an artifact the release would accept, without any of its values, or Refused."""
    try:
        artifact = _strict(raw)
    except ValueError:
        raise Refused("the artifact is not JSON") from None
    if not isinstance(artifact, dict) or artifact.get("schema_version") != MODE:
        raise Refused("the artifact is not a hierarchy artifact")
    try:
        # The release's own regeneration (#96): this checkout's tree at its fixed path, the artifact prepared again from
        # its values and equal to it, byte for byte once canonical.
        prepared = _admin._approved_hierarchy(artifact, artifact.get("artifact_sha256"))
    except (ValueError, OSError):
        raise Refused("the artifact does not regenerate from its own values against this checkout's collection "
                      "tree") from None
    keys = [entry["key"] for entry in prepared["hierarchy"]["collections"]]
    if not all(key in keys for key in _admin.WORKER_COLLECTION_KEYS):
        raise Refused("the worker's allow-listed collections are not all in the artifact")
    return [
        f"Mode: {MODE}.",
        f"It regenerates exactly from its own values against this checkout's {_admin.TREE_PATH}.",
        f"Collections: {len(keys)}, the reviewed tree's keys, names and parents in its order.",
        f"The administrator's collection: {prepared['hierarchy']['admin_collection_key']}.",
        f"The worker's collections: {', '.join(_admin.WORKER_COLLECTION_KEYS)}.",
        "Sensitive access: false.",
        "No identifier, identity, name or digest from the artifact is printed.",
    ]


def private_directory(path: Path) -> Path:
    """The artifact's directory, which must be yours, mode 0700 and outside Git, as write_private_artifact requires."""
    directory = path.resolve(strict=True).parent
    if any((ancestor / ".git").exists() for ancestor in (directory, *directory.parents)):
        raise Refused("the artifact's directory must be outside Git")
    info = directory.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise Refused("the artifact's directory must be yours with mode 0700")
    return directory


def write_new(path: Path, data: bytes) -> None:
    """Create the file exclusively, mode 0600; an existing file is never replaced."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def summarize(path: Path) -> int:
    """Print the summary, then record the approval only on exactly APPROVE. Returns the process exit code."""
    try:
        raw = read_private(path)
        directory = private_directory(path)
    except (ValueError, OSError):
        print("Approval refused: the artifact must be a private mode 0600 file of yours, in a mode 0700 directory "
              "outside Git.")
        return 2
    digest, record = directory / DIGEST, directory / RECORD
    if digest.exists() or digest.is_symlink() or record.exists() or record.is_symlink():
        print(f"Approval refused: {DIGEST} or {RECORD} already exists beside the artifact; it is never overwritten.")
        return 2
    try:
        lines = summary(raw)
    except Refused as reason:
        print(f"Approval refused: {reason}.")
        return 2
    print("\n".join(lines))
    print("Type APPROVE to record the SHA-256 of this artifact's exact bytes as approved; anything else writes nothing.")
    if sys.stdin.readline().rstrip("\r\n") != "APPROVE":
        print("Not approved: nothing was written.")
        return 1
    moment = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        write_new(digest, hashlib.sha256(raw).hexdigest().encode("ascii") + b"\n")
    except OSError:
        print(f"Approval refused: {DIGEST} could not be created; nothing was written.")
        return 2
    approval = {"version": "hierarchy-approval/v1", "approved_at": moment.isoformat().replace("+00:00", "Z")}
    try:
        write_new(record, json.dumps(approval, sort_keys=True).encode("ascii") + b"\n")
    except OSError:
        digest.unlink()  # this call created it exclusively a moment ago
        print(f"Approval refused: {RECORD} could not be created; nothing was kept.")
        return 2
    print(f"Approved: wrote {DIGEST} and {RECORD} beside the artifact, mode 0600. Set the data-production secret "
          f"DATA_BOOTSTRAP_APPROVED_SHA256 from {DIGEST}.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("summarize", help="summarize a private hierarchy artifact and record its approval")
    command.add_argument("artifact", type=Path, help="the private artifact bootstrap_admin.py --hierarchy wrote")
    args = parser.parse_args(argv)
    return summarize(args.artifact)


if __name__ == "__main__":
    raise SystemExit(main())
