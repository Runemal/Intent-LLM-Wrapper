import json
import logging
from enum import StrEnum
from typing import TypeVar

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)
StructuredResponseT = TypeVar("StructuredResponseT", bound=BaseModel)

# Weak/free models occasionally emit malformed JSON that fails schema parsing.
# Retrying the same request usually succeeds, so we retry parse failures.
_MAX_PARSE_ATTEMPTS = 3


class LLMClientError(RuntimeError):
    pass


class StructuredOutputMode(StrEnum):
    # Provider enforces the JSON schema natively (response_format=json_schema).
    JSON_SCHEMA = "json_schema"
    # Provider only guarantees a JSON object; we embed the schema in the prompt
    # and parse the returned object ourselves.
    JSON_OBJECT = "json_object"


class OpenAICompatibleLLMClient:
    """OpenAI-compatible chat-completions client used for every LLM provider.

    Works with OpenRouter, YandexGPT, Xiaomi MiMo, vLLM, etc. — anything that
    speaks chat.completions. Provider differences (base URL, auth headers, model)
    are baked into the supplied ``AsyncOpenAI`` by the factory; this class only
    owns the structured-output strategy and retry policy.
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        *,
        mode: StructuredOutputMode = StructuredOutputMode.JSON_SCHEMA,
        extra_body: dict[str, object] | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._mode = mode
        self._extra_body = extra_body

    async def complete_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        text_format: type[StructuredResponseT],
        max_output_tokens: int = 500,
        temperature: float = 0.0,
    ) -> StructuredResponseT:
        last_parse_error: Exception | None = None
        for attempt in range(1, _MAX_PARSE_ATTEMPTS + 1):
            try:
                parsed = await self._request_structured(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    text_format=text_format,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                )
            except APIStatusError as exc:
                logger.warning(
                    "LLM provider returned status=%s body=%s",
                    exc.status_code,
                    exc.response.text,
                )
                raise LLMClientError("LLM provider request failed") from exc
            except (APIConnectionError, APITimeoutError) as exc:
                logger.warning("LLM provider connection failed: %r", exc)
                raise LLMClientError("LLM provider request failed") from exc
            except (ValidationError, TypeError) as exc:
                # ValidationError: model emitted JSON that breaks the schema.
                # TypeError: the SDK's parse helper raised it because the provider
                # returned a completion with choices=None (empty/refusal), common
                # with weak/free models. Both are transient output issues — retry.
                last_parse_error = exc
                logger.info(
                    "Structured parse failed (attempt %s/%s), retrying",
                    attempt,
                    _MAX_PARSE_ATTEMPTS,
                )
                continue

            if parsed is not None:
                return parsed

            last_parse_error = None
            logger.info(
                "Empty/unparseable structured response (attempt %s/%s), retrying",
                attempt,
                _MAX_PARSE_ATTEMPTS,
            )

        if last_parse_error is not None:
            raise LLMClientError(
                "LLM provider returned an unparseable structured response"
            ) from last_parse_error
        raise LLMClientError("LLM provider returned an unparseable structured response")

    async def _request_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        text_format: type[StructuredResponseT],
        max_output_tokens: int,
        temperature: float,
    ) -> StructuredResponseT | None:
        if self._mode == StructuredOutputMode.JSON_SCHEMA:
            return await self._request_json_schema(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                text_format=text_format,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
            )
        return await self._request_json_object(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            text_format=text_format,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        )

    async def _request_json_schema(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        text_format: type[StructuredResponseT],
        max_output_tokens: int,
        temperature: float,
    ) -> StructuredResponseT | None:
        response = await self._client.chat.completions.parse(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=text_format,
            max_tokens=max_output_tokens,
            temperature=temperature,
            extra_body=self._extra_body,
        )
        if not response.choices:
            return None
        return response.choices[0].message.parsed

    async def _request_json_object(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        text_format: type[StructuredResponseT],
        max_output_tokens: int,
        temperature: float,
    ) -> StructuredResponseT | None:
        schema = json.dumps(text_format.model_json_schema(), ensure_ascii=False)
        instructed_system_prompt = (
            f"{system_prompt}\n\n"
            "Respond with a single valid JSON object that conforms exactly to the "
            "following JSON Schema. Output ONLY the JSON object — no markdown, no "
            f"commentary, no surrounding text.\n\nJSON Schema:\n{schema}"
        )
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": instructed_system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=max_output_tokens,
            temperature=temperature,
            extra_body=self._extra_body,
        )
        if not response.choices:
            return None
        content = response.choices[0].message.content
        if not content:
            return None
        return text_format.model_validate_json(content)

    async def close(self) -> None:
        await self._client.close()
