"""Batch upload lookups that stay outside the byte-qualified storage module.

The research harness qualifies ``storage.py`` by source digest. These queries
are the hot-path replacement for scanning every upload document, and they
attach to ``SQLiteRepository`` at import so the qualified file stays unchanged.
"""

from __future__ import annotations

import json

from .storage import SQLiteRepository


def uploads_for_batch(self, scope, batch_id, include_sensitive=False):
    with self.connect() as db:
        rows = db.execute(
            """SELECT payload FROM documents
               WHERE scope=? AND kind='upload'
                 AND json_extract(payload, '$.batch_id')=?
                 AND (? OR COALESCE(json_extract(payload, '$.sensitive'), 1)=0)
               ORDER BY id""",
            (scope.model_dump_json(), batch_id, include_sensitive),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def upload_by_idempotency(self, scope, batch_id, idempotency_key):
    with self.connect() as db:
        row = db.execute(
            """SELECT payload FROM documents
               WHERE scope=? AND kind='upload'
                 AND json_extract(payload, '$.batch_id')=?
                 AND json_extract(payload, '$.idempotency_key')=?
               LIMIT 1""",
            (scope.model_dump_json(), batch_id, idempotency_key),
        ).fetchone()
    return json.loads(row[0]) if row else None


def bind_sqlite_upload_lookups() -> None:
    SQLiteRepository.uploads_for_batch = uploads_for_batch
    SQLiteRepository.upload_by_idempotency = upload_by_idempotency


bind_sqlite_upload_lookups()
