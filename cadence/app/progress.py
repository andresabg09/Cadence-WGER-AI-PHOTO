"""Pure logic behind Progreso: streak runs, per-day totals and achievements (no I/O here)."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from .meals import entry_date
from .schemas import Achievement, StreakRun


def streak_runs(counting: set[date], today: date) -> tuple[StreakRun | None, list[StreakRun]]:
    """(the streak still alive, the ones before it newest first). A run is alive when it ends
    today or yesterday: today may simply not be logged yet."""
    runs: list[StreakRun] = []
    run_days: list[date] = []
    for day in sorted(counting) + [None]:
        if run_days and (day is None or day != run_days[-1] + timedelta(days=1)):
            runs.append(StreakRun(start=run_days[0].isoformat(), end=run_days[-1].isoformat(), length=len(run_days)))
            run_days = []
        if day is not None:
            run_days.append(day)
    current = None
    if runs and date.fromisoformat(runs[-1].end) >= today - timedelta(days=1):
        current = runs.pop()
    runs.reverse()
    return current, runs


def day_totals(entries: list[dict], info: Callable[[int], dict]) -> dict[date, dict[str, float]]:
    """Per day: kcal and protein, reading each distinct food once (in parallel)."""
    ids = {e["ingredient"] for e in entries}

    def load(ingredient_id: int):
        try:
            return ingredient_id, info(ingredient_id)
        except Exception:  # noqa: BLE001 - one unreadable food must not sink the page
            return ingredient_id, {}

    with ThreadPoolExecutor(max_workers=8) as pool:
        foods = dict(pool.map(load, ids))
    totals: dict[date, dict[str, float]] = {}
    for entry in entries:
        day = entry_date(entry)
        if day is None:
            continue
        food = foods.get(entry["ingredient"], {})
        ratio = float(entry["amount"]) / 100.0
        bucket = totals.setdefault(day, {"kcal": 0.0, "protein": 0.0, "count": 0})
        bucket["kcal"] += float(food.get("energy", 0) or 0) * ratio
        bucket["protein"] += float(food.get("protein", 0) or 0) * ratio
        bucket["count"] += 1
    return totals


def achievements(*, total_logged: int, photos: int, best_streak: int, weights: int,
                 totals: dict[date, dict[str, float]], goal_kcal: float, goal_protein: float) -> list[Achievement]:
    on_target = any(goal_kcal > 0 and 0.9 * goal_kcal <= t["kcal"] <= 1.05 * goal_kcal for t in totals.values())
    protein = any(goal_protein > 0 and t["protein"] >= goal_protein for t in totals.values())
    spec = [
        ("first_log", "Primer registro", "Registra tu primer alimento", "🍽️", total_logged >= 1),
        ("first_photo", "Primera foto", "Registra un plato con foto", "📸", photos >= 1),
        ("streak_3", "Arrancaste", "3 días seguidos", "🔥", best_streak >= 3),
        ("streak_7", "Una semana", "7 días seguidos", "🔥", best_streak >= 7),
        ("streak_14", "Dos semanas", "14 días seguidos", "⚡", best_streak >= 14),
        ("streak_30", "Un mes entero", "30 días seguidos", "👑", best_streak >= 30),
        ("logs_25", "25 alimentos", "Registra 25 alimentos", "🥗", total_logged >= 25),
        ("logs_100", "100 alimentos", "Registra 100 alimentos", "🏅", total_logged >= 100),
        ("first_weight", "Primer peso", "Anota tu peso", "⚖️", weights >= 1),
        ("weights_5", "Constancia", "Anota tu peso 5 veces", "📈", weights >= 5),
        ("on_target", "Día en la meta", "Termina un día cerca de tu meta de calorías", "🎯", on_target),
        ("protein", "Proteína completa", "Llega a tu meta de proteína en un día", "💪", protein),
    ]
    return [Achievement(key=k, title=t, hint=h, icon=i, unlocked=u) for k, t, h, i, u in spec]
