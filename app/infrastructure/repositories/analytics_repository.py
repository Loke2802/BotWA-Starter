from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.analytics.contracts import AnalyticsCounts
from app.domain.analytics.errors import AnalyticsPersistenceError
from app.domain.analytics.ports import (
    AnalyticsDailyValue,
    AnalyticsScope,
)
from app.domain.organization.contracts import DEFAULT_ORGANIZATION_TIMEZONE
from app.infrastructure.models.analytics import (
    AnalyticsDailySummaryModel,
    ConversationManagementEventModel,
    HandoffCycleModel,
)
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.managed_automation import (
    ManagedAutomationEventReceiptModel,
    ManagedAutomationExecutionModel,
)
from app.infrastructure.models.organization import OrganizationModel


def _integer(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float, Decimal)):
        return max(0, int(value))
    raise AnalyticsPersistenceError("analytics aggregate returned invalid data")


class SqlAlchemyAnalyticsRepository:
    """Tenant-scoped aggregate SQL repository for the PRD-016 read model."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def scope(
        self, organization_id: UUID, bot_id: UUID | None
    ) -> AnalyticsScope | None:
        try:
            settings = self.session.scalar(
                select(OrganizationModel.settings).where(
                    OrganizationModel.id == organization_id
                )
            )
            if settings is None:
                return None
            timezone = DEFAULT_ORGANIZATION_TIMEZONE
            configured = settings.get("timezone")
            if isinstance(configured, str):
                timezone = configured
            bot_ids = tuple(
                self.session.scalars(
                    select(BotModel.id)
                    .where(BotModel.organization_id == organization_id)
                    .order_by(BotModel.id)
                ).all()
            )
            if bot_id is not None and bot_id not in bot_ids:
                return None
            return AnalyticsScope(organization_id, bot_id, timezone, bot_ids)
        except SQLAlchemyError as exc:
            raise AnalyticsPersistenceError("analytics scope query failed") from exc

    def aggregate_sources(
        self,
        scope: AnalyticsScope,
        local_date: date,
        day_start: datetime,
        day_end: datetime,
        source_watermark_at: datetime,
    ) -> AnalyticsCounts:
        del local_date
        try:
            if scope.bot_id is None:
                contacts = self.session.scalar(
                    select(func.count())
                    .select_from(ContactModel)
                    .where(
                        ContactModel.organization_id == scope.organization_id,
                        ContactModel.created_at >= day_start,
                        ContactModel.created_at < day_end,
                        ContactModel.created_at < source_watermark_at,
                    )
                )
                return self._counts(contacts_created=_integer(contacts))

            conversations_started = self.session.scalar(
                select(func.count())
                .select_from(ConversationModel)
                .where(
                    ConversationModel.organization_id == scope.organization_id,
                    ConversationModel.bot_id == scope.bot_id,
                    ConversationModel.started_at >= day_start,
                    ConversationModel.started_at < day_end,
                    ConversationModel.started_at < source_watermark_at,
                )
            )
            conversations_closed = self.session.scalar(
                select(func.count())
                .select_from(ConversationManagementEventModel)
                .where(
                    ConversationManagementEventModel.organization_id
                    == scope.organization_id,
                    ConversationManagementEventModel.bot_id == scope.bot_id,
                    ConversationManagementEventModel.to_status == "closed",
                    ConversationManagementEventModel.occurred_at >= day_start,
                    ConversationManagementEventModel.occurred_at < day_end,
                    ConversationManagementEventModel.occurred_at < source_watermark_at,
                )
            )
            handoffs_created = self.session.scalar(
                select(func.count())
                .select_from(HandoffCycleModel)
                .where(
                    HandoffCycleModel.organization_id == scope.organization_id,
                    HandoffCycleModel.bot_id == scope.bot_id,
                    HandoffCycleModel.requested_at >= day_start,
                    HandoffCycleModel.requested_at < day_end,
                    HandoffCycleModel.requested_at < source_watermark_at,
                )
            )
            duration = self._duration_expression()
            handoff_row = self.session.execute(
                select(func.count(), func.coalesce(func.sum(duration), 0)).where(
                    HandoffCycleModel.organization_id == scope.organization_id,
                    HandoffCycleModel.bot_id == scope.bot_id,
                    HandoffCycleModel.resolved_at.is_not(None),
                    HandoffCycleModel.resolution_type.in_(
                        ("resolved", "returned_to_bot")
                    ),
                    HandoffCycleModel.resolved_at >= day_start,
                    HandoffCycleModel.resolved_at < day_end,
                    HandoffCycleModel.resolved_at < source_watermark_at,
                )
            ).one()
            created = self.session.scalar(
                select(func.count())
                .select_from(ManagedAutomationExecutionModel)
                .join(
                    ManagedAutomationEventReceiptModel,
                    ManagedAutomationEventReceiptModel.id
                    == ManagedAutomationExecutionModel.event_receipt_id,
                )
                .where(
                    ManagedAutomationExecutionModel.organization_id
                    == scope.organization_id,
                    ManagedAutomationEventReceiptModel.bot_id == scope.bot_id,
                    ManagedAutomationExecutionModel.created_at >= day_start,
                    ManagedAutomationExecutionModel.created_at < day_end,
                    ManagedAutomationExecutionModel.created_at < source_watermark_at,
                )
            )
            outcome_row = self.session.execute(
                select(
                    *(
                        func.count()
                        .filter(ManagedAutomationExecutionModel.status == state)
                        .label(state)
                        for state in ("succeeded", "failed", "skipped", "cancelled")
                    )
                )
                .select_from(ManagedAutomationExecutionModel)
                .join(
                    ManagedAutomationEventReceiptModel,
                    ManagedAutomationEventReceiptModel.id
                    == ManagedAutomationExecutionModel.event_receipt_id,
                )
                .where(
                    ManagedAutomationExecutionModel.organization_id
                    == scope.organization_id,
                    ManagedAutomationEventReceiptModel.bot_id == scope.bot_id,
                    ManagedAutomationExecutionModel.completed_at >= day_start,
                    ManagedAutomationExecutionModel.completed_at < day_end,
                    ManagedAutomationExecutionModel.completed_at < source_watermark_at,
                )
            ).one()
            return self._counts(
                conversations_started=_integer(conversations_started),
                conversations_closed=_integer(conversations_closed),
                handoffs_created=_integer(handoffs_created),
                handoffs_resolved=_integer(handoff_row[0]),
                handoff_resolution_seconds_sum=_integer(handoff_row[1]),
                handoff_resolution_count=_integer(handoff_row[0]),
                automation_executions_created=_integer(created),
                automation_succeeded=_integer(outcome_row.succeeded),
                automation_failed=_integer(outcome_row.failed),
                automation_skipped=_integer(outcome_row.skipped),
                automation_cancelled=_integer(outcome_row.cancelled),
            )
        except SQLAlchemyError as exc:
            raise AnalyticsPersistenceError("analytics source query failed") from exc

    def upsert_day(
        self,
        scope: AnalyticsScope,
        local_date: date,
        counts: AnalyticsCounts,
        source_watermark_at: datetime,
        computed_at: datetime,
    ) -> None:
        values: dict[str, object] = {
            "id": uuid4(),
            "organization_id": scope.organization_id,
            "bot_id": scope.bot_id,
            "local_date": local_date,
            "timezone": scope.timezone,
            **counts.model_dump(),
            "source_watermark_at": source_watermark_at,
            "computed_at": computed_at,
            "created_at": computed_at,
            "updated_at": computed_at,
        }
        mutable = {
            key: value
            for key, value in values.items()
            if key
            not in {"id", "organization_id", "bot_id", "local_date", "created_at"}
        }
        dialect = self.session.get_bind().dialect.name
        try:
            table = AnalyticsDailySummaryModel.__table__
            if dialect == "postgresql":
                pg_stmt = postgresql_insert(AnalyticsDailySummaryModel).values(**values)
                where = (
                    table.c.bot_id.is_(None)
                    if scope.bot_id is None
                    else table.c.bot_id.is_not(None)
                )
                elements = [table.c.organization_id, table.c.local_date]
                if scope.bot_id is not None:
                    elements.insert(1, table.c.bot_id)
                pg_stmt = pg_stmt.on_conflict_do_update(
                    index_elements=elements,
                    index_where=where,
                    set_=mutable,
                )
                self.session.execute(pg_stmt)
            elif dialect == "sqlite":
                sqlite_stmt = sqlite_insert(AnalyticsDailySummaryModel).values(**values)
                where = (
                    table.c.bot_id.is_(None)
                    if scope.bot_id is None
                    else table.c.bot_id.is_not(None)
                )
                elements = [table.c.organization_id, table.c.local_date]
                if scope.bot_id is not None:
                    elements.insert(1, table.c.bot_id)
                self.session.execute(
                    sqlite_stmt.on_conflict_do_update(
                        index_elements=elements,
                        index_where=where,
                        set_=mutable,
                    )
                )
            else:
                row = self.session.scalar(
                    select(AnalyticsDailySummaryModel).where(
                        AnalyticsDailySummaryModel.organization_id
                        == scope.organization_id,
                        AnalyticsDailySummaryModel.bot_id == scope.bot_id,
                        AnalyticsDailySummaryModel.local_date == local_date,
                    )
                )
                if row is None:
                    self.session.add(AnalyticsDailySummaryModel(**values))
                else:
                    for key, value in mutable.items():
                        setattr(row, key, value)
            self.session.flush()
        except SQLAlchemyError as exc:
            raise AnalyticsPersistenceError(
                "analytics projection upsert failed"
            ) from exc

    def daily_values(
        self, scope: AnalyticsScope, from_: date, to: date
    ) -> list[AnalyticsDailyValue]:
        filters = [
            AnalyticsDailySummaryModel.organization_id == scope.organization_id,
            AnalyticsDailySummaryModel.local_date >= from_,
            AnalyticsDailySummaryModel.local_date < to,
        ]
        if scope.bot_id is not None:
            filters.append(
                or_(
                    AnalyticsDailySummaryModel.bot_id == scope.bot_id,
                    AnalyticsDailySummaryModel.bot_id.is_(None),
                )
            )
        try:
            rows = self.session.scalars(
                select(AnalyticsDailySummaryModel)
                .where(*filters)
                .order_by(
                    AnalyticsDailySummaryModel.local_date,
                    AnalyticsDailySummaryModel.bot_id,
                )
            ).all()
            return [self._daily_value(row) for row in rows]
        except SQLAlchemyError as exc:
            raise AnalyticsPersistenceError("analytics read query failed") from exc

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def _duration_expression(self) -> object:
        if self.session.get_bind().dialect.name == "sqlite":
            return func.strftime("%s", HandoffCycleModel.resolved_at) - func.strftime(
                "%s", HandoffCycleModel.requested_at
            )
        return func.extract(
            "epoch", HandoffCycleModel.resolved_at - HandoffCycleModel.requested_at
        )

    @staticmethod
    def _counts(**overrides: int) -> AnalyticsCounts:
        values = {
            "conversations_started": 0,
            "conversations_closed": 0,
            "handoffs_created": 0,
            "handoffs_resolved": 0,
            "handoff_resolution_seconds_sum": 0,
            "handoff_resolution_count": 0,
            "automation_executions_created": 0,
            "automation_succeeded": 0,
            "automation_failed": 0,
            "automation_skipped": 0,
            "automation_cancelled": 0,
            "contacts_created": 0,
        }
        values.update(overrides)
        return AnalyticsCounts(**values)

    @staticmethod
    def _daily_value(row: AnalyticsDailySummaryModel) -> AnalyticsDailyValue:
        return AnalyticsDailyValue(
            local_date=row.local_date,
            bot_id=row.bot_id,
            timezone=row.timezone,
            counts=AnalyticsCounts(
                conversations_started=row.conversations_started,
                conversations_closed=row.conversations_closed,
                handoffs_created=row.handoffs_created,
                handoffs_resolved=row.handoffs_resolved,
                handoff_resolution_seconds_sum=row.handoff_resolution_seconds_sum,
                handoff_resolution_count=row.handoff_resolution_count,
                automation_executions_created=row.automation_executions_created,
                automation_succeeded=row.automation_succeeded,
                automation_failed=row.automation_failed,
                automation_skipped=row.automation_skipped,
                automation_cancelled=row.automation_cancelled,
                contacts_created=row.contacts_created,
            ),
            source_watermark_at=row.source_watermark_at,
            computed_at=row.computed_at,
        )
