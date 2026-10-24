"""Awards, daily/weekly challenges and the coin shop. Pure logic over facts read from the person's own data (no I/O).

Nothing here asks the AI anything, and nothing rewards eating less than you need: calorie challenges are only
completed inside a band around the person's own goal (90 %-115 %).
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from . import scoring

BAND_LOW, BAND_HIGH = 0.9, 1.15  # share of the calorie goal that counts as "on target" for challenges
EARLY_BREAKFAST = "09:00"


@dataclass
class MealFacts:
    key: str
    foods: list[scoring.Food]
    score: scoring.Score | None
    first_time: str | None = None  # HH:MM, local

    @property
    def kcal(self) -> float:
        return sum(f.kcal for f in self.foods)


@dataclass
class DayFacts:
    day: date
    meals: dict[str, MealFacts] = field(default_factory=dict)
    water_ml: int = 0
    workouts: int = 0
    weights: int = 0
    counts: bool = False  # something was registered that very day (the streak rule)

    @property
    def kcal(self) -> float:
        return sum(m.kcal for m in self.meals.values())

    @property
    def protein(self) -> float:
        return sum(f.protein for m in self.meals.values() for f in m.foods)

    @property
    def foods(self) -> set[str]:
        return {scoring._key(f.name) for m in self.meals.values() for f in m.foods}

    @property
    def score(self) -> int | None:
        day = scoring.score_day([(m.kcal, m.score.points) for m in self.meals.values() if m.score])
        return day[0] if day else None


# ------------------------------------------------------------------ awards
# key -> (title, hint, art, category). "art" names the picture the screens draw (js/bits.js).
MEAL_AWARDS = {
    "protein_high": ("Proteína alta", "Una comida con la proteína que le toca del día", "protein", "comida"),
    "fibre_rich": ("Con fibra", "Una comida con la fibra que le toca del día", "fibre", "comida"),
    "varied_plate": ("Plato variado", "Cuatro alimentos distintos en una comida", "variety", "comida"),
    "excellent_plate": ("Plato excelente", "Una comida con puntuación de 80 o más", "balance", "comida"),
}

# key, title, hint, art, category, target, stat
MILESTONES = [
    ("first_log", "Primer registro", "Registra tu primer alimento", "fork", "constancia", 1, "total_logged"),
    ("first_photo", "Primera foto", "Registra un plato con foto", "camera", "constancia", 1, "photos"),
    ("streak_3", "Arrancaste", "3 días seguidos", "streak", "constancia", 3, "best_streak"),
    ("streak_7", "Una semana", "7 días seguidos", "streak", "constancia", 7, "best_streak"),
    ("streak_14", "Dos semanas", "14 días seguidos", "bolt", "constancia", 14, "best_streak"),
    ("streak_30", "Un mes entero", "30 días seguidos", "trophy", "constancia", 30, "best_streak"),
    ("logs_25", "25 alimentos", "Registra 25 alimentos", "leaf", "constancia", 25, "total_logged"),
    ("logs_100", "100 alimentos", "Registra 100 alimentos", "trophy", "constancia", 100, "total_logged"),
    ("first_weight", "Primer peso", "Anota tu peso", "scale", "constancia", 1, "weights"),
    ("weights_5", "Constancia", "Anota tu peso 5 veces", "scale", "constancia", 5, "weights"),
    ("on_target", "Día en la meta", "Termina un día cerca de tu meta de calorías", "target", "comida", 1, "days_on_target"),
    ("protein_day", "Proteína completa", "Llega a tu meta de proteína en un día", "protein", "comida", 1, "days_protein"),
    ("bright_day", "Día brillante", "Un día con puntuación de 85 o más", "balance", "comida", 1, "days_bright"),
    ("explorer", "Explorador", "15 alimentos distintos en una semana", "variety", "comida", 15, "foods_week"),
    ("hydrated", "Hidratado", "Llega a tu meta de agua en un día", "water", "agua", 1, "days_water"),
    ("hydration_5", "Semana hidratada", "Cumple tu meta de agua 5 días", "water", "agua", 5, "days_water"),
    ("early_bird", "Madrugador", "Registra el desayuno antes de las 9:00, 5 días", "early", "constancia", 5, "early_days"),
    ("mover", "En movimiento", "Registra 3 entrenamientos", "move", "movimiento", 3, "workouts"),
]
CATEGORIES = ("comida", "constancia", "agua", "movimiento")


def meal_awards(meal: MealFacts, goal: scoring.Goal) -> list[str]:
    """Which awards a single meal earns (only meals that are a real meal: 150 kcal or more)."""
    if meal.kcal < 150:
        return []
    earned = []
    if scoring.protein_level(meal.foods, goal, meal.key).label == "alto":
        earned.append("protein_high")
    fibre = scoring.fibre_level(meal.foods, goal, meal.key)
    if fibre is not None and fibre.label == "alto":
        earned.append("fibre_rich")
    if len({scoring._key(f.name) for f in meal.foods}) >= 4:
        earned.append("varied_plate")
    if meal.score and meal.score.points >= 80:
        earned.append("excellent_plate")
    return earned


def milestone_stats(days: list[DayFacts], *, total_logged: int, photos: int, best_streak: int, weights: int, workouts: int,
                    goal: scoring.Goal, water_goal: int) -> dict[str, int]:
    on_target = sum(1 for d in days if goal.kcal > 0 and 0.9 * goal.kcal <= d.kcal <= 1.05 * goal.kcal)
    protein = sum(1 for d in days if goal.protein_g > 0 and d.protein >= goal.protein_g)
    bright = sum(1 for d in days if (d.score or 0) >= 85)
    water = sum(1 for d in days if water_goal > 0 and d.water_ml >= water_goal)
    early = sum(1 for d in days if d.meals.get("desayuno") and (d.meals["desayuno"].first_time or "99:99") < EARLY_BREAKFAST)
    by_day = {d.day: d.foods for d in days}
    best_week = 0
    for start in by_day:
        window = set()
        for offset in range(7):
            window |= by_day.get(start + timedelta(days=offset), set())
        best_week = max(best_week, len(window))
    return {"total_logged": total_logged, "photos": photos, "best_streak": best_streak, "weights": weights, "days_on_target": on_target,
            "days_protein": protein, "days_bright": bright, "foods_week": best_week, "days_water": water, "early_days": early, "workouts": workouts}


def milestone_states(stats: dict[str, int]) -> list[dict]:
    out = []
    for key, title, hint, art, category, target, stat in MILESTONES:
        value = int(stats.get(stat, 0))
        out.append({"key": key, "title": title, "hint": hint, "art": art, "category": category, "kind": "milestone",
                    "target": target, "value": min(value, target), "unlocked": value >= target})
    return out


# ------------------------------------------------------------------ challenges
@dataclass
class Challenge:
    key: str
    period: str  # day | week
    title: str
    hint: str
    art: str
    now: int
    total: int
    reward: int
    complete: bool
    note: str | None = None  # something to tell about this challenge instead of the progress bar


def on_target(kcal: float, goal_kcal: float) -> bool:
    return goal_kcal > 0 and BAND_LOW * goal_kcal <= kcal <= BAND_HIGH * goal_kcal


def daily_challenges(day: DayFacts, goal_kcal: float) -> list[Challenge]:
    kcal = day.kcal
    over = goal_kcal > 0 and kcal > BAND_HIGH * goal_kcal
    meals_logged = len(day.meals)
    good_meals = sum(1 for m in day.meals.values() if m.score and m.score.points > 70)
    return [
        Challenge("d_balance", "day", "Balance calórico", "Llega al 90 % de tu meta, sin pasarte mucho", "bolt", round(kcal), round(BAND_LOW * goal_kcal), 35,
                  on_target(kcal, goal_kcal), "Hoy te pasaste de tu meta: este reto ya no cuenta, mañana hay otro." if over else None),
        Challenge("d_constant", "day", "Mantente constante", "Registra comidas 2 veces", "fork", min(meals_logged, 2), 2, 25, meals_logged >= 2),
        Challenge("d_mindful", "day", "Come con equilibrio", "Saca más de 70 puntos en 2 comidas", "leaf", min(good_meals, 2), 2, 35, good_meals >= 2),
        Challenge("d_first", "day", "Empezar de nuevo", "Registra tu primera comida", "sun", min(meals_logged, 1), 1, 25, meals_logged >= 1),
    ]


def weekly_challenges(days: list[DayFacts], goal_kcal: float, water_goal: int) -> list[Challenge]:
    counted = sum(1 for d in days if d.counts)
    calories = sum(1 for d in days if on_target(d.kcal, goal_kcal))
    water = sum(1 for d in days if water_goal > 0 and d.water_ml >= water_goal)
    weights = sum(d.weights for d in days)
    workouts = sum(d.workouts for d in days)
    foods = set()
    for d in days:
        foods |= d.foods
    return [
        Challenge("w_streak", "week", "Mantén la racha", "Registra algo 5 días esta semana", "streak", min(counted, 5), 5, 100, counted >= 5),
        Challenge("w_calories", "week", "Control de calorías", "Llega a tu meta de calorías 5 días", "bolt", min(calories, 5), 5, 150, calories >= 5),
        Challenge("w_water", "week", "Héroe de la hidratación", "Cumple tu meta de agua 5 días", "water", min(water, 5), 5, 100, water >= 5),
        Challenge("w_weight", "week", "Seguir el progreso", "Registra tu peso", "scale", min(weights, 1), 1, 100, weights >= 1),
        Challenge("w_move", "week", "En movimiento", "Registra 3 entrenamientos", "move", min(workouts, 3), 3, 120, workouts >= 3),
        Challenge("w_variety", "week", "Come variado", "Registra 15 alimentos distintos", "variety", min(len(foods), 15), 15, 80, len(foods) >= 15),
    ]


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def period_id(challenge_key: str, today: date) -> str:
    """Daily challenges renew every day, weekly ones every Monday."""
    return today.isoformat() if challenge_key.startswith("d_") else week_start(today).isoformat()


# ------------------------------------------------------------------ the coin shop (cosmetics only)
# key -> (title, hint, price, slot)
SHOP = {
    "tema_aurora": ("Tema Aurora", "Violeta y verde menta para toda la app", 120, "theme"),
    "tema_atardecer": ("Tema Atardecer", "Ámbar y rosa, para la noche", 120, "theme"),
    "marco_dorado": ("Marco dorado", "Un aro dorado alrededor de tu foto de perfil", 300, "frame"),
}
