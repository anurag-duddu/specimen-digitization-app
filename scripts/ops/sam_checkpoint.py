#!/usr/bin/env python3
"""Put the pinned SAM 3 checkpoint where the SAM 3 service mounts it, and print its digest.

    uv run --frozen python scripts/ops/sam_checkpoint.py

Runs on the operator's machine: about 3.4 GB down from Hugging Face and 3.4 GB up to Cloud Storage, into a
temporary directory that is removed on exit. The digest is computed exactly as SAM 3 verifies it at start-up
(sam3_server.checkpoint_files_digest), and the files land at
gs://<BUCKET>/application/sha256/<digest>/sam3-cache/hub/models--facebook--sam3/snapshots/<revision>/, the Hugging
Face cache layout that HF_HOME=/model-cache resolves offline.

Idempotent. When the digest is known (SAM_CHECKPOINT_SHA256, else runtime_settings) and every file of the pinned
revision is already stored at that prefix with its Hub size, nothing is downloaded. Otherwise it downloads, refuses
a digest that differs from the known one, and uploads only what is missing or different (rsync, by checksum).

The Hugging Face token is read from Secret Manager (huggingface-runtime-token, at the version
runtime_settings.SECRET_VERSIONS pins for the runtime, never "latest") only when a download is needed, held in this
process and passed to the downloader; it is never printed and never written to disk.

Parameters (environment): PROJECT, BUCKET, SAM_CHECKPOINT_SHA256, WORK_DIR (where the temporary directory is made;
needs about 7 GB free), DRY_RUN=1.
"""
from __future__ import annotations

import os
from pathlib import Path
import signal
import sys
import tempfile

import ops_common as ops
from specimen_digitization.hub_models import SAM3_MODEL

PATTERNS = ["*.json", "*.safetensors", "*.txt"]  # Sam3Engine's allow_patterns; SAM 3 serves only these files.
TOKEN_SECRET = "huggingface-runtime-token"  # pragma: allowlist secret (secret name, not a value)


def snapshot_prefix(bucket: str, digest: str) -> str:
    folder = "models--" + SAM3_MODEL.repo_id.replace("/", "--")
    return f"gs://{bucket}/application/sha256/{digest}/sam3-cache/hub/{folder}/snapshots/{SAM3_MODEL.revision}/"


def hub_files(token) -> dict[str, int]:
    """{path: size} of the pinned revision's files that SAM 3 loads, as the Hub lists them."""
    from huggingface_hub import HfApi
    from huggingface_hub.hf_api import RepoFile
    from huggingface_hub.utils import filter_repo_objects

    tree = [item for item in HfApi().list_repo_tree(SAM3_MODEL.repo_id, revision=SAM3_MODEL.revision,
                                                     recursive=True, token=token) if isinstance(item, RepoFile)]
    return {item.path: item.size for item in filter_repo_objects(tree, allow_patterns=PATTERNS, key=lambda i: i.path)}


def stored_files(bucket: str, digest: str) -> dict[str, int] | None:
    """{path: size} stored under the digest's snapshot prefix; None under DRY_RUN=1."""
    import json

    prefix = snapshot_prefix(bucket, digest)
    out = ops.read(["gcloud", "storage", "objects", "list", prefix + "**", f"--project={ops.project()}",
                    "--format=json"])
    if out is None:
        return None if ops.dry_run() else {}
    start = prefix[len(f"gs://{bucket}/"):]
    return {item["name"][len(start):]: int(item["size"]) for item in json.loads(out or "[]")
            if item.get("name", "").startswith(start)}


def holds(stored: dict[str, int] | None, wanted: dict[str, int]) -> bool:
    return bool(wanted) and stored is not None and all(stored.get(path) == size for path, size in wanted.items())


def download(token: str, cache_dir: Path) -> Path:
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(repo_id=SAM3_MODEL.repo_id, revision=SAM3_MODEL.revision,
                                  allow_patterns=PATTERNS, cache_dir=str(cache_dir), token=token))


def local_files(snapshot: Path) -> dict[str, int]:
    return {path.relative_to(snapshot).as_posix(): path.stat().st_size
            for path in sorted(snapshot.rglob("*")) if path.is_file()}


def main() -> int:
    from specimen_digitization.application.sam3_server import checkpoint_files_digest

    project, dry = ops.project(), ops.dry_run()
    bucket = ops.param("BUCKET", f"{project}.firebasestorage.app")
    known = os.environ.get("SAM_CHECKPOINT_SHA256") or ops.settings.SAM_CHECKPOINT_SHA256
    if known is not None and not (isinstance(known, str) and ops.HEX64.fullmatch(known)):
        raise SystemExit("SAM_CHECKPOINT_SHA256 must be 64 lowercase hex digits")
    version = ops.pinned_secret(TOKEN_SECRET).rsplit(":", 1)[1]  # The version the worker's HF_TOKEN reads.
    token_command = ["gcloud", "secrets", "versions", "access", version, f"--secret={TOKEN_SECRET}",
                     f"--project={project}"]
    ops.note(f"checkpoint {SAM3_MODEL.repo_id}@{SAM3_MODEL.revision}, files {' '.join(PATTERNS)}")

    if dry:
        if known:
            stored_files(bucket, known)
        ops.secret_value(token_command)
        ops.note(f"download {SAM3_MODEL.repo_id}@{SAM3_MODEL.revision} into a temporary Hugging Face cache")
        ops.show(["gcloud", "storage", "rsync", "<temporary snapshot directory>", snapshot_prefix(bucket, known or
                  "<digest>"), "--recursive", "--no-ignore-symlinks", "--checksums-only", f"--project={project}"])
        print(known or "<digest>")
        return 0

    # SIGTERM unwinds like an error, so the temporary directory is removed on every exit path.
    previous = signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        return fetch(project, bucket, known, token_command, checkpoint_files_digest)
    finally:
        signal.signal(signal.SIGTERM, previous)


def fetch(project, bucket, known, token_command, checkpoint_files_digest) -> int:
    with tempfile.TemporaryDirectory(prefix="sam3-checkpoint-", dir=os.environ.get("WORK_DIR") or None) as work:
        # Set before huggingface_hub is imported, so its own caches stay inside the temporary directory too.
        os.environ["HF_HOME"] = str(Path(work, "hf-home"))
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        token = None
        try:
            wanted = hub_files(False)  # The gated repository's file list is public.
        except Exception:
            token = ops.secret_value(token_command)
            wanted = hub_files(token)
        if not wanted:
            raise SystemExit("the pinned revision lists no checkpoint files")
        if known and holds(stored_files(bucket, known), wanted):
            ops.note("already present and complete; nothing downloaded or uploaded")
            print(known)
            return 0
        if token is None:
            token = ops.secret_value(token_command)
        snapshot = download(token, Path(work, "hub"))
        token = None
        _, digest = checkpoint_files_digest(snapshot)
        if known and digest != known:
            raise SystemExit("the downloaded checkpoint's digest differs from SAM_CHECKPOINT_SHA256; nothing uploaded")
        files = local_files(snapshot)
        if not holds(files, wanted):
            raise SystemExit("the download is incomplete; nothing uploaded")
        prefix = snapshot_prefix(bucket, digest)
        if holds(stored_files(bucket, digest), files):
            ops.note("already present and complete; nothing uploaded")
        else:
            # HF cache entries are symlinks into blobs/; upload what they point to.
            ops.run(["gcloud", "storage", "rsync", str(snapshot), prefix, "--recursive", "--no-ignore-symlinks",
                     "--checksums-only", f"--project={project}"])
            if not holds(stored_files(bucket, digest), files):
                raise SystemExit("the upload is incomplete; re-run this script")
    print(digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
