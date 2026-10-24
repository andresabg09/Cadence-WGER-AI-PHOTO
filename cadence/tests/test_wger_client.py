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


def test_diagnostics_lists_every_missing_piece(monkeypatch):
    from app import diagnostics

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/nutritionplan/":
            return httpx.Response(200, json={"results": []})
        if request.url.path == "/api/v2/ingredientinfo/":
            return httpx.Response(200, json={"results": []})
        return httpx.Response(200, json={})

    monkeypatch.setattr(diagnostics.settings, "wger_api_token", "x")
    monkeypatch.setattr(diagnostics.settings, "gemini_api_key", "y")
    report = diagnostics.run_diagnostics(client_with(handler))
    failed = {c["name"] for c in report["checks"] if not c["ok"]}
    assert report["ok"] is False
    assert failed == {"wger tiene ingredientes cargados"}  # a missing plan is not a failure: cadence creates it
    assert all(c["fix"] for c in report["checks"] if not c["ok"])


def _stub_wger(monkeypatch, handler):
    monkeypatch.setattr(main.settings, "wger_api_token", "x")
    monkeypatch.setattr(main, "get_wger_client", lambda: client_with(handler))


def test_confirm_stamps_entries_inside_the_chosen_meal(monkeypatch):
    posted = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            import json

            posted.append(json.loads(request.content))
            return httpx.Response(201, json={"id": 55})
        return httpx.Response(200, json={"results": [{"id": 1}]})

    _stub_wger(monkeypatch, handler)
    response = TestClient(main.app).post(
        "/api/confirm",
        json={"items": [{"ingredient_id": 3, "amount_grams": 120}], "meal": "desayuno"},
    )
    assert response.status_code == 200
    assert posted and posted[0]["plan"] == 1 and posted[0]["ingredient"] == 3
    from app.meals import meal_key_for_entry

    assert meal_key_for_entry(posted[0]) == "desayuno"


def test_wger_status_reports_reachability(monkeypatch):
    main._wger_status_cache.update(at=0.0, value=None)
    _stub_wger(monkeypatch, lambda request: httpx.Response(200, json={"results": []}))
    assert TestClient(main.app).get("/api/wger-status").json() == {"ok": True, "detail": None}

    main._wger_status_cache.update(at=0.0, value=None)
    _stub_wger(monkeypatch, lambda request: httpx.Response(500))
    assert TestClient(main.app).get("/api/wger-status").json()["ok"] is False


def test_deep_diagnostics_writes_and_deletes_a_test_entry():
    from app import diagnostics

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/v2/nutritionplan/":
            return httpx.Response(200, json={"results": [{"id": 4}]})
        if request.url.path == "/api/v2/ingredientinfo/":
            return httpx.Response(200, json={"results": [{"id": 9, "name": "Chicken", "energy": 165}]})
        if request.method == "POST":
            return httpx.Response(201, json={"id": 77})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"results": []})

    report = diagnostics.run_diagnostics(client_with(handler), deep=True)
    write = next(c for c in report["checks"] if c["name"].startswith("Registrar y borrar"))
    assert write["ok"] is True
    assert ("DELETE", "/api/v2/nutritiondiary/77/") in calls


def test_confirm_creates_the_plan_when_wger_has_none(monkeypatch):
    posted = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        if request.method == "POST" and request.url.path == "/api/v2/nutritionplan/":
            posted.append(json.loads(request.content))
            return httpx.Response(201, json={"id": 8})
        if request.method == "POST":
            posted.append(json.loads(request.content))
            return httpx.Response(201, json={"id": 90})
        return httpx.Response(200, json={"results": []})

    _stub_wger(monkeypatch, handler)
    response = TestClient(main.app).post("/api/confirm", json={"items": [{"ingredient_id": 3, "amount_grams": 50}]})
    assert response.status_code == 200
    assert posted[0]["description"] == "cadence"
    assert posted[1]["plan"] == 8


def test_today_with_no_plan_is_an_empty_day_not_an_error(monkeypatch):
    _stub_wger(monkeypatch, lambda request: httpx.Response(200, json={"results": []}))
    body = TestClient(main.app).get("/api/today").json()
    assert body["meals"] == [] and body["streak_days"] == 0 and body["goal"]["kcal"] > 0


def test_unexpected_errors_report_their_cause(monkeypatch):
    def boom(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")  # wger answering HTML

    _stub_wger(monkeypatch, boom)
    response = TestClient(main.app, raise_server_exceptions=False).post(
        "/api/confirm", json={"items": [{"ingredient_id": 3, "amount_grams": 50}]}
    )
    assert response.status_code == 500
    assert "Error interno" in response.json()["detail"]


def test_today_survives_an_unreadable_plan_and_missing_ingredient(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v2/nutritionplan/":
            return httpx.Response(200, json={"results": [{"id": 4}]})
        if path == "/api/v2/nutritionplan/4/":
            return httpx.Response(500)
        if path == "/api/v2/nutritiondiary/":
            from app.meals import local_now

            return httpx.Response(200, json={"results": [
                {"id": 1, "plan": 4, "ingredient": 9, "amount": "50.00", "datetime": local_now().isoformat()}]})
        return httpx.Response(404)  # ingredient detail gone

    _stub_wger(monkeypatch, handler)
    body = TestClient(main.app).get("/api/today").json()
    assert body["goal"]["kcal"] > 0
    items = [i for m in body["meals"] for i in m["items"]]
    assert items and items[0]["name"] == "(alimento no disponible)"
