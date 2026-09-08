"""Private, externally pinned authority for the explicitly approved ten-specimen pilot.

This module performs no network I/O, provisioning, import, or inference. It
validates the internal structure of an independently approved binding artifact;
it does not prove source reads or imports occurred. The external pin is required.
Runtime launch policy must separately authorize spending and identity.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Generation = Annotated[str, Field(pattern=r"^[1-9][0-9]*$")]
PositiveSize = Annotated[int, Field(strict=True, gt=0)]


class PrivateManifestError(ValueError):
    """Sanitized rejection: never include paths, identity or source material."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Selection(StrictModel):
    order: Literal["explicit_source_order"]
    source_inventory_sha256: SHA256


class SourceObject(StrictModel):
    bucket: str = Field(min_length=3, max_length=222, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    object_name: str = Field(min_length=1, max_length=1024)
    generation: Generation
    sha256: SHA256
    size_bytes: PositiveSize
    crc32c: str | None = Field(default=None, pattern=r"^[A-Za-z0-9+/]{6}==$" )
    md5_hash: str | None = Field(default=None, pattern=r"^[A-Za-z0-9+/]{22}==$" )

    @model_validator(mode="after")
    def no_control_characters(self):
        if any(ord(c) < 32 or ord(c) == 127 for c in self.object_name):
            raise ValueError("Invalid object identifier")
        return self


class ApplicationSource(StrictModel):
    blob_ref: str = Field(pattern=r"^[0-9a-f]{64}:[1-9][0-9]*$")
    sha256: SHA256
    size_bytes: PositiveSize
    source_object_index: int = Field(strict=True, ge=0)


class PilotSpecimen(StrictModel):
    ordinal: int = Field(strict=True, ge=1, le=10)
    specimen_id: str
    organization_id: str
    collection_id: str
    source_objects: tuple[SourceObject, ...] = Field(min_length=1)
    application_source: ApplicationSource

    @model_validator(mode="after")
    def immutable_binding(self):
        for value in (self.specimen_id, self.organization_id, self.collection_id):
            if str(UUID(value)) != value:
                raise ValueError("Scope and specimen identifiers must be canonical UUIDs")
        app = self.application_source
        if app.source_object_index >= len(self.source_objects):
            raise ValueError("Application source index out of range")
        source = self.source_objects[app.source_object_index]
        if (source.sha256, source.size_bytes) != (app.sha256, app.size_bytes):
            raise ValueError("Source and application identity mismatch")
        if app.blob_ref.split(":", 1)[0] != app.sha256:
            raise ValueError("Application reference digest mismatch")
        return self


class PilotManifest(StrictModel):
    schema_version: Literal["specimen-pilot/v1"]
    status: Literal["ready"]
    project_id: Literal["specimen-digitization"]
    authorization_reference: str = Field(min_length=1, max_length=512)
    selection: Selection
    specimens: tuple[PilotSpecimen, ...] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def exact_authorized_scope(self):
        if [s.ordinal for s in self.specimens] != list(range(1, 11)):
            raise ValueError("Preserve the exact source order")
        if len({s.specimen_id for s in self.specimens}) != 10:
            raise ValueError("Ten distinct specimens required")
        if len({(s.organization_id, s.collection_id) for s in self.specimens}) != 1:
            raise ValueError("Pilot requires one explicitly authorized collection scope")
        objects = [
            (o.bucket, o.object_name, o.generation)
            for s in self.specimens for o in s.source_objects
        ]
        if len(objects) != len(set(objects)):
            raise ValueError("Source object generation assigned more than once")
        if len({s.application_source.blob_ref for s in self.specimens}) != 10:
            raise ValueError("Application source assigned more than once")
        return self


def _outside_git(path: Path) -> None:
    if any((parent / ".git").exists() for parent in path.resolve().parents):
        raise PrivateManifestError("Private manifests must remain outside Git")


def read_private(path: Path, expected_sha256: str | None = None) -> bytes:
    """Read one bounded regular file without following a final-component symlink."""
    _outside_git(path)
    if expected_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise PrivateManifestError("Invalid external manifest hash")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
                raise PrivateManifestError("Private manifest must be a mode 0600 regular file")
            if info.st_uid != os.getuid():
                raise PrivateManifestError("Private manifest owner mismatch")
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise PrivateManifestError("Private manifest too large")
        if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise PrivateManifestError("External manifest hash mismatch")
        return raw
    except OSError:
        raise PrivateManifestError("Private manifest unavailable") from None


def write_private(path: Path, payload: object) -> str:
    """Create exclusively: freezing never overwrites an earlier authority."""
    _outside_git(path)
    raw = (json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        raise PrivateManifestError("Private output unavailable or already exists") from None
    return hashlib.sha256(raw).hexdigest()


def load_ready_manifest(path: Path, expected_sha256: str) -> PilotManifest:
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise PrivateManifestError("External manifest hash required")
    try:
        return PilotManifest.model_validate_json(read_private(path, expected_sha256))
    except PrivateManifestError:
        raise
    except ValueError:
        raise PrivateManifestError("Ready pilot manifest validation failed") from None
