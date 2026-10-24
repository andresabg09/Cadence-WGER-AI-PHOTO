from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Gemini Vision
    gemini_api_key: str = ""
    # Verify the exact current model id in Google's docs before deploying;
    # Gemini model names are periodically retired/renamed.
    gemini_model: str = "gemini-flash-lite-latest"

    # Wger REST API
    wger_base_url: str = "https://crm-wger.cjauws.easypanel.host"
    wger_api_token: str = ""
    wger_language_id: int = 2  # 2 = English in wger's default fixtures
    wger_language_code: str = "en"  # same language, as ISO code (new search endpoint)

    # Behavior
    user_name: str = "Andrés"  # shown in the dashboard greeting
    # IANA zone used to decide "today" and which meal slot an entry falls in.
    # Without this the container's clock (UTC) is used, which shifts every
    # entry by the viewer's offset (e.g. a 7am breakfast in Panama lands in
    # "almuerzo", and anything after 7pm counts as tomorrow).
    timezone: str = "America/Panama"
    match_candidate_count: int = 3
    # How many wger matches to fetch before re-ranking them locally (wger's own
    # order is not by similarity, so the best match may not be in the first few).
    search_fetch_limit: int = 100
    default_nutrition_plan_id: int | None = None

    # Meal-slot time windows (24h, local server time) - used to bucket wger
    # diary entries into desayuno/almuerzo/merienda/cena since wger itself
    # doesn't tag entries with a meal slot. Adjust to taste.
    breakfast_start_hour: int = 5
    lunch_start_hour: int = 11
    snack_start_hour: int = 15
    dinner_start_hour: int = 18
    dinner_end_hour: int = 23

    # Fallback daily goals shown on the dashboard when the active wger
    # nutrition plan has no goal_* values set.
    fallback_goal_kcal: float = 2500
    fallback_goal_protein_g: float = 175
    fallback_goal_carbs_g: float = 250
    fallback_goal_fat_g: float = 70


settings = Settings()
