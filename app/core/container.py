from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI

from app.core.config import Settings
from app.infra.llm.openrouter_client import OpenRouterLLMClient
from app.infra.weather.open_meteo_client import OpenMeteoWeatherClient
from app.services.intent_service import IntentAnalysisService


@dataclass(slots=True)
class Container:
    llm_client: OpenRouterLLMClient
    weather_client: OpenMeteoWeatherClient
    intent_service: IntentAnalysisService

    @classmethod
    def from_settings(cls, settings: Settings) -> "Container":
        raw_key = settings.openrouter_api_key.get_secret_value()
        openai_client = AsyncOpenAI(
            api_key=raw_key or "missing-openrouter-api-key",
            base_url=str(settings.openrouter_base_url),
            timeout=settings.request_timeout_seconds,
            default_headers=_build_openrouter_headers(settings),
        )
        llm_client = OpenRouterLLMClient(openai_client, model=settings.openrouter_model)
        weather_client = OpenMeteoWeatherClient(
            httpx.AsyncClient(timeout=settings.request_timeout_seconds)
        )
        return cls(
            llm_client=llm_client,
            weather_client=weather_client,
            intent_service=IntentAnalysisService(
                llm_client=llm_client,
                weather_client=weather_client,
            ),
        )

    async def close(self) -> None:
        await self.llm_client.close()
        await self.weather_client.close()


def _build_openrouter_headers(settings: Settings) -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.openrouter_referer:
        headers["HTTP-Referer"] = settings.openrouter_referer
    if settings.openrouter_title:
        headers["X-OpenRouter-Title"] = settings.openrouter_title
    return headers
