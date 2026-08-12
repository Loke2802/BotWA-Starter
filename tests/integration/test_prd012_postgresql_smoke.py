import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.application.automation_management.service import ManagedAutomationService
from app.application.human_handoff.service import HumanHandoffService
from app.domain.automation_management.contracts import AutomationDefinitionInput
from app.domain.user.contracts import User
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.managed_automation import (
    ManagedAutomationEventReceiptModel,
    ManagedAutomationExecutionModel,
)
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.human_handoff_repository import (
    HumanHandoffRepository,
)
from app.infrastructure.repositories.managed_automation_repository import (
    ManagedAutomationRepository,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from tests.plan_support import allow_all_plan_enforcement

DATABASE_URL = os.getenv("BOTWA_PRD012_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="requires real PostgreSQL")


def test_prd012_postgresql_critical_smoke() -> None:
    assert DATABASE_URL and DATABASE_URL.startswith("postgresql")
    engine = create_engine(DATABASE_URL)
    factory = sessionmaker(bind=engine)
    org_id, other_org_id, bot_id, user_id, conversation_id = (uuid4() for _ in range(5))
    source_id, inside_source_id = uuid4(), uuid4()
    with factory() as session:
        session.add_all(
            [
                OrganizationModel(
                    id=org_id,
                    name="Smoke A",
                    slug=f"smoke-a-{org_id.hex[:8]}",
                    status="active",
                ),
                OrganizationModel(
                    id=other_org_id,
                    name="Smoke B",
                    slug=f"smoke-b-{other_org_id.hex[:8]}",
                    status="active",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                BotModel(
                    id=bot_id,
                    organization_id=org_id,
                    name="Smoke Bot",
                    slug="smoke-bot",
                    status="active",
                ),
                UserModel(
                    id=user_id,
                    organization_id=org_id,
                    email=f"smoke-{user_id}@example.invalid",
                    password_hash="synthetic",
                    role="organization_owner",
                    status="active",
                ),
                ConversationModel(
                    id=conversation_id,
                    company_id=str(org_id),
                    customer_id="synthetic",
                    organization_id=org_id,
                    bot_id=bot_id,
                    channel="whatsapp",
                    management_status="open",
                    status="new",
                ),
            ]
        )
        session.commit()
        actor = User(
            id=user_id,
            organization_id=org_id,
            email=f"smoke-{user_id}@example.invalid",
            role="organization_owner",
        )
        audit_writer = SqlAlchemyAuditRepository(session)
        handoff = HumanHandoffService(
            HumanHandoffRepository(session),
            session,
            audit_writer,
            allow_all_plan_enforcement(),
        )
        service = ManagedAutomationService(
            ManagedAutomationRepository(session),
            session,
            audit_writer,
            plan_enforcement=allow_all_plan_enforcement(),
            handoff=handoff,
        )
        definition = service.create(
            org_id,
            AutomationDefinitionInput(
                name="Outside-hours handoff",
                bot_id=str(bot_id),
                trigger_type="conversation.inbound_received",
                conditions_data={
                    "business_hours_state": "outside",
                    "handoff_active": False,
                },
                action_type="request_handoff",
                action_data={"reason_code": "outside_business_hours"},
            ),
            actor,
        )
        assert definition.status == "draft" and definition.version == 1
        assert (
            service.transition(org_id, definition.id, "activate", actor).status
            == "active"
        )
        service.record_inbound(
            organization_id=org_id,
            bot_id=bot_id,
            conversation_id=conversation_id,
            contact_id=None,
            channel_type="whatsapp",
            received_at=datetime.now(UTC),
            business_hours_state="outside",
            source_receipt_id=source_id,
        )
        service.record_inbound(
            organization_id=org_id,
            bot_id=bot_id,
            conversation_id=conversation_id,
            contact_id=None,
            channel_type="whatsapp",
            received_at=datetime.now(UTC),
            business_hours_state="outside",
            source_receipt_id=source_id,
        )
        assert (
            session.scalar(
                select(func.count()).select_from(ManagedAutomationEventReceiptModel)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count()).select_from(ManagedAutomationExecutionModel)
            )
            == 1
        )
        pending = session.scalars(select(ManagedAutomationExecutionModel)).one()
        assert pending.status == "pending"
        claimed = service.repo.claim("smoke-worker", 10, 60)
        assert len(claimed) == 1
        service.run(claimed[0])
        assert claimed[0].status == "succeeded"
        assert (
            session.scalar(select(func.count()).select_from(HandoffSessionModel)) == 1
        )
        service.record_inbound(
            organization_id=org_id,
            bot_id=bot_id,
            conversation_id=conversation_id,
            contact_id=None,
            channel_type="whatsapp",
            received_at=datetime.now(UTC),
            business_hours_state="inside",
            source_receipt_id=inside_source_id,
        )
        inside = session.scalars(
            select(ManagedAutomationExecutionModel).where(
                ManagedAutomationExecutionModel.event_receipt_id
                != pending.event_receipt_id
            )
        ).one()
        service.run(service.repo.claim("smoke-worker", 10, 60)[0])
        assert inside.status == "skipped"
        assert service.repo.definition(other_org_id, definition.id) is None
        forbidden = {
            "message",
            "text",
            "body",
            "phone",
            "sender",
            "external_customer_id",
            "ciphertext",
            "hash",
            "display_name",
            "notes",
            "token",
            "secret",
        }
        for receipt in session.scalars(select(ManagedAutomationEventReceiptModel)):
            assert forbidden.isdisjoint(receipt.event_data)
        succeeded_id = pending.id
        session.commit()
    with factory() as fresh:
        persisted = fresh.get(ManagedAutomationExecutionModel, succeeded_id)
        assert persisted is not None and persisted.status == "succeeded"
        assert fresh.scalar(select(func.count()).select_from(HandoffSessionModel)) == 1
    engine.dispose()
