from app.core.conversation.topic_detector import TopicDetector
from app.domain.conversation.contracts import ConversationContext, ConversationMessage


def _make_context(content: str) -> ConversationContext:
    message = ConversationMessage(content=content, customer_id="c1", company_id="co1")
    return ConversationContext(message=message)


def test_detect_greeting() -> None:
    detector = TopicDetector()
    context = detector.detect(_make_context("Hola buenos días"))
    assert context.topics is not None
    assert context.topics.primary is not None
    assert context.topics.primary.name == "greeting"
    assert context.topics.primary.confidence == "high"


def test_detect_farewell() -> None:
    detector = TopicDetector()
    context = detector.detect(_make_context("Adiós, hasta luego"))
    assert context.topics is not None
    assert context.topics.primary is not None
    assert context.topics.primary.name == "farewell"


def test_detect_purchase() -> None:
    detector = TopicDetector()
    context = detector.detect(_make_context("¿Cuánto cuesta?"))
    assert context.topics is not None
    assert context.topics.primary is not None
    assert context.topics.primary.name == "purchase"


def test_detect_support() -> None:
    detector = TopicDetector()
    context = detector.detect(_make_context("Necesito ayuda con esto"))
    assert context.topics is not None
    assert context.topics.primary is not None
    assert context.topics.primary.name == "support"


def test_detect_information() -> None:
    detector = TopicDetector()
    context = detector.detect(_make_context("¿Cuál es el horario de atención?"))
    assert context.topics is not None
    assert context.topics.primary is not None
    assert context.topics.primary.name == "information"


def test_detect_multiple_topics() -> None:
    detector = TopicDetector()
    context = detector.detect(_make_context("Hola, ¿cuánto cuesta este producto?"))
    assert context.topics is not None
    assert context.topics.primary is not None
    assert context.topics.primary.name == "greeting"
    assert len(context.topics.secondary) == 1
    assert context.topics.secondary[0].name == "purchase"


def test_detect_no_match_returns_general() -> None:
    detector = TopicDetector()
    context = detector.detect(_make_context("xyz123"))
    assert context.topics is not None
    assert context.topics.primary is not None
    assert context.topics.primary.name == "general"
    assert context.topics.primary.confidence == "medium"


def test_detect_preserves_context() -> None:
    detector = TopicDetector()
    original = _make_context("Hola")
    enriched = detector.detect(original)
    assert enriched.message.content == original.message.content
    assert enriched.message.customer_id == original.message.customer_id
    assert enriched.message.company_id == original.message.company_id
    assert enriched.topics is not None


def test_detect_question_without_keywords_returns_information() -> None:
    detector = TopicDetector()
    context = detector.detect(_make_context("¿Cómo hago para contactarlos?"))
    assert context.topics is not None
    assert context.topics.primary is not None
    assert context.topics.primary.name == "information"


def test_detect_empty_content_returns_general() -> None:
    detector = TopicDetector()
    message = ConversationMessage(content="xyz", customer_id="c1", company_id="co1")
    context = detector.detect(ConversationContext(message=message))
    assert context.topics is not None
    assert context.topics.primary is not None
    assert context.topics.primary.name == "general"


def test_detect_complaint() -> None:
    detector = TopicDetector()
    context = detector.detect(_make_context("Tengo un problema con el servicio"))
    assert context.topics is not None
    assert context.topics.primary is not None
    assert context.topics.primary.name == "complaint"
