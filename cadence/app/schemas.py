from pydantic import BaseModel


class DetectedComponent(BaseModel):
    name: str  # shown to the user (Spanish)
    # Generic English food name used to query/rank against wger's ingredient
    # DB (language 2). Falls back to `name` when the model doesn't provide it.
    search_name: str | None = None
    confidence: float | None = None


class IngredientCandidate(BaseModel):
    id: int
    name: str
    image: str | None = None
    score: float
    # Only populated for the top candidate of each component at /api/analyze
    # time (to limit extra wger calls) - fetch GET /api/ingredient/{id} for
    # any other candidate the user switches to.
    energy_kcal_100g: float | None = None


class ComponentMatch(BaseModel):
    detected_name: str
    confidence: float | None = None
    candidates: list[IngredientCandidate]


class AnalyzeResponse(BaseModel):
    components: list[ComponentMatch]


class ConfirmItem(BaseModel):
    ingredient_id: int
    amount_grams: float
    detected_name: str | None = None


class ConfirmRequest(BaseModel):
    items: list[ConfirmItem]
    plan_id: int | None = None


class ConfirmedEntry(BaseModel):
    ingredient_id: int
    amount_grams: float
    diary_entry_id: int


class ConfirmResponse(BaseModel):
    created: list[ConfirmedEntry]


class IngredientDetail(BaseModel):
    id: int
    name: str
    energy_kcal_100g: float
    protein_100g: float
    carbs_100g: float
    fat_100g: float


class SearchResult(BaseModel):
    id: int
    name: str
    energy_kcal_100g: float
    # Only for /api/recent: the last amount the user logged of this food.
    last_amount_grams: float | None = None
    last_logged: str | None = None


class MacroTotals(BaseModel):
    kcal: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0


class MealItem(BaseModel):
    diary_entry_id: int
    ingredient_id: int
    name: str
    amount_grams: float
    kcal: float


class MealGroup(BaseModel):
    key: str
    label: str
    totals: MacroTotals
    items: list[MealItem]


class TodayResponse(BaseModel):
    date: str
    totals: MacroTotals
    goal: MacroTotals
    meals: list[MealGroup]
    streak_days: int
    user_name: str
