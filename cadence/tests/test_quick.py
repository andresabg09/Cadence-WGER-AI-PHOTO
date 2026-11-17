"""'Rápido' (calories the person types, basics with home measures) and reading a product's nutrition label."""

import pytest

from app import main
from tests.test_foods import two_people, wger  # noqa: F401 - fixture

pytestmark = pytest.mark.anonymous


def test_quick_calories_are_logged_like_any_entry_and_stay_private(wger):
    admin, ana = two_people()
    saved = admin.post("/api/quick", json={"kcal": 700, "protein": 28, "meal": "almuerzo"})
    assert saved.status_code == 200, saved.text
    day = admin.get("/api/today").json()
    item = day["meals"][0]["items"][0]
    assert (item["name"], round(item["kcal"]), round(item["protein_g"]), item["quick"]) == ("Registro rápido", 700, 28, True)
    assert day["meals"][0]["key"] == "almuerzo"
    assert admin.get("/api/streaks").json()["current"]["length"] == 1  # counts for the streak like any entry
    assert admin.get("/api/foods").json() == []  # never offered back as a food in the list or the search
    assert admin.get("/api/search?term=registro").json() == []
    assert ana.get("/api/today").json()["totals"]["kcal"] == 0
    entry = item["diary_entry_id"]
    assert ana.delete(f"/api/diary/{entry}").status_code == 404
    assert admin.delete(f"/api/diary/{entry}").status_code == 200


def test_big_meals_and_bad_numbers(wger):
    admin, _ = two_people()
    assert admin.post("/api/quick", json={"kcal": 1500, "name": "Cumpleaños", "meal": "cena"}).status_code == 200
    item = admin.get("/api/today").json()["meals"][0]["items"][0]
    assert (item["name"], round(item["kcal"])) == ("Cumpleaños", 1500)
    assert admin.post("/api/quick", json={"kcal": 0}).status_code == 422
    assert admin.post("/api/quick", json={"kcal": 6000}).status_code == 422
    assert admin.post("/api/quick", json={"kcal": 100, "protein": 80}).status_code == 422  # 80 g of protein alone are 320 kcal


def test_basics_come_from_the_staples(wger, monkeypatch):
    admin, _ = two_people()
    monkeypatch.setattr(main, "_staples_cache", {"at": float("inf"), "items": [
        {"id": 5, "name": "Arroz blanco cocido", "energy": 130, "source": "cadence"},
        {"id": 6, "name": "Jugo de naranja", "energy": 45, "source": "cadence"},
        {"id": 7, "name": "Algo raro", "energy": 300, "source": "cadence"}]})
    basics = admin.get("/api/quick/basics").json()
    assert [(b["name"], b["liquid"]) for b in basics] == [("Arroz blanco cocido", False), ("Jugo de naranja", True)]


def test_label_values_are_converted_by_code_not_by_the_model():
    per100 = main.label_per_100g({"found": True, "basis": "serving", "serving_size": 15, "serving_unit": "ml", "energy_kcal": 120,
                                  "fat": 14, "carbohydrates": 0, "protein": 0, "name": "Aceite vegetal"})
    assert (per100["kcal"], per100["fat"], per100["liquid"]) == (800.0, 93.3, True)
    kj = main.label_per_100g({"found": True, "basis": "100g", "energy_kj": 1674, "protein": 10})
    assert round(kj["kcal"]) == 400 and kj["protein"] == 10
    for bad in ({"found": False}, {"found": True, "basis": "serving", "energy_kcal": 100},
                {"found": True, "basis": "100g", "energy_kcal": 300, "protein": 140}):
        with pytest.raises(main.HTTPException):
            main.label_per_100g(bad)


def test_label_endpoint_saves_nothing_and_counts_for_the_daily_limit(wger, monkeypatch):
    admin, _ = two_people()

    class Vision:
        def read_label(self, data, mime):
            return {"found": True, "basis": "100g", "energy_kcal": 52, "carbohydrates": 14, "sugars": 10, "protein": 0.3, "name": "Jugo de manzana"}

    monkeypatch.setattr(main, "get_vision_client", lambda: Vision())
    read = admin.post("/api/label", files={"image": ("e.jpg", b"\xff\xd8fake", "image/jpeg")}).json()
    assert (read["name"], read["kcal"], read["carbs"]) == ("Jugo de manzana", 52.0, 14.0)
    assert admin.get("/api/foods").json() == []  # only the food sheet saves, after the person checks it
