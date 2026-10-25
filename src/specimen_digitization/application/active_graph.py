"""Bounded immutable active-run storage with exact reconstruction and identity checks."""

import hashlib
import json
import math
import re

GRAPH_THRESHOLD = 96 * 1024
GRAPH_LIMIT = 16 * 1024 * 1024
NORMAL_GRAPH_LIMIT = GRAPH_LIMIT - 16 * 1024
WORKSPACE_LIMIT = 4 * 1024 * 1024
FIELD_REVIEW_LIMIT = 16 * 1024


class GraphTooLarge(ValueError):
    pass


class WorkspaceTooLarge(ValueError):
    def __init__(self, details):
        super().__init__("Workspace requires complete artifact retrieval")
        self.details = details


def encoded(value):
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()


def run_summary(run):
    omitted = {
        "observations",
        "first_pass_decisions",
        "transcripts",
        "fields",
        "evidence",
        "lookups",
        "phase_results",
        "reading_metadata",
        "reading_declarations",
        "label_language_handling",
        "disagreements",
        "authority_receipts",
        "authority_results",
        "dependencies",
        "profile_snapshot",
        "risk_policy_snapshot",
        "profile_rules",
    }
    return {
        key: ([] if isinstance(value, list) else {}) if key in omitted else value
        for key, value in run.items()
    }


def envelope(specimen):
    return {
        "contract_version": "active-run-v1",
        "scope": specimen.scope.model_dump(),
        "specimen_id": specimen.id,
        "revision": specimen.version,
        "run": specimen.run.model_dump(mode="json"),
    }


def field_review_projection(run):
    """Content-free fields from exactly the run stored in the immutable graph."""
    from .review_summary import project_fields
    from .storage import digest

    return {
        "version": "field-review-v1",
        "fields": project_fields(run.get("fields")),
        "reasons_sha256": digest(run.get("reasons", [])),
    }


def metadata_integer(value, maximum):
    """Struct transports integers as doubles; reject fractions and booleans."""
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value != int(value) or not 0 < value <= maximum):
        raise ValueError("Invalid graph integer")
    return int(value)


def validate_graph_metadata(metadata, *, scope, specimen_id, revision, run_id):
    """Bind an immutable graph to the exact authorized current row before I/O."""
    if not isinstance(metadata, dict) or (
        metadata.get("contract_version") != "active-run-v1"
        or metadata.get("scope") != scope
        or metadata.get("specimen_id") != specimen_id
        or metadata_integer(metadata.get("revision"), 2**53 - 1) != revision
        or metadata.get("run_id") != run_id
        or not isinstance(run_id, str) or not run_id
    ):
        raise ValueError("Graph identity mismatch")
    size = metadata_integer(metadata.get("size_bytes"), GRAPH_LIMIT)
    for name in ("sha256", "run_sha256"):
        if not isinstance(metadata.get(name), str) or not re.fullmatch(r"[0-9a-f]{64}", metadata[name]):
            raise ValueError("Invalid graph digest")
    ref = metadata.get("blob_ref")
    if (not isinstance(ref, str)
            or not re.fullmatch(r"[0-9a-f]{64}(?::[1-9][0-9]*)?", ref)
            or ref.split(":", 1)[0] != metadata["sha256"]):
        raise ValueError("Invalid immutable graph reference")
    return size


def verified_graph_run(raw, metadata):
    """Shared byte/envelope validator; callers first bind metadata to their row."""
    from .storage import digest

    if len(raw) != metadata["size_bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
        raise ValueError("Graph bytes mismatch")
    value = json.loads(raw)
    if (
        value["contract_version"] != "active-run-v1"
        or value["scope"] != metadata["scope"]
        or value["specimen_id"] != metadata["specimen_id"]
        or metadata_integer(value["revision"], 2**53 - 1) != metadata["revision"]
        or value["run"]["id"] != metadata["run_id"]
        or digest(value["run"]) != metadata["run_sha256"]
    ):
        raise ValueError("Graph envelope mismatch")
    if "field_review" in metadata and metadata["field_review"] != field_review_projection(value["run"]):
        raise ValueError("Graph field projection mismatch")
    return value["run"]


def pack(specimen, blobs):
    from .storage import digest, check_snapshot, SnapshotTooLarge

    payload = specimen.model_dump(mode="json")
    payload["active_graph"] = None
    if len(encoded(payload["run"])) <= GRAPH_THRESHOLD:
        specimen.active_graph = None
        return payload
    value = envelope(specimen)
    raw = encoded(value)
    limit = (
        GRAPH_LIMIT
        if specimen.run.stage in {"processing_blocked", "cancelled", "paused"}
        else NORMAL_GRAPH_LIMIT
    )
    if len(raw) > limit:
        raise GraphTooLarge("active_graph_limit_exceeded")
    if blobs is None:
        raise GraphTooLarge("active_graph_storage_not_configured")
    metadata = {
        "contract_version": "active-run-v1",
        "scope": value["scope"],
        "specimen_id": specimen.id,
        "revision": specimen.version,
        "run_id": specimen.run.id,
        "blob_ref": blobs.put(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "run_sha256": digest(value["run"]),
        "size_bytes": len(raw),
    }
    projection = field_review_projection(value["run"])
    if len(encoded(projection)) <= FIELD_REVIEW_LIMIT:
        metadata["field_review"] = projection
    payload["active_graph"] = metadata
    payload["run"] = run_summary(value["run"])
    # Optional acceleration cannot make an otherwise supported snapshot fail its
    # existing persistence limit. Wide/near-limit records use verified reads.
    if "field_review" in metadata:
        try:
            check_snapshot(encoded(payload).decode())
        except SnapshotTooLarge:
            metadata.pop("field_review")
    specimen.active_graph = metadata
    return payload


def read_graph(payload, blobs):
    from .storage import Conflict, digest

    metadata = payload.get("active_graph")
    if metadata is None:
        return None
    try:
        if blobs is None:
            raise ValueError()
        size = validate_graph_metadata(metadata, scope=payload["scope"],
            specimen_id=payload["id"], revision=payload["version"], run_id=payload["run"]["id"])
        raw = blobs.get_bounded(metadata["blob_ref"], size)
        run = verified_graph_run(raw, metadata)
        # This historical integrity check is intentionally unchanged in meaning.
        if digest(run_summary(run)) != digest(payload["run"]):
            raise ValueError()
        return raw, run
    except Exception as exc:
        raise Conflict("Active graph integrity or storage failure") from exc


def unpack(payload, blobs):
    from .domain import Specimen

    graph = read_graph(payload, blobs)
    if graph:
        payload = {**payload, "run": graph[1]}
    return Specimen.model_validate(payload, context={"persisted_snapshot": True})


def original_run_digest(payload, blobs):
    from .storage import digest

    graph = read_graph(payload, blobs)
    return digest(graph[1] if graph else payload["run"])


def save_recoverably(repository, principal, specimen, revision, key, request_digest):
    from .domain import AuditEvent
    from .storage import Conflict, SnapshotTooLarge, digest

    try:
        return repository.save(principal, specimen, revision, key, request_digest)
    except (GraphTooLarge, SnapshotTooLarge) as exc:
        reason = (
            str(exc) if isinstance(exc, GraphTooLarge) else "snapshot_limit_exceeded"
        )
        prior = repository.get(principal.scope, specimen.id)
        if prior.version != revision:
            raise Conflict("Record advanced during graph limit recovery")
        prior.run.stage = "processing_blocked"
        prior.run.disposition = None
        prior.run.blocker = reason
        prior.run.reasons = [reason]
        prior.run.human_approved = False
        prior.run.lease_until = None
        prior.audit.append(
            AuditEvent(
                actor=principal.user_id,
                action="active_graph_limit",
                reason=reason,
                after={"rejected_operation": key, "last_complete_revision": revision},
            )
        )
        return repository.save(
            principal,
            prior,
            revision,
            "graph-limit:" + key,
            digest({"request": request_digest, "limit": reason}),
        )
