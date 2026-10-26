"""Daily calorie and macro targets from a few personal data.

A STARTING ESTIMATE, not a prescription (no formula is certified for one person). It is built from published pieces and
then corrected with the person's own weight and food records (calibration.py):

* resting energy: Mifflin-St Jeor (Mifflin 1990; the best of the common equations in Frankenfield 2005), or Katch-McArdle
  when the body fat is known;
* daily life: a PAL (total energy / resting energy) inside the FAO/WHO/UNU 2004 bands, WITHOUT planned exercise;
* planned exercise: added on top as NET kcal ((MET - 1) x resting kcal/min), never counted twice;
* goal: a share of the expenditure (muscle gain, by training experience: Iraki 2019) or a pace in pounds per month with
  limits (loss); safety rules for minors, low weight, pregnancy, lactation, diabetes, kidney disease, eating-disorder risk.

The numbers are shown as a range because the equations miss by about +-10 %.
"""

from dataclasses import dataclass
from datetime import date

# Legacy three-level answer (accounts made before the interview). Kept so nobody's saved plan breaks.
ACTIVITY = {
    "low": 1.2,       # little or no exercise
    "moderate": 1.55,  # exercise 3-5 days a week
    "high": 1.725,    # exercise almost every day
}
GOALS = ("lose", "maintain", "gain", "muscle")
SEXES = ("female", "male", "other")

# Daily life WITHOUT planned exercise, as PAL. Anchored on the FAO/WHO/UNU 2004 bands (sedentary or light 1.40-1.69,
# active 1.70-1.99) and the IOM "sedentary" band (1.0-1.39) for the very low one; the point inside each band is
# a design choice (low-middle) because people overestimate how much they move. Steps follow Tudor-Locke's classes.
LIFESTYLE = {"very_low": 1.30, "low": 1.40, "light": 1.50, "moderate": 1.60, "heavy": 1.75}
LIFESTYLE_STEPS = ((4000, "very_low"), (7000, "low"), (10000, "light"), (12500, "moderate"))  # below -> level; above all -> heavy
PAL_CAP = 2.4  # FAO/WHO/UNU: above this a lifestyle is not sustainable
LIFTING = ("beginner", "intermediate", "advanced")
KCAL_PER_KG_BODY = 22  # Hall 2011: each kg of weight lost lowers the daily expenditure by about 10 kcal per pound
FAT_KCAL_PER_KG = 7700
_KCAL_FLOOR = {"female": 1200, "male": 1500, "other": 1350}

# Muscle gain by training experience: (surplus over the expenditure, monthly weight gain low and high as a share of the body
# weight). Iraki 2019: surplus of 10-20 % and 0.25-0.5 % of the body weight per week for novices and intermediates, more
# careful for advanced lifters; the middle steps are a design choice inside that range.
MUSCLE_RULES = {"beginner": (0.12, 0.010, 0.020), "intermediate": (0.08, 0.005, 0.010), "advanced": (0.04, 0.0025, 0.005)}
MAX_SURPLUS = 0.20
MAX_GAIN_PER_WEEK = 0.005
GAIN_SURPLUS = 0.10  # gaining weight without strength training: mostly fat, so a small surplus

# Protein (g per kg of reference weight) by goal: ISSN 2017 (1.4-2.0), Morton 2018 / Iraki 2019 (1.6-2.2), Helms 2014 (deficit).
_PROTEIN_PER_KG = {"lose": 2.0, "maintain": 1.4, "gain": 1.6, "muscle": 2.0}
_PROTEIN_ACTIVE_MAINTAIN = 1.6
_PROTEIN_KIDNEY = 0.8
_PROTEIN_SENIOR_MIN = 1.2  # PROT-AGE
_FAT_SHARE = 0.27
_FAT_MIN_PER_KG = 0.6

PREGNANCY_EXTRA = {0: 0, 1: 0, 2: 340, 3: 452}  # IOM: extra kcal per day by trimester
LACTATION_EXTRA = {0: 0, 1: 330, 2: 400}  # IOM: first six months / months 7-12 (already net of the weight the mother loses)

KCAL_PER_LB = 3500  # one pound of body fat holds about 3,500 kcal (7,700 per kg): only a first-month shortcut
LB_PER_KG = 2.2046226
_DAYS_PER_MONTH = 30
RANGE_UNCALIBRATED = 0.10  # the equations miss by about +-10 %
RANGE_CALIBRATED = 0.06


@dataclass
class Targets:
    kcal: int
    protein_g: int
    carbs_g: int
    fat_g: int
    maintenance_kcal: int
    note: str | None = None
    # What these calories mean for the scale, in pounds per month (positive = the weight goes the way of the goal).
    pace_lb_month: float | None = None
    max_pace_lb_month: float | None = None  # the fastest pace that is safe for this person
    projection_kg: list[float] | None = None  # expected weight after 1, 2 and 3 months (an estimate)
    recommended_pace_lb_month: float | None = None
    projection_low_kg: list[float] | None = None  # lowest and highest weight the estimate allows (the expenditure is uncertain)
    projection_high_kg: list[float] | None = None
    maintenance_low: int | None = None
    maintenance_high: int | None = None
    change_lb_month: float | None = None  # signed: what the scale does in the first month eating this
    blocked: str | None = None  # why a deficit was not given (minor, low weight, health...)
    breakdown: dict | None = None  # how the number was built, for "why this number"


def weight_change_lb_month(maintenance_kcal: float, kcal: float) -> float:
    """Pounds per month the scale would move eating `kcal` a day (negative = losing). First-month shortcut, an estimate."""
    return (kcal - maintenance_kcal) * _DAYS_PER_MONTH / KCAL_PER_LB


def kcal_gap_for_pace(lb_month: float) -> float:
    return lb_month * KCAL_PER_LB / _DAYS_PER_MONTH


def age_on(birthdate: date, today: date) -> int:
    return today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))


def bmr(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    """Mifflin-St Jeor."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    offset = {"male": 5, "female": -161}.get(sex, -78)  # "other": midpoint of both
    return base + offset


def resting_kcal(sex: str, age: int, height_cm: float, weight_kg: float, body_fat_pct: float | None = None) -> tuple[float, str]:
    """Resting energy and the method used: Katch-McArdle when the body fat is known, Mifflin-St Jeor otherwise."""
    if body_fat_pct and 5 <= body_fat_pct <= 60:
        return 370 + 21.6 * weight_kg * (1 - body_fat_pct / 100), "katch"
    return bmr(sex, weight_kg, height_cm, age), "mifflin"


def lifestyle_from_steps(steps: float) -> str:
    for limit, level in LIFESTYLE_STEPS:
        if steps < limit:
            return level
    return "heavy"


def lifestyle_label_legacy(pal: float) -> str:
    """The old three-level word for a total PAL (the column other parts of the app still read)."""
    return "low" if pal < 1.5 else "moderate" if pal < 1.75 else "high"


def clean_training(raw) -> list[dict]:
    """Planned exercise as the interview or the form gives it: [{kind, minutes, days}], sanitized."""
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            minutes = int(round(float(item.get("minutes"))))
            days = float(item.get("days", item.get("days_per_week")))
        except (TypeError, ValueError):
            continue
        kind = item.get("kind") if item.get("kind") in WORKOUT_MET else "otro"
        if 5 <= minutes <= 240 and 0.5 <= days <= 7:
            out.append({"kind": kind, "minutes": minutes, "days": round(days * 2) / 2})
    return out[:6]


def exercise_kcal_per_day(training: list[dict], resting: float) -> float:
    """Average NET kcal per day of the planned exercise: (MET - 1) x resting kcal per minute. The "- 1" removes what the body
    spends sitting still, which the daily-life factor already counts."""
    per_minute = resting / 1440
    total = sum((WORKOUT_MET.get(t["kind"], WORKOUT_MET["otro"]) - 1) * per_minute * t["minutes"] * t["days"] / 7 for t in training)
    return total


def total_expenditure(resting: float, pal: float, exercise: float, tee_factor: float = 1.0) -> float:
    return min(resting * pal + exercise, PAL_CAP * resting) * (tee_factor or 1.0)


def max_pace_lb_month(sex: str, goal: str, weight_kg: float, height_cm: float, age: int, maintenance: float,
                      lift_exp: str | None = None) -> float:
    """The fastest safe pace, in lb/month, in the direction of the goal.

    Losing: 0.5 % (BMI under 25), 0.75 % (25-30) or 1 % (30 and over) of the body weight per week, and no more than 20 / 25 /
    30 % of the daily expenditure, never under the daily minimum; 10 % at 65 or older; nothing for minors or low weight.
    Gaining: no more than 0.5 % of the body weight per week and 20 % over the expenditure."""
    weeks = _DAYS_PER_MONTH / 7
    bmi = weight_kg / ((height_cm / 100) ** 2)
    if goal == "lose":
        if age < 18 or bmi < 18.5:
            return 0.0
        rate, share = (0.005, 0.20) if bmi < 25 else (0.0075, 0.25) if bmi < 30 else (0.01, 0.30)
        if age >= 65:
            share = 0.10
        by_weight = rate * weight_kg * weeks * LB_PER_KG
        by_share = share * maintenance * _DAYS_PER_MONTH / KCAL_PER_LB
        by_floor = max(0.0, (maintenance - _KCAL_FLOOR.get(sex, 1350)) * _DAYS_PER_MONTH / KCAL_PER_LB)
        return round(min(by_weight, by_share, by_floor), 1)
    cap = MAX_GAIN_PER_WEEK * weight_kg * weeks * LB_PER_KG
    if goal == "muscle":
        base_pct, low, high = MUSCLE_RULES.get(lift_exp or "beginner", MUSCLE_RULES["beginner"])
        mid_lb = (low + high) / 2 * weight_kg * LB_PER_KG
        return round(min(cap, MAX_SURPLUS / base_pct * mid_lb), 1)
    if goal == "gain":
        return round(min(cap, MAX_SURPLUS * maintenance * _DAYS_PER_MONTH / KCAL_PER_LB), 1)
    return 0.0


def project_weight(weight_kg: float, maintenance: float, intake: float, months=(1, 2, 3)) -> list[float]:
    """Weight after each month eating `intake` a day, with Hall's rule: the expenditure follows the weight (22 kcal per kg), so
    the same intake moves the scale a little less each month. An estimate, not a promise."""
    w = weight_kg
    marks = {int(m * _DAYS_PER_MONTH): m for m in months}
    out = []
    for day in range(1, max(marks) + 1):
        expend = maintenance + KCAL_PER_KG_BODY * (w - weight_kg)
        w += (intake - expend) / FAT_KCAL_PER_KG
        if day in marks:
            out.append(round(w, 1))
    return out


def maintenance_estimate(sex: str, birthdate: date, height_cm: float, weight_kg: float, today: date, *,
                         lifestyle: str | None = None, training=None, body_fat_pct: float | None = None,
                         tee_factor: float = 1.0, activity: str | None = None) -> float:
    """What the body spends in a day: the interview's answers, or the old three-level answer for accounts that have not redone it."""
    age = age_on(birthdate, today)
    resting, _ = resting_kcal(sex, age, height_cm, weight_kg, body_fat_pct)
    if lifestyle in LIFESTYLE:
        return total_expenditure(resting, LIFESTYLE[lifestyle], exercise_kcal_per_day(clean_training(training), resting), tee_factor)
    return resting * ACTIVITY.get(activity or "moderate", ACTIVITY["moderate"]) * (tee_factor or 1.0)


def maintenance_kcal(sex: str, birthdate: date, height_cm: float, weight_kg: float, activity: str, today: date) -> float:
    return maintenance_estimate(sex, birthdate, height_cm, weight_kg, today, activity=activity)


_BLOCK_NOTES = {
    "minor": "Eres menor de edad: mantenemos tus calorías en lugar de un déficit.",
    "underweight": "Tu peso ya es bajo para tu estatura: te sugerimos mantener en lugar de bajar.",
    "ed": "Por tu bienestar, cadence no calcula un déficit ahora. Si quieres, habla con un médico o nutricionista; mientras tanto te damos tu mantenimiento.",
    "diabetes": "Con diabetes, bajar de peso se hace con tu médico o nutricionista. Te mostramos tu mantenimiento como referencia.",
    "kidney": "Con una enfermedad del riñón, las calorías y la proteína las define tu médico. Esto es solo una referencia.",
    "pregnancy": "Durante el embarazo o la lactancia no se baja de peso. Te mostramos lo que necesitas comer de más, según las guías (IOM).",
}


def blocked_reason(goal: str, age: int, bmi: float, health: dict) -> str | None:
    """Why a deficit must not be given (None = it can). The rules sit here, in code, and nothing else can override them."""
    if goal != "lose":
        return None
    if age < 18:
        return "minor"
    if health.get("ed_risk"):
        return "ed"
    if health.get("pregnancy") or health.get("lactation"):
        return "pregnancy"
    if health.get("diabetes"):
        return "diabetes"
    if health.get("kidney"):
        return "kidney"
    if bmi < 18.5:
        return "underweight"
    return None


def _protein_reference(weight_kg: float, height_cm: float) -> float:
    """Weight protein is counted on: the real weight, or the weight at BMI 25 for people with obesity."""
    bmi = weight_kg / ((height_cm / 100) ** 2)
    return weight_kg if bmi < 30 else 25 * (height_cm / 100) ** 2


def _macros(goal: str, kcal: float, weight_kg: float, height_cm: float, age: int, health: dict, trains: bool) -> tuple[int, int, int, float]:
    ref = _protein_reference(weight_kg, height_cm)
    per_kg = _PROTEIN_PER_KG[goal]
    if goal == "maintain" and trains:
        per_kg = _PROTEIN_ACTIVE_MAINTAIN
    if age >= 65:
        per_kg = max(per_kg, _PROTEIN_SENIOR_MIN)
    if health.get("kidney"):
        per_kg = _PROTEIN_KIDNEY
    protein = round(ref * per_kg)
    fat_g = kcal * _FAT_SHARE / 9
    fat = round(min(max(fat_g, _FAT_MIN_PER_KG * ref), 0.35 * kcal / 9))
    carbs = max(0, round((kcal - protein * 4 - fat * 9) / 4))
    return int(protein), int(carbs), int(fat), per_kg


def compute_targets(sex: str, birthdate: date, height_cm: float, weight_kg: float, activity: str | None, goal: str,
                    today: date, pace_lb_month: float | None = None, *, lifestyle: str | None = None, training=None,
                    lift_exp: str | None = None, body_fat_pct: float | None = None, health: dict | None = None,
                    tee_factor: float = 1.0, kcal_override: float | None = None) -> Targets:
    """Daily calories and macros.

    With `pace_lb_month` the calories come from the pace the person asked for (pounds per month in the direction of the
    goal), limited to what is safe; without it, the recommended pace. `lifestyle`/`training` come from the interview; with
    only the old `activity` the maintenance is the old estimate. `kcal_override` is the person nudging the calories by hand:
    everything else (pace, projection, macros) follows from it, but a deficit is never given where the rules forbid one."""
    health = health or {}
    age = age_on(birthdate, today)
    bmi = weight_kg / ((height_cm / 100) ** 2)
    resting, method = resting_kcal(sex, age, height_cm, weight_kg, body_fat_pct)
    modern = lifestyle in LIFESTYLE
    training = clean_training(training) if modern else []
    exercise = exercise_kcal_per_day(training, resting) if modern else 0.0
    pal = LIFESTYLE[lifestyle] if modern else ACTIVITY.get(activity or "moderate", ACTIVITY["moderate"])
    maintenance = total_expenditure(resting, pal, exercise, tee_factor) if modern else resting * pal * (tee_factor or 1.0)
    floor = _KCAL_FLOOR.get(sex, 1350)
    note = None
    blocked = blocked_reason(goal, age, bmi, health)
    pregnancy, lactation = int(health.get("pregnancy") or 0), int(health.get("lactation") or 0)
    extra = PREGNANCY_EXTRA.get(pregnancy, 0) + LACTATION_EXTRA.get(lactation, 0)
    effective = goal
    max_pace = max_pace_lb_month(sex, goal, weight_kg, height_cm, age, maintenance, lift_exp)
    recommended = None
    used = 0.0
    low_rate = high_rate = None  # monthly weight gain (kg) range, for gain goals

    if pregnancy or lactation:
        effective, kcal, max_pace = "maintain", maintenance + extra, 0.0
        note = _BLOCK_NOTES["pregnancy"] if goal == "lose" else (
            "Durante el embarazo o la lactancia tus calorías suman un extra según las guías (IOM). Habla con tu médico.")
    elif goal == "lose":
        if blocked:
            effective, kcal, max_pace, note = "maintain", maintenance, 0.0, _BLOCK_NOTES[blocked]
        else:
            recommended = round(0.75 * max_pace * 2) / 2 if max_pace >= 1 else round(0.75 * max_pace, 1)
            wanted = recommended if pace_lb_month is None else max(0.0, pace_lb_month)
            used = min(wanted, max_pace)
            if used < wanted - 0.05 and max_pace > 0:
                note = f"Ajustamos tu ritmo a {max_pace:g} libras al mes, lo más seguro para ti."
            kcal = maintenance - kcal_gap_for_pace(used)
            if kcal < floor:
                kcal, note = floor, "Ajustamos al mínimo diario recomendable; bajar más rápido no es seguro sin supervisión."
                used = max(0.0, (maintenance - kcal) * _DAYS_PER_MONTH / KCAL_PER_LB)
    elif goal == "muscle":
        base_pct, low, high = MUSCLE_RULES.get(lift_exp or "beginner", MUSCLE_RULES["beginner"])
        mid_lb = (low + high) / 2 * weight_kg * LB_PER_KG
        recommended = round(mid_lb, 1)
        f = 1.0 if pace_lb_month is None else max(0.0, pace_lb_month) / mid_lb
        f_max = max_pace / mid_lb if mid_lb else 0.0
        if f > f_max + 0.02:
            note = f"Ajustamos tu ritmo a {max_pace:g} libras al mes: subir más rápido casi todo sería grasa."
        f = min(f, f_max)
        kcal = maintenance * (1 + base_pct * f)
        used = f * mid_lb
        low_rate, high_rate = f * low * weight_kg, f * high * weight_kg
    elif goal == "gain":
        recommended = round(GAIN_SURPLUS * maintenance * _DAYS_PER_MONTH / KCAL_PER_LB, 1)
        wanted = recommended if pace_lb_month is None else max(0.0, pace_lb_month)
        used = min(wanted, max_pace)
        if used < wanted - 0.05:
            note = f"Ajustamos tu ritmo a {max_pace:g} libras al mes: subir más rápido casi todo sería grasa."
        kcal = maintenance + kcal_gap_for_pace(used)
        low_rate, high_rate = 0.75 * used / LB_PER_KG, 1.25 * used / LB_PER_KG
    else:
        kcal = maintenance
    rule = MUSCLE_RULES.get(lift_exp or "beginner", MUSCLE_RULES["beginner"])
    if kcal_override is not None and not (pregnancy or lactation):
        kcal = float(kcal_override)
        if effective == "maintain" and blocked:
            kcal = max(kcal, maintenance)
        if effective == "lose":
            used = max(0.0, (maintenance - kcal) * _DAYS_PER_MONTH / KCAL_PER_LB)
        elif effective == "muscle":
            mid_lb = (rule[1] + rule[2]) / 2 * weight_kg * LB_PER_KG
            f = max(0.0, (kcal / maintenance - 1) / rule[0]) if maintenance else 0.0
            used, low_rate, high_rate = f * mid_lb, f * rule[1] * weight_kg, f * rule[2] * weight_kg
        elif effective == "gain":
            used = max(0.0, (kcal - maintenance) * _DAYS_PER_MONTH / KCAL_PER_LB)
            low_rate, high_rate = 0.75 * used / LB_PER_KG, 1.25 * used / LB_PER_KG
        if not blocked:
            note = None  # the notes were about the pace the calculation chose, not the calories typed by hand
    if age >= 65 and goal == "lose" and not blocked and used:
        note = note or "A tu edad el déficit se limita al 10 % para cuidar tu músculo."
    kcal = round(kcal / 10) * 10

    trains = bool(training) and sum(t["days"] for t in training) >= 3
    protein, carbs, fat, per_kg = _macros(effective, kcal, weight_kg, height_cm, age, health, trains)

    # What the final calories mean for the scale (after every safety limit), and where the weight would be.
    spread = RANGE_UNCALIBRATED if (tee_factor or 1.0) == 1.0 else RANGE_CALIBRATED
    if effective in ("lose", "maintain"):
        proj = project_weight(weight_kg, maintenance, kcal)
        gap = max(0.0, (maintenance - kcal) * _DAYS_PER_MONTH / KCAL_PER_LB) if effective == "lose" else 0.0
        change, pace_out = weight_change_lb_month(maintenance, kcal), round(gap, 1)  # signed: eating above the expenditure gains
        if effective == "lose":  # bounds of the weight if the body spends 10 % more (lower weight) or 10 % less than estimated
            proj_low = project_weight(weight_kg, maintenance * (1 + spread), kcal)
            proj_high = project_weight(weight_kg, maintenance * (1 - spread), kcal)
        else:
            proj_low = proj_high = None
    else:
        per_month = used / LB_PER_KG
        proj = [round(weight_kg + per_month * m, 1) for m in (1, 2, 3)]
        proj_low = [round(weight_kg + (low_rate or 0.0) * m, 1) for m in (1, 2, 3)]
        proj_high = [round(weight_kg + (high_rate or 0.0) * m, 1) for m in (1, 2, 3)]
        change = used
        pace_out = round(used, 1)
    breakdown = {
        "resting_kcal": round(resting), "resting_method": method, "lifestyle": lifestyle if modern else None, "pal": pal,
        "exercise_kcal": round(exercise), "training": training, "tee_factor": tee_factor or 1.0, "maintenance": round(maintenance),
        "goal": effective, "adjust_kcal": round(kcal - maintenance), "adjust_pct": round((kcal - maintenance) / maintenance * 100, 1) if maintenance else 0,
        "protein_per_kg": per_kg, "protein_basis_kg": round(_protein_reference(weight_kg, height_cm), 1), "floor": floor,
        "extra_kcal": extra, "legacy": not modern, "lift_exp": lift_exp if goal == "muscle" else None,
    }
    return Targets(kcal=int(kcal), protein_g=protein, carbs_g=carbs, fat_g=fat, maintenance_kcal=int(round(maintenance / 10) * 10), note=note,
                   pace_lb_month=pace_out, max_pace_lb_month=max_pace, projection_kg=proj, recommended_pace_lb_month=recommended,
                   projection_low_kg=proj_low, projection_high_kg=proj_high,
                   maintenance_low=int(round(maintenance * (1 - spread) / 50) * 50), maintenance_high=int(round(maintenance * (1 + spread) / 50) * 50),
                   change_lb_month=round(change, 1), blocked=blocked, breakdown=breakdown)


def macros_for_kcal(kcal: float, weight_kg: float, goal: str, height_cm: float | None = None) -> tuple[int, int, int]:
    """Re-split macros after the user nudges the calories: protein by weight, fat about 27 %, carbs the rest."""
    ref = _protein_reference(weight_kg, height_cm) if height_cm else weight_kg
    protein = round(ref * _PROTEIN_PER_KG[goal])
    fat = round(min(max(kcal * _FAT_SHARE / 9, _FAT_MIN_PER_KG * ref), 0.35 * kcal / 9))
    carbs = max(0, round((kcal - protein * 4 - fat * 9) / 4))
    return int(protein), int(carbs), int(fat)


# Activities cadence offers, with their metabolic equivalent (kcal per kg per hour; values of the Compendium of Physical
# Activities, rounded): an ESTIMATE, shown as such. (key, label, group, icon, MET, search words). The first block of keys
# existed before the search list: they must keep working for workouts already logged.
ACTIVITIES = [
    ("caminar_lento", "Caminata lenta", "caminar", "person-simple-walk", 2.5, "pasear paseo"),
    ("caminar", "Caminata a paso normal", "caminar", "person-simple-walk", 3.5, "andar"),
    ("caminar_rapido", "Caminata rápida", "caminar", "sneaker-move", 4.8, "power walking"),
    ("caminar_carga", "Caminata con carga / cochecito", "caminar", "baby-carriage", 4.5, "mochila bebé coche"),
    ("senderismo", "Senderismo", "caminar", "person-simple-hike", 6.0, "hiking montaña cerro"),
    ("escaleras", "Subir escaleras", "caminar", "stairs", 8.8, "gradas"),
    ("trote", "Trote ligero", "correr", "person-simple-run", 7.0, "jogging trotar"),
    ("correr", "Carrera a ritmo moderado", "correr", "person-simple-run", 9.8, "correr running"),
    ("correr_rapido", "Carrera a ritmo rápido", "correr", "speedometer", 11.8, "sprint velocidad"),
    ("saltar_cuerda", "Saltar la cuerda", "correr", "lightning", 11.0, "comba"),
    ("ciclismo_suave", "Bicicleta suave", "bici", "person-simple-bike", 4.0, "pedalear paseo"),
    ("ciclismo", "Bicicleta, ritmo moderado", "bici", "person-simple-bike", 7.5, "ciclismo"),
    ("spinning", "Spinning / bici estática", "bici", "bicycle", 8.5, "estatica indoor"),
    ("natacion", "Natación, ritmo suave", "agua", "person-simple-swim", 6.0, "nadar piscina"),
    ("natacion_fuerte", "Natación intensa", "agua", "person-simple-swim", 9.8, "nadar piscina"),
    ("pesas", "Pesas, esfuerzo moderado", "fuerza", "barbell", 5.0, "gimnasio mancuernas"),
    ("pesas_fuertes", "Pesas, esfuerzo intenso", "fuerza", "barbell", 6.0, "gimnasio"),
    ("calistenia", "Ejercicios con tu peso", "fuerza", "person-arms-spread", 3.8, "calistenia flexiones abdominales"),
    ("hiit", "HIIT / circuito", "fuerza", "timer", 8.0, "intervalos crossfit funcional"),
    ("cardio", "Cardio general", "fuerza", "heartbeat", 7.0, "eliptica"),
    ("yoga", "Yoga", "flexibilidad", "flower-lotus", 2.5, ""),
    ("pilates", "Pilates", "flexibilidad", "person-simple-tai-chi", 3.0, ""),
    ("estiramiento", "Estiramientos", "flexibilidad", "person-arms-spread", 2.3, "stretching"),
    ("baile", "Baile", "deporte", "music-notes", 5.5, "bailar"),
    ("zumba", "Zumba / aeróbicos", "deporte", "music-notes-simple", 6.5, "aerobicos"),
    ("futbol", "Fútbol", "deporte", "soccer-ball", 7.0, "futbolito"),
    ("baloncesto", "Baloncesto", "deporte", "basketball", 6.5, "basquetbol"),
    ("tenis", "Tenis / pádel", "deporte", "tennis-ball", 7.3, "padel raqueta"),
    ("voleibol", "Voleibol", "deporte", "volleyball", 4.0, "voley"),
    ("boxeo", "Boxeo / artes marciales", "deporte", "boxing-glove", 7.8, "karate taekwondo"),
    ("remo", "Remo", "agua", "boat", 7.0, "kayak"),
    ("limpieza", "Limpiar la casa", "otros", "broom", 3.3, "quehaceres aseo"),
    ("jardineria", "Jardinería", "otros", "plant", 4.0, "huerto plantas"),
    ("otro", "Otro", "otros", "lightning", 4.5, ""),
]
WORKOUT_MET = {key: met for key, _l, _g, _i, met, _w in ACTIVITIES}


def workout_kcal(kind: str, minutes: int, weight_kg: float) -> float:
    return round(WORKOUT_MET.get(kind, WORKOUT_MET["otro"]) * weight_kg * minutes / 60)
