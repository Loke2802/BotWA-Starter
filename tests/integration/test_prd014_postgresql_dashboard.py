import os
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from app.domain.user.contracts import User
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_calendar import (
    BusinessCalendarModel,
    BusinessCalendarWeeklyIntervalModel,
)
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.integration_management import IntegrationConnectionModel
from app.infrastructure.models.managed_automation import (
    ManagedAutomationDefinitionModel,
    ManagedAutomationEventReceiptModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from tests.test_prd014_dashboard import (
    NOW,
    _automation,
    _conversation,
    _service,
)

DATABASE_URL = os.getenv("BOTWA_PRD014_POSTGRES_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="BOTWA_PRD014_POSTGRES_URL is required for explicit PostgreSQL tests",
)


def _database_url() -> str:
    assert DATABASE_URL is not None
    return DATABASE_URL


def _user(organization_id: UUID, label: str) -> User:
    return User(
        id=uuid4(),
        organization_id=organization_id,
        email=f"prd014-{label}-{uuid4()}@smoke.invalid",
        role="organization_owner",
    )


def test_prd014_postgresql_dashboard_is_read_only_and_tenant_scoped() -> None:
    engine = create_engine(_database_url())
    assert engine.dialect.name == "postgresql"
    assert not any(
        table.startswith("dashboard") for table in inspect(engine).get_table_names()
    )
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        organization_a, organization_b = uuid4(), uuid4()
        bot_a1, bot_a2, bot_b = uuid4(), uuid4(), uuid4()
        actor_a, actor_b = _user(organization_a, "a"), _user(organization_b, "b")
        conversation_a1 = _conversation(
            organization_a, bot_a1, "open", NOW - timedelta(hours=1)
        )
        conversation_a2 = _conversation(
            organization_a, bot_a2, "closed", NOW - timedelta(days=2)
        )
        conversation_b = _conversation(
            organization_b, bot_b, "open", NOW - timedelta(hours=1)
        )
        calendar_id = uuid4()
        session.add_all(
            (
                OrganizationModel(
                    id=organization_a,
                    name="PRD-014 tenant A",
                    slug=f"prd014-a-{str(organization_a)[:8]}",
                    status="active",
                    settings={"locale": "es", "timezone": "UTC"},
                ),
                OrganizationModel(
                    id=organization_b,
                    name="PRD-014 tenant B",
                    slug=f"prd014-b-{str(organization_b)[:8]}",
                    status="active",
                    settings={"locale": "es", "timezone": "UTC"},
                ),
                UserModel(
                    id=actor_a.id,
                    organization_id=organization_a,
                    email=actor_a.email,
                    password_hash="x",
                    role=actor_a.role,
                    status="active",
                ),
                UserModel(
                    id=actor_b.id,
                    organization_id=organization_b,
                    email=actor_b.email,
                    password_hash="x",
                    role=actor_b.role,
                    status="active",
                ),
                BotModel(
                    id=bot_a1,
                    organization_id=organization_a,
                    name="A1",
                    slug="a1",
                    status="active",
                    timezone="UTC",
                ),
                BotModel(
                    id=bot_a2,
                    organization_id=organization_a,
                    name="A2",
                    slug="a2",
                    status="inactive",
                    timezone="UTC",
                ),
                BotModel(
                    id=bot_b,
                    organization_id=organization_b,
                    name="B",
                    slug="b",
                    status="active",
                    timezone="UTC",
                ),
                conversation_a1,
                conversation_a2,
                conversation_b,
                ContactModel(
                    id=uuid4(),
                    organization_id=organization_a,
                    channel_type="whatsapp",
                    external_identifier_hash="d" * 64,
                    external_identifier_ciphertext="encrypted-a",
                    status="active",
                    created_at=NOW,
                    updated_at=NOW,
                ),
                ContactModel(
                    id=uuid4(),
                    organization_id=organization_b,
                    channel_type="whatsapp",
                    external_identifier_hash="e" * 64,
                    external_identifier_ciphertext="encrypted-b",
                    status="active",
                    created_at=NOW,
                    updated_at=NOW,
                ),
                HandoffSessionModel(
                    id=uuid4(),
                    conversation_id=conversation_a1.id,
                    organization_id=organization_a,
                    bot_id=bot_a1,
                    status="waiting_human",
                    requested_at=NOW - timedelta(minutes=30),
                    last_activity_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                HandoffSessionModel(
                    id=uuid4(),
                    conversation_id=conversation_b.id,
                    organization_id=organization_b,
                    bot_id=bot_b,
                    status="human_active",
                    requested_at=NOW,
                    last_activity_at=NOW,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                IntegrationConnectionModel(
                    id=uuid4(),
                    organization_id=organization_a,
                    bot_id=bot_a1,
                    name="A integration",
                    integration_type="calendar",
                    provider="google_calendar",
                    status="active",
                    version=1,
                    capabilities=["calendar.metadata.read"],
                    configuration={"read_only": True},
                    health_status="healthy",
                    created_by_user_id=actor_a.id,
                    updated_by_user_id=actor_a.id,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                IntegrationConnectionModel(
                    id=uuid4(),
                    organization_id=organization_b,
                    bot_id=bot_b,
                    name="B integration",
                    integration_type="calendar",
                    provider="google_calendar",
                    status="active",
                    version=1,
                    capabilities=["calendar.metadata.read"],
                    configuration={"read_only": True},
                    health_status="auth_error",
                    created_by_user_id=actor_b.id,
                    updated_by_user_id=actor_b.id,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                BusinessCalendarModel(
                    id=calendar_id,
                    organization_id=organization_a,
                    name="A hours",
                    timezone="UTC",
                    status="active",
                    version=1,
                    created_by_user_id=actor_a.id,
                    updated_by_user_id=actor_a.id,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                BusinessCalendarWeeklyIntervalModel(
                    id=uuid4(),
                    organization_id=organization_a,
                    calendar_id=calendar_id,
                    weekday=1,
                    start_minute=9 * 60,
                    end_minute=17 * 60,
                    created_at=NOW,
                ),
                *_automation(
                    organization_a,
                    bot_a1,
                    actor_a.id,
                    "succeeded",
                    NOW - timedelta(hours=1),
                ),
                *_automation(
                    organization_a,
                    bot_a2,
                    actor_a.id,
                    "failed",
                    NOW - timedelta(hours=1),
                ),
                *_automation(
                    organization_b,
                    bot_b,
                    actor_b.id,
                    "pending",
                    NOW - timedelta(hours=1),
                ),
            )
        )
        session.flush(
            [row for row in session.new if isinstance(row, OrganizationModel)]
        )
        session.flush(
            [row for row in session.new if isinstance(row, (UserModel, BotModel))]
        )
        session.flush(
            [
                row
                for row in session.new
                if isinstance(
                    row,
                    (
                        ConversationModel,
                        ContactModel,
                        IntegrationConnectionModel,
                        BusinessCalendarModel,
                        ManagedAutomationDefinitionModel,
                        ManagedAutomationEventReceiptModel,
                    ),
                )
            ]
        )
        session.commit()

        result_a = _service(session).summary(
            organization_a,
            actor_a,
            period="last_7_days",
            generated_at=NOW,
        )
        assert result_a.bots.total == 2
        assert result_a.conversations.total == 2
        assert result_a.contacts.total == 1
        assert result_a.handoffs.pending == 1
        assert result_a.handoffs.active == 0
        assert result_a.automations.total == 2
        assert result_a.integrations.total == 1
        assert result_a.business.status == "open"

        result_a1 = _service(session).summary(
            organization_a,
            actor_a,
            bot_id=bot_a1,
            period="last_7_days",
            generated_at=NOW,
        )
        assert result_a1.bots.total == 1
        assert result_a1.conversations.total == 1
        assert result_a1.automations.total == 1
        assert result_a1.contacts.total == 1
        assert not session.new
        assert not session.dirty
        assert not session.deleted
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()
        engine.dispose()
