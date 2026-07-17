"""Vertical Slice 1: end-to-end integration tests.

Validates the complete flow:
  POST /messages
  -> Conversation Engine
  -> Business Brain (IntentClassifier -> DecisionEngine)
  -> Knowledge Engine (when policy requires)
  -> Business Brain
  -> Conversation Engine
  -> Response
"""

from app.main import create_app
from fastapi.testclient import TestClient


def test_vs1_greeting_flow() -> None:
    """Greeting intent: CE -> BB -> CE, no knowledge needed."""
    client = TestClient(create_app())

    response = client.post(
        "/messages",
        json={
            "content": "Hola, buenos días",
            "customer_id": "customer-1",
            "company_id": "company-1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert "Hola" in data["message"]


def test_vs1_farewell_flow() -> None:
    """Farewell intent: CE -> BB -> CE, no knowledge needed."""
    client = TestClient(create_app())

    response = client.post(
        "/messages",
        json={
            "content": "Adiós, hasta luego",
            "customer_id": "customer-1",
            "company_id": "company-1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert "Gracias" in data["message"]


def test_vs1_knowledge_horario_flow() -> None:
    """Question with knowledge match: CE -> BB -> KE -> BB -> CE.

    'horario' matches InMemoryKnowledgeProvider -> returns business hours.
    """
    client = TestClient(create_app())

    response = client.post(
        "/messages",
        json={
            "content": "¿Cuál es el horario de atención?",
            "customer_id": "customer-1",
            "company_id": "company-1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert "horario" in data["message"].lower()
    assert "lunes a viernes" in data["message"].lower()


def test_vs1_knowledge_envio_flow() -> None:
    """Knowledge match for envío."""
    client = TestClient(create_app())

    response = client.post(
        "/messages",
        json={
            "content": "¿Hacen envíos a domicilio?",
            "customer_id": "customer-1",
            "company_id": "company-1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "envío" in data["message"].lower()


def test_vs1_knowledge_pago_flow() -> None:
    """Knowledge match for métodos de pago."""
    client = TestClient(create_app())

    response = client.post(
        "/messages",
        json={
            "content": "¿Qué métodos de pago aceptan?",
            "customer_id": "customer-1",
            "company_id": "company-1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "tarjetas" in data["message"].lower()


def test_vs1_knowledge_fallback_flow() -> None:
    """Question without knowledge match: policy fallback when KE returns nothing."""
    client = TestClient(create_app())

    response = client.post(
        "/messages",
        json={
            "content": "¿Cómo hago para contactarlos?",
            "customer_id": "customer-1",
            "company_id": "company-1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert (
        data["message"] == "Déjame revisar la información para responder tu consulta."
    )


def test_vs1_unknown_flow() -> None:
    """Unknown intent: CE -> BB -> CE, fallback to policy default."""
    client = TestClient(create_app())

    response = client.post(
        "/messages",
        json={
            "content": "xyz123",
            "customer_id": "customer-1",
            "company_id": "company-1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert data["message"] == "Gracias por tu mensaje. Estamos procesando tu solicitud."


def test_vs1_empty_content_rejected() -> None:
    """Validation: empty content is rejected at the contract level."""
    client = TestClient(create_app())

    response = client.post(
        "/messages",
        json={
            "content": "",
            "customer_id": "customer-1",
            "company_id": "company-1",
        },
    )

    assert response.status_code == 422


def test_vs1_original_endpoint_also_works() -> None:
    """The original /conversation/message endpoint remains functional."""
    client = TestClient(create_app())

    response = client.post(
        "/conversation/message",
        json={
            "content": "Hola",
            "customer_id": "customer-1",
            "company_id": "company-1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"


def test_vs1_price_inquiry_knowledge_flow() -> None:
    """Price inquiry: classified as price_inquiry, needs_knowledge=True.

    'cuánto cuesta' matches price_inquiry keywords.
    No knowledge item matches 'cuánto cuesta' -> falls back to policy.
    """
    client = TestClient(create_app())

    response = client.post(
        "/messages",
        json={
            "content": "¿Cuánto cuesta?",
            "customer_id": "customer-1",
            "company_id": "company-1",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"
    assert (
        data["message"]
        == "Gracias por tu interés. Un asesor te contactará con los precios."
    )
