from app.matching import rank_candidates


def test_rank_candidates_picks_closest_name_first():
    raw_matches = [
        {"id": 1, "name": "Pollo a la plancha", "image": None},
        {"id": 2, "name": "Pollo frito", "image": None},
        {"id": 3, "name": "Arroz blanco", "image": None},
    ]

    candidates = rank_candidates("pollo a la plancha", raw_matches, top_n=2)

    assert len(candidates) == 2
    assert candidates[0].id == 1
    assert candidates[0].score > candidates[1].score


def test_rank_candidates_empty_input_returns_empty():
    assert rank_candidates("algo", [], top_n=3) == []


def test_generic_name_beats_longer_variants():
    raw = [
        {"id": 1, "name": "Cherry vanilla ice cream, cherry vanilla"},
        {"id": 2, "name": "Chocolate & vanilla ice cream"},
        {"id": 3, "name": "Vanilla ice cream"},
        {"id": 4, "name": "Churn style vanilla ice cream"},
    ]
    assert rank_candidates("vanilla ice cream", raw, top_n=3)[0].id == 3


def test_inline_energy_is_carried_to_the_candidate():
    raw = [{"id": 9, "name": "Chicken Breast", "energy": 98}]
    assert rank_candidates("chicken breast", raw)[0].energy_kcal_100g == 98.0
