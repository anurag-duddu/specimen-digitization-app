"""Durable local reference adapters; production adapters live separately."""

from __future__ import annotations
from dataclasses import dataclass
import hashlib
from .active_graph import original_run_digest, unpack
import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Protocol
from .domain import AuditEvent, Principal, Scope, Specimen, WorkItem, WorkPage, now


def canonical_json(value: object) -> str:
    def canonical(item):
        if isinstance(item, dict):
            return {k: canonical(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [canonical(v) for v in item]
        if isinstance(item, float) and item.is_integer():
            return int(item)
        return item

    return json.dumps(
        canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


class Conflict(RuntimeError):
    pass


REVIEW_ROLES = frozenset({"reviewer", "manager", "admin"})
REVIEW_PROOF_READS = 50
REVIEW_PROVENANCE_INVALID = "review_decision_provenance_invalid"


def stamp_review_events(principal, specimen, previous, expected):
    """Bind genuinely new human events to the verified original CAS save.

    Existing event bytes and their compaction position are immutable. This is
    shared by the local reference and the named production adapter, not an API
    caller's declaration of authority or original revision.
    """
    retained = previous.audit if previous else []
    if previous and (
        previous.version != expected
        or specimen.audit_offset != previous.audit_offset
        or specimen.history_through_revision != previous.history_through_revision
        or specimen.audit[:len(retained)] != retained
    ):
        raise Conflict(REVIEW_PROVENANCE_INVALID)
    if not previous and (specimen.audit_offset or specimen.history_through_revision):
        raise Conflict(REVIEW_PROVENANCE_INVALID)
    ids = [event.id for event in specimen.audit]
    if len(set(ids)) != len(ids):
        raise Conflict(REVIEW_PROVENANCE_INVALID)
    for event in specimen.audit[len(retained):]:
        if not event.action.startswith("review_"):
            continue
        if (
            not expected
            or principal.role not in REVIEW_ROLES
            or event.actor != principal.user_id
            or (event.base_revision is not None and event.base_revision != expected)
            or (event.resulting_revision is not None and event.resulting_revision != expected + 1)
        ):
            raise Conflict(REVIEW_PROVENANCE_INVALID)
        event.base_revision = expected
        event.resulting_revision = expected + 1


@dataclass(frozen=True)
class ReviewSnapshot:
    """A digest-validated scoped row supplied by the repository itself."""
    payload: dict
    sha256: str
    specimen: Specimen


@dataclass(frozen=True)
class ReviewDecisionProof:
    specimen_id: str
    event: AuditEvent
    base_revision: int
    resulting_revision: int
    prior_sha256: str
    snapshot_sha256: str
    server_audit_id: str


def verify_review_decision_row(proof, row, *, required=False):
    """An actual scoped row agrees with every immutable original event value."""
    try:
        def same_id(left, right):
            return isinstance(left, str) and left.replace("-", "").lower() == right.replace("-", "").lower()

        def instant(value):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError(REVIEW_PROVENANCE_INVALID)
            return parsed

        event = proof.event
        original_time = instant(event.created_at)
        if row is None and not required:
            return
        if not isinstance(row, dict) or (
            not same_id(row.get("id"), event.id)
            or not same_id(row.get("specimenId"), proof.specimen_id)
            or row.get("actorUid") != event.actor
            or row.get("baseRevision") != proof.base_revision
            or row.get("resultingRevision") != proof.resulting_revision
            or row.get("reason") != event.reason
            or canonical_json(row.get("correction")) != canonical_json({
                "action": event.action, "before": event.before, "after": event.after,
            })
            or instant(row.get("createdAt", "")) != original_time
        ):
            raise ValueError(REVIEW_PROVENANCE_INVALID)
    except Exception:
        raise ValueError(REVIEW_PROVENANCE_INVALID) from None


class ReviewProofReader:
    """One pass's bounded, cached authoritative history and save-audit proof.

    Callback reads are scoped/authorized and validated by the native adapter.
    The 50 distinct-read ceiling is a technical fail-closed bound, not money,
    authority, available headroom, or a promise that legacy catch-up completed.
    """

    def __init__(self, specimen, read_snapshot, read_save_audits):
        self.specimen = specimen
        self.read_snapshot = read_snapshot
        self.read_save_audits = read_save_audits
        self.reads = {}
        self.inventories = {}

    def _read(self, key, callback):
        if key not in self.reads:
            if len(self.reads) >= REVIEW_PROOF_READS:
                raise ValueError(REVIEW_PROVENANCE_INVALID)
            self.reads[key] = callback()
        return self.reads[key]

    def _snapshot(self, revision):
        if type(revision) is not int or not 1 <= revision <= self.specimen.version:
            raise ValueError(REVIEW_PROVENANCE_INVALID)
        row = self._read(("snapshot", revision), lambda: self.read_snapshot(revision))
        payload = row.payload
        if (
            row.specimen.id != self.specimen.id
            or row.specimen.scope != self.specimen.scope
            or row.specimen.version != revision
            or payload.get("id") != self.specimen.id
            or payload.get("scope") != self.specimen.scope.model_dump()
            or payload.get("version") != revision
            or not isinstance(payload.get("audit"), list)
        ):
            raise ValueError(REVIEW_PROVENANCE_INVALID)
        return row

    def _inventory(self, revision):
        if revision in self.inventories:
            return self.inventories[revision]
        row = self._snapshot(revision)
        specimen = row.specimen
        prefix = []
        if specimen.audit_offset:
            through = specimen.history_through_revision
            if type(through) is not int or not 1 <= through < revision:
                raise ValueError(REVIEW_PROVENANCE_INVALID)
            prefix = self._inventory(through)
            if len(prefix) != specimen.audit_offset:
                raise ValueError(REVIEW_PROVENANCE_INVALID)
        events = [*prefix, *row.payload["audit"]]
        if any(not isinstance(event, dict) for event in events):
            raise ValueError(REVIEW_PROVENANCE_INVALID)
        ids = [event.get("id") for event in events]
        if any(not isinstance(ident, str) or not ident for ident in ids) or len(set(ids)) != len(ids):
            raise ValueError(REVIEW_PROVENANCE_INVALID)
        self.inventories[revision] = events
        return events

    def _original_revision(self, event):
        base, result = event.get("base_revision"), event.get("resulting_revision")
        if base is not None or result is not None:
            # Any/protobuf numeric values may be integral floats, never booleans.
            if (
                isinstance(base, bool) or isinstance(result, bool)
                or not isinstance(base, (int, float)) or not isinstance(result, (int, float))
                or base < 1 or result != base + 1 or int(base) != base
            ):
                raise ValueError(REVIEW_PROVENANCE_INVALID)
            return int(result)
        # Legacy metadata has no revision hint. Prove first appearance forward;
        # absence only in an adjacent compacted suffix is insufficient.
        for revision in range(1, self.specimen.version + 1):
            if any(item["id"] == event["id"] for item in self._inventory(revision)):
                if revision == 1:
                    raise ValueError(REVIEW_PROVENANCE_INVALID)
                return revision
        raise ValueError(REVIEW_PROVENANCE_INVALID)

    def _prove_event(self, event):
        required = {"id", "actor", "action", "reason", "before", "after", "created_at"}
        if not required <= event.keys():
            # A model default is not original persisted event identity or time.
            raise ValueError(REVIEW_PROVENANCE_INVALID)
        result = self._original_revision(event)
        target, prior = self._snapshot(result), self._snapshot(result - 1)
        matches = [item for item in target.payload["audit"] if item.get("id") == event["id"]]
        if (
            len(matches) != 1 or canonical_json(matches[0]) != canonical_json(event)
            or any(item["id"] == event["id"] for item in self._inventory(result - 1))
        ):
            raise ValueError(REVIEW_PROVENANCE_INVALID)
        response = self._read(
            ("save_proof", result, event["actor"], event["id"]),
            lambda: self.read_save_audits(result - 1, result, event, prior, target),
        )
        audits = response.get("saveAudits", [])
        if len(audits) != 1:
            raise ValueError(REVIEW_PROVENANCE_INVALID)
        audit = audits[0]
        def same_id(left, right):
            return isinstance(left, str) and left.replace("-", "").lower() == right.replace("-", "").lower()
        if (
            not isinstance(audit.get("id"), str)
            or not same_id(audit.get("organizationId"), self.specimen.scope.organization_id)
            or not same_id(audit.get("collectionId"), self.specimen.scope.collection_id)
            or not same_id(audit.get("specimenId"), self.specimen.id)
            or audit.get("actorUid") != event["actor"]
            or audit.get("revision") != result
            or audit.get("action") != "checkpoint_or_review"
        ):
            raise ValueError(REVIEW_PROVENANCE_INVALID)
        proof = ReviewDecisionProof(
            self.specimen.id, AuditEvent.model_validate(event), result - 1, result,
            prior.sha256, target.sha256, audit["id"],
        )
        # A V1 PK conflict is not evidence that original metadata was projected.
        verify_review_decision_row(proof, response.get("decision"))
        return proof

    def prove(self):
        try:
            original = self._snapshot(self.specimen.version)
            if original.specimen != self.specimen:
                raise ValueError(REVIEW_PROVENANCE_INVALID)
            return [
                self._prove_event(event)
                for event in self._inventory(self.specimen.version)
                if isinstance(event.get("action"), str) and event["action"].startswith("review_")
            ]
        except Exception:
            raise ValueError(REVIEW_PROVENANCE_INVALID) from None


class SnapshotTooLarge(ValueError):
    pass


def check_snapshot(payload: str) -> None:
    if len(payload.encode()) > 256 * 1024:
        raise SnapshotTooLarge(
            "Snapshot exceeds 256 KiB; archive pagination required, history was not truncated"
        )


def compact_history(specimen: Specimen, previous: Specimen) -> Specimen:
    """Offload only exact content already retained in the immutable previous version."""
    if len(specimen.model_dump_json().encode()) <= 128 * 1024:
        return specimen
    previous_audit = previous.audit
    if specimen.audit[: len(previous_audit)] == previous_audit:
        specimen.audit = specimen.audit[len(previous_audit) :]
        specimen.audit_offset = previous.audit_offset + len(previous_audit)
    retained_runs = [previous.run, *previous.previous_runs]
    specimen.previous_runs = [
        run
        for run in specimen.previous_runs
        if not any(run == retained for retained in retained_runs)
    ]
    specimen.history_through_revision = previous.version
    return specimen


class Missing(KeyError):
    pass


def work_available_at(specimen: Specimen) -> str | None:
    run = specimen.run
    if run.stage in {
        "finalized",
        "processing_blocked",
        "paused",
        "cancelled",
        "waiting_for_review",
    }:
        return None
    # A requested run waits its turn in request order (LANE.md T1, G13).
    if run.stage == "pending" and run.queued_at:
        return run.queued_at
    if run.blocker == "external_outcome_unknown" and run.lease_until:
        return run.lease_until
    if run.stage == "retry_scheduled" and run.next_retry_at:
        return run.next_retry_at
    return now()


@dataclass(frozen=True)
class ProjectionResult:
    """Whether a pass wrote every normalized row a revision supports (DATA_CONTRACT.md 11).

    `stopped_at` names the step a stopped pass did not write, a connector operation, or
    `not_computed` when the rows could not be computed; it never holds row data. After a
    run's final save the lane re-projects until a pass is complete (coordinator ruling).
    """

    complete: bool
    stopped_at: str | None = None


class Repository(Protocol):
    def oldest_due(self, scope: Scope, cutoff: str, limit: int = 1) -> list[WorkItem]: ...
    def due_page(
        self, scope: Scope, cutoff: str, after_id: str | None, limit: int = 50
    ) -> WorkPage: ...
    def get(self, scope: Scope, specimen_id: str) -> Specimen: ...
    def latest_run_version(
        self, scope: Scope, specimen_id: str, run_id: str, through_revision: int
    ) -> Specimen: ...
    def list(self, scope: Scope) -> list[Specimen]: ...
    def create(
        self, principal: Principal, specimen: Specimen, key: str, digest: str
    ) -> Specimen: ...
    def save(
        self,
        principal: Principal,
        specimen: Specimen,
        expected_revision: int,
        key: str,
        digest: str,
    ) -> Specimen: ...
    def write_projection(self, scope: Scope, specimen: Specimen) -> ProjectionResult: ...


class BlobStore(Protocol):
    def put(self, data: bytes) -> str: ...
    def get(self, ref: str) -> bytes: ...


class LocalBlobs:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes) -> str:
        ref = hashlib.sha256(data).hexdigest()
        path = self.root / ref
        # Publish only a fully written inode. Linking atomically creates the digest
        # name without replacing an existing immutable object.
        descriptor, temporary = tempfile.mkstemp(prefix=".blob-", dir=self.root)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if self.get_bounded(ref, max(1, len(data))) != data:
                    raise Conflict("Immutable blob content mismatch")
            directory = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return ref

    def get(self, ref: str) -> bytes:
        from .blob_limits import ORIGINAL_BYTES

        return self.get_bounded(ref, ORIGINAL_BYTES)

    def get_bounded(self, ref: str, max_bytes: int) -> bytes:
        from .blob_limits import read_limited, verify_digest

        if len(ref) != 64 or any(c not in "0123456789abcdef" for c in ref):
            raise Missing("Invalid blob reference")
        with (self.root / ref).open("rb") as source:
            data = read_limited(source.read, max_bytes)
        return verify_digest(data, ref)


class SQLiteRepository:
    """One transaction commits current state, immutable snapshot and retry receipt."""

    def __init__(self, path: Path):
        self.path = path
        self.graph_blobs = LocalBlobs(path.parent / (path.stem + "-graphs"))
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS records (org TEXT, collection TEXT, id TEXT,
                revision INTEGER NOT NULL, payload TEXT NOT NULL, checksum TEXT,
                PRIMARY KEY(org,collection,id), UNIQUE(org,collection,checksum));
            CREATE TABLE IF NOT EXISTS versions (org TEXT, collection TEXT, id TEXT,
                revision INTEGER, payload TEXT, PRIMARY KEY(org,collection,id,revision));
            CREATE TABLE IF NOT EXISTS receipts (scope TEXT, key TEXT, digest TEXT,
                payload TEXT, PRIMARY KEY(scope,key));
            CREATE TABLE IF NOT EXISTS documents (scope TEXT, kind TEXT, id TEXT,
                revision INTEGER, payload TEXT, PRIMARY KEY(scope,kind,id));
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(versions)")}
            if "sha256" not in columns:
                db.execute("ALTER TABLE versions ADD COLUMN sha256 TEXT")
                for row in db.execute(
                    "SELECT org,collection,id,revision,payload FROM versions"
                ):
                    db.execute(
                        "UPDATE versions SET sha256=? WHERE org=? AND collection=? AND id=? AND revision=?",
                        (digest(json.loads(row[4])), *row[:4]),
                    )
            columns = {row[1] for row in db.execute("PRAGMA table_info(records)")}
            migrate = "work_available_at" not in columns
            for column in ("work_available_at", "created_at", "state"):
                if column not in columns:
                    db.execute(f"ALTER TABLE records ADD COLUMN {column} TEXT")
            if migrate:
                for row in db.execute("SELECT org,collection,id,payload FROM records"):
                    specimen = Specimen.model_validate_json(row[3])
                    db.execute(
                        "UPDATE records SET work_available_at=?,created_at=?,state=? WHERE org=? AND collection=? AND id=?",
                        (
                            work_available_at(specimen),
                            specimen.created_at,
                            specimen.run.stage,
                            *row[:3],
                        ),
                    )
            db.execute(
                "CREATE INDEX IF NOT EXISTS records_search ON records(org,collection,created_at,id)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS records_due ON records(org,collection,id,work_available_at)"
            )

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA journal_mode=WAL")
        from .search import display_reference

        db.create_function("display_reference", 2, display_reference, deterministic=True)
        return db

    def get(self, scope: Scope, specimen_id: str) -> Specimen:
        with self.connect() as db:
            row = db.execute(
                "SELECT r.payload,v.sha256 FROM records r JOIN versions v ON v.org=r.org AND v.collection=r.collection AND v.id=r.id AND v.revision=r.revision WHERE r.org=? AND r.collection=? AND r.id=?",
                (*scope.model_dump().values(), specimen_id),
            ).fetchone()
        if row is None:
            raise Missing(specimen_id)
        payload = json.loads(row[0])
        if digest(payload) != row[1]:
            raise Conflict("Current snapshot digest mismatch")

        return unpack(payload, self.graph_blobs)

    def list(self, scope: Scope) -> list[Specimen]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM records WHERE org=? AND collection=? ORDER BY id",
                tuple(scope.model_dump().values()),
            ).fetchall()

        return [unpack(json.loads(r[0]), self.graph_blobs) for r in rows]

    def find_checksum(self, scope, checksum, include_sensitive=False):
        if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
            raise ValueError("Canonical source checksum required")
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,revision FROM records WHERE org=? AND collection=? AND checksum=? AND (? OR COALESCE(json_extract(payload,'$.asset.sensitive'),1)=0) LIMIT 2",
                (
                    scope.organization_id,
                    scope.collection_id,
                    checksum,
                    include_sensitive,
                ),
            ).fetchall()
        return [{"id": row[0], "revision": row[1]} for row in rows]

    def search(
        self,
        scope,
        filters,
        cutoff,
        after_created=None,
        after_id="",
        limit=50,
        include_sensitive=False,
    ):
        from .search import sqlite_search

        if not 1 <= limit <= 100:
            raise ValueError("Invalid search limit")
        return sqlite_search(
            self,
            scope,
            filters,
            cutoff,
            after_created,
            after_id,
            limit,
            include_sensitive,
        )

    def history_page(
        self, scope, ident, after_revision=0, through_revision=None, limit=50
    ):
        current = self.get(scope, ident)
        through = current.version if through_revision is None else through_revision
        if (
            not 1 <= limit <= 100
            or not 0 <= after_revision <= through <= current.version
        ):
            raise ValueError("Invalid history page bounds")
        with self.connect() as db:
            rows = db.execute(
                "SELECT revision,sha256 FROM versions WHERE org=? AND collection=? AND id=? AND revision>? AND revision<=? ORDER BY revision LIMIT ?",
                (
                    scope.organization_id,
                    scope.collection_id,
                    ident,
                    after_revision,
                    through,
                    limit,
                ),
            ).fetchall()
        items = [{"revision": r[0], "sha256": r[1]} for r in rows]
        return {
            "items": items,
            "through_revision": through,
            "next_cursor": items[-1]["revision"]
            if len(items) == limit and items[-1]["revision"] < through
            else None,
        }

    def version(self, scope, ident, revision):
        self.get(scope, ident)
        with self.connect() as db:
            row = db.execute(
                "SELECT payload,sha256 FROM versions WHERE org=? AND collection=? AND id=? AND revision=?",
                (scope.organization_id, scope.collection_id, ident, revision),
            ).fetchone()
        if not row:
            raise Missing(ident)
        if digest(json.loads(row[0])) != row[1]:
            raise Conflict("Historical snapshot digest mismatch")

        return unpack(json.loads(row[0]), self.graph_blobs)

    def latest_run_version(self, scope, ident, run_id, through_revision):
        """Read one scoped immutable snapshot; never infer lost accounting as zero."""
        current = self.get(scope, ident)
        if type(through_revision) is not int or not 1 <= through_revision <= current.version:
            raise ValueError("Invalid historical run bound")
        with self.connect() as db:
            row = db.execute(
                "SELECT payload,sha256 FROM versions WHERE org=? AND collection=? "
                "AND id=? AND revision<=? AND json_extract(payload,'$.run.id')=? "
                "ORDER BY revision DESC LIMIT 1",
                (scope.organization_id,scope.collection_id,ident,through_revision,run_id),
            ).fetchone()
        if not row:
            raise Missing(ident)
        payload = json.loads(row[0])
        if digest(payload) != row[1]:
            raise Conflict("Historical snapshot digest mismatch")
        result = unpack(payload,self.graph_blobs)
        if (result.id != ident or result.scope != scope or result.run.id != run_id
            or not 1 <= result.version <= through_revision):
            raise Conflict("Historical run identity mismatch")
        return result

    def oldest_due(self, scope, cutoff, limit=1):
        """Due, non-sensitive work, oldest request first (LANE.md T2, G13).

        The same states as ListDueWorkV2, so a stale due time is never listed.
        """
        from .lane import SQLITE_STATUS

        if not 1 <= limit <= 100:
            raise ValueError("Work page limit must be 1..100")
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,revision,state,work_available_at,created_at FROM records WHERE org=? AND collection=? AND created_at<=? AND work_available_at<=? AND COALESCE(json_extract(payload,'$.asset.sensitive'),1)=0 AND "
                + SQLITE_STATUS
                + " IN ('pending','running','retry_scheduled') ORDER BY work_available_at,id LIMIT ?",
                (scope.organization_id, scope.collection_id, cutoff, cutoff, limit),
            ).fetchall()
        return [
            WorkItem(
                specimen_id=r[0],
                revision=r[1],
                state=r[2],
                work_available_at=r[3],
                created_at=r[4],
            )
            for r in rows
        ]

    def due_page(self, scope, cutoff, after_id=None, limit=50):
        if not 1 <= limit <= 100:
            raise ValueError("Work page limit must be 1..100")
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,revision,state,work_available_at,created_at FROM records WHERE org=? AND collection=? AND created_at<=? AND work_available_at<=? AND id>? ORDER BY id LIMIT ?",
                (
                    scope.organization_id,
                    scope.collection_id,
                    cutoff,
                    cutoff,
                    after_id or "",
                    limit + 1,
                ),
            ).fetchall()
        items = [
            WorkItem(
                specimen_id=r[0],
                revision=r[1],
                state=r[2],
                work_available_at=r[3],
                created_at=r[4],
            )
            for r in rows[:limit]
        ]
        return WorkPage(
            items=items,
            next_cursor=items[-1].specimen_id if len(rows) > limit else None,
        )

    def version_info(self, scope, ident, revision):
        self.get(scope, ident)
        with self.connect() as db:
            row = db.execute(
                "SELECT payload,sha256 FROM versions WHERE org=? AND collection=? AND id=? AND revision=?",
                (scope.organization_id, scope.collection_id, ident, revision),
            ).fetchone()
        if not row:
            raise Missing(ident)
        payload = json.loads(row[0])
        if digest(payload) != row[1]:
            raise Conflict("Historical snapshot digest mismatch")
        return {
            "revision": revision,
            "sha256": row[1],
            "run_sha256": original_run_digest(payload, self.graph_blobs),
            "run_id": payload["run"]["id"],
        }

    def graph_bytes(self, scope, ident, revision):
        with self.connect() as db:
            row = db.execute(
                "SELECT payload,sha256 FROM versions WHERE org=? AND collection=? AND id=? AND revision=?",
                (scope.organization_id, scope.collection_id, ident, revision),
            ).fetchone()
        if not row:
            raise Missing(ident)
        payload = json.loads(row[0])
        if digest(payload) != row[1]:
            raise Conflict("Snapshot digest mismatch")
        from .active_graph import read_graph, encoded

        graph = read_graph(payload, self.graph_blobs)
        return (
            graph[0]
            if graph
            else encoded(
                {
                    "contract_version": "active-run-v1",
                    "scope": payload["scope"],
                    "specimen_id": ident,
                    "revision": revision,
                    "run": payload["run"],
                }
            )
        )

    def create(self, principal, specimen, key, digest):
        return self._commit(principal, specimen, 0, key, digest)

    def save(self, principal, specimen, expected_revision, key, digest):
        return self._commit(principal, specimen, expected_revision, key, digest)

    def _commit(self, principal, specimen, expected, key, request_digest):
        if principal.scope != specimen.scope:
            raise PermissionError("Scope mismatch")
        scope = f"{principal.scope.organization_id}/{principal.scope.collection_id}/{principal.user_id}/{specimen.id}"
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            receipt = db.execute(
                "SELECT digest,payload FROM receipts WHERE scope=? AND key=?",
                (scope, key),
            ).fetchone()
            if receipt:
                if receipt[0] != request_digest:
                    raise Conflict("Idempotency key reused with different request")

                return unpack(json.loads(receipt[1]), self.graph_blobs)
            identity = (
                specimen.scope.organization_id,
                specimen.scope.collection_id,
                specimen.id,
            )
            row = db.execute(
                "SELECT revision,payload FROM records WHERE org=? AND collection=? AND id=?",
                identity,
            ).fetchone()
            if (row[0] if row else 0) != expected:
                raise Conflict("Stale revision")
            if (
                row
                and json.loads(row[1])["asset"].get("sensitive", True) is not False
                and not specimen.asset.sensitive
            ):
                raise Conflict("Sensitive history cannot be downgraded")
            specimen = specimen.model_copy(deep=True)
            specimen.version = expected + 1
            previous = None
            if row:
                retained = db.execute(
                    "SELECT payload,sha256 FROM versions WHERE org=? AND collection=? AND id=? AND revision=?",
                    (*identity, expected),
                ).fetchone()
                if (
                    not retained
                    or retained[0] != row[1]
                    or digest(json.loads(retained[0])) != retained[1]
                ):
                    raise Conflict("History prefix snapshot integrity mismatch")
                previous = unpack(json.loads(retained[0]), self.graph_blobs)
            stamp_review_events(principal, specimen, previous, expected)
            if previous:
                specimen = compact_history(specimen, previous)
            from .active_graph import pack

            payload = json.dumps(
                pack(specimen, self.graph_blobs),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            check_snapshot(payload)
            try:
                db.execute(
                    "INSERT INTO records (org,collection,id,revision,payload,checksum,work_available_at,created_at,state) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(org,collection,id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload,work_available_at=excluded.work_available_at,state=excluded.state",
                    (
                        *identity,
                        specimen.version,
                        payload,
                        specimen.asset.sha256,
                        work_available_at(specimen),
                        specimen.created_at,
                        specimen.run.stage,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise Conflict("Duplicate source checksum within collection") from exc
            db.execute(
                "INSERT INTO versions (org,collection,id,revision,payload,sha256) VALUES (?,?,?,?,?,?)",
                (*identity, specimen.version, payload, digest(json.loads(payload))),
            )
            db.execute(
                "INSERT INTO receipts VALUES (?,?,?,?)",
                (scope, key, request_digest, payload),
            )
        return specimen

    def document(self, scope: Scope, kind: str, ident: str) -> dict:
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM documents WHERE scope=? AND kind=? AND id=?",
                (scope.model_dump_json(), kind, ident),
            ).fetchone()
        if not row:
            raise Missing(ident)
        return json.loads(row[0])

    def documents(self, scope: Scope, kind: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM documents WHERE scope=? AND kind=? ORDER BY id",
                (scope.model_dump_json(), kind),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def put_document(
        self, scope: Scope, kind: str, ident: str, payload: dict, expected: int
    ) -> dict:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT revision,payload FROM documents WHERE scope=? AND kind=? AND id=?",
                (scope.model_dump_json(), kind, ident),
            ).fetchone()
            if (row[0] if row else 0) != expected:
                raise Conflict("Stale document revision")
            if type(payload.get("sensitive", True)) is not bool:
                raise ValueError("Document sensitivity must be boolean")
            if (
                row
                and json.loads(row[1]).get("sensitive", True) is not False
                and not payload.get("sensitive", True)
            ):
                raise Conflict("Sensitive document cannot be downgraded")
            payload = dict(payload, revision=expected + 1)
            db.execute(
                "INSERT INTO documents VALUES (?,?,?,?,?) ON CONFLICT(scope,kind,id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload",
                (
                    scope.model_dump_json(),
                    kind,
                    ident,
                    expected + 1,
                    json.dumps(payload),
                ),
            )
        return payload

    def write_projection(self, scope: Scope, specimen: Specimen) -> ProjectionResult:
        """No normalized rows locally (DATA_CONTRACT.md 11), so every pass is complete."""
        return ProjectionResult(True)
