from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_web_page_and_assets_are_served() -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "AWS 经营问数" in page.text

    stylesheet = client.get("/styles.css")
    script = client.get("/app.js")
    assert stylesheet.status_code == 200
    assert script.status_code == 200
    assert "#ask-form" in script.text


def test_ask_rejects_empty_question() -> None:
    response = client.post("/ask", json={"question": ""})
    assert response.status_code == 422
