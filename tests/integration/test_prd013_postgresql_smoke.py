import base64
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.application.integration_management.oauth_state import OAuthStateSigner
from app.application.integration_management.service import (
    IntegrationManagementService,
    IntegrationNotFoundError,
    IntegrationOAuthStateReplayed,
    IntegrationProviderOperationError,
)
from app.domain.integration_management.contracts import (
    IntegrationConnectionCreate,
    IntegrationCredentialInput,
)
from app.domain.user.contracts import User
from app.infrastructure.integrations.registry import IntegrationProviderRegistry
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.integration_management import (
    IntegrationConnectionModel,
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
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from tests.test_prd013_integration_management import FakeGoogleCalendarAdapter

DATABASE_URL = os.getenv("BOTWA_PRD013_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="BOTWA_PRD013_POSTGRES_URL is required for explicit PostgreSQL smoke",
)


def _key() -> str:
    return base64.urlsafe_b64encode(b"p" * 32).decode("ascii")


def _service(
    session: Session, adapter: FakeGoogleCalendarAdapter
) -> IntegrationManagementService:
    return IntegrationManagementService(
        IntegrationManagementRepository(session),
        session,
        EnvironmentSecretCipher(_key()),
        OAuthStateSigner(secret_key="p" * 32),
        IntegrationProviderRegistry((adapter,)),
        SqlAlchemyAuditRepository(session),
    )


def test_prd013_postgresql_persistence_security_and_tenant_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert DATABASE_URL is not None
    engine = create_engine(DATABASE_URL)
    assert engine.dialect.name == "postgresql"
    expected_tables = {
        "integration_connection",
        "integration_credential",
        "integration_health_check",
        "integration_oauth_state",
    }
    assert expected_tables.issubset(set(inspect(engine).get_table_names()))
    sessions = sessionmaker(bind=engine)
    organization_id, foreign_org_id, bot_id, user_id, foreign_user_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    owner = User(
        id=user_id,
        organization_id=organization_id,
        email="owner@smoke.invalid",
        role="organization_owner",
    )
    foreign_owner = User(
        id=foreign_user_id,
        organization_id=foreign_org_id,
        email="foreign@smoke.invalid",
        role="organization_owner",
    )
    adapter = FakeGoogleCalendarAdapter()
    with sessions() as session:
        session.add_all(
            (
                OrganizationModel(
                    id=organization_id,
                    name="Smoke A",
                    slug=f"smoke-a-{str(organization_id)[:8]}",
                    status="active",
                ),
                OrganizationModel(
                    id=foreign_org_id,
                    name="Smoke B",
                    slug=f"smoke-b-{str(foreign_org_id)[:8]}",
                    status="active",
                ),
            )
        )
        session.flush()
        session.add_all(
            (
                BotModel(
                    id=bot_id,
                    organization_id=organization_id,
                    name="Smoke Bot",
                    slug="smoke-bot",
                    status="active",
                ),
                UserModel(
                    id=user_id,
                    organization_id=organization_id,
                    email=owner.email,
                    password_hash="x",
                    role=owner.role,
                    status="active",
                ),
                UserModel(
                    id=foreign_user_id,
                    organization_id=foreign_org_id,
                    email=foreign_owner.email,
                    password_hash="x",
                    role=foreign_owner.role,
                    status="active",
                ),
            )
        )
        session.commit()
        service = _service(session, adapter)
        created = service.create(
            organization_id,
            IntegrationConnectionCreate(
                name="PostgreSQL Calendar",
                bot_id=bot_id,
                integration_type="calendar",
                provider="google_calendar",
                capabilities=[
                    "calendar.metadata.read",
                    "calendar.availability.read",
                ],
                configuration={"timezone": "America/Lima", "read_only": True},
            ),
            owner,
        )
        service.update_credentials(
            organization_id,
            created.id,
            IntegrationCredentialInput(refresh_token="postgres-smoke-refresh"),
            owner,
        )
        assert service.activate(organization_id, created.id, owner).status == "active"
        assert service.check_health(organization_id, created.id, owner).status == (
            "healthy"
        )
        oauth_start = service.start_google_oauth(organization_id, created.id, owner)
        oauth_state = oauth_start.authorization_url.split("state=", maxsplit=1)[1]
        service.complete_google_oauth(oauth_state, "postgres-one-time-code")
        with pytest.raises(IntegrationOAuthStateReplayed):
            service.complete_google_oauth(oauth_state, "postgres-replay-code")

        with pytest.raises(IntegrationNotFoundError):
            service.get(foreign_org_id, created.id, foreign_owner)
        credential = session.scalars(
            select(IntegrationCredentialModel).where(
                IntegrationCredentialModel.integration_connection_id == created.id
            )
        ).one()
        assert "postgres-smoke-refresh" not in credential.encrypted_payload
        row = session.get(IntegrationConnectionModel, created.id)
        assert row is not None
        assert "refresh" not in str(row.configuration).lower()
        encrypted_before_failed_callback = credential.encrypted_payload
        health_count_before_failed_callback = len(
            session.scalars(
                select(IntegrationHealthCheckModel).where(
                    IntegrationHealthCheckModel.integration_connection_id == created.id
                )
            ).all()
        )
        adapter.oauth_refresh_token = "postgres-rollback-refresh"
        rollback_start = service.start_google_oauth(
            organization_id,
            created.id,
            owner,
        )
        rollback_state = rollback_start.authorization_url.split("state=", maxsplit=1)[1]

        def persist_invalid_health(
            connection: IntegrationConnectionModel,
            _adapter: object,
            access_token: str,
        ) -> None:
            assert access_token == "ephemeral-access"
            session.add(
                IntegrationHealthCheckModel(
                    organization_id=connection.organization_id,
                    integration_connection_id=connection.id,
                    status="invalid",
                    safe_error_code=None,
                    checked_at=datetime.now(UTC),
                    latency_ms=0,
                )
            )

        monkeypatch.setattr(service, "_record_oauth_health", persist_invalid_health)
        with pytest.raises(IntegrationProviderOperationError) as error:
            service.complete_google_oauth(
                rollback_state,
                "postgres-rollback-code",
            )
        assert error.value.safe_code == "INTEGRATION_PROVIDER_ERROR"

        rolled_back_credential = service.repository.credential(
            organization_id,
            created.id,
        )
        assert rolled_back_credential is not None
        assert (
            rolled_back_credential.encrypted_payload == encrypted_before_failed_callback
        )
        assert (
            len(
                session.scalars(
                    select(IntegrationHealthCheckModel).where(
                        IntegrationHealthCheckModel.integration_connection_id
                        == created.id
                    )
                ).all()
            )
            == health_count_before_failed_callback
        )
        rollback_claims = service.oauth_state_signer.decode(rollback_state)
        consumed_state = session.scalars(
            select(IntegrationOAuthStateModel).where(
                IntegrationOAuthStateModel.nonce_hash == rollback_claims.nonce_hash
            )
        ).one()
        assert consumed_state.consumed_at is not None
        with pytest.raises(IntegrationOAuthStateReplayed):
            service.complete_google_oauth(rollback_state, "postgres-replay-code")
        integration_id = created.id

    with sessions() as restarted:
        persisted = restarted.get(IntegrationConnectionModel, integration_id)
        assert persisted is not None
        assert persisted.status == "active"
        assert persisted.health_status == "healthy"
        health = restarted.scalars(
            select(IntegrationHealthCheckModel).where(
                IntegrationHealthCheckModel.integration_connection_id == integration_id
            )
        ).all()
        assert len(health) == 2
        assert all(item.safe_error_code is None for item in health)
    engine.dispose()
