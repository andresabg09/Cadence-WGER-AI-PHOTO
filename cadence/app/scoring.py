"""Nutrition score of a meal and of a day, plus protein and fibre levels.

Fixed formulas over the values wger (or the person's own foods) give: the AI never takes part. The score is an
orientation, not medical advice. When a value is missing (wger does not always have fibre, sugar or saturated
fat) that criterion does not subtract: the score is spread over the criteria we do have and the missing ones
are reported as "partial data".
"""

import unicodedata
from dataclasses import dataclass, field

# Each meal's share of the day: used to turn daily goals into what a single meal should bring.
MEAL_SHARE = {"desayuno": 0.25, "almuerzo": 0.35, "merienda": 0.10, "cena": 0.30, "otro": 0.10}
LABELS = ((80, "Excelente"), (65, "Buena"), (45, "Regular"), (0, "Mejorable"))
MAX_POINTS = {"macros": 30, "protein": 20, "fibre": 15, "quality": 15, "variety": 10, "portion": 10}
TITLES = {"macros": "Balance de macros", "protein": "Proteína de la comida", "fibre": "Fibra",
          "quality": "Azúcar y grasa saturada", "variety": "Variedad", "portion": "Porción"}

# (fibre, sugars, saturated fat) per 100 g of the basic prepared foods cadence adds to wger (approximate USDA values).
# Used only when wger itself has no value for that food. Keys: lower case, no accents, Spanish and English.
_STAPLE_ROWS = [
    ("arroz blanco cocido", "cooked white rice", 0.4, 0.1, 0.1), ("arroz integral cocido", "cooked brown rice", 1.6, 0.2, 0.2),
    ("pasta cocida", "cooked pasta", 1.8, 0.6, 0.2), ("quinoa cocida", "cooked quinoa", 2.8, 0.9, 0.2),
    ("avena cocida", "cooked oatmeal", 1.7, 0.3, 0.3), ("papa cocida", "boiled potato", 1.8, 0.8, 0.0),
    ("pure de papas", "mashed potatoes", 1.5, 1.2, 2.5), ("papas fritas", "french fries", 3.8, 0.3, 2.3),
    ("yuca cocida", "boiled yuca", 1.8, 1.7, 0.1), ("maiz cocido", "boiled corn", 2.4, 3.2, 0.2),
    ("pan blanco", "white bread", 2.7, 5.0, 0.7), ("pan integral", "whole wheat bread", 6.0, 5.6, 0.7),
    ("tortilla de maiz", "corn tortilla", 6.3, 0.9, 0.4), ("frijoles negros cocidos", "cooked black beans", 8.7, 0.3, 0.1),
    ("frijoles rojos cocidos", "cooked red beans", 6.4, 0.3, 0.1), ("frijoles pintos cocidos", "cooked pinto beans", 9.0, 0.3, 0.1),
    ("garbanzos cocidos", "cooked chickpeas", 7.6, 4.8, 0.3), ("lentejas cocidas", "cooked lentils", 7.9, 1.8, 0.1),
    ("guandu cocido", "cooked pigeon peas", 5.1, 2.0, 0.1), ("pechuga de pollo a la plancha", "grilled chicken breast", 0.0, 0.0, 1.0),
    ("muslo de pollo al horno", "roasted chicken thigh", 0.0, 0.0, 3.0), ("carne molida cocida", "cooked ground beef", 0.0, 0.0, 6.0),
    ("bistec de res a la plancha", "grilled beef steak", 0.0, 0.0, 3.3), ("tocino cocido", "cooked bacon", 0.0, 0.0, 14.0),
    ("salmon al horno", "baked salmon", 0.0, 0.0, 3.1), ("tilapia a la plancha", "grilled tilapia", 0.0, 0.0, 0.9),
    ("atun en agua", "canned tuna in water", 0.0, 0.0, 0.2), ("camarones cocidos", "cooked shrimp", 0.0, 0.0, 0.1),
    ("huevo cocido", "boiled egg", 0.0, 1.1, 3.3), ("huevos revueltos", "scrambled eggs", 0.0, 1.4, 3.3),
    ("huevo frito", "fried egg", 0.0, 0.4, 4.4), ("leche entera", "whole milk", 0.0, 5.0, 1.9),
    ("yogur natural", "plain yogurt", 0.0, 4.7, 2.1), ("queso cheddar", "cheddar cheese", 0.0, 0.5, 18.9),
    ("queso mozzarella", "mozzarella cheese", 0.0, 1.0, 10.9), ("ensalada verde", "green salad", 1.3, 1.3, 0.0),
    ("tomate", "tomato", 1.2, 2.6, 0.0), ("pepino", "cucumber", 0.5, 1.7, 0.0), ("zanahoria cruda", "raw carrot", 2.8, 4.7, 0.0),
    ("zanahoria cocida", "boiled carrots", 3.0, 3.5, 0.0), ("brocoli cocido", "boiled broccoli", 3.3, 1.4, 0.1),
    ("aguacate", "avocado", 6.7, 0.7, 2.1), ("platano frito", "fried plantain", 2.3, 14.0, 3.2), ("banano", "banana", 2.6, 12.2, 0.1),
    ("manzana", "apple", 2.4, 10.4, 0.0), ("naranja", "orange", 2.4, 9.4, 0.0), ("sandia", "watermelon", 0.4, 6.2, 0.0),
    ("pina", "pineapple", 1.4, 9.9, 0.0), ("mango", "mango", 1.6, 13.7, 0.1), ("papaya", "papaya", 1.7, 7.8, 0.1),
    ("uvas", "grapes", 0.9, 15.5, 0.1), ("fresas", "strawberries", 2.0, 4.9, 0.0), ("helado de vainilla", "vanilla ice cream", 0.7, 21.0, 6.8),
    ("helado de chocolate", "chocolate ice cream", 1.2, 22.0, 6.9), ("pizza de queso", "cheese pizza", 2.3, 3.6, 4.5),
    ("jugo de naranja", "orange juice", 0.2, 8.4, 0.0), ("gaseosa de cola", "cola soda", 0.0, 10.6, 0.0), ("cafe negro", "black coffee", 0.0, 0.0, 0.0),
    ("mantequilla", "butter", 0.0, 0.1, 51.0), ("aceite de oliva", "olive oil", 0.0, 0.0, 13.8), ("mayonesa", "mayonnaise", 0.0, 0.6, 11.2),
    ("salsa de tomate", "ketchup", 0.3, 22.8, 0.0), ("mantequilla de mani", "peanut butter", 6.0, 9.2, 10.0), ("miel", "honey", 0.2, 82.0, 0.0),
]


def _key(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower().strip()
    return " ".join(text.split())


STAPLE_EXTRA = {}
for _es, _en, _fibre, _sugar, _sat in _STAPLE_ROWS:
    STAPLE_EXTRA[_key(_es)] = STAPLE_EXTRA[_key(_en)] = (_fibre, _sugar, _sat)


def number(value) -> float | None:
    """wger sends decimals as numbers or strings and leaves unknowns as null."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def per_100g(name: str, ingredient: dict) -> tuple[float | None, float | None, float | None]:
    """(fibre, sugars, saturated fat) per 100 g: from wger, else from cadence's table of basic foods."""
    fibre = number(ingredient.get("fibres"))
    sugar = number(ingredient.get("carbohydrates_sugar"))
    sat = number(ingredient.get("fat_saturated"))
    known = STAPLE_EXTRA.get(_key(name))
    if known:
        fibre = known[0] if fibre is None else fibre
        sugar = known[1] if sugar is None else sugar
        sat = known[2] if sat is None else sat
    return fibre, sugar, sat


@dataclass
class Food:
    name: str
    grams: float
    kcal: float
    protein: float
    carbs: float
    fat: float
    fibre: float | None = None  # grams in this portion (None = unknown)
    sugar: float | None = None
    sat_fat: float | None = None


@dataclass
class Goal:
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float


@dataclass
class Part:
    key: str
    label: str
    points: float
    max: int
    note: str


@dataclass
class Score:
    points: int
    label: str
    parts: list[Part] = field(default_factory=list)
    partial: list[str] = field(default_factory=list)  # criteria skipped or incomplete for lack of data


@dataclass
class Level:
    value_g: float
    target_g: float
    pct: int  # of the target, capped at 100 (the bar's marker)
    label: str  # bajo | medio | alto


MIN_COVERAGE = 0.6  # a criterion needs data for at least this share of the plate's weight to be judged


def covered(foods: list[Food], attr: str) -> list[Food]:
    """The foods that have `attr` data, but only when they are most of the plate (else the criterion is skipped)."""
    known = [f for f in foods if getattr(f, attr) is not None]
    total = sum(f.grams for f in foods) or 1.0
    return known if sum(f.grams for f in known) / total >= MIN_COVERAGE else []


def missing_note(criterion: str, foods: list[Food], attr: str) -> str:
    names = [f.name for f in foods if getattr(f, attr) is None]
    return f"{criterion} de {', '.join(names)}" if len(names) <= 2 else f"{criterion} ({len(names)} de {len(foods)} alimentos)"


def label_for(points: float) -> str:
    return next(name for floor, name in LABELS if points >= floor)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def fibre_target(goal: Goal) -> float:
    """Daily fibre goal: 14 g per 1000 kcal, never below 25 g."""
    return max(25.0, 14.0 * goal.kcal / 1000.0)


def level(value: float, target: float) -> Level:
    pct = 0 if target <= 0 else value / target * 100
    return Level(round(value, 1), round(target, 1), int(round(min(100, pct))), "bajo" if pct < 50 else "medio" if pct < 90 else "alto")


def protein_level(foods: list[Food], goal: Goal, meal: str | None = None) -> Level:
    share = MEAL_SHARE.get(meal, 0.1) if meal else 1.0
    return level(sum(f.protein for f in foods), goal.protein_g * share)


def fibre_level(foods: list[Food], goal: Goal, meal: str | None = None) -> Level | None:
    """None when no food has fibre data at all (we cannot say 'low' about something we do not know)."""
    known = covered(foods, "fibre")
    if not known:
        return None
    share = MEAL_SHARE.get(meal, 0.1) if meal else 1.0
    return level(sum(f.fibre for f in known), fibre_target(goal) * share)


def score_meal(foods: list[Food], goal: Goal, meal: str) -> Score | None:
    total_kcal = sum(f.kcal for f in foods)
    if not foods or total_kcal < 20:
        return None
    share = MEAL_SHARE.get(meal, 0.1)
    grams = sum(f.grams for f in foods) or 1.0
    parts: list[Part] = []
    partial: list[str] = []

    # 1. Balance of macros: energy split against the split of the person's own goal.
    p_k, c_k, f_k = (sum(f.protein for f in foods) * 4, sum(f.carbs for f in foods) * 4, sum(f.fat for f in foods) * 9)
    eaten = p_k + c_k + f_k
    goal_k = goal.protein_g * 4 + goal.carbs_g * 4 + goal.fat_g * 9
    if eaten > 0 and goal_k > 0:
        actual = (p_k / eaten, c_k / eaten, f_k / eaten)
        ideal = (goal.protein_g * 4 / goal_k, goal.carbs_g * 4 / goal_k, goal.fat_g * 9 / goal_k)
        distance = sum(abs(a - b) for a, b in zip(actual, ideal))
        parts.append(Part("macros", TITLES["macros"], MAX_POINTS["macros"] * _clamp(1 - distance / 0.8), MAX_POINTS["macros"],
                          f"Proteína {actual[0]:.0%}, carbos {actual[1]:.0%} y grasa {actual[2]:.0%} de las calorías (tu meta: {ideal[0]:.0%}, {ideal[1]:.0%}, {ideal[2]:.0%})"))

    # 2. Protein against this meal's part of the day's goal (more than enough is not penalised).
    protein = sum(f.protein for f in foods)
    target = max(5.0, goal.protein_g * share)
    parts.append(Part("protein", TITLES["protein"], MAX_POINTS["protein"] * _clamp(protein / target), MAX_POINTS["protein"],
                      f"{protein:.0f} g de los {target:.0f} g sugeridos"))

    # 3. Fibre (only the foods that have the data count; the rest are reported).
    with_fibre = covered(foods, "fibre")
    if with_fibre:
        f_target = fibre_target(goal) * share
        got = sum(f.fibre for f in with_fibre)
        parts.append(Part("fibre", TITLES["fibre"], MAX_POINTS["fibre"] * _clamp(got / f_target), MAX_POINTS["fibre"],
                          f"{got:.0f} g de los {f_target:.0f} g sugeridos"))
        if len(with_fibre) < len(foods):
            partial.append(missing_note("fibra", foods, "fibre"))
    else:
        partial.append("fibra" if all(f.fibre is None for f in foods) else missing_note("fibra", foods, "fibre"))

    # 4. Quality: sugars and saturated fat per 100 g of food (like Nutri-Score, but over the whole plate).
    sub = []
    notes = []
    sugar_foods = covered(foods, "sugar")
    if sugar_foods:
        density = sum(f.sugar for f in sugar_foods) / (sum(f.grams for f in sugar_foods) or 1) * 100
        sub.append(_clamp(1 - (density - 5) / 10))  # 5 g per 100 g or less: full; 15 g or more: none
        notes.append(f"azúcares {density:.0f} g por 100 g")
        if len(sugar_foods) < len(foods):
            partial.append(missing_note("azúcar", foods, "sugar"))
    sat_foods = covered(foods, "sat_fat")
    if sat_foods:
        density = sum(f.sat_fat for f in sat_foods) / (sum(f.grams for f in sat_foods) or 1) * 100
        sub.append(_clamp(1 - (density - 1) / 3))  # 1 g per 100 g or less: full; 4 g or more: none
        notes.append(f"grasa saturada {density:.1f} g por 100 g")
        if len(sat_foods) < len(foods):
            partial.append(missing_note("grasa saturada", foods, "sat_fat"))
    if sub:
        parts.append(Part("quality", TITLES["quality"], MAX_POINTS["quality"] * sum(sub) / len(sub), MAX_POINTS["quality"], "; ".join(notes).capitalize()))
    else:
        partial.append("azúcar y grasa saturada" if all(f.sugar is None and f.sat_fat is None for f in foods) else "azúcar y grasa saturada (datos insuficientes)")

    # 5. Variety: how many different foods.
    distinct = len({_key(f.name) for f in foods})
    wanted = 3 if meal in ("desayuno", "almuerzo", "cena") else 2
    variety = 1.0 if distinct >= wanted else 0.3 + 0.7 * (distinct - 1) / (wanted - 1)
    parts.append(Part("variety", TITLES["variety"], MAX_POINTS["variety"] * variety, MAX_POINTS["variety"],
                      f"{distinct} alimento{'s' if distinct != 1 else ''} distinto{'s' if distinct != 1 else ''}"))

    # 6. Portion against the calories this meal should bring: 60 %-125 % of its part is fine.
    meal_target = max(80.0, goal.kcal * share)
    q = total_kcal / meal_target
    if q < 0.6:
        factor = q / 0.6
    elif q <= 1.25:
        factor = 1.0
    else:
        factor = _clamp(1 - (q - 1.25) / 0.75)
    parts.append(Part("portion", TITLES["portion"], MAX_POINTS["portion"] * factor, MAX_POINTS["portion"],
                      f"{total_kcal:.0f} kcal; lo esperado en esta comida ronda las {meal_target:.0f}"))

    earned = sum(p.points for p in parts)
    available = sum(p.max for p in parts)
    points = int(round(100 * earned / available)) if available else 0
    for p in parts:
        p.points = round(p.points, 1)
    return Score(points, label_for(points), parts, partial)


def score_day(meal_scores: list[tuple[float, int]]) -> tuple[int, str] | None:
    """The day's score: the meals' scores averaged by calories (so a snack does not weigh like lunch)."""
    total = sum(kcal for kcal, _ in meal_scores)
    if total <= 0:
        return None
    points = int(round(sum(kcal * pts for kcal, pts in meal_scores) / total))
    return points, label_for(points)
