from collections.abc import Callable
from typing import Annotated, NoReturn
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.contacts_dependencies import get_contact_administration_service
from app.api.conversation_management_dependencies import (
    get_conversation_management_service,
)
from app.api.dependencies import require_permission
from app.application.contacts.administration import (
    ContactAdministrationError,
    ContactAdministrationForbiddenError,
    ContactAdministrationNotFoundError,
    ContactAdministrationService,
)
from app.application.conversation_management.service import (
    ConversationManagementForbiddenError,
    ConversationManagementService,
)
from app.domain.contacts.api_contracts import (
    ContactDetailResponse,
    ContactListResponse,
    ContactResponse,
    ContactUpdateRequest,
)
from app.domain.conversation_management.contracts import ConversationListResponse
from app.domain.user.contracts import User

router = APIRouter(
    prefix="/organizations/{organization_id}/contacts", tags=["contacts"]
)
logger = structlog.get_logger(__name__)


def _raise(exc: ValueError) -> NoReturn:
    if isinstance(exc, ContactAdministrationForbiddenError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="permission denied"
        ) from exc
    if isinstance(exc, ContactAdministrationNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="contact not found"
        ) from exc
    if isinstance(exc, ContactAdministrationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid contact request"
        ) from exc
    if isinstance(exc, ConversationManagementForbiddenError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="permission denied"
        ) from exc
    raise exc


@router.get("", response_model=ContactListResponse)
def list_contacts(
    organization_id: UUID,
    service: Annotated[
        ContactAdministrationService, Depends(get_contact_administration_service)
    ],
    actor: Annotated[User, Depends(require_permission("contacts.read"))],
    contact_status: str | None = Query(
        default=None, alias="status", pattern="^(active|archived)$"
    ),
    channel_type: str | None = Query(default=None, min_length=1, max_length=50),
    bot_id: UUID | None = None,
    identifier: str | None = Query(default=None, min_length=1, max_length=255),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ContactListResponse:
    try:
        items, total = service.list(
            organization_id,
            actor,
            contact_status=contact_status,
            channel_type=channel_type,
            bot_id=bot_id,
            identifier=identifier,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        _raise(exc)
    logger.info(
        "contacts.list_accessed",
        organization_id=str(organization_id),
        actor_id=str(actor.id),
    )
    return ContactListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=page * page_size < total,
        has_previous=page > 1,
    )


@router.get("/{contact_id}", response_model=ContactDetailResponse)
def get_contact(
    organization_id: UUID,
    contact_id: UUID,
    service: Annotated[
        ContactAdministrationService, Depends(get_contact_administration_service)
    ],
    actor: Annotated[User, Depends(require_permission("contacts.read"))],
) -> ContactDetailResponse:
    try:
        return service.get(organization_id, contact_id, actor)
    except ValueError as exc:
        _raise(exc)


@router.patch("/{contact_id}", response_model=ContactResponse)
def update_contact(
    organization_id: UUID,
    contact_id: UUID,
    payload: ContactUpdateRequest,
    service: Annotated[
        ContactAdministrationService, Depends(get_contact_administration_service)
    ],
    actor: Annotated[User, Depends(require_permission("contacts.update"))],
) -> ContactResponse:
    try:
        return service.update(
            organization_id,
            contact_id,
            actor,
            display_name=payload.display_name,
            notes=payload.notes,
        )
    except ValueError as exc:
        _raise(exc)


def _status_operation(target: str) -> Callable[..., ContactResponse]:
    def operation(
        organization_id: UUID,
        contact_id: UUID,
        service: Annotated[
            ContactAdministrationService, Depends(get_contact_administration_service)
        ],
        actor: Annotated[User, Depends(require_permission("contacts.archive"))],
    ) -> ContactResponse:
        try:
            return service.set_status(organization_id, contact_id, actor, target)
        except ValueError as exc:
            _raise(exc)

    return operation


router.post("/{contact_id}/archive", response_model=ContactResponse)(
    _status_operation("archived")
)
router.post("/{contact_id}/reactivate", response_model=ContactResponse)(
    _status_operation("active")
)


@router.get("/{contact_id}/conversations", response_model=ConversationListResponse)
def list_contact_conversations(
    organization_id: UUID,
    contact_id: UUID,
    contacts: Annotated[
        ContactAdministrationService, Depends(get_contact_administration_service)
    ],
    conversations: Annotated[
        ConversationManagementService, Depends(get_conversation_management_service)
    ],
    actor: Annotated[User, Depends(require_permission("contacts.read"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ConversationListResponse:
    try:
        contacts.get(organization_id, contact_id, actor)
        items, total = conversations.list_for_contact(
            organization_id, contact_id, actor, page=page, page_size=page_size
        )
    except ValueError as exc:
        _raise(exc)
    return ConversationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=page * page_size < total,
        has_previous=page > 1,
    )
