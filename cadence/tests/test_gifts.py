"""Gifts (box of the day, chest of the week), the fasting challenges and the new awards (17 nov 2026)."""

from datetime import date, timedelta

import pytest

from app import gamify, main, store
from app.meals import local_now
from tests.test_foods import two_people, wger  # noqa: F401 - fixture

pytestmark = pytest.mark.anonymous


def done(key, period="day"):
    return gamify.Challenge(key, period, key, "", "star", 1, 1, 10, True)


def todo(key, period="day"):
    return gamify.Challenge(key, period, key, "", "star", 0, 1, 10, False)


def test_gift_rules_and_content_are_fixed_per_person_and_period():
    daily = [done(k) for k in gamify.BASE_DAILY]
    assert gamify.gift_ready("daily", daily, []) and not gamify.gift_ready("daily", daily[:3] + [todo("d_first")], [])
    weekly = [done(f"w{i}", "week") for i in range(4)] + [todo("w9", "week")]
    assert gamify.gift_ready("weekly", [], weekly) and not gamify.gift_ready("weekly", [], weekly[1:])
    a = gamify.gift_content(7, "daily", "2026-11-17", set())
    assert a == gamify.gift_content(7, "daily", "2026-11-17", set()) and 20 <= a["coins"] <= 60
    assert all(gamify.gift_content(u, "weekly", "2026-11-16", set(gamify.SHOP))["item"] is None for u in range(50))  # nothing left to give


def test_opening_a_gift_once_pays_once(wger, monkeypatch):
    admin, ana = two_people()
    daily = [done(k) for k in gamify.BASE_DAILY]
    weekly = [todo(f"w{i}", "week") for i in range(6)]
    today_ = local_now().date()
    monday = gamify.week_start(today_)
    monkeypatch.setattr(main, "_challenge_states", lambda user: (daily, weekly, today_, monday))
    monkeypatch.setattr(gamify, "gift_content", lambda *a: {"coins": 40, "item": "marco_plata"})
    states = {g["kind"]: g for g in admin.get("/api/gifts").json()["gifts"]}
    assert states["daily"]["ready"] and not states["daily"]["opened"] and not states["weekly"]["ready"]
    assert admin.get("/api/challenges/dot").json()["claimable"] >= 1
    opened = admin.post("/api/gifts/open", json={"kind": "daily"}).json()
    assert (opened["coins"], opened["item"], opened["balance"]) == (40, "marco_plata", 40)
    assert admin.post("/api/gifts/open", json={"kind": "daily"}).status_code == 409
    assert admin.post("/api/gifts/open", json={"kind": "weekly"}).status_code == 409
    assert admin.post("/api/gifts/open", json={"kind": "mystery"}).status_code == 404
    me = admin.get("/api/auth/me").json()
    assert "marco_plata" in store.owned_items(me["id"])
    assert ana.get("/api/challenges").json()["coins"] == 0  # her coins are her own


def test_fasting_challenges_only_for_whoever_fasts_and_may(wger):
    admin, _ = two_people()
    me = store.get_user(admin.get("/api/auth/me").json()["id"])
    today_ = local_now().date()
    assert main._fasting_facts(me, today_, gamify.week_start(today_)) is None  # never chose to fast: no fasting challenge
    admin.post("/api/fasting/intro", json={"none_apply": True})
    end = local_now().replace(second=0, microsecond=0)
    admin.post("/api/fasting/past", json={"start": (end - timedelta(hours=14, minutes=1)).isoformat(), "end": end.isoformat()})
    facts = main._fasting_facts(me, today_, gamify.week_start(today_))
    assert facts == {"done_today": True, "week_days": 1}
    keys = [c["key"] for c in admin.get("/api/challenges").json()["daily"]]
    assert "d_fast" in keys
    store.update_user(me.id, health='{"diabetes": true}')
    assert main._fasting_facts(store.get_user(me.id), today_, gamify.week_start(today_)) is None


def test_new_awards_are_listed():
    keys = [m[0] for m in gamify.MILESTONES]
    for key in ("first_fast", "fasts_5", "fasts_20", "first_recipe", "recipes_10", "hydration_14", "first_quick"):
        assert key in keys
    stats = gamify.milestone_stats([], total_logged=0, photos=0, best_streak=0, weights=0, workouts=0,
                                   goal=main._goal_obj.__globals__["scoring"].Goal(2000, 100, 200, 60), water_goal=2000, fasts=5, quick=1)
    states = {m["key"]: m["unlocked"] for m in gamify.milestone_states(stats)}
    assert states["fasts_5"] and states["first_quick"] and not states["fasts_20"]
