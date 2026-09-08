"""GBIF GADM modern administrative candidates, never historical georeferencing."""

import json

import httpx

from .authority_registry import (
    AuthorityCandidate,
    AuthorityQuery,
    AuthorityRegistry,
    AuthorityResult,
    BlobWriter,
    canonical,
    read_authority,
    result_base,
    response_fields,
)
from .domain import LookupStatus


class GeographyAdapter:
    version = "gbif-gadm-1"
    operation = "gadm_search"
    source_id = "gbif_gadm"

    def __init__(
        self,
        registry: AuthorityRegistry,
        blobs: BlobWriter,
        client: httpx.Client | None = None,
    ):
        self.registry, self.blobs = registry, blobs
        self.client = client or httpx.Client(
            headers={
                "User-Agent": "SpecimenDigitization/0.1 (https://github.com/anurag-duddu/specimen-digitization-app)"
            }
        )

    def lookup(self, query: AuthorityQuery) -> AuthorityResult:
        source = self.registry.authorize(self.source_id, self.operation, query)
        params = {"q": query.literal, "limit": 20, "offset": 0}
        base = result_base(
            query, self.source_id, self.operation, self.version, source, params
        )
        if (
            not source
            or source.endpoint != "https://api.gbif.org/v1/geocode/gadm/search"
        ):
            return AuthorityResult(
                **base,
                status=LookupStatus.POLICY,
                reasons=("modern_geography_source_not_approved",),
            )
        response = read_authority(source, self.blobs, self.client, params=params)
        fields = response_fields(response)
        if response.status != LookupStatus.SUCCESS:
            return AuthorityResult(**base, **fields, status=response.status)
        if not response.body:
            return AuthorityResult(**base, **fields, status=LookupStatus.EMPTY)
        try:
            payload = json.loads(response.body)
            rows, ended = payload["results"], payload["endOfRecords"]
            if not isinstance(rows, list) or len(rows) > 20 or type(ended) is not bool:
                raise ValueError("Invalid search envelope")
            candidates = []
            for row in rows:
                identifier, name, level = row["id"], row["name"], row["gadmLevel"]
                variants, parents = (
                    row.get("variantName", []),
                    row.get("higherRegions", []),
                )
                if (
                    not isinstance(identifier, str)
                    or not isinstance(name, str)
                    or type(level) is not int
                    or not 0 <= level <= 5
                ):
                    raise ValueError("Invalid region")
                if (
                    not isinstance(variants, list)
                    or not all(isinstance(v, str) for v in variants)
                    or not isinstance(parents, list)
                ):
                    raise ValueError("Invalid geography alternatives")
                if not all(
                    isinstance(p, dict)
                    and isinstance(p.get("id"), str)
                    and isinstance(p.get("name"), str)
                    for p in parents
                ):
                    raise ValueError("Invalid containment")
                exact = query.literal.casefold() in {
                    name.casefold(),
                    *(v.casefold() for v in variants),
                }
                candidates.append(
                    AuthorityCandidate(
                        identifier=identifier,
                        name=name,
                        source_version=source.version,
                        relation="supports"
                        if exact and not query.historical_context
                        else "unresolved",
                        reason="Modern administrative name only; historical jurisdiction and precise locality remain separate",
                        evidence_ids=query.evidence_ids,
                        context_json=canonical(
                            {
                                "modern_parents": parents,
                                "variants": variants,
                                "level": level,
                                "historical_literal": query.historical_context,
                            }
                        ),
                    )
                )
            if len({c.identifier for c in candidates}) != len(candidates):
                raise ValueError("Duplicate GADM identities")
            status = (
                LookupStatus.NO_MATCH
                if not candidates and ended
                else LookupStatus.AMBIGUOUS
            )
            if len(candidates) == 1 and ended and candidates[0].relation == "supports":
                status = LookupStatus.SUCCESS
            return AuthorityResult(
                **base, **fields, status=status, candidates=tuple(candidates)
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            return AuthorityResult(**base, **fields, status=LookupStatus.MALFORMED)
