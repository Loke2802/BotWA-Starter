"""Controlled internal conversation templates for Luri."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConversationTemplate:
    message: str
    tone: str


TEMPLATES: dict[str, ConversationTemplate] = {
    "greeting": ConversationTemplate(
        message=(
            "¡Hola! Soy Luri, la plataforma de Kalivur para atención por "
            "WhatsApp e IA. Puedo contarte qué es Luri, sus funciones, para "
            "qué negocios sirve o ayudarte a solicitar una demostración."
        ),
        tone="friendly",
    ),
    "farewell": ConversationTemplate(
        message="Gracias por contactarnos. Que tengas un buen día.",
        tone="cordial",
    ),
    "price_inquiry": ConversationTemplate(
        message=(
            "Para orientarte sobre una propuesta, comparte tu nombre, "
            "negocio, país y qué deseas automatizar: consultas, reservas, "
            "pagos, seguimientos u otro."
        ),
        tone="professional",
    ),
    "lead_qualification": ConversationTemplate(
        message=(
            "Con gusto te ayudo a preparar una demostración. Comparte tu "
            "nombre, negocio y qué buscas automatizar: consultas, reservas, "
            "pagos, seguimientos u otro."
        ),
        tone="professional",
    ),
    "human_handoff": ConversationTemplate(
        message=(
            "Para preparar la atención de un asesor, comparte tu nombre, "
            "negocio y la necesidad principal que quieres resolver."
        ),
        tone="helpful",
    ),
    "thanks": ConversationTemplate(
        message="¡De nada! Estoy aquí para ayudarte.",
        tone="grateful",
    ),
    "support": ConversationTemplate(
        message=(
            "Cuéntame qué ocurre, qué estabas intentando hacer y, si aparece, "
            "el mensaje de error."
        ),
        tone="helpful",
    ),
    "question": ConversationTemplate(
        message=(
            "Puedo ayudarte con Luri, sus funciones, los negocios para los "
            "que sirve, una demostración o una propuesta. ¿Qué quieres conocer?"
        ),
        tone="informative",
    ),
    "unknown": ConversationTemplate(
        message=(
            "Puedo ayudarte con Luri, sus funciones, los negocios para los "
            "que sirve, una demostración o una propuesta. ¿Qué quieres conocer?"
        ),
        tone="neutral",
    ),
}


def template_for(intent: str) -> ConversationTemplate:
    return TEMPLATES.get(intent, TEMPLATES["unknown"])
