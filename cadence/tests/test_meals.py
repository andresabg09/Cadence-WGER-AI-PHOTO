from datetime import date

from app.meals import compute_streak, entry_date, meal_key_for_entry


def entry(iso: str) -> dict:
    return {"datetime": iso}


def test_utc_entry_is_bucketed_in_local_time():
    # 12:10 UTC = 07:10 in Panama (UTC-5) -> desayuno, not almuerzo.
    assert meal_key_for_entry(entry("2026-10-24T12:10:00Z")) == "desayuno"
    # 00:30 UTC on the 25th = 19:30 on the 24th in Panama -> cena, same day.
    late = entry("2026-10-25T00:30:00+00:00")
    assert meal_key_for_entry(late) == "cena"
    assert entry_date(late) == date(2026, 10, 24)


def test_offset_from_wger_timezone_is_respected():
    # wger may serialize in its own TIME_ZONE (e.g. Berlin, +02:00).
    assert meal_key_for_entry(entry("2026-10-24T14:10:00+02:00")) == "desayuno"


def test_streak_uses_local_days():
    entries = [
        entry("2026-10-25T00:30:00Z"),  # = Oct 24 evening local
        entry("2026-10-23T15:00:00Z"),
        entry("2026-10-22T15:00:00Z"),
    ]
    assert compute_streak(entries, date(2026, 10, 24)) == 3


def test_unparseable_entry_is_otro():
    assert meal_key_for_entry({"datetime": "nope"}) == "otro"
