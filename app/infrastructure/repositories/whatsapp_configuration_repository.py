from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.application.whatsapp_configuration.repository import (
    WhatsAppConfigurationRepository,
)
from app.domain.whatsapp_configuration.contracts import (
    WhatsAppChannelConfigurationStatus,
)
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)


class SqlAlchemyWhatsAppConfigurationRepository(WhatsAppConfigurationRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, configuration: WhatsAppChannelConfigurationModel) -> None:
        self._session.add(configuration)

    def get_scoped(
        self,
        configuration_id: UUID,
        organization_id: UUID,
        bot_id: UUID,
        *,
        for_update: bool = False,
    ) -> WhatsAppChannelConfigurationModel | None:
        stmt = select(WhatsAppChannelConfigurationModel).where(
            WhatsAppChannelConfigurationModel.id == configuration_id,
            WhatsAppChannelConfigurationModel.organization_id == organization_id,
            WhatsAppChannelConfigurationModel.bot_id == bot_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self._session.scalars(stmt).first()

    @staticmethod
    def _filters(
        organization_id: UUID,
        bot_id: UUID,
        status: WhatsAppChannelConfigurationStatus | None,
        phone_number_id: str | None,
        search: str | None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [
            WhatsAppChannelConfigurationModel.organization_id == organization_id,
            WhatsAppChannelConfigurationModel.bot_id == bot_id,
        ]
        if status is not None:
            filters.append(WhatsAppChannelConfigurationModel.status == status)
        if phone_number_id:
            filters.append(
                WhatsAppChannelConfigurationModel.phone_number_id == phone_number_id,
            )
        if search:
            filters.append(
                WhatsAppChannelConfigurationModel.display_name.ilike(
                    f"%{search.strip()}%",
                ),
            )
        return filters

    def list_scoped(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        status: WhatsAppChannelConfigurationStatus | None,
        phone_number_id: str | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> list[WhatsAppChannelConfigurationModel]:
        stmt = (
            select(WhatsAppChannelConfigurationModel)
            .where(
                *self._filters(
                    organization_id,
                    bot_id,
                    status,
                    phone_number_id,
                    search,
                ),
            )
            .order_by(
                WhatsAppChannelConfigurationModel.created_at,
                WhatsAppChannelConfigurationModel.id,
            )
            .offset(offset)
            .limit(limit)
        )
        return list(self._session.scalars(stmt).all())

    def count_scoped(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        status: WhatsAppChannelConfigurationStatus | None,
        phone_number_id: str | None,
        search: str | None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(WhatsAppChannelConfigurationModel)
            .where(
                *self._filters(
                    organization_id,
                    bot_id,
                    status,
                    phone_number_id,
                    search,
                ),
            )
        )
        return int(self._session.execute(stmt).scalar_one())

    def resolve_active_by_phone_number_id(
        self,
        phone_number_id: str,
    ) -> WhatsAppChannelConfigurationModel | None:
        stmt = select(WhatsAppChannelConfigurationModel).where(
            WhatsAppChannelConfigurationModel.phone_number_id == phone_number_id,
            WhatsAppChannelConfigurationModel.status == "active",
            WhatsAppChannelConfigurationModel.webhook_enabled.is_(True),
        )
        return self._session.scalars(stmt).one_or_none()

    def get_active_by_public_webhook_id(
        self,
        public_webhook_id: UUID,
    ) -> WhatsAppChannelConfigurationModel | None:
        stmt = select(WhatsAppChannelConfigurationModel).where(
            WhatsAppChannelConfigurationModel.public_webhook_id == public_webhook_id,
            WhatsAppChannelConfigurationModel.status == "active",
            WhatsAppChannelConfigurationModel.webhook_enabled.is_(True),
        )
        return self._session.scalars(stmt).one_or_none()

    def delete(self, configuration: WhatsAppChannelConfigurationModel) -> None:
        self._session.delete(configuration)


class InMemoryWhatsAppConfigurationRepository(WhatsAppConfigurationRepository):
    def __init__(self) -> None:
        self.configurations: dict[UUID, WhatsAppChannelConfigurationModel] = {}

    def add(self, configuration: WhatsAppChannelConfigurationModel) -> None:
        self.configurations[configuration.id] = configuration

    def get_scoped(
        self,
        configuration_id: UUID,
        organization_id: UUID,
        bot_id: UUID,
        *,
        for_update: bool = False,
    ) -> WhatsAppChannelConfigurationModel | None:
        del for_update
        configuration = self.configurations.get(configuration_id)
        if (
            configuration is None
            or configuration.organization_id != organization_id
            or configuration.bot_id != bot_id
        ):
            return None
        return configuration

    @staticmethod
    def _matches(
        configuration: WhatsAppChannelConfigurationModel,
        organization_id: UUID,
        bot_id: UUID,
        status: WhatsAppChannelConfigurationStatus | None,
        phone_number_id: str | None,
        search: str | None,
    ) -> bool:
        if (
            configuration.organization_id != organization_id
            or configuration.bot_id != bot_id
        ):
            return False
        if status is not None and configuration.status != status:
            return False
        if phone_number_id and configuration.phone_number_id != phone_number_id:
            return False
        return not search or search.lower() in configuration.display_name.lower()

    def list_scoped(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        status: WhatsAppChannelConfigurationStatus | None,
        phone_number_id: str | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> list[WhatsAppChannelConfigurationModel]:
        matches = [
            configuration
            for configuration in self.configurations.values()
            if self._matches(
                configuration,
                organization_id,
                bot_id,
                status,
                phone_number_id,
                search,
            )
        ]
        matches.sort(key=lambda item: (item.created_at, item.id))
        return matches[offset : offset + limit]

    def count_scoped(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        status: WhatsAppChannelConfigurationStatus | None,
        phone_number_id: str | None,
        search: str | None,
    ) -> int:
        return sum(
            self._matches(
                configuration,
                organization_id,
                bot_id,
                status,
                phone_number_id,
                search,
            )
            for configuration in self.configurations.values()
        )

    def resolve_active_by_phone_number_id(
        self,
        phone_number_id: str,
    ) -> WhatsAppChannelConfigurationModel | None:
        matches = [
            configuration
            for configuration in self.configurations.values()
            if configuration.phone_number_id == phone_number_id
            and configuration.status == "active"
            and configuration.webhook_enabled
        ]
        if len(matches) > 1:
            raise ValueError("ambiguous WhatsApp channel configuration")
        return matches[0] if matches else None

    def get_active_by_public_webhook_id(
        self,
        public_webhook_id: UUID,
    ) -> WhatsAppChannelConfigurationModel | None:
        matches = [
            configuration
            for configuration in self.configurations.values()
            if configuration.public_webhook_id == public_webhook_id
            and configuration.status == "active"
            and configuration.webhook_enabled
        ]
        if len(matches) > 1:
            raise ValueError("ambiguous WhatsApp webhook configuration")
        return matches[0] if matches else None

    def delete(self, configuration: WhatsAppChannelConfigurationModel) -> None:
        self.configurations.pop(configuration.id, None)
