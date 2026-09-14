"""Administrator-registered storage prefixes a collection may ingest from.

A source is configuration, not a resource. Nothing here creates, edits or
deletes one, and no route does either: `docs/DEPLOYMENT.md` records that neither
bootstrap mode creates a generic runtime signup or collection-creation API, and
naming a bucket prefix a collection may read is the same class of decision. The
registry is supplied to the process at construction beside identity, membership
and origins. A reviewer selects within a registered source and never names a
bucket; a runtime configured with none has none.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .storage import Missing

# Formats the from-source import path can verify on its own. HEIC and DNG need
# the optional codec path that upload completion uses; a source declaring them
# is refused at registration rather than discovered at import.
SUPPORTED_MEDIA_TYPES = ("image/jpeg", "image/png", "image/tiff")

Uuid = Annotated[str, Field(min_length=36, max_length=36)]


def canonical_uuid(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("Scope and source identifiers must be canonical UUIDs")
    return value


def utc_instant(value: str) -> str:
    from .search import utc

    return utc(value)


class RegisteredSource(BaseModel):
    """One collection-scoped pointer at one storage prefix."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: Uuid
    collection_id: Uuid
    bucket: str = Field(min_length=3, max_length=222, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    prefix: str = Field(min_length=1, max_length=1024)
    media_types: tuple[str, ...] = Field(min_length=1)
    registered_by: str = Field(min_length=1, max_length=200)
    registered_at: str

    @model_validator(mode="after")
    def sound_configuration(self):
        canonical_uuid(self.source_id)
        canonical_uuid(self.collection_id)
        object.__setattr__(self, "registered_at", utc_instant(self.registered_at))
        unknown = set(self.media_types) - set(SUPPORTED_MEDIA_TYPES)
        if unknown:
            raise ValueError(
                "A source may declare only media the import path can verify"
            )
        if len(set(self.media_types)) != len(self.media_types):
            raise ValueError("Declare each media type once")
        validate_prefix(self.prefix)
        return self

    def contains(self, object_name: str) -> bool:
        return object_name.startswith(self.prefix) and len(object_name) > len(
            self.prefix
        )


def validate_prefix(prefix: str) -> str:
    """A prefix names a directory inside one bucket and can never leave it."""
    if not prefix.endswith("/"):
        raise ValueError("A source prefix must end with a separator")
    if prefix.startswith("/"):
        raise ValueError("A source prefix is relative to its bucket")
    if any(ord(c) < 32 or ord(c) == 127 for c in prefix):
        raise ValueError("Invalid source prefix")
    if "//" in prefix or any(part in {"", ".", ".."} for part in prefix.split("/")[:-1]):
        raise ValueError("A source prefix must not traverse")
    return prefix


def validate_object_name(source: RegisteredSource, object_name: str) -> str:
    """Admit only a name the registered prefix actually contains."""
    if not isinstance(object_name, str) or not 1 <= len(object_name) <= 1024:
        raise ValueError("Invalid object identifier")
    if any(ord(c) < 32 or ord(c) == 127 for c in object_name):
        raise ValueError("Invalid object identifier")
    if any(part in {".", ".."} for part in object_name.split("/")) or "//" in object_name:
        raise ValueError("Invalid object identifier")
    if not source.contains(object_name):
        raise ValueError("Object lies outside the registered source prefix")
    return object_name


class SourceRegistry:
    """The sources one process was configured with. Immutable for its lifetime."""

    def __init__(self, sources=()):
        ordered = tuple(sources)
        for source in ordered:
            if not isinstance(source, RegisteredSource):
                raise ValueError("A source registry holds registered sources only")
        if len({s.source_id for s in ordered}) != len(ordered):
            raise ValueError("Each source is registered once")
        if len({(s.collection_id, s.bucket, s.prefix) for s in ordered}) != len(ordered):
            raise ValueError("Each collection prefix is registered once")
        self._sources = ordered

    def __bool__(self) -> bool:
        return bool(self._sources)

    def for_collections(self, collection_ids) -> tuple[RegisteredSource, ...]:
        admitted = set(collection_ids)
        return tuple(s for s in self._sources if s.collection_id in admitted)

    def get(self, source_id: str, collection_ids) -> RegisteredSource:
        """Resolve within the caller's collections; anything else is simply absent."""
        for source in self.for_collections(collection_ids):
            if source.source_id == source_id:
                return source
        raise Missing(source_id)
