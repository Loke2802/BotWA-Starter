from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.audit.writer import append_non_user_audit
from app.application.conversation_management.repository import (
    ConversationManagementRepository,
    ConversationMessageManagementRepository,
)
from app.domain.audit.contracts import StatusTransitionMetadata
from app.domain.audit.ports import AuditWriter
from app.infrastructure.models.analytics import ConversationManagementEventModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.message import MessageModel


class SqlAlchemyConversationManagementRepository(ConversationManagementRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_or_create(
        self, conversation: ConversationModel
    ) -> tuple[ConversationModel, bool]:
        existing = self._get_identity(conversation)
        if existing is not None:
            return existing, False
        try:
            self._session.add(conversation)
            self._session.flush()
            return conversation, True
        except IntegrityError:
            self._session.rollback()
            existing = self._get_identity(conversation)
            if existing is None:
                raise
            return existing, False

    def get_scoped(
        self, conversation_id: UUID, organization_id: UUID
    ) -> ConversationModel | None:
        stmt = select(ConversationModel).where(
            ConversationModel.id == conversation_id,
            ConversationModel.organization_id == organization_id,
            ConversationModel.management_status.is_not(None),
        )
        return self._session.scalars(stmt).one_or_none()

    def list_scoped(
        self,
        organization_id: UUID,
        *,
        bot_id: UUID | None,
        channel_type: str | None,
        management_status: str | None,
        external_customer_id: str | None,
        has_inbound: bool | None,
        has_outbound: bool | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ConversationModel], int]:
        filters = [
            ConversationModel.organization_id == organization_id,
            ConversationModel.management_status.is_not(None),
        ]
        if bot_id is not None:
            filters.append(ConversationModel.bot_id == bot_id)
        if channel_type is not None:
            filters.append(ConversationModel.channel == channel_type)
        if management_status is not None:
            filters.append(ConversationModel.management_status == management_status)
        if external_customer_id is not None:
            filters.append(
                ConversationModel.external_customer_id == external_customer_id
            )
        if has_inbound is True:
            filters.append(ConversationModel.inbound_message_count > 0)
        if has_inbound is False:
            filters.append(ConversationModel.inbound_message_count == 0)
        if has_outbound is True:
            filters.append(ConversationModel.outbound_message_count > 0)
        if has_outbound is False:
            filters.append(ConversationModel.outbound_message_count == 0)
        stmt = (
            select(ConversationModel)
            .where(*filters)
            .order_by(ConversationModel.last_message_at.desc(), ConversationModel.id)
            .offset(offset)
            .limit(limit)
        )
        total_stmt = select(func.count()).select_from(ConversationModel).where(*filters)
        return list(self._session.scalars(stmt).all()), int(
            self._session.execute(total_stmt).scalar_one()
        )

    def transition(
        self, conversation: ConversationModel, target: str, occurred_at: datetime
    ) -> None:
        conversation.management_status = target
        conversation.closed_at = occurred_at if target == "closed" else None

    def list_by_contact(
        self,
        contact_id: UUID,
        organization_id: UUID,
        *,
        offset: int,
        limit: int,
    ) -> tuple[list[ConversationModel], int]:
        filters = [
            ConversationModel.contact_id == contact_id,
            ConversationModel.organization_id == organization_id,
            ConversationModel.management_status.is_not(None),
        ]
        stmt = (
            select(ConversationModel)
            .where(*filters)
            .order_by(ConversationModel.last_message_at.desc(), ConversationModel.id)
            .offset(offset)
            .limit(limit)
        )
        total_stmt = select(func.count()).select_from(ConversationModel).where(*filters)
        return list(self._session.scalars(stmt).all()), int(
            self._session.execute(total_stmt).scalar_one()
        )

    def _get_identity(
        self, conversation: ConversationModel
    ) -> ConversationModel | None:
        stmt = select(ConversationModel).where(
            ConversationModel.organization_id == conversation.organization_id,
            ConversationModel.bot_id == conversation.bot_id,
            ConversationModel.channel == conversation.channel,
            ConversationModel.external_customer_id == conversation.external_customer_id,
        )
        return self._session.scalars(stmt).one_or_none()


class SqlAlchemyConversationMessageManagementRepository(
    ConversationMessageManagementRepository
):
    def __init__(self, session: Session, audit_writer: AuditWriter) -> None:
        self._session = session
        self._audit_writer = audit_writer

    def create_once(self, message: MessageModel) -> tuple[MessageModel, bool]:
        existing = self._existing(message)
        if existing is not None:
            return existing, False
        try:
            self._session.add(message)
            self._session.flush()
        except IntegrityError:
            self._session.rollback()
            existing = self._existing(message)
            if existing is None:
                raise
            return existing, False
        conversation = self._session.scalars(
            select(ConversationModel)
            .where(ConversationModel.id == message.conversation_id)
            .with_for_update()
        ).one()
        conversation.message_count += 1
        conversation.last_message_at = message.occurred_at
        if message.direction == "inbound":
            conversation.inbound_message_count += 1
            conversation.last_inbound_at = message.occurred_at
            if conversation.management_status == "closed":
                # This is the management transition time, not the provider message time;
                # delayed inbound delivery must not backdate lifecycle history.
                occurred_at = datetime.now(UTC)
                if conversation.organization_id is None or conversation.bot_id is None:
                    raise ValueError("managed conversation tenant identity is required")
                self._session.add(
                    ConversationManagementEventModel(
                        organization_id=conversation.organization_id,
                        conversation_id=conversation.id,
                        bot_id=conversation.bot_id,
                        from_status="closed",
                        to_status="open",
                        occurred_at=occurred_at,
                        actor_type="system",
                        correlation_id=message.inbound_receipt_id,
                    )
                )
                append_non_user_audit(
                    self._audit_writer,
                    organization_id=conversation.organization_id,
                    actor_type="system",
                    action="conversation.reopened",
                    resource_type="conversation",
                    resource_id=conversation.id,
                    metadata=StatusTransitionMetadata(
                        from_status="closed", to_status="open"
                    ),
                    correlation_id=message.inbound_receipt_id,
                    occurred_at=occurred_at,
                )
                conversation.management_status = "open"
                conversation.closed_at = None
        else:
            conversation.outbound_message_count += 1
            conversation.last_outbound_at = message.occurred_at
        return message, True

    def list_scoped(
        self, conversation_id: UUID, organization_id: UUID, *, offset: int, limit: int
    ) -> tuple[list[MessageModel], int]:
        filters = [
            MessageModel.conversation_id == conversation_id,
            MessageModel.organization_id == organization_id,
            MessageModel.direction.is_not(None),
        ]
        stmt = (
            select(MessageModel)
            .where(*filters)
            .order_by(MessageModel.occurred_at, MessageModel.id)
            .offset(offset)
            .limit(limit)
        )
        total_stmt = select(func.count()).select_from(MessageModel).where(*filters)
        return list(self._session.scalars(stmt).all()), int(
            self._session.execute(total_stmt).scalar_one()
        )

    def sync_outbound_attempt(
        self, outbound_attempt_id: UUID, status: str, provider_message_id: str | None
    ) -> bool:
        stmt = (
            select(MessageModel)
            .where(MessageModel.outbound_attempt_id == outbound_attempt_id)
            .with_for_update()
        )
        message = self._session.scalars(stmt).one_or_none()
        if message is None:
            return False
        message.delivery_status = status
        message.provider_message_id = provider_message_id
        return True

    def _existing(self, message: MessageModel) -> MessageModel | None:
        if message.direction == "inbound" and message.external_message_id is not None:
            stmt = select(MessageModel).where(
                MessageModel.direction == "inbound",
                MessageModel.channel_type == message.channel_type,
                MessageModel.external_message_id == message.external_message_id,
            )
            return self._session.scalars(stmt).one_or_none()
        if message.direction == "outbound" and message.outbound_attempt_id is not None:
            stmt = select(MessageModel).where(
                MessageModel.outbound_attempt_id == message.outbound_attempt_id
            )
            return self._session.scalars(stmt).one_or_none()
        return None
