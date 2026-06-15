import asyncio

from app.infra.llm.client import OpenAICompatibleLLMClient
from app.infra.weather.exceptions import WeatherClientError
from app.infra.weather.open_meteo_client import OpenMeteoWeatherClient
from app.prompts.intent_analysis import intent_analysis_prompt
from app.prompts.response_generation import response_generation_prompt
from app.prompts.responses import (
    unsupported_topic_answer,
    weather_clarification,
    weather_unavailable,
)
from app.prompts.system import (
    INTENT_ANALYSIS_SYSTEM_PROMPT,
    RESPONSE_GENERATION_SYSTEM_PROMPT,
    WEATHER_FORMATTING_SYSTEM_PROMPT,
)
from app.prompts.weather_generation import weather_generation_prompt
from app.schemas.intent import (
    IntentAnalysisRequest,
    IntentAnalysisResponse,
    IntentClass,
    IntentSegment,
    ResponseGenerationLLMResponse,
    SegmentedIntentAnalysisLLMResponse,
    SegmentResponse,
)

# Segment analysis produces a list of units, so it needs more room than a single
# structured classification did.
_SEGMENT_ANALYSIS_MAX_TOKENS = 1500
# Per-segment generation keeps the original limit.
_GENERATION_MAX_TOKENS = 500


class IntentAnalysisService:
    def __init__(
        self,
        llm_client: OpenAICompatibleLLMClient,
        weather_client: OpenMeteoWeatherClient,
    ) -> None:
        self._llm_client = llm_client
        self._weather_client = weather_client

    async def analyze(self, payload: IntentAnalysisRequest) -> IntentAnalysisResponse:
        segmented = await self._analyze_intent(payload)
        segments = await self._process_segments(payload, segmented.segments)
        overall = _compute_overall(segmented.segments, segments)
        return IntentAnalysisResponse(
            intent=overall.intent,
            confidence=overall.confidence,
            reasoning=overall.reasoning,
            weather_location=overall.weather_location,
            answer=overall.answer,
            needs_clarification=any(segment.needs_clarification for segment in segments),
            segments=segments,
        )

    async def _analyze_intent(
        self,
        payload: IntentAnalysisRequest,
    ) -> SegmentedIntentAnalysisLLMResponse:
        prompt = intent_analysis_prompt(query=payload.query, history=payload.history)
        return await self._llm_client.complete_structured(
            system_prompt=INTENT_ANALYSIS_SYSTEM_PROMPT,
            user_prompt=prompt,
            text_format=SegmentedIntentAnalysisLLMResponse,
            max_output_tokens=_SEGMENT_ANALYSIS_MAX_TOKENS,
        )

    async def _process_segments(
        self,
        payload: IntentAnalysisRequest,
        llm_segments: list[IntentSegment],
    ) -> list[SegmentResponse]:
        # Segments are independent — process them concurrently so the generation
        # phase takes as long as the slowest segment, not the sum of all.
        results = await asyncio.gather(
            *(self._generate_segment_answer(payload, segment) for segment in llm_segments)
        )
        return [
            SegmentResponse(
                **segment.model_dump(),
                answer=answer,
                needs_clarification=needs_clarification,
            )
            for segment, (answer, needs_clarification) in zip(llm_segments, results, strict=True)
        ]

    async def _generate_segment_answer(
        self,
        payload: IntentAnalysisRequest,
        segment: IntentSegment,
    ) -> tuple[str, bool]:
        if segment.intent == IntentClass.OTHER:
            return unsupported_topic_answer(segment.language), False

        if segment.intent == IntentClass.WEATHER:
            return await self._generate_weather_answer(segment)

        prompt = response_generation_prompt(
            query=segment.text,
            history=payload.history,
            intent_analysis=segment,
            language=segment.language,
        )
        answer_response = await self._llm_client.complete_structured(
            system_prompt=RESPONSE_GENERATION_SYSTEM_PROMPT,
            user_prompt=prompt,
            text_format=ResponseGenerationLLMResponse,
            max_output_tokens=_GENERATION_MAX_TOKENS,
            temperature=0.3,
        )
        return answer_response.answer, False

    async def _generate_weather_answer(
        self,
        segment: IntentSegment,
    ) -> tuple[str, bool]:
        location = segment.weather_location
        if location is None or not location.strip():
            return weather_clarification(segment.language), True

        try:
            current_weather = await self._weather_client.get_current_weather(location.strip())
        except (WeatherClientError, ValueError):
            return weather_unavailable(segment.language, location), True

        place = current_weather.location_name
        if current_weather.country:
            place = f"{place}, {current_weather.country}"
        facts = {
            "condition": current_weather.condition,
            "temperature_c": current_weather.temperature_c,
            "feels_like_c": current_weather.apparent_temperature_c,
            "humidity_percent": current_weather.relative_humidity_percent,
            "wind_speed_kmh": current_weather.wind_speed_kmh,
            "precipitation_mm": current_weather.precipitation_mm,
        }
        prompt = weather_generation_prompt(
            place=place,
            facts=facts,
            language=segment.language,
        )
        answer_response = await self._llm_client.complete_structured(
            system_prompt=WEATHER_FORMATTING_SYSTEM_PROMPT,
            user_prompt=prompt,
            text_format=ResponseGenerationLLMResponse,
            max_output_tokens=_GENERATION_MAX_TOKENS,
            temperature=0.2,
        )
        return answer_response.answer, False


class _Overall:
    """Deterministic aggregate across all segments of a request."""

    __slots__ = ("answer", "confidence", "intent", "reasoning", "weather_location")

    def __init__(
        self,
        *,
        intent: IntentClass,
        confidence: float,
        reasoning: str,
        weather_location: str | None,
        answer: str,
    ) -> None:
        self.intent = intent
        self.confidence = confidence
        self.reasoning = reasoning
        self.weather_location = weather_location
        self.answer = answer


def _compute_overall(
    llm_segments: list[IntentSegment],
    segments: list[SegmentResponse],
) -> _Overall:
    distinct_intents = {segment.intent for segment in llm_segments}
    intent = next(iter(distinct_intents)) if len(distinct_intents) == 1 else IntentClass.MIXED

    confidence = min(segment.confidence for segment in llm_segments)
    reasoning = " | ".join(segment.reasoning for segment in llm_segments)
    answer = "\n\n".join(segment.answer for segment in segments)

    weather_segments = [
        segment for segment in llm_segments if segment.intent == IntentClass.WEATHER
    ]
    weather_location = weather_segments[0].weather_location if len(weather_segments) == 1 else None

    return _Overall(
        intent=intent,
        confidence=confidence,
        reasoning=reasoning,
        weather_location=weather_location,
        answer=answer,
    )
