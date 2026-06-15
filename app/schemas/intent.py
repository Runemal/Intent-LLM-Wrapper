from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DialogRole = Literal["system", "user", "assistant"]


class IntentClass(StrEnum):
    WEATHER = "weather"
    TECHNICAL_QUESTION = "technical_question"
    SMALL_TALK = "small_talk"
    OTHER = "other"
    MIXED = "mixed"


class DialogMessage(BaseModel):
    role: DialogRole
    content: str = Field(min_length=1, max_length=10_000)


class IntentAnalysisRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10_000, description="Current user request.")
    history: list[DialogMessage] = Field(default_factory=list, max_length=50)


class IntentSegment(BaseModel):
    """One semantic unit of a user request, classified independently."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        min_length=1,
        max_length=10_000,
        description="The verbatim text of this semantic unit.",
    )
    intent: IntentClass = Field(
        description=(
            "Class of this unit only. Use weather, technical_question, small_talk, "
            "or other. Never use mixed at the segment level."
        ),
    )
    language: str = Field(
        description=(
            "ISO 639-1 code of the language the segment text is written in "
            "(e.g. en, ru, fr, de)."
        ),
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Classification confidence for this unit, from 0 to 1.",
    )
    reasoning: str = Field(
        min_length=1,
        max_length=5_000,
        description="Brief explanation of why this unit got this intent.",
    )
    weather_location: str | None = Field(
        description=(
            "Location to use for weather lookup. Set this only for a weather unit when "
            "the user specified a location; otherwise set null."
        ),
    )


class SegmentedIntentAnalysisLLMResponse(BaseModel):
    """Structured output of the intent analysis step: a request split into units."""

    model_config = ConfigDict(extra="forbid")

    segments: list[IntentSegment] = Field(
        min_length=1,
        max_length=5,
        description=(
            "Independent semantic units of the current request, in order. A request "
            "with a single intent must produce exactly one segment."
        ),
    )


class ResponseGenerationLLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(
        min_length=1,
        max_length=5_000,
        description="Final user-facing answer in the user's language.",
    )


class SegmentResponse(IntentSegment):
    """One segment enriched with the generated answer for the API response."""

    answer: str = Field(
        min_length=1,
        max_length=5_000,
        description="Final user-facing answer for this segment in the user's language.",
    )
    needs_clarification: bool = Field(
        description="Whether the service should ask a clarifying question for this segment.",
    )


class IntentAnalysisResponse(BaseModel):
    """Top-level API response with both the overall intent and per-segment detail."""

    intent: IntentClass = Field(
        description="Overall intent across all segments. 'mixed' when segments disagree.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence: the minimum across all segments.",
    )
    reasoning: str = Field(
        min_length=1,
        max_length=30_000,
        description="Combined reasoning across all segments.",
    )
    weather_location: str | None = Field(
        description="Overall weather location, or null if there is no single weather unit.",
    )
    answer: str = Field(
        min_length=1,
        max_length=30_000,
        description="Final user-facing answer in the user's language: all segment answers joined.",
    )
    needs_clarification: bool = Field(
        description="True if any segment requires a clarifying question.",
    )
    segments: list[SegmentResponse] = Field(
        min_length=1,
        description="Per-segment classification and answers.",
    )
