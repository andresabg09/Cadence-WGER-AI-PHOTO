from app import scoring
from app.scoring import Food, Goal

GOAL = Goal(kcal=2000, protein_g=110, carbs_g=250, fat_g=60)


def lunch(**over):
    foods = [
        Food("Arroz blanco cocido", 180, 234, 4.9, 50.8, 0.5, fibre=0.7, sugar=0.2, sat_fat=0.1),
        Food("Pechuga de pollo a la plancha", 150, 247, 46.5, 0, 5.4, fibre=0, sugar=0, sat_fat=1.5),
        Food("Ensalada verde", 120, 20, 1.4, 4, 0.2, fibre=1.6, sugar=1.6, sat_fat=0),
        Food("Frijoles negros cocidos", 100, 132, 8.9, 23.7, 0.5, fibre=8.7, sugar=0.3, sat_fat=0.1),
    ]
    return foods


def test_a_balanced_lunch_scores_high_and_explains_itself():
    score = scoring.score_meal(lunch(), GOAL, "almuerzo")
    assert score.points >= 80 and score.label == "Excelente"
    assert [p.key for p in score.parts] == ["macros", "protein", "fibre", "quality", "variety", "portion"]
    assert sum(p.max for p in score.parts) == 100 and score.partial == []
    assert all(0 <= p.points <= p.max for p in score.parts)


def test_junk_scores_low():
    junk = [Food("Helado de vainilla", 200, 414, 7, 47, 22, fibre=1.4, sugar=42, sat_fat=13.6),
            Food("Gaseosa de cola", 350, 147, 0, 37, 0, fibre=0, sugar=37, sat_fat=0)]
    score = scoring.score_meal(junk, GOAL, "almuerzo")
    assert score.points < 45 and score.label == "Mejorable"


def test_missing_data_does_not_subtract_it_is_reported():
    foods = lunch()
    for f in foods:
        f.fibre = f.sugar = f.sat_fat = None
    score = scoring.score_meal(foods, GOAL, "almuerzo")
    keys = [p.key for p in score.parts]
    assert "fibre" not in keys and "quality" not in keys
    assert score.partial == ["fibra", "azúcar y grasa saturada"]
    assert score.points >= 75  # still judged on what we do know, not dragged down by the gaps
    one_gap = lunch()
    one_gap[1].fibre = None
    partial = scoring.score_meal(one_gap, GOAL, "almuerzo").partial
    assert partial == ["fibra de Pechuga de pollo a la plancha"]


def test_tiny_or_empty_meals_have_no_score():
    assert scoring.score_meal([], GOAL, "almuerzo") is None
    assert scoring.score_meal([Food("Café negro", 200, 2, 0.2, 0, 0)], GOAL, "desayuno") is None


def test_portion_and_protein_react():
    big = [Food("Pizza de queso", 700, 1862, 77, 233, 73, fibre=16, sugar=25, sat_fat=31)]
    huge = scoring.score_meal(big, GOAL, "cena")
    portion = next(p for p in huge.parts if p.key == "portion")
    assert portion.points == 0
    low_protein = [Food("Arroz blanco cocido", 250, 325, 6.8, 70, 0.8, fibre=1, sugar=0.3, sat_fat=0.2)]
    part = next(p for p in scoring.score_meal(low_protein, GOAL, "almuerzo").parts if p.key == "protein")
    assert part.points < 4


def test_levels_and_fibre_target():
    assert scoring.fibre_target(GOAL) == 28.0
    assert scoring.fibre_target(Goal(1500, 90, 180, 50)) == 25.0  # never below 25 g
    prot = scoring.protein_level(lunch(), GOAL, "almuerzo")
    assert (prot.label, prot.pct) == ("alto", 100) and prot.target_g == 38.5
    fibre = scoring.fibre_level(lunch(), GOAL, "almuerzo")
    assert fibre.label == "alto"
    nofibre = lunch()
    for f in nofibre:
        f.fibre = None
    assert scoring.fibre_level(nofibre, GOAL, "almuerzo") is None
    assert scoring.level(10, 40).label == "bajo" and scoring.level(25, 40).label == "medio"


def test_day_score_weighs_by_calories_and_labels():
    assert scoring.score_day([(500, 90), (500, 50)]) == (70, "Buena")
    assert scoring.score_day([(900, 40), (100, 100)]) == (46, "Regular")
    assert scoring.score_day([]) is None
    assert scoring.label_for(80) == "Excelente" and scoring.label_for(64) == "Regular"


def test_staple_table_fills_what_wger_lacks_and_wger_wins_when_it_has_data():
    fibre, sugar, sat = scoring.per_100g("Arroz blanco cocido", {})
    assert (fibre, sugar, sat) == (0.4, 0.1, 0.1)
    assert scoring.per_100g("Cooked white rice", {"fibres": "9.5"})[0] == 9.5
    assert scoring.per_100g("Pan de la abuela", {}) == (None, None, None)
    assert scoring.number("") is None and scoring.number("3.5") == 3.5 and scoring.number("x") is None
