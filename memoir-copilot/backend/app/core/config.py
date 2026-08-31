from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    app_name: str = "memoir-copilot"
    secret_key: str = "change-me-dev-secret-key-at-least-32-chars"
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    database_url: str = "postgresql+asyncpg://memoir:memoir@localhost:5432/memoir"
    database_url_sync: str = "postgresql+psycopg://memoir:memoir@localhost:5432/memoir"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = "ChangeMeAdmin123!"

    cos_secret_id: str = ""
    cos_secret_key: str = ""
    cos_region: str = "ap-guangzhou"
    cos_bucket: str = ""

    tencent_asr_secret_id: str = ""
    tencent_asr_secret_key: str = ""
    tencent_asr_app_id: str = ""

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    window_analyzer_model: str = "gpt-5.6-luna"
    global_analyzer_model: str = "gpt-5.6-terra"
    final_review_model: str = "gpt-5.6-sol"
    transcript_cleaner_model: str = "gpt-5.6-terra"
    third_opinion_asr_model: str = "gpt-4o-transcribe"
    watch_asr_model: str = "gpt-transcribe"

    llm_soft_limit_usd: float = 2.0
    llm_hard_limit_usd: float = 5.0

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,tauri://localhost"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
