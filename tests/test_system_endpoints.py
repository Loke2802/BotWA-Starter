from app.main import create_app
from fastapi.testclient import TestClient


def test_health_check() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/version")

    assert response.status_code == 200
    assert response.json()["app_name"] == "BotWA Starter"
    assert response.json()["api_version"] == "v1"
    assert response.json()["build_sha"] is None
    assert "environment" not in response.json()
