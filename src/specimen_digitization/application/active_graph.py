"""Bounded immutable active-run storage with exact reconstruction and identity checks."""

import hashlib
import json

GRAPH_THRESHOLD = 96 * 1024
GRAPH_LIMIT = 16 * 1024 * 1024
NORMAL_GRAPH_LIMIT = GRAPH_LIMIT - 16 * 1024
WORKSPACE_LIMIT = 4 * 1024 * 1024


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


def pack(specimen, blobs):
    from .storage import digest

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
    payload["active_graph"] = metadata
    payload["run"] = run_summary(value["run"])
    specimen.active_graph = metadata
    return payload


def read_graph(payload, blobs):
    from .storage import Conflict, digest

    metadata = payload.get("active_graph")
    if metadata is None:
        return None
    try:
        if (
            blobs is None
            or metadata["contract_version"] != "active-run-v1"
            or not 0 < metadata["size_bytes"] <= GRAPH_LIMIT
        ):
            raise ValueError()
        if (
            metadata["scope"] != payload["scope"]
            or metadata["specimen_id"] != payload["id"]
            or metadata["revision"] != payload["version"]
            or metadata["run_id"] != payload["run"]["id"]
        ):
            raise ValueError()
        raw = blobs.get_bounded(metadata["blob_ref"], GRAPH_LIMIT)
        if (
            len(raw) != metadata["size_bytes"]
            or hashlib.sha256(raw).hexdigest() != metadata["sha256"]
        ):
            raise ValueError()
        value = json.loads(raw)
        if (
            value["contract_version"] != "active-run-v1"
            or value["scope"] != metadata["scope"]
            or value["specimen_id"] != metadata["specimen_id"]
            or value["revision"] != metadata["revision"]
            or value["run"]["id"] != metadata["run_id"]
        ):
            raise ValueError()
        if digest(value["run"]) != metadata["run_sha256"] or digest(
            run_summary(value["run"])
        ) != digest(payload["run"]):
            raise ValueError()
        return raw, value["run"]
    except Exception as exc:
        raise Conflict("Active graph integrity or storage failure") from exc


def unpack(payload, blobs):
    from .domain import Specimen

    graph = read_graph(payload, blobs)
    if graph:
        payload = {**payload, "run": graph[1]}
    return Specimen.model_validate(payload)


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
