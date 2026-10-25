from pydantic import BaseModel, Field, model_validator

from .foodunits import is_liquid


class _Liquid(BaseModel):
    """Anything with a `name` that can be measured in millilitres. Unless it is said outright, it is guessed from the name."""
    liquid: bool = False

    @model_validator(mode="after")
    def _guess_liquid(self):
        if "liquid" not in self.model_fields_set:
            self.liquid = is_liquid(getattr(self, "name", ""))
        return self


class DetectedComponent(BaseModel):
    name: str  # shown to the user (Spanish)
    # Generic English food name used to query/rank against wger's ingredient
    # DB (language 2). Falls back to `name` when the model doesn't provide it.
    search_name: str | None = None
    # Other short English names for the same food ("chicken soup" -> "chicken noodle soup"):
    # wger's catalog often names it differently, so each is searched too.
    search_alternatives: list[str] = []
    # Plain water in the picture (a glass, a bottle): millilitres to add to the water bar, not a food to log.
    water_ml: int | None = None
    confidence: float | None = None
    # Portion the model sees on the plate. Only a starting point for the
    # quantity stepper - the user always confirms, calories come from wger.
    estimated_grams: int | None = None
    # Where it is in the photo: [x, y, width, height] as 0-1 fractions.
    box: list[float] | None = None
    # A soup or a drink: it is measured in millilitres, not grams (the model says so; the name is the fallback).
    liquid: bool | None = None


class IngredientCandidate(_Liquid):
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
    liquid: bool = False
    confidence: float | None = None
    estimated_grams: int | None = None
    box: list[float] | None = None
    candidates: list[IngredientCandidate]


class AnalyzeResponse(BaseModel):
    components: list[ComponentMatch]
    water_ml: int = 0  # plain water seen in the photo or heard in the audio: goes to the water bar


class ConfirmItem(BaseModel):
    ingredient_id: int
    amount_grams: float
    detected_name: str | None = None
    liquid: bool | None = None  # measured in millilitres (what the confirm screen showed); None = decide from the name


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
    # False for an old photo: it fills that day's diary but does not count for the streak.
    counts_for_streak: bool = True


class IngredientDetail(BaseModel):
    id: int
    name: str
    energy_kcal_100g: float
    protein_100g: float
    carbs_100g: float
    fat_100g: float


class SearchResult(_Liquid):
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


class MealItem(_Liquid):
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
    # Extra nutrients of this portion (None = wger does not know them); they feed the nutrition score.
    fibre_g: float | None = None
    sugar_g: float | None = None
    sat_fat_g: float | None = None


class DiaryUpdate(BaseModel):
    amount_grams: float | None = None
    meal: str | None = None  # moves the entry into that meal's time window, same day


class ScorePart(BaseModel):
    key: str
    label: str
    points: float
    max: int
    note: str


class ScoreOut(BaseModel):
    points: int
    label: str  # Excelente | Buena | Regular | Mejorable
    parts: list[ScorePart] = []
    partial: list[str] = []  # criteria that could not be judged for lack of data


class LevelOut(BaseModel):
    value_g: float
    target_g: float
    pct: int
    label: str  # bajo | medio | alto


class LevelsOut(BaseModel):
    protein: LevelOut | None = None
    fibre: LevelOut | None = None  # None: no food has fibre data


class AwardBrief(BaseModel):
    key: str
    title: str
    art: str


class MealGroup(BaseModel):
    key: str
    label: str
    totals: MacroTotals
    items: list[MealItem]
    score: ScoreOut | None = None
    levels: LevelsOut | None = None
    awards: list[AwardBrief] = []


class WorkoutOut(BaseModel):
    id: int
    day: str
    kind: str
    minutes: int
    kcal: float  # estimated burn
    note: str | None = None
    at: str | None = None


class BurnOut(BaseModel):
    over_kcal: int  # eaten above the goal
    worked_kcal: int  # estimated burn of the day's workouts
    kcal: int  # still to burn: what is over minus what the workouts already burned
    minutes: int  # a light jog (about 7 MET) that would burn it


class TodayResponse(BaseModel):
    workouts: list[WorkoutOut] = []
    date: str
    today: str | None = None  # the user's real today (date above is the day being shown)
    totals: MacroTotals
    goal: MacroTotals
    meals: list[MealGroup]
    streak_days: int
    user_name: str
    water_ml: int = 0
    score: ScoreOut | None = None  # the day: its meals' scores averaged by calories
    levels: LevelsOut | None = None
    water_goal_ml: int = 2000
    water_goal_auto: bool = True
    maintenance_kcal: int | None = None  # what the body spends in a day (None while the profile is incomplete)
    goal_change_lb_month: float | None = None  # what the scale does a month if every day is like the goal (negative = loses)
    burn: "BurnOut | None" = None
    awards_new: list[AwardBrief] = []  # awards earned by this very request (today only): the app celebrates them


class WaterAdd(BaseModel):
    date: str
    add_ml: int = Field(ge=-10000, le=10000)


class WaterImport(BaseModel):
    days: dict[str, int]


class WaterOut(BaseModel):
    date: str
    ml: int
    goal_ml: int = 2000


class WaterGoalIn(BaseModel):
    ml: int | None = Field(default=None, ge=500, le=8000)  # None = automatic (from the person's weight)
    step_ml: int | None = None  # size of the person's glass (250 ml or 237 ml = 8 oz): the goal is whole glasses


class BulkDelete(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=40)


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
    # Consecutive same-day-logged days ending on this one (1 = a new streak starts).
    # 0 = the day has entries but they were all added later (old photos): no flame.
    streak: int
    kcal: int = 0  # calories eaten that day (the ring around the day in the week strip)


class CalendarResponse(BaseModel):
    month: str  # YYYY-MM
    today: str
    goal_kcal: float = 0
    days: list[CalendarDay]


class StreakRun(BaseModel):
    start: str
    end: str
    length: int


class StreaksResponse(BaseModel):
    today: str
    current: StreakRun | None = None  # the streak still alive (ends today or yesterday)
    current_days: list[str] = []  # every day of it, oldest first
    logged_today: bool = False
    best: int = 0
    previous: list[StreakRun] = []  # earlier streaks, newest first


class FoodIn(BaseModel):
    """A food the person makes themself, per 100 g (or from a product label)."""
    name: str
    kcal: float
    protein: float = 0
    carbs: float = 0
    fat: float = 0
    fibre: float | None = None  # optional; it only improves the nutrition score
    barcode: str | None = None
    liquid: bool | None = None  # a drink or soup: its amount is shown in millilitres (None = guess from the name)


class BarcodeResult(BaseModel):
    found: bool
    source: str | None = None  # own | wger | off
    id: int | None = None  # usable ingredient id when it already exists (own/wger)
    name: str | None = None
    kcal: float | None = None
    protein: float | None = None
    carbs: float | None = None
    fat: float | None = None
    fibre: float | None = None
    barcode: str
    # When nothing was found: not_listed (the databases answered: not there) | no_nutrition (listed without values, `name` is its name) | unreachable
    reason: str | None = None


class WorkoutIn(BaseModel):
    kind: str
    minutes: int
    day: str | None = None  # AAAA-MM-DD, default today
    note: str | None = None
    at: str | None = None  # HH:MM, local time of the workout (default now)


class WorkoutUpdate(BaseModel):
    kind: str | None = None
    minutes: int | None = None
    note: str | None = None
    at: str | None = None


class ActivityOut(BaseModel):
    key: str
    label: str
    group: str
    icon: str
    met: float
    kcal_per_min: float  # for this person's weight
    words: str = ""


class ActivitiesOut(BaseModel):
    weight_kg: float
    weight_known: bool
    activities: list[ActivityOut]



class ProgressDay(BaseModel):
    date: str
    kcal: float = 0
    logged: bool = False  # something registered that day
    counts: bool = False  # and registered that same day (streak)


class Achievement(BaseModel):
    key: str
    title: str
    hint: str
    icon: str
    unlocked: bool


class WeightPoint(BaseModel):
    day: str
    kg: float


class PaceOut(BaseModel):
    """What the last days of eating mean for the scale: an estimate from calories, not from the scale."""
    days: int  # days with something registered inside the last 7 (a day without records is not counted as zero)
    avg_kcal: int
    goal_kcal: int
    maintenance_kcal: int
    change_lb_month: float  # negative = the weight goes down at this rhythm


class ProgressResponse(BaseModel):
    pace: PaceOut | None = None
    today: str
    streak_current: int
    streak_best: int
    logged_today: bool
    goal_kcal: float
    days: list[ProgressDay]  # last 28 days, oldest first
    weights: list[WeightPoint]
    weight_change_30d: float | None = None
    target_weight_kg: float | None = None
    achievements: list[Achievement]
    unlocked: int


class HistoryDay(BaseModel):
    date: str
    kcal: float
    count: int
    thumbs: list[str]  # entry ids that have a crop
    more: int = 0


class HistoryResponse(BaseModel):
    goal_kcal: float
    days: list[HistoryDay]  # newest first, only days with something
    next_before: str | None = None  # ask again with this to go further back


class AwardOut(BaseModel):
    key: str
    title: str
    hint: str
    art: str
    category: str  # comida | constancia | agua | movimiento
    kind: str  # milestone | meal
    unlocked: bool
    value: int = 0  # progress towards `target`
    target: int = 1
    count: int = 0  # times earned (meal awards can be earned again and again)
    last_day: str | None = None


class AwardsResponse(BaseModel):
    unlocked: int
    total: int
    awards: list[AwardOut]
    new: list[AwardBrief] = []


class ShopItemOut(BaseModel):
    key: str
    title: str
    hint: str
    price: int
    slot: str  # theme | frame
    owned: bool
    equipped: bool


class ChallengeOut(BaseModel):
    key: str
    period: str  # day | week
    title: str
    hint: str
    art: str
    now: int
    total: int
    reward: int
    state: str  # todo | ready | claimed
    note: str | None = None


class ChallengesResponse(BaseModel):
    coins: int
    daily: list[ChallengeOut]
    weekly: list[ChallengeOut]
    hours_left: int
    days_left: int
    claimable: int
    shop: list[ShopItemOut]


class ClaimIn(BaseModel):
    key: str


class ClaimOut(BaseModel):
    coins: int
    amount: int


class ShopBuyIn(BaseModel):
    item: str


class ShopEquipIn(BaseModel):
    slot: str
    item: str | None = None


class FavoriteItem(_Liquid):
    ingredient_id: int
    name: str
    grams: float


class FavoriteOut(BaseModel):
    key: str
    meal: str
    times: int  # how many times this same set of foods was logged in the last two months
    last_day: str
    kcal: float
    protein_g: float
    photo: str | None = None  # the person's own photo of it (path under /api/media)
    items: list[FavoriteItem]


class IdeaOut(BaseModel):
    name: str
    tag: str | None = None
    kcal: float
    protein_g: float
    items: list[FavoriteItem]  # already matched to foods in wger (or the person's own): ready to log


class IdeasResponse(BaseModel):
    meal: str
    kcal_left: int
    protein_left: int
    ideas: list[IdeaOut]
    done: bool = False  # the day's goal is already reached: nothing to complete
