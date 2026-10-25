"""Block 13: units to see things, goals by pace (pounds per month), liquids in millilitres and the one-time welcome."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import foodunits, main, nutrition, store
from tests.test_accounts import PROFILE, SharedWger, new_client, register

pytestmark = pytest.mark.anonymous  # real cookie login, like the account tests


@pytest.fixture
def wger(monkeypatch):
    fake = SharedWger()
    monkeypatch.setattr(main, "get_wger_client", lambda: fake)
    return fake


def test_liquids_are_guessed_from_the_name_and_solids_stay_in_grams():
    for name in ["Sopa de pollo", "Chicken noodle soup", "Leche entera", "Jugo de naranja", "Café con leche", "Sancocho", "Coca-Cola", "Agua"]:
        assert foodunits.is_liquid(name), name
    for name in ["Arroz blanco cocido", "Pollo a la plancha", "Leche condensada", "Aguacate", "Yogur natural", "Cola de res", "Queso"]:
        assert not foodunits.is_liquid(name), name
    assert foodunits.is_liquid("Pan", True) and not foodunits.is_liquid("Sopa", False)  # what was said wins


def test_pace_sets_the_calories_and_never_goes_past_what_is_safe():
    born, today = date(1991, 3, 14), date(2026, 10, 25)
    base = nutrition.compute_targets("male", born, 175, 75, "moderate", "lose", today, 4)
    assert base.pace_lb_month == 4.0 and base.kcal == pytest.approx(base.maintenance_kcal - 4 * 3500 / 30, abs=20)
    assert base.projection_kg[0] == pytest.approx(75 - 4 / nutrition.LB_PER_KG, abs=0.1) and base.projection_kg[2] < base.projection_kg[0]
    fast = nutrition.compute_targets("male", born, 175, 75, "moderate", "lose", today, 25)
    assert fast.pace_lb_month == fast.max_pace_lb_month <= 7.2 and fast.kcal >= 1500 and "más seguro" in fast.note
    low = nutrition.compute_targets("female", born, 160, 52, "low", "lose", today, 6)  # little room above the minimum
    assert low.kcal >= 1200
    minor = nutrition.compute_targets("female", date(2012, 1, 1), 150, 45, "low", "lose", today, 4)
    assert minor.kcal == minor.maintenance_kcal and minor.pace_lb_month == 0
    muscle = nutrition.compute_targets("male", born, 175, 75, "moderate", "muscle", today, 2)
    assert muscle.kcal > muscle.maintenance_kcal and muscle.pace_lb_month == 2.0 and muscle.projection_kg[0] > 75
    assert nutrition.weight_change_lb_month(2500, 2000) == pytest.approx(-4.29, abs=0.01)


def test_goal_by_pace_through_the_api_and_what_it_means_for_the_scale(wger):
    http = new_client()
    register(http, "a@example.com")
    preview = http.post("/api/plan/preview", json={**PROFILE, "pace_lb_month": 4}).json()
    assert preview["pace_lb_month"] == 4.0 and preview["max_pace_lb_month"] > 4 and len(preview["projection_kg"]) == 3
    assert preview["change_lb_month"] == pytest.approx(-4.0, abs=0.3)
    me = http.put("/api/profile", json={**PROFILE, "pace_lb_month": 4}).json()
    assert me["pace_lb_month"] == 4.0 and me["targets"]["kcal"] == preview["kcal"]
    assert me["targets"]["maintenance_kcal"] and me["targets"]["change_lb_month"] == pytest.approx(-4.0, abs=0.3)
    slower = http.put("/api/goals", json={"pace_lb_month": 2}).json()
    assert slower["pace_lb_month"] == 2.0 and slower["targets"]["kcal"] > me["targets"]["kcal"]
    by_hand = http.put("/api/goals", json={"kcal": slower["targets"]["kcal"] + 100}).json()
    assert by_hand["pace_lb_month"] is None  # calories typed by hand: no pace to speak of
    today = http.get("/api/today").json()
    assert today["maintenance_kcal"] and today["goal_change_lb_month"] < 0


def test_units_are_a_display_choice_saved_per_person(wger):
    admin, ana = new_client(), new_client()
    register(admin, "admin@example.com")
    code = admin.post("/api/admin/invites", json={}).json()["code"]
    register(ana, "ana@example.com", code)
    assert admin.get("/api/auth/me").json()["units"] == {"weight": "kg", "height": "cm", "liquid": "ml", "chosen": False}
    out = admin.put("/api/units", json={"weight": "lb", "height": "ft", "liquid": "oz"}).json()
    assert out["units"] == {"weight": "lb", "height": "ft", "liquid": "oz", "chosen": True}
    assert ana.get("/api/auth/me").json()["units"]["chosen"] is False  # nobody else's choice changes
    assert admin.put("/api/units", json={"weight": "stone", "height": "cm", "liquid": "ml"}).status_code == 422
    assert new_client().put("/api/units", json={"weight": "lb"}).status_code == 401
    assert new_client().post("/api/welcome/done").status_code == 401


def test_the_one_time_welcome_is_only_for_people_who_were_already_in(wger):
    http = new_client()
    register(http, "old@example.com")
    http.put("/api/profile", json=PROFILE)
    assert http.get("/api/auth/me").json()["needs_welcome"] is False  # signed up after the change: full flow, nothing "new"
    me = http.get("/api/auth/me").json()
    store.update_user(me["id"], welcome_v2=False)  # what the database migration does to everyone who existed before
    assert http.get("/api/auth/me").json()["needs_welcome"] is True
    assert http.get("/api/auth/me").json()["needs_welcome"] is True  # it stays until it is finished
    assert http.post("/api/welcome/done").json()["needs_welcome"] is False
    assert http.get("/api/auth/me").json()["needs_welcome"] is False  # and never comes back
    # someone who never finished the first-use questionnaire gets the full flow, not the "what changed" one
    other = new_client()
    register(other, "pending@example.com", http.post("/api/admin/invites", json={}).json()["code"])
    pending = other.get("/api/auth/me").json()
    store.update_user(pending["id"], welcome_v2=False)
    assert other.get("/api/auth/me").json()["needs_welcome"] is False and other.get("/api/auth/me").json()["onboarded"] is False


def test_liquids_keep_their_unit_from_the_confirm_screen_to_the_diary(wger):
    http = new_client()
    register(http, "a@example.com")
    http.put("/api/profile", json=PROFILE)
    own = http.post("/api/foods", json={"name": "Mi malta", "kcal": 40, "protein": 1, "carbs": 9, "fat": 0, "liquid": True}).json()
    assert own["liquid"] is True
    assert http.post("/api/foods", json={"name": "Mi pan", "kcal": 250, "protein": 8, "carbs": 50, "fat": 2}).json()["liquid"] is False
    body = {"items": [{"ingredient_id": 5, "amount_grams": 100},                     # "Arroz": a solid by name
                      {"ingredient_id": 6, "amount_grams": 250, "liquid": True},      # the model said it is a liquid
                      {"ingredient_id": own["id"], "amount_grams": 330}], "meal": "almuerzo"}
    assert http.post("/api/confirm", json=body).status_code == 200
    items = {i["ingredient_id"]: i for m in http.get("/api/today").json()["meals"] for i in m["items"]}
    assert items[5]["liquid"] is False and items[6]["liquid"] is True and items[own["id"]]["liquid"] is True
    assert [f for f in http.get("/api/foods").json() if f["name"] == "Mi malta"][0]["liquid"] is True


def test_the_water_goal_is_whole_glasses_of_the_persons_size(wger):
    http = new_client()
    register(http, "a@example.com")
    assert http.put("/api/water/goal", json={"ml": 2000, "step_ml": 237}).json()["goal_ml"] == 8 * 237
    assert http.put("/api/water/goal", json={"ml": 2000}).json()["goal_ml"] == 2000


def test_the_model_can_say_a_component_is_a_liquid():
    from app import vision
    parsed = vision._parse_components('[{"name": "sopa de pollo", "liquid": true, "estimated_grams": 300}, {"name": "arroz", "liquid": false}, {"name": "pan"}]')
    assert [c.liquid for c in parsed] == [True, False, None]  # None: decided later from the name of the food it matches
