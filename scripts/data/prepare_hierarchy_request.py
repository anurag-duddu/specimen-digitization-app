"""Mint one canonical UUID per reviewed collection; write only a private request.

This makes no cloud call, reads no credential and prepares no transaction. It
turns the reviewed public tree into the private request skeleton that
`bootstrap_admin.py --hierarchy` consumes, so the identifiers are chosen once,
offline, and never appear in the repository. Review the tree in Git; keep the
minted identifiers in the private file this writes.
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import uuid


ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("hierarchy_bootstrap_admin", Path(__file__).with_name("bootstrap_admin.py"))
_admin = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_admin)


def build_request(
    *,
    tree: bytes,
    organization_name: str,
    requested_email: str,
    requested_uid: str,
    admin_collection_key: str,
    organization_id: str | None = None,
    mint=None,
) -> dict[str, object]:
    """Return the private request skeleton; one fresh UUID per reviewed entry."""
    mint = (lambda: str(uuid.uuid4())) if mint is None else mint
    reviewed = _admin.tree_entries(tree)
    if not 1 <= len(reviewed) <= 64:
        raise ValueError("The reviewed tree must carry between one and 64 collections")
    collections = []
    for entry in reviewed:
        if not isinstance(entry, dict) or set(entry) != {"key", "name", "parent"}:
            raise ValueError("Unknown reviewed collection tree document")
        collections.append({"key": entry["key"], "id": _admin._identifier(mint()),
                            "name": entry["name"], "parent": entry["parent"]})
    if admin_collection_key not in {entry["key"] for entry in collections}:
        raise ValueError("The administrator's collection must be one of the reviewed keys")
    return {
        "requested_email": requested_email,
        "requested_uid": requested_uid,
        "organization_id": _admin._identifier(mint() if organization_id is None else organization_id),
        "organization_name": _admin._bounded_name(organization_name),
        "collections": collections,
        "admin_collection_key": admin_collection_key,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", type=Path, default=ROOT / _admin.TREE_PATH,
                        help="Reviewed public collection tree; defaults to the committed repository file")
    parser.add_argument("--organization-name", required=True, help="The organization's display name")
    parser.add_argument("--organization-id", default=None, help="Optional canonical UUID; one is minted when absent")
    parser.add_argument("--requested-email", required=True, help="The already approved owner's exact email address")
    parser.add_argument("--requested-uid", required=True, help="That account's Firebase UID")
    parser.add_argument("--admin-collection-key", required=True, help="The reviewed key the administrator is a member of")
    parser.add_argument("--output", type=Path, required=True, help="New private file outside Git; parent mode0700")
    args = parser.parse_args()
    try:
        request = build_request(
            tree=Path(args.tree).read_bytes(), organization_name=args.organization_name,
            organization_id=args.organization_id, requested_email=args.requested_email,
            requested_uid=args.requested_uid, admin_collection_key=args.admin_collection_key,
        )
        _admin.write_private_artifact(args.output, request)
    except (ValueError, TypeError, OSError):
        # Do not echo the minted identifiers, the owner's identity or the path.
        parser.exit(2, "Hierarchy request refused: check the reviewed tree, identity and private output requirements.\n")
    print("Minted a private hierarchy request skeleton; no cloud calls or transactions prepared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
