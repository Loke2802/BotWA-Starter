class IntentClassifier:
    _KEYWORDS: dict[str, list[str]] = {
        "greeting": ["hola", "buenos", "saludos", "hey", "buen día", "que tal"],
        "farewell": ["adiós", "chao", "hasta luego", "nos vemos", "hasta pronto"],
        "price_inquiry": ["precio", "cuánto", "costo", "tarifa", "valor", "cuesta"],
        "thanks": ["gracias", "agradezco", "thanks", "thank you"],
        "support": ["ayuda", "soporte", "problema", "error", "falla", "no funciona"],
    }

    def classify(self, content: str) -> str:
        text = content.lower().strip()

        if not text:
            return "unknown"

        if "?" in text:
            for intent, keywords in self._KEYWORDS.items():
                if intent != "question" and any(kw in text for kw in keywords):
                    return intent
            return "question"

        for intent, keywords in self._KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return intent

        return "unknown"
