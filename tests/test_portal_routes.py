from app.main import create_app
from fastapi.testclient import TestClient


def test_portal_shell_and_assets_are_served() -> None:
    client = TestClient(create_app())

    page = client.get("/portal")
    stylesheet = client.get("/portal/assets/portal.css")
    script = client.get("/portal/assets/portal.js")
    conversations = client.get("/portal/assets/conversations.js")
    opportunities = client.get("/portal/assets/opportunities.js")
    follow_up = client.get("/portal/assets/follow-up.js")

    assert page.status_code == 200
    assert "Bienvenido a Luri" in page.text
    assert stylesheet.status_code == 200
    assert "app-shell" in stylesheet.text
    assert "[hidden] { display: none !important; }" in stylesheet.text
    assert script.status_code == 200
    assert "startWorkspace" in script.text
    assert conversations.status_code == 200
    assert "/portal/assets/conversations.js" in page.text
    assert opportunities.status_code == 200
    assert "/portal/assets/opportunities.js" in page.text
    assert client.get("/portal/assets/opportunity-history.js").status_code == 200
    assert "/portal/assets/opportunity-history.js" in page.text
    assert follow_up.status_code == 200
    assert "/portal/assets/follow-up.js" in page.text
    assert 'data-view="follow-up"' in page.text

    for asset, view in [
        ("board.js", "board"),
        ("stages.js", "stages"),
        ("commercial-report.js", "commercial-report"),
    ]:
        assert client.get(f"/portal/assets/{asset}").status_code == 200
        assert f"/portal/assets/{asset}" in page.text
        assert f'data-view="{view}"' in page.text

    assert client.get("/portal/assets/customer-workspace.js").status_code == 200
    assert "/portal/assets/customer-workspace.js" in page.text
