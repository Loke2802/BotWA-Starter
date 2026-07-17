from typing import Any


class BusinessPolicy:
    def get_response(self, intent: str) -> dict[str, Any]:
        policies = {
            "greeting": {
                "status": "accepted",
                "message": "¡Hola! ¿En qué puedo ayudarte hoy?",
                "confidence": "high",
                "needs_knowledge": False,
            },
            "farewell": {
                "status": "accepted",
                "message": "Gracias por contactarnos. Que tengas un buen día.",
                "confidence": "high",
                "needs_knowledge": False,
            },
            "price_inquiry": {
                "status": "accepted",
                "message": (
                    "Gracias por tu interés. "
                    "Un asesor te contactará con los precios."
                ),
                "confidence": "medium",
                "needs_knowledge": True,
            },
            "thanks": {
                "status": "accepted",
                "message": "¡De nada! Estamos aquí para ayudarte.",
                "confidence": "high",
                "needs_knowledge": False,
            },
            "support": {
                "status": "accepted",
                "message": "Cuéntame más sobre el problema para poder ayudarte.",
                "confidence": "medium",
                "needs_knowledge": True,
            },
            "question": {
                "status": "accepted",
                "message": "Déjame revisar la información para responder tu consulta.",
                "confidence": "medium",
                "needs_knowledge": True,
            },
            "unknown": {
                "status": "accepted",
                "message": "Gracias por tu mensaje. Estamos procesando tu solicitud.",
                "confidence": "low",
                "needs_knowledge": False,
            },
        }
        return policies.get(intent, policies["unknown"])
