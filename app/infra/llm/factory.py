from openai import AsyncOpenAI

from app.core.config import Settings
from app.infra.llm.client import OpenAICompatibleLLMClient, StructuredOutputMode


def build_llm_client(settings: Settings) -> OpenAICompatibleLLMClient:
    """Build the configured LLM client for the active provider.

    All providers speak the OpenAI-compatible chat-completions API, so we return
    the same client class everywhere — only base URL, auth headers, model, and the
    structured-output strategy differ.
    """
    match settings.llm_provider:
        case "openrouter":
            return _build_openrouter(settings)
        case "yandex":
            return _build_yandex(settings)
        case "mimo":
            return _build_mimo(settings)


def _build_openrouter(settings: Settings) -> OpenAICompatibleLLMClient:
    api_key = settings.openrouter_api_key.get_secret_value() or "missing-openrouter-api-key"
    openai_client = AsyncOpenAI(
        api_key=api_key,
        base_url=str(settings.openrouter_base_url),
        timeout=settings.request_timeout_seconds,
        default_headers=_openrouter_headers(settings),
    )
    extra_body: dict[str, object] | None = None
    if settings.openrouter_require_parameters:
        extra_body = {"provider": {"require_parameters": True}}
    return OpenAICompatibleLLMClient(
        openai_client,
        model=settings.openrouter_model,
        mode=StructuredOutputMode.JSON_SCHEMA,
        extra_body=extra_body,
    )


def _build_yandex(settings: Settings) -> OpenAICompatibleLLMClient:
    api_key = settings.yandex_api_key.get_secret_value() or "missing-yandex-api-key"
    openai_client = AsyncOpenAI(
        # Pass a placeholder so the SDK does not refuse to build; the real
        # auth header is set explicitly below and overrides the default Bearer.
        api_key=api_key,
        base_url=str(settings.yandex_base_url),
        timeout=settings.request_timeout_seconds,
        default_headers={
            "Authorization": f"Api-Key {api_key}",
            "x-folder-id": settings.yandex_folder_id,
        },
    )
    return OpenAICompatibleLLMClient(
        openai_client,
        model=_yandex_model_uri(settings.yandex_model, settings.yandex_folder_id),
        mode=StructuredOutputMode.JSON_OBJECT,
    )


def _yandex_model_uri(model: str, folder_id: str) -> str:
    """Yandex's OpenAI-compatible endpoint needs a full model URI
    (``gpt://<folder>/<model>/<version>``), not a bare name — a bare name fails
    with "Failed to parse model URI". Fold the folder in automatically unless the
    caller already supplied a full ``gpt://``/``cls://``/``ds://`` URI.
    """
    if model.startswith(("gpt://", "cls://", "ds://")):
        return model
    return f"gpt://{folder_id}/{model.lstrip('/')}"


def _build_mimo(settings: Settings) -> OpenAICompatibleLLMClient:
    api_key = settings.mimo_api_key.get_secret_value() or "missing-mimo-api-key"
    openai_client = AsyncOpenAI(
        api_key=api_key,
        base_url=str(settings.mimo_base_url),
        timeout=settings.request_timeout_seconds,
    )
    return OpenAICompatibleLLMClient(
        openai_client,
        model=settings.mimo_model,
        mode=StructuredOutputMode.JSON_OBJECT,
    )


def _openrouter_headers(settings: Settings) -> dict[str, str]:
    headers: dict[str, str] = {}
    if settings.openrouter_referer:
        headers["HTTP-Referer"] = settings.openrouter_referer
    if settings.openrouter_title:
        headers["X-OpenRouter-Title"] = settings.openrouter_title
    return headers
