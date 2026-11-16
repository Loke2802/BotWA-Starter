"""Price-only fallback regressions from fictional evaluation; no model calls."""

import pytest
from app.application.generative_ai.response_continuation import safe_continuation
from app.domain.generative_ai.contracts import AdviserResult, AIConfig, NeedDefinition

from tests.test_commercial_continuity import CATALOG, CORPORATE, evidence

QUESTION = "¿Ya tienes algo implementado o empezaríamos desde cero?"
CONFIG = AIConfig(
    needs=[NeedDefinition(key="situacion", question=QUESTION, attribute="situacion")]
)
GAP = "No tengo confirmado el precio exacto de tu proyecto."


@pytest.mark.parametrize(
    "customer_request",
    [
        "Tengo un taller y quiero una web corporativa. "
        "¿Cuál sería el precio exacto de mi proyecto?",
        "¿Cuánto cuesta una web corporativa?",
        "Dime el costo exacto de mi web corporativa.",
    ],
)
def test_price_only_fallback_delimits_gap_instead_of_defining_service(
    customer_request: str,
) -> None:
    result, sources = evidence()
    text = safe_continuation(result, CONFIG, {}, sources, [], customer_request)
    assert text == f"{GAP}\n\n{QUESTION}"
    assert CORPORATE not in text and CATALOG not in text


def test_price_and_explanation_request_keeps_supported_description() -> None:
    result, sources = evidence()
    text = safe_continuation(
        result,
        CONFIG,
        {},
        sources,
        [],
        "¿Cuál es el precio y qué me aporta una web corporativa y un catálogo web?",
    )
    assert CORPORATE in text and CATALOG in text
    assert GAP not in text


def test_price_fallback_does_not_repeat_recent_scope_question() -> None:
    result, sources = evidence()
    text = safe_continuation(
        result, CONFIG, {}, sources, [QUESTION], "¿Cuál sería el precio exacto?"
    )
    assert text.startswith(GAP) and QUESTION not in text
    assert text.count("?") == 1


def test_authorized_catalog_amount_is_not_replaced_by_a_price_gap() -> None:
    result = AdviserResult.model_validate(
        {
            "tone": "understood",
            "question_key": None,
            "handoff_requested": False,
            "knowledge": [],
            "recommendations": [
                {
                    "item_ref": "item",
                    "matches": [{"need_key": "precio", "attribute_key": "precio"}],
                }
            ],
        }
    )
    sources = {
        "item": {
            "version": "v1",
            "catalog": {
                "name": "Servicio web",
                "attributes": [{"key": "precio", "label": "Precio", "value": "900"}],
            },
        }
    }
    config = AIConfig(
        needs=[
            NeedDefinition(key="precio", question="¿Qué precio?", attribute="precio")
        ]
    )
    text = safe_continuation(
        result,
        config,
        {"precio": {"value": "900"}},
        sources,
        [],
        "¿Cuál es el precio?",
    )
    assert "900" in text and "Servicio web" in text and GAP not in text
