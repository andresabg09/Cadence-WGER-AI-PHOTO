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


def test_gemini_boxes_become_fractions_and_bad_ones_are_dropped():
    from app.vision import _box_from_gemini, _parse_components

    # [ymin, xmin, ymax, xmax] on 0-1000  ->  [x, y, w, h] on 0-1
    assert _box_from_gemini([250, 100, 700, 480]) == [0.1, 0.25, 0.38, 0.45]
    assert _box_from_gemini([-20, -5, 1200, 2000]) == [0.0, 0.0, 1.0, 1.0]  # clamped
    assert _box_from_gemini([100, 100, 105, 900]) is None  # a sliver is not a food
    assert _box_from_gemini("nope") is None and _box_from_gemini(None) is None

    parsed = _parse_components('[{"name": "pollo", "search_name": "chicken", "confidence": 0.9, "estimated_grams": 120, "box_2d": [0, 500, 500, 1000]}]')
    assert parsed[0].box == [0.5, 0.0, 0.5, 0.5]


def _dry_and_staple():
    return [
        {"id": 1, "name": "White Rice", "energy": 340, "protein": 7, "carbohydrates": 79, "fat": 0.6, "source": "USDA"},
        {"id": 2, "name": "Cooked white rice", "energy": 130, "protein": 2.7, "carbohydrates": 28.2, "fat": 0.3, "source": "cadence"},
        {"id": 3, "name": "Arroz blanco cocido", "energy": 130, "protein": 2.7, "carbohydrates": 28.2, "fat": 0.3, "source": "cadence"},
    ]


def test_ready_to_eat_staple_beats_the_raw_product_with_the_same_name():
    top = rank_candidates("white rice", _dry_and_staple(), top_n=3)
    assert top[0].id in (2, 3) and top[0].energy_kcal_100g == 130


def test_spanish_name_finds_the_spanish_staple_and_twins_are_shown_once():
    top = rank_candidates("cooked white rice", _dry_and_staple(), top_n=3, alt="arroz blanco")
    ids = [c.id for c in top]
    assert len({2, 3} & set(ids)) == 1, ids  # English and Spanish twin: one of them, not both
    top_es = rank_candidates("cooked white rice", _dry_and_staple(), top_n=3, alt="arroz blanco cocido")
    assert top_es[0].id == 3  # the user's own wording wins


def test_alternative_names_rescue_a_food_the_catalog_names_differently():
    from app.matching import rank_matches
    raw = [{"id": 1, "name": "Sopa de pescado"}, {"id": 2, "name": "Chicken noodle soup"}, {"id": 3, "name": "Sopa de vaca"}]
    ranked = rank_matches("sopa de pollo", raw, 3, alt=["chicken soup", "chicken noodle soup"])
    assert ranked[0][1]["id"] == 2
