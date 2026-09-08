"""Durable local reference adapters; production adapters live separately."""

from __future__ import annotations
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Protocol
from .domain import Principal, Scope, Specimen


def digest(value: object) -> str:
    def canonical(item):
        if isinstance(item, dict):
            return {k: canonical(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [canonical(v) for v in item]
        if isinstance(item, float) and item.is_integer():
            return int(item)
        return item

    return hashlib.sha256(
        json.dumps(
            canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


class Conflict(RuntimeError):
    pass


class SnapshotTooLarge(ValueError):
    pass


def check_snapshot(payload: str) -> None:
    if len(payload.encode()) > 256 * 1024:
        raise SnapshotTooLarge(
            "Snapshot exceeds 256 KiB; archive pagination required, history was not truncated"
        )


class Missing(KeyError):
    pass


class Repository(Protocol):
    def get(self, scope: Scope, specimen_id: str) -> Specimen: ...
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
        try:
            with path.open("xb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
        except FileExistsError:
            if path.read_bytes() != data:
                raise Conflict("Immutable blob content mismatch")
        return ref

    def get(self, ref: str) -> bytes:
        if len(ref) != 64 or any(c not in "0123456789abcdef" for c in ref):
            raise Missing("Invalid blob reference")
        data = (self.root / ref).read_bytes()
        if hashlib.sha256(data).hexdigest() != ref:
            raise Conflict("Blob integrity failure")
        return data


class SQLiteRepository:
    """One transaction commits current state, immutable snapshot and retry receipt."""

    def __init__(self, path: Path):
        self.path = path
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

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA journal_mode=WAL")
        return db

    def get(self, scope: Scope, specimen_id: str) -> Specimen:
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM records WHERE org=? AND collection=? AND id=?",
                (*scope.model_dump().values(), specimen_id),
            ).fetchone()
        if row is None:
            raise Missing(specimen_id)
        return Specimen.model_validate_json(row[0])

    def list(self, scope: Scope) -> list[Specimen]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM records WHERE org=? AND collection=? ORDER BY id",
                tuple(scope.model_dump().values()),
            ).fetchall()
        return [Specimen.model_validate_json(r[0]) for r in rows]

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
                return Specimen.model_validate_json(receipt[1])
            identity = (
                specimen.scope.organization_id,
                specimen.scope.collection_id,
                specimen.id,
            )
            row = db.execute(
                "SELECT revision FROM records WHERE org=? AND collection=? AND id=?",
                identity,
            ).fetchone()
            if (row[0] if row else 0) != expected:
                raise Conflict("Stale revision")
            specimen = specimen.model_copy(deep=True)
            specimen.version = expected + 1
            payload = specimen.model_dump_json()
            check_snapshot(payload)
            try:
                db.execute(
                    "INSERT INTO records VALUES (?,?,?,?,?,?) ON CONFLICT(org,collection,id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload",
                    (*identity, specimen.version, payload, specimen.asset.sha256),
                )
            except sqlite3.IntegrityError as exc:
                raise Conflict("Duplicate source checksum within collection") from exc
            db.execute(
                "INSERT INTO versions VALUES (?,?,?,?,?)",
                (*identity, specimen.version, payload),
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
                "SELECT revision FROM documents WHERE scope=? AND kind=? AND id=?",
                (scope.model_dump_json(), kind, ident),
            ).fetchone()
            if (row[0] if row else 0) != expected:
                raise Conflict("Stale document revision")
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
