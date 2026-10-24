from time import monotonic
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta

import httpx
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .diagnostics import run_diagnostics
from .matching import rank_candidates, rank_matches
from .meals import (
    MEAL_LABELS,
    MEAL_ORDER,
    compute_streak,
    datetime_for_meal,
    entry_date,
    entry_datetime,
    local_now,
    meal_key_for_entry,
    parse_taken_at,
)
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
    SearchResult,
    TodayResponse,
    WgerStatus,
)
from .vision import GeminiVisionClient
from .wger_client import WgerClient, WgerError

logger = logging.getLogger("cadence")
app = FastAPI(title="cadence", version="0.1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")

_vision_client: GeminiVisionClient | None = None


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    # A bare "Internal Server Error" tells the user (and us) nothing. Log the full
    # traceback for the container logs and return the cause in the JSON `detail`
    # that the UI already shows in its error banner.
    logger.exception("error no controlado en %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"Error interno ({type(exc).__name__}): {exc}"[:300]})


@app.exception_handler(WgerError)
async def wger_error_handler(request: Request, exc: WgerError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(httpx.HTTPError)
async def wger_http_error_handler(request: Request, exc: httpx.HTTPError):
    # Without this any wger failure (bad token, wrong URL, 404...) surfaced as
    # an opaque "Internal Server Error" with no hint of what to fix.
    if isinstance(exc, httpx.HTTPStatusError):
        detail = f"wger respondio {exc.response.status_code} en {exc.request.url.path}"
        if exc.response.status_code in (401, 403):
            detail += " - revisa WGER_API_TOKEN"
    else:
        detail = f"No se pudo conectar con wger ({type(exc).__name__}) - revisa WGER_BASE_URL"
    return JSONResponse(status_code=502, content={"detail": detail})


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
    return WgerClient(settings.wger_base_url, settings.wger_api_token, settings.wger_language_id, settings.wger_language_code)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/meal-now")
def meal_now(at: str | None = None):
    """Which meal slot a moment falls in (TIMEZONE); 'otro' outside all windows.

    `at` is the photo's own time when it has one; otherwise the clock. This is only
    a suggestion: the UI always lets the user pick a different meal."""
    when = parse_taken_at(at, local_now())
    return {"meal": meal_key_for_entry({"datetime": when.isoformat()}), "at": when.isoformat()}


_staples_cache: dict = {"at": 0.0, "items": []}


def candidate_pool(wger: WgerClient, term: str) -> list[dict]:
    """wger's text search plus the ready-to-eat staples (cached 10 min), without repeats."""
    pool = wger.search_ingredients(term, limit=settings.search_fetch_limit)
    now = monotonic()
    if now - _staples_cache["at"] > 600:
        try:
            _staples_cache.update(at=now, items=wger.list_staples())
        except Exception:  # noqa: BLE001 - staples are a bonus; search works without them
            logger.exception("no se pudieron leer los basicos")
            _staples_cache.update(at=now - 540, items=_staples_cache["items"])  # retry in a minute
    seen = {item["id"] for item in pool}
    return pool + [item for item in _staples_cache["items"] if item["id"] not in seen]


_wger_status_cache: dict = {"at": 0.0, "value": None}


@app.get("/api/wger-status", response_model=WgerStatus)
def wger_status():
    """Cheap reachability probe for the sidebar dot / offline banner (cached 60 s)."""
    now = monotonic()
    cached = _wger_status_cache["value"]
    if cached is not None and now - _wger_status_cache["at"] < 60:
        return cached
    if not settings.wger_api_token:
        result = WgerStatus(ok=False, detail="WGER_API_TOKEN no esta configurado")
    else:
        wger = get_wger_client()
        try:
            wger._client.get("/api/v2/nutritionplan/", params={"limit": 1, "format": "json"}).raise_for_status()
            result = WgerStatus(ok=True)
        except Exception as exc:  # noqa: BLE001 - any failure means "not reachable"
            result = WgerStatus(ok=False, detail=type(exc).__name__)
        finally:
            wger.close()
    _wger_status_cache.update(at=now, value=result)
    return result


@app.get("/api/diagnostics")
def diagnostics(deep: bool = False):
    """Checklist of everything cadence needs; ?deep=1 also calls Gemini once."""
    wger = None
    if settings.wger_api_token:
        wger = WgerClient(settings.wger_base_url, settings.wger_api_token, settings.wger_language_id, settings.wger_language_code)
    try:
        return run_diagnostics(wger, deep=deep)
    finally:
        if wger:
            wger.close()


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


@app.get("/search.html")
def search_page():
    return FileResponse("static/search.html")


@app.get("/api/today", response_model=TodayResponse)
def today():
    wger = get_wger_client()
    try:
        plan_id = settings.default_nutrition_plan_id or wger.find_default_nutrition_plan_id()
        if plan_id is None:
            # Nothing logged yet: show an empty day instead of creating a plan on a read.
            return TodayResponse(
                date=local_now().date().isoformat(),
                totals=MacroTotals(),
                goal=MacroTotals(
                    kcal=settings.fallback_goal_kcal,
                    protein_g=settings.fallback_goal_protein_g,
                    carbs_g=settings.fallback_goal_carbs_g,
                    fat_g=settings.fallback_goal_fat_g,
                ),
                meals=[],
                streak_days=0,
                user_name=settings.user_name,
            )
        try:
            plan = wger.get_nutrition_plan(plan_id)
        except Exception:  # noqa: BLE001 - goals fall back to defaults, the diary still shows
            logger.exception("no se pudo leer el plan %s", plan_id)
            plan = {}

        now = local_now()
        today_date = now.date()
        history_start = datetime.combine(today_date - timedelta(days=30), time.min, tzinfo=now.tzinfo)
        day_end = datetime.combine(today_date, time.max, tzinfo=now.tzinfo)
        entries = wger.get_diary_entries(plan_id, history_start, day_end)

        streak_days = compute_streak(entries, today_date)
        today_entries = [e for e in entries if entry_date(e) == today_date]

        ingredient_cache: dict[int, dict] = {}

        def macros_for(ingredient_id: int) -> dict:
            if ingredient_id not in ingredient_cache:
                try:
                    ingredient_cache[ingredient_id] = wger.get_ingredient(ingredient_id)
                except Exception:  # noqa: BLE001
                    logger.exception("no se pudo leer el alimento %s", ingredient_id)
                    ingredient_cache[ingredient_id] = {"name": "(alimento no disponible)"}
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
                    diary_entry_id=str(entry["id"]),  # UUID text on current wger, int on older ones
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
            user_name=settings.user_name,
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
            # Search/rank with the English generic name (wger's DB language);
            # detected_name stays the Spanish label the user sees.
            term = component.search_name or component.name
            raw_matches = candidate_pool(wger, term)
            candidates = rank_candidates(term, raw_matches, settings.match_candidate_count, alt=component.name)
            if candidates and candidates[0].energy_kcal_100g is None:
                # Older wger versions don't send nutrition values with the search
                # hit; fetch the top pick only (others load on demand through
                # GET /api/ingredient/{id}) to keep this endpoint's latency bounded.
                try:
                    top = wger.get_ingredient(candidates[0].id)
                    candidates[0].energy_kcal_100g = float(top.get("energy", 0) or 0)
                except Exception:
                    pass
            components.append(
                ComponentMatch(
                    detected_name=component.name,
                    confidence=component.confidence,
                    estimated_grams=component.estimated_grams,
                    box=component.box,
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


@app.get("/api/search", response_model=list[SearchResult])
def search_foods(term: str):
    """Manual food search (search.html): wger hits + their kcal/100g."""
    term = term.strip()
    if len(term) < 2:
        return []
    wger = get_wger_client()
    try:
        matches = candidate_pool(wger, term)
        results: list[SearchResult] = []
        for _score, match in rank_matches(term, matches, 8):
            energy = match.get("energy")
            if energy is None:  # older wger: nutrition values need a second call
                try:
                    energy = wger.get_ingredient(match["id"]).get("energy")
                except Exception:
                    continue
            results.append(SearchResult(id=match["id"], name=match["name"], energy_kcal_100g=float(energy or 0)))
        return results
    finally:
        wger.close()


@app.get("/api/recent", response_model=list[SearchResult])
def recent_foods():
    """Distinct foods logged in the last 30 days, newest first."""
    wger = get_wger_client()
    try:
        plan_id = settings.default_nutrition_plan_id or wger.find_default_nutrition_plan_id()
        if plan_id is None:
            return []
        now = local_now()
        start = datetime.combine(now.date() - timedelta(days=30), time.min, tzinfo=now.tzinfo)
        # Until the end of today: logging "desayuno" at night stamps it at 8:00, i.e. later than now.
        entries = wger.get_diary_entries(plan_id, start, datetime.combine(now.date(), time.max, tzinfo=now.tzinfo))
        entries.sort(key=lambda e: e.get("datetime", ""), reverse=True)

        seen: dict[int, dict] = {}
        for entry in entries:
            seen.setdefault(entry["ingredient"], entry)
            if len(seen) >= 8:
                break

        def to_result(entry: dict) -> SearchResult | None:
            try:
                data = wger.get_ingredient(entry["ingredient"])
            except Exception:
                return None
            when = entry_datetime(entry)
            return SearchResult(
                id=entry["ingredient"],
                name=data.get("name", "?"),
                energy_kcal_100g=float(data.get("energy", 0) or 0),
                last_amount_grams=float(entry["amount"]),
                last_logged=when.date().isoformat() if when else None,
            )

        with ThreadPoolExecutor(max_workers=4) as pool:
            return [r for r in pool.map(to_result, seen.values()) if r is not None]
    finally:
        wger.close()


@app.delete("/api/diary/{entry_id}")
def delete_diary_entry(entry_id: str):
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

        when = datetime_for_meal(request.meal, parse_taken_at(request.taken_at, local_now()))
        created = []
        for item in request.items:
            try:
                diary_entry_id = wger.log_diary_entry(plan_id, item.ingredient_id, item.amount_grams, when)
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
