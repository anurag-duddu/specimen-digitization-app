"""Generation-bound reads of objects under a registered source prefix.

Upload completion proves declared-equals-actual because a client declared the
metadata first and the server checked the uploaded bytes against it. Here the
server is the only reader, so the equivalent proof is the generation binding:
every read carries a precondition on the object's *current* generation, and
bytes are returned only when that generation is still the one the inventory
recorded. Pinning a read to a historical generation would prove only "these are
that version's bytes"; it would not prove the object is unchanged, which is the
claim an import actually depends on.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Protocol

from .blob_limits import ORIGINAL_BYTES, read_limited
from .storage import Missing

GENERATION_PATTERN = r"^[1-9][0-9]*$"


class SourceObjectChanged(ValueError):
    """The object is not the object the inventory recorded. Never import it."""


class SourceUnavailable(RuntimeError):
    """The source could not be read. This is operational, not a refusal."""


class SourceReader(Protocol):
    def list_objects(self, bucket: str, prefix: str, limit: int) -> list[dict]: ...
    def current_generation(self, bucket: str, object_name: str) -> str: ...
    def read(self, bucket: str, object_name: str, generation: str) -> bytes: ...


def valid_generation(generation) -> str:
    import re

    if not isinstance(generation, str) or not re.fullmatch(
        GENERATION_PATTERN, generation
    ):
        raise ValueError("Object generation must be a positive integer")
    return generation


def sniff_media_type(data: bytes) -> str:
    """Read only enough of the header to name the format; never decode pixels."""
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as image:
            return Image.MIME.get(image.format) or "application/octet-stream"
    except Exception:
        return "application/octet-stream"


class LocalSourceReader:
    """Filesystem-backed source for synthetic and local operation.

    An object's generation is its modification time in nanoseconds: it changes
    whenever the bytes are rewritten, which is the property the binding needs.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, bucket: str, object_name: str) -> Path:
        base = (self.root / bucket).resolve()
        if any(part in {"", ".", ".."} for part in object_name.split("/")):
            raise Missing("Invalid object identifier")
        target = (base / object_name).resolve()
        if base != target and base not in target.parents:
            raise Missing("Object lies outside its bucket")
        return target

    def _generation(self, path: Path) -> str:
        try:
            info = os.stat(path)
        except OSError as exc:
            raise Missing("Source object unavailable") from exc
        if not os.path.isfile(path) or info.st_mtime_ns <= 0:
            raise Missing("Source object unavailable")
        return str(info.st_mtime_ns)

    def list_objects(self, bucket: str, prefix: str, limit: int) -> list[dict]:
        base = (self.root / bucket).resolve()
        root = (base / prefix).resolve()
        if not root.is_dir():
            return []
        rows = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            name = prefix + str(path.relative_to(root))
            rows.append(
                {
                    "object_name": name,
                    "generation": self._generation(path),
                    "size_bytes": path.stat().st_size,
                    "crc32c": None,
                    "md5_hash": None,
                }
            )
            if len(rows) > limit:
                return rows
        return rows

    def current_generation(self, bucket: str, object_name: str) -> str:
        return self._generation(self._path(bucket, object_name))

    def read(self, bucket: str, object_name: str, generation: str) -> bytes:
        valid_generation(generation)
        path = self._path(bucket, object_name)
        if self._generation(path) != generation:
            raise SourceObjectChanged(
                "Source object generation no longer matches the inventory"
            )
        with path.open("rb") as stream:
            data = read_limited(stream.read, ORIGINAL_BYTES)
        # Re-read the generation so a write racing this read cannot be admitted.
        if self._generation(path) != generation:
            raise SourceObjectChanged(
                "Source object changed while it was being read"
            )
        return data


class GcsSourceReader:
    """Cloud Storage source, read with an `ifGenerationMatch` precondition."""

    def __init__(self, client=None, project="specimen-digitization"):
        from google.cloud import storage

        self.client = client or storage.Client(project=project)

    def list_objects(self, bucket: str, prefix: str, limit: int) -> list[dict]:
        from .worker_deadline import deadline_call

        rows, seen = [], 0
        iterator = deadline_call(
            self.client.list_blobs, bucket, prefix=prefix, max_results=limit + 1
        )
        for blob in iterator:
            if blob.name.endswith("/") or blob.size is None:
                continue
            rows.append(
                {
                    "object_name": blob.name,
                    "generation": str(blob.generation),
                    "size_bytes": int(blob.size),
                    "crc32c": blob.crc32c,
                    "md5_hash": blob.md5_hash,
                }
            )
            seen += 1
            if seen > limit:
                break
        rows.sort(key=lambda row: row["object_name"])
        return rows

    def current_generation(self, bucket: str, object_name: str) -> str:
        from .worker_deadline import deadline_call

        blob = self.client.bucket(bucket).get_blob(object_name)
        if blob is None:
            raise Missing("Source object unavailable")
        deadline_call(blob.reload)
        return str(blob.generation)

    def read(self, bucket: str, object_name: str, generation: str) -> bytes:
        from urllib.parse import quote

        from .blob_limits import BlobTooLarge
        from .worker_deadline import deadline_call

        valid_generation(generation)
        url = (
            "https://storage.googleapis.com/storage/v1/b/"
            + quote(bucket, safe="")
            + "/o/"
            + quote(object_name, safe="")
        )
        response = deadline_call(
            self.client._http.get,
            url,
            # ifGenerationMatch, not generation: this admits the bytes only while
            # the live object still is the generation the inventory recorded.
            params={"alt": "media", "ifGenerationMatch": generation},
            stream=True,
            headers={"Accept-Encoding": "identity"},
            allow_redirects=False,
            timeout=30,
        )
        with response:
            if response.status_code == 412:
                raise SourceObjectChanged(
                    "Source object generation no longer matches the inventory"
                )
            if response.status_code == 404:
                raise Missing("Source object unavailable")
            if response.status_code != 200:
                raise SourceUnavailable("object_storage_unavailable")
            declared = response.headers.get("Content-Length")
            if declared is not None:
                try:
                    declared = int(declared)
                except ValueError as exc:
                    raise SourceUnavailable("invalid_object_length") from exc
                if declared < 0:
                    raise SourceUnavailable("invalid_object_length")
                if declared > ORIGINAL_BYTES:
                    raise BlobTooLarge("Source object exceeds the intake byte limit")
            return read_limited(
                lambda count: deadline_call(
                    response.raw.read, count, decode_content=False
                ),
                ORIGINAL_BYTES,
            )
