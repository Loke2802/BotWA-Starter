"""Durable IA execution. Every remote call occurs after its DB session closes."""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.application.audit.writer import append_non_user_audit
from app.application.generative_ai.policy import config_hash, configuration
from app.application.generative_ai.validation import FALLBACK, apply_discovery, render
from app.domain.generative_ai.contracts import (
    AdviserResult,
    AIConfig,
    CatalogItem,
    Discovery,
    ProviderError,
)
from app.domain.generative_ai.ports import AIProvider
from app.infrastructure.generative_ai.openai_provider import MODEL, PROMPT_VERSION
from app.infrastructure.models.ai_generation import (
    AIAttemptModel,
    AIJobModel,
    AIMemoryModel,
)
from app.infrastructure.models.bot import BotModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.human_handoff import HandoffSessionModel
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.settings import Settings
from app.security.secret_cipher import SecretCipher

ACTIVE = ("pending", "retry", "running", "ready")


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def source_data(row: KnowledgeEntryModel) -> dict[str, Any]:
    catalog = row.metadata_data.get("catalog_item")
    if catalog is not None:
        catalog = CatalogItem.model_validate(catalog).model_dump()
    return {
        "version": utc(row.updated_at).isoformat(),
        "title": row.title,
        "content": row.content[:2000],
        "catalog": catalog,
    }


def blocked(session: Session, job: AIJobModel) -> bool:
    return (
        session.scalar(
            select(HandoffSessionModel.id).where(
                HandoffSessionModel.organization_id == job.organization_id,
                HandoffSessionModel.bot_id == job.bot_id,
                HandoffSessionModel.conversation_id == job.conversation_id,
                HandoffSessionModel.status.in_(("waiting_human", "human_active")),
            )
        )
        is not None
    )


class AIService:
    def __init__(
        self,
        sessions: Callable[[], Session],
        settings: Settings,
        cipher: SecretCipher,
        provider: AIProvider,
    ) -> None:
        self.sessions, self.settings = sessions, settings
        self.cipher, self.provider = cipher, provider

    def _eligible(self, session: Session, job: AIJobModel) -> AIConfig | None:
        config = configuration(session, self.settings, job.organization_id, job.bot_id)
        channel = session.get(WhatsAppChannelConfigurationModel, job.configuration_id)
        conversation = session.get(ConversationModel, job.conversation_id)
        if (
            config is None
            or config_hash(config) != job.config_hash
            or blocked(session, job)
            or channel is None
            or channel.status != "active"
            or not channel.webhook_enabled
            or channel.organization_id != job.organization_id
            or channel.bot_id != job.bot_id
            or conversation is None
            or conversation.organization_id != job.organization_id
            or conversation.bot_id != job.bot_id
            or conversation.inbound_message_count != job.sequence
        ):
            return None
        return config

    def claim(self) -> tuple[UUID, UUID] | None:
        now = datetime.now(UTC)
        with self.sessions() as session:
            rows = session.scalars(
                select(AIJobModel)
                .where(
                    or_(
                        (AIJobModel.status.in_(("pending", "retry")))
                        & (AIJobModel.available_at <= now),
                        (AIJobModel.status == "running")
                        & (AIJobModel.lease_until < now),
                    )
                )
                .order_by(AIJobModel.created_at, AIJobModel.id)
                .limit(20)
                .with_for_update(skip_locked=True)
            ).all()
            for job in rows:
                conversation = session.scalar(
                    select(ConversationModel)
                    .where(ConversationModel.id == job.conversation_id)
                    .with_for_update(skip_locked=True)
                )
                if conversation is None:
                    continue
                other = session.scalar(
                    select(AIJobModel.id)
                    .where(
                        AIJobModel.conversation_id == job.conversation_id,
                        AIJobModel.id != job.id,
                        AIJobModel.status.in_(ACTIVE),
                        AIJobModel.sequence < job.sequence,
                    )
                    .limit(1)
                )
                if other is not None:
                    continue
                if self._eligible(session, job) is None:
                    job.status, job.error_code = "cancelled", "POLICY_OR_NEW_INPUT"
                    job.completed_at = now
                    session.flush()
                    continue
                if (
                    job.attempts >= self.settings.ai_max_attempts
                    or (now - utc(job.created_at)).total_seconds()
                    > self.settings.ai_job_max_age_seconds
                ):
                    self._fallback(job, "EXHAUSTED")
                    session.flush()
                    continue
                job.status, job.token = "running", uuid4()
                job.lease_until = now + timedelta(
                    seconds=2 * self.settings.ai_timeout_seconds + 60
                )
                job.attempts += 1
                job.started_at = job.started_at or now
                identity = (job.id, job.token)
                session.commit()
                return identity
            session.commit()
        return None

    def _owned(self, session: Session, job_id: UUID, token: UUID) -> AIJobModel:
        job = session.scalar(
            select(AIJobModel)
            .where(
                AIJobModel.id == job_id,
                AIJobModel.token == token,
                AIJobModel.status == "running",
                AIJobModel.lease_until > datetime.now(UTC),
            )
            .with_for_update()
        )
        if job is None:
            raise ProviderError("LOST_LEASE")
        return job

    def snapshot(self, job_id: UUID, token: UUID) -> dict[str, Any]:
        with self.sessions() as session:
            job = self._owned(session, job_id, token)
            config = self._eligible(session, job)
            if config is None:
                raise ProviderError("POLICY_CHANGED")
            memory_row = session.get(AIMemoryModel, job.conversation_id)
            memory: dict[str, Any] = {}
            if memory_row:
                if (
                    memory_row.organization_id != job.organization_id
                    or memory_row.bot_id != job.bot_id
                ):
                    raise ProviderError("SCOPE_MISMATCH")
                memory = json.loads(self.cipher.decrypt(memory_row.ciphertext))
            rows = session.scalars(
                select(MessageModel)
                .where(
                    MessageModel.conversation_id == job.conversation_id,
                    MessageModel.organization_id == job.organization_id,
                    MessageModel.bot_id == job.bot_id,
                    or_(
                        MessageModel.direction == "inbound",
                        MessageModel.delivery_status.in_(("sent", "delivered", "read")),
                    ),
                )
                .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
                .limit(20)
            ).all()
            history = []
            for row in reversed(rows):
                if row.text_ciphertext:
                    history.append(
                        {
                            "ref": str(row.id),
                            "role": "human" if row.author_user_id else row.role,
                            "direction": row.direction,
                            "text": self.cipher.decrypt(row.text_ciphertext)[:1200],
                        }
                    )
            return {
                "config": config.model_dump(),
                "memory": memory,
                "history": history,
                "memory_revision": memory_row.revision if memory_row else 0,
            }

    async def _generate(
        self,
        job_id: UUID,
        token: UUID,
        stage: str,
        context: dict[str, Any],
        schema: type[BaseModel],
    ) -> str:
        now, attempt_id = datetime.now(UTC), uuid4()
        with self.sessions() as session:
            job = self._owned(session, job_id, token)
            config = self._eligible(session, job)
            if config is None:
                raise ProviderError("POLICY_CHANGED")
            # Serialize daily admission only; this lock is released before HTTP.
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                session.execute(text("SELECT pg_advisory_xact_lock(681529310)"))
            session.scalar(
                select(BotModel.id).where(BotModel.id == job.bot_id).with_for_update()
            )
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(AIAttemptModel)
                    .where(AIAttemptModel.started_at >= midnight)
                )
                or 0
            )
            tenant_count = (
                session.scalar(
                    select(func.count())
                    .select_from(AIAttemptModel)
                    .join(AIJobModel)
                    .where(
                        AIJobModel.organization_id == job.organization_id,
                        AIJobModel.bot_id == job.bot_id,
                        AIAttemptModel.started_at >= midnight,
                    )
                )
                or 0
            )
            if (
                count >= self.settings.ai_daily_call_limit
                or tenant_count >= config.daily_jobs * 2
            ):
                raise ProviderError("DAILY_LIMIT")
            session.add(
                AIAttemptModel(
                    id=attempt_id,
                    job_id=job_id,
                    stage=stage,
                    model=MODEL,
                    prompt_version=PROMPT_VERSION,
                    parameters={
                        "schema_version": "1",
                        "reasoning_effort": "low",
                        "timeout_seconds": self.settings.ai_timeout_seconds,
                        "max_output_tokens": self.settings.ai_max_output_tokens,
                    },
                    started_at=now,
                )
            )
            session.commit()
        started = perf_counter()
        error = "unknown"
        generation = None
        try:
            generation = await self.provider.generate(
                stage=stage,
                context=json.dumps(context, ensure_ascii=False),
                schema=schema,
            )
            error = "success"
            return generation.data
        except ProviderError as exc:
            error = exc.code
            raise
        finally:
            with self.sessions() as session:
                attempt = session.get(AIAttemptModel, attempt_id)
                if attempt is not None:
                    attempt.duration_ms = int((perf_counter() - started) * 1000)
                    attempt.result = error
                    if generation:
                        attempt.input_tokens = generation.usage.input_tokens
                        attempt.output_tokens = generation.usage.output_tokens
                        attempt.model = generation.usage.model[:100]
                    session.commit()

    def retrieve(
        self, job_id: UUID, token: UUID, terms: list[str]
    ) -> dict[str, dict[str, Any]]:
        with self.sessions() as session:
            job = self._owned(session, job_id, token)
            # Scoped filtering precedes limiting. Small pilot catalog; lexical search.
            query = select(KnowledgeEntryModel).where(
                KnowledgeEntryModel.organization_id == job.organization_id,
                KnowledgeEntryModel.bot_id == job.bot_id,
                KnowledgeEntryModel.status == "published",
            )
            words = [
                w[:50] for term in terms for w in re.findall(r"\w+", term) if len(w) > 2
            ][:12]
            if words:
                query = query.where(
                    or_(
                        *[
                            KnowledgeEntryModel.title.ilike(f"%{word}%")
                            | KnowledgeEntryModel.content.ilike(f"%{word}%")
                            for word in words
                        ]
                    )
                )
            rows = session.scalars(
                query.order_by(KnowledgeEntryModel.id).limit(12)
            ).all()
            result = {}
            for row in rows:
                try:
                    result[str(row.id)] = source_data(row)
                except ValidationError:
                    continue
            return result

    async def run_once(self) -> bool:
        claim = self.claim()
        if claim is None:
            return False
        job_id, token = claim
        try:
            snapshot = self.snapshot(job_id, token)
            discovery = Discovery.model_validate_json(
                await self._generate(job_id, token, "discovery", snapshot, Discovery)
            )
            config = AIConfig.model_validate(snapshot["config"])
            memory = apply_discovery(
                discovery,
                config,
                snapshot["memory"],
                {
                    item["ref"]: item["text"]
                    for item in snapshot["history"]
                    if item["direction"] == "inbound"
                },
            )
            sources = self.retrieve(job_id, token, discovery.search_terms)
            if discovery.handoff_requested:
                result = AdviserResult(
                    tone="unknown",
                    question_key=None,
                    handoff_requested=True,
                    recommendations=[],
                    knowledge=[],
                )
            else:
                result = AdviserResult.model_validate_json(
                    await self._generate(
                        job_id,
                        token,
                        "adviser",
                        {
                            "config": snapshot["config"],
                            "history": snapshot["history"],
                            "memory": memory,
                            "sources": sources,
                        },
                        AdviserResult,
                    )
                )
            reply, used = render(result, config, memory, sources)
            with self.sessions() as session:
                job = self._owned(session, job_id, token)
                session.scalar(
                    select(ConversationModel.id)
                    .where(ConversationModel.id == job.conversation_id)
                    .with_for_update()
                )
                if self._eligible(session, job) is None:
                    raise ProviderError("POLICY_CHANGED")
                self.check_sources(session, job, used)
                row = session.get(AIMemoryModel, job.conversation_id)
                if (row.revision if row else 0) != snapshot["memory_revision"]:
                    raise ProviderError("MEMORY_CHANGED")
                if row is None:
                    row = AIMemoryModel(
                        conversation_id=job.conversation_id,
                        organization_id=job.organization_id,
                        bot_id=job.bot_id,
                        revision=0,
                    )
                    session.add(row)
                row.revision += 1
                row.ciphertext = self.cipher.encrypt(json.dumps(memory))
                job.result_ciphertext = self.cipher.encrypt(
                    json.dumps({"reply": reply, "handoff": result.handoff_requested})
                )
                append_non_user_audit(
                    SqlAlchemyAuditRepository(session),
                    organization_id=job.organization_id,
                    actor_type="system",
                    action="ai.generated",
                    resource_type="ai_job",
                    resource_id=job.id,
                )
                job.sources, job.status = used, "ready"
                job.completed_at, job.token, job.lease_until = (
                    datetime.now(UTC),
                    None,
                    None,
                )
                session.commit()
        except (ProviderError, ValidationError) as exc:
            self.fail(
                job_id,
                token,
                (
                    exc
                    if isinstance(exc, ProviderError)
                    else ProviderError("INVALID_SCHEMA")
                ),
            )
        except Exception:
            # Never log prompts, provider exceptions or private context.
            self.fail(job_id, token, ProviderError("INTERNAL_ERROR", True))
        return True

    @staticmethod
    def check_sources(
        session: Session, job: AIJobModel, sources: dict[str, str]
    ) -> None:
        for ref, version in sources.items():
            row = session.scalar(
                select(KnowledgeEntryModel).where(
                    KnowledgeEntryModel.id == UUID(ref),
                    KnowledgeEntryModel.organization_id == job.organization_id,
                    KnowledgeEntryModel.bot_id == job.bot_id,
                    KnowledgeEntryModel.status == "published",
                )
            )
            if row is None or utc(row.updated_at).isoformat() != version:
                raise ProviderError("SOURCE_CHANGED")

    def _fallback(self, job: AIJobModel, code: str) -> None:
        job.status, job.error_code = "ready", code
        job.result_ciphertext = self.cipher.encrypt(
            json.dumps({"reply": FALLBACK, "handoff": False})
        )
        job.completed_at, job.token, job.lease_until = datetime.now(UTC), None, None

    def fail(self, job_id: UUID, token: UUID, error: ProviderError) -> None:
        with self.sessions() as session:
            job = session.scalar(
                select(AIJobModel)
                .where(AIJobModel.id == job_id, AIJobModel.token == token)
                .with_for_update()
            )
            if job is None:
                return
            job.error_code, job.token, job.lease_until = error.code, None, None
            if error.code in {
                "POLICY_CHANGED",
                "MEMORY_CHANGED",
                "SCOPE_MISMATCH",
                "LOST_LEASE",
            }:
                job.status, job.completed_at = "cancelled", datetime.now(UTC)
            elif error.retryable and job.attempts < self.settings.ai_max_attempts:
                job.status = "retry"
                job.available_at = datetime.now(UTC) + timedelta(
                    seconds=5 * job.attempts
                )
            else:
                self._fallback(job, error.code)
                append_non_user_audit(
                    SqlAlchemyAuditRepository(session),
                    organization_id=job.organization_id,
                    actor_type="system",
                    action="ai.fallback",
                    resource_type="ai_job",
                    resource_id=job.id,
                )
            session.commit()
