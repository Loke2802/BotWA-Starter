from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.integration_management import (
    IntegrationConnectionModel,
    IntegrationCredentialModel,
    IntegrationHealthCheckModel,
    IntegrationOAuthStateModel,
)


class IntegrationManagementRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_connection(
        self, connection: IntegrationConnectionModel
    ) -> IntegrationConnectionModel:
        self.session.add(connection)
        self.session.flush()
        return connection

    def connection(
        self,
        organization_id: UUID,
        integration_id: UUID,
        *,
        lock: bool = False,
    ) -> IntegrationConnectionModel | None:
        stmt = select(IntegrationConnectionModel).where(
            IntegrationConnectionModel.organization_id == organization_id,
            IntegrationConnectionModel.id == integration_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return self.session.scalars(stmt).one_or_none()

    def connections(
        self,
        organization_id: UUID,
        *,
        status: str | None,
        provider: str | None,
        bot_id: UUID | None,
        offset: int,
        limit: int,
    ) -> tuple[list[IntegrationConnectionModel], int]:
        filters = [IntegrationConnectionModel.organization_id == organization_id]
        for column, value in (
            (IntegrationConnectionModel.status, status),
            (IntegrationConnectionModel.provider, provider),
            (IntegrationConnectionModel.bot_id, bot_id),
        ):
            if value is not None:
                filters.append(column == value)
        query = (
            select(IntegrationConnectionModel)
            .where(*filters)
            .order_by(
                IntegrationConnectionModel.created_at.desc(),
                IntegrationConnectionModel.id,
            )
            .offset(offset)
            .limit(limit)
        )
        total_query = (
            select(func.count()).select_from(IntegrationConnectionModel).where(*filters)
        )
        return list(self.session.scalars(query)), int(
            self.session.scalar(total_query) or 0
        )

    def bot_belongs_to(self, organization_id: UUID, bot_id: UUID) -> bool:
        return (
            self.session.scalar(
                select(BotModel.id).where(
                    BotModel.id == bot_id,
                    BotModel.organization_id == organization_id,
                )
            )
            is not None
        )

    def credential(
        self,
        organization_id: UUID,
        integration_id: UUID,
        *,
        lock: bool = False,
    ) -> IntegrationCredentialModel | None:
        stmt = select(IntegrationCredentialModel).where(
            IntegrationCredentialModel.organization_id == organization_id,
            IntegrationCredentialModel.integration_connection_id == integration_id,
        )
        if lock:
            stmt = stmt.with_for_update()
        return self.session.scalars(stmt).one_or_none()

    def health_checks(
        self,
        organization_id: UUID,
        integration_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[IntegrationHealthCheckModel], int]:
        filters = (
            IntegrationHealthCheckModel.organization_id == organization_id,
            IntegrationHealthCheckModel.integration_connection_id == integration_id,
        )
        query = (
            select(IntegrationHealthCheckModel)
            .where(*filters)
            .order_by(
                IntegrationHealthCheckModel.checked_at.desc(),
                IntegrationHealthCheckModel.id,
            )
            .offset(offset)
            .limit(limit)
        )
        total_query = (
            select(func.count())
            .select_from(IntegrationHealthCheckModel)
            .where(*filters)
        )
        return list(self.session.scalars(query)), int(
            self.session.scalar(total_query) or 0
        )

    def oauth_state_by_nonce(
        self, nonce_hash: str, *, lock: bool = False
    ) -> IntegrationOAuthStateModel | None:
        stmt = select(IntegrationOAuthStateModel).where(
            IntegrationOAuthStateModel.nonce_hash == nonce_hash
        )
        if lock:
            stmt = stmt.with_for_update()
        return self.session.scalars(stmt).one_or_none()
