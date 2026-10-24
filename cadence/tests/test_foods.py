"""Own foods and scanned products live in cadence (wger's catalog is read-only): per person, in the diary, in search."""

import pytest

from app import main
from tests.test_accounts import SharedWger, new_client, register

pytestmark = pytest.mark.anonymous


class CatalogWger(SharedWger):
    codes = {"7501055300004": {"id": 77, "name": "Leche entera", "energy": 61, "protein": 3.2, "carbohydrates": 4.8, "fat": 3.3}}

    def search_ingredients(self, term, limit=15): return []
    def list_staples(self): return []
    def get_ingredient_by_code(self, code): return self.codes.get(code)


@pytest.fixture
def wger(monkeypatch):
    fake = CatalogWger()
    monkeypatch.setattr(main, "get_wger_client", lambda: fake)
    return fake


FOOD = {"name": "Pan de la abuela", "kcal": 280, "protein": 8, "carbs": 50, "fat": 4}


def two_people():
    admin, ana = new_client(), new_client()
    register(admin, "admin@example.com")
    register(ana, "ana@example.com", admin.post("/api/admin/invites", json={}).json()["code"])
    return admin, ana


def test_own_food_is_searchable_loggable_editable_and_private(wger):
    admin, ana = two_people()
    made = admin.post("/api/foods", json=FOOD).json()
    assert made["id"] < 0 and made["energy_kcal_100g"] == 280
    assert [f["name"] for f in admin.get("/api/search?term=pan abuela").json()] == ["Pan de la abuela"]
    assert ana.get("/api/search?term=pan abuela").json() == []  # not shared

    saved = admin.post("/api/confirm", json={"items": [{"ingredient_id": made["id"], "amount_grams": 100}], "meal": "desayuno"}).json()
    entry_id = saved["created"][0]["diary_entry_id"]
    assert entry_id.startswith("c") and saved["counts_for_streak"] is True
    day = admin.get("/api/today").json()
    item = day["meals"][0]["items"][0]
    assert (item["name"], item["kcal"], day["totals"]["kcal"]) == ("Pan de la abuela", 280, 280)
    assert admin.get("/api/recent").json()[0]["id"] == made["id"]
    assert admin.get("/api/streaks").json()["current"]["length"] == 1

    assert admin.patch(f"/api/diary/{entry_id}", json={"amount_grams": 50}).status_code == 200
    assert admin.get("/api/today").json()["totals"]["kcal"] == 140
    assert ana.get("/api/today").json()["totals"]["kcal"] == 0
    assert ana.delete(f"/api/diary/{entry_id}").status_code == 404
    assert ana.patch(f"/api/diary/{entry_id}", json={"amount_grams": 1}).status_code == 404
    assert ana.post("/api/confirm", json={"items": [{"ingredient_id": made["id"], "amount_grams": 10}]}).status_code == 404
    assert ana.get(f"/api/ingredient/{made['id']}").status_code == 502  # not hers
    assert admin.delete(f"/api/diary/{entry_id}").status_code == 200
    assert admin.get("/api/today").json()["meals"] == []


def test_food_values_are_sanity_checked(wger):
    admin, _ = two_people()
    assert admin.post("/api/foods", json={**FOOD, "kcal": 5000}).status_code == 422
    assert admin.post("/api/foods", json={**FOOD, "protein": 60, "carbs": 60}).status_code == 422
    assert admin.post("/api/foods", json={**FOOD, "name": "  "}).status_code == 422


def test_barcode_prefers_own_then_wger_then_nothing(wger, monkeypatch):
    admin, _ = two_people()
    monkeypatch.setattr(main, "_off_product", lambda code: {"name": "Galletas", "kcal": 450, "protein": 6, "carbs": 70, "fat": 16} if code == "8000000000019" else None)
    assert admin.get("/api/barcode/abc").status_code == 422
    hit = admin.get("/api/barcode/7501055300004").json()
    assert (hit["found"], hit["source"], hit["id"], hit["kcal"]) == (True, "wger", 77, 61)
    off = admin.get("/api/barcode/8000000000019").json()
    assert (off["found"], off["source"], off["id"], off["name"]) == (True, "off", None, "Galletas")
    assert admin.get("/api/barcode/1234567890123").json()["found"] is False
    made = admin.post("/api/foods", json={**off, "barcode": "8000000000019"}).json()
    again = admin.get("/api/barcode/8000000000019").json()
    assert (again["source"], again["id"]) == ("own", made["id"])
    assert admin.post("/api/foods", json={**off, "barcode": "8000000000019"}).json()["id"] == made["id"]  # no duplicates


def test_workouts_are_estimated_private_and_shown_in_the_day(wger):
    admin, ana = two_people()
    admin.post("/api/weight", json={"kg": 80})
    done = admin.post("/api/workouts", json={"kind": "pesas", "minutes": 45, "note": "pecho y tríceps"}).json()
    assert done["kcal"] == 300  # 5 MET x 80 kg x 0.75 h
    assert admin.post("/api/workouts", json={"kind": "volar", "minutes": 30}).status_code == 422
    assert admin.post("/api/workouts", json={"kind": "yoga", "minutes": 1}).status_code == 422
    assert admin.post("/api/workouts", json={"kind": "yoga", "minutes": 30, "day": "2999-01-01"}).status_code == 422
    assert [w["note"] for w in admin.get("/api/today").json()["workouts"]] == ["pecho y tríceps"]
    assert ana.get("/api/today").json()["workouts"] == []
    assert ana.delete(f"/api/workouts/{done['id']}").status_code == 404
    assert admin.delete(f"/api/workouts/{done['id']}").status_code == 200
    assert admin.get("/api/today").json()["workouts"] == []


def test_progress_and_history_read_the_persons_own_days(wger):
    from datetime import timedelta
    from app import store
    from app.meals import local_now

    admin, ana = two_people()
    me = admin.get("/api/auth/me").json()
    made = admin.post("/api/foods", json=FOOD).json()
    noon = local_now().replace(hour=12, minute=0, second=0, microsecond=0)
    for back in (0, 1, 2, 3, 4, 9):  # 5 days in a row, then a gap
        store.add_local_entry(me["id"], made["id"], 100, noon - timedelta(days=back))
    admin.post("/api/weight", json={"kg": 82, "day": (noon - timedelta(days=20)).date().isoformat()})
    admin.post("/api/weight", json={"kg": 80.6})

    p = admin.get("/api/progress").json()
    assert (p["streak_current"], p["streak_best"], p["logged_today"]) == (5, 5, True)
    assert len(p["days"]) == 28 and p["days"][-1]["logged"] and p["days"][-1]["kcal"] == 280
    assert p["weight_change_30d"] == -1.4 and len(p["weights"]) == 2
    medals = {a["key"]: a["unlocked"] for a in p["achievements"]}
    assert medals["first_log"] and medals["streak_3"] and not medals["streak_7"] and medals["first_weight"] and not medals["weights_5"]
    assert p["unlocked"] == sum(medals.values())

    h = admin.get("/api/history?days=14").json()
    assert [d["count"] for d in h["days"]] == [1, 1, 1, 1, 1, 1] and h["days"][0]["kcal"] == 280
    older = admin.get(f"/api/history?before={h['days'][-1]['date']}&days=14").json()
    assert older["days"] == []
    assert ana.get("/api/history").json()["days"] == [] and ana.get("/api/progress").json()["streak_best"] == 0
    assert admin.delete(f"/api/weight/{noon.date().isoformat()}").status_code == 200
    assert [w["kg"] for w in admin.get("/api/weights").json()] == [82]
