from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from app.domain.whatsapp_live.contracts import WhatsAppProviderStatus
from app.infrastructure.models.whatsapp_message_transport import (
    InboundMessageReceiptModel,
    OutboundMessageAttemptModel,
)


class InboundMessageReceiptRepository(ABC):
    @abstractmethod
    def create_or_get(
        self,
        receipt: InboundMessageReceiptModel,
    ) -> tuple[InboundMessageReceiptModel, bool]: ...

    @abstractmethod
    def acquire_for_processing(self, receipt_id: UUID) -> bool: ...

    @abstractmethod
    def mark_processed(self, receipt_id: UUID, processed_at: datetime) -> None: ...

    @abstractmethod
    def mark_failed(self, receipt_id: UUID, error_code: str) -> None: ...

    @abstractmethod
    def get_by_external_message_id(
        self,
        channel_type: str,
        external_message_id: str,
    ) -> InboundMessageReceiptModel | None: ...


class OutboundMessageAttemptRepository(ABC):
    @abstractmethod
    def create_pending(self, attempt: OutboundMessageAttemptModel) -> None: ...

    @abstractmethod
    def get(
        self, attempt_id: UUID, *, for_update: bool = False
    ) -> OutboundMessageAttemptModel | None: ...

    @abstractmethod
    def mark_attempt_started(self, attempt_id: UUID) -> OutboundMessageAttemptModel: ...

    @abstractmethod
    def mark_sent(
        self,
        attempt_id: UUID,
        provider_message_id: str,
        sent_at: datetime,
    ) -> None: ...

    @abstractmethod
    def mark_failed(self, attempt_id: UUID, error_code: str) -> None: ...

    @abstractmethod
    def schedule_retry(
        self,
        attempt_id: UUID,
        error_code: str,
        next_attempt_at: datetime,
    ) -> None: ...

    @abstractmethod
    def update_provider_status(
        self,
        provider_message_id: str,
        status: WhatsAppProviderStatus,
        occurred_at: datetime,
        error_code: str | None,
    ) -> bool: ...

    @abstractmethod
    def get_by_provider_message_id(
        self,
        provider_message_id: str,
    ) -> OutboundMessageAttemptModel | None: ...
