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

    found = client_with(handler).search_ingredients("chicken")
    assert [(f["id"], f["name"], f["energy"]) for f in found] == [(7, "Chicken", 165)]


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


def test_confirm_creates_the_plan_when_wger_has_none(monkeypatch, signed_in):
    from app import store

    store.update_user(signed_in.id, plan_id=None)  # a user who has not logged anything yet
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
    assert posted[0]["description"] == f"cadence:{signed_in.id}"  # one plan per person
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


def test_diary_ids_may_be_uuids(monkeypatch):
    """Field test: this wger returns UUID ids for diary entries; they must pass through as text."""
    entry_id = "01a16c5a-ce16-7cdc-a3f0-b506bc3690f9"
    deleted = []

    def handler(request: httpx.Request) -> httpx.Response:
        from app.meals import local_now

        path = request.url.path
        if request.method == "POST":
            return httpx.Response(201, json={"id": entry_id})
        if request.method == "DELETE":
            deleted.append(path)
            return httpx.Response(204)
        if path == "/api/v2/nutritionplan/":
            return httpx.Response(200, json={"results": [{"id": "p-1", "creation_date": "2026-10-01"}, {"id": "p-2", "creation_date": "2026-10-20"}]})
        if path == "/api/v2/nutritionplan/p-2/":
            return httpx.Response(200, json={"id": "p-2", "goal_energy": None})
        if path == "/api/v2/nutritiondiary/":
            return httpx.Response(200, json={"results": [{"id": entry_id, "plan": "p-2", "ingredient": 9, "amount": "50.00", "datetime": local_now().isoformat()}]})
        return httpx.Response(200, json={"id": 9, "name": "Vanilla ice cream", "energy": 200})

    _stub_wger(monkeypatch, handler)
    client = TestClient(main.app)

    saved = client.post("/api/confirm", json={"items": [{"ingredient_id": 9, "amount_grams": 50}]})
    assert saved.status_code == 200 and saved.json()["created"][0]["diary_entry_id"] == entry_id

    today = client.get("/api/today").json()
    assert [i["diary_entry_id"] for m in today["meals"] for i in m["items"]] == [entry_id]

    assert client.delete(f"/api/diary/{entry_id}").status_code == 200
    assert deleted == [f"/api/v2/nutritiondiary/{entry_id}/"]


def test_meal_suggestion_uses_the_photo_time_and_clamps_the_future():
    client = TestClient(main.app)
    # a lunch photo (naive EXIF time = the user's clock) uploaded at night still suggests lunch
    assert client.get("/api/meal-now", params={"at": "2026-10-20T13:05:00"}).json()["meal"] == "almuerzo"
    assert client.get("/api/meal-now", params={"at": "2026-10-20T07:40:00"}).json()["meal"] == "desayuno"
    # an absolute instant is converted to the local zone: 01:30Z is 20:30 the day before in Panama
    assert client.get("/api/meal-now", params={"at": "2026-10-21T01:30:00Z"}).json()["meal"] == "cena"
    # garbage / future -> falls back to now (never later than now)
    bad = client.get("/api/meal-now", params={"at": "mañana"}).json()
    future = client.get("/api/meal-now", params={"at": "2999-01-01T12:00:00"}).json()
    assert bad["meal"] == future["meal"] and future["at"].startswith(local_today_prefix())


def local_today_prefix() -> str:
    from app.meals import local_now

    return local_now().date().isoformat()


def test_confirm_stamps_the_photo_day_inside_the_chosen_meal(monkeypatch):
    import json

    posted = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(json.loads(request.content))
            return httpx.Response(201, json={"id": "uuid-1"})
        return httpx.Response(200, json={"results": [{"id": 1}]})

    _stub_wger(monkeypatch, handler)
    client = TestClient(main.app)
    base = {"items": [{"ingredient_id": 3, "amount_grams": 80}], "taken_at": "2026-10-20T13:05:00"}

    # lunch photo, kept as lunch: exact photo time, on the photo's day
    client.post("/api/confirm", json={**base, "meal": "almuerzo"})
    assert posted[-1]["datetime"].startswith("2026-10-20T13:05:00")

    # same photo, the user says it was dinner: that day, middle of the dinner window
    client.post("/api/confirm", json={**base, "meal": "cena"})
    assert posted[-1]["datetime"].startswith("2026-10-20T20:00:00")

    # no taken_at (manual add): today
    client.post("/api/confirm", json={"items": base["items"], "meal": "almuerzo"})
    assert posted[-1]["datetime"][:10] == local_today_prefix()


def test_analyze_offers_the_ready_to_eat_staple_in_spanish(monkeypatch):
    from app.schemas import DetectedComponent

    class StubVision:
        def identify_components(self, image_bytes, mime):
            return [DetectedComponent(name="arroz blanco", search_name="cooked white rice", confidence=0.9, estimated_grams=150,
                                      box=[0.1, 0.2, 0.3, 0.4])]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/ingredientinfo/" and request.url.params.get("source_name") == "cadence":
            staples = [
                {"id": 2, "name": "Cooked white rice", "energy": 130, "protein": 2.7, "carbohydrates": 28.2, "fat": 0.3, "source_name": "cadence"},
                {"id": 3, "name": "Arroz blanco cocido", "energy": 130, "protein": 2.7, "carbohydrates": 28.2, "fat": 0.3, "source_name": "cadence"},
            ]
            return httpx.Response(200, json={"results": staples})
        if request.url.path == "/api/v2/ingredientinfo/":
            dry = {"id": 1, "name": "White Rice", "energy": 340, "protein": 7, "carbohydrates": 79, "fat": 0.6, "source_name": "USDA"}
            return httpx.Response(200, json={"results": [dry]})
        return httpx.Response(404)

    main._staples_cache.update(at=float("-inf"), items=[])
    _stub_wger(monkeypatch, handler)
    monkeypatch.setattr(main, "get_vision_client", lambda: StubVision())
    response = TestClient(main.app).post("/api/analyze", files={"image": ("plate.jpg", b"fake-bytes", "image/jpeg")})
    assert response.status_code == 200
    component = response.json()["components"][0]
    assert component["estimated_grams"] == 150 and component["box"] == [0.1, 0.2, 0.3, 0.4]
    names = [c["name"] for c in component["candidates"]]
    assert names[0] == "Arroz blanco cocido" and component["candidates"][0]["energy_kcal_100g"] == 130
    assert not ({"Cooked white rice"} & set(names[:1])) and names.count("Cooked white rice") + names.count("Arroz blanco cocido") == 1


def _http(internal_handler, public_handler):
    from app.wger_client import _Http
    return _Http(httpx.Client(base_url="http://public", transport=httpx.MockTransport(public_handler)),
                 httpx.Client(base_url="http://nginx", transport=httpx.MockTransport(internal_handler)))


def test_internal_route_is_used_and_falls_back_to_the_public_address():
    seen = []

    def internal_ok(request):
        seen.append("internal")
        return httpx.Response(200, json={"ok": True})

    def public(request):
        seen.append("public")
        return httpx.Response(200, json={"ok": True})

    http = _http(internal_ok, public)
    http.get("/x"); http.get("/x")
    assert seen == ["internal", "internal"]

    def refused(request):
        raise httpx.ConnectError("no route")

    seen.clear()
    http = _http(refused, public)
    assert http.get("/x").status_code == 200 and http.get("/x").status_code == 200
    assert seen == ["public", "public"]  # remembered: not retried on every call


def test_internal_route_that_answers_like_a_wrong_door_is_dropped_on_first_use():
    seen = []
    http = _http(lambda r: (seen.append("internal"), httpx.Response(400))[1], lambda r: (seen.append("public"), httpx.Response(200, json={}))[1])
    assert http.get("/x").status_code == 200
    assert seen == ["internal", "public"]


def test_ingredient_reads_are_remembered_and_diary_reads_follow_writes(monkeypatch):
    from app import main, store
    calls = {"ingredient": 0, "diary": 0}

    def handler(request):
        if request.url.path.startswith("/api/v2/ingredient/"):
            calls["ingredient"] += 1
            return httpx.Response(200, json={"id": 5, "name": "Arroz", "energy": 130})
        if request.url.path == "/api/v2/nutritiondiary/":
            calls["diary"] += 1
            return httpx.Response(200, json={"results": []})
        return httpx.Response(404)

    wger = client_with(handler)
    wger.get_ingredient(5); wger.get_ingredient(5)
    assert calls["ingredient"] == 1

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    me = type("U", (), {"id": 77})()
    main.user_entries(wger, me, 1, now - timedelta(days=1), now)
    main.user_entries(wger, me, 1, now - timedelta(days=1), now)
    assert calls["diary"] == 1  # second read came from memory
    main.invalidate_entries(77)
    main.user_entries(wger, me, 1, now - timedelta(days=1), now)
    assert calls["diary"] == 2  # a write cleared it
