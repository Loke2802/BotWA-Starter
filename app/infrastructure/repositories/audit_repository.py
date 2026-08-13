from datetime import UTC, datetime
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import Row, and_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.application.audit.metrics import AuditMetricsRegistry, audit_metrics
from app.domain.access.contracts import Role
from app.domain.audit.contracts import (
    AUDIT_METADATA_ADAPTER,
    AuditAction,
    AuditActor,
    AuditActorType,
    AuditCursor,
    AuditEventDraft,
    AuditEventResponse,
    AuditQuery,
    AuditResource,
    AuditResourceType,
    AuditResult,
)
from app.domain.audit.errors import AuditUnavailable, AuditWriteError
from app.infrastructure.models.audit import AuditEventModel

ACTOR_TYPE_ADAPTER: TypeAdapter[AuditActorType] = TypeAdapter(AuditActorType)
ROLE_ADAPTER: TypeAdapter[Role] = TypeAdapter(Role)
ACTION_ADAPTER: TypeAdapter[AuditAction] = TypeAdapter(AuditAction)
RESOURCE_TYPE_ADAPTER: TypeAdapter[AuditResourceType] = TypeAdapter(AuditResourceType)
RESULT_ADAPTER: TypeAdapter[AuditResult] = TypeAdapter(AuditResult)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class SqlAlchemyAuditRepository:
    """Append/read repository bound to the application service transaction."""

    def __init__(
        self, session: Session, *, metrics: AuditMetricsRegistry | None = None
    ) -> None:
        self.session = session
        self.metrics = metrics or audit_metrics

    def append(self, draft: AuditEventDraft) -> None:
        try:
            self.session.add(
                AuditEventModel(
                    organization_id=draft.organization_id,
                    actor_type=draft.actor_type,
                    actor_user_id=draft.actor_user_id,
                    actor_role=draft.actor_role,
                    action=draft.action,
                    resource_type=draft.resource_type,
                    resource_id=draft.resource_id,
                    result=draft.result,
                    metadata_data=draft.metadata.model_dump(mode="json"),
                    correlation_id=draft.correlation_id,
                    occurred_at=draft.occurred_at,
                    created_at=datetime.now(UTC),
                )
            )
            self.metrics.record(
                "audit_append_attempts_total",
                operation="append",
                result="accepted_by_unit_of_work",
            )
        except SQLAlchemyError as exc:
            self.session.rollback()
            self.metrics.record(
                "audit_append_attempts_total",
                operation="append",
                result="rejected_by_unit_of_work",
            )
            raise AuditWriteError("audit event could not be appended") from exc

    def page(
        self, query: AuditQuery
    ) -> tuple[list[AuditEventResponse], AuditCursor | None]:
        model = AuditEventModel
        filters = [
            model.organization_id == query.organization_id,
            model.occurred_at >= query.from_,
            model.occurred_at < query.to,
        ]
        if query.actor_user_id is not None:
            filters.append(model.actor_user_id == query.actor_user_id)
        if query.action is not None:
            filters.append(model.action == query.action)
        if query.resource_type is not None:
            filters.append(model.resource_type == query.resource_type)
        if query.resource_id is not None:
            filters.append(model.resource_id == query.resource_id)
        if query.cursor is not None:
            filters.append(
                or_(
                    model.occurred_at < query.cursor.occurred_at,
                    and_(
                        model.occurred_at == query.cursor.occurred_at,
                        model.id < query.cursor.id,
                    ),
                )
            )
        statement = (
            select(
                model.id,
                model.actor_type,
                model.actor_user_id,
                model.actor_role,
                model.action,
                model.resource_type,
                model.resource_id,
                model.result,
                model.metadata_data,
                model.correlation_id,
                model.occurred_at,
            )
            .where(*filters)
            .order_by(model.occurred_at.desc(), model.id.desc())
            .limit(query.limit + 1)
        )
        try:
            rows = self.session.execute(statement).all()
            has_next = len(rows) > query.limit
            page_rows = rows[: query.limit]
            items = [self._response(row) for row in page_rows]
            next_cursor = None
            if has_next and page_rows:
                last = page_rows[-1]
                next_cursor = AuditCursor(
                    occurred_at=_aware(last.occurred_at), id=last.id
                )
            return items, next_cursor
        except (SQLAlchemyError, ValidationError, TypeError, ValueError) as exc:
            raise AuditUnavailable("audit query failed") from exc

    @staticmethod
    def _response(
        row: Row[
            tuple[
                UUID,
                str,
                UUID | None,
                str | None,
                str,
                str,
                UUID | None,
                str,
                dict[str, object],
                UUID | None,
                datetime,
            ]
        ],
    ) -> AuditEventResponse:
        (
            event_id,
            actor_type_value,
            actor_user_id,
            actor_role_value,
            action_value,
            resource_type_value,
            resource_id,
            result_value,
            metadata_data,
            correlation_id,
            occurred_at,
        ) = row
        actor_type = ACTOR_TYPE_ADAPTER.validate_python(actor_type_value)
        actor_role = (
            ROLE_ADAPTER.validate_python(actor_role_value)
            if actor_role_value is not None
            else None
        )
        action = ACTION_ADAPTER.validate_python(action_value)
        resource_type = RESOURCE_TYPE_ADAPTER.validate_python(resource_type_value)
        result = RESULT_ADAPTER.validate_python(result_value)
        return AuditEventResponse(
            id=event_id,
            occurred_at=_aware(occurred_at),
            actor=AuditActor(
                type=actor_type,
                user_id=actor_user_id,
                role=actor_role,
            ),
            action=action,
            resource=AuditResource(
                type=resource_type,
                id=resource_id,
            ),
            result=result,
            metadata=AUDIT_METADATA_ADAPTER.validate_python(metadata_data),
            correlation_id=correlation_id,
        )
