from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.whatsapp_live.repository import (
    InboundMessageReceiptRepository,
    OutboundMessageAttemptRepository,
)
from app.domain.whatsapp_live.contracts import WhatsAppProviderStatus
from app.infrastructure.models.whatsapp_message_transport import (
    InboundMessageReceiptModel,
    OutboundMessageAttemptModel,
)

_PROVIDER_STATUS_RANK = {
    "pending": 0,
    "sent": 1,
    "delivered": 2,
    "read": 3,
    "failed": 1,
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SqlAlchemyInboundMessageReceiptRepository(
    InboundMessageReceiptRepository,
):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_or_get(
        self,
        receipt: InboundMessageReceiptModel,
    ) -> tuple[InboundMessageReceiptModel, bool]:
        existing = self.get_by_external_message_id(
            receipt.channel_type,
            receipt.external_message_id,
        )
        if existing is not None:
            return existing, False
        try:
            self._session.add(receipt)
            self._session.flush()
            return receipt, True
        except IntegrityError:
            self._session.rollback()
            existing = self.get_by_external_message_id(
                receipt.channel_type,
                receipt.external_message_id,
            )
            if existing is None:
                raise
            return existing, False

    def acquire_for_processing(self, receipt_id: UUID) -> bool:
        stmt = (
            select(InboundMessageReceiptModel)
            .where(InboundMessageReceiptModel.id == receipt_id)
            .with_for_update()
        )
        receipt = self._session.scalars(stmt).one_or_none()
        if receipt is None or receipt.status != "received":
            return False
        receipt.status = "processing"
        receipt.attempt_count = (receipt.attempt_count or 0) + 1
        receipt.last_error_code = None
        return True

    def mark_processed(self, receipt_id: UUID, processed_at: datetime) -> None:
        receipt = self._session.get(InboundMessageReceiptModel, receipt_id)
        if receipt is None:
            raise ValueError("inbound receipt was not found")
        receipt.status = "processed"
        receipt.processed_at = processed_at
        receipt.last_error_code = None

    def mark_failed(self, receipt_id: UUID, error_code: str) -> None:
        receipt = self._session.get(InboundMessageReceiptModel, receipt_id)
        if receipt is None:
            raise ValueError("inbound receipt was not found")
        receipt.status = "failed"
        receipt.last_error_code = error_code

    def get_by_external_message_id(
        self,
        channel_type: str,
        external_message_id: str,
    ) -> InboundMessageReceiptModel | None:
        stmt = select(InboundMessageReceiptModel).where(
            InboundMessageReceiptModel.channel_type == channel_type,
            InboundMessageReceiptModel.external_message_id == external_message_id,
        )
        return self._session.scalars(stmt).one_or_none()


class SqlAlchemyOutboundMessageAttemptRepository(
    OutboundMessageAttemptRepository,
):
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_pending(self, attempt: OutboundMessageAttemptModel) -> None:
        self._session.add(attempt)
        self._session.flush()

    def get(
        self,
        attempt_id: UUID,
        *,
        for_update: bool = False,
    ) -> OutboundMessageAttemptModel | None:
        stmt = select(OutboundMessageAttemptModel).where(
            OutboundMessageAttemptModel.id == attempt_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self._session.scalars(stmt).one_or_none()

    def mark_attempt_started(
        self,
        attempt_id: UUID,
    ) -> OutboundMessageAttemptModel:
        attempt = self.get(attempt_id, for_update=True)
        if attempt is None:
            raise ValueError("outbound attempt was not found")
        attempt.attempt_count = (attempt.attempt_count or 0) + 1
        attempt.next_attempt_at = None
        return attempt

    def mark_sent(
        self,
        attempt_id: UUID,
        provider_message_id: str,
        sent_at: datetime,
    ) -> None:
        attempt = self.get(attempt_id, for_update=True)
        if attempt is None:
            raise ValueError("outbound attempt was not found")
        attempt.status = "sent"
        attempt.provider_message_id = provider_message_id
        attempt.sent_at = sent_at
        attempt.provider_status_updated_at = sent_at
        attempt.last_error_code = None
        attempt.next_attempt_at = None

    def mark_failed(self, attempt_id: UUID, error_code: str) -> None:
        attempt = self.get(attempt_id, for_update=True)
        if attempt is None:
            raise ValueError("outbound attempt was not found")
        attempt.status = "failed"
        attempt.last_error_code = error_code
        attempt.next_attempt_at = None

    def schedule_retry(
        self,
        attempt_id: UUID,
        error_code: str,
        next_attempt_at: datetime,
    ) -> None:
        attempt = self.get(attempt_id, for_update=True)
        if attempt is None:
            raise ValueError("outbound attempt was not found")
        attempt.status = "pending"
        attempt.last_error_code = error_code
        attempt.next_attempt_at = next_attempt_at

    def update_provider_status(
        self,
        provider_message_id: str,
        status: WhatsAppProviderStatus,
        occurred_at: datetime,
        error_code: str | None,
    ) -> bool:
        if status == "unknown":
            return False
        stmt = (
            select(OutboundMessageAttemptModel)
            .where(
                OutboundMessageAttemptModel.provider_message_id == provider_message_id,
            )
            .with_for_update()
        )
        attempt = self._session.scalars(stmt).one_or_none()
        if attempt is None:
            return False
        if attempt.provider_status_updated_at is not None and _utc(occurred_at) < _utc(
            attempt.provider_status_updated_at
        ):
            return False
        if _PROVIDER_STATUS_RANK[status] < _PROVIDER_STATUS_RANK[attempt.status]:
            return False
        attempt.status = status
        attempt.provider_status_updated_at = occurred_at
        attempt.last_error_code = error_code if status == "failed" else None
        return True

    def get_by_provider_message_id(
        self,
        provider_message_id: str,
    ) -> OutboundMessageAttemptModel | None:
        stmt = select(OutboundMessageAttemptModel).where(
            OutboundMessageAttemptModel.provider_message_id == provider_message_id,
        )
        return self._session.scalars(stmt).one_or_none()


class InMemoryInboundMessageReceiptRepository(InboundMessageReceiptRepository):
    def __init__(self) -> None:
        self.receipts: dict[UUID, InboundMessageReceiptModel] = {}
        self.keys: dict[tuple[str, str], UUID] = {}

    def create_or_get(
        self,
        receipt: InboundMessageReceiptModel,
    ) -> tuple[InboundMessageReceiptModel, bool]:
        key = (receipt.channel_type, receipt.external_message_id)
        receipt_id = self.keys.get(key)
        if receipt_id is not None:
            return self.receipts[receipt_id], False
        self.receipts[receipt.id] = receipt
        self.keys[key] = receipt.id
        return receipt, True

    def acquire_for_processing(self, receipt_id: UUID) -> bool:
        receipt = self.receipts.get(receipt_id)
        if receipt is None or receipt.status != "received":
            return False
        receipt.status = "processing"
        receipt.attempt_count = (receipt.attempt_count or 0) + 1
        receipt.last_error_code = None
        return True

    def mark_processed(self, receipt_id: UUID, processed_at: datetime) -> None:
        receipt = self.receipts[receipt_id]
        receipt.status = "processed"
        receipt.processed_at = processed_at
        receipt.last_error_code = None

    def mark_failed(self, receipt_id: UUID, error_code: str) -> None:
        receipt = self.receipts[receipt_id]
        receipt.status = "failed"
        receipt.last_error_code = error_code

    def get_by_external_message_id(
        self,
        channel_type: str,
        external_message_id: str,
    ) -> InboundMessageReceiptModel | None:
        receipt_id = self.keys.get((channel_type, external_message_id))
        return self.receipts.get(receipt_id) if receipt_id is not None else None


class InMemoryOutboundMessageAttemptRepository(
    OutboundMessageAttemptRepository,
):
    def __init__(self) -> None:
        self.attempts: dict[UUID, OutboundMessageAttemptModel] = {}

    def create_pending(self, attempt: OutboundMessageAttemptModel) -> None:
        self.attempts[attempt.id] = attempt

    def get(
        self,
        attempt_id: UUID,
        *,
        for_update: bool = False,
    ) -> OutboundMessageAttemptModel | None:
        del for_update
        return self.attempts.get(attempt_id)

    def mark_attempt_started(
        self,
        attempt_id: UUID,
    ) -> OutboundMessageAttemptModel:
        attempt = self.attempts[attempt_id]
        attempt.attempt_count = (attempt.attempt_count or 0) + 1
        attempt.next_attempt_at = None
        return attempt

    def mark_sent(
        self,
        attempt_id: UUID,
        provider_message_id: str,
        sent_at: datetime,
    ) -> None:
        attempt = self.attempts[attempt_id]
        attempt.status = "sent"
        attempt.provider_message_id = provider_message_id
        attempt.sent_at = sent_at
        attempt.provider_status_updated_at = sent_at
        attempt.last_error_code = None
        attempt.next_attempt_at = None

    def mark_failed(self, attempt_id: UUID, error_code: str) -> None:
        attempt = self.attempts[attempt_id]
        attempt.status = "failed"
        attempt.last_error_code = error_code
        attempt.next_attempt_at = None

    def schedule_retry(
        self,
        attempt_id: UUID,
        error_code: str,
        next_attempt_at: datetime,
    ) -> None:
        attempt = self.attempts[attempt_id]
        attempt.status = "pending"
        attempt.last_error_code = error_code
        attempt.next_attempt_at = next_attempt_at

    def update_provider_status(
        self,
        provider_message_id: str,
        status: WhatsAppProviderStatus,
        occurred_at: datetime,
        error_code: str | None,
    ) -> bool:
        attempt = self.get_by_provider_message_id(provider_message_id)
        if attempt is None or status == "unknown":
            return False
        if attempt.provider_status_updated_at is not None and _utc(occurred_at) < _utc(
            attempt.provider_status_updated_at
        ):
            return False
        if _PROVIDER_STATUS_RANK[status] < _PROVIDER_STATUS_RANK[attempt.status]:
            return False
        attempt.status = status
        attempt.provider_status_updated_at = occurred_at
        attempt.last_error_code = error_code if status == "failed" else None
        return True

    def get_by_provider_message_id(
        self,
        provider_message_id: str,
    ) -> OutboundMessageAttemptModel | None:
        return next(
            (
                attempt
                for attempt in self.attempts.values()
                if attempt.provider_message_id == provider_message_id
            ),
            None,
        )
