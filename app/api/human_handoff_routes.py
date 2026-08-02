from collections.abc import Callable
from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import require_permission
from app.api.human_handoff_dependencies import get_human_handoff_service
from app.api.whatsapp_live_dependencies import get_whatsapp_live_message_processor
from app.application.human_handoff.service import (
    HandoffConflictError,
    HandoffForbiddenError,
    HumanHandoffService,
)
from app.application.whatsapp_live.processor import (
    WhatsAppLiveMessageProcessor,
    WhatsAppRuntimeRoutingError,
)
from app.domain.human_handoff.contracts import (
    HandoffListResponse,
    HandoffMessageRequest,
    HandoffRequest,
    HandoffSessionResponse,
    HandoffTransferRequest,
)
from app.domain.user.contracts import User

router = APIRouter(prefix="/organizations/{organization_id}", tags=["human-handoff"])


def _raise(exc: ValueError) -> NoReturn:
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
    except WhatsAppRuntimeRoutingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="channel is not available for this conversation",
        ) from exc
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


def _finish(return_to_bot: bool) -> Callable[..., HandoffSessionResponse]:
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


@router.post("/conversations/{conversation_id}/handoff/messages")
async def send_handoff_message(
    organization_id: UUID,
    conversation_id: UUID,
    payload: HandoffMessageRequest,
    service: Annotated[HumanHandoffService, _service()],
    processor: Annotated[
        WhatsAppLiveMessageProcessor, Depends(get_whatsapp_live_message_processor)
    ],
    actor: Annotated[User, Depends(require_permission("handoff.reply"))],
) -> dict[str, str]:
    try:
        service.authorize_reply(organization_id, conversation_id, actor)
        conversation = service._conversation(conversation_id, organization_id)
        if (
            conversation.channel_configuration_id is None
            or conversation.external_customer_id is None
            or conversation.bot_id is None
        ):
            raise HandoffConflictError("conversation channel is not resolvable")
        attempt = await processor.send_human_reply(
            conversation_id=conversation_id,
            organization_id=organization_id,
            bot_id=conversation.bot_id,
            channel_configuration_id=conversation.channel_configuration_id,
            recipient_id=conversation.external_customer_id,
            text=payload.text,
            idempotency_key=payload.idempotency_key,
            author_user_id=actor.id,
        )
    except ValueError as exc:
        _raise(exc)
    if attempt.last_error_code is not None:
        error_status = {
            "INVALID_REQUEST": status.HTTP_400_BAD_REQUEST,
            "RATE_LIMITED": status.HTTP_429_TOO_MANY_REQUESTS,
            "TIMEOUT": status.HTTP_503_SERVICE_UNAVAILABLE,
            "PROVIDER_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
        }.get(attempt.last_error_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        raise HTTPException(
            status_code=error_status,
            detail="message delivery could not be completed",
        )
    return {"attempt_id": str(attempt.id), "status": attempt.status}


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
