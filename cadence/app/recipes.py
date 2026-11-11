"""Real recipes with real photos, for each person's own numbers.

Where they come from: TheMealDB (https://www.themealdb.com): every recipe has a photo of the finished dish and every ingredient
has its own picture. wger has no recipes at all, and its ingredient pictures are supermarket packaging that only arrive with
celery (which is off here). TheMealDB's terms let us copy and modify what its API returns ("as long as you use the official end
points") and ask for attribution; a public release on an app store needs their one-off supporter key (MEALDB_API_KEY).

What happens here, without any step on the server:
1. `sync_catalog` reads the whole catalog through the official API (once a week) and files it in `recipes` (status raw).
2. A background thread prepares one recipe at a time: Gemini puts it into Spanish and converts each measure to grams and the
   recipe to servings (NEVER calories), and every ingredient is looked up in the food catalog AS IT GOES INTO THE POT (raw rice,
   not cooked rice). Calories and macros per serving come only from the catalog. A recipe of which too little is in the catalog
   is set aside instead of being shown with made-up numbers.
3. Photos are fetched from TheMealDB the first time someone needs them and kept on the data volume.

Each person then sees the recipes that fit what is left of THEIR day, with the portion that lands closest (see `portion_for`).
"""

import hashlib
import logging
import re
import threading
import time as clock
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

from . import store
from .config import settings
from .matching import rank_matches

logger = logging.getLogger("cadence.recipes")

HOST = "https://www.themealdb.com"
CREDIT = "Receta y fotos: TheMealDB"
PREP_VERSION = 1  # raise it when the preparation rules change: everything is prepared again in the background
SYNC_EVERY = timedelta(days=7)
MEALS = ("desayuno", "almuerzo", "merienda", "cena")
# The part of the day's calories each meal usually brings (the same shares the meal score uses).
SHARE = {"desayuno": 0.25, "almuerzo": 0.35, "merienda": 0.10, "cena": 0.30}
MIN_MATCH = 62  # 0-100: below this the catalog food does not read as the same ingredient
MIN_COVERAGE = 0.7  # at least this much of the recipe's weight must be in the catalog
KCAL_RANGE = (60, 1500)  # per serving; outside it the servings or a match are wrong

CATEGORY_ES = {
    "Beef": "Carne de res", "Chicken": "Pollo", "Dessert": "Postre", "Lamb": "Cordero", "Miscellaneous": "Variado", "Pasta": "Pasta",
    "Pork": "Cerdo", "Seafood": "Pescado y mariscos", "Side": "Acompañamiento", "Starter": "Entrada", "Vegan": "Vegano",
    "Vegetarian": "Vegetariano", "Breakfast": "Desayuno", "Goat": "Cabra",
}
AREA_ES = {
    "afghanistan": "Afganistán", "albania": "Albania", "algerian": "Argelia", "andorra": "Andorra", "angola": "Angola",
    "antigua and barbuda": "Antigua y Barbuda", "argentina": "Argentina", "armenia": "Armenia", "aruba": "Aruba",
    "australian": "Australia", "austria": "Austria", "azerbaijan": "Azerbaiyán", "bahamas": "Bahamas", "bangladesh": "Bangladés",
    "barbados": "Barbados", "belgium": "Bélgica", "botswana": "Botsuana", "brazil": "Brasil", "british": "Reino Unido",
    "bulgaria": "Bulgaria", "cambodia": "Camboya", "canadian": "Canadá", "cayman islands": "Islas Caimán", "chile": "Chile",
    "chinese": "China", "colombia": "Colombia", "costa rica": "Costa Rica", "croatian": "Croacia", "cuba": "Cuba",
    "denmark": "Dinamarca", "dominica": "Dominica", "egyptian": "Egipto", "estonia": "Estonia", "filipino": "Filipinas",
    "france": "Francia", "french": "Francia", "greek": "Grecia", "india": "India", "indian": "India", "irish": "Irlanda",
    "italian": "Italia", "jamaican": "Jamaica", "japanese": "Japón", "kenyan": "Kenia", "laos": "Laos", "malaysian": "Malasia",
    "mexican": "México", "moroccan": "Marruecos", "netherlands": "Países Bajos", "dutch": "Países Bajos", "norway": "Noruega",
    "panamanian": "Panamá", "peruvian": "Perú", "polish": "Polonia", "portuguese": "Portugal", "russian": "Rusia",
    "saudi arabian": "Arabia Saudita", "slovakia": "Eslovaquia", "spanish": "España", "syrian": "Siria", "thai": "Tailandia",
    "tunisian": "Túnez", "turkish": "Turquía", "ukrainian": "Ucrania", "united states": "Estados Unidos", "american": "Estados Unidos",
    "uruguayan": "Uruguay", "venezuela": "Venezuela", "vietnamese": "Vietnam",
}
# Kitchens closest to the people who use cadence: their recipes are prepared (and so appear) first.
NEAR = {"spanish", "mexican", "argentina", "venezuela", "uruguayan", "colombia", "costa rica", "cuba", "chile", "brazil",
        "panamanian", "peruvian", "jamaican", "dominica", "barbados", "aruba", "bahamas", "cayman islands", "antigua and barbuda"}


class Unusable(Exception):
    """This recipe cannot be shown with honest numbers (too little of it is in the catalog, or the result makes no sense)."""


# ------------------------------------------------------------------ reading the source

def priority(category: str, area: str) -> int:
    """Lower is prepared sooner: nearby kitchens and breakfasts, then main dishes, then sides, desserts last."""
    near = area.lower() in NEAR
    if category == "Dessert":
        return 3
    if category in ("Side", "Starter"):
        return 1 if near else 2
    return 0 if near or category == "Breakfast" else 1


def normalize(raw: dict) -> dict | None:
    """One meal as TheMealDB sends it -> what cadence files. None for anything incomplete or pointing outside their site."""
    recipe_id = str(raw.get("idMeal") or "").strip()
    name = " ".join(str(raw.get("strMeal") or "").split())
    thumb = str(raw.get("strMealThumb") or "").strip()
    if not recipe_id.isdigit() or not name or not thumb.startswith(f"{HOST}/images/media/meals/") or ".." in thumb:
        return None
    ingredients = []
    for i in range(1, 21):
        ingredient = " ".join(str(raw.get(f"strIngredient{i}") or "").split())
        if ingredient:
            ingredients.append({"name": ingredient[:60], "measure": " ".join(str(raw.get(f"strMeasure{i}") or "").split())[:60]})
    instructions = str(raw.get("strInstructions") or "").strip()
    if len(ingredients) < 2 or len(instructions) < 40:
        return None
    category = str(raw.get("strCategory") or "").strip()
    area = str(raw.get("strArea") or raw.get("strCountry") or "").strip()
    links = {key: str(raw.get(field) or "").strip() for key, field in (("source", "strSource"), ("youtube", "strYoutube"))}
    return {"id": recipe_id, "name": name[:120], "category": category, "area": area, "thumb": thumb, "prio": priority(category, area),
            "raw": {"ingredients": ingredients, "instructions": instructions[:6000],
                    **{key: url for key, url in links.items() if url.startswith("https://")}}}


def sync_catalog(minimum: int = 50) -> int:
    """Read every recipe through the official API (one request per first letter) and file the new or changed ones."""
    rows: dict[str, dict] = {}
    with httpx.Client(timeout=25, headers={"User-Agent": "cadence"}) as http:
        for letter in "abcdefghijklmnopqrstuvwxyz0123456789":
            response = http.get(f"{HOST}/api/json/v1/{quote(settings.mealdb_api_key, safe='')}/search.php", params={"f": letter})
            response.raise_for_status()
            meals = response.json().get("meals")
            for raw in meals if isinstance(meals, list) else []:
                row = normalize(raw) if isinstance(raw, dict) else None
                if row:
                    rows[row["id"]] = row
            clock.sleep(0.25)  # a guest on a free service: no hurry
    if len(rows) < minimum:
        raise RuntimeError(f"TheMealDB devolvio solo {len(rows)} recetas")  # a broken answer is not the catalog
    added = store.recipes_upsert(list(rows.values()))
    store.set_kv("recipes_synced_at", datetime.now(timezone.utc).isoformat())
    _ready.update(at=0.0)
    return added


# ------------------------------------------------------------------ measures and foods

_AMOUNT = r"(\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+(?:[.,]\d+)?|[½¼¾⅓⅔])"
_WEIGHT = re.compile(rf"^\s*{_AMOUNT}\s*(kg|kilos?|grams?|gms?|gr|g|ml|litres?|liters?|lbs?|l|ounces?|oz|pounds?)\b", re.IGNORECASE)
_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3}
_UNIT_GRAMS = {"kg": 1000, "kilo": 1000, "g": 1, "gr": 1, "gram": 1, "gm": 1, "ml": 1, "l": 1000, "litre": 1000, "liter": 1000,
               "oz": 28.35, "ounce": 28.35, "lb": 453.6, "pound": 453.6}


def _amount(text: str) -> float:
    text = re.sub(r"\s*/\s*", "/", text.strip())
    if text in _FRACTIONS:
        return _FRACTIONS[text]
    whole, _, fraction = text.rpartition(" ") if "/" in text else ("", "", text)
    if "/" in fraction:
        top, bottom = (float(part) for part in fraction.split("/"))
        return (float(whole) if whole.strip() else 0.0) + (top / bottom if bottom else 0.0)
    return float(fraction.replace(",", "."))


def explicit_grams(measure: str) -> float | None:
    """Grams when the recipe itself states a weight or a volume ("200g", "1 lb", "500 ml"; 1 ml counts as 1 g).
    None for cups, spoons, pieces and "to taste": those are the model's to estimate."""
    match = _WEIGHT.match(measure or "")
    if not match:
        return None
    unit = match.group(2).lower()
    unit = unit if unit in _UNIT_GRAMS else unit.rstrip("s")
    grams = _amount(match.group(1)) * _UNIT_GRAMS.get(unit, 0)
    return round(grams, 1) if 0.5 <= grams <= 5000 else None


_COOKED = re.compile(r"\b(cooked|boiled|grilled|fried|baked|roasted|steamed|mashed|scrambled|cocid[oa]s?|hervid[oa]s?|frit[oa]s?|"
                     r"asad[oa]s?|plancha|horno|revueltos?|pure)\b", re.IGNORECASE)


def find_food(wger, term: str, alternatives: list[str]) -> dict | None:
    """The catalog food for a recipe ingredient AS IT GOES INTO THE POT. The ready-to-eat staples ("Cooked white rice") are
    left out unless the recipe says the ingredient is added cooked: 200 g of raw rice is not 200 g of cooked rice."""
    wants_cooked = bool(_COOKED.search(term))
    pool: list[dict] = []
    seen: set = set()
    for word in dict.fromkeys(w for w in [term, *alternatives] if w):
        for item in wger.search_ingredients(word, limit=settings.search_fetch_limit):
            if item["id"] in seen or (item.get("source") == "cadence" and not wants_cooked and _COOKED.search(item["name"] or "")):
                continue
            seen.add(item["id"])
            pool.append(item)
        ranked = rank_matches(term, pool, 1, alt=alternatives)
        if ranked and ranked[0][0] >= 90:
            break  # found by its first name: the other names are not needed
    else:
        ranked = rank_matches(term, pool, 1, alt=alternatives)
    if not ranked or ranked[0][0] < MIN_MATCH:
        return None
    item = ranked[0][1]
    if item.get("energy") is None:
        item = {**item, **wger.get_ingredient(item["id"])}  # older wger: the search hit has no nutrition values
    try:
        food = {"id": int(item["id"]), "name": str(item["name"]),
                **{key: float(item.get(key) or 0) for key in ("energy", "protein", "carbohydrates", "fat")}}
    except (TypeError, ValueError):
        return None
    return food if 0 <= food["energy"] <= 900 else None


def image_key(ingredient: str) -> str:
    """TheMealDB names each ingredient picture after the ingredient, with underscores for spaces."""
    return "_".join(ingredient.lower().split())


def slots(category: str, said: list[str]) -> list[str]:
    """Which meals a recipe is offered for. The source's category decides the clear cases; the model's reading the rest."""
    said = [meal for meal in said if meal in MEALS]
    if category == "Dessert":
        return ["merienda"]
    if category == "Breakfast":
        return said or ["desayuno"]
    return said or ["almuerzo", "cena"]


def build(recipe: dict, said: dict, find) -> dict:
    """The recipe as cadence shows and logs it. `said` is the model's edited text and grams; `find(term, alternatives)` looks a
    food up in the catalog. Every calorie here is catalog value x grams. Raises Unusable instead of guessing."""
    servings = said["servings"]
    ingredients, counted, missing = [], [], []
    total_grams = found_grams = 0.0
    for index, original in enumerate(recipe["raw"]["ingredients"], start=1):
        info = said["items"].get(index) or {}
        label = info.get("name") or original["name"]
        ingredients.append({"name": label, "measure": info.get("measure") or original["measure"], "img": image_key(original["name"])})
        if not info or info.get("skip"):
            continue
        grams = explicit_grams(original["measure"]) or info.get("grams")  # a weight written in the recipe beats an estimate
        if not grams:
            continue
        total_grams += grams
        food = find(info.get("search_name") or original["name"], [*info.get("search_alternatives", []), original["name"]])
        if food is None:
            missing.append(label)
            continue
        found_grams += grams
        counted.append((food, grams, label, bool(info.get("liquid")), ingredients[-1]["img"]))
    if len(counted) < 2 or found_grams < MIN_COVERAGE * total_grams:
        raise Unusable("muy poco de la receta esta en el catalogo")

    by_food: dict[int, dict] = {}
    for food, grams, label, liquid, img in counted:
        per_serving = grams / servings
        if per_serving < 1 or food["energy"] * per_serving / 100 < 3:
            continue  # a pinch: it is in the ingredient list, but it is not worth a line in the diary
        item = by_food.setdefault(food["id"], {"ingredient_id": food["id"], "name": food["name"], "label": label, "grams": 0.0,
                                               "liquid": liquid, "img": img, "food": food})
        item["grams"] += per_serving
    items = []
    totals = {"energy": 0.0, "protein": 0.0, "carbohydrates": 0.0, "fat": 0.0}
    for item in by_food.values():
        food = item.pop("food")
        item["grams"] = float(max(1, round(item["grams"])))  # what is shown is exactly what gets logged
        for key in totals:
            totals[key] += food[key] * item["grams"] / 100
        items.append(item)
    if len(items) < 2 or not KCAL_RANGE[0] <= totals["energy"] <= KCAL_RANGE[1]:
        raise Unusable("las calorias por porcion no tienen sentido")
    return {
        "name": said["name"], "servings": servings, "minutes": said.get("minutes"), "slots": slots(recipe["category"], said.get("meals") or []),
        "steps": said["steps"], "ingredients": ingredients, "items": items, "missing": missing,
        "kcal": round(totals["energy"]), "protein": round(totals["protein"], 1), "carbs": round(totals["carbohydrates"], 1),
        "fat": round(totals["fat"], 1),
    }


# ------------------------------------------------------------------ preparing in the background

_ready: dict = {"at": 0.0, "items": []}
_foods: dict[str, dict | None] = {}  # ingredient as searched -> catalog food (None = not in the catalog)
_fails = 0


def prepare_one(recipe: dict, ai, wger) -> bool:
    """Prepare one filed recipe. False when something OUTSIDE the recipe failed (the model, the catalog): it stays for later."""
    def find(term: str, alternatives: list[str]) -> dict | None:
        # The same few hundred ingredients (onion, garlic, olive oil...) appear in recipe after recipe: each is looked up in the
        # catalog once per run of the app, not once per recipe (the server is shared and wger's search is not cheap).
        key = term.lower()
        if key not in _foods:
            _foods[key] = find_food(wger, term, alternatives)
        return _foods[key]

    try:
        said = ai.prepare_recipe(name=recipe["name"], category=recipe["category"] or "", area=recipe["area"] or "",
                                 ingredients=recipe["raw"]["ingredients"], instructions=recipe["raw"]["instructions"])
        prepared = build(recipe, said, find)
    except Unusable as exc:
        logger.info("receta %s apartada: %s", recipe["id"], exc)
        store.recipe_set_prepared(recipe["id"], None, PREP_VERSION)
        return True
    except Exception:  # noqa: BLE001 - Gemini or the catalog did not answer, or answered something unreadable
        logger.exception("no se pudo preparar la receta %s", recipe["id"])
        store.recipe_failed(recipe["id"])
        return False
    store.recipe_set_prepared(recipe["id"], prepared, PREP_VERSION)
    _ready.update(at=0.0)
    return True


def _sync_due() -> bool:
    stamp = store.get_kv("recipes_synced_at")
    try:
        return stamp is None or datetime.now(timezone.utc) - datetime.fromisoformat(stamp) > SYNC_EVERY
    except ValueError:
        return True


def tick() -> float:
    """One turn of the background thread; returns how many seconds to rest before the next."""
    global _fails
    if _sync_due():
        try:
            added = sync_catalog()
            logger.info("recetario sincronizado: %s recetas nuevas", added)
        except Exception:  # noqa: BLE001 - their site may be down; what is already filed keeps working
            logger.exception("no se pudo leer el recetario de TheMealDB")
            if not store.recipes_counts()["total"]:
                return 900
            store.set_kv("recipes_synced_at", (datetime.now(timezone.utc) - SYNC_EVERY + timedelta(hours=6)).isoformat())
    if not settings.gemini_api_key or not settings.wger_api_token:
        return 600
    recipe = store.recipe_next_raw()
    if recipe is None:
        return 1800
    from . import main  # late: main imports this module, and tests replace its clients

    wger = main.get_wger_client()
    try:
        ok = prepare_one(recipe, main.get_vision_client(), wger)
    finally:
        wger.close()
    _fails = 0 if ok else _fails + 1
    return max(1, settings.recipes_prep_seconds) if ok else min(1800, 60 * 2 ** min(_fails, 5))


def start_worker() -> None:
    if not settings.recipes_sync:
        return

    def loop():
        clock.sleep(20)  # let the app come up first
        try:
            store.recipes_requeue(PREP_VERSION)
        except Exception:  # noqa: BLE001
            logger.exception("no se pudo revisar el recetario")
        while True:
            try:
                rest = tick()
            except Exception:  # noqa: BLE001 - the loop must survive anything
                logger.exception("fallo el preparador de recetas")
                rest = 300
            clock.sleep(rest)

    threading.Thread(target=loop, name="recipes", daemon=True).start()


# ------------------------------------------------------------------ what each person sees

def _plain(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(ch) != "Mn")


def ready() -> list[dict]:
    """Every prepared recipe, as the list needs it (re-read from the store at most once a minute)."""
    now = clock.monotonic()
    if not _ready["at"] or now - _ready["at"] > 60:
        items = []
        for row in store.recipes_ready():
            prepared = row["prepared"]
            items.append({
                "id": row["id"], "name": prepared["name"], "original": row["name"], "category": row["category"],
                "area": AREA_ES.get((row["area"] or "").lower()), "kcal": prepared["kcal"], "protein": prepared["protein"],
                "carbs": prepared["carbs"], "fat": prepared["fat"], "minutes": prepared.get("minutes"), "servings": prepared["servings"],
                "slots": prepared["slots"],
                "words": _plain(" ".join([prepared["name"], row["name"], *(i["name"] for i in prepared["ingredients"])])),
            })
        _ready.update(at=now, items=items)
    return _ready["items"]


def target_kcal(goal_kcal: float, kcal_left: float | None, meal: str) -> float:
    """What this meal should bring for this person: its usual share of their goal, never more than what is left of the day."""
    share = goal_kcal * SHARE.get(meal, 0.3)
    return share if kcal_left is None else max(100.0, min(share, kcal_left))


def portion_for(kcal_serving: float, target: float) -> float:
    """How much of the recipe to serve yourself, in halves between 0.5 and 2: the portion that lands closest to the target."""
    return min(2.0, max(0.5, round(target / max(kcal_serving, 1) * 2) / 2))


def _daily_shuffle(day: str, recipe_id: str) -> float:
    """0..1, fixed for a recipe and a day: among recipes that fit equally well, the order changes every day."""
    return int(hashlib.sha1(f"{day}:{recipe_id}".encode()).hexdigest()[:6], 16) / 0xFFFFFF


def rank(items: list[dict], target: float, kcal_left: float | None, day: str) -> list[tuple[dict, float, bool]]:
    """(recipe, portion, fits) best first: closest to the calories this meal should bring, protein as the tie-breaker."""
    scored = []
    for item in items:
        portion = portion_for(item["kcal"], target)
        kcal = item["kcal"] * portion
        off = abs(kcal - target) / target
        protein_share = min(1.0, item["protein"] * 4 / max(item["kcal"], 1) / 0.3)  # 30 % of its calories from protein = full marks
        fits = off <= 0.25 and (kcal_left is None or kcal <= kcal_left * 1.05)
        scored.append((off - 0.15 * protein_share + 0.12 * _daily_shuffle(day, item["id"]), item, portion, fits))
    scored.sort(key=lambda row: (row[0], row[1]["name"]))
    return [(item, portion, fits) for _, item, portion, fits in scored]


def search(items: list[dict], text: str) -> list[dict]:
    words = _plain(text).split()
    return [item for item in items if all(word in item["words"] for word in words)]


# ------------------------------------------------------------------ photos (fetched once, kept on the data volume)

_SIZES = {"s": "/small", "m": "/medium", "l": "/large"}
_KEY = re.compile(r"[\w\-',&]{1,60}")
_missing: dict[str, float] = {}


def _cached(name: str, url: str) -> tuple[bytes, str] | None:
    folder = Path(settings.data_dir) / "recipe-photos"
    path = folder / hashlib.sha1(name.encode()).hexdigest()
    if path.exists():
        data = path.read_bytes()
    else:
        if clock.monotonic() - _missing.get(name, float("-inf")) < 3600:
            return None  # it was not there a moment ago: do not ask their site again on every view
        try:
            response = httpx.get(url, timeout=15, headers={"User-Agent": "cadence"})
            data = response.content if response.status_code == 200 else b""
        except httpx.HTTPError:
            data = b""
        if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n") or len(data) > 3_000_000:
            _missing[name] = clock.monotonic()
            return None
        folder.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{threading.get_ident()}.tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
    return data, "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"


def recipe_photo(recipe: dict, size: str) -> tuple[bytes, str] | None:
    """The dish photo. The address was checked when the recipe was filed (`normalize`): it is always on TheMealDB's site."""
    suffix = _SIZES.get(size, "/medium")
    return _cached(f"meal:{recipe['id']}:{suffix}", recipe["thumb"] + suffix)


def ingredient_photo(key: str) -> tuple[bytes, str] | None:
    if not _KEY.fullmatch(key):
        return None
    return _cached(f"ingredient:{key}", f"{HOST}/images/ingredients/{quote(key, safe='')}-small.png")
