from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_conversation_service
from app.api.schemas import HealthResponse, VersionResponse
from app.core.conversation.service import ConversationService
from app.domain.conversation.contracts import ChannelResponse, ConversationMessage
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
