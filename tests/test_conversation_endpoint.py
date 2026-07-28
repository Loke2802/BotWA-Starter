from app.main import create_app
from fastapi.testclient import TestClient


def test_conversation_message_endpoint() -> None:
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
    assert "Hola" in data["message"]


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
