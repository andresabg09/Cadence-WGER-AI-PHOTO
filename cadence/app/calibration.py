"""Calibration: what the person's OWN weight and food say about how much their body spends.

Formulas miss by about +-10 %. After a few weeks of records the energy balance can be read backwards:

    expenditure = average intake - (change of the trend weight per day) x (energy of that weight change)

The scale is noisy (water, salt, a full stomach), so the slope is a least-squares line through all the weigh-ins of the window
(not an exponential moving average: that one lags behind a real trend and would shrink the slope, and with it the loss we read).
A window whose weights scatter too much around the line is not used. The result is mixed with the formula, more as more days
support it, and limited:

* DOWN is limited harder than up. People forget to log things; unlogged food makes the body look like it spends LESS, and the
  app would then cut their calories. So the factor never goes below 0.90 (up to 1.15), a day only counts when the food records
  look complete (at least 60 % of the goal and 1,000 kcal), and a suggestion is only a suggestion: nothing changes unless the
  person accepts it.
"""

from datetime import date, timedelta

WINDOW_DAYS = 28
MIN_VALID_DAYS = 10
MIN_WEIGH_INS = 4
MIN_SPAN_DAYS = 12
MAX_SCATTER_KG = 1.5  # standard deviation of the weigh-ins around the line: beyond this the scale says too little
KCAL_PER_KG_LOSS = 7700  # fat-like tissue (Hall)
KCAL_PER_KG_GAIN = 5500  # a mix of lean tissue (about 1,800) and fat (about 7,700): an assumption, stated as such
FACTOR_MIN, FACTOR_MAX = 0.90, 1.15
MIN_MEANINGFUL = 0.03  # a difference smaller than 3 % (about 80 kcal) is not worth a suggestion
MAX_STEP_KCAL = 150  # one accepted suggestion moves the goal by at most this
SUGGEST_EVERY_DAYS = 14
CACHE: dict[int, tuple[float, dict]] = {}  # per person: the last result (it costs a read of a month of diary)


def _fit(points: list[tuple[int, float]]) -> tuple[float, float]:
    """Least-squares line through (day, kg): its slope (kg per day) and how far the weigh-ins scatter around it (kg)."""
    n = len(points)
    if n < 2:
        return 0.0, 0.0
    mean_x = sum(x for x, _ in points) / n
    mean_y = sum(y for _, y in points) / n
    den = sum((x - mean_x) ** 2 for x, _ in points)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / den if den else 0.0
    scatter = (sum((y - (mean_y + slope * (x - mean_x))) ** 2 for x, y in points) / n) ** 0.5
    return slope, scatter


def calibrate(intake_by_day: dict[str, float], weights: dict[str, float], base_tee: float, goal_kcal: float, current_factor: float,
              today: date) -> dict:
    """What the records say. `base_tee` is the expenditure from the formula alone (factor 1). Returns a dict with `ready`,
    the reason when it is not, the evidence used and, when ready, the factor and the expenditure it implies."""
    end = today - timedelta(days=1)  # today is not finished
    start = end - timedelta(days=WINDOW_DAYS - 1)
    in_window = sorted(d for d in weights if start.isoformat() <= d <= end.isoformat())
    result = {"ready": False, "reason": None, "valid_days": 0, "weigh_ins": len(in_window), "base_tee": round(base_tee),
              "observed_tee": None, "factor": current_factor or 1.0, "slope_kg_week": None}
    if len(in_window) < MIN_WEIGH_INS:
        result["reason"] = "weights"  # needs more weigh-ins spread over about two weeks
        return result
    first_day, last_day = date.fromisoformat(in_window[0]), date.fromisoformat(in_window[-1])
    if (last_day - first_day).days < MIN_SPAN_DAYS:
        result["reason"] = "weights"
        return result
    floor_kcal = max(1000.0, 0.6 * goal_kcal)
    valid = [intake_by_day[d] for d in intake_by_day
             if first_day.isoformat() <= d <= last_day.isoformat() and intake_by_day[d] >= floor_kcal]
    result["valid_days"] = len(valid)
    if len(valid) < MIN_VALID_DAYS:
        result["reason"] = "food"  # needs more days with the food records complete
        return result
    slope, scatter = _fit([((date.fromisoformat(d) - first_day).days, weights[d]) for d in in_window])  # kg per day
    result["slope_kg_week"] = round(slope * 7, 2)
    if abs(slope * 7) > 1.2 or scatter > MAX_SCATTER_KG:
        result["reason"] = "noisy"  # a swing that big, or weights that jump around, are water and not tissue
        return result
    density = KCAL_PER_KG_LOSS if slope < 0 else KCAL_PER_KG_GAIN
    observed = sum(valid) / len(valid) - slope * density
    result["observed_tee"] = round(observed)
    weight_of_data = min(1.0, max(0.0, (len(valid) - 7) / 14))  # 10 days: 21 %, 14 days: 50 %, 21 days or more: all of it
    raw = 1 + weight_of_data * (observed / base_tee - 1)
    result["factor"] = round(min(FACTOR_MAX, max(FACTOR_MIN, raw)), 3)
    result["limited"] = raw < FACTOR_MIN
    result["ready"] = True
    return result


def suggestion(result: dict, current_factor: float, base_tee: float, goal_kcal: float, floor: float) -> dict | None:
    """The change to offer, or None when it is not worth one. The goal moves by the same kcal as the expenditure, so the
    person keeps the deficit or surplus they chose; one step is limited, and a deficit never goes under the minimum."""
    if not result.get("ready"):
        return None
    current = current_factor or 1.0
    new = result["factor"]
    if abs(new - current) / current < MIN_MEANINGFUL:
        return None
    delta = base_tee * (new - current)
    delta = max(-MAX_STEP_KCAL, min(MAX_STEP_KCAL, delta))
    target = round((goal_kcal + delta) / 10) * 10
    if target < floor <= goal_kcal:
        target = round(floor / 10) * 10
    if target == round(goal_kcal / 10) * 10:
        return None
    reached = abs(base_tee * (new - current)) <= MAX_STEP_KCAL
    return {"factor": new if reached else round(current + (new - current) * MAX_STEP_KCAL / abs(base_tee * (new - current)), 3),
            "goal_kcal": target, "change_kcal": target - round(goal_kcal / 10) * 10}


def next_day(today: date) -> str:
    return (today + timedelta(days=SUGGEST_EVERY_DAYS)).isoformat()
