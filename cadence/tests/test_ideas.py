"""Block 12: favourites ("repetir una comida") and ideas to complete the day. The model only names things: calories come from the catalog."""

from datetime import timedelta

import pytest

from app import main, store
from app.meals import local_now
from tests.test_foods import CatalogWger, two_people

pytestmark = pytest.mark.anonymous


@pytest.fixture
def wger(monkeypatch):
    fake = CatalogWger()
    monkeypatch.setattr(main, "get_wger_client", lambda: fake)
    main._ideas_cache.clear()
    return fake


class Thinker:
    def __init__(self, ideas=None):
        self.calls = []
        self.ideas = ideas if ideas is not None else [
            {"name": "Pan con aguacate", "tag": "Rápida", "items": [
                {"name": "pan de la abuela", "search_name": "grandma bread", "search_alternatives": [], "grams": 100},
                {"name": "aguacate casero", "search_name": "home avocado", "search_alternatives": [], "grams": 60}]},
            {"name": "Algo inventado", "tag": None, "items": [
                {"name": "pan de la abuela", "search_name": "grandma bread", "search_alternatives": [], "grams": 50},
                {"name": "zzzxxqq", "search_name": "zzzxxqq", "search_alternatives": [], "grams": 50}]},
        ]

    def suggest_meals(self, **kwargs):
        self.calls.append(kwargs)
        return self.ideas


def foods(client):
    bread = client.post("/api/foods", json={"name": "Pan de la abuela", "kcal": 280, "protein": 8, "carbs": 50, "fat": 4}).json()
    avocado = client.post("/api/foods", json={"name": "Aguacate casero", "kcal": 160, "protein": 2, "carbs": 9, "fat": 15}).json()
    return bread, avocado


def test_favorites_are_the_meals_repeated_most_and_private(wger):
    admin, ana = two_people()
    me = admin.get("/api/auth/me").json()
    bread, avocado = foods(admin)
    noon = local_now().replace(hour=13, minute=0, second=0, microsecond=0)
    for back in (1, 3, 5):  # same lunch three times
        store.add_local_entry(me["id"], bread["id"], 100, noon - timedelta(days=back))
        store.add_local_entry(me["id"], avocado["id"], 50, noon - timedelta(days=back))
    store.add_local_entry(me["id"], bread["id"], 100, noon - timedelta(days=2))  # a different one, once
    favs = admin.get("/api/favorites").json()
    assert [f["times"] for f in favs] == [3, 1]
    assert favs[0]["meal"] == "almuerzo" and favs[0]["kcal"] == 360 and favs[0]["protein_g"] == 9.0
    assert sorted(i["name"] for i in favs[0]["items"]) == ["Aguacate casero", "Pan de la abuela"]
    assert ana.get("/api/favorites").json() == []


def test_ideas_use_catalog_calories_and_drop_what_cannot_be_found(wger, monkeypatch):
    admin, ana = two_people()
    foods(admin)
    thinker = Thinker()
    monkeypatch.setattr(main, "get_vision_client", lambda: thinker)
    out = admin.get("/api/ideas?meal=cena").json()
    assert out["done"] is False and out["kcal_left"] > 1000
    assert [i["name"] for i in out["ideas"]] == ["Pan con aguacate"]  # the invented one lost an ingredient and was dropped
    idea = out["ideas"][0]
    assert idea["kcal"] == 376 and idea["protein_g"] == 9.2  # 100 g * 2.8 + 60 g * 1.6, from the catalog
    assert [i["grams"] for i in idea["items"]] == [100, 60] and idea["tag"] == "Rápida"
    assert thinker.calls[0]["meal"] == "cena"
    admin.get("/api/ideas?meal=cena")  # cached: the model is not asked again
    assert len(thinker.calls) == 1
    admin.get("/api/ideas?meal=cena&refresh=true")
    assert len(thinker.calls) == 2


def test_ideas_say_done_when_nothing_is_left_and_ana_cannot_use_admins_foods(wger, monkeypatch):
    admin, ana = two_people()
    me = admin.get("/api/auth/me").json()
    bread, _ = foods(admin)
    thinker = Thinker()
    monkeypatch.setattr(main, "get_vision_client", lambda: thinker)
    assert ana.get("/api/ideas").json()["ideas"] == []  # she has no such foods: nothing resolves
    goal = admin.get("/api/auth/me").json().get("goal_kcal") or main.settings.fallback_goal_kcal
    store.add_local_entry(me["id"], bread["id"], goal / 2.8 + 50, local_now())
    out = admin.get("/api/ideas").json()
    assert out["done"] is True and out["ideas"] == [] and len(thinker.calls) == 1  # only Ana's call reached the model


def test_ideas_count_toward_the_daily_limit(wger, monkeypatch):
    admin, ana = two_people()
    foods(admin)
    thinker = Thinker()
    monkeypatch.setattr(main, "get_vision_client", lambda: thinker)
    monkeypatch.setattr(main.settings, "analyze_daily_limit", 1)
    assert ana.get("/api/ideas").status_code == 200
    assert ana.get("/api/ideas?refresh=true").status_code == 429
    assert admin.get("/api/ideas?refresh=true").status_code == 200  # the administrator has no limit
