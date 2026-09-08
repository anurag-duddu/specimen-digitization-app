"""Server-owned source allowlists and immutable, provider-neutral evidence contracts."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Literal, Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import LookupStatus, OPERATIONAL


def canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AuthorityQuery(Frozen):
    organization_id: str = Field(min_length=1, max_length=100)
    collection_id: str = Field(min_length=1, max_length=100)
    data_classification: Literal["public", "internal", "restricted"]
    literal: str = Field(min_length=1, max_length=2000)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    historical_context: str | None = Field(default=None, max_length=2000)


class AuthoritySource(Frozen):
    source_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    endpoint: str
    operations: tuple[str, ...]
    scopes: tuple[tuple[str, str], ...]
    classifications: tuple[Literal["public", "internal", "restricted"], ...]
    approved: bool = False
    license: str | None = None
    max_response_bytes: int = Field(default=262144, gt=0, le=1048576)
    timeout_seconds: float = Field(default=10, gt=0, le=30)

    @model_validator(mode="after")
    def endpoint_is_fixed_https(self):
        url = urlsplit(self.endpoint)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "Authority requires a fixed credential-free HTTPS endpoint"
            )
        return self


class AuthorityRegistry(Frozen):
    version: str
    sources: tuple[AuthoritySource, ...] = ()

    @model_validator(mode="after")
    def unique_sources(self):
        if len({s.source_id for s in self.sources}) != len(self.sources):
            raise ValueError("Duplicate authority source")
        return self

    def authorize(
        self, source_id: str, operation: str, query: AuthorityQuery
    ) -> AuthoritySource | None:
        return next(
            (
                s
                for s in self.sources
                if s.source_id == source_id
                and s.approved
                and operation in s.operations
                and (query.organization_id, query.collection_id) in s.scopes
                and query.data_classification in s.classifications
            ),
            None,
        )


class PartiesIdentity(Frozen):
    source_system: str = Field(min_length=1)
    connection_id: str = Field(min_length=1)
    tenant: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    environment: str = Field(min_length=1)
    module: Literal["eparties"] = "eparties"
    irn: int = Field(gt=0, strict=True)


class AuthorityCandidate(Frozen):
    identifier: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=2000)
    source_version: str = Field(min_length=1)
    relation: Literal["supports", "contradicts", "unresolved"]
    reason: str
    evidence_ids: tuple[str, ...]
    identity: PartiesIdentity | None = None
    context_json: str = "{}"


class AuthorityResult(Frozen):
    source_id: str
    source_version: str
    adapter_version: str
    operation: str
    status: LookupStatus
    literal: str
    evidence_ids: tuple[str, ...]
    query_json: str
    input_sha256: str
    retrieved_at: str
    candidates: tuple[AuthorityCandidate, ...] = ()
    reasons: tuple[str, ...] = ()
    raw_ref: str | None = None
    response_sha256: str | None = None
    retry_after_seconds: int | None = None
    license: str | None = None

    @property
    def operationally_blocked(self) -> bool:
        return self.status in OPERATIONAL


def result_base(
    query: AuthorityQuery,
    source_id: str,
    operation: str,
    adapter_version: str,
    source: AuthoritySource | None,
    parameters: object,
) -> dict:
    query_json = canonical(
        {"input": query.model_dump(mode="json"), "parameters": parameters}
    )
    return dict(
        source_id=source_id,
        source_version=source.version if source else "unconfigured",
        adapter_version=adapter_version,
        operation=operation,
        literal=query.literal,
        evidence_ids=query.evidence_ids,
        query_json=query_json,
        input_sha256=digest(query_json.encode()),
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        license=source.license if source else None,
    )


class BlobWriter(Protocol):
    def put(self, content: bytes) -> str: ...


class CapturedResponse(Frozen):
    status: LookupStatus
    body: bytes = b""
    raw_ref: str | None = None
    response_sha256: str | None = None
    retry_after_seconds: int | None = None
    truncated: bool = False


def read_authority(
    source: AuthoritySource,
    blobs: BlobWriter,
    client: httpx.Client,
    *,
    method: str = "GET",
    params: dict | None = None,
    data: dict | None = None,
    headers: dict | None = None,
) -> CapturedResponse:
    """One bounded attempt; retries/checkpoint scheduling belong to the outer workflow.

    No redirects, response links, provider-supplied URLs or executable code are followed.
    Oversize evidence captures the bounded prefix and is explicitly marked truncated.
    """
    started = time.monotonic()
    body = bytearray()
    try:
        with client.stream(
            method,
            source.endpoint,
            params=params,
            data=data,
            headers=headers,
            timeout=httpx.Timeout(source.timeout_seconds),
            follow_redirects=False,
        ) as response:
            truncated = False
            for chunk in response.iter_bytes(chunk_size=8192):
                available = source.max_response_bytes - len(body)
                body.extend(chunk[:available])
                if len(chunk) > available:
                    truncated = True
                    break
                if time.monotonic() - started > source.timeout_seconds:
                    raise httpx.ReadTimeout("authority deadline")
            raw = bytes(body)
            ref = blobs.put(raw)
            status = {
                200: LookupStatus.SUCCESS,
                401: LookupStatus.AUTHENTICATION,
                403: LookupStatus.AUTHORIZATION,
                429: LookupStatus.RATE_LIMITED,
            }.get(response.status_code, LookupStatus.PROVIDER)
            if truncated:
                status = LookupStatus.MALFORMED
            retry = response.headers.get("Retry-After", "")
            seconds = None
            try:
                seconds = (
                    int(retry)
                    if retry.isdigit()
                    else int(
                        (
                            parsedate_to_datetime(retry) - datetime.now(timezone.utc)
                        ).total_seconds()
                    )
                )
                seconds = max(0, min(seconds, 86400))
            except (TypeError, ValueError, OverflowError):
                pass
            return CapturedResponse(
                status=status,
                body=raw,
                raw_ref=ref,
                response_sha256=digest(raw),
                retry_after_seconds=seconds,
                truncated=truncated,
            )
    except httpx.TimeoutException:
        status = LookupStatus.TIMEOUT
    except httpx.HTTPError:
        status = LookupStatus.PROVIDER
    # Partial bytes are retained and never represented as a full response.
    raw = bytes(body)
    return CapturedResponse(
        status=status,
        body=raw,
        raw_ref=blobs.put(raw) if raw else None,
        response_sha256=digest(raw) if raw else None,
        truncated=bool(raw),
    )


def response_fields(response: CapturedResponse) -> dict:
    return dict(
        raw_ref=response.raw_ref,
        response_sha256=response.response_sha256,
        retry_after_seconds=response.retry_after_seconds,
        reasons=("response_capture_truncated",) if response.truncated else (),
    )
