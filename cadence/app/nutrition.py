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


@dataclass
class Targets:
    kcal: int
    protein_g: int
    carbs_g: int
    fat_g: int
    maintenance_kcal: int
    note: str | None = None


def age_on(birthdate: date, today: date) -> int:
    return today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))


def bmr(sex: str, weight_kg: float, height_cm: float, age: int) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    offset = {"male": 5, "female": -161}.get(sex, -78)  # "other": midpoint of both
    return base + offset


def compute_targets(sex: str, birthdate: date, height_cm: float, weight_kg: float, activity: str, goal: str,
                    today: date) -> Targets:
    age = age_on(birthdate, today)
    maintenance = bmr(sex, weight_kg, height_cm, age) * ACTIVITY[activity]
    rule = _GOAL_RULES[goal]
    note = None
    factor = rule["factor"]
    if age < 18 and factor < 1:
        factor, note = 1.0, "Eres menor de edad: mantenemos tus calorías en lugar de un déficit."
    kcal = maintenance * factor
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
    return Targets(kcal=int(kcal), protein_g=int(protein), carbs_g=int(carbs), fat_g=int(fat),
                   maintenance_kcal=int(round(maintenance / 10) * 10), note=note)


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
