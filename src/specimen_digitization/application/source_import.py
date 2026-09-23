"""Create specimens from objects a reviewer selected in a source inventory.

Upload completion verifies a client's declaration against the uploaded bytes. No
client declares anything here, so the snapshot is the declaration: an object must
appear in its source's current inventory at the generation the request names, the
live object must still be on that generation when it is read, and the bytes must
digest to the value the server itself recorded at capture. The snapshot is the
one declaration a client can neither supply nor alter.

This module dispatches nothing itself. Outside synthetic mode the caller passes
`on_intake`, which queues each new specimen within its collection's allowance
before it is created: adding a source photograph is intake, and intake
processes (docs/execution/golive/LANE.md, T1).
"""

from __future__ import annotations

import hashlib
import io
from uuid import NAMESPACE_URL, uuid5

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from .domain import Asset, AuditEvent, Profile, Run, Specimen
from .image_quality import ImageLimits, orientation_view
from .source_reader import SourceObjectChanged, valid_generation
from .source_registry import SUPPORTED_MEDIA_TYPES, validate_object_name
from .storage import Conflict, Missing

# Each object is read whole, so a request is bounded and the client pages.
MAX_IMPORT_OBJECTS = 50

IMPORTED = "imported"
DUPLICATE = "duplicate"
UNSUPPORTED = "unsupported_media_type"
NOT_IN_SOURCE = "not_in_source"


class SourceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_name: str = Field(min_length=1, max_length=1024)
    generation: str = Field(pattern=r"^[1-9][0-9]*$")


class FromSourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sensitive: bool = Field(default=True, strict=True)
    source_id: str
    objects: list[SourceSelection] = Field(min_length=1)


class UnsupportedSourceMedia(ValueError):
    """The bytes are not media this source admits. Refused per object, not fatal."""


def verified_image(data: bytes, permitted):
    """The bytes name the format, exactly as upload completion lets them."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            actual = Image.MIME.get(image.format)
            if actual not in permitted:
                raise UnsupportedSourceMedia("Source media type not permitted")
            if image.width * image.height > 40000000 or max(image.size) > 20000:
                # A property of this object, so it is reported against this object
                # rather than failing a selection the rest of which is importable.
                raise UnsupportedSourceMedia(
                    "Decoded image resolution limit exceeded"
                )
            image.load()
            dimensions = image.size
    except UnsupportedSourceMedia:
        raise
    except (OSError, SyntaxError, EOFError, Image.DecompressionBombError) as exc:
        raise UnsupportedSourceMedia("Invalid or truncated source image") from exc
    derivative, provenance = orientation_view(
        data, ImageLimits(allowed_formats=("JPEG", "PNG", "TIFF"))
    )
    return actual, dimensions, derivative, provenance


def identifier(source_id: str, object_name: str, generation: str, kind: str) -> str:
    return str(
        uuid5(NAMESPACE_URL, f"source:{source_id}:{object_name}:{generation}:{kind}")
    )


def verify_selection(source, entries, selections):
    """Nothing is created until every declared generation is the live generation."""
    if len(selections) > MAX_IMPORT_OBJECTS:
        raise ValueError(
            f"An import selects at most {MAX_IMPORT_OBJECTS} objects; page the rest"
        )
    names = [s.object_name for s in selections]
    if len(set(names)) != len(names):
        raise ValueError("Select each object once")
    inventoried = {entry.source_object.object_name: entry for entry in entries}
    resolved = []
    for selection in selections:
        validate_object_name(source, selection.object_name)
        valid_generation(selection.generation)
        entry = inventoried.get(selection.object_name)
        if entry is None:
            # The snapshot does not hold this object at all. Reported per object.
            resolved.append((selection, None))
            continue
        if entry.source_object.generation != selection.generation:
            # It is inventoried, at other bytes. That is the stale-selection case
            # the whole request must fail on, not a per-object note.
            raise SourceObjectChanged(
                "Source object generation was never inventoried: "
                + selection.object_name[:120]
            )
        resolved.append((selection, entry))
    return resolved


def outcome_row(source_object, state, specimen_id, checksum):
    return {
        "object_name": source_object.object_name,
        "generation": source_object.generation,
        "sha256": checksum,
        "state": state,
        "specimen_id": specimen_id,
    }


def import_objects(
    *,
    principal,
    user,
    source,
    entries,
    selections,
    reader,
    repository,
    blobs,
    batch_id,
    sensitive,
    synthetic,
    duplicate_of,
    on_intake=None,
):
    """Two passes: prove every generation first, then create."""
    resolved = verify_selection(source, entries, selections)
    absent = [s.object_name for s, entry in resolved if entry is None]
    live = []
    for selection, entry in resolved:
        if entry is None:
            continue
        try:
            current = reader.current_generation(source.bucket, selection.object_name)
        except Missing:
            current = None
        if current != selection.generation:
            raise SourceObjectChanged(
                "Source object changed since the inventory: "
                + selection.object_name[:120]
            )
        live.append(entry)

    permitted = tuple(
        media for media in source.media_types if media in SUPPORTED_MEDIA_TYPES
    )
    results, created = [], []
    for entry in live:
        source_object = entry.source_object
        existing = duplicate_of(source_object.sha256)
        if existing:
            # Already in the queue. Re-running "select all" reads nothing at all.
            results.append(
                outcome_row(source_object, DUPLICATE, existing, source_object.sha256)
            )
            continue
        if entry.media_type not in permitted:
            results.append(outcome_row(source_object, UNSUPPORTED, None, None))
            continue
        try:
            outcome = create_from_object(
                principal=principal,
                user=user,
                source=source,
                source_object=source_object,
                permitted=permitted,
                reader=reader,
                repository=repository,
                blobs=blobs,
                batch_id=batch_id,
                sensitive=sensitive,
                synthetic=synthetic,
                duplicate_of=duplicate_of,
                on_intake=on_intake,
            )
        except SourceObjectChanged as exc:
            # A change racing the import. Name what already exists; conceal nothing.
            raise SourceObjectChanged(
                f"{exc} (already created: {len(created)} of {len(live)})"
            ) from None
        except UnsupportedSourceMedia:
            results.append(outcome_row(source_object, UNSUPPORTED, None, None))
            continue
        results.append(outcome)
        if outcome["state"] == IMPORTED:
            created.append(outcome["specimen_id"])
    for object_name in absent:
        results.append(
            {
                "object_name": object_name,
                "generation": next(
                    s.generation for s in selections if s.object_name == object_name
                ),
                "sha256": None,
                "state": NOT_IN_SOURCE,
                "specimen_id": None,
            }
        )
    order = {s.object_name: index for index, s in enumerate(selections)}
    results.sort(key=lambda item: order[item["object_name"]])
    return {
        "batch_id": batch_id,
        "source_id": source.source_id,
        "requested": len(selections),
        "imported": sum(1 for item in results if item["state"] == IMPORTED),
        "duplicates": sum(1 for item in results if item["state"] == DUPLICATE),
        "items": results,
    }


def create_from_object(
    *,
    principal,
    user,
    source,
    source_object,
    permitted,
    reader,
    repository,
    blobs,
    batch_id,
    sensitive,
    synthetic,
    duplicate_of,
    on_intake=None,
):
    data = reader.read(
        source.bucket, source_object.object_name, source_object.generation
    )
    checksum = hashlib.sha256(data).hexdigest()
    if checksum != source_object.sha256 or len(data) != source_object.size_bytes:
        # The generation held but the bytes are not the bytes that were digested.
        raise SourceObjectChanged(
            "Source object content does not match the inventory: "
            + source_object.object_name[:120]
        )
    media_type, dimensions, derivative, provenance = verified_image(data, permitted)
    specimen = Specimen(
        id=identifier(
            source.source_id,
            source_object.object_name,
            source_object.generation,
            "specimen",
        ),
        scope=principal.scope,
        batch_id=batch_id,
        run=Run(
            profile=Profile(
                synthetic=synthetic,
                institutional_policy_approved=synthetic,
                semantics_confirmed=synthetic,
            )
        ),
        asset=Asset(
            sensitive=sensitive,
            id=identifier(
                source.source_id,
                source_object.object_name,
                source_object.generation,
                "asset",
            ),
            view_derivative=dict(
                provenance.model_dump(mode="json"), blob_ref=blobs.put(derivative)
            ),
            sha256=checksum,
            blob_ref=blobs.put(data),
            media_type=media_type,
            size_bytes=len(data),
            width=dimensions[0],
            height=dimensions[1],
            filename=source_object.object_name.rsplit("/", 1)[-1][:255],
            uploader=user,
        ),
    )
    specimen.audit.append(
        AuditEvent(
            actor=user,
            action="ingest",
            reason="Verified immutable source object generation",
            after={
                "bucket": source_object.bucket,
                "object_name": source_object.object_name,
                "generation": source_object.generation,
                "source_id": source.source_id,
            },
        )
    )
    key = (
        f"source:{source.source_id}:{source_object.object_name}:"
        f"{source_object.generation}"
    )
    request_digest = hashlib.sha256(
        f"{key}:{batch_id}:{checksum}:{sensitive}".encode()
    ).hexdigest()
    if on_intake is not None:
        on_intake(specimen)
    try:
        specimen = repository.create(principal, specimen, key, request_digest)
    except Conflict:
        existing = duplicate_of(checksum)
        if not existing:
            raise
        return outcome_row(source_object, DUPLICATE, existing, checksum)
    return outcome_row(source_object, IMPORTED, specimen.id, checksum)
