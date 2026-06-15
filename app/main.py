from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import gradio as gr
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router as api_router
from app.core.config import Settings, get_settings
from app.core.container import Container
from app.infra.llm.client import LLMClientError
from app.ui.chat import build_chat_ui


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.container = Container.from_settings(settings)
    yield
    await app.state.container.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": resolved_settings.app_env}

    @app.exception_handler(LLMClientError)
    async def llm_error_handler(_request: Request, exc: LLMClientError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    chat_ui = build_chat_ui(
        api_base_url=str(resolved_settings.internal_api_base_url),
        request_timeout_seconds=resolved_settings.chat_request_timeout_seconds,
    )
    return gr.mount_gradio_app(app, chat_ui, path="/chat")


app = create_app()
