"""Author-controlled permission to reword descriptive published knowledge.

Classification belongs to the knowledge editor, never to a model. Unknown,
stale or sensitive content keeps the existing literal contract. The lexical
guard is conservative defense in depth, not a semantic classifier.
"""

import hashlib
import re
import unicodedata
from typing import Any, Literal

from pydantic import Field, ValidationError

from app.domain.generative_ai.contracts import StrictModel


class KnowledgeExpressionPolicy(StrictModel):
    mode: Literal["descriptive_paraphrase"]
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def content_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# Ordinary explanations may be rewritten. Numerical facts, contacts, conditions
# and commercial commitments need the original immutable-clause path. This is
# intentionally restrictive; expanding it needs a typed protected-fact contract.
SENSITIVE = re.compile(
    r"\d|https?://|www\.|@|[%$€£]|s/|\b(?:"
    r"precio\w*|cost[oea]\w*|tarifa\w*|pago\w*|pag[ao]r\w*|cuota\w*|"
    r"inversion\w*|presupuesto\w*|financi\w*|cotiza\w*|"
    r"descuento\w*|promocion\w*|oferta\w*|gratis|gratuit\w*|compromiso\w*|"
    r"stock|disponib\w*|garanti\w*|asegur\w*|segur\w*|certific\w*|"
    r"plazo\w*|entrega\w*|horario\w*|edad\w*|ano\w*|mes\w*|dia\w*|hora\w*|"
    r"politica\w*|condicion\w*|termino\w*|contrat\w*|reembolso\w*|"
    r"devolucion\w*|cancel\w*|privacidad|dato\w*|consent\w*|"
    r"no|sin|excepto|salvo|solo|solamente|si|cuando|requiere\w*|depende\w*|"
    r"sujet\w*|segun|siempre|nunca|hasta|desde|"
    r"inclu\w*|exclu\w*|limite\w*|minim\w*|maxim\w*|"
    r"telefono\w*|whatsapp|correo\w*|direccion\w*|contact\w*|"
    r"soles|dolar\w*|euros|usd|pen|precio|vale|valor|"
    r"price\w*|cost\w*|free|warrant\w*|refund\w*|stock|available|"
    r"not|only|if|when|unless|except|until|deadline\w*|day\w*|hour\w*|age(?:s|d)?"
    r")\b",
    re.I,
)


def allows_paraphrase(content: str, policy: Any) -> bool:
    try:
        parsed = KnowledgeExpressionPolicy.model_validate(policy)
    except (ValidationError, TypeError):
        return False
    if not content.strip() or len(content) > 800:
        return False
    if parsed.content_sha256 != content_digest(content):
        return False
    normalized = "".join(
        c
        for c in unicodedata.normalize("NFKD", content)
        if not unicodedata.combining(c)
    )
    return not bool(SENSITIVE.search(normalized))
