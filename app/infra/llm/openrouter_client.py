import logging
from typing import TypeVar

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)
StructuredResponseT = TypeVar("StructuredResponseT", bound=BaseModel)


class LLMClientError(RuntimeError):
    pass


class OpenRouterLLMClient:
    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def complete_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        text_format: type[StructuredResponseT],
        max_output_tokens: int = 500,
        temperature: float = 0.0,
    ) -> StructuredResponseT:
        try:
            response = await self._client.responses.parse(
                model=self._model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                text_format=text_format,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                extra_body={"provider": {"require_parameters": True}},
            )
        except APIStatusError as exc:
            logger.warning(
                "OpenRouter returned status=%s body=%s",
                exc.status_code,
                exc.response.text,
            )
            raise LLMClientError("OpenRouter request failed") from exc
        except (APIConnectionError, APITimeoutError) as exc:
            logger.warning("OpenRouter connection failed: %r", exc)
            raise LLMClientError("OpenRouter request failed") from exc

        parsed = response.output_parsed
        if parsed is None:
            raise LLMClientError("OpenRouter returned an unparseable structured response")

        return parsed

    async def close(self) -> None:
        await self._client.close()
