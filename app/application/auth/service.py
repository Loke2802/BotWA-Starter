import structlog

from app.application.users.service import (
    UserAuthenticationRequiredError,
    UserNotFoundError,
    UserService,
)
from app.domain.user.contracts import TokenResponse, User
from app.security.tokens import AccessTokenService, TokenError

logger = structlog.get_logger(__name__)


class AuthInvalidCredentialsError(ValueError):
    pass


class AuthInactiveUserError(ValueError):
    pass


class AuthInvalidTokenError(ValueError):
    pass


class AuthService:
    def __init__(
        self,
        user_service: UserService,
        token_service: AccessTokenService,
    ) -> None:
        self._user_service = user_service
        self._token_service = token_service

    def login(self, email: str, password: str) -> TokenResponse:
        model = self._user_service.find_by_email(email)
        if model is None:
            self._user_service.verify_dummy_password(password)
            logger.info("authentication_failed", reason_code="credentials")
            raise AuthInvalidCredentialsError("invalid credentials")
        password_valid = self._user_service.verify_password(
            password, model.password_hash
        )
        account_active = model.status == "active" and (
            model.role == "platform_admin"
            or self._user_service.organization_is_active(model.organization_id)
        )
        if not password_valid or not account_active:
            logger.info("authentication_failed", reason_code="credentials")
            raise AuthInvalidCredentialsError("invalid credentials")

        self._user_service.record_login(model)
        token = self._token_service.create(model.id, model.auth_version)
        return TokenResponse(
            access_token=token,
            expires_in=self._token_service.expires_seconds,
        )

    def authenticate_token(self, token: str) -> User:
        try:
            payload = self._token_service.decode(token)
        except TokenError as exc:
            raise AuthInvalidTokenError("invalid token") from exc

        model = self._user_service.get_model(payload.user_id)
        if model is None:
            raise AuthInvalidTokenError("invalid token")
        if model.status != "active":
            raise AuthInactiveUserError("user is inactive")
        if (
            model.role != "platform_admin"
            and not self._user_service.organization_is_active(model.organization_id)
        ):
            raise AuthInactiveUserError("account is unavailable")
        if model.auth_version != payload.auth_version:
            raise AuthInvalidTokenError("invalid token")
        return self._user_service._to_domain(model)

    def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
    ) -> User:
        try:
            return self._user_service.change_password(
                user_id=user.id,
                current_password=current_password,
                new_password=new_password,
                actor=user,
            )
        except (UserAuthenticationRequiredError, UserNotFoundError) as exc:
            raise AuthInvalidCredentialsError("invalid credentials") from exc
