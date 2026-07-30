from abc import ABC, abstractmethod

from app.domain.channel.contracts import ResolvedChannelContext


class ChannelResolutionError(ValueError):
    pass


class ChannelResolver(ABC):
    @abstractmethod
    def resolve(self, external_channel_id: str) -> ResolvedChannelContext: ...
