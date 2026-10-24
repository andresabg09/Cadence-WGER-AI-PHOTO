"""Buckets nutrition diary entries into desayuno/almuerzo/merienda/cena by
time of day, since wger's diary entries don't carry a meal-slot field we can
rely on across versions. Windows match what's documented to the user in the
cadence design review; tune via Settings if they don't fit his schedule.

All time-of-day logic runs in `settings.timezone`, never the server's clock:
wger stores/returns entries as aware datetimes (UTC or its own TIME_ZONE),
so the hour must be converted before bucketing.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import settings

MEAL_ORDER = ["desayuno", "almuerzo", "merienda", "cena", "otro"]
MEAL_LABELS = {
    "desayuno": "Desayuno",
    "almuerzo": "Almuerzo",
    "merienda": "Merienda",
    "cena": "Cena",
    "otro": "Otro",
}


def local_tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def local_now() -> datetime:
    return datetime.now(local_tz())


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


def meal_window(meal: str) -> tuple[int, int] | None:
    return {
        "desayuno": (settings.breakfast_start_hour, settings.lunch_start_hour),
        "almuerzo": (settings.lunch_start_hour, settings.snack_start_hour),
        "merienda": (settings.snack_start_hour, settings.dinner_start_hour),
        "cena": (settings.dinner_start_hour, settings.dinner_end_hour),
    }.get(meal)


def datetime_for_meal(meal: str | None, now: datetime) -> datetime:
    """Timestamp to log an entry under `meal`.

    wger has no meal-slot field, so the slot is encoded in the time of day.
    If `now` already falls inside the chosen slot we keep it; otherwise the
    entry is stamped at the middle of that slot, today, so it shows up under
    the meal the user picked instead of whatever the clock says.
    """
    window = meal_window(meal) if meal else None
    if window is None:
        return now
    start, end = window
    if start <= now.hour < end:
        return now
    return now.replace(hour=(start + end) // 2, minute=0, second=0, microsecond=0)


def entry_datetime(entry: dict) -> datetime | None:
    """The entry's timestamp expressed in the user's timezone."""
    raw = entry.get("datetime", "")
    try:
        when = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    tz = local_tz()
    if when.tzinfo is None:
        return when.replace(tzinfo=tz)
    return when.astimezone(tz)


def meal_key_for_entry(entry: dict) -> str:
    when = entry_datetime(entry)
    return "otro" if when is None else meal_key_for_hour(when.hour)


def entry_date(entry: dict) -> date | None:
    when = entry_datetime(entry)
    return None if when is None else when.date()


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
