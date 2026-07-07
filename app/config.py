from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEPRECATED_GROQ_MODEL_ALIASES = {
    "llama3-70b-8192": "llama-3.3-70b-versatile",
    "llama3-8b-8192": "llama-3.1-8b-instant",
}


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

    groq_api_key: str = Field(alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")

    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_key: str = Field(alias="SUPABASE_KEY")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")

    default_results_limit: int = Field(default=5, alias="DEFAULT_RESULTS_LIMIT")
    mentor_results_limit: int = Field(default=6, alias="MENTOR_RESULTS_LIMIT")
    job_results_limit: int = Field(default=6, alias="JOB_RESULTS_LIMIT")

    @model_validator(mode="after")
    def normalize_groq_model(self) -> "Settings":
        """Keep older deployment env values working after Groq model migrations."""
        normalized_model = DEPRECATED_GROQ_MODEL_ALIASES.get(self.groq_model, self.groq_model)
        if normalized_model != self.groq_model:
            self.groq_model = normalized_model
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache settings so every import path reads the same resolved configuration."""
    return Settings()
