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
