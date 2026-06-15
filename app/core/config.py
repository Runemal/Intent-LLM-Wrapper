from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProvider = Literal["openrouter", "yandex", "mimo"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Intent LLM Wrapper"
    app_version: str = "0.1.0"
    app_env: str = "local"

    # Active LLM provider. Switch by setting LLM_PROVIDER and restarting.
    llm_provider: LLMProvider = "openrouter"

    openrouter_api_key: SecretStr = Field(default=SecretStr(""))
    openrouter_base_url: AnyHttpUrl = Field(default="https://openrouter.ai/api/v1")
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_referer: str | None = None
    openrouter_title: str | None = None
    # Restrict routing to providers that honor all passed params. Some free models
    # have no provider satisfying this, so it defaults off. Re-enable for models
    # where you want strict parameter honoring.
    openrouter_require_parameters: bool = False

    # Yandex Cloud (YandexGPT), OpenAI-compatible chat completions endpoint.
    # Auth uses "Api-Key" + x-folder-id (not the SDK default Bearer).
    yandex_api_key: SecretStr = Field(default=SecretStr(""))
    yandex_folder_id: str = ""
    yandex_model: str = "yandexgpt"
    yandex_base_url: AnyHttpUrl = Field(default="https://ai.api.cloud.yandex.net/v1")

    # Xiaomi MiMo, OpenAI-compatible endpoint.
    mimo_api_key: SecretStr = Field(default=SecretStr(""))
    mimo_model: str = "xiaomi/MiMo-7B-RL"
    mimo_base_url: AnyHttpUrl = Field(default="https://api.xiaomimimo.com/v1")

    # Per-provider HTTP timeout (backend -> LLM).
    request_timeout_seconds: float = 60.0
    # UI -> backend timeout. Composite requests fan out into several LLM calls,
    # so this is larger than the single-call timeout.
    chat_request_timeout_seconds: float = 120.0
    internal_api_base_url: AnyHttpUrl = Field(default="http://127.0.0.1:8000")


@lru_cache
def get_settings() -> Settings:
    return Settings()
