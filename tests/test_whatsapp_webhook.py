from app.main import create_app
from fastapi.testclient import TestClient

WHATSAPP_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "123456789",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "15551234567",
                            "phone_number_id": "company-phone-id",
                        },
                        "contacts": [
                            {
                                "profile": {"name": "John Doe"},
                                "wa_id": "15557654321",
                            }
                        ],
                        "messages": [
                            {
                                "from": "15557654321",
                                "id": "wamid.ABC123",
                                "timestamp": "1712345678",
                                "text": {"body": "Hola, buenos días"},
                                "type": "text",
                            }
                        ],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}


def test_whatsapp_webhook_get_verification_success() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "botwa_verify_token",
            "hub.challenge": "987654321",
        },
    )

    assert response.status_code == 200
    assert response.text == "987654321"


def test_whatsapp_webhook_get_verification_wrong_token() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "987654321",
        },
    )

    assert response.status_code == 403


def test_whatsapp_webhook_get_verification_wrong_mode() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "unsubscribe",
            "hub.verify_token": "botwa_verify_token",
            "hub.challenge": "987654321",
        },
    )

    assert response.status_code == 403


def test_whatsapp_webhook_post_message() -> None:
    client = TestClient(create_app())

    response = client.post("/webhooks/whatsapp", json=WHATSAPP_PAYLOAD)

    assert response.status_code == 200
    assert response.text == "OK"


def test_whatsapp_webhook_post_no_text_message() -> None:
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456789",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15551234567",
                                "phone_number_id": "company-phone-id",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Jane"},
                                    "wa_id": "15551112222",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "15551112222",
                                    "id": "wamid.DEF456",
                                    "timestamp": "1712345679",
                                    "type": "image",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    client = TestClient(create_app())
    response = client.post("/webhooks/whatsapp", json=payload)

    assert response.status_code == 200
    assert response.text == "OK"


def test_whatsapp_webhook_post_empty_payload() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/webhooks/whatsapp",
        json={
            "object": "whatsapp_business_account",
            "entry": [],
        },
    )

    assert response.status_code == 200
    assert response.text == "OK"


def test_whatsapp_message_integration() -> None:
    """Verify WhatsApp message flows through the core and returns OK."""
    client = TestClient(create_app())

    response = client.post("/webhooks/whatsapp", json=WHATSAPP_PAYLOAD)

    assert response.status_code == 200
    assert response.text == "OK"
