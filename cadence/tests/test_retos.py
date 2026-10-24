"""Awards, daily and weekly challenges, coins and the shop: per person, computed on the server."""

import pytest

from app import store
from tests.test_foods import FOOD, two_people, wger  # noqa: F401  (wger is a fixture)

pytestmark = pytest.mark.anonymous


def log_meal(client, meal="almuerzo"):
    foods = [client.post("/api/foods", json={**FOOD, **f}).json() for f in (
        {"name": "Lentejas de la casa", "kcal": 116, "protein": 9, "carbs": 20, "fat": 0.4, "fibre": 7.9},
        {"name": "Pollo de la casa", "kcal": 165, "protein": 31, "carbs": 0, "fat": 3.6, "fibre": 0},
        {"name": "Arroz de la casa", "kcal": 130, "protein": 2.7, "carbs": 28, "fat": 0.3, "fibre": 0.4},
        {"name": "Ensalada de la casa", "kcal": 20, "protein": 1.2, "carbs": 3, "fat": 0.2, "fibre": 1.5})]
    grams = [200, 150, 150, 120]
    client.post("/api/confirm", json={"items": [{"ingredient_id": f["id"], "amount_grams": g} for f, g in zip(foods, grams)], "meal": meal})


def test_meal_awards_are_earned_once_shown_and_kept(wger):
    admin, ana = two_people()
    assert admin.get("/api/today").json()["awards_new"] == []
    log_meal(admin)
    first = admin.get("/api/today").json()
    keys = {a["key"] for a in first["meals"][0]["awards"]}
    assert {"protein_high", "varied_plate"} <= keys
    assert {a["key"] for a in first["awards_new"]} == keys  # celebrated the first time...
    assert admin.get("/api/today").json()["awards_new"] == []  # ...and only then
    assert {a["key"] for a in admin.get("/api/today").json()["meals"][0]["awards"]} == keys  # but still listed on the meal
    assert ana.get("/api/today").json()["awards_new"] == []


def test_awards_page_lists_everything_with_progress_and_celebrates_new_ones(wger):
    admin, ana = two_people()
    empty = admin.get("/api/awards").json()
    assert empty["total"] == 22 and empty["unlocked"] == 0 and empty["new"] == []
    log_meal(admin)
    admin.post("/api/weight", json={"kg": 70})
    page = admin.get("/api/awards").json()
    by = {a["key"]: a for a in page["awards"]}
    assert by["first_log"]["unlocked"] and by["first_weight"]["unlocked"] and not by["streak_7"]["unlocked"]
    assert (by["streak_7"]["value"], by["streak_7"]["target"]) == (1, 7)
    assert by["protein_high"]["unlocked"] and by["protein_high"]["count"] == 1 and by["protein_high"]["kind"] == "meal"
    assert {n["key"] for n in page["new"]} >= {"first_log", "first_weight", "protein_high"}
    assert admin.get("/api/awards").json()["new"] == []  # not celebrated twice
    assert page["unlocked"] == sum(a["unlocked"] for a in page["awards"])
    assert ana.get("/api/awards").json()["unlocked"] == 0  # hers are her own
    assert admin.get("/api/awards").json()["unlocked"] == page["unlocked"]


def test_challenges_are_claimed_once_and_only_when_finished(wger):
    admin, ana = two_people()
    start = admin.get("/api/challenges").json()
    assert start["coins"] == 0 and len(start["daily"]) == 4 and len(start["weekly"]) == 6 and start["claimable"] == 0
    assert {c["state"] for c in start["daily"] + start["weekly"]} == {"todo"}
    assert admin.post("/api/challenges/claim", json={"key": "d_first"}).status_code == 409  # nothing logged yet
    assert admin.post("/api/challenges/claim", json={"key": "nope"}).status_code == 404
    log_meal(admin)
    ready = admin.get("/api/challenges").json()
    by = {c["key"]: c for c in ready["daily"]}
    assert by["d_first"]["state"] == "ready" and by["d_constant"]["state"] == "todo" and ready["claimable"] >= 1
    paid = admin.post("/api/challenges/claim", json={"key": "d_first"}).json()
    assert paid == {"coins": 25, "amount": 25}
    assert admin.post("/api/challenges/claim", json={"key": "d_first"}).status_code == 409  # not twice
    after = admin.get("/api/challenges").json()
    assert {c["key"]: c["state"] for c in after["daily"]}["d_first"] == "claimed" and after["coins"] == 25
    assert ana.get("/api/challenges").json()["coins"] == 0
    assert ana.post("/api/challenges/claim", json={"key": "d_first"}).status_code == 409
    assert 1 <= after["hours_left"] <= 24 and 1 <= after["days_left"] <= 7


def test_shop_spends_coins_once_and_equips_per_person(wger):
    admin, ana = two_people()
    assert admin.post("/api/shop/buy", json={"item": "tema_aurora"}).status_code == 402  # no coins
    assert admin.post("/api/shop/buy", json={"item": "reloj"}).status_code == 404
    me = admin.get("/api/auth/me").json()
    admin_id = me["id"]
    store.add_coins(admin_id, "d_first", "2026-01-01", 500)  # coins from earlier challenges
    items = admin.post("/api/shop/buy", json={"item": "tema_aurora"}).json()
    aurora = next(i for i in items if i["key"] == "tema_aurora")
    assert aurora["owned"] and aurora["equipped"]
    assert admin.get("/api/challenges").json()["coins"] == 380
    assert admin.post("/api/shop/buy", json={"item": "tema_aurora"}).status_code == 409
    assert admin.post("/api/shop/buy", json={"item": "marco_dorado"}).status_code == 200
    me = admin.get("/api/auth/me").json()
    assert me["frame"] == "marco_dorado" and me["themes"] == ["tema_aurora"]
    assert admin.post("/api/shop/equip", json={"slot": "frame", "item": None}).status_code == 200
    assert admin.get("/api/auth/me").json()["frame"] is None
    assert admin.post("/api/shop/equip", json={"slot": "frame", "item": "tema_aurora"}).status_code == 403  # wrong slot
    assert admin.post("/api/shop/equip", json={"slot": "robot", "item": None}).status_code == 422
    assert ana.post("/api/shop/equip", json={"slot": "frame", "item": "marco_dorado"}).status_code == 403  # not hers
    assert ana.get("/api/auth/me").json()["frame"] is None and admin.get("/api/challenges").json()["coins"] == 80
    assert admin.post("/api/shop/buy", json={"item": "tema_atardecer"}).status_code == 402  # 80 left, costs 120
