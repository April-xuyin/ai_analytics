from fastapi.testclient import TestClient

from app.api import main
from app.auth import authenticate

client = TestClient(main.app)


def test_ask_requires_api_token_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    response = client.post("/ask", json={"question": "测试"})
    assert response.status_code == 401


def test_health_does_not_require_api_token(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "test-token")
    response = client.get("/health")
    assert response.status_code == 200


def test_operator_token_gets_configured_shop_scope(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_API_TOKEN", "operator-token")
    monkeypatch.setenv("OPERATOR_SHOPS", "CuspinArtGallery-US, VG Artisan-US")
    principal = authenticate("operator-token")
    assert principal is not None
    assert principal.role == "operator"
    assert principal.shops == ("CuspinArtGallery-US", "VG Artisan-US")


def test_metrics_requires_admin_token(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_TOKEN", "admin-token")
    monkeypatch.setenv("OPERATOR_API_TOKEN", "operator-token")
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"X-API-Key": "operator-token"}).status_code == 403
    response = client.get("/metrics", headers={"X-API-Key": "admin-token"})
    assert response.status_code == 200
    assert "vg_http_requests_total" in response.text


def test_me_returns_operator_scope(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_API_TOKEN", "operator-token")
    monkeypatch.setenv("OPERATOR_SHOPS", "CuspinArtGallery-US")
    response = client.get("/me", headers={"X-API-Key": "operator-token"})
    assert response.status_code == 200
    assert response.json() == {
        "name": "operator", "role": "operator", "shops": ["CuspinArtGallery-US"]
    }
