from app.core.knowledge.retriever import KnowledgeRetriever
from app.domain.knowledge.contracts import KnowledgeItem, KnowledgeQuery


class InMemoryKnowledgeRetriever(KnowledgeRetriever):
    def __init__(self) -> None:
        self._items: list[dict[str, str | list[str]]] = [
            {
                "keywords": [
                    "horario",
                    "horarios",
                    "atención",
                    "abren",
                    "cierran",
                ],
                "content": (
                    "Nuestro horario de atención es de lunes a viernes "
                    "de 9:00 a 18:00."
                ),
                "confidence": "high",
            },
            {
                "keywords": [
                    "domicilio",
                    "envío",
                    "envian",
                    "entrega",
                    "enviar",
                ],
                "content": (
                    "Realizamos envíos a todo el país. " "El costo varía según la zona."
                ),
                "confidence": "high",
            },
            {
                "keywords": [
                    "pago",
                    "pagar",
                    "métodos",
                    "tarjeta",
                    "transferencia",
                    "efectivo",
                ],
                "content": (
                    "Aceptamos tarjetas de crédito, débito, "
                    "transferencia bancaria y efectivo."
                ),
                "confidence": "high",
            },
            {
                "keywords": [
                    "devolución",
                    "cambio",
                    "reembolso",
                    "garantía",
                ],
                "content": (
                    "Ofrecemos 30 días de garantía. "
                    "Las devoluciones deben gestionarse "
                    "dentro de ese período."
                ),
                "confidence": "high",
            },
        ]

    def retrieve(self, query: KnowledgeQuery) -> list[KnowledgeItem]:
        text = query.content.lower()
        for item in self._items:
            keywords = item["keywords"]
            if any(kw in text for kw in keywords):
                return [
                    KnowledgeItem(
                        source_id="in_memory_seed",
                        content=item["content"],
                        confidence=item["confidence"],
                    ),
                ]
        return []
