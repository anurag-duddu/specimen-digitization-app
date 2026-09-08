"""Read-only EMu eparties search; never a catalogue-IRN or name-only resolver.

Wire contract: Axiell emurestapi 3.1.3 Texpress search and Field Museum examples.
The museum must approve the exact connection, read fields and matching policy.
"""

import json
import re
from urllib.parse import urlsplit

import httpx
from pydantic import Field, SecretStr

from .authority_registry import (
    AuthorityCandidate,
    AuthorityQuery,
    AuthorityRegistry,
    AuthorityResult,
    BlobWriter,
    Frozen,
    PartiesIdentity,
    canonical,
    read_authority,
    result_base,
    response_fields,
)
from .domain import LookupStatus


class PartiesConnection(Frozen):
    source_id: str
    source_system: str = Field(min_length=1)
    connection_id: str = Field(min_length=1)
    tenant: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    environment: str = Field(min_length=1)
    max_candidates: int = Field(default=10, ge=1, le=50)


class PartiesAdapter:
    version = "emu-parties-search-1"
    operation = "eparties_search"

    def __init__(
        self,
        registry: AuthorityRegistry,
        blobs: BlobWriter,
        connection: PartiesConnection | None = None,
        token: SecretStr | None = None,
        client: httpx.Client | None = None,
    ):
        self.registry, self.blobs, self.connection, self.token = (
            registry,
            blobs,
            connection,
            token,
        )
        self.client = client or httpx.Client(
            headers={"User-Agent": "SpecimenDigitization/0.1"}
        )

    def lookup(self, query: AuthorityQuery) -> AuthorityResult:
        connection = self.connection
        source_id = connection.source_id if connection else "field_museum_parties"
        source = self.registry.authorize(source_id, self.operation, query)
        parameters = {
            "filter": canonical(
                {"AND": [{"data.NamFullName": {"exact": {"value": query.literal}}}]}
            ),
            "select": "id,version,data.NamFullName",
            "limit": connection.max_candidates if connection else 10,
        }
        base = result_base(
            query, source_id, self.operation, self.version, source, parameters
        )
        if not source or not connection:
            return AuthorityResult(
                **base,
                status=LookupStatus.POLICY,
                reasons=("parties_source_not_approved_or_configured",),
            )
        if urlsplit(source.endpoint).path != f"/{connection.tenant}/eparties":
            return AuthorityResult(
                **base,
                status=LookupStatus.POLICY,
                reasons=("parties_endpoint_module_or_tenant_mismatch",),
            )
        if not self.token or not self.token.get_secret_value():
            return AuthorityResult(
                **base,
                status=LookupStatus.AUTHENTICATION,
                reasons=("parties_credential_missing",),
            )
        response = read_authority(
            source,
            self.blobs,
            self.client,
            method="POST",
            data=parameters,
            headers={
                "Authorization": "Bearer " + self.token.get_secret_value(),
                "X-HTTP-Method-Override": "GET",
                "Prefer": "representation=minimal",
            },
        )
        fields = response_fields(response)
        if response.status != LookupStatus.SUCCESS:
            return AuthorityResult(**base, **fields, status=response.status)
        if not response.body:
            return AuthorityResult(**base, **fields, status=LookupStatus.EMPTY)
        try:
            payload = json.loads(response.body)
            hits, matches = payload["hits"], payload["matches"]
            if (
                type(hits) is not int
                or hits < 0
                or not isinstance(matches, list)
                or len(matches) > connection.max_candidates
                or hits < len(matches)
            ):
                raise ValueError("Invalid match count")
            candidates = []
            for match in matches:
                identifier, name, version = (
                    match["id"],
                    match["data"]["NamFullName"],
                    match["version"],
                )
                parsed = re.fullmatch(
                    r"emu:/"
                    + re.escape(connection.tenant)
                    + r"/eparties/([1-9][0-9]*)",
                    identifier,
                )
                if (
                    not parsed
                    or not isinstance(name, str)
                    or not name.strip()
                    or type(version) is not int
                    or version < 1
                ):
                    raise ValueError("Invalid Parties identity or record version")
                identity = PartiesIdentity(
                    source_system=connection.source_system,
                    connection_id=connection.connection_id,
                    tenant=connection.tenant,
                    environment=connection.environment,
                    irn=int(parsed[1]),
                )
                candidates.append(
                    AuthorityCandidate(
                        identifier=identifier,
                        name=name,
                        source_version=str(version),
                        relation="supports" if name == query.literal else "unresolved",
                        reason="Authority name observation; person identity selection requires corroboration or reviewer decision",
                        evidence_ids=query.evidence_ids,
                        identity=identity,
                    )
                )
            if len({c.identifier for c in candidates}) != len(candidates):
                raise ValueError("Duplicate authority identities")
            # A unique name is not proof of person identity, even if the record is real.
            status = LookupStatus.NO_MATCH if hits == 0 else LookupStatus.AMBIGUOUS
            if hits and not matches:
                status = LookupStatus.EMPTY
            return AuthorityResult(
                **base, **fields, status=status, candidates=tuple(candidates)
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            return AuthorityResult(**base, **fields, status=LookupStatus.MALFORMED)
