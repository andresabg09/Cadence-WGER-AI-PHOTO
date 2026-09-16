from pydantic import BaseModel


class DetectedComponent(BaseModel):
    name: str
    confidence: float | None = None


class IngredientCandidate(BaseModel):
    id: int
    name: str
    image: str | None = None
    score: float


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
