from app.core.business.intent_classifier import IntentClassifier


def test_classify_greeting() -> None:
    classifier = IntentClassifier()
    assert classifier.classify("Hola, buenos días") == "greeting"


def test_classify_farewell() -> None:
    classifier = IntentClassifier()
    assert classifier.classify("Adiós, hasta luego") == "farewell"


def test_classify_price_inquiry() -> None:
    classifier = IntentClassifier()
    assert classifier.classify("¿Cuánto cuesta?") == "price_inquiry"


def test_classify_thanks() -> None:
    classifier = IntentClassifier()
    assert classifier.classify("Muchas gracias") == "thanks"


def test_classify_support() -> None:
    classifier = IntentClassifier()
    assert classifier.classify("Tengo un problema con el sistema") == "support"


def test_classify_question_with_keyword() -> None:
    classifier = IntentClassifier()
    result = classifier.classify("¿Cuál es el precio?")
    assert result == "price_inquiry"


def test_classify_question_without_keyword() -> None:
    classifier = IntentClassifier()
    assert classifier.classify("¿Cómo funciona?") == "question"


def test_classify_unknown() -> None:
    classifier = IntentClassifier()
    assert classifier.classify("xyz123") == "unknown"


def test_classify_empty_returns_unknown() -> None:
    classifier = IntentClassifier()
    assert classifier.classify("") == "unknown"
