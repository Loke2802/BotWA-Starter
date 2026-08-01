from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import require_permission
from app.api.human_handoff_dependencies import get_human_handoff_service
from app.application.human_handoff.service import (
    HandoffConflictError,
    HandoffForbiddenError,
    HumanHandoffService,
)
from app.domain.human_handoff.contracts import (
    HandoffListResponse,
    HandoffRequest,
    HandoffSessionResponse,
    HandoffTransferRequest,
)
from app.domain.user.contracts import User

router = APIRouter(prefix="/organizations/{organization_id}", tags=["human-handoff"])


def _raise(exc: ValueError) -> None:
    code = (
        status.HTTP_409_CONFLICT
        if isinstance(exc, HandoffConflictError)
        else (
            status.HTTP_403_FORBIDDEN
            if isinstance(exc, HandoffForbiddenError)
            else status.HTTP_404_NOT_FOUND
        )
    )
    raise HTTPException(status_code=code, detail=str(exc)) from exc


def _service() -> object:
    return Depends(get_human_handoff_service)


@router.post(
    "/conversations/{conversation_id}/handoff/request",
    response_model=HandoffSessionResponse,
)
def request(
    organization_id: UUID,
    conversation_id: UUID,
    payload: HandoffRequest,
    service: Annotated[HumanHandoffService, _service()],
    actor: Annotated[User, Depends(require_permission("handoff.request"))],
) -> HandoffSessionResponse:
    try:
        return service.request(
            organization_id, conversation_id, actor, payload.reason_code
        )
    except ValueError as exc:
        _raise(exc)


@router.post(
    "/conversations/{conversation_id}/handoff/claim",
    response_model=HandoffSessionResponse,
)
def claim(
    organization_id: UUID,
    conversation_id: UUID,
    service: Annotated[HumanHandoffService, _service()],
    actor: Annotated[User, Depends(require_permission("handoff.claim"))],
) -> HandoffSessionResponse:
    try:
        return service.claim(organization_id, conversation_id, actor)
    except ValueError as exc:
        _raise(exc)


@router.post(
    "/conversations/{conversation_id}/handoff/release",
    response_model=HandoffSessionResponse,
)
def release(
    organization_id: UUID,
    conversation_id: UUID,
    service: Annotated[HumanHandoffService, _service()],
    actor: Annotated[User, Depends(require_permission("handoff.release"))],
) -> HandoffSessionResponse:
    try:
        return service.release(organization_id, conversation_id, actor)
    except ValueError as exc:
        _raise(exc)


@router.post(
    "/conversations/{conversation_id}/handoff/transfer",
    response_model=HandoffSessionResponse,
)
def transfer(
    organization_id: UUID,
    conversation_id: UUID,
    payload: HandoffTransferRequest,
    service: Annotated[HumanHandoffService, _service()],
    actor: Annotated[User, Depends(require_permission("handoff.transfer"))],
) -> HandoffSessionResponse:
    try:
        return service.transfer(
            organization_id, conversation_id, actor, payload.assigned_user_id
        )
    except ValueError as exc:
        _raise(exc)


def _finish(return_to_bot: bool):
    def operation(
        organization_id: UUID,
        conversation_id: UUID,
        service: Annotated[HumanHandoffService, _service()],
        actor: Annotated[User, Depends(require_permission("handoff.resolve"))],
    ) -> HandoffSessionResponse:
        try:
            return service.resolve(
                organization_id, conversation_id, actor, return_to_bot=return_to_bot
            )
        except ValueError as exc:
            _raise(exc)

    return operation


router.post(
    "/conversations/{conversation_id}/handoff/resolve",
    response_model=HandoffSessionResponse,
)(_finish(False))
router.post(
    "/conversations/{conversation_id}/handoff/return-to-bot",
    response_model=HandoffSessionResponse,
)(_finish(True))


@router.get(
    "/conversations/{conversation_id}/handoff", response_model=HandoffSessionResponse
)
def get_handoff(
    organization_id: UUID,
    conversation_id: UUID,
    service: Annotated[HumanHandoffService, _service()],
    actor: Annotated[User, Depends(require_permission("handoff.read"))],
) -> HandoffSessionResponse:
    try:
        return service.get(organization_id, conversation_id, actor)
    except ValueError as exc:
        _raise(exc)


@router.get("/handoffs", response_model=HandoffListResponse)
def list_handoffs(
    organization_id: UUID,
    service: Annotated[HumanHandoffService, _service()],
    actor: Annotated[User, Depends(require_permission("handoff.read"))],
    handoff_status: str | None = Query(default=None, alias="status"),
    bot_id: UUID | None = None,
    assigned_user_id: UUID | None = None,
    unassigned_only: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> HandoffListResponse:
    try:
        items, total = service.list(
            organization_id,
            actor,
            status=handoff_status,
            bot_id=bot_id,
            assigned_user_id=assigned_user_id,
            unassigned_only=unassigned_only,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        _raise(exc)
    return HandoffListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=page * page_size < total,
    )
