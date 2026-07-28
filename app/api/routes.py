from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_conversation_service, get_organization_service
from app.api.schemas import HealthResponse, VersionResponse
from app.application.organizations.service import (
    OrganizationConflictError,
    OrganizationNotFoundError,
    OrganizationService,
)
from app.core.conversation.service import ConversationService
from app.domain.conversation.contracts import ChannelResponse, ConversationMessage
from app.domain.organization.contracts import (
    OrganizationCreate,
    OrganizationListResponse,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.infrastructure.settings import get_settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/version", response_model=VersionResponse, tags=["system"])
def version() -> VersionResponse:
    settings = get_settings()
    return VersionResponse(
        app_name=settings.app_name,
        api_version=settings.api_version,
        environment=settings.environment,
    )


@router.post(
    "/conversation/message",
    response_model=ChannelResponse,
    tags=["conversation"],
)
def receive_conversation_message(
    message: ConversationMessage,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> ChannelResponse:
    return service.handle_message(message)


@router.post(
    "/messages",
    response_model=ChannelResponse,
    tags=["vs1"],
)
def receive_vs1_message(
    message: ConversationMessage,
    service: Annotated[ConversationService, Depends(get_conversation_service)],
) -> ChannelResponse:
    return service.handle_message(message)


@router.post(
    "/organizations",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["organizations"],
)
def create_organization(
    request: OrganizationCreate,
    service: Annotated[OrganizationService, Depends(get_organization_service)],
) -> OrganizationResponse:
    try:
        organization = service.create(request)
    except OrganizationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return OrganizationResponse(organization=organization)


@router.get(
    "/organizations",
    response_model=OrganizationListResponse,
    tags=["organizations"],
)
def list_organizations(
    service: Annotated[OrganizationService, Depends(get_organization_service)],
) -> OrganizationListResponse:
    organizations = service.list()
    return OrganizationListResponse(
        organizations=organizations,
        total=len(organizations),
    )


@router.get(
    "/organizations/{organization_id}",
    response_model=OrganizationResponse,
    tags=["organizations"],
)
def get_organization(
    organization_id: UUID,
    service: Annotated[OrganizationService, Depends(get_organization_service)],
) -> OrganizationResponse:
    try:
        organization = service.get(organization_id)
    except OrganizationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return OrganizationResponse(organization=organization)


@router.patch(
    "/organizations/{organization_id}",
    response_model=OrganizationResponse,
    tags=["organizations"],
)
def update_organization(
    organization_id: UUID,
    request: OrganizationUpdate,
    service: Annotated[OrganizationService, Depends(get_organization_service)],
) -> OrganizationResponse:
    try:
        organization = service.update(organization_id, request)
    except OrganizationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except OrganizationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return OrganizationResponse(organization=organization)


@router.post(
    "/organizations/{organization_id}/deactivate",
    response_model=OrganizationResponse,
    tags=["organizations"],
)
def deactivate_organization(
    organization_id: UUID,
    service: Annotated[OrganizationService, Depends(get_organization_service)],
) -> OrganizationResponse:
    try:
        organization = service.deactivate(organization_id)
    except OrganizationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return OrganizationResponse(organization=organization)
