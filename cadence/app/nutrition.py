"""Daily calorie and macro targets from a few personal data (Mifflin-St Jeor).

A general starting point, not medical advice: the user can always adjust it.
"""

from dataclasses import dataclass
from datetime import date

ACTIVITY = {
    "low": 1.2,       # little or no exercise
    "moderate": 1.55,  # exercise 3-5 days a week
    "high": 1.725,    # exercise almost every day
}
GOALS = ("lose", "maintain", "gain", "muscle")
SEXES = ("female", "male", "other")

# kcal adjustment over maintenance, and protein per kg of body weight.
_GOAL_RULES = {
    "lose": {"factor": 0.80, "protein_per_kg": 1.8},
    "maintain": {"factor": 1.00, "protein_per_kg": 1.4},
    "gain": {"factor": 1.10, "protein_per_kg": 1.6},
    "muscle": {"factor": 1.10, "protein_per_kg": 2.0},
}
_KCAL_FLOOR = {"female": 1200, "male": 1500, "other": 1350}


KCAL_PER_LB = 3500  # one pound of body fat holds about 3,500 kcal (7,700 per kg)
LB_PER_KG = 2.2046226
_DAYS_PER_MONTH = 30


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


def weight_change_lb_month(maintenance_kcal: float, kcal: float) -> float:
    """Pounds per month the scale would move eating `kcal` a day (negative = losing). An estimate, not a promise."""
    return (kcal - maintenance_kcal) * _DAYS_PER_MONTH / KCAL_PER_LB


def kcal_gap_for_pace(lb_month: float) -> float:
    return lb_month * KCAL_PER_LB / _DAYS_PER_MONTH


def max_pace_lb_month(sex: str, goal: str, weight_kg: float, height_cm: float, age: int, maintenance: float) -> float:
    """The fastest safe pace, in lb/month, in the direction of the goal.

    Losing: no more than 1 % of the body weight per week, never under the daily minimum, nothing for minors or for a
    weight that is already low. Gaining: no more than 0.5 % of the body weight per week."""
    weeks = _DAYS_PER_MONTH / 7
    if goal == "lose":
        bmi = weight_kg / ((height_cm / 100) ** 2)
        if age < 18 or bmi < 18.5:
            return 0.0
        by_weight = 0.01 * weight_kg * weeks * LB_PER_KG
        by_floor = max(0.0, (maintenance - _KCAL_FLOOR.get(sex, 1350)) * _DAYS_PER_MONTH / KCAL_PER_LB)
        return round(min(by_weight, by_floor), 1)
    if goal in ("gain", "muscle"):
        return round(0.005 * weight_kg * weeks * LB_PER_KG, 1)
    return 0.0


def maintenance_kcal(sex: str, birthdate: date, height_cm: float, weight_kg: float, activity: str, today: date) -> float:
    return bmr(sex, weight_kg, height_cm, age_on(birthdate, today)) * ACTIVITY[activity]


def age_on(birthdate: date, today: date) -> int:
    return today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))


def bmr(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    offset = {"male": 5, "female": -161}.get(sex, -78)  # "other": midpoint of both
    return base + offset


def compute_targets(sex: str, birthdate: date, height_cm: float, weight_kg: float, activity: str, goal: str,
                    today: date, pace_lb_month: float | None = None) -> Targets:
    """Daily calories and macros. With `pace_lb_month` the calories come from the pace the person asked for
    (pounds per month in the direction of the goal), limited to what is safe; without it, the fixed rule of the goal."""
    age = age_on(birthdate, today)
    maintenance = bmr(sex, weight_kg, height_cm, age) * ACTIVITY[activity]
    rule = _GOAL_RULES[goal]
    note = None
    factor = rule["factor"]
    if age < 18 and factor < 1:
        factor, note = 1.0, "Eres menor de edad: mantenemos tus calorías en lugar de un déficit."
    kcal = maintenance * factor
    max_pace = max_pace_lb_month(sex, goal, weight_kg, height_cm, age, maintenance)
    if pace_lb_month is not None and goal in ("lose", "gain", "muscle"):
        wanted = max(0.0, pace_lb_month)
        used = min(wanted, max_pace)
        if used < wanted - 0.05 and max_pace > 0:
            note = f"Ajustamos tu ritmo a {max_pace:g} libras al mes, lo más seguro para ti."
        elif max_pace == 0 and goal == "lose":
            note = ("Eres menor de edad: mantenemos tus calorías en lugar de un déficit." if age < 18
                    else "Tu peso ya es bajo para tu estatura: te sugerimos mantener en lugar de bajar.")
        sign = -1 if goal == "lose" else 1
        kcal = maintenance + sign * kcal_gap_for_pace(used)
    bmi = weight_kg / ((height_cm / 100) ** 2)
    if goal == "lose" and bmi < 18.5:
        kcal, note = maintenance, "Tu peso ya es bajo para tu estatura: te sugerimos mantener en lugar de bajar."
    floor = _KCAL_FLOOR.get(sex, 1350)
    if kcal < floor and factor < 1:
        kcal, note = floor, "Ajustamos al mínimo diario recomendable; bajar más rápido no es seguro sin supervisión."
    kcal = round(kcal / 10) * 10

    protein = round(weight_kg * rule["protein_per_kg"])
    fat = round(kcal * 0.27 / 9)
    carbs = max(0, round((kcal - protein * 4 - fat * 9) / 4))
    # What the final calories mean for the scale (after every safety limit), and where the weight would be.
    change = weight_change_lb_month(maintenance, kcal)  # negative = losing
    along = -change if goal == "lose" else change if goal in ("gain", "muscle") else 0.0
    pace = round(max(0.0, along), 1)
    kg_month = change / LB_PER_KG
    projection = [round(weight_kg + kg_month * m, 1) for m in (1, 2, 3)]
    return Targets(kcal=int(kcal), protein_g=int(protein), carbs_g=int(carbs), fat_g=int(fat),
                   maintenance_kcal=int(round(maintenance / 10) * 10), note=note, pace_lb_month=pace,
                   max_pace_lb_month=max_pace, projection_kg=projection)


def macros_for_kcal(kcal: float, weight_kg: float, goal: str) -> tuple[int, int, int]:
    """Re-split macros after the user nudges the calories: protein by weight, fat 27 %, carbs the rest."""
    protein = round(weight_kg * _GOAL_RULES[goal]["protein_per_kg"])
    fat = round(kcal * 0.27 / 9)
    carbs = max(0, round((kcal - protein * 4 - fat * 9) / 4))
    return int(protein), int(carbs), int(fat)


# Activities cadence offers, with their metabolic equivalent (kcal per kg per hour; values of the Compendium of Physical
# Activities, rounded): an ESTIMATE, shown as such. (key, label, group, icon, MET, search words). The first block of keys
# existed before the search list: they must keep working for workouts already logged.
ACTIVITIES = [
    ("caminar_lento", "Caminata lenta", "caminar", "shoe", 2.5, "pasear paseo"),
    ("caminar", "Caminata a paso normal", "caminar", "shoe", 3.5, "andar"),
    ("caminar_rapido", "Caminata rápida", "caminar", "shoe", 4.8, "power walking"),
    ("caminar_carga", "Caminata con carga / cochecito", "caminar", "shoe", 4.5, "mochila bebé coche"),
    ("senderismo", "Senderismo", "caminar", "sun", 6.0, "hiking montaña cerro"),
    ("escaleras", "Subir escaleras", "caminar", "shoe", 8.8, "gradas"),
    ("trote", "Trote ligero", "correr", "shoe", 7.0, "jogging trotar"),
    ("correr", "Carrera a ritmo moderado", "correr", "shoe", 9.8, "correr running"),
    ("correr_rapido", "Carrera a ritmo rápido", "correr", "shoe", 11.8, "sprint velocidad"),
    ("saltar_cuerda", "Saltar la cuerda", "correr", "bolt", 11.0, "comba"),
    ("ciclismo_suave", "Bicicleta suave", "bici", "bike", 4.0, "pedalear paseo"),
    ("ciclismo", "Bicicleta, ritmo moderado", "bici", "bike", 7.5, "ciclismo"),
    ("spinning", "Spinning / bici estática", "bici", "bike", 8.5, "estatica indoor"),
    ("natacion", "Natación, ritmo suave", "agua", "swim", 6.0, "nadar piscina"),
    ("natacion_fuerte", "Natación intensa", "agua", "swim", 9.8, "nadar piscina"),
    ("pesas", "Pesas, esfuerzo moderado", "fuerza", "dumbbell", 5.0, "gimnasio mancuernas"),
    ("pesas_fuertes", "Pesas, esfuerzo intenso", "fuerza", "dumbbell", 6.0, "gimnasio"),
    ("calistenia", "Ejercicios con tu peso", "fuerza", "dumbbell", 3.8, "calistenia flexiones abdominales"),
    ("hiit", "HIIT / circuito", "fuerza", "flame", 8.0, "intervalos crossfit funcional"),
    ("cardio", "Cardio general", "fuerza", "flame", 7.0, "eliptica"),
    ("yoga", "Yoga", "flexibilidad", "yoga", 2.5, ""),
    ("pilates", "Pilates", "flexibilidad", "yoga", 3.0, ""),
    ("estiramiento", "Estiramientos", "flexibilidad", "yoga", 2.3, "stretching"),
    ("baile", "Baile", "deporte", "bolt", 5.5, "bailar"),
    ("zumba", "Zumba / aeróbicos", "deporte", "bolt", 6.5, "aerobicos"),
    ("futbol", "Fútbol", "deporte", "bolt", 7.0, "futbolito"),
    ("baloncesto", "Baloncesto", "deporte", "bolt", 6.5, "basquetbol"),
    ("tenis", "Tenis / pádel", "deporte", "bolt", 7.3, "padel raqueta"),
    ("voleibol", "Voleibol", "deporte", "bolt", 4.0, "voley"),
    ("boxeo", "Boxeo / artes marciales", "deporte", "bolt", 7.8, "karate taekwondo"),
    ("remo", "Remo", "agua", "swim", 7.0, "kayak"),
    ("limpieza", "Limpiar la casa", "otros", "sun", 3.3, "quehaceres aseo"),
    ("jardineria", "Jardinería", "otros", "leaf", 4.0, "huerto plantas"),
    ("otro", "Otro", "otros", "bolt", 4.5, ""),
]
WORKOUT_MET = {key: met for key, _l, _g, _i, met, _w in ACTIVITIES}


def workout_kcal(kind: str, minutes: int, weight_kg: float) -> float:
    return round(WORKOUT_MET.get(kind, WORKOUT_MET["otro"]) * weight_kg * minutes / 60)
