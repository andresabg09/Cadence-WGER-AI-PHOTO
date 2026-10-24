from datetime import date, timedelta

import pytest

from app import gamify, scoring
from app.scoring import Food, Goal

GOAL = Goal(kcal=2000, protein_g=110, carbs_g=250, fat_g=60)


def meal(key="almuerzo", foods=None, at="12:30"):
    foods = foods or [
        Food("Arroz blanco cocido", 180, 234, 4.9, 50.8, 0.5, 0.7, 0.2, 0.1), Food("Pechuga de pollo a la plancha", 150, 247, 46.5, 0, 5.4, 0, 0, 1.5),
        Food("Ensalada verde", 120, 20, 1.4, 4, 0.2, 1.6, 1.6, 0), Food("Frijoles negros cocidos", 100, 132, 8.9, 23.7, 0.5, 8.7, 0.3, 0.1)]
    return gamify.MealFacts(key, foods, scoring.score_meal(foods, GOAL, key), at)


def day(offset, kcal_meal=None, **kw):
    d = date(2026, 10, 19) + timedelta(days=offset)  # a Monday
    facts = gamify.DayFacts(d, **kw)
    if kcal_meal:
        facts.meals["almuerzo"] = kcal_meal
    return facts


def test_meal_awards_follow_the_meal():
    assert set(gamify.meal_awards(meal(), GOAL)) == {"protein_high", "fibre_rich", "varied_plate", "excellent_plate"}
    small = gamify.MealFacts("merienda", [Food("Manzana", 100, 52, 0.3, 13.8, 0.2, 2.4, 10.4, 0)], None)
    assert gamify.meal_awards(small, GOAL) == []  # under 150 kcal is not a meal
    plain = meal(foods=[Food("Arroz blanco cocido", 300, 390, 8, 85, 1, 1.2, 0.3, 0.2)])
    assert "protein_high" not in gamify.meal_awards(plain, GOAL) and "varied_plate" not in gamify.meal_awards(plain, GOAL)


def test_daily_challenges_band_and_no_reward_for_eating_less():
    under = gamify.daily_challenges(day(0, meal()), 2000)
    by = {c.key: c for c in under}
    assert by["d_balance"].complete is False  # 633 kcal of 2000: not in the band
    assert (by["d_first"].complete, by["d_constant"].complete, by["d_mindful"].complete) == (True, False, False)
    huge = gamify.MealFacts("almuerzo", [Food("Pizza", 900, 2400, 90, 300, 90)], None)
    over = {c.key: c for c in gamify.daily_challenges(day(0, huge), 2000)}
    assert over["d_balance"].complete is False and "pasaste" in over["d_balance"].note
    ok = gamify.MealFacts("almuerzo", [Food("Comida", 700, 1900, 90, 240, 60)], None)
    assert {c.key: c for c in gamify.daily_challenges(day(0, ok), 2000)}["d_balance"].complete is True
    two = day(0, meal())
    two.meals["cena"] = meal("cena", at="19:00")
    states = {c.key: c for c in gamify.daily_challenges(two, 2000)}
    assert states["d_constant"].complete and states["d_mindful"].complete and sum(c.reward for c in states.values()) == 120


def test_weekly_challenges_count_days():
    days = [day(i, meal(), water_ml=2500, counts=True, workouts=1 if i < 3 else 0, weights=1 if i == 0 else 0) for i in range(5)]
    states = {c.key: c for c in gamify.weekly_challenges(days, 650, 2500)}
    assert states["w_streak"].complete and states["w_water"].complete and states["w_move"].complete and states["w_weight"].complete
    assert states["w_calories"].complete  # 633 kcal a day against a 650 goal is inside the band
    assert states["w_variety"].now == 4 and not states["w_variety"].complete
    assert [c.reward for c in gamify.weekly_challenges([], 2000, 2000)] == [100, 150, 100, 100, 120, 80]


def test_period_ids_renew_daily_and_weekly():
    wed = date(2026, 10, 21)
    assert gamify.period_id("d_first", wed) == "2026-10-21"
    assert gamify.period_id("w_water", wed) == "2026-10-19"
    assert gamify.week_start(date(2026, 10, 25)) == date(2026, 10, 19)


def test_milestones_and_stats():
    days = [day(i, meal(), water_ml=2500, counts=True) for i in range(6)]
    days[0].meals["desayuno"] = meal("desayuno", at="07:30")
    stats = gamify.milestone_stats(days, total_logged=30, photos=2, best_streak=6, weights=1, workouts=3, goal=GOAL, water_goal=2500)
    assert stats["days_water"] == 6 and stats["early_days"] == 1 and stats["foods_week"] == 4 and stats["workouts"] == 3
    states = {s["key"]: s for s in gamify.milestone_states(stats)}
    assert states["streak_3"]["unlocked"] and not states["streak_7"]["unlocked"] and states["streak_7"]["value"] == 6
    assert states["hydration_5"]["unlocked"] and states["logs_25"]["unlocked"] and not states["logs_100"]["unlocked"] and states["mover"]["unlocked"]
    assert len(states) == len(gamify.MILESTONES) == 18


def test_shop_catalog_has_themes_and_a_frame():
    assert {slot for *_x, slot in gamify.SHOP.values()} == {"theme", "frame"}
