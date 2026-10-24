from datetime import date

from app.nutrition import age_on, bmr, compute_targets
from app.security import hash_password, new_invite_code, token_hash, verify_password

TODAY = date(2026, 10, 25)


def test_mifflin_st_jeor_reference_values():
    # 80 kg, 180 cm, 30 y: male 10*80+6.25*180-5*30+5 = 1780, female = 1614
    assert bmr("male", 80, 180, 30) == 1780
    assert bmr("female", 80, 180, 30) == 1614
    assert bmr("other", 80, 180, 30) == 1697


def test_age_counts_birthdays():
    assert age_on(date(1996, 10, 26), TODAY) == 29
    assert age_on(date(1996, 10, 25), TODAY) == 30


def test_goal_changes_calories_and_protein():
    base = dict(sex="male", birthdate=date(1996, 10, 25), height_cm=180, weight_kg=80, activity="moderate", today=TODAY)
    keep = compute_targets(goal="maintain", **base)
    lose = compute_targets(goal="lose", **base)
    muscle = compute_targets(goal="muscle", **base)
    assert keep.kcal == 2760 and keep.maintenance_kcal == 2760
    assert lose.kcal < keep.kcal < muscle.kcal
    assert muscle.protein_g > keep.protein_g
    # macros add up to (about) the calories
    assert abs(keep.protein_g * 4 + keep.carbs_g * 4 + keep.fat_g * 9 - keep.kcal) < 25


def test_safety_rails():
    tiny = compute_targets("female", date(1990, 1, 1), 160, 45, "low", "lose", TODAY)  # underweight: do not cut
    assert tiny.kcal == round(tiny.maintenance_kcal / 10) * 10 and tiny.note
    teen = compute_targets("male", date(2011, 1, 1), 160, 60, "moderate", "lose", TODAY)
    assert teen.kcal == teen.maintenance_kcal and teen.note
    small = compute_targets("female", date(1990, 1, 1), 150, 55, "low", "lose", TODAY)  # deficit would go below the floor
    assert small.kcal >= 1200


def test_passwords_and_tokens():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored) and not verify_password("wrong", stored)
    assert not verify_password("x", "garbage") and stored != hash_password("correct horse")  # salted
    assert len(token_hash("t")) == 64
    code = new_invite_code()
    assert len(code) == 9 and code[4] == "-"
