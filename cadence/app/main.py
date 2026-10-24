from datetime import date, timedelta

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .matching import rank_candidates
from .meals import MEAL_LABELS, MEAL_ORDER, compute_streak, entry_date, meal_key_for_entry
from .schemas import (
    AnalyzeResponse,
    ComponentMatch,
    ConfirmedEntry,
    ConfirmRequest,
    ConfirmResponse,
    IngredientDetail,
    MacroTotals,
    MealGroup,
    MealItem,
    TodayResponse,
)
from .vision import GeminiVisionClient
from .wger_client import WgerClient, WgerError

app = FastAPI(title="cadence", version="0.1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

_vision_client: GeminiVisionClient | None = None


def get_vision_client() -> GeminiVisionClient:
    global _vision_client
    if _vision_client is None:
        if not settings.gemini_api_key:
            raise HTTPException(500, "GEMINI_API_KEY no esta configurado")
        _vision_client = GeminiVisionClient(settings.gemini_api_key, settings.gemini_model)
    return _vision_client


def get_wger_client() -> WgerClient:
    if not settings.wger_api_token:
        raise HTTPException(500, "WGER_API_TOKEN no esta configurado")
    return WgerClient(settings.wger_base_url, settings.wger_api_token, settings.wger_language_id)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
@app.get("/index.html")
def index_page():
    return FileResponse("static/index.html")


@app.get("/sw.js")
def service_worker():
    # Served at the app root (not /static/sw.js) on purpose: a service
    # worker's default scope is its own directory, and we need it to
    # control every page under /cadence/, not just /cadence/static/.
    return FileResponse("static/sw.js", media_type="application/javascript")


@app.get("/scan.html")
def scan_page():
    return FileResponse("static/scan.html")


@app.get("/confirm.html")
def confirm_page():
    return FileResponse("static/confirm.html")


@app.get("/api/today", response_model=TodayResponse)
def today():
    wger = get_wger_client()
    try:
        plan_id = settings.default_nutrition_plan_id or wger.get_default_nutrition_plan_id()
        plan = wger.get_nutrition_plan(plan_id)

        today_date = date.today()
        history_start = today_date - timedelta(days=30)
        entries = wger.get_diary_entries(plan_id, history_start, today_date)

        streak_days = compute_streak(entries, today_date)
        today_entries = [e for e in entries if entry_date(e) == today_date]

        ingredient_cache: dict[int, dict] = {}

        def macros_for(ingredient_id: int) -> dict:
            if ingredient_id not in ingredient_cache:
                ingredient_cache[ingredient_id] = wger.get_ingredient(ingredient_id)
            return ingredient_cache[ingredient_id]

        groups: dict[str, list[MealItem]] = {key: [] for key in MEAL_ORDER}
        totals = MacroTotals()

        for entry in today_entries:
            ingredient_id = entry["ingredient"]
            amount = float(entry["amount"])
            ingredient = macros_for(ingredient_id)
            ratio = amount / 100.0
            kcal = float(ingredient.get("energy", 0) or 0) * ratio
            protein = float(ingredient.get("protein", 0) or 0) * ratio
            carbs = float(ingredient.get("carbohydrates", 0) or 0) * ratio
            fat = float(ingredient.get("fat", 0) or 0) * ratio

            totals.kcal += kcal
            totals.protein_g += protein
            totals.carbs_g += carbs
            totals.fat_g += fat

            key = meal_key_for_entry(entry)
            groups[key].append(
                MealItem(
                    diary_entry_id=entry["id"],
                    ingredient_id=ingredient_id,
                    name=ingredient.get("name", "?"),
                    amount_grams=amount,
                    kcal=round(kcal, 1),
                )
            )

        meals = []
        for key in MEAL_ORDER:
            items = groups[key]
            if not items:
                continue
            meals.append(
                MealGroup(
                    key=key,
                    label=MEAL_LABELS[key],
                    totals=MacroTotals(
                        kcal=round(sum(i.kcal for i in items), 1),
                        protein_g=0,
                        carbs_g=0,
                        fat_g=0,
                    ),
                    items=items,
                )
            )

        goal = MacroTotals(
            kcal=float(plan.get("goal_energy") or settings.fallback_goal_kcal),
            protein_g=float(plan.get("goal_protein") or settings.fallback_goal_protein_g),
            carbs_g=float(plan.get("goal_carbohydrates") or settings.fallback_goal_carbs_g),
            fat_g=float(plan.get("goal_fat") or settings.fallback_goal_fat_g),
        )

        return TodayResponse(
            date=today_date.isoformat(),
            totals=MacroTotals(
                kcal=round(totals.kcal, 1),
                protein_g=round(totals.protein_g, 1),
                carbs_g=round(totals.carbs_g, 1),
                fat_g=round(totals.fat_g, 1),
            ),
            goal=goal,
            meals=meals,
            streak_days=streak_days,
        )
    finally:
        wger.close()


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(image: UploadFile):
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, "Imagen vacia")

    vision = get_vision_client()
    detected = vision.identify_components(image_bytes, image.content_type or "image/jpeg")
    if not detected:
        raise HTTPException(422, "No se identifico ningun alimento en la foto")

    wger = get_wger_client()
    try:
        components = []
        for component in detected:
            raw_matches = wger.search_ingredients(component.name)
            candidates = rank_candidates(component.name, raw_matches, settings.match_candidate_count)
            if candidates:
                # Only the top pick, to keep this endpoint's latency bounded -
                # other candidates' macros are fetched on demand if the user
                # switches to them (GET /api/ingredient/{id}).
                try:
                    top = wger.get_ingredient(candidates[0].id)
                    candidates[0].energy_kcal_100g = float(top.get("energy", 0) or 0)
                except Exception:
                    pass
            components.append(
                ComponentMatch(
                    detected_name=component.name,
                    confidence=component.confidence,
                    candidates=candidates,
                )
            )
    finally:
        wger.close()

    return AnalyzeResponse(components=components)


@app.get("/api/ingredient/{ingredient_id}", response_model=IngredientDetail)
def ingredient_detail(ingredient_id: int):
    wger = get_wger_client()
    try:
        data = wger.get_ingredient(ingredient_id)
        return IngredientDetail(
            id=data["id"],
            name=data.get("name", "?"),
            energy_kcal_100g=float(data.get("energy", 0) or 0),
            protein_100g=float(data.get("protein", 0) or 0),
            carbs_100g=float(data.get("carbohydrates", 0) or 0),
            fat_100g=float(data.get("fat", 0) or 0),
        )
    finally:
        wger.close()


@app.delete("/api/diary/{entry_id}")
def delete_diary_entry(entry_id: int):
    wger = get_wger_client()
    try:
        wger.delete_diary_entry(entry_id)
        return {"status": "deleted"}
    except WgerError as exc:
        raise HTTPException(502, str(exc)) from exc
    finally:
        wger.close()


@app.post("/api/confirm", response_model=ConfirmResponse)
def confirm(request: ConfirmRequest):
    wger = get_wger_client()
    try:
        plan_id = request.plan_id or settings.default_nutrition_plan_id or wger.get_default_nutrition_plan_id()

        created = []
        for item in request.items:
            try:
                diary_entry_id = wger.log_diary_entry(plan_id, item.ingredient_id, item.amount_grams)
            except WgerError as exc:
                raise HTTPException(502, str(exc)) from exc
            created.append(
                ConfirmedEntry(
                    ingredient_id=item.ingredient_id,
                    amount_grams=item.amount_grams,
                    diary_entry_id=diary_entry_id,
                )
            )
        return ConfirmResponse(created=created)
    finally:
        wger.close()
