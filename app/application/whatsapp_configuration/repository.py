from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.whatsapp_configuration.contracts import (
    WhatsAppChannelConfigurationStatus,
)
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)


class WhatsAppConfigurationRepository(ABC):
    @abstractmethod
    def add(self, configuration: WhatsAppChannelConfigurationModel) -> None: ...

    @abstractmethod
    def get_scoped(
        self,
        configuration_id: UUID,
        organization_id: UUID,
        bot_id: UUID,
        *,
        for_update: bool = False,
    ) -> WhatsAppChannelConfigurationModel | None: ...

    @abstractmethod
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
    ) -> list[WhatsAppChannelConfigurationModel]: ...

    @abstractmethod
    def count_scoped(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        status: WhatsAppChannelConfigurationStatus | None,
        phone_number_id: str | None,
        search: str | None,
    ) -> int: ...

    @abstractmethod
    def resolve_active_by_phone_number_id(
        self,
        phone_number_id: str,
    ) -> WhatsAppChannelConfigurationModel | None: ...

    @abstractmethod
    def get_active_by_public_webhook_id(
        self,
        public_webhook_id: UUID,
    ) -> WhatsAppChannelConfigurationModel | None: ...

    @abstractmethod
    def delete(self, configuration: WhatsAppChannelConfigurationModel) -> None: ...
