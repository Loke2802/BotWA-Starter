from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta
from inspect import Parameter, signature
from uuid import UUID, uuid4

import pytest
from app.api.audit_dependencies import get_audit_query_service
from app.api.audit_routes import router
from app.api.dependencies import require_authenticated_user
from app.application.audit.metrics import AuditMetricsRegistry
from app.application.audit.service import AuditCursorCodec, AuditQueryService
from app.application.audit.writer import append_non_user_audit, append_user_audit
from app.application.automation_management.service import ManagedAutomationService
from app.application.bots.service import BotService
from app.application.business_calendar.service import BusinessCalendarService
from app.application.conversation_management.service import (
    ConversationManagementService,
)
from app.application.human_handoff.service import HumanHandoffService
from app.application.integration_management.service import IntegrationManagementService
from app.application.organizations.service import OrganizationService
from app.application.users.service import UserService
from app.domain.access.contracts import ALL_PERMISSIONS, ROLE_PERMISSIONS
from app.domain.audit.contracts import (
    AuditEventDraft,
    ChangedFieldsMetadata,
    CredentialRotationMetadata,
    EmptyMetadata,
    RoleAssignmentMetadata,
    StatusTransitionMetadata,
)
from app.domain.audit.errors import (
    AuditForbidden,
    AuditInvalidCursor,
    AuditInvalidFilter,
    AuditInvalidRange,
    AuditRangeTooLarge,
    AuditWriteError,
)
from app.domain.user.contracts import User
from app.infrastructure.database import Base
from app.infrastructure.models.audit import AuditEventModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.audit_repository import (
    SqlAlchemyAuditRepository,
)
from app.infrastructure.repositories.conversation_management_repository import (
    SqlAlchemyConversationMessageManagementRepository,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 8, 18, tzinfo=UTC)


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


def _seed(session: Session) -> tuple[UUID, UUID, User, User]:
    organization_a, organization_b = uuid4(), uuid4()
    actor_a_id, actor_b_id = uuid4(), uuid4()
    session.add_all(
        (
            OrganizationModel(
                id=organization_a,
                name="Tenant A",
                slug=f"audit-a-{organization_a}",
                status="active",
            ),
            OrganizationModel(
                id=organization_b,
                name="Tenant B",
                slug=f"audit-b-{organization_b}",
                status="active",
            ),
            UserModel(
                id=actor_a_id,
                organization_id=organization_a,
                email=f"{actor_a_id}@audit.invalid",
                password_hash="x",
                role="organization_owner",
                status="active",
            ),
            UserModel(
                id=actor_b_id,
                organization_id=organization_b,
                email=f"{actor_b_id}@audit.invalid",
                password_hash="x",
                role="organization_owner",
                status="active",
            ),
        )
    )
    session.commit()
    return (
        organization_a,
        organization_b,
        User(
            id=actor_a_id,
            organization_id=organization_a,
            email=f"{actor_a_id}@audit.invalid",
            role="organization_owner",
        ),
        User(
            id=actor_b_id,
            organization_id=organization_b,
            email=f"{actor_b_id}@audit.invalid",
            role="organization_owner",
        ),
    )


def _draft(
    organization_id: UUID,
    actor: User,
    *,
    action: str = "bot.deactivated",
    resource_id: UUID | None = None,
    occurred_at: datetime = NOW,
) -> AuditEventDraft:
    return AuditEventDraft.model_validate(
        {
            "organization_id": organization_id,
            "actor_type": "user",
            "actor_user_id": actor.id,
            "actor_role": actor.role,
            "action": action,
            "resource_type": "bot",
            "resource_id": resource_id or uuid4(),
            "metadata": {"from_status": "active", "to_status": "inactive"},
            "occurred_at": occurred_at,
        }
    )


def _service(session: Session) -> AuditQueryService:
    return AuditQueryService(
        SqlAlchemyAuditRepository(session),
        cursor_codec=AuditCursorCodec("audit-test-secret"),
    )


def test_contracts_are_closed_typed_and_reject_pii_secrets_and_free_text() -> None:
    ChangedFieldsMetadata(changed_fields=("name", "timezone"))
    StatusTransitionMetadata(from_status="active", to_status="inactive")
    RoleAssignmentMetadata(from_role="viewer", to_role="operator")
    CredentialRotationMetadata()
    unsafe_payloads: tuple[dict[str, object], ...] = (
        {"email": "person@example.com"},
        {"phone": "+51999999999"},
        {"name": "Person"},
        {"message": "private"},
        {"reason_code": "free text"},
        {"password": "secret"},
        {"password_hash": "hash"},
        {"access_token": "token"},
        {"refresh_token": "token"},
        {"client_secret": "secret"},
        {"api_key": "secret"},
        {"ciphertext": "encrypted"},
        {"oauth_code": "code"},
        {"oauth_state": "state"},
        {"provider_payload": {}},
        {"idempotency_key": "raw-key"},
    )
    for unsafe in unsafe_payloads:
        with pytest.raises(ValidationError):
            AuditEventDraft.model_validate(
                {
                    "organization_id": uuid4(),
                    "actor_type": "system",
                    "action": "organization.created",
                    "resource_type": "organization",
                    "metadata": unsafe,
                    "occurred_at": NOW,
                }
            )


@pytest.mark.parametrize(
    "service_type",
    (
        OrganizationService,
        UserService,
        BotService,
        ConversationManagementService,
        HumanHandoffService,
        ManagedAutomationService,
        IntegrationManagementService,
        BusinessCalendarService,
        SqlAlchemyConversationMessageManagementRepository,
    ),
)
def test_auditable_constructors_require_non_optional_writer(
    service_type: type[object],
) -> None:
    parameter = signature(service_type).parameters["audit_writer"]
    assert parameter.default is Parameter.empty
    assert "None" not in str(parameter.annotation)


@pytest.mark.parametrize("helper", (append_user_audit, append_non_user_audit))
def test_audit_helpers_require_non_optional_writer(
    helper: Callable[..., object],
) -> None:
    parameter = signature(helper).parameters["writer"]
    assert parameter.default is Parameter.empty
    assert "None" not in str(parameter.annotation)


def test_append_metrics_report_unit_of_work_not_durable_commit(
    session: Session,
) -> None:
    organization_id, _, actor, _ = _seed(session)
    metrics = AuditMetricsRegistry()
    writer = SqlAlchemyAuditRepository(session, metrics=metrics)
    writer.append(_draft(organization_id, actor))

    counters = metrics.snapshot()["counters"]
    assert (
        counters[("audit_append_attempts_total", "append", "accepted_by_unit_of_work")]
        == 1
    )
    assert session.scalar(select(func.count(AuditEventModel.id))) == 1
    session.rollback()
    assert session.scalar(select(func.count(AuditEventModel.id))) == 0


def test_append_staging_failure_is_observed(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    organization_id, _, actor, _ = _seed(session)
    metrics = AuditMetricsRegistry()
    writer = SqlAlchemyAuditRepository(session, metrics=metrics)

    def fail_add(_object: object) -> None:
        raise SQLAlchemyError("unit of work rejected audit row")

    monkeypatch.setattr(session, "add", fail_add)
    with pytest.raises(AuditWriteError):
        writer.append(_draft(organization_id, actor))
    assert (
        metrics.snapshot()["counters"][
            ("audit_append_attempts_total", "append", "rejected_by_unit_of_work")
        ]
        == 1
    )


def test_actor_shape_result_action_and_timestamp_are_strict() -> None:
    base = {
        "organization_id": uuid4(),
        "action": "organization.created",
        "resource_type": "organization",
        "occurred_at": NOW,
    }
    with pytest.raises(ValidationError):
        AuditEventDraft.model_validate({**base, "actor_type": "user"})
    with pytest.raises(ValidationError):
        AuditEventDraft.model_validate(
            {**base, "actor_type": "system", "actor_user_id": uuid4()}
        )
    with pytest.raises(ValidationError):
        AuditEventDraft.model_validate(
            {**base, "actor_type": "system", "result": "failed"}
        )
    with pytest.raises(ValidationError):
        AuditEventDraft.model_validate(
            {**base, "actor_type": "system", "occurred_at": datetime(2026, 8, 8)}
        )


def test_writer_is_append_only_and_uses_caller_transaction(session: Session) -> None:
    organization_a, _, actor_a, _ = _seed(session)
    writer = SqlAlchemyAuditRepository(session)
    assert not hasattr(writer, "update")
    assert not hasattr(writer, "delete")
    writer.append(_draft(organization_a, actor_a))
    assert session.scalar(select(func.count(AuditEventModel.id))) == 1
    session.rollback()
    assert session.scalar(select(func.count(AuditEventModel.id))) == 0
    writer.append(_draft(organization_a, actor_a))
    session.commit()
    assert session.scalar(select(func.count(AuditEventModel.id))) == 1


def test_query_is_tenant_scoped_filtered_and_keyset_stable(session: Session) -> None:
    organization_a, organization_b, actor_a, actor_b = _seed(session)
    writer = SqlAlchemyAuditRepository(session)
    ids = [uuid4(), uuid4(), uuid4()]
    for resource_id in ids:
        writer.append(_draft(organization_a, actor_a, resource_id=resource_id))
    writer.append(
        _draft(
            organization_b,
            actor_b,
            action="bot.activated",
            occurred_at=NOW - timedelta(minutes=1),
        )
    )
    session.commit()
    service = _service(session)
    first = service.query(
        organization_a,
        actor_a,
        from_=NOW - timedelta(days=1),
        to=NOW + timedelta(days=1),
        action="bot.deactivated",
        resource_type="bot",
        limit=2,
    )
    assert len(first.items) == 2
    assert first.next_cursor is not None
    assert all(item.actor.user_id == actor_a.id for item in first.items)
    second = service.query(
        organization_a,
        actor_a,
        from_=NOW - timedelta(days=1),
        to=NOW + timedelta(days=1),
        action="bot.deactivated",
        resource_type="bot",
        cursor=first.next_cursor,
        limit=2,
    )
    assert len(second.items) == 1
    assert {item.resource.id for item in first.items + second.items} == set(ids)
    assert not {item.id for item in first.items}.intersection(
        item.id for item in second.items
    )
    combined = first.items + second.items
    assert [item.id for item in combined] == sorted(
        (item.id for item in combined), reverse=True
    )
    filtered = service.query(
        organization_a,
        actor_a,
        actor_user_id=actor_a.id,
        resource_id=ids[0],
        from_=NOW - timedelta(days=1),
        to=NOW + timedelta(days=1),
    )
    assert [item.resource.id for item in filtered.items] == [ids[0]]


def test_query_validation_rbac_and_cursor_integrity(session: Session) -> None:
    organization_a, _, actor_a, _ = _seed(session)
    service = _service(session)
    operator = actor_a.model_copy(update={"role": "operator"})
    viewer = actor_a.model_copy(update={"role": "viewer"})
    with pytest.raises(AuditForbidden):
        service.query(organization_a, operator, now=NOW)
    with pytest.raises(AuditForbidden):
        service.query(organization_a, viewer, now=NOW)
    with pytest.raises(AuditInvalidRange):
        service.query(organization_a, actor_a, from_=NOW, to=NOW)
    with pytest.raises(AuditRangeTooLarge):
        service.query(
            organization_a,
            actor_a,
            from_=NOW - timedelta(days=367),
            to=NOW,
        )
    service.query(
        organization_a,
        actor_a,
        from_=NOW - timedelta(days=366),
        to=NOW,
    )
    with pytest.raises(AuditInvalidFilter):
        service.query(organization_a, actor_a, action="raw.action", now=NOW)
    with pytest.raises(AuditInvalidCursor):
        service.query(organization_a, actor_a, cursor="modified", now=NOW)


def test_rbac_permission_is_admin_owner_and_platform_only() -> None:
    assert "audit.read" in ALL_PERMISSIONS
    assert "audit.read" in ROLE_PERMISSIONS["organization_owner"]
    assert "audit.read" in ROLE_PERMISSIONS["organization_admin"]
    assert "audit.read" in ROLE_PERMISSIONS["platform_admin"]
    assert "audit.read" not in ROLE_PERMISSIONS["operator"]
    assert "audit.read" not in ROLE_PERMISSIONS["viewer"]


def test_api_returns_safe_no_pii_shape_and_denies_operator(session: Session) -> None:
    organization_a, _, actor_a, _ = _seed(session)
    writer = SqlAlchemyAuditRepository(session)
    writer.append(_draft(organization_a, actor_a))
    session.commit()
    actors = {"current": actor_a}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_audit_query_service] = lambda: _service(session)
    app.dependency_overrides[require_authenticated_user] = lambda: actors["current"]
    client = TestClient(app)
    response = client.get(
        f"/organizations/{organization_a}/audit-events",
        params={
            "from": (NOW - timedelta(days=1)).isoformat(),
            "to": (NOW + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["items"]) == 1
    serialized = response.text.lower()
    assert "email" not in serialized
    assert "password" not in serialized
    event_count = session.scalar(select(func.count(AuditEventModel.id)))
    actors["current"] = actor_a.model_copy(update={"role": "operator"})
    denied = client.get(f"/organizations/{organization_a}/audit-events")
    assert denied.status_code == 403
    assert denied.json() == {"detail": {"code": "AUDIT_FORBIDDEN"}}
    assert session.scalar(select(func.count(AuditEventModel.id))) == event_count


def test_system_and_automation_events_have_no_user_identity(session: Session) -> None:
    organization_a, _, actor_a, _ = _seed(session)
    writer = SqlAlchemyAuditRepository(session)
    for actor_type in ("system", "automation"):
        writer.append(
            AuditEventDraft.model_validate(
                {
                    "organization_id": organization_a,
                    "actor_type": actor_type,
                    "action": "organization.created",
                    "resource_type": "organization",
                    "resource_id": organization_a,
                    "metadata": EmptyMetadata(),
                    "occurred_at": NOW,
                }
            )
        )
    session.commit()
    items = (
        _service(session)
        .query(
            organization_a,
            actor_a,
            from_=NOW - timedelta(minutes=1),
            to=NOW + timedelta(minutes=1),
        )
        .items
    )
    assert {item.actor.type for item in items} == {"system", "automation"}
    assert all(item.actor.user_id is None and item.actor.role is None for item in items)
