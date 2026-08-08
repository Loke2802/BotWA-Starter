import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Literal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.integration_management.oauth_state import (
    OAuthStateExpiredError,
    OAuthStateInvalidError,
    OAuthStateSigner,
)
from app.application.integration_management.providers import (
    IntegrationProviderAuthError,
    IntegrationProviderResponseError,
    IntegrationProviderUnreachableError,
)
from app.domain.access.contracts import Permission
from app.domain.integration_management.contracts import (
    AvailabilityRequest,
    CalendarAvailability,
    CalendarMetadata,
    GoogleCalendarConfiguration,
    IntegrationConnectionCreate,
    IntegrationConnectionResponse,
    IntegrationConnectionUpdate,
    IntegrationCredentialInput,
    IntegrationCredentialResponse,
    IntegrationHealthCheckResponse,
    OAuthCallbackResponse,
    OAuthStartResponse,
)
from app.domain.user.contracts import User
from app.infrastructure.integrations.registry import (
    IntegrationProviderNotSupportedError,
    IntegrationProviderRegistry,
)
from app.infrastructure.models.integration_management import (
    IntegrationConnectionModel,
    IntegrationCredentialModel,
    IntegrationHealthCheckModel,
    IntegrationOAuthStateModel,
)
from app.infrastructure.repositories.integration_management_repository import (
    IntegrationManagementRepository,
)
from app.security.authorization import AuthorizationError, require_scoped_permission
from app.security.secret_cipher import SecretCipher, SecretCipherError


class IntegrationManagementError(ValueError):
    safe_code = "INTEGRATION_PROVIDER_ERROR"


class IntegrationNotFoundError(IntegrationManagementError):
    pass


class IntegrationForbiddenError(IntegrationManagementError):
    pass


class IntegrationConflictError(IntegrationManagementError):
    pass


class IntegrationValidationError(IntegrationManagementError):
    safe_code = "INTEGRATION_CONFIGURATION_INVALID"


class IntegrationNotActiveError(IntegrationConflictError):
    safe_code = "INTEGRATION_NOT_ACTIVE"


class IntegrationCredentialError(IntegrationManagementError):
    safe_code = "INTEGRATION_CREDENTIAL_INVALID"


class IntegrationCredentialRequiredError(IntegrationCredentialError):
    safe_code = "INTEGRATION_AUTH_REQUIRED"


class IntegrationOAuthStateError(IntegrationManagementError):
    safe_code = "OAUTH_STATE_INVALID"


class IntegrationOAuthStateExpired(IntegrationOAuthStateError):
    safe_code = "OAUTH_STATE_EXPIRED"


class IntegrationOAuthStateReplayed(IntegrationOAuthStateError):
    safe_code = "OAUTH_STATE_REPLAYED"


class IntegrationProviderOperationError(IntegrationManagementError):
    def __init__(self, safe_code: str) -> None:
        super().__init__("integration provider operation failed")
        self.safe_code = safe_code


Transition = Literal["activate", "deactivate", "archive"]


class IntegrationManagementService:
    def __init__(
        self,
        repository: IntegrationManagementRepository,
        session: Session,
        cipher: SecretCipher,
        oauth_state_signer: OAuthStateSigner,
        providers: IntegrationProviderRegistry,
    ) -> None:
        self.repository = repository
        self.session = session
        self.cipher = cipher
        self.oauth_state_signer = oauth_state_signer
        self.providers = providers

    @staticmethod
    def _authorize(actor: User, permission: Permission, organization_id: UUID) -> None:
        try:
            require_scoped_permission(actor, permission, organization_id)
        except AuthorizationError as exc:
            raise IntegrationForbiddenError("integration access denied") from exc

    def _connection(
        self, organization_id: UUID, integration_id: UUID, *, lock: bool = False
    ) -> IntegrationConnectionModel:
        row = self.repository.connection(organization_id, integration_id, lock=lock)
        if row is None:
            raise IntegrationNotFoundError("integration not found")
        return row

    def _validate_bot(self, organization_id: UUID, bot_id: UUID | None) -> None:
        if bot_id is not None and not self.repository.bot_belongs_to(
            organization_id, bot_id
        ):
            raise IntegrationValidationError("bot scope is invalid")

    def _response(
        self, row: IntegrationConnectionModel
    ) -> IntegrationConnectionResponse:
        credential = self.repository.credential(row.organization_id, row.id)
        return IntegrationConnectionResponse(
            id=row.id,
            organization_id=row.organization_id,
            bot_id=row.bot_id,
            name=row.name,
            description=row.description,
            integration_type=row.integration_type,
            provider=row.provider,
            status=row.status,
            version=row.version,
            capabilities=row.capabilities,
            configuration=GoogleCalendarConfiguration.model_validate(row.configuration),
            health_status=row.health_status,
            last_health_checked_at=row.last_health_checked_at,
            has_credentials=credential is not None,
            created_at=row.created_at,
            updated_at=row.updated_at,
            activated_at=row.activated_at,
            deactivated_at=row.deactivated_at,
            archived_at=row.archived_at,
        )

    def create(
        self,
        organization_id: UUID,
        payload: IntegrationConnectionCreate,
        actor: User,
    ) -> IntegrationConnectionResponse:
        self._authorize(actor, "integration.create", organization_id)
        self._validate_bot(organization_id, payload.bot_id)
        row = IntegrationConnectionModel(
            organization_id=organization_id,
            bot_id=payload.bot_id,
            name=payload.name,
            description=payload.description,
            integration_type=payload.integration_type,
            provider=payload.provider,
            status="draft",
            version=1,
            capabilities=list(payload.capabilities),
            configuration=payload.configuration.model_dump(mode="json"),
            health_status="unknown",
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
        )
        try:
            self.repository.add_connection(row)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise IntegrationConflictError("integration name already exists") from exc
        return self._response(row)

    def list_connections(
        self,
        organization_id: UUID,
        actor: User,
        *,
        status: str | None,
        provider: str | None,
        bot_id: UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[IntegrationConnectionResponse], int]:
        self._authorize(actor, "integration.read", organization_id)
        rows, total = self.repository.connections(
            organization_id,
            status=status,
            provider=provider,
            bot_id=bot_id,
            offset=offset,
            limit=limit,
        )
        return [self._response(row) for row in rows], total

    def get(
        self, organization_id: UUID, integration_id: UUID, actor: User
    ) -> IntegrationConnectionResponse:
        self._authorize(actor, "integration.read", organization_id)
        return self._response(self._connection(organization_id, integration_id))

    def update(
        self,
        organization_id: UUID,
        integration_id: UUID,
        payload: IntegrationConnectionUpdate,
        actor: User,
    ) -> IntegrationConnectionResponse:
        self._authorize(actor, "integration.update", organization_id)
        row = self._connection(organization_id, integration_id, lock=True)
        if row.status == "archived":
            raise IntegrationConflictError("archived integration is terminal")
        data = payload.model_dump(exclude_unset=True)
        functional_keys = {"bot_id", "capabilities", "configuration"}
        if row.status == "active" and functional_keys.intersection(data):
            raise IntegrationConflictError(
                "active integration functional changes are not allowed"
            )
        if "bot_id" in data:
            bot_value = data["bot_id"]
            if bot_value is not None and not isinstance(bot_value, UUID):
                raise IntegrationValidationError("bot scope is invalid")
            self._validate_bot(organization_id, bot_value)
            row.bot_id = bot_value
        if "name" in data and isinstance(data["name"], str):
            row.name = data["name"]
        if "description" in data:
            description = data["description"]
            if description is not None and not isinstance(description, str):
                raise IntegrationValidationError("description is invalid")
            row.description = description
        if payload.capabilities is not None:
            row.capabilities = list(payload.capabilities)
        if payload.configuration is not None:
            row.configuration = payload.configuration.model_dump(mode="json")
        if functional_keys.intersection(data):
            row.version += 1
        row.updated_by_user_id = actor.id
        row.updated_at = datetime.now(UTC)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise IntegrationConflictError("integration update conflicts") from exc
        return self._response(row)

    def activate(
        self, organization_id: UUID, integration_id: UUID, actor: User
    ) -> IntegrationConnectionResponse:
        return self._transition(
            organization_id,
            integration_id,
            actor,
            transition="activate",
            permission="integration.activate",
        )

    def deactivate(
        self, organization_id: UUID, integration_id: UUID, actor: User
    ) -> IntegrationConnectionResponse:
        return self._transition(
            organization_id,
            integration_id,
            actor,
            transition="deactivate",
            permission="integration.deactivate",
        )

    def archive(
        self, organization_id: UUID, integration_id: UUID, actor: User
    ) -> IntegrationConnectionResponse:
        return self._transition(
            organization_id,
            integration_id,
            actor,
            transition="archive",
            permission="integration.archive",
        )

    def _transition(
        self,
        organization_id: UUID,
        integration_id: UUID,
        actor: User,
        *,
        transition: Transition,
        permission: Permission,
    ) -> IntegrationConnectionResponse:
        self._authorize(actor, permission, organization_id)
        row = self._connection(organization_id, integration_id, lock=True)
        target = {
            "activate": "active",
            "deactivate": "inactive",
            "archive": "archived",
        }[transition]
        allowed = {
            "active": {"draft", "inactive"},
            "inactive": {"active"},
            "archived": {"draft", "active", "inactive"},
        }
        if row.status not in allowed[target]:
            raise IntegrationConflictError("invalid integration lifecycle transition")
        now = datetime.now(UTC)
        if target == "active":
            GoogleCalendarConfiguration.model_validate(row.configuration)
            if self.repository.credential(organization_id, integration_id) is None:
                raise IntegrationCredentialRequiredError(
                    "integration credentials are required"
                )
            row.activated_at = now
        elif target == "inactive":
            row.deactivated_at = now
        else:
            row.archived_at = now
        row.status = target
        row.updated_by_user_id = actor.id
        row.updated_at = now
        self.session.commit()
        return self._response(row)

    def update_credentials(
        self,
        organization_id: UUID,
        integration_id: UUID,
        payload: IntegrationCredentialInput,
        actor: User,
    ) -> IntegrationCredentialResponse:
        self._authorize(actor, "integration.credentials.update", organization_id)
        row = self._connection(organization_id, integration_id, lock=True)
        if row.status == "archived":
            raise IntegrationConflictError("archived integration is terminal")
        refresh_token = payload.refresh_token.get_secret_value()
        credential = self._store_refresh_token(row, refresh_token)
        self.session.commit()
        return IntegrationCredentialResponse(
            integration_id=row.id,
            credential_type=credential.credential_type,
            configured=True,
            rotated_at=credential.rotated_at,
        )

    def _store_refresh_token(
        self, row: IntegrationConnectionModel, refresh_token: str
    ) -> IntegrationCredentialModel:
        encrypted = self.cipher.encrypt(
            json.dumps({"refresh_token": refresh_token}, separators=(",", ":"))
        )
        now = datetime.now(UTC)
        credential = self.repository.credential(row.organization_id, row.id, lock=True)
        if credential is None:
            credential = IntegrationCredentialModel(
                organization_id=row.organization_id,
                integration_connection_id=row.id,
                credential_type="google_oauth_refresh",
                encrypted_payload=encrypted,
                key_version="v1",
                rotated_at=now,
            )
            self.session.add(credential)
        else:
            credential.credential_type = "google_oauth_refresh"
            credential.encrypted_payload = encrypted
            credential.key_version = "v1"
            credential.rotated_at = now
            credential.updated_at = now
        return credential

    def _refresh_token(self, row: IntegrationConnectionModel) -> str:
        credential = self.repository.credential(row.organization_id, row.id)
        if credential is None:
            raise IntegrationCredentialRequiredError(
                "integration credentials are required"
            )
        try:
            plaintext = self.cipher.decrypt(credential.encrypted_payload)
            payload = json.loads(plaintext)
        except (SecretCipherError, json.JSONDecodeError) as exc:
            raise IntegrationCredentialError(
                "integration credential is invalid"
            ) from exc
        if not isinstance(payload, dict):
            raise IntegrationCredentialError("integration credential is invalid")
        refresh_token = payload.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise IntegrationCredentialError("integration credential is invalid")
        return refresh_token

    def start_google_oauth(
        self, organization_id: UUID, integration_id: UUID, actor: User
    ) -> OAuthStartResponse:
        self._authorize(actor, "integration.credentials.update", organization_id)
        row = self._connection(organization_id, integration_id)
        if row.status == "archived" or row.provider != "google_calendar":
            raise IntegrationConflictError("google oauth is not available")
        token, claims = self.oauth_state_signer.issue(
            organization_id=organization_id,
            integration_id=integration_id,
            provider=row.provider,
        )
        try:
            adapter = self.providers.calendar(row.provider)
            authorization_url = adapter.build_authorization_url(token)
        except (
            IntegrationProviderNotSupportedError,
            IntegrationProviderResponseError,
        ) as exc:
            raise IntegrationValidationError("google oauth is not configured") from exc
        self.session.add(
            IntegrationOAuthStateModel(
                organization_id=organization_id,
                integration_connection_id=integration_id,
                provider=row.provider,
                nonce_hash=claims.nonce_hash,
                expires_at=claims.expires_at,
            )
        )
        self.session.commit()
        return OAuthStartResponse(
            authorization_url=authorization_url, expires_at=claims.expires_at
        )

    def complete_google_oauth(self, state: str, code: str) -> OAuthCallbackResponse:
        try:
            claims = self.oauth_state_signer.decode(state)
        except OAuthStateExpiredError as exc:
            raise IntegrationOAuthStateExpired("oauth state expired") from exc
        except OAuthStateInvalidError as exc:
            raise IntegrationOAuthStateError("oauth state invalid") from exc
        stored_state = self.repository.oauth_state_by_nonce(
            claims.nonce_hash, lock=True
        )
        now = datetime.now(UTC)
        if stored_state is None:
            raise IntegrationOAuthStateError("oauth state invalid")
        if stored_state.consumed_at is not None:
            raise IntegrationOAuthStateReplayed("oauth state replayed")
        state_expires_at = stored_state.expires_at
        if state_expires_at.tzinfo is None:
            state_expires_at = state_expires_at.replace(tzinfo=UTC)
        if state_expires_at < now:
            raise IntegrationOAuthStateExpired("oauth state expired")
        if (
            stored_state.organization_id != claims.organization_id
            or stored_state.integration_connection_id != claims.integration_id
            or stored_state.provider != claims.provider
        ):
            raise IntegrationOAuthStateError("oauth state invalid")
        row = self._connection(claims.organization_id, claims.integration_id, lock=True)
        if row.provider != claims.provider or row.status == "archived":
            raise IntegrationOAuthStateError("oauth state invalid")
        stored_state.consumed_at = now
        self.session.commit()
        try:
            adapter = self.providers.calendar(row.provider)
            tokens = adapter.exchange_authorization_code(code)
        except IntegrationProviderAuthError as exc:
            raise IntegrationProviderOperationError("INTEGRATION_AUTH_FAILED") from exc
        except IntegrationProviderUnreachableError as exc:
            raise IntegrationProviderOperationError("INTEGRATION_UNREACHABLE") from exc
        except (
            IntegrationProviderNotSupportedError,
            IntegrationProviderResponseError,
        ) as exc:
            raise IntegrationProviderOperationError(
                "INTEGRATION_PROVIDER_ERROR"
            ) from exc
        if tokens.refresh_token is not None:
            self._store_refresh_token(row, tokens.refresh_token)
        elif self.repository.credential(row.organization_id, row.id) is None:
            raise IntegrationCredentialError("google did not return a refresh token")
        self._record_oauth_health(row, adapter, tokens.access_token)
        self.session.commit()
        return OAuthCallbackResponse()

    def _record_oauth_health(
        self, row: IntegrationConnectionModel, adapter: object, access_token: str
    ) -> None:
        start = perf_counter()
        status = "healthy"
        safe_error: str | None = None
        try:
            if not hasattr(adapter, "get_health_with_access_token"):
                raise IntegrationProviderResponseError("provider contract invalid")
            adapter.get_health_with_access_token(access_token)
        except IntegrationProviderAuthError:
            status, safe_error = "auth_error", "INTEGRATION_AUTH_FAILED"
        except IntegrationProviderUnreachableError:
            status, safe_error = "unreachable", "INTEGRATION_UNREACHABLE"
        except IntegrationProviderResponseError:
            status, safe_error = "degraded", "INTEGRATION_PROVIDER_ERROR"
        self._persist_health(row, status, safe_error, start)

    def check_health(
        self, organization_id: UUID, integration_id: UUID, actor: User
    ) -> IntegrationHealthCheckResponse:
        self._authorize(actor, "integration.health.check", organization_id)
        row = self._connection(organization_id, integration_id, lock=True)
        if row.status != "active":
            raise IntegrationNotActiveError("integration is not active")
        start = perf_counter()
        try:
            refresh_token = self._refresh_token(row)
            adapter = self.providers.calendar(row.provider)
            adapter.get_health(refresh_token)
            status, safe_error = "healthy", None
        except IntegrationCredentialRequiredError:
            status, safe_error = "auth_error", "INTEGRATION_AUTH_REQUIRED"
        except IntegrationCredentialError:
            status, safe_error = "auth_error", "INTEGRATION_CREDENTIAL_INVALID"
        except IntegrationProviderAuthError:
            status, safe_error = "auth_error", "INTEGRATION_AUTH_FAILED"
        except IntegrationProviderUnreachableError:
            status, safe_error = "unreachable", "INTEGRATION_UNREACHABLE"
        except (
            IntegrationProviderNotSupportedError,
            IntegrationProviderResponseError,
        ):
            status, safe_error = "degraded", "INTEGRATION_PROVIDER_ERROR"
        health = self._persist_health(row, status, safe_error, start)
        self.session.commit()
        return IntegrationHealthCheckResponse.model_validate(health)

    def _persist_health(
        self,
        row: IntegrationConnectionModel,
        status: str,
        safe_error_code: str | None,
        started: float,
    ) -> IntegrationHealthCheckModel:
        checked_at = datetime.now(UTC)
        health = IntegrationHealthCheckModel(
            organization_id=row.organization_id,
            integration_connection_id=row.id,
            status=status,
            safe_error_code=safe_error_code,
            checked_at=checked_at,
            latency_ms=max(0, int((perf_counter() - started) * 1000)),
        )
        self.session.add(health)
        row.health_status = status
        row.last_health_checked_at = checked_at
        return health

    def health_history(
        self,
        organization_id: UUID,
        integration_id: UUID,
        actor: User,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[IntegrationHealthCheckResponse], int]:
        self._authorize(actor, "integration.health.read", organization_id)
        self._connection(organization_id, integration_id)
        rows, total = self.repository.health_checks(
            organization_id, integration_id, offset=offset, limit=limit
        )
        return [
            IntegrationHealthCheckResponse.model_validate(row) for row in rows
        ], total

    def list_calendars(
        self, organization_id: UUID, integration_id: UUID, actor: User
    ) -> list[CalendarMetadata]:
        self._authorize(actor, "integration.read", organization_id)
        row = self._active_connection(organization_id, integration_id)
        return self.providers.calendar(row.provider).list_calendars(
            self._refresh_token(row)
        )

    def get_availability(
        self,
        organization_id: UUID,
        integration_id: UUID,
        request: AvailabilityRequest,
        actor: User,
    ) -> list[CalendarAvailability]:
        self._authorize(actor, "integration.read", organization_id)
        row = self._active_connection(organization_id, integration_id)
        return self.providers.calendar(row.provider).get_availability(
            self._refresh_token(row), request
        )

    def _active_connection(
        self, organization_id: UUID, integration_id: UUID
    ) -> IntegrationConnectionModel:
        row = self._connection(organization_id, integration_id)
        if row.status != "active":
            raise IntegrationNotActiveError("integration is not active")
        return row
