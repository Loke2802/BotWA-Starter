from app.infrastructure.models.knowledge_catalog_entry import (
    KnowledgeCatalogEntryModel,
)
from app.infrastructure.repositories.knowledge_catalog_repository import (
    KnowledgeCatalogRepository,
)

_SEED_ITEMS: list[dict[str, object]] = [
    {
        "keywords": "horario,horarios,atención,abren,cierran",
        "content": (
            "Nuestro horario de atención es de lunes a viernes de 9:00 a 18:00."
        ),
        "confidence": "high",
    },
    {
        "keywords": "domicilio,envío,envian,entrega,enviar",
        "content": ("Realizamos envíos a todo el país. El costo varía según la zona."),
        "confidence": "high",
    },
    {
        "keywords": "pago,pagar,métodos,tarjeta,transferencia,efectivo",
        "content": (
            "Aceptamos tarjetas de crédito, débito, "
            "transferencia bancaria y efectivo."
        ),
        "confidence": "high",
    },
    {
        "keywords": "devolución,cambio,reembolso,garantía",
        "content": (
            "Ofrecemos 30 días de garantía. "
            "Las devoluciones deben gestionarse "
            "dentro de ese período."
        ),
        "confidence": "high",
    },
]


def ensure_knowledge_seed_data(
    repo: KnowledgeCatalogRepository,
) -> None:
    existing = repo.list()
    if existing:
        return
    for item in _SEED_ITEMS:
        entry = KnowledgeCatalogEntryModel(
            source_id="in_memory_seed",
            keywords=item["keywords"],
            content=item["content"],
            confidence=item["confidence"],
            source_trust_level=1.0,
        )
        repo.add(entry)
