"""Real recipes (TheMealDB) prepared for cadence: the model only translates and converts measures to grams; every calorie
comes from the food catalog, looked up as the ingredient goes into the pot. Each person sees them fitted to their own day."""

import pytest

from app import main, recipes, store, vision
from tests.test_foods import CatalogWger, two_people

pytestmark = pytest.mark.anonymous

FOODS = [
    {"id": 1, "name": "Dry penne pasta", "energy": 350, "protein": 12, "carbohydrates": 72, "fat": 1.5, "source": "off"},
    {"id": 2, "name": "Olive oil", "energy": 884, "protein": 0, "carbohydrates": 0, "fat": 100, "source": "off"},
    {"id": 3, "name": "Chopped tomatoes", "energy": 24, "protein": 1.2, "carbohydrates": 4, "fat": 0.2, "source": "off"},
    {"id": 4, "name": "White rice", "energy": 340, "protein": 7, "carbohydrates": 77, "fat": 0.6, "source": "off"},
    {"id": 5, "name": "Cooked white rice", "energy": 130, "protein": 2.7, "carbohydrates": 28, "fat": 0.3, "source": "cadence"},
    {"id": 6, "name": "Raw chicken breast", "energy": 120, "protein": 22.5, "carbohydrates": 0, "fat": 2.6, "source": "off"},
    {"id": 7, "name": "Garlic", "energy": 149, "protein": 6.4, "carbohydrates": 33, "fat": 0.5, "source": "off"},
]


class Pantry(CatalogWger):
    def search_ingredients(self, term, limit=15):
        words = term.lower().split()
        return [dict(food) for food in FOODS if any(word in food["name"].lower() for word in words)]

    def get_ingredient(self, ingredient_id):
        return next(dict(food) for food in FOODS if food["id"] == ingredient_id)


def meal(recipe_id="52771", name="Spicy Arrabiata Penne", category="Vegetarian", area="Italian", ingredients=None):
    ingredients = ingredients or [("penne rigate", "1 pound"), ("olive oil", "1/4 cup"), ("chopped tomatoes", "1 tin"),
                                  ("garlic", "3 cloves"), ("salt", "to taste")]
    raw = {"idMeal": recipe_id, "strMeal": name, "strCategory": category, "strArea": area,
           "strInstructions": "Bring a large pot of water to a boil. Cook the pasta. Make the sauce and toss everything together.",
           "strMealThumb": f"https://www.themealdb.com/images/media/meals/{recipe_id}.jpg", "strSource": "https://example.com/recipe",
           "strYoutube": ""}
    for i, (ingredient, measure) in enumerate(ingredients, start=1):
        raw[f"strIngredient{i}"], raw[f"strMeasure{i}"] = ingredient, measure
    return raw


ARRABIATA = {"name": "Penne arrabiata picante", "servings": 4, "minutes": 30, "meals": ["almuerzo", "cena"],
             "steps": ["Hierve agua y cocina la pasta.", "Haz la salsa y mezcla todo."],
             "items": {1: {"name": "pasta penne", "measure": "1 libra", "grams": 400, "search_name": "dry penne pasta",
                           "search_alternatives": ["dry pasta"], "liquid": False, "skip": False},
                       2: {"name": "aceite de oliva", "measure": "1/4 de taza", "grams": 54, "search_name": "olive oil",
                           "search_alternatives": [], "liquid": True, "skip": False},
                       3: {"name": "tomates picados", "measure": "1 lata", "grams": 400, "search_name": "chopped tomatoes",
                           "search_alternatives": [], "liquid": False, "skip": False},
                       4: {"name": "ajo", "measure": "3 dientes", "grams": 12, "search_name": "garlic",
                           "search_alternatives": [], "liquid": False, "skip": False},
                       5: {"name": "sal", "measure": "al gusto", "grams": None, "search_name": None,
                           "search_alternatives": [], "liquid": False, "skip": True}}}


class Editor:
    """Stands in for Gemini: answers each recipe with a prepared text, or fails like a model that did not answer."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def prepare_recipe(self, **recipe):
        self.calls.append(recipe["name"])
        answer = self.answers.get(recipe["name"])
        if answer is None:
            raise RuntimeError("el modelo no respondio")
        return answer


@pytest.fixture
def wger(monkeypatch):
    fake = Pantry()
    monkeypatch.setattr(main, "get_wger_client", lambda: fake)
    recipes._ready.update(at=0.0, items=[])
    recipes._foods.clear()
    return fake


def file_and_prepare(wger, raws, answers):
    store.recipes_upsert([recipes.normalize(raw) for raw in raws])
    editor = Editor(answers)
    while (waiting := store.recipe_next_raw()) is not None:
        recipes.prepare_one(waiting, editor, wger)
        if store.recipes_counts()["waiting"] and len(editor.calls) > 20:
            break
    return editor


def test_only_weights_written_in_the_recipe_are_read_without_the_model():
    grams = recipes.explicit_grams
    assert (grams("200g"), grams("1 lb"), grams("1 1/2 lb"), grams("175g/6oz"), grams("500ml"), grams("1.5 litres")) == (200, 453.6, 680.4, 175, 500, 1500)
    assert (grams("½ lb"), grams("8 oz"), grams("1/2 kg"), grams("400g tin")) == (226.8, 226.8, 500, 400)
    for measure in ("1 large", "2 tbs", "3 cloves", "1 garlic", "to taste", "", "1 cup"):
        assert grams(measure) is None  # cups, spoons and pieces are the model's to estimate


def test_what_the_source_sends_is_checked_before_it_is_filed():
    row = recipes.normalize(meal())
    assert (row["id"], row["area"], len(row["raw"]["ingredients"]), row["raw"]["source"]) == ("52771", "Italian", 5, "https://example.com/recipe")
    assert "youtube" not in row["raw"]
    assert recipes.normalize({**meal(), "strMealThumb": "https://evil.example/x.jpg"}) is None  # photos only from their own site
    assert recipes.normalize({**meal(), "idMeal": "../1"}) is None
    assert recipes.normalize(meal(ingredients=[("salt", "pinch")])) is None  # not a recipe
    # the newest entries name the country instead of the "area"
    assert recipes.normalize({**meal(), "strArea": None, "strCountry": "Colombia"})["area"] == "Colombia"
    assert recipes.priority("Chicken", "Colombia") < recipes.priority("Chicken", "British") < recipes.priority("Dessert", "Colombia")


def test_calories_come_from_the_catalog_per_serving_and_what_is_shown_is_what_is_logged(wger):
    file_and_prepare(wger, [meal()], {"Spicy Arrabiata Penne": ARRABIATA})
    admin, _ = two_people()
    out = admin.get("/api/recipes?meal=almuerzo").json()
    assert out["catalog"] == {"total": 1, "ready": 1, "waiting": 0, "skipped": 0}
    card = out["recipes"][0]
    assert (card["name"], card["category"], card["area"], card["servings"], card["minutes"]) == ("Penne arrabiata picante", "Vegetariano", "Italia", 4, 30)
    detail = admin.get(f"/api/recipes/{card['id']}").json()
    # "1 pound" is written in the recipe: 453.6 g, not the model's 400. Per serving: 113 g pasta, 14 g oil (13.5 rounded), 100 g tomato.
    by_food = {item["name"]: item["grams"] for item in detail["items"]}
    assert by_food == {"Dry penne pasta": 113, "Olive oil": 14, "Chopped tomatoes": 100, "Garlic": 3}
    kcal = 350 * 1.13 + 884 * 0.14 + 24 * 1.0 + 149 * 0.03
    assert card["kcal"] == detail["kcal"] == round(kcal)
    assert detail["protein_g"] == round(12 * 1.13 + 1.2 + 6.4 * 0.03, 1)
    assert [i["name"] for i in detail["ingredients"]] == ["pasta penne", "aceite de oliva", "tomates picados", "ajo", "sal"]  # salt is listed, not logged
    assert detail["ingredients"][1] == {"name": "aceite de oliva", "measure": "1/4 de taza", "photo": "api/recipe-ingredient/olive_oil"}
    assert detail["items"][1]["label"] == "aceite de oliva" and detail["items"][1]["liquid"] is True
    assert detail["items"][1]["photo"] == "api/recipe-ingredient/olive_oil"
    assert detail["steps"] == ARRABIATA["steps"] and detail["source"] == "https://example.com/recipe" and "TheMealDB" in detail["credit"]

    # Logging one serving = the same foods and grams through the usual confirm: the day shows the same calories.
    saved = admin.post("/api/confirm", json={"meal": "almuerzo", "items": [
        {"ingredient_id": i["ingredient_id"], "amount_grams": i["grams"], "liquid": i["liquid"]} for i in detail["items"]]})
    assert saved.status_code == 200
    assert round(admin.get("/api/today").json()["totals"]["kcal"]) == detail["kcal"]


def test_raw_rice_is_not_counted_as_cooked_rice(wger):
    said = {"name": "Arroz con pollo", "servings": 2, "minutes": 40, "meals": ["almuerzo"], "steps": ["Cocina todo junto."],
            "items": {1: {"name": "arroz", "measure": "1 taza", "grams": 185, "search_name": "white rice", "search_alternatives": ["rice"],
                          "liquid": False, "skip": False},
                      2: {"name": "pechuga de pollo", "measure": "300 g", "grams": 250, "search_name": "raw chicken breast",
                          "search_alternatives": [], "liquid": False, "skip": False}}}
    raw = meal("53000", "Arroz con pollo", "Chicken", "Panamanian", [("rice", "1 cup"), ("chicken breast", "300g")])
    file_and_prepare(wger, [raw], {"Arroz con pollo": said})
    items = {i["name"]: i["grams"] for i in store.recipe_get("53000")["prepared"]["items"]}
    assert items == {"White rice": 92, "Raw chicken breast": 150}  # the staple "Cooked white rice" would have a third of the calories
    assert recipes.find_food(wger, "cooked white rice", [])["name"] == "Cooked white rice"  # unless the recipe adds it cooked


def test_a_recipe_the_catalog_cannot_cover_is_set_aside_and_a_silent_model_is_retried(wger):
    unknown = {**ARRABIATA, "name": "Guiso raro", "items": {
        1: {"name": "zzz", "measure": "1 taza", "grams": 300, "search_name": "zzzxxqq", "search_alternatives": [], "liquid": False, "skip": False},
        2: {"name": "aceite", "measure": "1 cda", "grams": 15, "search_name": "olive oil", "search_alternatives": [], "liquid": True, "skip": False},
        3: {"name": "ajo", "measure": "1 diente", "grams": 4, "search_name": "garlic", "search_alternatives": [], "liquid": False, "skip": False}}}
    huge = {**ARRABIATA, "name": "Para uno", "servings": 1, "items": {**ARRABIATA["items"], 2: {**ARRABIATA["items"][2], "grams": 500}}}
    raws = [meal("1", "Strange stew", ingredients=[("zzz", "1 cup"), ("oil", "1 tbs"), ("garlic", "1 clove")]),
            meal("2", "For one"), meal("3", "Silent")]
    editor = file_and_prepare(wger, raws, {"Strange stew": unknown, "For one": huge})
    counts = store.recipes_counts()
    assert (counts["ready"], counts["waiting"], counts["skipped"]) == (0, 0, 3)
    assert store.recipe_get("1")["status"] == "skipped"  # most of its weight is not in the catalog: no made-up numbers
    assert store.recipe_get("2")["status"] == "skipped"  # 6 000 kcal "per serving": the servings are wrong
    assert store.recipe_get("3")["status"] == "failed" and editor.calls.count("Silent") == 3  # three tries, then it waits
    store.recipes_requeue(recipes.PREP_VERSION)  # the next restart gives it another chance; the set-aside ones stay
    assert store.recipes_counts()["waiting"] == 1 and store.recipe_get("1")["status"] == "skipped"
    store.recipes_requeue(recipes.PREP_VERSION + 1)  # new preparation rules: everything is prepared again
    assert store.recipes_counts()["waiting"] == 3


def test_the_models_answer_is_checked(wger):
    good = ('```json\n{"name": " Arroz  con pollo ", "servings": 4, "minutes": 9999, "meals": ["cena", "brunch"], "steps": ["Uno", "", 3],'
            ' "items": [{"i": 1, "name": "arroz", "measure": "1 taza", "grams": 185, "search_name": "white rice",'
            ' "search_alternatives": ["rice", "x", "y"]}, {"i": 2, "name": "sal", "skip": true}, {"i": 9, "name": "de mas", "grams": 5},'
            ' {"i": 1, "name": "repetido", "grams": 1}, {"i": 2, "kcal": 500}]}\n```')
    parsed = vision._parse_recipe(good, 2)
    assert (parsed["name"], parsed["servings"], parsed["minutes"], parsed["meals"], parsed["steps"]) == ("Arroz con pollo", 4, None, ["cena"], ["Uno"])
    assert set(parsed["items"]) == {1, 2} and parsed["items"][1]["grams"] == 185 and parsed["items"][1]["search_alternatives"] == ["rice", "x"]
    assert parsed["items"][2]["skip"] is True and "kcal" not in parsed["items"][2]
    for bad in ('{"name": "x", "servings": 40, "steps": ["a"]}', '{"name": "", "servings": 2, "steps": ["a"]}',
                '{"name": "x", "servings": 2, "steps": []}', "no es json", "[1, 2]"):
        with pytest.raises(ValueError):
            vision._parse_recipe(bad, 2)


def test_each_person_gets_the_portion_for_their_own_day_and_their_own_saved_list(wger):
    light = {**ARRABIATA, "name": "Ensalada de tomate", "servings": 8}
    raws = [meal(), meal("52772", "Tomato salad", "Side", "Spanish"), meal("52773", "Sweet thing", "Dessert", "Spanish")]
    file_and_prepare(wger, raws, {"Spicy Arrabiata Penne": ARRABIATA, "Tomato salad": light, "Sweet thing": {**ARRABIATA, "name": "Dulce"}})
    admin, ana = two_people()
    store.update_user(admin.get("/api/auth/me").json()["id"], goal_kcal=3200, goal_protein=160, goal_carbs=400, goal_fat=90)
    store.update_user(ana.get("/api/auth/me").json()["id"], goal_kcal=1400, goal_protein=90, goal_carbs=150, goal_fat=45)

    big = {c["name"]: c for c in admin.get("/api/recipes?meal=almuerzo").json()["recipes"]}
    small = {c["name"]: c for c in ana.get("/api/recipes?meal=almuerzo").json()["recipes"]}
    assert set(big) == set(small) == {"Penne arrabiata picante", "Ensalada de tomate"}  # the dessert is a snack, not lunch
    assert big["Penne arrabiata picante"]["kcal"] == small["Penne arrabiata picante"]["kcal"]  # the recipe is the same...
    assert big["Penne arrabiata picante"]["portions"] > small["Penne arrabiata picante"]["portions"]  # ...the portion is personal
    assert small["Penne arrabiata picante"]["portions"] == recipes.portion_for(548, 1400 * 0.35)
    assert [c["name"] for c in ana.get("/api/recipes?meal=merienda").json()["recipes"]] == ["Dulce"]

    # What Ana already ate today changes what fits her; it changes nothing for the administrator.
    before = ana.get("/api/recipes?meal=almuerzo").json()
    ana.post("/api/confirm", json={"meal": "desayuno", "items": [{"ingredient_id": 2, "amount_grams": 140}]})  # ~1 240 kcal of oil
    after = ana.get("/api/recipes?meal=almuerzo").json()
    assert before["kcal_left"] == 1400 and after["kcal_left"] < 200 and after["done"] is False
    pasta = lambda out: next(c for c in out["recipes"] if c["name"] == "Penne arrabiata picante")  # noqa: E731
    assert pasta(before)["fits"] is True and pasta(after)["fits"] is False  # even half a serving is more than what she has left
    assert next(c for c in after["recipes"] if c["name"] == "Ensalada de tomate")["fits"] is True  # half a light one still fits
    assert after["recipes"][0]["name"] == "Ensalada de tomate"  # and it is the one offered first
    assert admin.get("/api/recipes?meal=cena").json()["kcal_left"] == 3200

    # Search looks in every meal, in Spanish or in the original name, and in the ingredients.
    assert [c["name"] for c in ana.get("/api/recipes?q=dulce").json()["recipes"]] == ["Dulce"]
    assert len(ana.get("/api/recipes?q=ARRABIATA").json()["recipes"]) == 1 and len(ana.get("/api/recipes?q=ajo").json()["recipes"]) == 3
    assert ana.get("/api/recipes?q=zzzz").json()["recipes"] == []
    cats = {c["key"]: c["count"] for c in ana.get("/api/recipes?q=ajo").json()["categories"]}
    assert cats == {"Vegetarian": 1, "Side": 1, "Dessert": 1}
    assert [c["name"] for c in ana.get("/api/recipes?q=ajo&category=Side").json()["recipes"]] == ["Ensalada de tomate"]

    # Saved recipes belong to whoever saved them.
    assert ana.put("/api/recipes/52771/save", json={"saved": True}).json() == {"saved": True}
    assert ana.put("/api/recipes/52773/save", json={"saved": True}).status_code == 200
    assert [c["id"] for c in ana.get("/api/recipes?saved=true").json()["recipes"]] == ["52773", "52771"]  # the latest first
    assert ana.get("/api/recipes/52771").json()["saved"] is True
    assert admin.get("/api/recipes?saved=true").json()["recipes"] == [] and admin.get("/api/recipes/52771").json()["saved"] is False
    assert ana.put("/api/recipes/52771/save", json={"saved": False}).status_code == 200
    assert [c["id"] for c in ana.get("/api/recipes?saved=true").json()["recipes"]] == ["52773"]
    assert ana.put("/api/recipes/999/save", json={"saved": True}).status_code == 404
    assert ana.get("/api/recipes/abc").status_code == 404


def test_recipes_and_their_photos_need_a_session_and_photos_only_come_from_the_source(wger, monkeypatch):
    from tests.test_accounts import new_client

    file_and_prepare(wger, [meal()], {"Spicy Arrabiata Penne": ARRABIATA})
    stranger = new_client()
    for path in ("/api/recipes", "/api/recipes/52771", "/api/recipes/52771/photo", "/api/recipe-ingredient/olive_oil"):
        assert stranger.get(path).status_code == 401
    assert stranger.put("/api/recipes/52771/save", json={"saved": True}).status_code == 401

    asked = []

    class Reply:
        def __init__(self, status, content):
            self.status_code, self.content = status, content

    def fake_get(url, **_):
        asked.append(url)
        if url.endswith("olive_oil-small.png"):
            return Reply(200, b"\x89PNG\r\n\x1a\n" + b"0" * 20)
        if "/images/media/meals/52771.jpg" in url:
            return Reply(200, b"\xff\xd8\xff" + b"0" * 20)
        return Reply(200, b"<html>not a picture</html>")

    monkeypatch.setattr(recipes.httpx, "get", fake_get)
    recipes._missing.clear()
    admin, _ = two_people()
    photo = admin.get("/api/recipes/52771/photo?size=l")
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg" and "max-age" in photo.headers["cache-control"]
    assert asked == ["https://www.themealdb.com/images/media/meals/52771.jpg/large"]
    admin.get("/api/recipes/52771/photo?size=l")
    assert len(asked) == 1  # kept on the data volume: their site is asked once
    oil = admin.get("/api/recipe-ingredient/olive_oil")
    assert oil.status_code == 200 and oil.headers["content-type"] == "image/png"
    assert admin.get("/api/recipe-ingredient/nothing").status_code == 404  # what comes back is not a picture
    before = len(asked)
    assert admin.get("/api/recipe-ingredient/nothing").status_code == 404 and len(asked) == before  # and it is not asked again right away
    for bad in ("..%2F..%2Fetc", "a%2Fb", "x" * 80):
        assert admin.get(f"/api/recipe-ingredient/{bad}").status_code == 404
    assert all(url.startswith("https://www.themealdb.com/images/") for url in asked)
    assert admin.get("/api/recipes/999/photo").status_code == 404


def test_the_catalog_is_read_through_the_official_api_and_a_broken_answer_is_not_taken_for_it(wger, monkeypatch):
    class Http:
        def __init__(self, meals): self.meals, self.urls = meals, []
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def get(self, url, params=None):
            self.urls.append((url, params["f"]))
            answer = {"meals": self.meals if params["f"] == "s" else None}
            return type("R", (), {"raise_for_status": lambda self: None, "json": lambda self: answer})()

    monkeypatch.setattr(recipes.clock, "sleep", lambda _: None)
    http = Http([meal(), {"idMeal": "x"}, "Invalid"])
    monkeypatch.setattr(recipes.httpx, "Client", lambda **_: http)
    with pytest.raises(RuntimeError):
        recipes.sync_catalog()  # one recipe is not a catalog: nothing is stamped as synced
    assert store.get_kv("recipes_synced_at") is None
    assert recipes.sync_catalog(minimum=1) == 1 and store.recipes_counts()["waiting"] == 1
    assert len(http.urls) == 72 and http.urls[0][0] == "https://www.themealdb.com/api/json/v1/1/search.php"
    file_and_prepare(wger, [], {"Spicy Arrabiata Penne": ARRABIATA})
    assert recipes.sync_catalog(minimum=1) == 0 and store.recipes_counts()["ready"] == 1  # reading it again keeps what was prepared
    changed = meal(ingredients=[("penne rigate", "500g"), ("olive oil", "1/4 cup")])
    http.meals = [changed]
    recipes.sync_catalog(minimum=1)
    assert store.recipe_get("52771")["status"] == "raw"  # the recipe itself changed: it is prepared again


def test_the_background_turn_syncs_once_prepares_one_recipe_and_rests_longer_when_something_fails(wger, monkeypatch):
    synced = []

    def sync():
        synced.append(1)
        store.recipes_upsert([recipes.normalize(meal()), recipes.normalize(meal("2", "Silent"))])
        store.set_kv("recipes_synced_at", recipes.datetime.now(recipes.timezone.utc).isoformat())
        return 2

    monkeypatch.setattr(recipes, "sync_catalog", sync)
    monkeypatch.setattr(main, "get_vision_client", lambda: Editor({"Spicy Arrabiata Penne": ARRABIATA}))
    monkeypatch.setattr(recipes.settings, "recipes_prep_seconds", 20)
    monkeypatch.setattr(recipes, "_fails", 0)
    rests = [recipes.tick() for _ in range(3)]
    assert synced == [1]  # the catalog is read once (then once a week), not on every turn
    counts = store.recipes_counts()
    assert counts["ready"] == 1 and sorted(rests)[0] == 20 and max(rests) >= 120  # a failure waits longer before the next try
    monkeypatch.setattr(recipes.settings, "gemini_api_key", "")
    assert recipes.tick() == 600  # without the model nothing is prepared (and nothing is marked as failed)
    assert store.recipes_counts() == counts


def test_deep_diagnostics_check_the_recipe_book(wger, monkeypatch):
    from app import diagnostics

    monkeypatch.setattr(diagnostics.httpx, "get", lambda url, **_: type("R", (), {
        "raise_for_status": lambda self: None, "json": lambda self: {"categories": [{"strCategory": "Beef"}]}})())
    monkeypatch.setattr(diagnostics.settings, "recipes_sync", True)
    monkeypatch.setattr(diagnostics.settings, "gemini_api_key", "")
    checks: list[dict] = []
    diagnostics._recipe_checks(checks)
    assert [(c["name"], c["ok"]) for c in checks] == [("Recetario: la fuente responde", True), ("Recetario: descargado", False)]
    file_and_prepare(wger, [meal()], {"Spicy Arrabiata Penne": ARRABIATA})
    checks.clear()
    diagnostics._recipe_checks(checks)
    assert checks[1]["ok"] and checks[1]["detail"].startswith("1 recetas listas")
