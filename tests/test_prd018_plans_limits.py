from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.api.dependencies import require_authenticated_user
from app.api.plan_dependencies import (
    get_plan_assignment_service,
    get_plan_query_service,
)
from app.api.plan_routes import router
from app.application.organizations.service import OrganizationService
from app.application.plans.service import (
    PlanAssignmentService,
    PlanEnforcementService,
    PlanQueryService,
)
from app.domain.audit.contracts import AuditEventDraft, PlanAssignmentMetadata
from app.domain.organization.contracts import OrganizationCreate
from app.domain.plans.contracts import LimitedLimit, PlanConfiguration
from app.domain.plans.errors import (
    PlanFeatureNotAvailable,
    PlanForbidden,
    PlanLimitReached,
    PlanUnavailable,
    PlanVersionConflict,
)
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.plan import (
    OrganizationPlanAssignmentModel,
    PlanDefinitionModel,
)
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.plan_repository import SqlAlchemyPlanRepository
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


class RecordingAuditWriter:
    def __init__(self) -> None:
        self.events: list[AuditEventDraft] = []

    def append(self, draft: AuditEventDraft) -> None:
        self.events.append(draft)


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as value:
        yield value
    Base.metadata.drop_all(engine)
    engine.dispose()


def _configuration(
    *, analytics: bool = True, active_bots: int | None = None
) -> PlanConfiguration:
    limit = (
        {"kind": "unlimited"}
        if active_bots is None
        else {"kind": "limited", "value": active_bots}
    )
    return PlanConfiguration.model_validate(
        {
            "features": {
                "analytics": analytics,
                "analytics_export": True,
                "audit": True,
                "integrations": True,
                "automations": True,
                "human_handoff": True,
                "business_calendar": True,
                "knowledge": True,
                "whatsapp_configuration": True,
            },
            "limits": {
                "max_active_bots": limit,
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
    second_configuration: PlanConfiguration | None = None,
    second_status: str = "active",
) -> tuple[UUID, User, PlanDefinitionModel, PlanDefinitionModel | None]:
    organization_id = uuid4()
    user_id = uuid4()
    default = PlanDefinitionModel(
        id=UUID("01800000-0000-0000-0000-000000000001"),
        plan_code="default",
        display_name="Default",
        status="active",
        configuration=_configuration().model_dump(mode="json"),
        created_at=NOW,
        updated_at=NOW,
    )
    second = None
    if second_configuration is not None:
        second = PlanDefinitionModel(
            id=uuid4(),
            plan_code="restricted",
            display_name="Restricted",
            status=second_status,
            configuration=second_configuration.model_dump(mode="json"),
            created_at=NOW,
            updated_at=NOW,
        )
    session.add_all(
        [
            OrganizationModel(
                id=organization_id,
                name="Tenant",
                slug=f"tenant-{organization_id.hex[:8]}",
                status="active",
                settings={},
                created_at=NOW,
                updated_at=NOW,
            ),
            default,
        ]
        + ([second] if second is not None else [])
    )
    session.flush()
    session.add(
        UserModel(
            id=user_id,
            organization_id=organization_id,
            email=f"admin-{user_id.hex[:8]}@example.com",
            password_hash="hash",
            role="platform_admin",
            status="active",
            auth_version=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.add(
        OrganizationPlanAssignmentModel(
            organization_id=organization_id,
            plan_definition_id=default.id,
            version=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.commit()
    actor = User(
        id=user_id,
        organization_id=organization_id,
        email="platform@example.com",
        role="platform_admin",
    )
    return organization_id, actor, default, second


def _services(
    session: Session, writer: RecordingAuditWriter
) -> tuple[PlanEnforcementService, PlanQueryService, PlanAssignmentService]:
    repository = SqlAlchemyPlanRepository(session)
    enforcement = PlanEnforcementService(repository)
    query = PlanQueryService(repository, enforcement)
    assignment = PlanAssignmentService(repository, session, writer, query)
    return enforcement, query, assignment


def test_configuration_is_closed_and_zero_means_no_capacity() -> None:
    with pytest.raises(ValidationError):
        PlanConfiguration.model_validate(
            {
                **_configuration().model_dump(mode="json"),
                "unknown": True,
            }
        )
    limit = _configuration(active_bots=0).limits.max_active_bots
    assert isinstance(limit, LimitedLimit)
    assert limit.value == 0


def test_new_organization_bootstraps_default_assignment_in_same_uow(
    session: Session,
) -> None:
    session.add(
        PlanDefinitionModel(
            id=UUID("01800000-0000-0000-0000-000000000001"),
            plan_code="default",
            display_name="Default",
            status="active",
            configuration=_configuration().model_dump(mode="json"),
            created_at=NOW,
            updated_at=NOW,
        )
    )
    session.commit()
    writer = RecordingAuditWriter()
    service = OrganizationService(
        OrganizationRepository(session),
        session,
        writer,
        plan_repository=SqlAlchemyPlanRepository(session),
    )
    organization = service.create(
        OrganizationCreate(name="Bootstrap", slug="bootstrap")
    )
    assignment = session.get(OrganizationPlanAssignmentModel, organization.id)
    assert assignment is not None
    assert assignment.plan_definition_id == UUID("01800000-0000-0000-0000-000000000001")
    assert [event.action for event in writer.events] == ["organization.created"]


def test_default_plan_is_unlimited_and_counts_source_of_truth(session: Session) -> None:
    organization_id, actor, _, _ = _seed(session)
    writer = RecordingAuditWriter()
    enforcement, query, _ = _services(session, writer)
    session.add(
        BotModel(
            organization_id=organization_id,
            name="Bot",
            slug="bot",
            status="active",
            settings={},
        )
    )
    session.commit()
    enforcement.require_capacity(organization_id, "max_active_bots")
    response = query.get(organization_id, actor)
    limit = response.limits.max_active_bots
    assert (limit.kind, limit.current, limit.reached, limit.over_limit) == (
        "unlimited",
        1,
        False,
        False,
    )


def test_feature_and_hard_limit_denials(session: Session) -> None:
    organization_id, _, default, _ = _seed(session)
    default.configuration = _configuration(analytics=False, active_bots=0).model_dump(
        mode="json"
    )
    session.commit()
    enforcement, _, _ = _services(session, RecordingAuditWriter())
    with pytest.raises(PlanFeatureNotAvailable):
        enforcement.require_feature(organization_id, "analytics")
    with pytest.raises(PlanLimitReached) as exc_info:
        enforcement.require_capacity(organization_id, "max_active_bots")
    assert exc_info.value.limit_key == "max_active_bots"


def test_plan_change_is_versioned_audited_and_same_plan_is_noop(
    session: Session,
) -> None:
    configuration = _configuration(active_bots=1)
    organization_id, actor, _, restricted = _seed(
        session, second_configuration=configuration
    )
    assert restricted is not None
    writer = RecordingAuditWriter()
    _, _, assignment = _services(session, writer)
    changed = assignment.assign(organization_id, "restricted", 1, actor)
    assert changed.version == 2
    assert len(writer.events) == 1
    assert writer.events[0].action == "plan.changed"
    assert writer.events[0].resource_type == "plan_assignment"
    metadata = writer.events[0].metadata
    assert isinstance(metadata, PlanAssignmentMetadata)
    assert metadata.from_plan_code == "default"
    noop = assignment.assign(organization_id, "restricted", 2, actor)
    assert noop.version == 2
    assert len(writer.events) == 1
    with pytest.raises(PlanVersionConflict):
        assignment.assign(organization_id, "restricted", 1, actor)


def test_retired_plan_cannot_be_new_target(session: Session) -> None:
    organization_id, actor, _, _ = _seed(
        session,
        second_configuration=_configuration(),
        second_status="retired",
    )
    _, _, assignment = _services(session, RecordingAuditWriter())
    with pytest.raises(PlanUnavailable):
        assignment.assign(organization_id, "restricted", 1, actor)


def test_downgrade_reports_reached_and_over_limit_without_deleting(
    session: Session,
) -> None:
    organization_id, actor, _, _ = _seed(
        session, second_configuration=_configuration(active_bots=1)
    )
    for index in range(2):
        session.add(
            BotModel(
                organization_id=organization_id,
                name=f"Bot {index}",
                slug=f"bot-{index}",
                status="active",
                settings={},
            )
        )
    session.commit()
    _, _, assignment = _services(session, RecordingAuditWriter())
    response = assignment.assign(organization_id, "restricted", 1, actor)
    assert response.limits.max_active_bots.current == 2
    assert response.limits.max_active_bots.reached is True
    assert response.limits.max_active_bots.over_limit is True
    assert session.scalar(select(BotModel).limit(1)) is not None


def test_plan_api_is_tenant_scoped_and_platform_assign_only(session: Session) -> None:
    organization_id, actor, _, _ = _seed(
        session, second_configuration=_configuration(active_bots=2)
    )
    writer = RecordingAuditWriter()
    _, query, assignment = _services(session, writer)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_plan_query_service] = lambda: query
    app.dependency_overrides[get_plan_assignment_service] = lambda: assignment
    app.dependency_overrides[require_authenticated_user] = lambda: actor
    client = TestClient(app)
    response = client.get(f"/organizations/{organization_id}/plan")
    assert response.status_code == 200
    assert response.json()["plan"]["code"] == "default"
    changed = client.put(
        f"/organizations/{organization_id}/plan",
        json={"plan_code": "restricted", "expected_version": 1},
    )
    assert changed.status_code == 200
    assert changed.json()["version"] == 2


def test_owner_can_read_own_plan_but_cannot_assign_or_cross_tenant(
    session: Session,
) -> None:
    organization_id, _, _, _ = _seed(
        session, second_configuration=_configuration(active_bots=2)
    )
    owner = User(
        organization_id=organization_id,
        email="owner@example.com",
        role="organization_owner",
    )
    other_owner = User(
        organization_id=uuid4(),
        email="other@example.com",
        role="organization_owner",
    )
    writer = RecordingAuditWriter()
    _, query, assignment = _services(session, writer)
    assert query.get(organization_id, owner).plan.code == "default"
    with pytest.raises(PlanForbidden):
        query.get(organization_id, other_owner)
    with pytest.raises(PlanForbidden):
        assignment.assign(organization_id, "restricted", 1, owner)


def test_audit_failure_rolls_back_plan_change(session: Session) -> None:
    organization_id, actor, default, _ = _seed(
        session, second_configuration=_configuration(active_bots=2)
    )

    class FailingWriter:
        def append(self, draft: AuditEventDraft) -> None:
            raise RuntimeError("audit unavailable")

    repository = SqlAlchemyPlanRepository(session)
    enforcement = PlanEnforcementService(repository)
    query = PlanQueryService(repository, enforcement)
    assignment = PlanAssignmentService(repository, session, FailingWriter(), query)
    with pytest.raises(RuntimeError):
        assignment.assign(organization_id, "restricted", 1, actor)
    session.rollback()
    persisted = repository.get_assignment(organization_id)
    assert persisted is not None
    assert persisted.plan_definition_id == default.id
    assert persisted.version == 1
