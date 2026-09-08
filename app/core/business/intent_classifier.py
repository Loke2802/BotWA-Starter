class IntentClassifier:
    _COMMERCIAL_KEYWORDS: dict[str, list[str]] = {
        "human_handoff": ["asesor", "agente", "hablar con una persona", "humano"],
        "lead_qualification": [
            "demostracion",
            "demostración",
            "demo",
            "me interesa",
            "quiero informacion",
            "quiero información",
            "quiero contratar",
        ],
    }
    _KEYWORDS: dict[str, list[str]] = {
        "greeting": ["hola", "buenos", "saludos", "hey", "buen día", "que tal"],
        "farewell": ["adiós", "chao", "hasta luego", "nos vemos", "hasta pronto"],
        "price_inquiry": ["precio", "cuánto", "costo", "tarifa", "valor", "cuesta"],
        "thanks": ["gracias", "agradezco", "thanks", "thank you"],
        "support": ["ayuda", "soporte", "problema", "error", "falla", "no funciona"],
    }
    _QUESTION_PREFIXES: tuple[str, ...] = (
        "como funciona",
        "cómo funciona",
        "para que negocios",
        "para qué negocios",
        "que es",
        "que funciones",
        "qué es",
        "qué funciones",
    )

    def classify(self, content: str) -> str:
        text = content.lower().strip()

        if not text:
            return "unknown"

        for intent, keywords in self._COMMERCIAL_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return intent

        for intent, keywords in self._KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return intent

        if "?" in text:
            return "question"

        if text.startswith(self._QUESTION_PREFIXES):
            return "question"

        return "unknown"
