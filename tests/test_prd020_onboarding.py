from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.api.dependencies import require_authenticated_user
from app.api.onboarding_dependencies import get_onboarding_service
from app.api.onboarding_routes import router
from app.application.onboarding.readiness import OnboardingReadinessService
from app.application.onboarding.service import OnboardingService
from app.domain.audit.contracts import AuditEventDraft, OnboardingMetadata
from app.domain.audit.ports import AuditWriter
from app.domain.onboarding.contracts import OnboardingResponse, OnboardingStepResponse
from app.domain.onboarding.errors import (
    OnboardingNotReady,
    OnboardingNotStarted,
    OnboardingVersionConflict,
)
from app.domain.plans.contracts import PlanConfiguration
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.audit import AuditEventModel
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.business_configuration import BusinessConfigurationModel
from app.infrastructure.models.integration_management import (
    IntegrationConnectionModel,
    IntegrationCredentialModel,
)
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.models.onboarding import OrganizationOnboardingModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.plan import (
    OrganizationPlanAssignmentModel,
    PlanDefinitionModel,
)
from app.infrastructure.models.user import UserModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.onboarding_repository import (
    SqlAlchemyOnboardingRepository,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as value:
        yield value
    engine.dispose()


def _plan_configuration(
    *, whatsapp: bool = True, knowledge: bool = True, integrations: bool = True
) -> PlanConfiguration:
    return PlanConfiguration.model_validate(
        {
            "features": {
                "analytics": True,
                "analytics_export": True,
                "audit": True,
                "integrations": integrations,
                "automations": True,
                "human_handoff": True,
                "business_calendar": True,
                "knowledge": knowledge,
                "whatsapp_configuration": whatsapp,
            },
            "limits": {
                "max_active_bots": {"kind": "unlimited"},
                "max_active_users": {"kind": "unlimited"},
                "max_integrations": {"kind": "unlimited"},
                "max_automations": {"kind": "unlimited"},
                "max_business_calendars": {"kind": "unlimited"},
                "max_whatsapp_configurations": {"kind": "unlimited"},
                "max_knowledge_entries": {"kind": "unlimited"},
            },
        }
    )


def _seed(
    session: Session,
    *,
    role: str = "organization_owner",
    organization_status: str = "active",
    whatsapp_feature: bool = True,
    knowledge_feature: bool = True,
    integrations_feature: bool = True,
) -> tuple[UUID, User]:
    organization_id, user_id, plan_id = uuid4(), uuid4(), uuid4()
    session.add_all(
        [
            OrganizationModel(
                id=organization_id,
                name="Tenant",
                slug=f"tenant-{organization_id.hex[:8]}",
                status=organization_status,
                settings={"locale": "es", "timezone": "America/Lima"},
                created_at=NOW,
                updated_at=NOW,
            ),
            PlanDefinitionModel(
                id=plan_id,
                plan_code=f"plan-{plan_id.hex[:8]}",
                display_name="Onboarding",
                status="active",
                configuration=_plan_configuration(
                    whatsapp=whatsapp_feature,
                    knowledge=knowledge_feature,
                    integrations=integrations_feature,
                ).model_dump(mode="json"),
                created_at=NOW,
                updated_at=NOW,
            ),
        ]
    )
    session.flush()
    session.add_all(
        [
            UserModel(
                id=user_id,
                organization_id=organization_id,
                email=f"{user_id}@example.invalid",
                password_hash="hash",
                role=role,
                status="active",
                auth_version=1,
                created_at=NOW,
                updated_at=NOW,
            ),
            OrganizationPlanAssignmentModel(
                organization_id=organization_id,
                plan_definition_id=plan_id,
                version=1,
                created_at=NOW,
                updated_at=NOW,
            ),
        ]
    )
    session.commit()
    actor = User(
        id=user_id,
        organization_id=organization_id,
        email="owner@example.invalid",
        role=role,
    )
    return organization_id, actor


def _service(session: Session, writer: AuditWriter | None = None) -> OnboardingService:
    repository = SqlAlchemyOnboardingRepository(session)
    return OnboardingService(
        repository,
        OnboardingReadinessService(repository),
        session,
        writer or SqlAlchemyAuditRepository(session),
    )


def _business_hours() -> dict[str, object]:
    closed = {"enabled": False, "open_time": None, "close_time": None}
    return {
        day: dict(closed)
        for day in (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )
    }


def _make_ready(session: Session, organization_id: UUID, actor: User) -> UUID:
    bot_id = uuid4()
    session.add(
        BotModel(
            id=bot_id,
            organization_id=organization_id,
            name="Ready Bot",
            slug=f"ready-{bot_id.hex[:8]}",
            status="active",
            settings={},
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.flush()
    session.add_all(
        [
            BusinessConfigurationModel(
                bot_id=bot_id,
                business_name="Luri",
                description="Configured business",
                timezone="America/Lima",
                business_hours=_business_hours(),
                services=[{"name": "Support", "active": True}],
                payment_methods=["cash"],
                policies=[],
                service_instructions="Answer safely",
                handoff_enabled=False,
                handoff_keywords=[],
                handoff_outside_business_hours=False,
                status="configured",
                created_at=NOW,
                updated_at=NOW,
            ),
            WhatsAppChannelConfigurationModel(
                organization_id=organization_id,
                bot_id=bot_id,
                display_name="Support",
                phone_number_id=f"phone-{bot_id}",
                whatsapp_business_account_id=f"waba-{bot_id}",
                public_webhook_id=uuid4(),
                status="active",
                webhook_enabled=True,
                verify_token_ciphertext="encrypted",
                access_token_ciphertext="encrypted",
                app_secret_ciphertext="encrypted",
                created_by_user_id=actor.id,
                created_at=NOW,
                updated_at=NOW,
            ),
        ]
    )
    session.commit()
    return bot_id


def _steps(response: OnboardingResponse) -> dict[str, OnboardingStepResponse]:
    return {step.code: step for step in response.steps}


def test_legacy_get_derives_not_started_without_creating_row(session: Session) -> None:
    organization_id, actor = _seed(session, whatsapp_feature=False)
    response = _service(session).get(organization_id, actor)
    assert response.workflow_status == "not_started"
    assert response.version is None
    assert response.current_readiness == "not_ready"
    assert response.next_step == "initial_bot"
    assert session.get(OrganizationOnboardingModel, organization_id) is None


def test_readiness_required_optional_and_feature_applicability(
    session: Session,
) -> None:
    organization_id, actor = _seed(
        session,
        whatsapp_feature=False,
        knowledge_feature=False,
        integrations_feature=False,
    )
    bot_id = _make_ready(session, organization_id, actor)
    response = _service(session).get(organization_id, actor)
    steps = _steps(response)
    assert response.ready_to_complete is True
    assert response.current_readiness == "ready"
    assert steps["whatsapp"].status == "not_applicable"
    assert steps["knowledge"].status == "not_applicable"
    assert steps["integrations"].status == "not_applicable"
    assert response.steps[2].resource_reference is not None
    assert response.steps[2].resource_reference.resource_id == bot_id


def test_whatsapp_is_required_but_knowledge_and_integrations_are_optional(
    session: Session,
) -> None:
    organization_id, actor = _seed(session)
    bot_id = _make_ready(session, organization_id, actor)
    session.query(WhatsAppChannelConfigurationModel).delete()
    session.add(
        KnowledgeEntryModel(
            organization_id=organization_id,
            bot_id=bot_id,
            title="Published",
            content="Safe content",
            status="published",
            source_type="manual",
            metadata_data={},
            created_by_user_id=actor.id,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.commit()
    response = _service(session).get(organization_id, actor)
    steps = _steps(response)
    assert response.ready_to_complete is False
    assert steps["whatsapp"].blocking_reason_code == "WHATSAPP_CONFIGURATION_REQUIRED"
    assert steps["knowledge"].status == "ready"
    assert steps["integrations"].status == "incomplete"


def test_core_blocking_reasons_are_derived_from_current_sources(
    session: Session,
) -> None:
    organization_id, actor = _seed(session, whatsapp_feature=False)
    organization = session.get(OrganizationModel, organization_id)
    assert organization is not None
    organization.status = "inactive"
    owner = session.get(UserModel, actor.id)
    assert owner is not None
    owner.status = "inactive"
    assignment = session.get(OrganizationPlanAssignmentModel, organization_id)
    assert assignment is not None
    session.delete(assignment)
    session.commit()
    response = _service(session).get(organization_id, actor)
    steps = _steps(response)
    assert steps["organization_profile"].blocking_reason_code == (
        "ORGANIZATION_INACTIVE"
    )
    assert steps["owner_ready"].blocking_reason_code == "OWNER_REQUIRED"
    assert steps["initial_bot"].blocking_reason_code == "BOT_REQUIRED"
    assert steps["review"].status == "blocked"


def test_inactive_bot_and_invalid_business_configuration_are_not_ready(
    session: Session,
) -> None:
    organization_id, actor = _seed(session, whatsapp_feature=False)
    bot = BotModel(
        organization_id=organization_id,
        name="Inactive",
        slug="inactive",
        status="inactive",
        settings={},
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(bot)
    session.commit()
    response = _service(session).get(organization_id, actor)
    assert _steps(response)["initial_bot"].blocking_reason_code == "BOT_INACTIVE"
    bot.status = "active"
    session.add(
        BusinessConfigurationModel(
            bot_id=bot.id,
            business_name="Invalid",
            description="Stored invalid configuration",
            timezone="America/Lima",
            business_hours={},
            services=[],
            payment_methods=[],
            policies=[],
            service_instructions="",
            handoff_enabled=False,
            handoff_keywords=[],
            handoff_outside_business_hours=False,
            status="configured",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.commit()
    response = _service(session).get(organization_id, actor)
    assert _steps(response)["business_configuration"].status == "incomplete"


def test_retired_plan_is_unavailable(session: Session) -> None:
    organization_id, actor = _seed(session, whatsapp_feature=False)
    assignment = session.get(OrganizationPlanAssignmentModel, organization_id)
    assert assignment is not None
    plan = session.get(PlanDefinitionModel, assignment.plan_definition_id)
    assert plan is not None
    plan.status = "retired"
    session.commit()
    response = _service(session).get(organization_id, actor)
    assert _steps(response)["review"].blocking_reason_code == "PLAN_UNAVAILABLE"


def test_multi_bot_selector_prefers_active_configured_then_created_at(
    session: Session,
) -> None:
    organization_id, actor = _seed(session, whatsapp_feature=False)
    first = BotModel(
        organization_id=organization_id,
        name="First",
        slug="first",
        status="active",
        settings={},
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(first)
    session.commit()
    configured_id = _make_ready(session, organization_id, actor)
    response = _service(session).get(organization_id, actor)
    assert response.steps[2].resource_reference is not None
    assert response.steps[2].resource_reference.resource_id == configured_id


def test_start_complete_noops_versioning_audit_and_degradation(
    session: Session,
) -> None:
    organization_id, actor = _seed(session)
    bot_id = _make_ready(session, organization_id, actor)
    service = _service(session)
    started = service.start(organization_id, actor)
    assert (started.workflow_status, started.version) == ("in_progress", 1)
    assert service.start(organization_id, actor).version == 1
    completed = service.complete(organization_id, 1, actor)
    assert (completed.workflow_status, completed.version) == ("completed", 2)
    assert service.complete(organization_id, 999, actor).version == 2
    actions = session.scalars(
        select(AuditEventModel.action).where(
            AuditEventModel.organization_id == organization_id
        )
    ).all()
    assert sorted(actions) == ["onboarding.completed", "onboarding.started"]
    session.query(WhatsAppChannelConfigurationModel).filter_by(bot_id=bot_id).delete()
    session.commit()
    degraded = service.get(organization_id, actor)
    assert degraded.workflow_status == "completed"
    assert degraded.current_readiness == "degraded"
    assert degraded.completed_at is not None
    assert completed.completed_at is not None
    assert degraded.completed_at.replace(tzinfo=UTC) == completed.completed_at


def test_complete_errors_do_not_mutate_or_audit(session: Session) -> None:
    organization_id, actor = _seed(session)
    service = _service(session)
    with pytest.raises(OnboardingNotStarted):
        service.complete(organization_id, 1, actor)
    service.start(organization_id, actor)
    with pytest.raises(OnboardingVersionConflict):
        service.complete(organization_id, 2, actor)
    with pytest.raises(OnboardingNotReady) as exc_info:
        service.complete(organization_id, 1, actor)
    assert "BOT_REQUIRED" in exc_info.value.blockers
    workflow = session.get(OrganizationOnboardingModel, organization_id)
    assert workflow is not None and workflow.version == 1
    assert session.scalar(select(func.count(AuditEventModel.id))) == 1


def test_audit_failure_rolls_back_start_and_complete(session: Session) -> None:
    organization_id, actor = _seed(session)

    class FailingWriter:
        def append(self, draft: AuditEventDraft) -> None:
            raise RuntimeError("audit unavailable")

    with pytest.raises(RuntimeError):
        _service(session, FailingWriter()).start(organization_id, actor)
    assert session.get(OrganizationOnboardingModel, organization_id) is None
    _make_ready(session, organization_id, actor)
    healthy = _service(session)
    healthy.start(organization_id, actor)
    with pytest.raises(RuntimeError):
        _service(session, FailingWriter()).complete(organization_id, 1, actor)
    workflow = session.get(OrganizationOnboardingModel, organization_id)
    assert workflow is not None and workflow.status == "in_progress"


@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        ("platform_admin", True),
        ("organization_owner", True),
        ("organization_admin", True),
        ("operator", False),
        ("viewer", False),
    ],
)
def test_rbac_and_api_safe_response(session: Session, role: str, allowed: bool) -> None:
    organization_id, actor = _seed(session, role=role, whatsapp_feature=False)
    service = _service(session)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_onboarding_service] = lambda: service
    app.dependency_overrides[require_authenticated_user] = lambda: actor
    client = TestClient(app)
    response = client.get(f"/organizations/{organization_id}/onboarding")
    assert response.status_code == (200 if allowed else 403)
    if allowed:
        payload = response.json()
        serialized = str(payload).lower()
        assert "access_token" not in serialized
        assert "phone_number_id" not in serialized
        assert "ciphertext" not in serialized


def test_tenant_isolation_and_platform_admin_explicit_scope(session: Session) -> None:
    organization_id, _ = _seed(session, whatsapp_feature=False)
    other_id, other_owner = _seed(session, whatsapp_feature=False)
    service = _service(session)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_onboarding_service] = lambda: service
    app.dependency_overrides[require_authenticated_user] = lambda: other_owner
    client = TestClient(app)
    forbidden = client.get(f"/organizations/{organization_id}/onboarding")
    assert forbidden.status_code == 403
    platform = User(
        id=other_owner.id,
        organization_id=other_id,
        email="platform@example.invalid",
        role="platform_admin",
    )
    app.dependency_overrides[require_authenticated_user] = lambda: platform
    allowed = client.get(f"/organizations/{organization_id}/onboarding")
    assert allowed.status_code == 200


def test_integration_uses_persisted_health_without_network(session: Session) -> None:
    organization_id, actor = _seed(session, whatsapp_feature=False)
    bot_id = _make_ready(session, organization_id, actor)
    integration = IntegrationConnectionModel(
        organization_id=organization_id,
        bot_id=bot_id,
        name="Calendar",
        integration_type="calendar",
        provider="google_calendar",
        status="active",
        version=1,
        capabilities=["calendar.metadata.read"],
        configuration={"read_only": True},
        health_status="healthy",
        last_health_checked_at=NOW,
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
        created_at=NOW,
        updated_at=NOW,
    )
    session.add(integration)
    session.flush()
    session.add(
        IntegrationCredentialModel(
            organization_id=organization_id,
            integration_connection_id=integration.id,
            credential_type="google_oauth_refresh",
            encrypted_payload="encrypted",
            key_version="v1",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.commit()
    steps = _steps(_service(session).get(organization_id, actor))
    assert steps["integrations"].status == "ready"
    assert steps["integrations"].external_validation == "last_known_valid"


def test_onboarding_audit_metadata_is_typed() -> None:
    metadata = OnboardingMetadata(
        workflow_version=2,
        required_steps_ready=6,
        required_steps_total=6,
    )
    assert metadata.required_steps_ready == metadata.required_steps_total
