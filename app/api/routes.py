from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import (
    get_auth_service,
    get_conversation_service,
    get_current_user,
    get_optional_current_user,
    get_organization_service,
    get_user_service,
)
from app.api.schemas import HealthResponse, VersionResponse
from app.application.auth.service import (
    AuthInactiveUserError,
    AuthInvalidCredentialsError,
    AuthService,
)
from app.application.organizations.service import (
    OrganizationConflictError,
    OrganizationNotFoundError,
    OrganizationService,
)
from app.application.users.service import (
    OrganizationInactiveError,
    UserAuthenticationRequiredError,
    UserConflictError,
    UserForbiddenError,
    UserNotFoundError,
    UserService,
)
from app.core.conversation.service import ConversationService
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
    actor: Annotated[User, Depends(get_current_user)],
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
    actor: Annotated[User, Depends(get_current_user)],
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
    actor: Annotated[User, Depends(get_current_user)],
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
    actor: Annotated[User, Depends(get_current_user)],
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
