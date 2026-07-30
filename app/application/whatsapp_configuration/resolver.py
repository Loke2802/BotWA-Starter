from app.application.channel.resolver import (
    ChannelResolutionError,
    ChannelResolver,
)
from app.application.whatsapp_configuration.repository import (
    WhatsAppConfigurationRepository,
)
from app.domain.channel.contracts import ResolvedChannelContext


class WhatsAppChannelResolver(ChannelResolver):
    def __init__(self, repository: WhatsAppConfigurationRepository) -> None:
        self._repository = repository

    def resolve(self, external_channel_id: str) -> ResolvedChannelContext:
        phone_number_id = external_channel_id.strip()
        if not phone_number_id:
            raise ChannelResolutionError("WhatsApp channel was not resolved")
        try:
            configuration = self._repository.resolve_active_by_phone_number_id(
                phone_number_id,
            )
        except ValueError as exc:
            raise ChannelResolutionError(
                "WhatsApp channel configuration is ambiguous",
            ) from exc
        if configuration is None:
            raise ChannelResolutionError("WhatsApp channel was not resolved")
        return ResolvedChannelContext(
            channel_type="whatsapp",
            organization_id=configuration.organization_id,
            bot_id=configuration.bot_id,
            channel_configuration_id=configuration.id,
            external_channel_id=configuration.phone_number_id,
        )
