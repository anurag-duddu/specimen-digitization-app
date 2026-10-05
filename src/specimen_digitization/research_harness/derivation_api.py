"""Private authenticated G38 enqueue and persisted proposal endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path
from specimen_digitization.application.domain import Principal
from .api import IdentifierPath, _PrivateResearchRoute
from .derivation_contracts import (
    DerivationAccepted, DerivationCapability, DerivationRequest, DerivationResultRead,
)


def create_derivation_router(service, *, verified_principal_dependency):
    router = APIRouter(prefix="/v1/organizations/{organization_id}/collections/{collection_id}"
        "/specimens/{specimen_id}/research/derivations", tags=["research"],
        route_class=_PrivateResearchRoute)
    identity = Depends(verified_principal_dependency)

    @router.get("/capability", response_model=DerivationCapability)
    async def capability(organization_id: IdentifierPath, collection_id: IdentifierPath,
                         specimen_id: IdentifierPath, principal: Principal = identity):
        return await service.capability(principal, specimen_id)

    @router.post("", response_model=DerivationAccepted, status_code=202)
    async def enqueue(organization_id: IdentifierPath, collection_id: IdentifierPath,
                      specimen_id: IdentifierPath, request: DerivationRequest,
                      idempotency_key: Annotated[str, Header(min_length=1, max_length=200)],
                      principal: Principal = identity):
        return await service.enqueue(principal, specimen_id, request, idempotency_key)

    @router.get("/{request_id}", response_model=DerivationResultRead)
    async def result(organization_id: IdentifierPath, collection_id: IdentifierPath,
                     specimen_id: IdentifierPath,
                     request_id: Annotated[str, Path(pattern=r"^[a-f0-9]{64}$")],
                     principal: Principal = identity):
        return await service.result(principal, specimen_id, request_id)

    return router
