from abc import ABC, abstractmethod

from app.domain.conversation.contracts import ChannelResponse
from app.domain.conversation.response import BusinessResponse


class ChannelAdapter(ABC):
    @abstractmethod
    def adapt(self, response: BusinessResponse) -> ChannelResponse: ...


class HttpChannelAdapter(ChannelAdapter):
    def adapt(self, response: BusinessResponse) -> ChannelResponse:
        return ChannelResponse(
            status=response.status,
            message=response.message,
        )
