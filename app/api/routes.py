from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_access_service,
    get_auth_service,
    get_bot_service,
    get_conversation_service,
    get_current_user,
    get_optional_current_user,
    get_organization_service,
    get_user_service,
    require_permission,
)
from app.api.schemas import HealthResponse, VersionResponse
from app.application.access.service import AccessService
from app.application.auth.service import (
    AuthInactiveUserError,
    AuthInvalidCredentialsError,
    AuthService,
)
from app.application.bots.service import (
    BotConflictError,
    BotForbiddenError,
    BotNotFoundError,
    BotOrganizationInactiveError,
    BotOrganizationNotFoundError,
    BotService,
)
from app.application.organizations.service import (
    OrganizationConflictError,
    OrganizationNotFoundError,
    OrganizationService,
)
from app.application.users.service import (
    LastOwnerProtectionError,
    OrganizationInactiveError,
    UserAuthenticationRequiredError,
    UserConflictError,
    UserForbiddenError,
    UserNotFoundError,
    UserService,
)
from app.core.conversation.service import ConversationService
from app.domain.access.contracts import (
    EffectivePermissionsResponse,
    RoleAssignmentRequest,
    RoleListResponse,
)
from app.domain.bot.contracts import (
    BotCreate,
    BotListResponse,
    BotResponse,
    BotUpdate,
)
from app.domain.conversation.contracts import ChannelResponse, ConversationMessage
from app.domain.organization.contracts import (
    OrganizationCreate,
    OrganizationListResponse,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.domain.user.contracts import (
    ChangePasswordRequest,
    CurrentUserResponse,
    LoginRequest,
    TokenResponse,
    User,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from app.infrastructure.settings import get_settings
from app.security.authorization import AuthorizationError, require_organization_access

router = APIRouter()


def _raise_bot_error(exc: ValueError) -> None:
    if isinstance(exc, BotConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, BotOrganizationInactiveError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if isinstance(exc, (BotNotFoundError, BotOrganizationNotFoundError)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if isinstance(exc, BotForbiddenError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    raise exc


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
    actor: Annotated[User, Depends(require_permission("organizations.read"))],
) -> OrganizationListResponse:
    organizations = service.list()
    if actor.role != "platform_admin":
        organizations = [
            organization
            for organization in organizations
            if organization.id == actor.organization_id
        ]
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
    actor: Annotated[User, Depends(require_permission("organizations.read"))],
) -> OrganizationResponse:
    try:
        organization = service.get(organization_id)
    except OrganizationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    try:
        require_organization_access(actor, organization_id)
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="permission denied",
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
    actor: Annotated[User, Depends(require_permission("organizations.update"))],
) -> OrganizationResponse:
    try:
        service.get(organization_id)
    except OrganizationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    try:
        require_organization_access(actor, organization_id)
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="permission denied",
        ) from exc
    try:
        organization = service.update(organization_id, request)
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
    actor: Annotated[User, Depends(require_permission("organizations.update"))],
) -> OrganizationResponse:
    try:
        service.get(organization_id)
    except OrganizationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    try:
        require_organization_access(actor, organization_id)
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="permission denied",
        ) from exc
    try:
        organization = service.deactivate(organization_id)
    except OrganizationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return OrganizationResponse(organization=organization)


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["users"],
)
def create_user(
    request: UserCreate,
    service: Annotated[UserService, Depends(get_user_service)],
    actor: Annotated[User | None, Depends(get_optional_current_user)],
) -> UserResponse:
    try:
        user = service.create(request, actor=actor)
    except UserConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except OrganizationInactiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except UserAuthenticationRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except UserForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return UserResponse(user=user)


@router.get(
    "/users",
    response_model=UserListResponse,
    tags=["users"],
)
def list_users(
    service: Annotated[UserService, Depends(get_user_service)],
    actor: Annotated[User, Depends(require_permission("users.read"))],
) -> UserListResponse:
    users = service.list(actor=actor)
    return UserListResponse(users=users, total=len(users))


@router.get(
    "/users/{user_id}",
    response_model=UserResponse,
    tags=["users"],
)
def get_user(
    user_id: UUID,
    service: Annotated[UserService, Depends(get_user_service)],
    actor: Annotated[User, Depends(require_permission("users.read"))],
) -> UserResponse:
    try:
        user = service.get(user_id, actor=actor)
    except UserForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return UserResponse(user=user)


@router.patch(
    "/users/{user_id}",
    response_model=UserResponse,
    tags=["users"],
)
def update_user(
    user_id: UUID,
    request: UserUpdate,
    service: Annotated[UserService, Depends(get_user_service)],
    actor: Annotated[User, Depends(require_permission("users.update"))],
) -> UserResponse:
    try:
        user = service.update(user_id, request, actor=actor)
    except UserForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return UserResponse(user=user)


@router.post(
    "/users/{user_id}/deactivate",
    response_model=UserResponse,
    tags=["users"],
)
def deactivate_user(
    user_id: UUID,
    service: Annotated[UserService, Depends(get_user_service)],
    actor: Annotated[User, Depends(require_permission("users.deactivate"))],
) -> UserResponse:
    try:
        user = service.deactivate(user_id, actor=actor)
    except UserForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except LastOwnerProtectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return UserResponse(user=user)


@router.post(
    "/bots",
    response_model=BotResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["bots"],
)
def create_bot(
    request: BotCreate,
    service: Annotated[BotService, Depends(get_bot_service)],
    actor: Annotated[User, Depends(require_permission("bots.create"))],
) -> BotResponse:
    try:
        bot = service.create(request, actor=actor)
    except ValueError as exc:
        _raise_bot_error(exc)
    return BotResponse(bot=bot)


@router.get(
    "/bots",
    response_model=BotListResponse,
    tags=["bots"],
)
def list_bots(
    service: Annotated[BotService, Depends(get_bot_service)],
    actor: Annotated[User, Depends(require_permission("bots.read"))],
) -> BotListResponse:
    try:
        bots = service.list(actor=actor)
    except ValueError as exc:
        _raise_bot_error(exc)
    return BotListResponse(bots=bots, total=len(bots))


@router.get(
    "/bots/{bot_id}",
    response_model=BotResponse,
    tags=["bots"],
)
def get_bot(
    bot_id: UUID,
    service: Annotated[BotService, Depends(get_bot_service)],
    actor: Annotated[User, Depends(require_permission("bots.read"))],
) -> BotResponse:
    try:
        bot = service.get(bot_id, actor=actor)
    except ValueError as exc:
        _raise_bot_error(exc)
    return BotResponse(bot=bot)


@router.patch(
    "/bots/{bot_id}",
    response_model=BotResponse,
    tags=["bots"],
)
def update_bot(
    bot_id: UUID,
    request: BotUpdate,
    service: Annotated[BotService, Depends(get_bot_service)],
    actor: Annotated[User, Depends(require_permission("bots.update"))],
) -> BotResponse:
    try:
        bot = service.update(bot_id, request, actor=actor)
    except ValueError as exc:
        _raise_bot_error(exc)
    return BotResponse(bot=bot)


@router.post(
    "/bots/{bot_id}/activate",
    response_model=BotResponse,
    tags=["bots"],
)
def activate_bot(
    bot_id: UUID,
    service: Annotated[BotService, Depends(get_bot_service)],
    actor: Annotated[User, Depends(require_permission("bots.activate"))],
) -> BotResponse:
    try:
        bot = service.activate(bot_id, actor=actor)
    except ValueError as exc:
        _raise_bot_error(exc)
    return BotResponse(bot=bot)


@router.post(
    "/bots/{bot_id}/deactivate",
    response_model=BotResponse,
    tags=["bots"],
)
def deactivate_bot(
    bot_id: UUID,
    service: Annotated[BotService, Depends(get_bot_service)],
    actor: Annotated[User, Depends(require_permission("bots.deactivate"))],
) -> BotResponse:
    try:
        bot = service.deactivate(bot_id, actor=actor)
    except ValueError as exc:
        _raise_bot_error(exc)
    return BotResponse(bot=bot)


@router.get(
    "/roles",
    response_model=RoleListResponse,
    tags=["roles"],
)
def list_roles(
    service: Annotated[AccessService, Depends(get_access_service)],
    actor: Annotated[User, Depends(require_permission("roles.read"))],
) -> RoleListResponse:
    return service.list_roles()


@router.get(
    "/permissions/me",
    response_model=EffectivePermissionsResponse,
    tags=["roles"],
)
def get_my_permissions(
    service: Annotated[AccessService, Depends(get_access_service)],
    actor: Annotated[User, Depends(get_current_user)],
) -> EffectivePermissionsResponse:
    return service.effective_permissions(actor)


@router.patch(
    "/users/{user_id}/role",
    response_model=UserResponse,
    tags=["roles"],
)
def assign_user_role(
    user_id: UUID,
    request: RoleAssignmentRequest,
    service: Annotated[UserService, Depends(get_user_service)],
    actor: Annotated[User, Depends(require_permission("roles.assign"))],
) -> UserResponse:
    try:
        user = service.assign_role(user_id, request.role, actor=actor)
    except LastOwnerProtectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except UserForbiddenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return UserResponse(user=user)


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    tags=["auth"],
)
def login(
    request: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    try:
        return service.login(email=request.email, password=request.password)
    except AuthInactiveUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user is inactive",
        ) from exc
    except AuthInvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        ) from exc


@router.get(
    "/auth/me",
    response_model=CurrentUserResponse,
    tags=["auth"],
)
def get_me(
    actor: Annotated[User, Depends(get_current_user)],
) -> CurrentUserResponse:
    return CurrentUserResponse(user=actor)


@router.post(
    "/auth/change-password",
    response_model=CurrentUserResponse,
    tags=["auth"],
)
def change_password(
    request: ChangePasswordRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
    actor: Annotated[User, Depends(get_current_user)],
) -> CurrentUserResponse:
    try:
        user = service.change_password(
            user=actor,
            current_password=request.current_password,
            new_password=request.new_password,
        )
    except AuthInvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        ) from exc
    return CurrentUserResponse(user=user)
