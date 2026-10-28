"""The administrator can follow how everyone is doing (numbers) and open one person's day READ-ONLY; nobody else can, and chats stay private."""

import json

import pytest

from app import coach, store
from app.meals import local_now
from tests.test_accounts import SharedWger, new_client, register
from tests.test_block14 import StubGemini  # noqa: F401  (same fake model)

pytestmark = pytest.mark.anonymous


@pytest.fixture
def wger(monkeypatch):
    from app import main

    fake = SharedWger()
    monkeypatch.setattr(main, "get_wger_client", lambda: fake)
    return fake


def _two_people(wger):
    admin, ana = new_client(), new_client()
    register(admin, "admin@example.com", name="Andrés")
    register(ana, "ana@example.com", admin.post("/api/admin/invites", json={}).json()["code"], name="Ana")
    ana.post("/api/confirm", json={"items": [{"ingredient_id": 5, "amount_grams": 200}], "meal": "almuerzo"})
    return admin, ana


def test_the_overview_counts_what_each_person_has_done(wger):
    admin, ana = _two_people(wger)
    people = {u["name"]: u for u in admin.get("/api/admin/overview").json()["users"]}
    assert people["Ana"]["entries"] == 1 and people["Ana"]["last_meal_day"] == local_now().date().isoformat()
    assert people["Ana"]["photos"] == 0 and people["Ana"]["weights"] == 0 and people["Ana"]["last_login"]
    assert people["Andrés"]["entries"] == 0
    assert {"onboarded", "welcome_pending", "review_pending"} <= set(people["Ana"])


def test_the_administrator_opens_a_day_read_only_and_it_is_logged(wger):
    admin, ana = _two_people(wger)
    ana_id = next(u["id"] for u in admin.get("/api/admin/overview").json()["users"] if u["name"] == "Ana")
    day = admin.get(f"/api/admin/users/{ana_id}/day").json()
    assert day["user"]["name"] == "Ana" and day["totals"]["kcal"] == 260
    assert day["meals"][0]["items"][0]["name"] == "Arroz" and day["meals"][0]["items"][0]["grams"] == 200
    assert [v["what"] for v in store.admin_views_of(ana_id)] == [f"day:{day['date']}"]
    assert admin.get(f"/api/admin/users/{ana_id}/day?date=2020-01-01").json()["totals"]["kcal"] == 0
    assert admin.get(f"/api/admin/users/{ana_id}/day?date=ayer").status_code == 400
    assert admin.get("/api/admin/users/9999/day").status_code == 404


def test_only_the_administrator_can_look(wger):
    admin, ana = _two_people(wger)
    admin_id = admin.get("/api/auth/me").json()["id"]
    assert ana.get(f"/api/admin/users/{admin_id}/day").status_code == 403
    assert ana.get("/api/admin/overview").status_code == 403
    assert new_client().get(f"/api/admin/users/{admin_id}/day").status_code == 401


def test_chats_never_reach_the_administrators_view(wger, monkeypatch):
    admin, ana = _two_people(wger)
    stub = StubGemini("Claro, te explico.")
    monkeypatch.setattr(coach, "_client", lambda: stub)
    ana.post("/api/assistant", json={"history": [{"role": "user", "text": "algo muy personal sobre mi salud"}]})
    ana_id = next(u["id"] for u in admin.get("/api/admin/overview").json()["users"] if u["name"] == "Ana")
    seen = json.dumps([admin.get("/api/admin/overview").json(), admin.get(f"/api/admin/users/{ana_id}/day").json()])
    assert "personal" not in seen and "te explico" not in seen
    assert admin.get("/api/chats").json() == []  # and the admin's own chat list is only the admin's


def test_view_as_shows_how_the_person_is_doing_read_only_and_logs_it(wger):
    admin, ana = _two_people(wger)
    ana_id = next(u["id"] for u in admin.get("/api/admin/overview").json()["users"] if u["name"] == "Ana")
    view = admin.get(f"/api/admin/users/{ana_id}/view").json()
    assert view["user"]["name"] == "Ana" and view["stats"]["entries"] == 1
    assert view["progress"]["streak_current"] == 1 and len(view["progress"]["days"]) == 28
    assert {"today", "week", "analyze_limit", "chat_limit"} <= set(view["ai"])
    assert all({"tone", "text"} <= set(a) for a in view["attention"])
    assert "view" in [v["what"] for v in store.admin_views_of(ana_id)]
    assert admin.get("/api/admin/users/9999/view").status_code == 404
    # it looks, it never signs in as her: the administrator is still the administrator
    assert admin.get("/api/auth/me").json()["name"] == "Andrés"


def test_view_as_is_for_the_administrator_only_and_never_shows_chats(wger, monkeypatch):
    admin, ana = _two_people(wger)
    admin_id = admin.get("/api/auth/me").json()["id"]
    assert ana.get(f"/api/admin/users/{admin_id}/view").status_code == 403
    assert new_client().get(f"/api/admin/users/{admin_id}/view").status_code == 401
    monkeypatch.setattr(coach, "_client", lambda: StubGemini("Claro, te explico."))
    ana.post("/api/assistant", json={"history": [{"role": "user", "text": "algo muy personal sobre mi salud"}]})
    ana_id = next(u["id"] for u in admin.get("/api/admin/overview").json()["users"] if u["name"] == "Ana")
    seen = json.dumps(admin.get(f"/api/admin/users/{ana_id}/view").json())
    assert "personal" not in seen and "te explico" not in seen
    # it counts how often she used the AI (that is what runs out), not what she wrote
    assert admin.get(f"/api/admin/users/{ana_id}/view").json()["ai"]["today"]["chats"] == 1
    people = {u["name"]: u for u in admin.get("/api/admin/overview").json()["users"]}
    assert people["Ana"]["ai_today"]["chats"] == 1


def test_view_as_flags_what_is_wrong(wger):
    admin, ana = _two_people(wger)
    carla = new_client()
    register(carla, "carla@example.com", admin.post("/api/admin/invites", json={}).json()["code"], name="Carla")
    carla_id = next(u["id"] for u in admin.get("/api/admin/overview").json()["users"] if u["name"] == "Carla")
    texts = " ".join(a["text"] for a in admin.get(f"/api/admin/users/{carla_id}/view").json()["attention"])
    assert "primer uso" in texts  # a new account that has not finished the welcome says so
