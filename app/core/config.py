from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Intent LLM Wrapper"
    app_version: str = "0.1.0"
    app_env: str = "local"

    openrouter_api_key: SecretStr = Field(default=SecretStr(""))
    openrouter_base_url: AnyHttpUrl = Field(default="https://openrouter.ai/api/v1")
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_referer: str | None = None
    openrouter_title: str | None = None

    request_timeout_seconds: float = 60.0
    internal_api_base_url: AnyHttpUrl = Field(default="http://127.0.0.1:8000")


@lru_cache
def get_settings() -> Settings:
    return Settings()
