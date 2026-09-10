from app.main import create_app
from fastapi.testclient import TestClient


def test_portal_shell_and_assets_are_served() -> None:
    client = TestClient(create_app())

    page = client.get("/portal")
    stylesheet = client.get("/portal/assets/portal.css")
    script = client.get("/portal/assets/portal.js")

    assert page.status_code == 200
    assert "Bienvenido a Luri" in page.text
    assert stylesheet.status_code == 200
    assert "app-shell" in stylesheet.text
    assert "[hidden] { display: none !important; }" in stylesheet.text
    assert script.status_code == 200
    assert "startWorkspace" in script.text
