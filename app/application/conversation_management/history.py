"""Tenant-scoped plaintext history for transient Core context only."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.channel.contracts import ResolvedChannelContext
from app.domain.conversation.contracts import ConversationMessage, HistoryEntry
from app.infrastructure.models.message import MessageModel
from app.security.secret_cipher import SecretCipher


class ManagedConversationHistoryLoader:
    def __init__(
        self, session: Session, cipher: SecretCipher, scope: ResolvedChannelContext
    ) -> None:
        self._session = session
        self._cipher = cipher
        self._scope = scope

    def __call__(self, message: ConversationMessage) -> list[HistoryEntry]:
        if message.company_id != str(self._scope.organization_id):
            raise ValueError("conversation history scope mismatch")
        current_id = message.metadata.get("external_message_id")
        if not isinstance(current_id, str):
            raise ValueError("current message identity is required")
        rows = self._session.scalars(
            select(MessageModel)
            .where(
                MessageModel.organization_id == self._scope.organization_id,
                MessageModel.bot_id == self._scope.bot_id,
                MessageModel.conversation_id == message.conversation_id,
                or_(
                    MessageModel.external_message_id.is_(None),
                    MessageModel.external_message_id != current_id,
                ),
            )
            .order_by(MessageModel.occurred_at.desc(), MessageModel.id.desc())
            .limit(20)
        )
        history: list[HistoryEntry] = []
        remaining = 16_000
        for row in rows:
            if not row.text_ciphertext:
                continue
            content = self._cipher.decrypt(row.text_ciphertext)[
                -min(4_000, remaining) :
            ]
            history.append(
                HistoryEntry(
                    role=row.role,
                    content=content,
                    created_at=row.occurred_at or row.created_at,
                )
            )
            remaining -= len(content)
            if remaining == 0:
                break
        history.reverse()
        return history
