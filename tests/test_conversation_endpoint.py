from app.main import create_app
from fastapi.testclient import TestClient


def test_conversation_message_endpoint() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/conversation/message",
        json={
            "content": "Hello",
            "customer_id": "customer-1",
            "company_id": "company-1",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "accepted",
        "message": "Gracias por tu mensaje. Estamos procesando tu solicitud.",
    }


def test_conversation_message_endpoint_rejects_empty_content() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/conversation/message",
        json={
            "content": "",
            "customer_id": "customer-1",
            "company_id": "company-1",
        },
    )

    assert response.status_code == 422
