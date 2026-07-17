from app.core.business.policy import BusinessPolicy


def test_policy_returns_greeting_response() -> None:
    policy = BusinessPolicy()
    response = policy.get_response("greeting")

    assert response["status"] == "accepted"
    assert response["confidence"] == "high"
    assert "Hola" in response["message"]


def test_policy_returns_unknown_response() -> None:
    policy = BusinessPolicy()
    response = policy.get_response("unknown")

    assert response["status"] == "accepted"
    assert response["confidence"] == "low"


def test_policy_returns_needs_knowledge_for_question() -> None:
    policy = BusinessPolicy()
    response = policy.get_response("question")

    assert response["needs_knowledge"] is True


def test_policy_returns_no_knowledge_for_greeting() -> None:
    policy = BusinessPolicy()
    response = policy.get_response("greeting")

    assert response["needs_knowledge"] is False
