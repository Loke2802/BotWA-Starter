"""Reuse evidence-backed IA memory without remote calls or automatic CRM writes."""

import json
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select

from app.application.crm.service import OpportunityService
from app.application.generative_ai.policy import config_hash, configuration
from app.domain.crm.customer_contracts import CommercialSuggestion
from app.domain.generative_ai.contracts import NeedPatch
from app.domain.user.contracts import User
from app.infrastructure.models.ai_generation import AIJobModel, AIMemoryModel
from app.infrastructure.models.message import MessageModel
from app.infrastructure.repositories.crm_identity import canonical
from app.infrastructure.settings import Settings
from app.security.authorization import require_scoped_permission


class CommercialSuggestionService:
    def __init__(self, commercial: OpportunityService, settings: Settings) -> None:
        self.commercial, self.settings = commercial, settings

    def suggest(
        self, org: UUID, contact: UUID, conversation_id: UUID, actor: User
    ) -> CommercialSuggestion:
        self.commercial._write(org, actor)
        require_scoped_permission(actor, "conversation.read", org)
        require_scoped_permission(actor, "conversation.read_content", org)
        self.commercial.repository.organization(org)
        self.commercial.repository.contact(org, contact)
        conversation = self.commercial.repository.conversation(org, conversation_id)
        if conversation.contact_id is None or canonical(
            self.commercial.session, org, conversation.contact_id
        ) != canonical(self.commercial.session, org, contact):
            from app.domain.crm.contracts import CrmNotFound

            raise CrmNotFound()
        unavailable = CommercialSuggestion(
            available=False,
            explanation=(
                "No hay una extracción de IA vigente con evidencia "
                "para esta conversación. Puedes completar "
                "la oportunidad manualmente."
            ),
            conversation_id=conversation_id,
        )
        if conversation.bot_id is None:
            return unavailable
        config = configuration(
            self.commercial.session, self.settings, org, conversation.bot_id
        )
        if config is None:
            return unavailable
        memory = self.commercial.session.scalar(
            select(AIMemoryModel).where(
                AIMemoryModel.organization_id == org,
                AIMemoryModel.conversation_id == conversation_id,
                AIMemoryModel.bot_id == conversation.bot_id,
            )
        )
        job = self.commercial.session.scalar(
            select(AIJobModel)
            .where(
                AIJobModel.organization_id == org,
                AIJobModel.conversation_id == conversation_id,
                AIJobModel.bot_id == conversation.bot_id,
                AIJobModel.status == "sent",
                AIJobModel.sequence == conversation.inbound_message_count,
                AIJobModel.config_hash == config_hash(config),
            )
            .order_by(AIJobModel.created_at.desc())
            .limit(1)
        )
        if memory is None or job is None:
            return unavailable
        try:
            values = json.loads(self.commercial.cipher.decrypt(memory.ciphertext))
            if not isinstance(values, dict) or len(values) > 20:
                return unavailable
            verified = {}
            for definition in config.needs:
                value = values.get(definition.key)
                if (
                    not isinstance(value, dict)
                    or value.get("status") != "evidence_backed"
                ):
                    continue
                patch = NeedPatch(
                    key=definition.key,
                    value=value["value"],
                    quote=value["quote"],
                    message_ref=value["message_ref"],
                )
                ref = UUID(patch.message_ref)
                message = self.commercial.session.scalar(
                    select(MessageModel).where(
                        MessageModel.id == ref,
                        MessageModel.organization_id == org,
                        MessageModel.conversation_id == conversation_id,
                        MessageModel.bot_id == conversation.bot_id,
                        MessageModel.direction == "inbound",
                    )
                )
                if message is None or not message.text_ciphertext:
                    return unavailable
                text = self.commercial.cipher.decrypt(message.text_ciphertext)
                if (
                    patch.quote not in text
                    or patch.value.casefold() not in patch.quote.casefold()
                ):
                    return unavailable
                verified[definition.key] = patch
        except (ValueError, KeyError, TypeError, ValidationError):
            return unavailable
        if not verified:
            return unavailable
        open_stages = [
            s for s in self.commercial.stages(org, actor) if s.kind == "open"
        ]
        stage = next((s for s in open_stages if s.code == "need"), open_stages[0])
        missing = next(
            (d.question for d in config.needs if d.required and d.key not in verified),
            None,
        )
        return CommercialSuggestion(
            available=True,
            explanation=(
                "Propuesta basada en necesidades extraídas por la IA "
                "existente y verificadas contra los mensajes. "
                "La etapa y la acción son sugerencias de seguimiento; "
                "revisa antes de guardar y elige responsable y fecha."
            ),
            conversation_id=conversation_id,
            memory_revision=memory.revision,
            need="; ".join(p.value for p in verified.values())[:4000],
            stage_code=stage.code,
            next_action=missing
            or "Confirmar las necesidades y preparar una propuesta con el cliente.",
            evidence=[p.quote for p in verified.values()],
        )

    def for_opportunity(
        self, org: UUID, opportunity: UUID, conversation: UUID, actor: User
    ) -> CommercialSuggestion:
        current = self.commercial.get(org, opportunity, actor)
        result = self.suggest(org, current.contact_id, conversation, actor)
        if current.stage_kind != "open":
            result.available = False
            result.explanation = (
                "La oportunidad está cerrada. Revisa su estado manualmente."
            )
        return result.model_copy(
            update={
                "opportunity_id": current.id,
                "expected_version": current.version,
                "current_need": current.need,
                "current_stage_code": current.stage_code,
                "current_action": (
                    current.next_action.description
                    if current.next_action
                    else current.no_action_reason
                ),
            }
        )
