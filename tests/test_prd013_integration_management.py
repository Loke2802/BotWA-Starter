import base64
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from app.application.integration_management.oauth_state import OAuthStateSigner
from app.application.integration_management.providers import (
    IntegrationProviderAuthError,
    IntegrationProviderResponseError,
    IntegrationProviderUnreachableError,
    OAuthTokenResult,
)
from app.application.integration_management.service import (
    IntegrationConflictError,
    IntegrationCredentialError,
    IntegrationCredentialRequiredError,
    IntegrationForbiddenError,
    IntegrationManagementService,
    IntegrationNotFoundError,
    IntegrationOAuthStateError,
    IntegrationOAuthStateExpired,
    IntegrationOAuthStateReplayed,
    IntegrationProviderOperationError,
    IntegrationValidationError,
)
from app.domain.access.contracts import ROLE_PERMISSIONS
from app.domain.integration_management.contracts import (
    AvailabilityRequest,
    CalendarAvailability,
    CalendarMetadata,
    IntegrationConnectionCreate,
    IntegrationConnectionUpdate,
    IntegrationCredentialInput,
)
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.integrations.registry import IntegrationProviderRegistry
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.integration_management import (
    IntegrationCredentialModel,
    IntegrationHealthCheckModel,
    IntegrationOAuthStateModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.integration_management_repository import (
    IntegrationManagementRepository,
)
from app.security.secret_cipher import EnvironmentSecretCipher
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.plan_support import allow_all_plan_enforcement


def _key(seed: bytes = b"i") -> str:
    return base64.urlsafe_b64encode(seed * 32).decode("ascii")


class FakeGoogleCalendarAdapter:
    provider = "google_calendar"

    def __init__(self) -> None:
        self.health_failure: str | None = None
        self.exchanged_code: str | None = None
        self.exchange_failure: str | None = None
        self.oauth_refresh_token: str | None = "provider-refresh-token"
        self.health_rotated_refresh_token: str | None = None

    def build_authorization_url(self, state: str) -> str:
        return f"https://accounts.example/authorize?state={state}"

    def exchange_authorization_code(self, code: str) -> OAuthTokenResult:
        self.exchanged_code = code
        if self.exchange_failure == "auth":
            raise IntegrationProviderAuthError("auth")
        if self.exchange_failure == "unreachable":
            raise IntegrationProviderUnreachableError("unreachable")
        if self.exchange_failure == "provider":
            raise IntegrationProviderResponseError("provider")
        return OAuthTokenResult("ephemeral-access", self.oauth_refresh_token)

    def _health(self) -> None:
        if self.health_failure == "auth":
            raise IntegrationProviderAuthError("auth")
        if self.health_failure == "unreachable":
            raise IntegrationProviderUnreachableError("unreachable")
        if self.health_failure == "provider":
            raise IntegrationProviderResponseError("provider")

    def get_health(self, refresh_token: str) -> str | None:
        assert refresh_token
        self._health()
        return self.health_rotated_refresh_token

    def get_health_with_access_token(self, access_token: str) -> None:
        assert access_token == "ephemeral-access"
        self._health()

    def list_calendars(self, refresh_token: str) -> list[CalendarMetadata]:
        assert refresh_token
        return [
            CalendarMetadata(
                calendar_id="primary",
                display_name="Primary",
                timezone="America/Lima",
                primary=True,
                access_role="owner",
            )
        ]

    def get_calendar_metadata(
        self, refresh_token: str, calendar_id: str
    ) -> CalendarMetadata:
        return self.list_calendars(refresh_token)[0]

    def get_availability(
        self, refresh_token: str, request: AvailabilityRequest
    ) -> list[CalendarAvailability]:
        assert refresh_token
        return [CalendarAvailability(start=request.start, end=request.end, busy=[])]


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _actor(organization_id: UUID, role: str = "organization_owner") -> User:
    return User(
        id=uuid4(),
        organization_id=organization_id,
        email=f"{uuid4()}@example.com",
        role=role,
    )


def _setup(
    session: Session,
) -> tuple[IntegrationManagementService, FakeGoogleCalendarAdapter, User, UUID, UUID]:
    organization_id, bot_id = uuid4(), uuid4()
    actor = _actor(organization_id)
    session.add_all(
        (
            OrganizationModel(
                id=organization_id,
                name="Kalivur",
                slug=str(organization_id)[:12],
                status="active",
            ),
            BotModel(
                id=bot_id,
                organization_id=organization_id,
                name="Luri",
                slug="luri",
                status="active",
            ),
            UserModel(
                id=actor.id,
                organization_id=organization_id,
                email=actor.email,
                password_hash="x",
                role=actor.role,
                status="active",
            ),
        )
    )
    session.commit()
    adapter = FakeGoogleCalendarAdapter()
    service = IntegrationManagementService(
        IntegrationManagementRepository(session),
        session,
        EnvironmentSecretCipher(_key()),
        OAuthStateSigner(secret_key="s" * 32),
        IntegrationProviderRegistry((adapter,)),
        SqlAlchemyAuditRepository(session),
        allow_all_plan_enforcement(),
    )
    return service, adapter, actor, organization_id, bot_id


def _payload(bot_id: UUID | None = None) -> IntegrationConnectionCreate:
    return IntegrationConnectionCreate(
        name="Main calendar",
        bot_id=bot_id,
        integration_type="calendar",
        provider="google_calendar",
        capabilities=[
            "calendar.metadata.read",
            "calendar.availability.read",
        ],
        configuration={"timezone": "America/Lima", "read_only": True},
    )


def _created(
    service: IntegrationManagementService,
    actor: User,
    organization_id: UUID,
    bot_id: UUID | None = None,
) -> UUID:
    return service.create(organization_id, _payload(bot_id), actor).id


def test_contract_rejects_wrong_type_extra_configuration_and_duplicate_capability() -> (
    None
):
    with pytest.raises(ValidationError):
        IntegrationConnectionCreate(
            name="CRM",
            integration_type="crm",
            provider="google_calendar",
            capabilities=["calendar.metadata.read"],
            configuration={},
        )
    with pytest.raises(ValidationError):
        IntegrationConnectionCreate(
            name="Unsafe",
            integration_type="calendar",
            provider="google_calendar",
            capabilities=["calendar.metadata.read"],
            configuration={"client_secret": "not-allowed"},
        )
    with pytest.raises(ValidationError):
        IntegrationConnectionCreate(
            name="Duplicate",
            integration_type="calendar",
            provider="google_calendar",
            capabilities=["calendar.metadata.read", "calendar.metadata.read"],
            configuration={},
        )


def test_rbac_assigns_prd013_permissions_without_viewer_access() -> None:
    expected = {
        "integration.read",
        "integration.create",
        "integration.update",
        "integration.activate",
        "integration.deactivate",
        "integration.archive",
        "integration.credentials.update",
        "integration.health.read",
        "integration.health.check",
    }
    assert expected.issubset(ROLE_PERMISSIONS["organization_owner"])
    assert expected.issubset(ROLE_PERMISSIONS["organization_admin"])
    assert {
        "integration.read",
        "integration.health.read",
        "integration.health.check",
    }.issubset(ROLE_PERMISSIONS["operator"])
    assert not expected.intersection(ROLE_PERMISSIONS["viewer"])


def test_create_list_bot_scope_and_cross_tenant_are_safe(session: Session) -> None:
    service, _adapter, actor, organization_id, bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id, bot_id)
    items, total = service.list_connections(
        organization_id,
        actor,
        status="draft",
        provider="google_calendar",
        bot_id=bot_id,
        offset=0,
        limit=20,
    )
    assert total == 1
    assert items[0].id == integration_id
    assert items[0].has_credentials is False

    foreign_org = uuid4()
    with pytest.raises(IntegrationForbiddenError):
        service.get(foreign_org, integration_id, actor)
    foreign_actor = _actor(foreign_org)
    with pytest.raises(IntegrationNotFoundError):
        service.get(foreign_org, integration_id, foreign_actor)
    with pytest.raises(IntegrationValidationError):
        service.create(organization_id, _payload(uuid4()), actor)


def test_credentials_are_encrypted_rotatable_and_never_returned(
    session: Session,
) -> None:
    service, _adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    first = service.update_credentials(
        organization_id,
        integration_id,
        IntegrationCredentialInput(refresh_token="first-refresh-token"),
        actor,
    )
    credential = session.scalars(select(IntegrationCredentialModel)).one()
    assert "first-refresh-token" not in credential.encrypted_payload
    assert first.configured is True
    assert not hasattr(first, "refresh_token")

    service.update_credentials(
        organization_id,
        integration_id,
        IntegrationCredentialInput(refresh_token="second-refresh-token"),
        actor,
    )
    assert session.scalars(select(IntegrationCredentialModel)).one().id == credential.id
    assert service._refresh_token(
        service._connection(organization_id, integration_id)
    ) == ("second-refresh-token")


def test_credential_rotation_is_tenant_scoped(session: Session) -> None:
    service, _adapter, actor, organization_id, _bot_id = _setup(session)
    local_integration_id = _created(service, actor, organization_id)
    service.update_credentials(
        organization_id,
        local_integration_id,
        IntegrationCredentialInput(refresh_token="local-original"),
        actor,
    )

    foreign_organization_id = uuid4()
    foreign_actor = _actor(foreign_organization_id)
    session.add_all(
        (
            OrganizationModel(
                id=foreign_organization_id,
                name="Foreign",
                slug=str(foreign_organization_id)[:12],
                status="active",
            ),
            UserModel(
                id=foreign_actor.id,
                organization_id=foreign_organization_id,
                email=foreign_actor.email,
                password_hash="x",
                role=foreign_actor.role,
                status="active",
            ),
        )
    )
    session.commit()
    foreign_integration_id = _created(service, foreign_actor, foreign_organization_id)
    service.update_credentials(
        foreign_organization_id,
        foreign_integration_id,
        IntegrationCredentialInput(refresh_token="foreign-original"),
        foreign_actor,
    )
    foreign_credential = service.repository.credential(
        foreign_organization_id, foreign_integration_id
    )
    assert foreign_credential is not None
    foreign_encrypted_payload = foreign_credential.encrypted_payload

    service.update_credentials(
        organization_id,
        local_integration_id,
        IntegrationCredentialInput(refresh_token="local-rotated"),
        actor,
    )
    assert service._refresh_token(
        service._connection(organization_id, local_integration_id)
    ) == ("local-rotated")
    unchanged_foreign_credential = service.repository.credential(
        foreign_organization_id, foreign_integration_id
    )
    assert unchanged_foreign_credential is not None
    assert unchanged_foreign_credential.encrypted_payload == foreign_encrypted_payload

    with pytest.raises(IntegrationNotFoundError):
        service.update_credentials(
            foreign_organization_id,
            local_integration_id,
            IntegrationCredentialInput(refresh_token="cross-tenant"),
            foreign_actor,
        )

    service.archive(organization_id, local_integration_id, actor)
    with pytest.raises(IntegrationConflictError):
        service.update_credentials(
            organization_id,
            local_integration_id,
            IntegrationCredentialInput(refresh_token="archived-rotation"),
            actor,
        )


def test_credential_rotation_db_failure_rolls_back_existing_secret(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    service.update_credentials(
        organization_id,
        integration_id,
        IntegrationCredentialInput(refresh_token="original-refresh"),
        actor,
    )
    original = service.repository.credential(organization_id, integration_id)
    assert original is not None
    original_encrypted_payload = original.encrypted_payload
    real_rollback = session.rollback
    rollback_calls = 0

    def fail_commit() -> None:
        raise SQLAlchemyError("forced commit failure")

    def track_rollback() -> None:
        nonlocal rollback_calls
        rollback_calls += 1
        real_rollback()

    monkeypatch.setattr(session, "commit", fail_commit)
    monkeypatch.setattr(session, "rollback", track_rollback)

    with pytest.raises(IntegrationProviderOperationError) as error:
        service.update_credentials(
            organization_id,
            integration_id,
            IntegrationCredentialInput(refresh_token="replacement-refresh"),
            actor,
        )

    assert error.value.safe_code == "INTEGRATION_PROVIDER_ERROR"
    assert rollback_calls == 1
    credential = service.repository.credential(organization_id, integration_id)
    assert credential is not None
    assert credential.encrypted_payload == original_encrypted_payload


def test_lifecycle_versioning_and_archive_terminal(session: Session) -> None:
    service, _adapter, actor, organization_id, bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    with pytest.raises(IntegrationCredentialError):
        service.activate(organization_id, integration_id, actor)
    service.update_credentials(
        organization_id,
        integration_id,
        IntegrationCredentialInput(refresh_token="refresh"),
        actor,
    )
    updated = service.update(
        organization_id,
        integration_id,
        IntegrationConnectionUpdate(bot_id=bot_id),
        actor,
    )
    assert updated.version == 2
    active = service.activate(organization_id, integration_id, actor)
    assert active.status == "active"
    renamed = service.update(
        organization_id,
        integration_id,
        IntegrationConnectionUpdate(name="Renamed"),
        actor,
    )
    assert renamed.name == "Renamed"
    with pytest.raises(IntegrationConflictError):
        service.update(
            organization_id,
            integration_id,
            IntegrationConnectionUpdate(configuration={"calendar_id": "primary"}),
            actor,
        )
    assert (
        service.deactivate(organization_id, integration_id, actor).status == "inactive"
    )
    assert service.archive(organization_id, integration_id, actor).status == "archived"
    with pytest.raises(IntegrationConflictError):
        service.activate(organization_id, integration_id, actor)


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_code"),
    [
        (None, "healthy", None),
        ("auth", "auth_error", "INTEGRATION_AUTH_FAILED"),
        ("unreachable", "unreachable", "INTEGRATION_UNREACHABLE"),
        ("provider", "degraded", "INTEGRATION_PROVIDER_ERROR"),
    ],
)
def test_on_demand_health_maps_safe_history(
    session: Session,
    failure: str | None,
    expected_status: str,
    expected_code: str | None,
) -> None:
    service, adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    service.update_credentials(
        organization_id,
        integration_id,
        IntegrationCredentialInput(refresh_token="refresh"),
        actor,
    )
    service.activate(organization_id, integration_id, actor)
    adapter.health_failure = failure
    operator = _actor(organization_id, "operator")
    result = service.check_health(organization_id, integration_id, operator)
    assert result.status == expected_status
    assert result.safe_error_code == expected_code
    history, total = service.health_history(
        organization_id,
        integration_id,
        operator,
        offset=0,
        limit=10,
    )
    assert total == 1
    assert history[0].safe_error_code == expected_code
    viewer = _actor(organization_id, "viewer")
    with pytest.raises(IntegrationForbiddenError):
        service.health_history(
            organization_id, integration_id, viewer, offset=0, limit=10
        )


def test_health_persists_rotated_refresh_token_atomically(session: Session) -> None:
    service, adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    service.update_credentials(
        organization_id,
        integration_id,
        IntegrationCredentialInput(refresh_token="original-refresh"),
        actor,
    )
    service.activate(organization_id, integration_id, actor)
    adapter.health_rotated_refresh_token = "rotated-refresh"

    result = service.check_health(organization_id, integration_id, actor)

    assert result.status == "healthy"
    assert service._refresh_token(
        service._connection(organization_id, integration_id)
    ) == ("rotated-refresh")
    credential = service.repository.credential(organization_id, integration_id)
    assert credential is not None
    assert "rotated-refresh" not in credential.encrypted_payload


def test_health_failure_does_not_destroy_valid_credential(session: Session) -> None:
    service, adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    service.update_credentials(
        organization_id,
        integration_id,
        IntegrationCredentialInput(refresh_token="stable-refresh"),
        actor,
    )
    service.activate(organization_id, integration_id, actor)
    original = service.repository.credential(organization_id, integration_id)
    assert original is not None
    original_encrypted_payload = original.encrypted_payload
    adapter.health_failure = "unreachable"

    result = service.check_health(organization_id, integration_id, actor)

    assert result.status == "unreachable"
    credential = service.repository.credential(organization_id, integration_id)
    assert credential is not None
    assert credential.encrypted_payload == original_encrypted_payload
    assert service._refresh_token(
        service._connection(organization_id, integration_id)
    ) == ("stable-refresh")


def test_health_db_failure_rolls_back_credential_and_history(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    service.update_credentials(
        organization_id,
        integration_id,
        IntegrationCredentialInput(refresh_token="original-refresh"),
        actor,
    )
    service.activate(organization_id, integration_id, actor)
    original_credential = service.repository.credential(organization_id, integration_id)
    assert original_credential is not None
    original_encrypted_payload = original_credential.encrypted_payload
    adapter.health_rotated_refresh_token = "rotated-refresh"
    real_rollback = session.rollback
    rollback_calls = 0

    def fail_commit() -> None:
        raise SQLAlchemyError("forced commit failure")

    def track_rollback() -> None:
        nonlocal rollback_calls
        rollback_calls += 1
        real_rollback()

    monkeypatch.setattr(session, "commit", fail_commit)
    monkeypatch.setattr(session, "rollback", track_rollback)

    with pytest.raises(IntegrationProviderOperationError) as error:
        service.check_health(organization_id, integration_id, actor)

    assert error.value.safe_code == "INTEGRATION_PROVIDER_ERROR"
    assert rollback_calls == 1
    credential = service.repository.credential(organization_id, integration_id)
    assert credential is not None
    assert credential.encrypted_payload == original_encrypted_payload
    assert session.scalars(select(IntegrationHealthCheckModel)).all() == []


def test_oauth_start_callback_encrypts_refresh_and_rejects_replay(
    session: Session,
) -> None:
    service, adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    start = service.start_google_oauth(organization_id, integration_id, actor)
    state = start.authorization_url.split("state=", maxsplit=1)[1]
    result = service.complete_google_oauth(state, "one-time-code")
    assert result.status == "connected"
    assert adapter.exchanged_code == "one-time-code"
    credential = session.scalars(select(IntegrationCredentialModel)).one()
    assert "provider-refresh-token" not in credential.encrypted_payload
    assert "one-time-code" not in credential.encrypted_payload
    assert "ephemeral-access" not in credential.encrypted_payload
    with pytest.raises(IntegrationOAuthStateReplayed):
        service.complete_google_oauth(state, "second-code")


def test_oauth_replaces_refresh_token_when_new_one_is_returned(
    session: Session,
) -> None:
    service, adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    service.update_credentials(
        organization_id,
        integration_id,
        IntegrationCredentialInput(refresh_token="existing-refresh"),
        actor,
    )
    original = service.repository.credential(organization_id, integration_id)
    assert original is not None
    original_id = original.id
    original_encrypted_payload = original.encrypted_payload
    adapter.oauth_refresh_token = "provider-replacement-refresh"
    start = service.start_google_oauth(organization_id, integration_id, actor)
    state = start.authorization_url.split("state=", maxsplit=1)[1]

    service.complete_google_oauth(state, "authorization-code")

    credential = service.repository.credential(organization_id, integration_id)
    assert credential is not None
    assert credential.id == original_id
    assert credential.encrypted_payload != original_encrypted_payload
    assert "provider-replacement-refresh" not in credential.encrypted_payload
    assert service._refresh_token(
        service._connection(organization_id, integration_id)
    ) == ("provider-replacement-refresh")


@pytest.mark.parametrize("new_refresh_token", [None, ""])
def test_oauth_preserves_existing_refresh_token_when_google_omits_new_one(
    session: Session, new_refresh_token: str | None
) -> None:
    service, adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    service.update_credentials(
        organization_id,
        integration_id,
        IntegrationCredentialInput(refresh_token="existing-refresh"),
        actor,
    )
    original = service.repository.credential(organization_id, integration_id)
    assert original is not None
    original_id = original.id
    original_encrypted_payload = original.encrypted_payload
    original_rotated_at = original.rotated_at
    adapter.oauth_refresh_token = new_refresh_token
    start = service.start_google_oauth(organization_id, integration_id, actor)
    state = start.authorization_url.split("state=", maxsplit=1)[1]

    service.complete_google_oauth(state, "authorization-code")

    credential = service.repository.credential(organization_id, integration_id)
    assert credential is not None
    assert credential.id == original_id
    assert credential.encrypted_payload == original_encrypted_payload
    assert credential.rotated_at == original_rotated_at


def test_oauth_without_refresh_token_and_without_existing_credential_fails_safely(
    session: Session,
) -> None:
    service, adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    adapter.oauth_refresh_token = None
    start = service.start_google_oauth(organization_id, integration_id, actor)
    state = start.authorization_url.split("state=", maxsplit=1)[1]

    with pytest.raises(IntegrationCredentialRequiredError) as error:
        service.complete_google_oauth(state, "authorization-code")

    assert error.value.safe_code == "INTEGRATION_AUTH_REQUIRED"
    assert session.scalars(select(IntegrationCredentialModel)).all() == []
    assert session.scalars(select(IntegrationHealthCheckModel)).all() == []
    stored_state = session.scalars(select(IntegrationOAuthStateModel)).one()
    assert stored_state.consumed_at is not None


def test_consumed_state_cannot_replay_after_provider_exchange_failure(
    session: Session,
) -> None:
    service, adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    adapter.exchange_failure = "unreachable"
    start = service.start_google_oauth(organization_id, integration_id, actor)
    state = start.authorization_url.split("state=", maxsplit=1)[1]

    with pytest.raises(IntegrationProviderOperationError) as error:
        service.complete_google_oauth(state, "authorization-code")
    assert error.value.safe_code == "INTEGRATION_UNREACHABLE"

    adapter.exchange_failure = None
    with pytest.raises(IntegrationOAuthStateReplayed):
        service.complete_google_oauth(state, "replay-code")


def test_failed_oauth_exchange_does_not_persist_partial_credential(
    session: Session,
) -> None:
    service, adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    adapter.exchange_failure = "provider"
    start = service.start_google_oauth(organization_id, integration_id, actor)
    state = start.authorization_url.split("state=", maxsplit=1)[1]

    with pytest.raises(IntegrationProviderOperationError):
        service.complete_google_oauth(state, "sensitive-authorization-code")

    assert session.scalars(select(IntegrationCredentialModel)).all() == []
    assert session.scalars(select(IntegrationHealthCheckModel)).all() == []
    stored_state = session.scalars(select(IntegrationOAuthStateModel)).one()
    assert stored_state.consumed_at is not None
    assert "sensitive-authorization-code" not in stored_state.nonce_hash


def test_oauth_db_failure_after_exchange_rolls_back_partial_credential(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    service.update_credentials(
        organization_id,
        integration_id,
        IntegrationCredentialInput(refresh_token="existing-refresh"),
        actor,
    )
    original = service.repository.credential(organization_id, integration_id)
    assert original is not None
    original_encrypted_payload = original.encrypted_payload
    start = service.start_google_oauth(organization_id, integration_id, actor)
    state = start.authorization_url.split("state=", maxsplit=1)[1]
    adapter.oauth_refresh_token = "replacement-refresh"
    real_commit = session.commit
    real_rollback = session.rollback
    commit_calls = 0
    rollback_calls = 0

    def fail_final_commit() -> None:
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 2:
            raise SQLAlchemyError("forced commit failure")
        real_commit()

    def track_rollback() -> None:
        nonlocal rollback_calls
        rollback_calls += 1
        real_rollback()

    monkeypatch.setattr(session, "commit", fail_final_commit)
    monkeypatch.setattr(session, "rollback", track_rollback)

    with pytest.raises(IntegrationProviderOperationError) as error:
        service.complete_google_oauth(state, "authorization-code")

    assert error.value.safe_code == "INTEGRATION_PROVIDER_ERROR"
    assert rollback_calls == 1
    credential = service.repository.credential(organization_id, integration_id)
    assert credential is not None
    assert credential.encrypted_payload == original_encrypted_payload
    assert session.scalars(select(IntegrationHealthCheckModel)).all() == []
    stored_state = session.scalars(select(IntegrationOAuthStateModel)).one()
    assert stored_state.consumed_at is not None


def test_oauth_rejects_tampering_expiration_and_scope_mismatch(
    session: Session,
) -> None:
    service, _adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    start = service.start_google_oauth(organization_id, integration_id, actor)
    state = start.authorization_url.split("state=", maxsplit=1)[1]
    with pytest.raises(IntegrationOAuthStateError):
        service.complete_google_oauth(f"{state}tampered", "code")

    expired = jwt.encode(
        {
            "org": str(organization_id),
            "integration": str(integration_id),
            "provider": "google_calendar",
            "nonce": "expired-nonce",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        "s" * 32,
        algorithm="HS256",
    )
    with pytest.raises(IntegrationOAuthStateExpired):
        service.complete_google_oauth(expired, "code")

    for claim_organization_id, claim_integration_id, claim_provider in (
        (uuid4(), integration_id, "google_calendar"),
        (organization_id, uuid4(), "google_calendar"),
        (organization_id, integration_id, "wrong_provider"),
    ):
        wrong_state, claims = service.oauth_state_signer.issue(
            organization_id=claim_organization_id,
            integration_id=claim_integration_id,
            provider=claim_provider,
        )
        session.add(
            IntegrationOAuthStateModel(
                organization_id=organization_id,
                integration_connection_id=integration_id,
                provider="google_calendar",
                nonce_hash=claims.nonce_hash,
                expires_at=claims.expires_at,
            )
        )
        session.commit()
        with pytest.raises(IntegrationOAuthStateError):
            service.complete_google_oauth(wrong_state, "code")


def test_runtime_calendar_capabilities_use_active_tenant_connection(
    session: Session,
) -> None:
    service, _adapter, actor, organization_id, _bot_id = _setup(session)
    integration_id = _created(service, actor, organization_id)
    service.update_credentials(
        organization_id,
        integration_id,
        IntegrationCredentialInput(refresh_token="refresh"),
        actor,
    )
    service.activate(organization_id, integration_id, actor)
    calendars = service.list_calendars(organization_id, integration_id, actor)
    availability = service.get_availability(
        organization_id,
        integration_id,
        AvailabilityRequest(
            calendar_ids=["primary"],
            start=datetime.now(UTC),
            end=datetime.now(UTC) + timedelta(hours=1),
        ),
        actor,
    )
    assert calendars[0].calendar_id == "primary"
    assert availability[0].busy == []
