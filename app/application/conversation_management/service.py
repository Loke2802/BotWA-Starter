from builtins import list as builtin_list
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.application.audit.writer import append_user_audit
from app.application.conversation_management.repository import (
    ConversationManagementRepository,
    ConversationMessageManagementRepository,
)
from app.domain.access.contracts import Permission
from app.domain.audit.contracts import AuditAction, StatusTransitionMetadata
from app.domain.audit.ports import AuditWriter
from app.domain.channel.contracts import InboundChannelMessage, OutboundChannelMessage
from app.domain.conversation_management.contracts import (
    ConversationDetail,
    ConversationMessageRecord,
    ConversationSummary,
)
from app.domain.user.contracts import User
from app.infrastructure.models.analytics import ConversationManagementEventModel
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.repositories.bot_repository import BotRepository
from app.security.authorization import AuthorizationError, require_scoped_permission
from app.security.secret_cipher import SecretCipher


class ConversationManagementNotFoundError(ValueError):
    pass


class ConversationManagementConflictError(ValueError):
    pass


class ConversationManagementForbiddenError(ValueError):
    pass


class ConversationManagementService:
    def __init__(
        self,
        conversations: ConversationManagementRepository,
        messages: ConversationMessageManagementRepository,
        bot_repository: BotRepository,
        cipher: SecretCipher,
        session: Session,
        audit_writer: AuditWriter,
    ) -> None:
        self._conversations = conversations
        self._messages = messages
        self._bots = bot_repository
        self._cipher = cipher
        self._session = session
        self._audit_writer = audit_writer

    def record_inbound(
        self,
        message: InboundChannelMessage,
        conversation_id: UUID,
        receipt_id: UUID,
        contact_id: UUID | None = None,
    ) -> ConversationModel:
        context = message.resolved_context
        conversation, _ = self._conversations.get_or_create(
            ConversationModel(
                id=conversation_id,
                company_id=str(context.organization_id),
                customer_id=message.external_sender_id,
                organization_id=context.organization_id,
                bot_id=context.bot_id,
                channel_configuration_id=context.channel_configuration_id,
                external_customer_id=message.external_sender_id,
                contact_id=contact_id,
                masked_customer_identifier=_mask(message.external_sender_id),
                channel=message.channel_type,
                status="new",
                management_status="open",
                started_at=message.timestamp,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        self._associate_contact(conversation, contact_id, context.organization_id)
        if conversation.management_status == "archived":
            raise ConversationManagementConflictError(
                "archived conversation cannot receive messages"
            )
        record, _ = self._messages.create_once(
            MessageModel(
                id=uuid4(),
                conversation_id=conversation.id,
                role="user",
                content="",
                organization_id=context.organization_id,
                bot_id=context.bot_id,
                direction="inbound",
                channel_type=message.channel_type,
                external_message_id=message.external_message_id,
                message_type="text",
                text_ciphertext=self._cipher.encrypt(message.text),
                delivery_status="received",
                occurred_at=message.timestamp,
                inbound_receipt_id=receipt_id,
                metadata_data=dict(message.metadata),
                created_at=datetime.now(UTC),
            )
        )
        del record
        self._commit()
        return conversation

    def _associate_contact(
        self,
        conversation: ConversationModel,
        contact_id: UUID | None,
        organization_id: UUID,
    ) -> None:
        if contact_id is None:
            return
        contact = self._session.get(ContactModel, contact_id)
        if contact is None or contact.organization_id != organization_id:
            raise ConversationManagementConflictError("contact tenant mismatch")
        if conversation.contact_id is None:
            conversation.contact_id = contact.id
        elif conversation.contact_id != contact.id:
            raise ConversationManagementConflictError("conversation contact mismatch")

    def mark_inbound_processed(
        self, external_message_id: str, channel_type: str
    ) -> None:
        self._mark_inbound(external_message_id, channel_type, "processed")

    def mark_inbound_failed(self, external_message_id: str, channel_type: str) -> None:
        self._mark_inbound(external_message_id, channel_type, "failed")

    def _mark_inbound(
        self, external_message_id: str, channel_type: str, target: str
    ) -> None:
        from sqlalchemy import select

        stmt = select(MessageModel).where(
            MessageModel.direction == "inbound",
            MessageModel.channel_type == channel_type,
            MessageModel.external_message_id == external_message_id,
        )
        record = self._session.scalars(stmt).one_or_none()
        if record is not None:
            record.delivery_status = target
            self._commit()

    def record_outbound(
        self,
        outbound: OutboundChannelMessage,
        conversation_id: UUID,
        context_organization_id: UUID,
        context_bot_id: UUID,
        attempt_id: UUID,
        occurred_at: datetime,
    ) -> None:
        self._messages.create_once(
            MessageModel(
                id=uuid4(),
                conversation_id=conversation_id,
                role="assistant",
                content="",
                organization_id=context_organization_id,
                bot_id=context_bot_id,
                direction="outbound",
                channel_type=outbound.channel_type,
                message_type="text",
                text_ciphertext=self._cipher.encrypt(outbound.text),
                delivery_status="pending",
                occurred_at=occurred_at,
                outbound_attempt_id=attempt_id,
                metadata_data=dict(outbound.metadata),
                created_at=datetime.now(UTC),
            )
        )
        self._commit()

    def sync_outbound_attempt(
        self, attempt_id: UUID, status: str, provider_message_id: str | None
    ) -> None:
        if self._messages.sync_outbound_attempt(
            attempt_id, status, provider_message_id
        ):
            self._commit()

    def list(
        self,
        organization_id: UUID,
        actor: User,
        *,
        bot_id: UUID | None,
        channel_type: str | None,
        management_status: str | None,
        external_customer_id: str | None,
        has_inbound: bool | None,
        has_outbound: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ConversationSummary], int]:
        self._validate(organization_id, actor, "conversation.read", bot_id)
        models, total = self._conversations.list_scoped(
            organization_id,
            bot_id=bot_id,
            channel_type=channel_type,
            management_status=management_status,
            external_customer_id=external_customer_id,
            has_inbound=has_inbound,
            has_outbound=has_outbound,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return [_summary(model) for model in models], total

    def get(
        self, organization_id: UUID, conversation_id: UUID, actor: User
    ) -> ConversationDetail:
        self._validate(organization_id, actor, "conversation.read", None)
        model = self._get_scoped(conversation_id, organization_id)
        return _detail(model)

    def list_for_contact(
        self,
        organization_id: UUID,
        contact_id: UUID,
        actor: User,
        *,
        page: int,
        page_size: int,
    ) -> tuple[builtin_list[ConversationSummary], int]:
        self._validate(organization_id, actor, "conversation.read", None)
        models, total = self._conversations.list_by_contact(
            contact_id,
            organization_id,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return [_summary(model) for model in models], total

    def list_messages(
        self,
        organization_id: UUID,
        conversation_id: UUID,
        actor: User,
        *,
        page: int,
        page_size: int,
    ) -> tuple[builtin_list[ConversationMessageRecord], int]:
        self._validate(organization_id, actor, "conversation.read_content", None)
        self._get_scoped(conversation_id, organization_id)
        models, total = self._messages.list_scoped(
            conversation_id,
            organization_id,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return [_message(model, self._cipher) for model in models], total

    def transition(
        self, organization_id: UUID, conversation_id: UUID, target: str, actor: User
    ) -> ConversationDetail:
        permission: Permission = (
            "conversation.close"
            if target in {"closed", "open"}
            else "conversation.archive"
        )
        self._validate(organization_id, actor, permission, None)
        model = self._get_scoped(conversation_id, organization_id)
        if target == "archived":
            active_handoff = self._session.scalars(
                select(HandoffSessionModel)
                .where(
                    HandoffSessionModel.conversation_id == conversation_id,
                    HandoffSessionModel.organization_id == organization_id,
                    HandoffSessionModel.status.in_(("waiting_human", "human_active")),
                )
                .with_for_update()
            ).one_or_none()
            if active_handoff is not None:
                raise ConversationManagementConflictError(
                    "active handoff prevents conversation archive"
                )
        allowed = {
            "open": {"closed", "archived"},
            "closed": {"open", "archived"},
            "archived": set(),
        }
        if target not in allowed.get(model.management_status or "", set()):
            raise ConversationManagementConflictError(
                "conversation transition is not allowed"
            )
        from_status = model.management_status
        assert from_status is not None and model.bot_id is not None
        occurred_at = datetime.now(UTC)
        self._conversations.transition(model, target, occurred_at)
        self._session.add(
            ConversationManagementEventModel(
                organization_id=organization_id,
                conversation_id=model.id,
                bot_id=model.bot_id,
                from_status=from_status,
                to_status=target,
                occurred_at=occurred_at,
                actor_type="user",
                actor_id=actor.id,
            )
        )
        actions: dict[str, AuditAction] = {
            "closed": "conversation.closed",
            "open": "conversation.reopened",
            "archived": "conversation.archived",
        }
        append_user_audit(
            self._audit_writer,
            organization_id=organization_id,
            actor=actor,
            action=actions[target],
            resource_type="conversation",
            resource_id=model.id,
            metadata=StatusTransitionMetadata(
                from_status=from_status, to_status=target
            ),
            occurred_at=occurred_at,
        )
        self._commit()
        return _detail(model)

    def _get_scoped(
        self, conversation_id: UUID, organization_id: UUID
    ) -> ConversationModel:
        model = self._conversations.get_scoped(conversation_id, organization_id)
        if model is None:
            raise ConversationManagementNotFoundError("conversation not found")
        return model

    def _validate(
        self,
        organization_id: UUID,
        actor: User,
        permission: Permission,
        bot_id: UUID | None,
    ) -> None:
        try:
            require_scoped_permission(actor, permission, organization_id)
        except AuthorizationError as exc:
            raise ConversationManagementForbiddenError("permission denied") from exc
        if bot_id is not None:
            bot = self._bots.get(bot_id)
            if bot is None or bot.organization_id != organization_id:
                raise ConversationManagementNotFoundError("bot not found")

    def _commit(self) -> None:
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise ConversationManagementConflictError("conversation conflict") from exc


def _mask(value: str) -> str:
    return f"***{value[-4:]}" if len(value) > 4 else "***"


def _summary(model: ConversationModel) -> ConversationSummary:
    assert model.organization_id is not None and model.bot_id is not None
    return ConversationSummary(
        id=model.id,
        organization_id=model.organization_id,
        bot_id=model.bot_id,
        channel_type=model.channel,
        status=model.management_status or "open",
        masked_customer_identifier=model.masked_customer_identifier or "***",
        started_at=model.started_at,
        last_message_at=model.last_message_at,
        message_count=model.message_count,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _detail(model: ConversationModel) -> ConversationDetail:
    return ConversationDetail(
        **_summary(model).model_dump(),
        channel_configuration_id=model.channel_configuration_id,
        inbound_message_count=model.inbound_message_count,
        outbound_message_count=model.outbound_message_count,
        last_inbound_at=model.last_inbound_at,
        last_outbound_at=model.last_outbound_at,
        closed_at=model.closed_at,
    )


def _message(model: MessageModel, cipher: SecretCipher) -> ConversationMessageRecord:
    assert model.direction is not None and model.channel_type is not None
    assert model.message_type is not None and model.delivery_status is not None
    assert model.occurred_at is not None
    return ConversationMessageRecord(
        id=model.id,
        conversation_id=model.conversation_id,
        direction=model.direction,
        channel_type=model.channel_type,
        message_type=model.message_type,
        text=cipher.decrypt(model.text_ciphertext) if model.text_ciphertext else None,
        status=model.delivery_status,
        occurred_at=model.occurred_at,
        provider_message_id=model.provider_message_id,
        metadata=model.metadata_data or {},
    )
