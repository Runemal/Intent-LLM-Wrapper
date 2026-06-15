from app.infra.llm.openrouter_client import OpenRouterLLMClient
from app.infra.weather.exceptions import WeatherClientError
from app.infra.weather.models import CurrentWeather
from app.infra.weather.open_meteo_client import OpenMeteoWeatherClient
from app.prompts.intent_analysis import intent_analysis_prompt
from app.prompts.response_generation import response_generation_prompt
from app.prompts.responses import UNSUPPORTED_TOPIC_ANSWER
from app.prompts.system import INTENT_ANALYSIS_SYSTEM_PROMPT, RESPONSE_GENERATION_SYSTEM_PROMPT
from app.schemas.intent import (
    IntentAnalysisLLMResponse,
    IntentAnalysisRequest,
    IntentAnalysisResponse,
    IntentClass,
    ResponseGenerationLLMResponse,
)


class IntentAnalysisService:
    def __init__(
        self,
        llm_client: OpenRouterLLMClient,
        weather_client: OpenMeteoWeatherClient,
    ) -> None:
        self._llm_client = llm_client
        self._weather_client = weather_client

    async def analyze(self, payload: IntentAnalysisRequest) -> IntentAnalysisResponse:
        intent_analysis = await self._analyze_intent(payload)
        answer, needs_clarification = await self._generate_answer(payload, intent_analysis)
        return IntentAnalysisResponse(
            **intent_analysis.model_dump(),
            answer=answer,
            needs_clarification=needs_clarification,
        )

    async def _analyze_intent(
        self,
        payload: IntentAnalysisRequest,
    ) -> IntentAnalysisLLMResponse:
        prompt = intent_analysis_prompt(query=payload.query, history=payload.history)
        return await self._llm_client.complete_structured(
            system_prompt=INTENT_ANALYSIS_SYSTEM_PROMPT,
            user_prompt=prompt,
            text_format=IntentAnalysisLLMResponse,
        )

    async def _generate_answer(
        self,
        payload: IntentAnalysisRequest,
        intent_analysis: IntentAnalysisLLMResponse,
    ) -> tuple[str, bool]:
        if intent_analysis.intent == IntentClass.OTHER:
            return UNSUPPORTED_TOPIC_ANSWER, False

        if intent_analysis.intent == IntentClass.WEATHER:
            return await self._generate_weather_answer(intent_analysis)

        prompt = response_generation_prompt(
            query=payload.query,
            history=payload.history,
            intent_analysis=intent_analysis,
        )
        answer_response = await self._llm_client.complete_structured(
            system_prompt=RESPONSE_GENERATION_SYSTEM_PROMPT,
            user_prompt=prompt,
            text_format=ResponseGenerationLLMResponse,
            temperature=0.3,
        )
        return answer_response.answer, False

    async def _generate_weather_answer(
        self,
        intent_analysis: IntentAnalysisLLMResponse,
    ) -> tuple[str, bool]:
        location = intent_analysis.weather_location
        if location is None or not location.strip():
            return "Which location should I check the weather for?", True

        try:
            current_weather = await self._weather_client.get_current_weather(location.strip())
        except (WeatherClientError, ValueError):
            return f"I could not retrieve weather for {location}. Try another city.", True

        return _format_weather_answer(current_weather), False


def _format_weather_answer(weather: CurrentWeather) -> str:
    place = weather.location_name
    if weather.country:
        place = f"{place}, {weather.country}"

    details = [
        f"The current weather in {place} is {weather.condition}.",
        f"Temperature: {weather.temperature_c:.1f} C.",
    ]
    if weather.apparent_temperature_c is not None:
        details.append(f"Feels like: {weather.apparent_temperature_c:.1f} C.")
    if weather.relative_humidity_percent is not None:
        details.append(f"Humidity: {weather.relative_humidity_percent}%.")
    if weather.wind_speed_kmh is not None:
        details.append(f"Wind: {weather.wind_speed_kmh:.1f} km/h.")
    if weather.precipitation_mm is not None:
        details.append(f"Precipitation: {weather.precipitation_mm:.1f} mm.")

    return " ".join(details)
