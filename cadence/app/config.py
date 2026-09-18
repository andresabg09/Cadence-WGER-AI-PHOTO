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

    # Behavior
    match_candidate_count: int = 3
    default_nutrition_plan_id: int | None = None


settings = Settings()
