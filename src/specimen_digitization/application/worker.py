"""Bounded polling worker over retained runs. Engine selection remains separate."""

import argparse
import os
import time
from pathlib import Path
from .api import SYNTHETIC_TEXT, SYNTHETIC_COLLECTION, SYNTHETIC_ORG
from .domain import Principal, Scope
from .production import SqlConnectRepository, GcsBlobs, ProductionAdapters, actor_uid
from .storage import SQLiteRepository, LocalBlobs, Conflict
from .workflow import Workflow, SyntheticAdapters


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["synthetic", "production"], required=True)
    parser.add_argument(
        "--state-dir", type=Path, default=Path("/tmp/specimen-synthetic")
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--persistence", choices=["sqlite", "sql-emulator"], default="sqlite"
    )
    args = parser.parse_args()
    from ..observability import configure_observability, CaptureMode

    configure_observability(
        send_to_logfire=False if args.mode == "synthetic" else None,
        capture_mode=CaptureMode.METADATA,
    )
    if args.mode == "synthetic":
        repository = (
            SqlConnectRepository(
                project="demo-specimen-data", emulator_host="127.0.0.1:9499"
            )
            if args.persistence == "sql-emulator"
            else SQLiteRepository(args.state_dir / "state.sqlite3")
        )
        blobs = LocalBlobs(args.state_dir / "blobs")
        adapters = SyntheticAdapters(blobs, SYNTHETIC_TEXT)
        user = "synthetic-reviewer"
        memberships = [
            {
                "organization_id": SYNTHETIC_ORG,
                "collection_id": SYNTHETIC_COLLECTION,
                "role": "reviewer",
            }
        ]
    else:
        user = os.environ["SPECIMEN_WORKER_ACTOR_UID"]
        repository = SqlConnectRepository()
        blobs = GcsBlobs()
        adapters = ProductionAdapters(blobs)
        memberships = repository.memberships(user)
    workflow = Workflow(repository, blobs, adapters)
    while True:
        actor_uid.set(user)
        if args.mode == "production":
            memberships = repository.memberships(user)
        for membership in memberships:
            scope = Scope(
                organization_id=membership["organization_id"],
                collection_id=membership["collection_id"],
            )
            principal = Principal(user_id=user, scope=scope, role=membership["role"])
            for specimen in repository.list(scope):
                if specimen.run.stage in {
                    "finalized",
                    "processing_blocked",
                    "paused",
                    "cancelled",
                }:
                    continue
                try:
                    workflow.step(principal, specimen.id)
                except Conflict:
                    # Another worker won the fenced CAS; no external call follows.
                    continue
        if args.once:
            return
        time.sleep(1)


if __name__ == "__main__":
    main()
