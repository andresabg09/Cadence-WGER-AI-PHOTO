from time import monotonic
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date as date_type, datetime, time, timedelta

import hashlib
from pathlib import Path

import httpx
import threading

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from . import accounts, auth, nutrition, reminders, scoring, store
from .config import settings
from .diagnostics import run_diagnostics
from .progress import achievements as build_achievements, day_totals, streak_runs
from .matching import rank_candidates, rank_matches
from .auth import current_user, require_admin
from .meals import (
    MEAL_LABELS,
    MEAL_ORDER,
    compute_streak,
    counts_for_streak,
    streak_by_day,
    datetime_for_meal,
    entry_date,
    entry_datetime,
    local_now,
    local_tz,
    meal_key_for_entry,
    parse_taken_at,
)
from .schemas import (
    LevelOut,
    LevelsOut,
    ScoreOut,
    ScorePart,
    WaterAdd,
    ActivitiesOut,
    ActivityOut,
    WorkoutUpdate,
    WaterGoalIn,
    BurnOut,
    WaterImport,
    WaterOut,
    AnalyzeResponse,
    ComponentMatch,
    CalendarDay,
    CalendarResponse,
    BarcodeResult,
    HistoryDay,
    HistoryResponse,
    ProgressDay,
    ProgressResponse,
    WeightPoint,
    ConfirmedEntry,
    ConfirmRequest,
    ConfirmResponse,
    DiaryUpdate,
    FoodIn,
    IngredientDetail,
    MacroTotals,
    MealGroup,
    MealItem,
    MediaUpload,
    NoteUpdate,
    SearchResult,
    StreakRun,
    StreaksResponse,
    TodayResponse,
    WorkoutIn,
    WorkoutOut,
    WgerStatus,
)
from .vision import GeminiVisionClient
from .wger_client import WgerClient, WgerError

logger = logging.getLogger("cadence")
app = FastAPI(title="cadence", version="0.1.0")
app.include_router(accounts.router)
app.include_router(reminders.router)


@app.on_event("startup")
def _start_reminder_scheduler():
    reminders.start_scheduler()
app.add_middleware(GZipMiddleware, minimum_size=800)  # pages and scripts are ~45 KB of text: send them squeezed
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
    return WgerClient(settings.wger_base_url, settings.wger_api_token, settings.wger_language_id, settings.wger_language_code,
                      settings.wger_internal_url)


_plan_lock = threading.Lock()


def plan_ref(plan_id: str | int) -> int | str:
    return int(plan_id) if str(plan_id).isdigit() else plan_id


def plan_for(wger: WgerClient, user: store.User, create: bool = True) -> int | str | None:
    """The user's own wger nutrition plan (one per person, made on first use).

    The administrator adopts the plan that existed before accounts, so their earlier diary stays.
    """
    if user.plan_id:
        return plan_ref(user.plan_id)
    with _plan_lock:
        fresh = store.get_user(user.id)
        if fresh and fresh.plan_id:  # another request just made it
            user.plan_id = fresh.plan_id
            return plan_ref(fresh.plan_id)
        plan = wger.find_legacy_plan_id() if user.is_admin else None
        if plan is None and create:
            plan = wger.create_nutrition_plan(f"cadence:{user.id}")
        if plan is not None:
            store.update_user(user.id, plan_id=str(plan))
            user.plan_id = str(plan)
        return plan


_entries_cache: dict[tuple, tuple[float, list[dict]]] = {}
_entries_gen: dict[int, int] = {}
_entries_lock = threading.Lock()
ENTRIES_TTL = 120


def invalidate_entries(user_id: int) -> None:
    """Call after every change to a person's diary: their cached reads are dropped."""
    with _entries_lock:
        _entries_gen[user_id] = _entries_gen.get(user_id, 0) + 1


def user_entries(wger: WgerClient, user: store.User, plan_id: int | str | None, start: datetime, end: datetime) -> list[dict]:
    """The person's diary in [start, end]: their wger plan plus the entries cadence keeps itself
    (own foods and scanned products, which wger's read-only catalog cannot hold).

    The wger part is remembered for 2 minutes (only cadence writes to a person's plan, and every write
    clears it), so moving between Diario, Progreso and Historial does not re-read wger each time."""
    entries: list[dict] = []
    if plan_id is not None:
        with _entries_lock:
            key = (user.id, _entries_gen.get(user.id, 0), str(plan_id), start.isoformat(), end.isoformat())
            hit = _entries_cache.get(key)
        if hit and monotonic() - hit[0] < ENTRIES_TTL:
            entries = hit[1]
        else:
            entries = wger.get_diary_entries(plan_id, start, end)
            with _entries_lock:
                if len(_entries_cache) > 300:
                    _entries_cache.clear()
                _entries_cache[key] = (monotonic(), entries)
    return entries + store.local_entries(user.id, start, end)


def ingredient_info(wger: WgerClient, user: store.User, ingredient_id: int) -> dict:
    """wger-shaped nutrition of a food: own foods have a negative id and live in cadence."""
    if ingredient_id < 0:
        food = store.get_custom_food(ingredient_id, user.id)
        if food is None:
            raise WgerError("Ese alimento propio no existe")
        return food
    return wger.get_ingredient(ingredient_id)


def owns_entry(wger: WgerClient, user: store.User, entry_id: str) -> bool:
    """Is this diary entry in the user's own plan? (Every write goes through here.)"""
    if store.is_local_entry(entry_id):
        local = store.local_entry(entry_id)
        return bool(local and local["user_id"] == user.id)
    owner = store.entry_owner(entry_id)
    if owner is not None:
        return owner == user.id
    try:
        entry = wger.get_diary_entry(entry_id)
    except WgerError:
        return False
    if user.plan_id and str(entry.get("plan")) == str(user.plan_id):
        store.claim_entry(entry_id, user.id)
        return True
    return False


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


_staples_cache: dict = {"at": float("-inf"), "items": []}  # monotonic() can be tiny right after a host boot


def candidate_pool(wger: WgerClient, term: str, user: store.User | None = None) -> list[dict]:
    """wger's text search plus the ready-to-eat staples (cached 10 min) and the person's own
    foods, without repeats."""
    pool = wger.search_ingredients(term, limit=settings.search_fetch_limit)
    if user is not None:
        pool = store.custom_foods(user.id, term) + pool
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
def diagnostics(deep: bool = False, _: store.User = Depends(require_admin)):
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


_build: dict[str, str] = {}


def _build_id() -> str:
    """Short fingerprint of the static files (names, sizes, times): changes whenever a deploy changes anything."""
    if "id" not in _build:
        digest = hashlib.sha1()
        for path in sorted(Path("static").rglob("*")):
            if path.is_file():
                info = path.stat()
                digest.update(f"{path}:{info.st_size}:{int(info.st_mtime)}".encode())
        _build["id"] = digest.hexdigest()[:10]
    return _build["id"]


@app.get("/sw.js")
def service_worker():
    # Served at the app root (not /static/sw.js) on purpose: a service
    # worker's default scope is its own directory, and we need it to
    # control every page under /cadence/, not just /cadence/static/.
    # The build id (a fingerprint of every static file) makes each deploy a new worker.
    body = Path("static/sw.js").read_text(encoding="utf-8").replace("__BUILD__", _build_id())
    return Response(body, media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/scan.html")
def scan_page():
    return FileResponse("static/scan.html")


@app.get("/confirm.html")
def confirm_page():
    return FileResponse("static/confirm.html")


@app.get("/search.html")
def search_page():
    return FileResponse("static/search.html")


@app.get("/login.html")
def login_page():
    return FileResponse("static/login.html")


@app.get("/onboarding.html")
def onboarding_page():
    return FileResponse("static/onboarding.html")


@app.get("/profile.html")
def profile_page():
    return FileResponse("static/profile.html")


@app.get("/settings.html")
def settings_page():
    return FileResponse("static/settings.html")


@app.get("/progress.html")
def progress_page():
    return FileResponse("static/progress.html")


@app.get("/reminders.html")
def reminders_page():
    return FileResponse("static/reminders.html")


@app.get("/voice.html")
def voice_page():
    return FileResponse("static/voice.html")


@app.get("/history.html")
def history_page():
    return FileResponse("static/history.html")


@app.get("/goals.html")
def goals_page():
    return FileResponse("static/goals.html")


def _water_day(raw: str) -> str:
    try:
        day = date_type.fromisoformat(raw)
    except ValueError:
        raise HTTPException(400, "Fecha invalida (usa AAAA-MM-DD)") from None
    if day > local_now().date() + timedelta(days=1):  # a day of slack for devices in another timezone
        raise HTTPException(422, "No se puede registrar agua en el futuro")
    return day.isoformat()


@app.post("/api/water", response_model=WaterOut)
def add_water(body: WaterAdd, user: store.User = Depends(current_user)):
    """Water is kept per person on the server (it used to live only in one browser): add or remove millilitres of a day."""
    day = _water_day(body.date)
    return WaterOut(date=day, ml=store.add_water(user.id, day, body.add_ml), goal_ml=water_goal_for(user)[0])


def water_goal_for(user: store.User) -> tuple[int, bool]:
    """(daily water goal in ml, is it automatic?): the person's own, else 35 ml per kg of body weight, in glasses of 250 ml."""
    own = store.water_goal(user.id)
    if own:
        return own, False
    kg = store.latest_weight(user.id)
    if not kg:
        return 2000, True
    return int(min(4000, max(1500, round(35 * kg / 250) * 250))), True


@app.put("/api/water/goal", response_model=WaterOut)
def set_water_goal(body: WaterGoalIn, user: store.User = Depends(current_user)):
    """Change the daily water goal (ml), or None to go back to the automatic one."""
    store.set_water_goal(user.id, None if body.ml is None else int(round(body.ml / 250) * 250))
    today_iso = local_now().date().isoformat()
    return WaterOut(date=today_iso, ml=store.water_ml(user.id, today_iso), goal_ml=water_goal_for(user)[0])


@app.post("/api/water/import")
def import_water(body: WaterImport, user: store.User = Depends(current_user)):
    """One-time upload of the water a device had saved locally before it was kept on the server."""
    days = {}
    for raw, ml in list(body.days.items())[:400]:
        try:
            days[date_type.fromisoformat(raw).isoformat()] = int(ml)
        except ValueError:
            continue
    store.import_water(user.id, days)
    return {"imported": len(days)}


JOG_MET = 7.0  # a light jog: the yardstick for "minutes to burn it"


def _burn(eaten: float, goal_kcal: float, workouts: list[dict], weight_kg: float | None) -> BurnOut:
    over = max(0, round(eaten - goal_kcal))
    worked = round(sum(w["kcal"] for w in workouts))
    left = max(0, over - worked)
    kg = weight_kg or 70.0
    return BurnOut(over_kcal=over, worked_kcal=worked, kcal=left, minutes=int(-(-left // (JOG_MET * kg / 60))) if left else 0)


def _scoring_food(item: MealItem) -> scoring.Food:
    return scoring.Food(item.name, item.amount_grams, item.kcal, item.protein_g, item.carbs_g, item.fat_g,
                        item.fibre_g, item.sugar_g, item.sat_fat_g)


def _score_out(score: scoring.Score | None) -> ScoreOut | None:
    if score is None:
        return None
    return ScoreOut(points=score.points, label=score.label, partial=score.partial,
                    parts=[ScorePart(key=p.key, label=p.label, points=p.points, max=p.max, note=p.note) for p in score.parts])


def _day_score(scored: list[tuple[float, int]]) -> ScoreOut | None:
    day = scoring.score_day(scored)
    return ScoreOut(points=day[0], label=day[1]) if day else None


def _levels_out(foods: list[scoring.Food], goal: scoring.Goal, meal: str | None) -> LevelsOut:
    def out(level):
        return None if level is None else LevelOut(value_g=level.value_g, target_g=level.target_g, pct=level.pct, label=level.label)
    return LevelsOut(protein=out(scoring.protein_level(foods, goal, meal)), fibre=out(scoring.fibre_level(foods, goal, meal)))


@app.get("/api/today", response_model=TodayResponse)
def today(date: str | None = None, user: store.User = Depends(current_user)):
    """The diary of one day (default: today in the user's timezone)."""
    real_today = local_now().date()
    try:
        shown_date = date_type.fromisoformat(date) if date else real_today
    except ValueError:
        raise HTTPException(400, "Fecha invalida (usa AAAA-MM-DD)") from None
    shown_date = min(shown_date, real_today)  # nothing can be logged in the future
    wger = get_wger_client()
    try:
        plan_id = plan_for(wger, user, create=False)
        goal = MacroTotals(
            kcal=user.goal_kcal or settings.fallback_goal_kcal,
            protein_g=user.goal_protein or settings.fallback_goal_protein_g,
            carbs_g=user.goal_carbs or settings.fallback_goal_carbs_g,
            fat_g=user.goal_fat or settings.fallback_goal_fat_g,
        )
        now = local_now()
        today_date = real_today
        history_start = datetime.combine(today_date - timedelta(days=30), time.min, tzinfo=now.tzinfo)
        day_end = datetime.combine(today_date, time.max, tzinfo=now.tzinfo)
        entries = user_entries(wger, user, plan_id, history_start, day_end)

        try:
            logged_on = store.get_logged_on([str(e["id"]) for e in entries])
        except Exception:  # noqa: BLE001
            logger.exception("no se pudo leer el almacen local (racha)")
            logged_on = {}
        streak_days = compute_streak(counts_for_streak(entries, logged_on), today_date)
        if shown_date < history_start.date():
            # Older than the streak window: read that day on its own.
            day_start = datetime.combine(shown_date, time.min, tzinfo=now.tzinfo)
            entries = user_entries(wger, user, plan_id, day_start, datetime.combine(shown_date, time.max, tzinfo=now.tzinfo))
        today_entries = [e for e in entries if entry_date(e) == shown_date]

        ingredient_cache: dict[int, dict] = {}

        def macros_for(ingredient_id: int) -> dict:
            if ingredient_id not in ingredient_cache:
                try:
                    ingredient_cache[ingredient_id] = ingredient_info(wger, user, ingredient_id)
                except Exception:  # noqa: BLE001
                    logger.exception("no se pudo leer el alimento %s", ingredient_id)
                    ingredient_cache[ingredient_id] = {"name": "(alimento no disponible)"}
            return ingredient_cache[ingredient_id]

        # Read every distinct food of the day at once (wger answers each in ~hundreds of ms; they used to queue).
        wanted = {e["ingredient"] for e in today_entries}
        if len(wanted) > 1:
            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(macros_for, wanted))
        groups: dict[str, list[MealItem]] = {key: [] for key in MEAL_ORDER}
        totals = MacroTotals()

        try:
            meta = store.get_meta([str(e["id"]) for e in today_entries])
        except Exception:  # noqa: BLE001 - notes/photos are extras; the diary still shows
            logger.exception("no se pudo leer el almacen local de notas y fotos")
            meta = {}

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
            fibre100, sugar100, sat100 = scoring.per_100g(ingredient.get("name", ""), ingredient)
            part = lambda per100: None if per100 is None else round(per100 * ratio, 2)  # noqa: E731
            groups[key].append(
                MealItem(
                    diary_entry_id=str(entry["id"]),  # UUID text on current wger, int on older ones
                    ingredient_id=ingredient_id,
                    name=ingredient.get("name", "?"),
                    amount_grams=amount,
                    kcal=round(kcal, 1),
                    protein_g=round(protein, 1),
                    carbs_g=round(carbs, 1),
                    fat_g=round(fat, 1),
                    taken_at=(entry_datetime(entry).isoformat() if entry_datetime(entry) else None),
                    note=meta.get(str(entry["id"]), {}).get("note"),
                    has_crop=meta.get(str(entry["id"]), {}).get("has_crop", False),
                    plate_key=meta.get(str(entry["id"]), {}).get("plate_key"),
                    box=meta.get(str(entry["id"]), {}).get("box"),
                    fibre_g=part(fibre100),
                    sugar_g=part(sugar100),
                    sat_fat_g=part(sat100),
                )
            )

        meals = []
        goal_for_score = scoring.Goal(goal.kcal, goal.protein_g, goal.carbs_g, goal.fat_g)
        scored: list[tuple[float, int]] = []
        day_foods: list[scoring.Food] = []
        for key in MEAL_ORDER:
            items = groups[key]
            if not items:
                continue
            foods = [_scoring_food(i) for i in items]
            day_foods += foods
            meal_score = scoring.score_meal(foods, goal_for_score, key)
            if meal_score:
                scored.append((sum(f.kcal for f in foods), meal_score.points))
            meals.append(
                MealGroup(
                    score=_score_out(meal_score),
                    levels=_levels_out(foods, goal_for_score, key),
                    key=key,
                    label=MEAL_LABELS[key],
                    totals=MacroTotals(
                        kcal=round(sum(i.kcal for i in items), 1),
                        protein_g=round(sum(i.protein_g for i in items), 1),
                        carbs_g=round(sum(i.carbs_g for i in items), 1),
                        fat_g=round(sum(i.fat_g for i in items), 1),
                    ),
                    items=items,
                )
            )

        return TodayResponse(
            workouts=[WorkoutOut(**w) for w in store.workouts_between(user.id, shown_date.isoformat(), shown_date.isoformat())],
            date=shown_date.isoformat(),
            today=real_today.isoformat(),
            totals=MacroTotals(
                kcal=round(totals.kcal, 1),
                protein_g=round(totals.protein_g, 1),
                carbs_g=round(totals.carbs_g, 1),
                fat_g=round(totals.fat_g, 1),
            ),
            goal=goal,
            meals=meals,
            score=_day_score(scored),
            levels=_levels_out(day_foods, goal_for_score, None) if day_foods else None,
            streak_days=streak_days,
            user_name=user.name,
            water_ml=store.water_ml(user.id, shown_date.isoformat()),
            water_goal_ml=water_goal_for(user)[0],
            water_goal_auto=water_goal_for(user)[1],
            burn=_burn(totals.kcal, goal.kcal, store.workouts_between(user.id, shown_date.isoformat(), shown_date.isoformat()), store.latest_weight(user.id)),
        )
    finally:
        wger.close()


def diary_days(wger: WgerClient, user: store.User, plan_id: int | str | None, now: datetime, start: date_type,
               end: date_type) -> tuple[dict[date_type, int], set[date_type]]:
    """(entries per day, days that count for the streak) between two dates."""
    entries = user_entries(
        wger, user, plan_id,
        datetime.combine(start, time.min, tzinfo=now.tzinfo),
        datetime.combine(end, time.max, tzinfo=now.tzinfo),
    )
    try:
        logged_on = store.get_logged_on([str(e["id"]) for e in entries])
    except Exception:  # noqa: BLE001
        logger.exception("no se pudo leer el almacen local (racha)")
        logged_on = {}
    counts: dict[date_type, int] = {}
    for entry in entries:
        day = entry_date(entry)
        if day is not None:
            counts[day] = counts.get(day, 0) + 1
    counting = {entry_date(e) for e in counts_for_streak(entries, logged_on)}
    return counts, counting


@app.get("/api/calendar", response_model=CalendarResponse)
def calendar(month: str | None = None, user: store.User = Depends(current_user)):
    """Days with something logged in a month, each with the streak it belongs to."""
    now = local_now()
    real_today = now.date()
    try:
        first = date_type.fromisoformat(f"{month}-01") if month else real_today.replace(day=1)
    except ValueError:
        raise HTTPException(400, "Mes invalido (usa AAAA-MM)") from None
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    wger = get_wger_client()
    try:
        plan_id = plan_for(wger, user, create=False)

        window_start = first - timedelta(days=62)
        counts, counting = diary_days(wger, user, plan_id, now, window_start, last)
        # A streak running into the month can be older than the window: read further back until it breaks.
        for _ in range(6):
            if window_start not in counting:
                break
            older_end = window_start - timedelta(days=1)
            older_start = older_end - timedelta(days=62)
            older_counts, older_counting = diary_days(wger, user, plan_id, now, older_start, older_end)
            counts.update(older_counts)
            counting |= older_counting
            window_start = older_start
        streaks = streak_by_day(counting)
        return CalendarResponse(
            month=first.strftime("%Y-%m"),
            today=real_today.isoformat(),
            days=[
                CalendarDay(date=d.isoformat(), count=counts[d], streak=streaks.get(d, 0))
                for d in sorted(counts) if first <= d <= last
            ],
        )
    finally:
        wger.close()


@app.get("/api/streaks", response_model=StreaksResponse)
def streaks(user: store.User = Depends(current_user)):
    """The streak in progress and the ones before it (last 12 months)."""
    now = local_now()
    real_today = now.date()
    wger = get_wger_client()
    try:
        plan_id = plan_for(wger, user, create=False)
        counting: set[date_type] = set()
        # Three reads of ~4 months keep each wger page small.
        for chunk in range(3):
            end = real_today - timedelta(days=122 * chunk)
            start = end - timedelta(days=121)
            counting |= diary_days(wger, user, plan_id, now, start, end)[1]
        current, runs = streak_runs(counting, real_today)
        return StreaksResponse(
            today=real_today.isoformat(),
            current=current,
            current_days=(
                [(date_type.fromisoformat(current.start) + timedelta(days=i)).isoformat() for i in range(current.length)]
                if current else []
            ),
            logged_today=real_today in counting,
            best=max([r.length for r in runs] + ([current.length] if current else []), default=0),
            previous=runs[:12],
        )
    finally:
        wger.close()


def _year_entries(wger: WgerClient, user: store.User, plan_id, now: datetime, days: int = 366) -> list[dict]:
    """The person's diary for the last `days` days, read in parallel ~4-month chunks to keep wger pages small."""
    def chunk(offset: int) -> list[dict]:
        end = now.date() - timedelta(days=offset)
        start = end - timedelta(days=min(121, days - offset - 1))
        return user_entries(wger, user, plan_id, datetime.combine(start, time.min, tzinfo=now.tzinfo),
                            datetime.combine(end, time.max, tzinfo=now.tzinfo))

    with ThreadPoolExecutor(max_workers=4) as pool:
        return [e for part in pool.map(chunk, range(0, days, 122)) for e in part]


def _goal_kcal(user: store.User) -> float:
    return user.goal_kcal or settings.fallback_goal_kcal


@app.get("/api/progress", response_model=ProgressResponse)
def progress(user: store.User = Depends(current_user)):
    """Streak, the last 4 weeks, weight and achievements (everything read from the person's own data)."""
    now = local_now()
    today_ = now.date()
    wger = get_wger_client()
    try:
        plan_id = plan_for(wger, user, create=False)
        entries = _year_entries(wger, user, plan_id, now)
        try:
            logged_on = store.get_logged_on([str(e["id"]) for e in entries])
        except Exception:  # noqa: BLE001
            logger.exception("no se pudo leer el almacen local (racha)")
            logged_on = {}
        counting = {d for d in (entry_date(e) for e in counts_for_streak(entries, logged_on)) if d is not None}
        current, previous = streak_runs(counting, today_)
        best = max([r.length for r in previous] + ([current.length] if current else []), default=0)

        recent_start = today_ - timedelta(days=89)
        recent = [e for e in entries if (entry_date(e) or today_) >= recent_start]
        totals = day_totals(recent, lambda ingredient_id: ingredient_info(wger, user, ingredient_id))
        goal = _goal_kcal(user)
        logged_days = {entry_date(e) for e in entries}
        days = []
        for offset in range(27, -1, -1):
            d = today_ - timedelta(days=offset)
            days.append(ProgressDay(date=d.isoformat(), kcal=round(totals.get(d, {}).get("kcal", 0)), logged=d in logged_days, counts=d in counting))

        weights = store.weights_since(user.id, (today_ - timedelta(days=180)).isoformat())
        change = None
        month = [w for w in weights if w["day"] >= (today_ - timedelta(days=30)).isoformat()]
        if len(month) >= 2:
            change = round(month[-1]["kg"] - month[0]["kg"], 1)
        all_weights = store.weights_since(user.id, "0000-00-00")
        medals = build_achievements(
            total_logged=len(entries), photos=store.photo_count(user.id), best_streak=best, weights=len(all_weights),
            totals=totals, goal_kcal=goal, goal_protein=user.goal_protein or settings.fallback_goal_protein_g)
        return ProgressResponse(
            today=today_.isoformat(), streak_current=current.length if current else 0, streak_best=best,
            logged_today=today_ in counting, goal_kcal=goal, days=days,
            weights=[WeightPoint(**w) for w in weights], weight_change_30d=change,
            target_weight_kg=user.target_weight_kg, achievements=medals, unlocked=sum(m.unlocked for m in medals))
    finally:
        wger.close()


@app.get("/api/history", response_model=HistoryResponse)
def history(before: str | None = None, days: int = 14, user: store.User = Depends(current_user)):
    """Past days with something logged, newest first: calories and the photos of that day."""
    now = local_now()
    today_ = now.date()
    try:
        end_day = date_type.fromisoformat(before) - timedelta(days=1) if before else today_
    except ValueError:
        raise HTTPException(400, "Fecha invalida (usa AAAA-MM-DD)") from None
    end_day = min(end_day, today_)
    span = max(1, min(days, 31))
    start_day = end_day - timedelta(days=span - 1)
    wger = get_wger_client()
    try:
        plan_id = plan_for(wger, user, create=False)
        entries = user_entries(wger, user, plan_id, datetime.combine(start_day, time.min, tzinfo=now.tzinfo),
                               datetime.combine(end_day, time.max, tzinfo=now.tzinfo))
        totals = day_totals(entries, lambda ingredient_id: ingredient_info(wger, user, ingredient_id))
        try:
            meta = store.get_meta([str(e["id"]) for e in entries])
        except Exception:  # noqa: BLE001
            meta = {}
        by_day: dict[date_type, list[dict]] = {}
        for entry in entries:
            d = entry_date(entry)
            if d is not None:
                by_day.setdefault(d, []).append(entry)
        out = []
        for d in sorted(by_day, reverse=True):
            with_crop = [str(e["id"]) for e in by_day[d] if meta.get(str(e["id"]), {}).get("has_crop")]
            out.append(HistoryDay(date=d.isoformat(), kcal=round(totals[d]["kcal"]), count=len(by_day[d]),
                                  thumbs=with_crop[:5], more=max(0, len(by_day[d]) - 5)))
        oldest = today_ - timedelta(days=730)
        return HistoryResponse(goal_kcal=_goal_kcal(user), days=out,
                               next_before=start_day.isoformat() if start_day > oldest else None)
    finally:
        wger.close()


def split_water(detected: list) -> tuple[list, int]:
    """(foods, millilitres of plain water): water is not logged as food, it fills the water bar."""
    foods, water = [], 0
    for item in detected:
        ml = item.water_ml
        if ml is None and (item.name or "").strip().lower() in {"agua", "agua natural", "agua mineral", "water"}:
            ml = 250  # named but not measured: one glass
        if ml:
            water += ml
        else:
            foods.append(item)
    return foods, min(water, 3000)


def match_components(wger: WgerClient, user: store.User, detected: list) -> list[ComponentMatch]:
    """For each food the model named: wger candidates (plus the person's own foods), best first."""
    components = []
    for component in detected:
        # Search/rank with the English generic name (wger's DB language);
        # detected_name stays the Spanish label the user sees.
        term = component.search_name or component.name
        raw_matches = candidate_pool(wger, term, user)
        # The catalog may name the food differently ("chicken soup" vs "chicken noodle soup"):
        # search the model's alternative names (and, if still thin, the Spanish one) too.
        seen_ids = {m["id"] for m in raw_matches}
        for extra in [*component.search_alternatives[:3], component.name]:
            if extra.lower() == term.lower():
                continue
            try:
                more = candidate_pool(wger, extra, user)
            except Exception:  # noqa: BLE001 - alternatives are a bonus
                continue
            raw_matches += [m for m in more if m["id"] not in seen_ids]
            seen_ids.update(m["id"] for m in more)
        candidates = rank_candidates(term, raw_matches, settings.match_candidate_count,
                                    alt=[component.name, *component.search_alternatives])
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
    return components


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(image: UploadFile, user: store.User = Depends(current_user)):
    if not user.is_admin and not store.bump_usage(user.id, local_now().date().isoformat(), settings.analyze_daily_limit):
        raise HTTPException(429, f"Llegaste al límite de {settings.analyze_daily_limit} fotos por día. Mañana puedes seguir; mientras tanto, busca el alimento a mano.")
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, "Imagen vacia")

    vision = get_vision_client()
    detected, water_ml = split_water(vision.identify_components(image_bytes, image.content_type or "image/jpeg"))
    if not detected and not water_ml:
        raise HTTPException(422, "No se identifico ningun alimento en la foto")

    components = []
    if detected:
        wger = get_wger_client()
        try:
            components = match_components(wger, user, detected)
        finally:
            wger.close()

    return AnalyzeResponse(components=components, water_ml=water_ml)


_AUDIO_TYPES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/mpeg", "audio/mp3", "audio/mp4", "audio/aac", "audio/ogg", "audio/webm", "audio/flac"}


@app.post("/api/voice", response_model=AnalyzeResponse)
async def voice(audio: UploadFile, user: store.User = Depends(current_user)):
    """"Registra 200 gramos de pollo a la plancha": the audio is turned into the same list a photo gives."""
    if not user.is_admin and not store.bump_usage(user.id, local_now().date().isoformat(), settings.analyze_daily_limit):
        raise HTTPException(429, f"Llegaste al límite de {settings.analyze_daily_limit} análisis por día. Mañana puedes seguir; mientras tanto, busca el alimento a mano.")
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Audio vacío")
    if len(data) > 4_000_000:
        raise HTTPException(413, "El audio es demasiado largo: di solo lo que vas a registrar (máx. 60 segundos)")
    mime = (audio.content_type or "audio/wav").split(";")[0].lower()
    detected, water_ml = split_water(get_vision_client().identify_from_audio(data, mime if mime in _AUDIO_TYPES else "audio/wav"))
    if not detected and not water_ml:
        raise HTTPException(422, "No identifiqué ningún alimento en lo que dijiste")
    if not detected:
        return AnalyzeResponse(components=[], water_ml=water_ml)
    wger = get_wger_client()
    try:
        return AnalyzeResponse(components=match_components(wger, user, detected), water_ml=water_ml)
    finally:
        wger.close()


@app.get("/api/ingredient/{ingredient_id}", response_model=IngredientDetail)
def ingredient_detail(ingredient_id: int, user: store.User = Depends(current_user)):
    wger = get_wger_client()
    try:
        data = ingredient_info(wger, user, ingredient_id)
        return IngredientDetail(
            id=ingredient_id,
            name=data.get("name", "?"),
            energy_kcal_100g=float(data.get("energy", 0) or 0),
            protein_100g=float(data.get("protein", 0) or 0),
            carbs_100g=float(data.get("carbohydrates", 0) or 0),
            fat_100g=float(data.get("fat", 0) or 0),
        )
    finally:
        wger.close()


@app.get("/api/search", response_model=list[SearchResult])
def search_foods(term: str, user: store.User = Depends(current_user)):
    """Manual food search (search.html): wger hits + their kcal/100g."""
    term = term.strip()
    if len(term) < 2:
        return []
    wger = get_wger_client()
    try:
        matches = candidate_pool(wger, term, user)
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


def _check_food(food: FoodIn) -> None:
    if not food.name.strip() or len(food.name) > 80:
        raise HTTPException(422, "Ponle un nombre al alimento (máx. 80 letras)")
    for label, value, top in (("calorías", food.kcal, 950), ("proteína", food.protein, 100), ("carbohidratos", food.carbs, 100), ("grasa", food.fat, 100)):
        if not 0 <= value <= top:
            raise HTTPException(422, f"Revisa las {label}: por 100 g debe estar entre 0 y {top}")
    if food.fibre is not None and not 0 <= food.fibre <= 100:
        raise HTTPException(422, "La fibra por 100 g debe estar entre 0 y 100")
    if food.protein + food.carbs + food.fat > 105:
        raise HTTPException(422, "Proteína + carbohidratos + grasa no pueden pasar de 100 g por cada 100 g")


@app.post("/api/foods", response_model=SearchResult)
def create_food(food: FoodIn, user: store.User = Depends(current_user)):
    """The person's own food (macros per 100 g). Reusing a barcode updates that food."""
    _check_food(food)
    code = (food.barcode or "").strip() or None
    existing = store.custom_food_by_barcode(user.id, code) if code else None
    if existing:
        return SearchResult(id=existing["id"], name=existing["name"], energy_kcal_100g=existing["energy"])
    fid = store.create_custom_food(user.id, food.name, food.kcal, food.protein, food.carbs, food.fat, code, food.fibre)
    return SearchResult(id=-fid, name=food.name.strip(), energy_kcal_100g=food.kcal)


@app.get("/api/foods", response_model=list[SearchResult])
def my_foods(user: store.User = Depends(current_user)):
    return [SearchResult(id=f["id"], name=f["name"], energy_kcal_100g=f["energy"]) for f in store.custom_foods(user.id)[:30]]


def _off_lookup(code: str) -> tuple[dict | None, str, str | None]:
    """Open Food Facts, only as a fallback when wger could not resolve the code.

    Returns (product with nutrition or None, why not, product name if the entry exists without nutrition):
    why = "found" | "not_listed" (they answered: not in their database) | "no_nutrition" (listed, no values) | "unreachable".
    """
    try:
        response = httpx.get(f"https://world.openfoodfacts.org/api/v2/product/{code}.json",
                             params={"fields": "product_name,nutriments"}, timeout=8,
                             headers={"User-Agent": "cadence/1.0 (personal nutrition diary)"})
        if response.status_code == 404 or (response.status_code == 200 and response.json().get("status") != 1):
            return None, "not_listed", None
        if response.status_code != 200:
            return None, "unreachable", None
        product = response.json()["product"]
        n = product.get("nutriments") or {}
        kcal = n.get("energy-kcal_100g")
        if kcal is None and n.get("energy_100g") is not None:
            kcal = float(n["energy_100g"]) / 4.184
        name = (product.get("product_name") or "").strip() or None
        if not name or kcal is None:
            return None, "no_nutrition", name
        return ({"name": name, "kcal": round(float(kcal), 1), "protein": round(float(n.get("proteins_100g") or 0), 1),
                 "carbs": round(float(n.get("carbohydrates_100g") or 0), 1), "fat": round(float(n.get("fat_100g") or 0), 1),
                 "fibre": round(float(n["fiber_100g"]), 1) if n.get("fiber_100g") is not None else None},
                "found", name)
    except Exception:  # noqa: BLE001 - a bonus lookup
        logger.exception("Open Food Facts no respondio para %s", code)
        return None, "unreachable", None


@app.get("/api/barcode/{code}", response_model=BarcodeResult)
def barcode(code: str, user: store.User = Depends(current_user)):
    """Own food with that code -> wger's catalog (which asks Open Food Facts itself) -> Open Food Facts."""
    code = code.strip()
    if not code.isdigit() or not 6 <= len(code) <= 14:
        raise HTTPException(422, "Ese código de barras no es válido")
    own = store.custom_food_by_barcode(user.id, code)
    if own:
        return BarcodeResult(found=True, source="own", id=own["id"], name=own["name"], kcal=own["energy"], protein=own["protein"],
                             carbs=own["carbohydrates"], fat=own["fat"], fibre=own.get("fibres"), barcode=code)
    wger = get_wger_client()
    wger_failed = False
    try:
        try:
            hit = wger.get_ingredient_by_code(code)
        except Exception:  # noqa: BLE001
            logger.exception("wger no pudo buscar el codigo %s", code)
            hit, wger_failed = None, True
    finally:
        wger.close()
    if hit and hit.get("energy") is not None:
        return BarcodeResult(found=True, source="wger", id=hit["id"], name=hit["name"], kcal=float(hit["energy"]),
                             protein=float(hit.get("protein") or 0), carbs=float(hit.get("carbohydrates") or 0),
                             fat=float(hit.get("fat") or 0), barcode=code)
    off, why, listed_name = _off_lookup(code)
    if off:
        return BarcodeResult(found=True, source="off", barcode=code, **off)
    # Not found anywhere: say WHY, so the person knows what happened and what to do.
    if why == "not_listed" and wger_failed:
        why = "unreachable"  # one of the two databases did not answer: we cannot say it does not exist
    if hit and hit.get("name"):
        why, listed_name = "no_nutrition", hit["name"]
    return BarcodeResult(found=False, barcode=code, reason=why, name=listed_name)


@app.post("/api/workouts", response_model=WorkoutOut)
def add_workout(body: WorkoutIn, user: store.User = Depends(current_user)):
    """A workout in the person's own log (kcal = estimate from the activity, minutes and weight)."""
    if body.kind not in nutrition.WORKOUT_MET:
        raise HTTPException(422, "Elige el tipo de entrenamiento")
    if not 5 <= body.minutes <= 600:
        raise HTTPException(422, "La duración debe estar entre 5 y 600 minutos")
    today_ = local_now().date()
    try:
        day = date_type.fromisoformat(body.day) if body.day else today_
    except ValueError:
        raise HTTPException(400, "Fecha invalida (usa AAAA-MM-DD)") from None
    if day > today_:
        raise HTTPException(422, "No se puede registrar un entrenamiento futuro")
    kcal = nutrition.workout_kcal(body.kind, body.minutes, store.latest_weight(user.id) or 70)
    at = _clock(body.at) or local_now().strftime("%H:%M")
    wid = store.add_workout(user.id, day.isoformat(), body.kind, body.minutes, kcal, body.note, at)
    return WorkoutOut(id=wid, day=day.isoformat(), kind=body.kind, minutes=body.minutes, kcal=kcal, note=(body.note or "").strip() or None, at=at)


def _clock(text: str | None) -> str | None:
    """HH:MM or None; anything else is a 422."""
    if not text:
        return None
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", text):
        raise HTTPException(422, "La hora debe ser HH:MM")
    return text


@app.get("/api/activities", response_model=ActivitiesOut)
def activities(user: store.User = Depends(current_user)):
    """Every activity with its kcal per minute for THIS person's weight (70 kg when they have not logged one)."""
    kg = store.latest_weight(user.id)
    weight = kg or 70.0
    return ActivitiesOut(weight_kg=weight, weight_known=bool(kg), activities=[
        ActivityOut(key=k, label=label, group=g, icon=ic, met=met, kcal_per_min=round(met * weight / 60, 2), words=words)
        for k, label, g, ic, met, words in nutrition.ACTIVITIES])


@app.patch("/api/workouts/{workout_id}", response_model=WorkoutOut)
def update_workout(workout_id: int, body: WorkoutUpdate, user: store.User = Depends(current_user)):
    """Edit a logged workout (activity, minutes, note, time): the burn is estimated again."""
    current = next((w for w in store.workouts_between(user.id, "0000-01-01", "9999-12-31") if w["id"] == workout_id), None)
    if current is None:
        raise HTTPException(404, "Entrenamiento no encontrado")
    kind = body.kind or current["kind"]
    minutes = body.minutes if body.minutes is not None else current["minutes"]
    if kind not in nutrition.WORKOUT_MET:
        raise HTTPException(422, "Elige el tipo de entrenamiento")
    if not 5 <= minutes <= 600:
        raise HTTPException(422, "La duración debe estar entre 5 y 600 minutos")
    note = current["note"] if body.note is None else body.note
    at = _clock(body.at) or current.get("at")
    kcal = nutrition.workout_kcal(kind, minutes, store.latest_weight(user.id) or 70)
    store.update_workout(user.id, workout_id, kind, minutes, kcal, note, at)
    return WorkoutOut(id=workout_id, day=current["day"], kind=kind, minutes=minutes, kcal=kcal, note=(note or "").strip() or None, at=at)


@app.delete("/api/workouts/{workout_id}")
def delete_workout(workout_id: int, user: store.User = Depends(current_user)):
    if not store.delete_workout(user.id, workout_id):
        raise HTTPException(404, "Entrenamiento no encontrado")
    return {"status": "deleted"}


@app.get("/api/recent", response_model=list[SearchResult])
def recent_foods(user: store.User = Depends(current_user)):
    """Distinct foods logged in the last 30 days, newest first."""
    wger = get_wger_client()
    try:
        plan_id = plan_for(wger, user, create=False)
        now = local_now()
        start = datetime.combine(now.date() - timedelta(days=30), time.min, tzinfo=now.tzinfo)
        # Until the end of today: logging "desayuno" at night stamps it at 8:00, i.e. later than now.
        entries = user_entries(wger, user, plan_id, start, datetime.combine(now.date(), time.max, tzinfo=now.tzinfo))
        entries.sort(key=lambda e: e.get("datetime", ""), reverse=True)

        seen: dict[int, dict] = {}
        for entry in entries:
            seen.setdefault(entry["ingredient"], entry)
            if len(seen) >= 8:
                break

        def to_result(entry: dict) -> SearchResult | None:
            try:
                data = ingredient_info(wger, user, entry["ingredient"])
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
def delete_diary_entry(entry_id: str, user: store.User = Depends(current_user)):
    wger = get_wger_client()
    try:
        if not owns_entry(wger, user, entry_id):
            raise HTTPException(404, "Registro no encontrado")
        if store.is_local_entry(entry_id):
            store.delete_local_entry(entry_id)
        else:
            wger.delete_diary_entry(entry_id)
        invalidate_entries(user.id)
        try:
            store.delete_entry(entry_id)
        except Exception:  # noqa: BLE001
            logger.exception("no se pudo limpiar el almacen local de %s", entry_id)
        return {"status": "deleted"}
    except WgerError as exc:
        raise HTTPException(502, str(exc)) from exc
    finally:
        wger.close()


@app.put("/api/diary/{entry_id}/note")
def save_note(entry_id: str, body: NoteUpdate, user: store.User = Depends(current_user)):
    wger = get_wger_client()
    try:
        if not owns_entry(wger, user, entry_id):
            raise HTTPException(404, "Registro no encontrado")
    finally:
        wger.close()
    store.set_note(entry_id, body.note, user.id)
    return {"status": "saved"}


@app.post("/api/entry-media")
def save_entry_media(upload: MediaUpload, user: store.User = Depends(current_user)):
    """Photos of a plate and each ingredient's crop, filed under the diary entries."""
    wger = get_wger_client()
    try:
        mine = {item.entry_id for item in upload.items if owns_entry(wger, user, item.entry_id)}
    finally:
        wger.close()
    if not mine:
        raise HTTPException(404, "Registro no encontrado")
    keys: dict[int, str] = {}
    for index, data_url in enumerate(upload.photos):
        raw = store.decode_image(data_url)
        if raw:
            keys[index] = f"{user.id}-{upload.plate_id}:{index}"
            store.put_plate(keys[index], raw, user.id)
    saved = 0
    for item in upload.items:
        if item.entry_id not in mine:
            continue
        crop = store.decode_image(item.crop)
        # A food added by hand to a photographed plate belongs to that plate (same group in the diary).
        plate_key = keys.get(item.photo) if item.photo is not None else next(iter(keys.values()), None)
        box = item.box if item.photo is not None else None
        if crop or plate_key:
            store.set_media(item.entry_id, crop, plate_key, box, user.id)
            saved += 1
    return {"saved": saved}


@app.get("/api/media/crop/{entry_id}")
def media_crop(entry_id: str, user: store.User = Depends(current_user)):
    data = store.get_crop(entry_id) if store.entry_owner(entry_id) == user.id else None
    if data is None:
        raise HTTPException(404, "Sin recorte")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/media/plate/{key}")
def media_plate(key: str, user: store.User = Depends(current_user)):
    data = store.get_plate(key) if store.plate_owner(key) == user.id else None
    if data is None:
        raise HTTPException(404, "Sin foto")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@app.patch("/api/diary/{entry_id}")
def update_diary_entry(entry_id: str, update: DiaryUpdate, user: store.User = Depends(current_user)):
    wger = get_wger_client()
    try:
        if not owns_entry(wger, user, entry_id):
            raise HTTPException(404, "Registro no encontrado")
        when = None
        if update.meal:
            entry = store.local_entry(entry_id) if store.is_local_entry(entry_id) else wger.get_diary_entry(entry_id)
            current = entry_datetime(entry) or local_now()
            when = datetime_for_meal(update.meal, current)
        if update.amount_grams is not None and update.amount_grams <= 0:
            raise HTTPException(400, "La cantidad debe ser mayor que cero")
        if store.is_local_entry(entry_id):
            store.update_local_entry(entry_id, update.amount_grams, when)
        else:
            wger.update_diary_entry(entry_id, update.amount_grams, when)
        invalidate_entries(user.id)
        return {"status": "updated"}
    except WgerError as exc:
        raise HTTPException(502, str(exc)) from exc
    finally:
        wger.close()


@app.post("/api/confirm", response_model=ConfirmResponse)
def confirm(request: ConfirmRequest, user: store.User = Depends(current_user)):
    wger = get_wger_client()
    try:
        plan_id = plan_for(wger, user)  # always the caller's own plan, never one sent by the client

        when = datetime_for_meal(request.meal, parse_taken_at(request.taken_at, local_now()))
        created = []
        for item in request.items:
            if item.ingredient_id < 0:  # one of the person's own foods: kept by cadence
                if store.get_custom_food(item.ingredient_id, user.id) is None:
                    raise HTTPException(404, "Ese alimento propio no existe")
                diary_entry_id = store.add_local_entry(user.id, item.ingredient_id, item.amount_grams, when)
            else:
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
        invalidate_entries(user.id)
        entry_day = when.astimezone(local_tz()).date()
        real_today = local_now().date()
        try:
            store.set_logged_on([c.diary_entry_id for c in created], real_today.isoformat(), user.id)
        except Exception:  # noqa: BLE001 - the plate is already in wger; only the streak bookkeeping is lost
            logger.exception("no se pudo anotar el dia de registro")
        return ConfirmResponse(created=created, date=entry_day.isoformat(), counts_for_streak=entry_day >= real_today)
    finally:
        wger.close()
