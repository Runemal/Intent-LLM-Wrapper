# Intent LLM Wrapper

FastAPI service for intent classification via OpenRouter using the OpenAI-compatible API.

## Features

- `POST /api/v1/message` analyzes the current user request with dialogue history.
- `GET /health` returns service health.
- `GET /chat` serves a Gradio chat UI.
- Prompt builder lives in `app/prompts/intent_analysis.py`.
- Structured output is parsed through the OpenAI SDK with a Pydantic schema.
- Intent classes are `weather`, `technical_question`, `small_talk`, and `other`.
- Weather requests call Open-Meteo geocoding and forecast APIs.

## Request Pipeline

Every user message is handled in a deterministic sequence:

1. Intent analysis LLM call returns structured data only:
   `intent`, `confidence`, `reasoning`, and `weather_location`.
2. The service applies intent policy:
   - `weather`: call Open-Meteo using `weather_location`.
   - `technical_question` and `small_talk`: make a second LLM call to generate the final answer.
   - `other`: return a fixed policy response without a second generation call.
3. The API returns the final user-facing `answer` plus intent metadata.

Unsupported `other` requests always return:

```text
I can tell you about weather, technology, and keep up a little conversation. I do not discuss other topics.
```

## Local Run

```bash
cp .env.example .env
# fill OPENROUTER_API_KEY
uv sync
uv run uvicorn app.main:app --reload
```

API: `http://localhost:8000`
Chat UI: `http://localhost:8000/chat`

## Docker

```bash
cp .env.example .env
docker compose up --build
```

## Example Request

```bash
curl -X POST http://localhost:8000/api/v1/message \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What is the weather in Warsaw?",
    "history": []
  }'
```
