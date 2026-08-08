from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.dashboard.contracts import (
    DashboardAutomationSummary,
    DashboardBotSummary,
    DashboardContactSummary,
    DashboardConversationSummary,
    DashboardHandoffSummary,
    DashboardIntegrationSummary,
)
from app.domain.dashboard.errors import DashboardPersistenceError
from app.domain.dashboard.ports import (
    DashboardAggregate,
    DashboardHandoffAggregate,
    DashboardScope,
)
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.integration_management import IntegrationConnectionModel
from app.infrastructure.models.managed_automation import (
    ManagedAutomationEventReceiptModel,
    ManagedAutomationExecutionModel,
)
from app.infrastructure.models.organization import OrganizationModel


def _count(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    raise DashboardPersistenceError("dashboard aggregate returned a non-integer count")


class SqlAlchemyDashboardRepository:
    """Read-only SQL aggregate repository. It never hydrates domain collections."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def scope(
        self, organization_id: UUID, bot_id: UUID | None
    ) -> DashboardScope | None:
        try:
            settings = self.session.scalar(
                select(OrganizationModel.settings).where(
                    OrganizationModel.id == organization_id
                )
            )
            if settings is None:
                return None
            timezone = "America/Lima"
            configured_timezone = settings.get("timezone")
            if isinstance(configured_timezone, str):
                timezone = configured_timezone
            if bot_id is not None:
                bot_timezone = self.session.scalar(
                    select(BotModel.timezone).where(
                        BotModel.organization_id == organization_id,
                        BotModel.id == bot_id,
                    )
                )
                if bot_timezone is None:
                    return None
                timezone = bot_timezone
            return DashboardScope(organization_id, bot_id, timezone)
        except SQLAlchemyError as exc:
            raise DashboardPersistenceError("dashboard scope query failed") from exc

    def aggregate(
        self,
        scope: DashboardScope,
        period_start: datetime,
        period_end: datetime,
    ) -> DashboardAggregate:
        try:
            return DashboardAggregate(
                bots=self._bots(scope),
                conversations=self._conversations(scope, period_start, period_end),
                handoffs=self._handoffs(scope, period_start, period_end),
                automations=self._automations(scope, period_start, period_end),
                integrations=self._integrations(scope),
                contacts=self._contacts(scope, period_start, period_end),
            )
        except SQLAlchemyError as exc:
            raise DashboardPersistenceError("dashboard aggregate query failed") from exc

    def _bots(self, scope: DashboardScope) -> DashboardBotSummary:
        filters = [BotModel.organization_id == scope.organization_id]
        if scope.bot_id is not None:
            filters.append(BotModel.id == scope.bot_id)
        row = self.session.execute(
            select(
                func.count().label("total"),
                func.count().filter(BotModel.status == "active").label("active"),
                func.count().filter(BotModel.status == "inactive").label("inactive"),
            ).where(*filters)
        ).one()
        return DashboardBotSummary(
            scope="bot" if scope.bot_id else "organization",
            total=_count(row.total),
            active=_count(row.active),
            inactive=_count(row.inactive),
        )

    def _conversations(
        self,
        scope: DashboardScope,
        period_start: datetime,
        period_end: datetime,
    ) -> DashboardConversationSummary:
        filters = [
            ConversationModel.organization_id == scope.organization_id,
            ConversationModel.management_status.in_(("open", "closed", "archived")),
        ]
        if scope.bot_id is not None:
            filters.append(ConversationModel.bot_id == scope.bot_id)
        row = self.session.execute(
            select(
                func.count().label("total"),
                func.count()
                .filter(ConversationModel.management_status == "open")
                .label("open"),
                func.count()
                .filter(ConversationModel.management_status == "closed")
                .label("closed"),
                func.count()
                .filter(ConversationModel.management_status == "archived")
                .label("archived"),
                func.count()
                .filter(
                    ConversationModel.started_at >= period_start,
                    ConversationModel.started_at < period_end,
                )
                .label("started_in_period"),
            ).where(*filters)
        ).one()
        return DashboardConversationSummary(
            scope="bot" if scope.bot_id else "organization",
            total=_count(row.total),
            open=_count(row.open),
            closed=_count(row.closed),
            archived=_count(row.archived),
            started_in_period=_count(row.started_in_period),
        )

    def _handoffs(
        self,
        scope: DashboardScope,
        period_start: datetime,
        period_end: datetime,
    ) -> DashboardHandoffAggregate:
        filters = [HandoffSessionModel.organization_id == scope.organization_id]
        if scope.bot_id is not None:
            filters.append(HandoffSessionModel.bot_id == scope.bot_id)
        active_states = ("waiting_human", "human_active")
        row = self.session.execute(
            select(
                func.count()
                .filter(HandoffSessionModel.status == "human_active")
                .label("active"),
                func.count()
                .filter(HandoffSessionModel.status == "waiting_human")
                .label("pending"),
                func.count()
                .filter(
                    HandoffSessionModel.created_at >= period_start,
                    HandoffSessionModel.created_at < period_end,
                )
                .label("created_in_period"),
                func.count()
                .filter(
                    HandoffSessionModel.resolved_at >= period_start,
                    HandoffSessionModel.resolved_at < period_end,
                )
                .label("completed_in_period"),
                func.min(
                    func.coalesce(
                        HandoffSessionModel.requested_at,
                        HandoffSessionModel.created_at,
                    )
                )
                .filter(HandoffSessionModel.status.in_(active_states))
                .label("oldest_active_since"),
            ).where(*filters)
        ).one()
        summary = DashboardHandoffSummary(
            scope="bot" if scope.bot_id else "organization",
            active=_count(row.active),
            pending=_count(row.pending),
            created_in_period=_count(row.created_in_period),
            completed_in_period=_count(row.completed_in_period),
        )
        return DashboardHandoffAggregate(summary, row.oldest_active_since)

    def _automations(
        self,
        scope: DashboardScope,
        period_start: datetime,
        period_end: datetime,
    ) -> DashboardAutomationSummary:
        filters = [
            ManagedAutomationExecutionModel.organization_id == scope.organization_id,
            ManagedAutomationExecutionModel.created_at >= period_start,
            ManagedAutomationExecutionModel.created_at < period_end,
        ]
        if scope.bot_id is not None:
            filters.append(ManagedAutomationEventReceiptModel.bot_id == scope.bot_id)
        row = self.session.execute(
            select(
                func.count().label("total"),
                *(
                    func.count()
                    .filter(ManagedAutomationExecutionModel.status == state)
                    .label(state)
                    for state in (
                        "pending",
                        "running",
                        "succeeded",
                        "failed",
                        "skipped",
                        "cancelled",
                    )
                ),
            )
            .select_from(ManagedAutomationExecutionModel)
            .join(
                ManagedAutomationEventReceiptModel,
                ManagedAutomationEventReceiptModel.id
                == ManagedAutomationExecutionModel.event_receipt_id,
            )
            .where(*filters)
        ).one()
        return DashboardAutomationSummary(
            scope="bot" if scope.bot_id else "organization",
            total=_count(row.total),
            pending=_count(row.pending),
            running=_count(row.running),
            succeeded=_count(row.succeeded),
            failed=_count(row.failed),
            skipped=_count(row.skipped),
            cancelled=_count(row.cancelled),
        )

    def _integrations(self, scope: DashboardScope) -> DashboardIntegrationSummary:
        filters = [IntegrationConnectionModel.organization_id == scope.organization_id]
        if scope.bot_id is not None:
            filters.append(IntegrationConnectionModel.bot_id == scope.bot_id)
        row = self.session.execute(
            select(
                func.count().label("total"),
                func.count()
                .filter(IntegrationConnectionModel.status == "active")
                .label("active"),
                *(
                    func.count()
                    .filter(IntegrationConnectionModel.health_status == state)
                    .label(state)
                    for state in (
                        "healthy",
                        "degraded",
                        "unreachable",
                        "auth_error",
                        "unknown",
                    )
                ),
            ).where(*filters)
        ).one()
        return DashboardIntegrationSummary(
            scope="bot" if scope.bot_id else "organization",
            total=_count(row.total),
            active=_count(row.active),
            healthy=_count(row.healthy),
            degraded=_count(row.degraded),
            unreachable=_count(row.unreachable),
            auth_error=_count(row.auth_error),
            unknown=_count(row.unknown),
        )

    def _contacts(
        self,
        scope: DashboardScope,
        period_start: datetime,
        period_end: datetime,
    ) -> DashboardContactSummary:
        row = self.session.execute(
            select(
                func.count().label("total"),
                func.count()
                .filter(
                    ContactModel.created_at >= period_start,
                    ContactModel.created_at < period_end,
                )
                .label("created_in_period"),
            ).where(ContactModel.organization_id == scope.organization_id)
        ).one()
        return DashboardContactSummary(
            total=_count(row.total),
            created_in_period=_count(row.created_in_period),
        )
