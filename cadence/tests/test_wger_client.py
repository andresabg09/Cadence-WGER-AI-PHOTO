import httpx
from fastapi.testclient import TestClient

from app import main
from app.wger_client import WgerClient


def client_with(handler) -> WgerClient:
    wger = WgerClient("http://wger", "token")
    wger._client = httpx.Client(base_url="http://wger", transport=httpx.MockTransport(handler))
    return wger


def test_search_uses_ingredientinfo_and_returns_inline_energy():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v2/ingredientinfo/"
        assert request.url.params["name__search"] == "chicken"
        assert request.url.params["language__code"] == "en"
        return httpx.Response(200, json={"results": [{"id": 7, "name": "Chicken", "energy": 165, "image": None}]})

    assert client_with(handler).search_ingredients("chicken") == [
        {"id": 7, "name": "Chicken", "image": None, "energy": 165}
    ]


def test_search_falls_back_to_legacy_endpoint_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/ingredientinfo/":
            return httpx.Response(404)
        return httpx.Response(200, json={"suggestions": [{"value": "Rice", "data": {"id": 2, "name": "Rice"}}]})

    assert client_with(handler).search_ingredients("rice")[0]["id"] == 2


def test_wger_failures_become_readable_502(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    monkeypatch.setattr(main.settings, "wger_api_token", "x")
    monkeypatch.setattr(main, "get_wger_client", lambda: client_with(handler))
    response = TestClient(main.app).get("/api/today")
    assert response.status_code == 502
    assert "WGER_API_TOKEN" in response.json()["detail"]
