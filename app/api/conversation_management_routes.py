from collections.abc import Callable
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.conversation_management_dependencies import (
    get_conversation_management_service,
)
from app.api.dependencies import require_permission
from app.application.conversation_management.service import (
    ConversationManagementConflictError,
    ConversationManagementForbiddenError,
    ConversationManagementNotFoundError,
    ConversationManagementService,
)
from app.domain.conversation_management.contracts import (
    ConversationDetail,
    ConversationListResponse,
    ConversationMessageListResponse,
)
from app.domain.user.contracts import User

router = APIRouter(
    prefix="/organizations/{organization_id}/conversations",
    tags=["conversation-management"],
)
logger = structlog.get_logger(__name__)


def _raise(exc: ValueError) -> None:
    if isinstance(exc, ConversationManagementConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    if isinstance(exc, ConversationManagementNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found"
        ) from exc
    if isinstance(exc, ConversationManagementForbiddenError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="permission denied"
        ) from exc
    raise exc


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    organization_id: UUID,
    service: Annotated[
        ConversationManagementService, Depends(get_conversation_management_service)
    ],
    actor: Annotated[User, Depends(require_permission("conversation.read"))],
    bot_id: UUID | None = None,
    channel_type: str | None = Query(default=None, min_length=1, max_length=50),
    conversation_status: str | None = Query(
        default=None, alias="status", pattern="^(open|closed|archived)$"
    ),
    external_customer_id: str | None = Query(
        default=None, min_length=1, max_length=255
    ),
    has_inbound: bool | None = None,
    has_outbound: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ConversationListResponse:
    try:
        items, total = service.list(
            organization_id,
            actor,
            bot_id=bot_id,
            channel_type=channel_type,
            management_status=conversation_status,
            external_customer_id=external_customer_id,
            has_inbound=has_inbound,
            has_outbound=has_outbound,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        _raise(exc)
    logger.info(
        "conversation.list_accessed",
        organization_id=str(organization_id),
        actor_id=str(actor.id),
    )
    return ConversationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=page * page_size < total,
        has_previous=page > 1,
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    organization_id: UUID,
    conversation_id: UUID,
    service: Annotated[
        ConversationManagementService, Depends(get_conversation_management_service)
    ],
    actor: Annotated[User, Depends(require_permission("conversation.read"))],
) -> ConversationDetail:
    try:
        result = service.get(organization_id, conversation_id, actor)
    except ValueError as exc:
        _raise(exc)
    logger.info(
        "conversation.detail_accessed",
        conversation_id=str(conversation_id),
        organization_id=str(organization_id),
        actor_id=str(actor.id),
    )
    return result


@router.get(
    "/{conversation_id}/messages", response_model=ConversationMessageListResponse
)
def list_messages(
    organization_id: UUID,
    conversation_id: UUID,
    service: Annotated[
        ConversationManagementService, Depends(get_conversation_management_service)
    ],
    actor: Annotated[User, Depends(require_permission("conversation.read_content"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> ConversationMessageListResponse:
    try:
        items, total = service.list_messages(
            organization_id, conversation_id, actor, page=page, page_size=page_size
        )
    except ValueError as exc:
        _raise(exc)
    return ConversationMessageListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=page * page_size < total,
        has_previous=page > 1,
    )


def _transition(target: str) -> Callable[..., ConversationDetail]:
    def operation(
        organization_id: UUID,
        conversation_id: UUID,
        service: Annotated[
            ConversationManagementService, Depends(get_conversation_management_service)
        ],
        actor: Annotated[
            User,
            Depends(
                require_permission(
                    "conversation.archive"
                    if target == "archived"
                    else "conversation.close"
                )
            ),
        ],
    ) -> ConversationDetail:
        try:
            result = service.transition(organization_id, conversation_id, target, actor)
        except ValueError as exc:
            _raise(exc)
        logger.info(
            f"conversation.{target}",
            conversation_id=str(conversation_id),
            organization_id=str(organization_id),
            actor_id=str(actor.id),
        )
        return result

    return operation


router.post("/{conversation_id}/close", response_model=ConversationDetail)(
    _transition("closed")
)
router.post("/{conversation_id}/reopen", response_model=ConversationDetail)(
    _transition("open")
)
router.post("/{conversation_id}/archive", response_model=ConversationDetail)(
    _transition("archived")
)
