from pydantic import BaseModel


class DetectedComponent(BaseModel):
    name: str  # shown to the user (Spanish)
    # Generic English food name used to query/rank against wger's ingredient
    # DB (language 2). Falls back to `name` when the model doesn't provide it.
    search_name: str | None = None
    confidence: float | None = None
    # Portion the model sees on the plate. Only a starting point for the
    # quantity stepper - the user always confirms, calories come from wger.
    estimated_grams: int | None = None
    # Where it is in the photo: [x, y, width, height] as 0-1 fractions.
    box: list[float] | None = None


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
    estimated_grams: int | None = None
    box: list[float] | None = None
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
    # desayuno | almuerzo | merienda | cena - stamps the entries inside that
    # slot's time window (see meals.datetime_for_meal). None = "now".
    meal: str | None = None
    # When the photo was taken (EXIF time for gallery images, "now" for the in-app
    # camera). Entries are stamped on that day, inside the chosen meal's window.
    taken_at: str | None = None


class WgerStatus(BaseModel):
    ok: bool
    detail: str | None = None


class ConfirmedEntry(BaseModel):
    ingredient_id: int
    amount_grams: float
    # wger's diary ids are UUIDs (text) in current versions, ints in older ones.
    diary_entry_id: str


class ConfirmResponse(BaseModel):
    created: list[ConfirmedEntry]
    # Local day the plate was filed under (the photo's day), so the app can open that day.
    date: str | None = None


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
    # wger's diary ids are UUIDs (text) in current versions, ints in older ones.
    diary_entry_id: str
    ingredient_id: int
    name: str
    amount_grams: float
    kcal: float
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    taken_at: str | None = None  # local ISO time of the entry (for the detail sheet)
    note: str | None = None
    has_crop: bool = False  # a stored crop is served at /api/media/crop/{diary_entry_id}
    plate_key: str | None = None  # the plate photo, served at /api/media/plate/{plate_key}
    box: list[float] | None = None


class DiaryUpdate(BaseModel):
    amount_grams: float | None = None
    meal: str | None = None  # moves the entry into that meal's time window, same day


class MealGroup(BaseModel):
    key: str
    label: str
    totals: MacroTotals
    items: list[MealItem]


class TodayResponse(BaseModel):
    date: str
    today: str | None = None  # the user's real today (date above is the day being shown)
    totals: MacroTotals
    goal: MacroTotals
    meals: list[MealGroup]
    streak_days: int
    user_name: str


class NoteUpdate(BaseModel):
    note: str | None = None


class MediaEntry(BaseModel):
    entry_id: str
    crop: str | None = None  # data URL, zoomed square of this ingredient
    photo: int | None = None  # index into MediaUpload.photos
    box: list[float] | None = None


class MediaUpload(BaseModel):
    plate_id: str
    photos: list[str] = []  # data URLs of the plate photo(s)
    items: list[MediaEntry]


class CalendarDay(BaseModel):
    date: str
    count: int  # diary entries that day
    streak: int  # consecutive logged days ending on this one (1 = a new streak starts)


class CalendarResponse(BaseModel):
    month: str  # YYYY-MM
    today: str
    days: list[CalendarDay]
