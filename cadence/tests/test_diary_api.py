import os

os.environ.setdefault("GEMINI_API_KEY", "x")
os.environ.setdefault("WGER_API_TOKEN", "x")

import tempfile
from unittest.mock import patch

import pytest

from fastapi.testclient import TestClient

from app import main
from app import store
from app.config import settings
from app.meals import local_now


@pytest.fixture(autouse=True)
def data_dir(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(settings, "data_dir", tmp)
        yield tmp


class FakeWger:
    def __init__(self, entries):
        self.entries = entries
        self.updated = None
        self.logged = []

    def find_default_nutrition_plan_id(self): return 1
    def get_default_nutrition_plan_id(self): return 1
    def get_nutrition_plan(self, plan_id): return {}
    def get_diary_entries(self, plan, start, end):
        return [e for e in self.entries if start.isoformat() <= e["datetime"] <= end.isoformat() or True]
    def get_ingredient(self, ingredient_id):
        return {"name": "Arroz", "energy": 130, "protein": 2.7, "carbohydrates": 28, "fat": 0.3}
    def get_diary_entry(self, entry_id): return self.entries[0]
    def update_diary_entry(self, entry_id, amount_grams=None, when=None): self.updated = (entry_id, amount_grams, when)
    def log_diary_entry(self, plan, ingredient, grams, when): self.logged.append(when); return "uuid-1"
    def close(self): pass


def client(fake):
    patcher = patch.object(main, "get_wger_client", lambda: fake)
    patcher.start()
    return TestClient(main.app, raise_server_exceptions=False), patcher


def test_today_can_show_an_older_day_with_macros_and_time():
    entry = {"id": "u1", "ingredient": 5, "amount": 200, "datetime": "2026-10-10T08:00:00-05:00"}
    http, patcher = client(FakeWger([entry]))
    try:
        data = http.get("/api/today", params={"date": "2026-10-10"}).json()
        assert data["date"] == "2026-10-10"
        assert data["today"] == local_now().date().isoformat()
        item = data["meals"][0]["items"][0]
        assert item["kcal"] == 260 and item["protein_g"] == 5.4 and item["taken_at"].startswith("2026-10-10T08:00")
        assert data["meals"][0]["key"] == "desayuno"
        # A different day does not show it.
        assert http.get("/api/today", params={"date": "2026-10-11"}).json()["meals"] == []
        assert http.get("/api/today", params={"date": "nope"}).status_code == 400
    finally:
        patcher.stop()


def test_confirm_reports_the_day_it_was_filed_under():
    fake = FakeWger([])
    http, patcher = client(fake)
    try:
        body = {"items": [{"ingredient_id": 5, "amount_grams": 100}], "meal": "almuerzo",
                "taken_at": "2026-10-10T18:00:00Z"}
        data = http.post("/api/confirm", json=body).json()
        assert data["date"] == "2026-10-10"
    finally:
        patcher.stop()


def test_patch_moves_meal_within_the_same_day_and_changes_amount():
    entry = {"id": "u1", "ingredient": 5, "amount": 200, "datetime": "2026-10-10T08:00:00-05:00"}
    fake = FakeWger([entry])
    http, patcher = client(fake)
    try:
        assert http.patch("/api/diary/u1", json={"amount_grams": 150, "meal": "cena"}).status_code == 200
        entry_id, grams, when = fake.updated
        assert grams == 150 and when.date().isoformat() == "2026-10-10" and when.hour == 20
        assert http.patch("/api/diary/u1", json={"amount_grams": 0}).status_code == 400
    finally:
        patcher.stop()


def test_calendar_marks_days_and_restarts_the_streak_after_a_gap():
    from datetime import date, datetime

    class Ranged(FakeWger):
        def get_diary_entries(self, plan, start, end):
            return [e for e in self.entries if start <= datetime.fromisoformat(e["datetime"]) <= end]

    days = ["2026-08-30", "2026-08-31", "2026-09-01", "2026-09-02",  # a run that crosses the month start
            "2026-09-05", "2026-09-06"]                               # after a gap: starts again at 1
    entries = [{"id": f"e{i}", "ingredient": 5, "amount": 100, "datetime": f"{d}T12:00:00-05:00"} for i, d in enumerate(days)]
    entries.append({"id": "x", "ingredient": 5, "amount": 100, "datetime": "2026-09-02T19:00:00-05:00"})  # 2 entries that day
    http, patcher = client(Ranged(entries))
    try:
        data = http.get("/api/calendar", params={"month": "2026-09"}).json()
        by_day = {d["date"]: d for d in data["days"]}
        assert sorted(by_day) == ["2026-09-01", "2026-09-02", "2026-09-05", "2026-09-06"]
        assert by_day["2026-09-01"]["streak"] == 3  # Aug 30, Aug 31 and Sep 1
        assert by_day["2026-09-02"]["streak"] == 4 and by_day["2026-09-02"]["count"] == 2
        assert by_day["2026-09-05"]["streak"] == 1 and by_day["2026-09-06"]["streak"] == 2
        assert http.get("/api/calendar", params={"month": "xx"}).status_code == 400
    finally:
        patcher.stop()


def test_an_old_photo_fills_its_day_but_does_not_bring_back_a_lost_streak():
    from datetime import datetime, timedelta

    today = local_now().date()
    d = lambda n: (today - timedelta(days=n)).isoformat()  # noqa: E731

    class Live(FakeWger):
        def get_diary_entries(self, plan, start, end):
            return [e for e in self.entries if start <= datetime.fromisoformat(e["datetime"]) <= end]

        def log_diary_entry(self, plan, ingredient, grams, when):
            entry_id = f"n{len(self.entries)}"
            self.entries.append({"id": entry_id, "ingredient": ingredient, "amount": grams, "datetime": when.isoformat()})
            return entry_id

    # Logged on the day itself: yesterday and the day before (no records = trusted, like older entries).
    entries = [{"id": f"old{n}", "ingredient": 5, "amount": 100, "datetime": f"{d(n)}T12:00:00-05:00"} for n in (2, 1)]
    http, patcher = client(Live(entries))
    try:
        # Today the user registers the photo of a meal from 4 days ago, after missing days 3 and 4.
        body = {"items": [{"ingredient_id": 5, "amount_grams": 100}], "meal": "almuerzo", "taken_at": f"{d(4)}T18:00:00Z"}
        confirmed = http.post("/api/confirm", json=body).json()
        assert confirmed["date"] == d(4) and confirmed["counts_for_streak"] is False
        assert store.get_logged_on([confirmed["created"][0]["diary_entry_id"]]) == {confirmed["created"][0]["diary_entry_id"]: today.isoformat()}

        month = today.strftime("%Y-%m")
        by_day = {x["date"]: x for x in http.get("/api/calendar", params={"month": month}).json()["days"]}
        if d(4)[:7] == month:
            assert by_day[d(4)]["count"] == 1 and by_day[d(4)]["streak"] == 0  # data, but no flame
        if d(2)[:7] == month and d(1)[:7] == month:
            assert by_day[d(2)]["streak"] == 1 and by_day[d(1)]["streak"] == 2  # the old photo did not extend it

        # Registered today for today: counts, and the header streak = 3 (d2, d1, today).
        http.post("/api/confirm", json={"items": [{"ingredient_id": 5, "amount_grams": 100}], "meal": "almuerzo"})
        assert http.get("/api/today").json()["streak_days"] == 3
    finally:
        patcher.stop()


def test_streaks_lists_the_current_run_and_the_previous_ones():
    from datetime import datetime, timedelta

    class Ranged(FakeWger):
        def get_diary_entries(self, plan, start, end):
            return [e for e in self.entries if start <= datetime.fromisoformat(e["datetime"]) <= end]

    today = local_now().date()
    offsets = [0, 1, 2, 5, 6, 7, 8, 9, 20]  # run of 3 now, a run of 5 before it, a lone day before that
    entries = [{"id": f"e{n}", "ingredient": 5, "amount": 100,
                "datetime": f"{(today - timedelta(days=n)).isoformat()}T12:00:00-05:00"} for n in offsets]
    http, patcher = client(Ranged(entries))
    try:
        data = http.get("/api/streaks").json()
        assert data["current"]["length"] == 3 and data["logged_today"] is True
        assert data["current_days"] == [(today - timedelta(days=n)).isoformat() for n in (2, 1, 0)]
        assert [r["length"] for r in data["previous"]] == [5, 1] and data["best"] == 5
    finally:
        patcher.stop()
