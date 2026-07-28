from app.domain.business.contracts import BusinessDecision
from app.domain.conversation.contracts import ConversationContext
from app.domain.conversation.response import BusinessResponse


class ResponseComposer:
    _TEMPLATES: dict[str, str] = {
        "greeting": "¡Hola! ¿En qué puedo ayudarte hoy?",
        "farewell": "Gracias por contactarnos. Que tengas un buen día.",
        "price_inquiry": (
            "Gracias por tu interés. " "Un asesor te contactará con los precios."
        ),
        "thanks": "¡De nada! Estamos aquí para ayudarte.",
        "support": "Cuéntame más sobre el problema para poder ayudarte.",
        "question": "Déjame revisar la información para responder tu consulta.",
        "unknown": "Gracias por tu mensaje. Estamos procesando tu solicitud.",
    }

    _TONE_MAP: dict[str, str] = {
        "greeting": "friendly",
        "farewell": "cordial",
        "price_inquiry": "professional",
        "thanks": "grateful",
        "support": "helpful",
        "question": "informative",
        "unknown": "neutral",
    }

    _DEFAULT_MESSAGE: str = "Gracias por tu mensaje. Estamos procesando tu solicitud."

    def compose(
        self,
        decision: BusinessDecision,
        context: ConversationContext,
    ) -> BusinessResponse:
        if decision.knowledge_content:
            message = decision.knowledge_content
        else:
            template_key = decision.intent
            message = self._TEMPLATES.get(template_key, self._DEFAULT_MESSAGE)

        tone = self._TONE_MAP.get(decision.intent, "neutral")

        return BusinessResponse(
            message=message,
            tone=tone,
            status=decision.status,
        )
