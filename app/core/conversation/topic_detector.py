from app.domain.conversation.contracts import ConversationContext
from app.domain.conversation.topics import ConversationTopic, ConversationTopics

_TOPIC_RULES: dict[str, list[str]] = {
    "greeting": [
        "hola",
        "buenos",
        "saludos",
        "hey",
        "buen día",
        "que tal",
    ],
    "farewell": [
        "adiós",
        "chao",
        "hasta luego",
        "nos vemos",
        "hasta pronto",
    ],
    "complaint": [
        "queja",
        "reclamo",
        "problema",
        "error",
        "falla",
        "no funciona",
        "mal servicio",
    ],
    "purchase": [
        "precio",
        "cuánto",
        "costo",
        "tarifa",
        "valor",
        "comprar",
        "cotizar",
        "presupuesto",
    ],
    "support": [
        "ayuda",
        "soporte",
        "asistencia",
        "contacto",
        "asesor",
        "ayúdame",
    ],
    "information": [
        "horario",
        "dirección",
        "teléfono",
        "información",
        "cómo",
        "qué es",
        "cuándo",
        "dónde",
        "quién",
        "abren",
        "cierran",
    ],
}


class TopicDetector:
    def detect(self, context: ConversationContext) -> ConversationContext:
        text = context.message.content.lower().strip()

        if not text:
            return context.model_copy(
                update={
                    "topics": ConversationTopics(
                        primary=ConversationTopic(name="general", confidence="medium")
                    )
                }
            )

        matched: list[str] = []
        for topic, keywords in _TOPIC_RULES.items():
            if any(kw in text for kw in keywords):
                matched.append(topic)

        if not matched:
            if "?" in text:
                matched.append("information")
            else:
                return context.model_copy(
                    update={
                        "topics": ConversationTopics(
                            primary=ConversationTopic(
                                name="general", confidence="medium"
                            )
                        )
                    }
                )

        primary_name = matched[0]
        secondary_names = matched[1:]

        topics = ConversationTopics(
            primary=ConversationTopic(name=primary_name, confidence="high"),
            secondary=[
                ConversationTopic(name=t, confidence="high", is_primary=False)
                for t in secondary_names
            ],
        )

        return context.model_copy(update={"topics": topics})
