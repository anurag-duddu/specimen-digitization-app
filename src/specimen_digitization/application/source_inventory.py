"""A snapshot of the objects under a registered source prefix.

Snapshotted, never listed live, for three reasons. Interactive paging over a
thousand-object bucket listing is slow. `generation` has to be captured at a
known moment, so a later import can prove it binds to the bytes that were seen.
And a reviewer's selection must stay stable while they are choosing it.

The rows are serialized once into a content-addressed blob and read back
digest-verified, so a snapshot has one identity — the same sense in which
`Selection.source_inventory_sha256` already gives the frozen release cohort one.
`SourceObject` is reused unchanged as the per-object shape; nothing else in
`pilot_manifest` is touched, imported or extended.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from .blob_limits import ARTIFACT_BYTES, ORIGINAL_BYTES
from .domain import now
from .pilot_manifest import SourceObject
from .source_reader import sniff_media_type
from .storage import Conflict, Missing

# A capture reads every object once to digest it, so it is bounded on purpose.
# A prefix holding more fails closed rather than silently offering a truncation.
MAX_INVENTORY_OBJECTS = 5000
CURSOR_LIMIT = 2500

AVAILABLE = "available"
IMPORTED = "imported"
UNSUPPORTED = "unsupported_media_type"


class InventoryEntry(BaseModel):
    """One inventoried object: the frozen SourceObject shape plus its media type."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_object: SourceObject
    media_type: str = Field(min_length=1, max_length=200)


class SourceInventory(BaseModel):
    """The snapshot header. Rows live in the referenced content-addressed blob."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["source-inventory/v1"] = "source-inventory/v1"
    inventory_id: str
    source_id: str
    collection_id: str
    bucket: str
    prefix: str
    captured_at: str
    captured_by: str
    object_count: int = Field(ge=0, le=MAX_INVENTORY_OBJECTS)
    skipped_oversize: int = Field(default=0, ge=0)
    entries_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entries_blob_ref: str = Field(min_length=1, max_length=200)
    sensitive: bool = True
    revision: int = 0

    def wire(self) -> dict:
        """`entries_blob_ref` is an internal storage handle and stays off the wire,
        as `asset.blob_ref` already does. `entries_sha256` is the snapshot's
        identity and a client legitimately needs it to notice a change."""
        return self.model_dump(mode="json", exclude={"entries_blob_ref"})


def inventory_document_id(source_id: str) -> str:
    """One current inventory per source, addressed by a derived id, never listed."""
    return str(uuid5(NAMESPACE_URL, "source-inventory:" + str(UUID(source_id))))


def serialize(entries) -> bytes:
    return json.dumps(
        [entry.model_dump(mode="json") for entry in entries],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()


def capture(
    reader, source, actor: str, blobs, previous=()
) -> tuple[SourceInventory, tuple]:
    """Read the prefix, digesting every object at the generation it is on.

    An object already recorded at the same generation and size is carried over
    without being read again. A generation identifies immutable bytes, so the
    retained digest still describes exactly what the server read at that
    generation. This is what keeps a refresh cheap: a first capture of a
    thousand-object prefix reads every object, a refresh reads only what moved.
    """
    listed = reader.list_objects(source.bucket, source.prefix, MAX_INVENTORY_OBJECTS)
    if len(listed) > MAX_INVENTORY_OBJECTS:
        raise ValueError(
            f"A source inventory holds at most {MAX_INVENTORY_OBJECTS} objects"
        )
    retained = {
        (
            entry.source_object.object_name,
            entry.source_object.generation,
            entry.source_object.size_bytes,
        ): entry
        for entry in previous
    }
    entries, skipped = [], 0
    for row in listed:
        if not source.contains(row["object_name"]):
            continue
        if not 0 < row["size_bytes"] <= ORIGINAL_BYTES:
            # Nothing intake could ever accept. Counted, never silently dropped.
            skipped += 1
            continue
        carried = retained.get(
            (row["object_name"], row["generation"], row["size_bytes"])
        )
        if carried is not None:
            entries.append(carried)
            continue
        data = reader.read(source.bucket, row["object_name"], row["generation"])
        if not data:
            skipped += 1
            continue
        entries.append(
            InventoryEntry(
                source_object=SourceObject(
                    bucket=source.bucket,
                    object_name=row["object_name"],
                    generation=row["generation"],
                    sha256=hashlib.sha256(data).hexdigest(),
                    size_bytes=len(data),
                    crc32c=row.get("crc32c"),
                    md5_hash=row.get("md5_hash"),
                ),
                media_type=sniff_media_type(data),
            )
        )
    entries = tuple(sorted(entries, key=lambda e: e.source_object.object_name))
    payload = serialize(entries)
    entries_sha256 = hashlib.sha256(payload).hexdigest()
    inventory = SourceInventory(
        # Content-derived, so an unchanged prefix recaptures to the same snapshot.
        inventory_id=str(
            uuid5(NAMESPACE_URL, "source-inventory:" + source.source_id + entries_sha256)
        ),
        source_id=source.source_id,
        collection_id=source.collection_id,
        bucket=source.bucket,
        prefix=source.prefix,
        captured_at=now(),
        captured_by=actor,
        object_count=len(entries),
        skipped_oversize=skipped,
        entries_sha256=entries_sha256,
        entries_blob_ref=blobs.put(payload),
    )
    return inventory, entries


def read_entries(blobs, inventory: SourceInventory) -> tuple[InventoryEntry, ...]:
    """Never trust a retained reference without rechecking the snapshot digest."""
    data = blobs.get_bounded(inventory.entries_blob_ref, ARTIFACT_BYTES)
    if hashlib.sha256(data).hexdigest() != inventory.entries_sha256:
        raise Conflict("Source inventory integrity failure")
    entries = tuple(InventoryEntry.model_validate(row) for row in json.loads(data))
    if len(entries) != inventory.object_count:
        raise Conflict("Source inventory integrity failure")
    return entries


def find_entry(entries, object_name: str) -> InventoryEntry | None:
    for entry in entries:
        if entry.source_object.object_name == object_name:
            return entry
    return None


class InventoryFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    imported: bool | None = None
    media_type: str | None = Field(default=None, min_length=1, max_length=200)


def binding(scope, inventory_id: str, filters: InventoryFilters, actor, sensitive):
    return hashlib.sha256(
        json.dumps(
            [
                scope.model_dump(),
                inventory_id,
                filters.model_dump(),
                actor,
                sensitive,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()


def decode_cursor(cursor, bound: str) -> str:
    """Return the object name to resume after; reject anything not this page set."""
    if cursor in (None, "", "0"):
        return ""
    try:
        if len(cursor) > CURSOR_LIMIT:
            raise ValueError()
        item = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if (
            set(item) != {"v", "binding", "after"}
            or item["v"] != 1
            or item["binding"] != bound
            or not isinstance(item["after"], str)
            or not 1 <= len(item["after"]) <= 1024
        ):
            raise ValueError()
        return item["after"]
    except Exception as exc:
        raise ValueError(
            "Invalid cursor or changed snapshot, scope, identity, permission or filters"
        ) from exc


def encode_cursor(bound: str, object_name: str) -> str:
    return (
        base64.urlsafe_b64encode(
            json.dumps(
                dict(v=1, binding=bound, after=object_name), separators=(",", ":")
            ).encode()
        )
        .decode()
        .rstrip("=")
    )


def row(entry: InventoryEntry, state: str, specimen_id: str | None) -> dict:
    source_object = entry.source_object
    return {
        "bucket": source_object.bucket,
        "object_name": source_object.object_name,
        "generation": source_object.generation,
        "sha256": source_object.sha256,
        "size_bytes": source_object.size_bytes,
        "crc32c": source_object.crc32c,
        "md5_hash": source_object.md5_hash,
        "media_type": entry.media_type,
        "state": state,
        "specimen_id": specimen_id,
    }


def entry_state(entry: InventoryEntry, source, resolve) -> tuple[str, str | None]:
    """Already in the queue is the reviewer's most actionable signal, so it wins."""
    specimen_id = resolve(entry.source_object.sha256)
    if specimen_id:
        return IMPORTED, specimen_id
    if entry.media_type not in source.media_types:
        return UNSUPPORTED, None
    return AVAILABLE, None


def page(entries, source, filters: InventoryFilters, after: str, limit: int, resolve):
    """One bounded page of an immutable snapshot, ordered by object name."""
    if not 1 <= limit <= 100:
        raise ValueError("Source listing limit must be 1 to 100")
    rows = []
    for entry in entries:
        if entry.source_object.object_name <= after:
            continue
        if filters.media_type and entry.media_type != filters.media_type:
            continue
        state, specimen_id = entry_state(entry, source, resolve)
        if filters.imported is not None and filters.imported != (state == IMPORTED):
            continue
        rows.append(row(entry, state, specimen_id))
        if len(rows) == limit:
            break
    return rows


def header(repository, scope, source) -> SourceInventory:
    """The current snapshot header, or Missing when none was ever captured."""
    document = repository.document(
        scope, "source_inventory", inventory_document_id(source.source_id)
    )
    inventory = SourceInventory.model_validate(document)
    if (
        inventory.source_id != source.source_id
        or inventory.collection_id != source.collection_id
        or inventory.bucket != source.bucket
        or inventory.prefix != source.prefix
    ):
        # The configuration moved under a retained snapshot; recapture, never guess.
        raise Missing(source.source_id)
    return inventory


def load(repository, scope, source, blobs):
    inventory = header(repository, scope, source)
    return inventory, read_entries(blobs, inventory)
