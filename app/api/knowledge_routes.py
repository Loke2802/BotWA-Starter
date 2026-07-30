from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.dependencies import require_permission
from app.api.knowledge_dependencies import get_knowledge_management_service
from app.application.knowledge_management.service import (
    KnowledgeEntryBotNotFoundError,
    KnowledgeEntryConflictError,
    KnowledgeEntryForbiddenError,
    KnowledgeEntryNotFoundError,
    KnowledgeEntryOrganizationInactiveError,
    KnowledgeManagementService,
)
from app.domain.knowledge_management.contracts import (
    KnowledgeEntryCreate,
    KnowledgeEntryListResponse,
    KnowledgeEntryResponse,
    KnowledgeEntryStatus,
    KnowledgeEntryUpdate,
)
from app.domain.user.contracts import User

router = APIRouter(
    prefix="/organizations/{organization_id}/bots/{bot_id}/knowledge",
    tags=["knowledge-management"],
)


def _raise_knowledge_error(exc: ValueError) -> None:
    if isinstance(
        exc,
        (KnowledgeEntryConflictError, KnowledgeEntryOrganizationInactiveError),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, (KnowledgeEntryNotFoundError, KnowledgeEntryBotNotFoundError)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if isinstance(exc, KnowledgeEntryForbiddenError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="permission denied",
        ) from exc
    raise exc


@router.post(
    "",
    response_model=KnowledgeEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_entry(
    organization_id: UUID,
    bot_id: UUID,
    request: KnowledgeEntryCreate,
    service: Annotated[
        KnowledgeManagementService,
        Depends(get_knowledge_management_service),
    ],
    actor: Annotated[User, Depends(require_permission("knowledge.create"))],
) -> KnowledgeEntryResponse:
    try:
        entry = service.create(organization_id, bot_id, request, actor)
    except ValueError as exc:
        _raise_knowledge_error(exc)
    return KnowledgeEntryResponse(knowledge_entry=entry)


@router.get("", response_model=KnowledgeEntryListResponse)
def list_knowledge_entries(
    organization_id: UUID,
    bot_id: UUID,
    service: Annotated[
        KnowledgeManagementService,
        Depends(get_knowledge_management_service),
    ],
    actor: Annotated[User, Depends(require_permission("knowledge.read"))],
    entry_status: Annotated[
        KnowledgeEntryStatus | None,
        Query(alias="status"),
    ] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> KnowledgeEntryListResponse:
    try:
        items, total = service.list(
            organization_id,
            bot_id,
            actor,
            status=entry_status,
            search=search,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        _raise_knowledge_error(exc)
    return KnowledgeEntryListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{knowledge_id}", response_model=KnowledgeEntryResponse)
def get_knowledge_entry(
    organization_id: UUID,
    bot_id: UUID,
    knowledge_id: UUID,
    service: Annotated[
        KnowledgeManagementService,
        Depends(get_knowledge_management_service),
    ],
    actor: Annotated[User, Depends(require_permission("knowledge.read"))],
) -> KnowledgeEntryResponse:
    try:
        entry = service.get(organization_id, bot_id, knowledge_id, actor)
    except ValueError as exc:
        _raise_knowledge_error(exc)
    return KnowledgeEntryResponse(knowledge_entry=entry)


@router.patch("/{knowledge_id}", response_model=KnowledgeEntryResponse)
def update_knowledge_entry(
    organization_id: UUID,
    bot_id: UUID,
    knowledge_id: UUID,
    request: KnowledgeEntryUpdate,
    service: Annotated[
        KnowledgeManagementService,
        Depends(get_knowledge_management_service),
    ],
    actor: Annotated[User, Depends(require_permission("knowledge.update"))],
) -> KnowledgeEntryResponse:
    try:
        entry = service.update(
            organization_id,
            bot_id,
            knowledge_id,
            request,
            actor,
        )
    except ValueError as exc:
        _raise_knowledge_error(exc)
    return KnowledgeEntryResponse(knowledge_entry=entry)


@router.delete("/{knowledge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_entry(
    organization_id: UUID,
    bot_id: UUID,
    knowledge_id: UUID,
    service: Annotated[
        KnowledgeManagementService,
        Depends(get_knowledge_management_service),
    ],
    actor: Annotated[User, Depends(require_permission("knowledge.delete"))],
) -> Response:
    try:
        service.delete(organization_id, bot_id, knowledge_id, actor)
    except ValueError as exc:
        _raise_knowledge_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{knowledge_id}/publish", response_model=KnowledgeEntryResponse)
def publish_knowledge_entry(
    organization_id: UUID,
    bot_id: UUID,
    knowledge_id: UUID,
    service: Annotated[
        KnowledgeManagementService,
        Depends(get_knowledge_management_service),
    ],
    actor: Annotated[User, Depends(require_permission("knowledge.publish"))],
) -> KnowledgeEntryResponse:
    try:
        entry = service.publish(organization_id, bot_id, knowledge_id, actor)
    except ValueError as exc:
        _raise_knowledge_error(exc)
    return KnowledgeEntryResponse(knowledge_entry=entry)


@router.post("/{knowledge_id}/archive", response_model=KnowledgeEntryResponse)
def archive_knowledge_entry(
    organization_id: UUID,
    bot_id: UUID,
    knowledge_id: UUID,
    service: Annotated[
        KnowledgeManagementService,
        Depends(get_knowledge_management_service),
    ],
    actor: Annotated[User, Depends(require_permission("knowledge.delete"))],
) -> KnowledgeEntryResponse:
    try:
        entry = service.archive(organization_id, bot_id, knowledge_id, actor)
    except ValueError as exc:
        _raise_knowledge_error(exc)
    return KnowledgeEntryResponse(knowledge_entry=entry)
