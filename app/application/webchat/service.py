import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.human_handoff.service import HumanHandoffService
from app.application.knowledge_management.provider import BotKnowledgeProvider
from app.application.knowledge_management.retriever import (
    PublishedBotKnowledgeRetriever,
)
from app.application.plans.service import PlanEnforcementService
from app.domain.knowledge.contracts import KnowledgeQuery
from app.domain.webchat.contracts import (
    WebchatError,
    WebchatHistory,
    WebchatMessage,
    WebchatMessageRequest,
    WebchatSession,
)
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.conversation_management_repository import (
    SqlAlchemyConversationMessageManagementRepository,
)
from app.infrastructure.repositories.knowledge_entry_repository import (
    SqlAlchemyKnowledgeEntryRepository,
)
from app.infrastructure.settings import Settings
from app.security.secret_cipher import SecretCipher

FALLBACK = (
    "No tengo información publicada suficiente para responder esa consulta. "
    "Puedes solicitar atención del equipo con el botón Hablar con una persona."
)


class WebchatService:
    """Scoped capabilities and encrypted history; writes lock the conversation.

    No AI/WhatsApp ingress or sender is reachable from this service.
    """

    def __init__(
        self,
        session: Session,
        settings: Settings,
        cipher: SecretCipher,
        handoff: HumanHandoffService,
        plan_enforcement: PlanEnforcementService,
    ) -> None:
        self.session, self.settings = session, settings
        self.cipher, self.handoff = cipher, handoff
        self.plans = plan_enforcement
        self.messages = SqlAlchemyConversationMessageManagementRepository(
            session, SqlAlchemyAuditRepository(session)
        )

    def _scope(self) -> tuple[UUID, UUID]:
        org_id = self.settings.webchat_organization_id
        bot_id = self.settings.webchat_bot_id
        if not self.settings.webchat_enabled or org_id is None or bot_id is None:
            raise WebchatError(503, "Chat unavailable")
        org = self.session.get(OrganizationModel, org_id)
        bot = self.session.get(BotModel, bot_id)
        if (
            org is None
            or org.status != "active"
            or bot is None
            or bot.organization_id != org_id
            or bot.status != "active"
        ):
            raise WebchatError(503, "Chat unavailable")
        return org_id, bot_id

    def create(self, origin: str) -> WebchatSession:
        org_id, bot_id = self._scope()
        identifier = uuid4()
        self.plans.require_consuming_action(org_id, feature="knowledge")
        token = f"{identifier}.{secrets.token_urlsafe(32)}"
        expires = datetime.now(UTC) + timedelta(
            seconds=self.settings.webchat_session_ttl_seconds
        )
        visitor = f"web:{identifier}"
        self.session.add(
            ConversationModel(
                id=identifier,
                organization_id=org_id,
                bot_id=bot_id,
                company_id=str(org_id),
                customer_id=visitor,
                external_customer_id=visitor,
                masked_customer_identifier=f"Visitante web · {str(identifier)[:8]}",
                channel="web",
                status="new",
                management_status="open",
                extra_data={
                    "webchat_token_digest": hashlib.sha256(token.encode()).hexdigest(),
                    "webchat_origin": origin,
                    "webchat_expires_at": expires.isoformat(),
                },
            )
        )
        self.session.commit()
        return WebchatSession(token=token, expires_at=expires)

    @staticmethod
    def _available(row: ConversationModel) -> bool:
        data = row.extra_data or {}
        expiry = data.get("webchat_expires_at")
        return (
            isinstance(expiry, str)
            and datetime.fromisoformat(expiry) > datetime.now(UTC)
            and data.get("webchat_token_digest") != "revoked"
            and row.management_status != "archived"
        )

    def _conversation(self, token: str, origin: str) -> ConversationModel:
        org_id, bot_id = self._scope()
        try:
            identifier = UUID(token.split(".", 1)[0])
        except ValueError as exc:
            raise WebchatError(401, "Session unavailable") from exc
        row = self.session.get(ConversationModel, identifier, with_for_update=True)
        if (
            row is None
            or row.organization_id != org_id
            or row.bot_id != bot_id
            or row.channel != "web"
        ):
            raise WebchatError(401, "Session unavailable")
        data = row.extra_data or {}
        digest = data.get("webchat_token_digest")
        if (
            not isinstance(digest, str)
            or not secrets.compare_digest(
                digest, hashlib.sha256(token.encode()).hexdigest()
            )
            or data.get("webchat_origin") != origin
            or not self._available(row)
        ):
            raise WebchatError(401, "Session unavailable")
        return row

    def _status(
        self,
        row: ConversationModel,
    ) -> Literal["bot_active", "waiting_human", "human_active", "resolved"]:
        handoff = self.session.scalar(
            select(HandoffSessionModel).where(
                HandoffSessionModel.conversation_id == row.id,
                HandoffSessionModel.organization_id == row.organization_id,
            )
        )
        if handoff:
            if handoff.status == "waiting_human":
                return "waiting_human"
            if handoff.status == "human_active":
                return "human_active"
            if handoff.status == "resolved":
                return "resolved"
        return "bot_active"

    def _history(self, row: ConversationModel) -> WebchatHistory:
        records = self.session.scalars(
            select(MessageModel)
            .where(
                MessageModel.conversation_id == row.id,
                MessageModel.organization_id == row.organization_id,
                MessageModel.bot_id == row.bot_id,
                MessageModel.channel_type == "web",
            )
            .order_by(MessageModel.occurred_at, MessageModel.id)
            .limit(200)
        ).all()
        return WebchatHistory(
            status=self._status(row),
            messages=[
                WebchatMessage(
                    id=item.id,
                    role=(
                        "user"
                        if item.direction == "inbound"
                        else ("operator" if item.author_user_id else "assistant")
                    ),
                    text=(
                        self.cipher.decrypt(item.text_ciphertext)
                        if item.text_ciphertext
                        else ""
                    ),
                )
                for item in records
            ],
        )

    def history(self, token: str, origin: str) -> WebchatHistory:
        return self._history(self._conversation(token, origin))

    def _append(
        self,
        row: ConversationModel,
        identifier: UUID,
        text: str,
        *,
        inbound: bool,
        author: UUID | None = None,
        source: str | None = None,
    ) -> None:
        self.messages.create_once(
            MessageModel(
                id=identifier,
                conversation_id=row.id,
                organization_id=row.organization_id,
                bot_id=row.bot_id,
                channel_type="web",
                role="user" if inbound else "assistant",
                direction="inbound" if inbound else "outbound",
                content="",
                text_ciphertext=self.cipher.encrypt(text),
                message_type="text",
                delivery_status="processed" if inbound else "sent",
                external_message_id=str(identifier) if inbound else None,
                author_user_id=author,
                occurred_at=datetime.now(UTC),
                metadata_data={"source_id": source} if source else {},
            )
        )

    def submit(
        self,
        token: str,
        origin: str,
        body: WebchatMessageRequest,
    ) -> WebchatHistory:
        org_id, _ = self._scope()
        # Same lock order as operator handoff: organization before conversation.
        self.plans.require_consuming_action(org_id, feature="knowledge")
        row = self._conversation(token, origin)
        identifier = uuid5(row.id, f"visitor:{body.idempotency_key}")
        previous = self.session.get(MessageModel, identifier)
        if previous is not None:
            if self.cipher.decrypt(previous.text_ciphertext or "") != body.message:
                raise WebchatError(409, "Idempotency key already used")
            return self._history(row)
        if row.message_count > 198:
            raise WebchatError(409, "Session message limit reached")
        if self._status(row) == "resolved":
            raise WebchatError(409, "Human attention has ended; start a new session")
        self._append(row, identifier, body.message, inbound=True)
        if self._status(row) == "bot_active":
            assert row.organization_id is not None and row.bot_id is not None
            matches = PublishedBotKnowledgeRetriever(
                BotKnowledgeProvider(SqlAlchemyKnowledgeEntryRepository(self.session)),
                row.organization_id,
                row.bot_id,
            ).retrieve(
                KnowledgeQuery(
                    content=body.message,
                    intent="information",
                    company_id=str(row.organization_id),
                )
            )
            self._append(
                row,
                uuid5(identifier, "reply"),
                matches[0].content[:8000] if matches else FALLBACK,
                inbound=False,
                source=matches[0].source_id if matches else None,
            )
        self.session.commit()
        return self._history(row)

    def request_human(self, token: str, origin: str) -> WebchatHistory:
        org_id, _ = self._scope()
        self.plans.require_consuming_action(org_id, feature="human_handoff")
        row = self._conversation(token, origin)
        if self._status(row) == "resolved":
            raise WebchatError(409, "Human attention has ended; start a new session")
        if self._status(row) not in {"waiting_human", "human_active"}:
            assert row.organization_id is not None and row.bot_id is not None
            self.handoff.request_assistant(row.organization_id, row.bot_id, row.id)
        return self._history(row)

    def close(self, token: str, origin: str) -> None:
        row = self._conversation(token, origin)
        row.extra_data = {**(row.extra_data or {}), "webchat_token_digest": "revoked"}
        self.session.commit()

    def reply(
        self,
        conversation_id: UUID,
        organization_id: UUID,
        text: str,
        key: str,
        author: UUID,
    ) -> dict[str, str]:
        org_id, bot_id = self._scope()
        row = self.session.get(ConversationModel, conversation_id, with_for_update=True)
        if (
            row is None
            or row.organization_id != organization_id
            or organization_id != org_id
            or row.bot_id != bot_id
            or row.channel != "web"
        ):
            raise WebchatError(404, "Conversation unavailable")
        if not self._available(row):
            raise WebchatError(409, "Web session expired or closed")
        identifier = uuid5(row.id, f"operator:{key}")
        previous = self.session.get(MessageModel, identifier)
        if previous is not None:
            if (
                previous.author_user_id != author
                or self.cipher.decrypt(previous.text_ciphertext or "") != text
            ):
                raise WebchatError(409, "Idempotency key already used")
        else:
            if row.message_count >= 200:
                raise WebchatError(409, "Session message limit reached")
            self._append(row, identifier, text, inbound=False, author=author)
            self.session.commit()
        return {"attempt_id": str(identifier), "status": "sent"}
