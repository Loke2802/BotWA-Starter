import pytest
from app.core.conversation.response_composer import ResponseComposer
from app.domain.business.contracts import BusinessDecision
from app.domain.conversation.contracts import (
    ConversationContext,
    ConversationMessage,
)
from app.domain.conversation.topics import (
    ConversationTopic,
    ConversationTopics,
)


def test_compose_greeting_returns_friendly_response() -> None:
    decision = BusinessDecision(
        status="accepted",
        intent="greeting",
        confidence="high",
    )
    message = ConversationMessage(
        content="Hola",
        customer_id="c1",
        company_id="co1",
    )
    context = ConversationContext(message=message)
    composer = ResponseComposer()

    response = composer.compose(decision, context)

    assert "Soy Luri" in response.message
    assert response.status == "accepted"
    assert response.tone == "friendly"


def test_compose_knowledge_content_overrides_template() -> None:
    decision = BusinessDecision(
        status="accepted",
        intent="greeting",
        confidence="high",
        knowledge_content="Nuestro horario es de 9 a 18.",
    )
    message = ConversationMessage(
        content="Horario",
        customer_id="c1",
        company_id="co1",
    )
    context = ConversationContext(message=message)
    composer = ResponseComposer()

    response = composer.compose(decision, context)

    assert response.message == "Nuestro horario es de 9 a 18."


def test_compose_unknown_returns_default() -> None:
    decision = BusinessDecision(
        status="accepted",
        intent="unknown",
        confidence="low",
    )
    message = ConversationMessage(
        content="xyz",
        customer_id="c1",
        company_id="co1",
    )
    context = ConversationContext(message=message)
    composer = ResponseComposer()

    response = composer.compose(decision, context)

    assert "Puedo ayudarte con Luri" in response.message
    assert response.tone == "neutral"


def test_compose_preserves_decision_status() -> None:
    decision = BusinessDecision(
        status="accepted",
        intent="farewell",
        confidence="high",
    )
    message = ConversationMessage(
        content="Adiós",
        customer_id="c1",
        company_id="co1",
    )
    context = ConversationContext(message=message)
    composer = ResponseComposer()

    response = composer.compose(decision, context)

    assert response.status == "accepted"


def test_compose_invalid_intent_falls_back_to_default() -> None:
    decision = BusinessDecision(
        status="accepted",
        intent="nonexistent",
        confidence="low",
    )
    message = ConversationMessage(
        content="Test",
        customer_id="c1",
        company_id="co1",
    )
    context = ConversationContext(message=message)
    composer = ResponseComposer()

    response = composer.compose(decision, context)

    assert "Puedo ayudarte con Luri" in response.message


def test_compose_with_topics_in_context() -> None:
    decision = BusinessDecision(
        status="accepted",
        intent="support",
        confidence="medium",
    )
    message = ConversationMessage(
        content="Necesito ayuda",
        customer_id="c1",
        company_id="co1",
    )
    topics = ConversationTopics(
        primary=ConversationTopic(name="support", confidence="high"),
    )
    context = ConversationContext(message=message, topics=topics)
    composer = ResponseComposer()

    response = composer.compose(decision, context)

    assert "Cuéntame qué ocurre" in response.message
    assert response.tone == "helpful"


def test_tone_maps_for_each_intent() -> None:
    composer = ResponseComposer()
    message = ConversationMessage(
        content="Test",
        customer_id="c1",
        company_id="co1",
    )
    context = ConversationContext(message=message)

    cases = [
        ("greeting", "friendly"),
        ("farewell", "cordial"),
        ("price_inquiry", "professional"),
        ("lead_qualification", "professional"),
        ("human_handoff", "helpful"),
        ("thanks", "grateful"),
        ("support", "helpful"),
        ("question", "informative"),
        ("unknown", "neutral"),
    ]

    for intent, expected_tone in cases:
        decision = BusinessDecision(
            status="accepted",
            intent=intent,
            confidence="high",
        )
        response = composer.compose(decision, context)
        assert response.tone == expected_tone, f"Failed for intent={intent}"


@pytest.mark.parametrize(
    ("intent", "expected_fragment"),
    [
        ("price_inquiry", "propuesta"),
        ("lead_qualification", "demostración"),
        ("human_handoff", "asesor"),
    ],
)
def test_compose_commercial_templates(intent: str, expected_fragment: str) -> None:
    decision = BusinessDecision(status="accepted", intent=intent, confidence="high")
    message = ConversationMessage(content="test", customer_id="c1", company_id="co1")

    response = ResponseComposer().compose(
        decision,
        ConversationContext(message=message),
    )

    assert expected_fragment in response.message
