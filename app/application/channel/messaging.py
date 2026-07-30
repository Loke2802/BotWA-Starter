from abc import ABC, abstractmethod

from app.domain.channel.contracts import (
    ChannelDeliveryResult,
    InboundChannelMessage,
    OutboundChannelMessage,
    ResolvedChannelContext,
)


class ChannelMessageHandler(ABC):
    @abstractmethod
    def handle(self, message: InboundChannelMessage) -> OutboundChannelMessage: ...


class ChannelMessageSender(ABC):
    @abstractmethod
    async def send(
        self,
        message: OutboundChannelMessage,
        context: ResolvedChannelContext,
    ) -> ChannelDeliveryResult: ...
