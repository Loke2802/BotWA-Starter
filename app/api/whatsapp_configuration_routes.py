from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import PlainTextResponse

from app.api.dependencies import require_permission
from app.api.whatsapp_configuration_dependencies import (
    get_whatsapp_configuration_service,
    get_whatsapp_webhook_validation_service,
)
from app.application.whatsapp_configuration.service import (
    WhatsAppConfigurationBotNotFoundError,
    WhatsAppConfigurationConflictError,
    WhatsAppConfigurationForbiddenError,
    WhatsAppConfigurationNotFoundError,
    WhatsAppConfigurationOrganizationInactiveError,
    WhatsAppConfigurationService,
)
from app.application.whatsapp_configuration.webhook import (
    WhatsAppWebhookValidationError,
    WhatsAppWebhookValidationService,
)
from app.domain.user.contracts import User
from app.domain.whatsapp_configuration.contracts import (
    WhatsAppChannelConfigurationCreate,
    WhatsAppChannelConfigurationListResponse,
    WhatsAppChannelConfigurationResponse,
    WhatsAppChannelConfigurationStatus,
    WhatsAppChannelConfigurationUpdate,
    WhatsAppSecretRotation,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/bots/{bot_id}/whatsapp-configurations",
    tags=["whatsapp-configuration"],
)
webhook_router = APIRouter(tags=["whatsapp-configuration"])


def _raise_configuration_error(exc: ValueError) -> None:
    if isinstance(
        exc,
        (
            WhatsAppConfigurationConflictError,
            WhatsAppConfigurationOrganizationInactiveError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    if isinstance(
        exc,
        (WhatsAppConfigurationNotFoundError, WhatsAppConfigurationBotNotFoundError),
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    if isinstance(exc, WhatsAppConfigurationForbiddenError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="permission denied",
        ) from exc
    raise exc


@router.post(
    "",
    response_model=WhatsAppChannelConfigurationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_configuration(
    organization_id: UUID,
    bot_id: UUID,
    request: WhatsAppChannelConfigurationCreate,
    service: Annotated[
        WhatsAppConfigurationService,
        Depends(get_whatsapp_configuration_service),
    ],
    actor: Annotated[User, Depends(require_permission("whatsapp_config.create"))],
) -> WhatsAppChannelConfigurationResponse:
    try:
        configuration = service.create(organization_id, bot_id, request, actor)
    except ValueError as exc:
        _raise_configuration_error(exc)
    return WhatsAppChannelConfigurationResponse(configuration=configuration)


@router.get("", response_model=WhatsAppChannelConfigurationListResponse)
def list_configurations(
    organization_id: UUID,
    bot_id: UUID,
    service: Annotated[
        WhatsAppConfigurationService,
        Depends(get_whatsapp_configuration_service),
    ],
    actor: Annotated[User, Depends(require_permission("whatsapp_config.read"))],
    configuration_status: Annotated[
        WhatsAppChannelConfigurationStatus | None,
        Query(alias="status"),
    ] = None,
    phone_number_id: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> WhatsAppChannelConfigurationListResponse:
    try:
        items, total = service.list(
            organization_id,
            bot_id,
            actor,
            status=configuration_status,
            phone_number_id=phone_number_id,
            search=search,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        _raise_configuration_error(exc)
    return WhatsAppChannelConfigurationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{configuration_id}",
    response_model=WhatsAppChannelConfigurationResponse,
)
def get_configuration(
    organization_id: UUID,
    bot_id: UUID,
    configuration_id: UUID,
    service: Annotated[
        WhatsAppConfigurationService,
        Depends(get_whatsapp_configuration_service),
    ],
    actor: Annotated[User, Depends(require_permission("whatsapp_config.read"))],
) -> WhatsAppChannelConfigurationResponse:
    try:
        configuration = service.get(
            organization_id,
            bot_id,
            configuration_id,
            actor,
        )
    except ValueError as exc:
        _raise_configuration_error(exc)
    return WhatsAppChannelConfigurationResponse(configuration=configuration)


@router.patch(
    "/{configuration_id}",
    response_model=WhatsAppChannelConfigurationResponse,
)
def update_configuration(
    organization_id: UUID,
    bot_id: UUID,
    configuration_id: UUID,
    request: WhatsAppChannelConfigurationUpdate,
    service: Annotated[
        WhatsAppConfigurationService,
        Depends(get_whatsapp_configuration_service),
    ],
    actor: Annotated[User, Depends(require_permission("whatsapp_config.update"))],
) -> WhatsAppChannelConfigurationResponse:
    try:
        configuration = service.update(
            organization_id,
            bot_id,
            configuration_id,
            request,
            actor,
        )
    except ValueError as exc:
        _raise_configuration_error(exc)
    return WhatsAppChannelConfigurationResponse(configuration=configuration)


@router.delete("/{configuration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_configuration(
    organization_id: UUID,
    bot_id: UUID,
    configuration_id: UUID,
    service: Annotated[
        WhatsAppConfigurationService,
        Depends(get_whatsapp_configuration_service),
    ],
    actor: Annotated[User, Depends(require_permission("whatsapp_config.delete"))],
) -> Response:
    try:
        service.delete(organization_id, bot_id, configuration_id, actor)
    except ValueError as exc:
        _raise_configuration_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{configuration_id}/activate",
    response_model=WhatsAppChannelConfigurationResponse,
)
def activate_configuration(
    organization_id: UUID,
    bot_id: UUID,
    configuration_id: UUID,
    service: Annotated[
        WhatsAppConfigurationService,
        Depends(get_whatsapp_configuration_service),
    ],
    actor: Annotated[User, Depends(require_permission("whatsapp_config.activate"))],
) -> WhatsAppChannelConfigurationResponse:
    try:
        configuration = service.activate(
            organization_id,
            bot_id,
            configuration_id,
            actor,
        )
    except ValueError as exc:
        _raise_configuration_error(exc)
    return WhatsAppChannelConfigurationResponse(configuration=configuration)


@router.post(
    "/{configuration_id}/deactivate",
    response_model=WhatsAppChannelConfigurationResponse,
)
def deactivate_configuration(
    organization_id: UUID,
    bot_id: UUID,
    configuration_id: UUID,
    service: Annotated[
        WhatsAppConfigurationService,
        Depends(get_whatsapp_configuration_service),
    ],
    actor: Annotated[User, Depends(require_permission("whatsapp_config.activate"))],
) -> WhatsAppChannelConfigurationResponse:
    try:
        configuration = service.deactivate(
            organization_id,
            bot_id,
            configuration_id,
            actor,
        )
    except ValueError as exc:
        _raise_configuration_error(exc)
    return WhatsAppChannelConfigurationResponse(configuration=configuration)


@router.post(
    "/{configuration_id}/rotate-secrets",
    response_model=WhatsAppChannelConfigurationResponse,
)
def rotate_configuration_secrets(
    organization_id: UUID,
    bot_id: UUID,
    configuration_id: UUID,
    request: WhatsAppSecretRotation,
    service: Annotated[
        WhatsAppConfigurationService,
        Depends(get_whatsapp_configuration_service),
    ],
    actor: Annotated[
        User,
        Depends(require_permission("whatsapp_config.rotate_secrets")),
    ],
) -> WhatsAppChannelConfigurationResponse:
    try:
        configuration = service.rotate_secrets(
            organization_id,
            bot_id,
            configuration_id,
            request,
            actor,
        )
    except ValueError as exc:
        _raise_configuration_error(exc)
    return WhatsAppChannelConfigurationResponse(configuration=configuration)


@webhook_router.get(
    "/webhooks/whatsapp/{public_webhook_id}",
    response_class=PlainTextResponse,
)
def verify_configured_webhook(
    public_webhook_id: UUID,
    service: Annotated[
        WhatsAppWebhookValidationService,
        Depends(get_whatsapp_webhook_validation_service),
    ],
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    try:
        challenge = service.verify_challenge(
            public_webhook_id,
            mode=hub_mode,
            verify_token=hub_verify_token,
            challenge=hub_challenge,
        )
    except WhatsAppWebhookValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="webhook verification failed",
        ) from exc
    return PlainTextResponse(challenge)


@webhook_router.post(
    "/webhooks/whatsapp/{public_webhook_id}/validate-signature",
    response_class=PlainTextResponse,
)
async def validate_configured_webhook_signature(
    public_webhook_id: UUID,
    request: Request,
    service: Annotated[
        WhatsAppWebhookValidationService,
        Depends(get_whatsapp_webhook_validation_service),
    ],
    signature: Annotated[
        str | None,
        Header(alias="X-Hub-Signature-256"),
    ] = None,
) -> PlainTextResponse:
    try:
        service.verify_signature(
            public_webhook_id,
            raw_body=await request.body(),
            signature_header=signature,
        )
    except WhatsAppWebhookValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="webhook signature is invalid",
        ) from exc
    return PlainTextResponse("Signature valid")
