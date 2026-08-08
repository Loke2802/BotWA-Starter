from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import require_permission
from app.api.integration_management_dependencies import (
    get_integration_management_service,
)
from app.application.integration_management.service import (
    IntegrationConflictError,
    IntegrationCredentialError,
    IntegrationForbiddenError,
    IntegrationManagementError,
    IntegrationManagementService,
    IntegrationNotFoundError,
    IntegrationOAuthStateError,
    IntegrationValidationError,
)
from app.domain.integration_management.contracts import (
    IntegrationConnectionCreate,
    IntegrationConnectionListResponse,
    IntegrationConnectionResponse,
    IntegrationConnectionUpdate,
    IntegrationCredentialInput,
    IntegrationCredentialResponse,
    IntegrationHealthCheckResponse,
    IntegrationHealthListResponse,
    OAuthCallbackResponse,
    OAuthStartResponse,
)
from app.domain.user.contracts import User

router = APIRouter(
    prefix="/organizations/{organization_id}/integrations",
    tags=["integration-management"],
)
oauth_router = APIRouter(tags=["integration-management-oauth"])


def _raise(exc: IntegrationManagementError) -> NoReturn:
    if isinstance(exc, IntegrationNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, IntegrationForbiddenError):
        code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, IntegrationConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(
        exc,
        (
            IntegrationValidationError,
            IntegrationCredentialError,
            IntegrationOAuthStateError,
        ),
    ):
        code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        code = status.HTTP_502_BAD_GATEWAY
    raise HTTPException(status_code=code, detail={"code": exc.safe_code}) from exc


@router.post(
    "",
    response_model=IntegrationConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_integration(
    organization_id: UUID,
    payload: IntegrationConnectionCreate,
    service: Annotated[
        IntegrationManagementService, Depends(get_integration_management_service)
    ],
    actor: Annotated[User, Depends(require_permission("integration.create"))],
) -> IntegrationConnectionResponse:
    try:
        return service.create(organization_id, payload, actor)
    except IntegrationManagementError as exc:
        _raise(exc)


@router.get("", response_model=IntegrationConnectionListResponse)
def list_integrations(
    organization_id: UUID,
    service: Annotated[
        IntegrationManagementService, Depends(get_integration_management_service)
    ],
    actor: Annotated[User, Depends(require_permission("integration.read"))],
    status_filter: str | None = Query(None, alias="status"),
    provider: str | None = None,
    bot_id: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> IntegrationConnectionListResponse:
    try:
        items, total = service.list_connections(
            organization_id,
            actor,
            status=status_filter,
            provider=provider,
            bot_id=bot_id,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return IntegrationConnectionListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
        )
    except IntegrationManagementError as exc:
        _raise(exc)


@router.get("/{integration_id}", response_model=IntegrationConnectionResponse)
def get_integration(
    organization_id: UUID,
    integration_id: UUID,
    service: Annotated[
        IntegrationManagementService, Depends(get_integration_management_service)
    ],
    actor: Annotated[User, Depends(require_permission("integration.read"))],
) -> IntegrationConnectionResponse:
    try:
        return service.get(organization_id, integration_id, actor)
    except IntegrationManagementError as exc:
        _raise(exc)


@router.patch("/{integration_id}", response_model=IntegrationConnectionResponse)
def update_integration(
    organization_id: UUID,
    integration_id: UUID,
    payload: IntegrationConnectionUpdate,
    service: Annotated[
        IntegrationManagementService, Depends(get_integration_management_service)
    ],
    actor: Annotated[User, Depends(require_permission("integration.update"))],
) -> IntegrationConnectionResponse:
    try:
        return service.update(organization_id, integration_id, payload, actor)
    except IntegrationManagementError as exc:
        _raise(exc)


@router.post("/{integration_id}/activate", response_model=IntegrationConnectionResponse)
def activate_integration(
    organization_id: UUID,
    integration_id: UUID,
    service: Annotated[
        IntegrationManagementService, Depends(get_integration_management_service)
    ],
    actor: Annotated[User, Depends(require_permission("integration.activate"))],
) -> IntegrationConnectionResponse:
    try:
        return service.activate(organization_id, integration_id, actor)
    except IntegrationManagementError as exc:
        _raise(exc)


@router.post(
    "/{integration_id}/deactivate", response_model=IntegrationConnectionResponse
)
def deactivate_integration(
    organization_id: UUID,
    integration_id: UUID,
    service: Annotated[
        IntegrationManagementService, Depends(get_integration_management_service)
    ],
    actor: Annotated[User, Depends(require_permission("integration.deactivate"))],
) -> IntegrationConnectionResponse:
    try:
        return service.deactivate(organization_id, integration_id, actor)
    except IntegrationManagementError as exc:
        _raise(exc)


@router.post("/{integration_id}/archive", response_model=IntegrationConnectionResponse)
def archive_integration(
    organization_id: UUID,
    integration_id: UUID,
    service: Annotated[
        IntegrationManagementService, Depends(get_integration_management_service)
    ],
    actor: Annotated[User, Depends(require_permission("integration.archive"))],
) -> IntegrationConnectionResponse:
    try:
        return service.archive(organization_id, integration_id, actor)
    except IntegrationManagementError as exc:
        _raise(exc)


@router.put(
    "/{integration_id}/credentials", response_model=IntegrationCredentialResponse
)
def update_integration_credentials(
    organization_id: UUID,
    integration_id: UUID,
    payload: IntegrationCredentialInput,
    service: Annotated[
        IntegrationManagementService, Depends(get_integration_management_service)
    ],
    actor: Annotated[
        User, Depends(require_permission("integration.credentials.update"))
    ],
) -> IntegrationCredentialResponse:
    try:
        return service.update_credentials(
            organization_id, integration_id, payload, actor
        )
    except IntegrationManagementError as exc:
        _raise(exc)


@router.get("/{integration_id}/health", response_model=IntegrationHealthListResponse)
def get_integration_health(
    organization_id: UUID,
    integration_id: UUID,
    service: Annotated[
        IntegrationManagementService, Depends(get_integration_management_service)
    ],
    actor: Annotated[User, Depends(require_permission("integration.health.read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> IntegrationHealthListResponse:
    try:
        items, total = service.health_history(
            organization_id,
            integration_id,
            actor,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return IntegrationHealthListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
        )
    except IntegrationManagementError as exc:
        _raise(exc)


@router.post(
    "/{integration_id}/health-check", response_model=IntegrationHealthCheckResponse
)
def check_integration_health(
    organization_id: UUID,
    integration_id: UUID,
    service: Annotated[
        IntegrationManagementService, Depends(get_integration_management_service)
    ],
    actor: Annotated[User, Depends(require_permission("integration.health.check"))],
) -> IntegrationHealthCheckResponse:
    try:
        return service.check_health(organization_id, integration_id, actor)
    except IntegrationManagementError as exc:
        _raise(exc)


@router.post("/{integration_id}/oauth/google/start", response_model=OAuthStartResponse)
def start_google_oauth(
    organization_id: UUID,
    integration_id: UUID,
    service: Annotated[
        IntegrationManagementService, Depends(get_integration_management_service)
    ],
    actor: Annotated[
        User, Depends(require_permission("integration.credentials.update"))
    ],
) -> OAuthStartResponse:
    try:
        return service.start_google_oauth(organization_id, integration_id, actor)
    except IntegrationManagementError as exc:
        _raise(exc)


@oauth_router.get(
    "/integrations/oauth/google/callback", response_model=OAuthCallbackResponse
)
def google_oauth_callback(
    state: str,
    code: str,
    service: Annotated[
        IntegrationManagementService, Depends(get_integration_management_service)
    ],
) -> OAuthCallbackResponse:
    try:
        return service.complete_google_oauth(state, code)
    except IntegrationManagementError as exc:
        _raise(exc)
