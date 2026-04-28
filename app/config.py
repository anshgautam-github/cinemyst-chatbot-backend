from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object loaded from environment variables and local `.env`."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")

    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_key: str = Field(alias="SUPABASE_KEY")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")

    default_results_limit: int = Field(default=5, alias="DEFAULT_RESULTS_LIMIT")
    mentor_results_limit: int = Field(default=6, alias="MENTOR_RESULTS_LIMIT")
    job_results_limit: int = Field(default=6, alias="JOB_RESULTS_LIMIT")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache settings so every import path reads the same resolved configuration."""
    return Settings()
