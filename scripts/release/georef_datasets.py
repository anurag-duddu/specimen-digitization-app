#!/usr/bin/env python3
"""Publish the ten pinned georeferencing reference files from Data release only.

The public GitHub release assets are named by the manifest SHA-256. This
workflow copies their exact bytes into the runtime bucket with GCS's
ifGenerationMatch=0 create precondition; an existing object is verified and
never overwritten.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Protocol
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from specimen_digitization.application.georef_datasets import (  # noqa: E402
    MANIFEST,
    Dataset,
    DigestMismatch,
    verified,
)

BUCKET = "specimen-digitization.firebasestorage.app"
ASSET_ROOT = (
    "https://github.com/anurag-duddu/specimen-digitization-app/releases/download/"
    "georef-reference-20261004"
)
GCS_ROOT = "https://storage.googleapis.com"
HTTP_TIMEOUT = (10, 120)
CHUNK_SIZE = 64 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT_SHA = re.compile(r"[0-9a-f]{40}")


class PublicationFailure(RuntimeError):
    """A dataset could not be safely verified or published."""


class PublicResponse(Protocol):
    status_code: int
    headers: dict[str, str]

    def raise_for_status(self) -> None: ...

    def iter_content(self, chunk_size: int) -> object: ...

    def close(self) -> None: ...


class PublicHttp(Protocol):
    def get(self, url: str, **kwargs: object) -> PublicResponse: ...


class Storage(Protocol):
    def read_object(self, name: str, expected_size: int) -> bytes | None: ...

    def create_if_absent(self, name: str, content_type: str, data: bytes) -> bool: ...


def checkout_sha() -> str:
    """Read the commit that actions/checkout placed in this worktree."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise PublicationFailure("could not read the checked-out commit")
    return result.stdout.strip()


def require_data_release(env: dict[str, str], checked_out: str) -> None:
    """Refuse local runs, non-main refs, another workflow, or a different SHA."""
    if env.get("GITHUB_ACTIONS") != "true":
        raise PublicationFailure("dataset publication runs only in GitHub Actions Data release")
    if env.get("GITHUB_REF") != "refs/heads/main":
        raise PublicationFailure("dataset publication requires refs/heads/main")
    if env.get("GITHUB_WORKFLOW") != "Data release":
        raise PublicationFailure("dataset publication requires the Data release workflow")
    sha = env.get("GITHUB_SHA", "")
    if not COMMIT_SHA.fullmatch(sha) or checked_out != sha:
        raise PublicationFailure("GITHUB_SHA must match the checked-out commit")


def asset_url(entry: Dataset) -> str:
    if not SHA256.fullmatch(entry.sha256):
        raise PublicationFailure(f"{entry.id}: the manifest SHA-256 is malformed")
    return f"{ASSET_ROOT}/{entry.sha256}.bin"


def _read_bounded(response: PublicResponse, maximum: int) -> bytes:
    """Keep at most maximum+1 bytes in memory, even if a server ignores length."""
    data = bytearray()
    for part in response.iter_content(chunk_size=CHUNK_SIZE):
        if not isinstance(part, (bytes, bytearray)) or not part:
            continue
        remaining = maximum + 1 - len(data)
        if remaining <= 0:
            break
        data.extend(part[:remaining])
        if len(data) > maximum:
            break
    return bytes(data)


def download_dataset(http: PublicHttp, entry: Dataset) -> bytes:
    url = asset_url(entry)
    response = http.get(url, stream=True, timeout=HTTP_TIMEOUT)
    try:
        response.raise_for_status()
        length = response.headers.get("Content-Length")
        if length is not None and (not length.isdecimal() or int(length) > entry.size):
            raise PublicationFailure(f"{entry.id}: release asset exceeds the manifest size")
        data = _read_bounded(response, entry.size)
    finally:
        response.close()
    try:
        return verified(entry, data)
    except DigestMismatch as error:
        raise PublicationFailure(f"{entry.id}: release asset does not match its manifest size and SHA-256") from error


class GoogleStorage:
    """Minimal GCS JSON API adapter over the workflow's authenticated session."""

    def __init__(self, session: object, bucket: str = BUCKET):
        self.session = session
        self.bucket = bucket

    def _object_url(self, name: str) -> str:
        return f"{GCS_ROOT}/storage/v1/b/{quote(self.bucket, safe='')}/o/{quote(name, safe='')}"

    def read_object(self, name: str, expected_size: int) -> bytes | None:
        metadata = self.session.get(  # type: ignore[attr-defined]
            self._object_url(name), params={"fields": "size,generation,name"}, timeout=HTTP_TIMEOUT
        )
        if metadata.status_code == 404:
            return None
        if not 200 <= metadata.status_code < 300:
            raise PublicationFailure(f"GCS could not inspect {name} (HTTP {metadata.status_code})")
        try:
            info = metadata.json()
            actual_size = int(info["size"])
        except (ValueError, TypeError, KeyError):
            raise PublicationFailure(f"GCS returned invalid metadata for {name}") from None
        if actual_size != expected_size:
            raise PublicationFailure(f"existing object {name} has size {actual_size}, expected {expected_size}")
        body = self.session.get(  # type: ignore[attr-defined]
            f"{GCS_ROOT}/download/storage/v1/b/{quote(self.bucket, safe='')}/o/{quote(name, safe='')}",
            params={"alt": "media"},
            headers={"Range": f"bytes=0-{expected_size}"},
            stream=True,
            timeout=HTTP_TIMEOUT,
        )
        try:
            if not 200 <= body.status_code < 300:
                raise PublicationFailure(f"GCS could not read existing object {name} (HTTP {body.status_code})")
            return _read_bounded(body, expected_size)
        finally:
            body.close()

    def create_if_absent(self, name: str, content_type: str, data: bytes) -> bool:
        response = self.session.post(  # type: ignore[attr-defined]
            f"{GCS_ROOT}/upload/storage/v1/b/{quote(self.bucket, safe='')}/o",
            params={"uploadType": "media", "name": name, "ifGenerationMatch": "0"},
            data=data,
            headers={"Content-Type": content_type},
            timeout=HTTP_TIMEOUT,
        )
        if response.status_code in {409, 412}:
            return False
        if not 200 <= response.status_code < 300:
            raise PublicationFailure(f"GCS could not create {name} (HTTP {response.status_code})")
        return True


def publish(
    http: PublicHttp,
    storage: Storage,
    manifest: tuple[Dataset, ...] = MANIFEST,
    emit=print,
) -> None:
    if len(manifest) != 10 or len({entry.object_name for entry in manifest}) != 10:
        raise PublicationFailure("the georeferencing manifest must contain ten unique datasets")
    for entry in manifest:
        data = download_dataset(http, entry)
        existing = storage.read_object(entry.object_name, entry.size)
        if existing is not None:
            try:
                verified(entry, existing)
            except DigestMismatch as error:
                raise PublicationFailure(f"existing object {entry.object_name} does not match the manifest") from error
            emit(f"dataset {entry.id}: already present and verified")
            continue
        if storage.create_if_absent(entry.object_name, entry.content_type, data):
            emit(f"dataset {entry.id}: created and verified source bytes")
            continue
        # A writer may have won between the read and create. Never retry as an overwrite.
        raced = storage.read_object(entry.object_name, entry.size)
        if raced is None:
            raise PublicationFailure(f"object {entry.object_name} raced creation but cannot be read back")
        try:
            verified(entry, raced)
        except DigestMismatch as error:
            raise PublicationFailure(f"racing object {entry.object_name} does not match the manifest") from error
        emit(f"dataset {entry.id}: appeared concurrently and verified")


def main() -> int:
    try:
        require_data_release(dict(os.environ), checkout_sha())
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        publish(requests.Session(), GoogleStorage(AuthorizedSession(credentials)))
    except PublicationFailure as error:
        print(f"georeferencing datasets failed: {error}", file=sys.stderr, flush=True)
        return 1
    except Exception as error:  # avoid dumping credential-bearing transport details into logs
        print(f"georeferencing datasets failed: {type(error).__name__}", file=sys.stderr, flush=True)
        return 1
    print("georeferencing datasets complete", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
