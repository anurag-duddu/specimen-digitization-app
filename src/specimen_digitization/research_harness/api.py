"""Optional versioned router; the existing application's owner supplies auth.

No application mount, identity verifier, bearer parser or global error handler
is installed by importing or constructing this router.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from specimen_digitization.application.domain import Principal
from specimen_digitization.process_logging import log_code

from .canonical_binding import BindingUnavailable
from .compatibility import PublicationUnavailable
from .contracts import FieldKey
from .persistence import BudgetExceeded, CasConflict, HeldUnknown, StaleWork
from .service import ResearchLocator, ResearchService, RetryAccepted, RetryFieldRequest
from .thread_view import ResearchThread
from .status import ResearchStatusV1, ResearchOutputV1
from .discovery import ResearchDiscovery, ResearchDiscoveryResult

LOGGER = logging.getLogger(__name__)
# The repository's fixed-code exception types: raised with a short code as the
# only argument. log_code checks that shape before anything is logged, so a
# message that is not a code is dropped rather than written.
_FIXED_CODE_ERRORS = (PublicationUnavailable, BindingUnavailable)
_NO_CACHE = {"Cache-Control":"no-store, private", "Pragma":"no-cache"}
IdentifierPath = Annotated[str, Path(min_length=1, max_length=100)]
GenerationPath = Annotated[int, Path(ge=1)]
JobPath = Annotated[str, Path(min_length=1, max_length=256)]


def _log_unavailable(method: str, route_path: str, error: Exception) -> None:
    """Record why a private 503 happened; the response itself stays opaque.

    Logged: the HTTP method, the route template (never the ids in the path; the
    request log line carries those), the exception class and, for the repository's
    fixed-code types, the code. Never the message of any other exception (a
    validation or provider error can embed input text) and never a traceback.

    This runs inside the catch-all: it must never change the response, so any error
    while describing the failure is reduced to a bare line.
    """
    try:
        if isinstance(error, _FIXED_CODE_ERRORS):
            code = log_code(error.args[0] if len(error.args) == 1 else None)
            LOGGER.warning("research route unavailable: %s %s error_class=%s code=%s",
                           method, route_path, type(error).__name__, code)
        else:
            LOGGER.error("research route unavailable: %s %s error_class=%s",
                         method, route_path, type(error).__name__)
    except Exception:  # noqa: BLE001 - describing a failure must not change the response
        LOGGER.error("research route unavailable: details unavailable")


class _PrivateResearchRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        route_path = self.path

        async def private_handler(request: Request):
            try:
                if request.query_params:
                    raise RequestValidationError([])
                response = await original(request)
            except RequestValidationError:
                response = JSONResponse({"detail":"invalid_research_request"}, status_code=422)
            except HTTPException as error:
                code = "research_access_required" if error.status_code == 401 else "research_request_denied"
                response = JSONResponse({"detail":code}, status_code=error.status_code)
            except PermissionError:
                response = JSONResponse({"detail":"research_access_denied"}, status_code=403)
            except (StaleWork, CasConflict):
                response = JSONResponse({"detail":"research_state_changed"}, status_code=409)
            except (HeldUnknown, BudgetExceeded):
                response = JSONResponse({"detail":"research_retry_unavailable"}, status_code=409)
            except Exception as error:
                _log_unavailable(request.method, route_path, error)
                response = JSONResponse({"detail":"research_service_unavailable"}, status_code=503)
            response.headers.update(_NO_CACHE)
            return response

        return private_handler


def create_research_router(
    service: ResearchService, *, verified_principal_dependency: Callable,
) -> APIRouter:
    """Inject the application's existing verified identity/membership dependency.

    The dependency returns ``Principal`` and can bind organization/collection
    route parameters. This factory performs no identity or credential discovery.
    """
    router = APIRouter(
        prefix="/v1/organizations/{organization_id}/collections/{collection_id}"
        "/specimens/{specimen_id}/research/jobs/{job_id}/generations/{generation}",
        tags=["research"], route_class=_PrivateResearchRoute,
    )
    identity = Depends(verified_principal_dependency)
    @router.get("/thread", response_model=ResearchThread)
    async def thread(
        organization_id: IdentifierPath, collection_id: IdentifierPath,
        specimen_id: IdentifierPath, job_id: JobPath, generation: GenerationPath,
        principal: Principal = identity,
    ):
        locator = ResearchLocator(organization_id=organization_id, collection_id=collection_id,
            specimen_id=specimen_id, job_id=job_id, generation=generation)
        return await service.thread(principal, locator)

    @router.post("/fields/{field_key}/retry", response_model=RetryAccepted, status_code=202)
    async def retry(
        organization_id: IdentifierPath, collection_id: IdentifierPath,
        specimen_id: IdentifierPath, job_id: JobPath, generation: GenerationPath,
        field_key: FieldKey, request: RetryFieldRequest, principal: Principal = identity,
    ):
        locator = ResearchLocator(organization_id=organization_id, collection_id=collection_id,
            specimen_id=specimen_id, job_id=job_id, generation=generation)
        return await service.retry_field(principal, locator, field_key, request)

    @router.get("/status", response_model=ResearchStatusV1)
    async def status(organization_id: IdentifierPath, collection_id: IdentifierPath,
                     specimen_id: IdentifierPath, job_id: JobPath, generation: GenerationPath,
                     principal: Principal = identity):
        locator = ResearchLocator(organization_id=organization_id, collection_id=collection_id,
            specimen_id=specimen_id, job_id=job_id, generation=generation)
        return ResearchStatusV1.from_thread(await service.thread(principal, locator))

    @router.get("/output", response_model=ResearchOutputV1)
    async def output(organization_id: IdentifierPath, collection_id: IdentifierPath,
                     specimen_id: IdentifierPath, job_id: JobPath, generation: GenerationPath,
                     principal: Principal = identity):
        locator = ResearchLocator(organization_id=organization_id, collection_id=collection_id,
            specimen_id=specimen_id, job_id=job_id, generation=generation)
        return ResearchOutputV1.from_thread(await service.thread(principal, locator))

    return router


def create_research_discovery_router(
    discovery: ResearchDiscovery, *, verified_principal_dependency: Callable,
    result_model=ResearchDiscoveryResult,
) -> APIRouter:
    """Expose only coherent owner registration; a GET admits no worker/effect."""
    router = APIRouter(
        prefix="/v1/organizations/{organization_id}/collections/{collection_id}"
        "/specimens/{specimen_id}/research", tags=["research"],
        route_class=_PrivateResearchRoute,
    )
    identity = Depends(verified_principal_dependency)

    @router.get("/current", response_model=result_model)
    async def current(
        organization_id: IdentifierPath, collection_id: IdentifierPath,
        specimen_id: IdentifierPath, principal: Principal = identity,
    ):
        return await discovery.discover(principal, specimen_id)

    @router.get("/jobs", response_model=list[result_model])
    async def active_jobs(organization_id: IdentifierPath, collection_id: IdentifierPath,
                          specimen_id: IdentifierPath, principal: Principal = identity):
        # This lists the one owner-registered current job, not inferred history.
        return [await discovery.discover(principal, specimen_id)]

    return router
