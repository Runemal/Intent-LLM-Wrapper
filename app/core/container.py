from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.infra.llm.client import OpenAICompatibleLLMClient
from app.infra.llm.factory import build_llm_client
from app.infra.weather.open_meteo_client import OpenMeteoWeatherClient
from app.services.intent_service import IntentAnalysisService


@dataclass(slots=True)
class Container:
    llm_client: OpenAICompatibleLLMClient
    weather_client: OpenMeteoWeatherClient
    intent_service: IntentAnalysisService

    @classmethod
    def from_settings(cls, settings: Settings) -> "Container":
        llm_client = build_llm_client(settings)
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
