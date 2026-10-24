"""Buckets nutrition diary entries into desayuno/almuerzo/merienda/cena by
time of day, since wger's diary entries don't carry a meal-slot field we can
rely on across versions. Windows match what's documented to the user in the
cadence design review; tune via Settings if they don't fit his schedule.
"""

from datetime import date, datetime, timedelta

from .config import settings

MEAL_ORDER = ["desayuno", "almuerzo", "merienda", "cena", "otro"]
MEAL_LABELS = {
    "desayuno": "Desayuno",
    "almuerzo": "Almuerzo",
    "merienda": "Merienda",
    "cena": "Cena",
    "otro": "Otro",
}


def meal_key_for_hour(hour: int) -> str:
    if settings.breakfast_start_hour <= hour < settings.lunch_start_hour:
        return "desayuno"
    if settings.lunch_start_hour <= hour < settings.snack_start_hour:
        return "almuerzo"
    if settings.snack_start_hour <= hour < settings.dinner_start_hour:
        return "merienda"
    if settings.dinner_start_hour <= hour < settings.dinner_end_hour:
        return "cena"
    return "otro"


def meal_key_for_entry(entry: dict) -> str:
    raw = entry.get("datetime", "")
    try:
        when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return "otro"
    return meal_key_for_hour(when.hour)


def entry_date(entry: dict) -> date | None:
    raw = entry.get("datetime", "")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def compute_streak(entries: list[dict], today: date) -> int:
    """Consecutive days with >=1 diary entry, counted backwards from today.

    If today has nothing logged yet (common mid-day, before the first
    meal), that alone shouldn't zero out an otherwise-intact streak - we
    start counting from yesterday in that case instead.
    """
    days_with_entries = {d for d in (entry_date(e) for e in entries) if d is not None}

    cursor = today if today in days_with_entries else today - timedelta(days=1)
    streak = 0
    while cursor in days_with_entries:
        streak += 1
        cursor -= timedelta(days=1)
    return streak
