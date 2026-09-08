"""Bounded current-metadata search; cursors carry no authorization authority."""

import base64
import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("Search timestamps must specify UTC")
    return parsed.isoformat()


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specimen_id: str | None = None
    asset_id: str | None = None
    active_run_id: str | None = None
    batch_id: str | None = None
    uploader_id: str | None = Field(default=None, min_length=1, max_length=200)
    state: (
        Literal[
            "running",
            "completed",
            "processing_blocked",
            "retry_scheduled",
            "paused",
            "cancelled",
        ]
        | None
    ) = None
    stage: (
        Literal[
            "ingested",
            "classify",
            "quality_check",
            "segment",
            "transcribe",
            "adjudicate",
            "parse",
            "plan",
            "lookup",
            "resolve",
            "normalize",
            "validate",
            "finalize",
            "finalized",
            "processing_blocked",
            "retry_scheduled",
            "paused",
            "cancelled",
        ]
        | None
    ) = None
    disposition: Literal["cleared", "needs_human_review", "deferred"] | None = None
    profile_id: str | None = Field(default=None, min_length=1, max_length=200)
    profile_version: str | None = Field(default=None, min_length=1, max_length=200)
    reason_code: str | None = Field(default=None, min_length=1, max_length=200)
    blocker: str | None = Field(default=None, min_length=1, max_length=200)
    created_from: str | None = None
    created_before: str | None = None
    risk_min: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    risk_max: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def bounds(self):
        for name in ("specimen_id", "asset_id", "active_run_id", "batch_id"):
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, str(UUID(value)))
        for name in ("created_from", "created_before"):
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, utc(value))
        if (
            self.created_from
            and self.created_before
            and self.created_from >= self.created_before
        ):
            raise ValueError("created_from must precede created_before")
        if (
            self.risk_min is not None
            and self.risk_max is not None
            and self.risk_min > self.risk_max
        ):
            raise ValueError("risk_min must not exceed risk_max")
        return self


def binding(scope, filters, actor, sensitive):
    return hashlib.sha256(
        json.dumps(
            [scope.model_dump(), filters.model_dump(), actor, sensitive], sort_keys=True
        ).encode()
    ).hexdigest()


def decode_cursor(cursor, bound):
    now = datetime.now(timezone.utc).isoformat()
    if cursor in (None, "", "0"):
        return now, None, ""
    try:
        if len(cursor) > 1500:
            raise ValueError()
        item = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if (
            set(item) != {"v", "binding", "cutoff", "created_at", "id"}
            or item["v"] != 1
            or item["binding"] != bound
        ):
            raise ValueError()
        cutoff, created = utc(item["cutoff"]), utc(item["created_at"])
        if cutoff > now or created > cutoff:
            raise ValueError()
        return cutoff, created, str(UUID(item["id"]))
    except Exception as exc:
        raise ValueError(
            "Invalid cursor or changed scope, identity, permission or filters"
        ) from exc


def encode_cursor(bound, cutoff, row):
    value = dict(
        v=1,
        binding=bound,
        cutoff=cutoff,
        created_at=row["created_at"],
        id=row["specimen_id"],
    )
    return (
        base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )


def sql_item(row, scope):
    names = {
        "id": "specimen_id",
        "revision": "revision",
        "status": "status",
        "stage": "stage",
        "disposition": "disposition",
        "sensitive": "sensitive",
        "createdAt": "created_at",
        "domainCreatedAt": "domain_created_at",
        "updatedAt": "updated_at",
        "assetId": "asset_id",
        "batchId": "batch_id",
        "filename": "filename",
        "uploader": "uploader_id",
        "activeRunId": "active_run_id",
        "blocker": "blocker",
        "profileId": "profile_id",
        "profileVersion": "profile_version",
        "reasonCodes": "reason_codes",
        "risk": "risk",
        "synthetic": "synthetic",
    }
    result = {target: row.get(source) for source, target in names.items()}
    result.update(scope.model_dump())
    result["record_version_id"] = f"{result['active_run_id']}:{result['revision']}"
    result["risk_calibrated"] = False
    return result


def sqlite_search(
    repository,
    scope,
    filters,
    cutoff,
    after_created,
    after_id,
    limit,
    include_sensitive,
):
    # JSON projection/filtering occurs in SQLite; no snapshots enter Python.
    projections = {
        "specimen_id": "id",
        "revision": "revision",
        "created_at": "created_at",
        "domain_created_at": "json_extract(payload,'$.created_at')",
        "asset_id": "json_extract(payload,'$.asset.id')",
        "batch_id": "json_extract(payload,'$.batch_id')",
        "filename": "json_extract(payload,'$.asset.filename')",
        "uploader_id": "json_extract(payload,'$.asset.uploader')",
        "active_run_id": "json_extract(payload,'$.run.id')",
        "stage": "json_extract(payload,'$.run.stage')",
        "disposition": "json_extract(payload,'$.run.disposition')",
        "blocker": "json_extract(payload,'$.run.blocker')",
        "profile_id": "json_extract(payload,'$.run.profile.id')",
        "profile_version": "json_extract(payload,'$.run.profile.version')",
        "synthetic": "json_extract(payload,'$.run.profile.synthetic')",
        "sensitive": "json_extract(payload,'$.asset.sensitive')",
        "reason_codes": "json_extract(payload,'$.run.reasons')",
        "risk": "CASE WHEN json_type(payload,'$.run.review_risk.composite') IN ('integer','real') AND json_extract(payload,'$.run.review_risk.composite') BETWEEN 0 AND 100 THEN json_extract(payload,'$.run.review_risk.composite') END",
        "status": "CASE WHEN json_extract(payload,'$.run.disposition') IS NOT NULL THEN 'completed' WHEN state IN ('processing_blocked','retry_scheduled','paused','cancelled') THEN state ELSE 'running' END",
    }
    clauses = ["org=?", "collection=?", "created_at<=?"]
    values = [scope.organization_id, scope.collection_id, cutoff]
    if not include_sensitive:
        clauses.append("COALESCE(json_extract(payload,'$.asset.sensitive'),1)=0")
    if after_created:
        clauses.append("(created_at>? OR (created_at=? AND id>?))")
        values.extend((after_created, after_created, after_id))
    for name, value in filters.model_dump(exclude_none=True).items():
        if name == "reason_code":
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(payload,'$.run.reasons') WHERE value=?)"
            )
        elif name in ("created_from", "created_before"):
            clauses.append("created_at" + (">=?" if name == "created_from" else "<?"))
        elif name in ("risk_min", "risk_max"):
            clauses.append(
                "("
                + projections["risk"]
                + ")"
                + (">=?" if name == "risk_min" else "<=?")
            )
        else:
            clauses.append(
                "(" + projections["status" if name == "state" else name] + ")=?"
            )
        values.append(value)
    query = (
        "SELECT "
        + ",".join(projections.values())
        + " FROM records WHERE "
        + " AND ".join(clauses)
        + " ORDER BY created_at,id LIMIT ?"
    )
    with repository.connect() as db:
        rows = db.execute(query, (*values, limit)).fetchall()
    result = []
    for values in rows:
        row = dict(zip(projections, values))
        row.update(scope.model_dump())
        row["reason_codes"] = json.loads(row["reason_codes"] or "[]")
        row["sensitive"] = row["sensitive"] is None or bool(row["sensitive"])
        row["synthetic"] = bool(row["synthetic"])
        row["record_version_id"] = f"{row['active_run_id']}:{row['revision']}"
        row["risk_calibrated"] = False
        result.append(row)
    return result
