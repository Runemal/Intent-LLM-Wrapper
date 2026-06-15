# Intent LLM Wrapper

FastAPI service that splits a user request into semantic units, classifies each, and
answers per a strict intent policy — in the user's language. LLM calls go through one
of three OpenAI-compatible providers (OpenRouter / Yandex Cloud / Xiaomi MiMo).
Weather uses Open-Meteo. A Gradio chat UI is served at `/chat`.

> Полная техническая документация: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
> Для получения $2 на баланс MiMo воспользуйтесь промокодом Y95BZJ при регистрации https://platform.xiaomimimo.com?ref=Y95BZJ


## Features

- `POST /api/v1/message` analyzes the current request with dialogue history and returns
  per-segment classification plus the final answer.
- **Segmentation:** a multi-intent request is split into 1–5 semantic units; each is
  classified independently, and an overall intent is derived (`mixed` when they differ).
- **Multi-provider LLM:** select `openrouter` / `yandex` / `mimo` via `LLM_PROVIDER`.
- **Multilingual:** answers, weather descriptions, and refusals are produced in the
  user's language. Cities are recognized in any language/script and geocoded
  (Москва→Moscow, Warszawa→Warsaw). Multiple cities and descriptive references
  ("capital of Zimbabwe"→Harare) are supported.
- Intent classes (per segment): `weather`, `technical_question`, `small_talk`, `other`;
  overall may also be `mixed`. Humor→`small_talk`, math/arithmetic→`technical_question`.
- `GET /health` returns service health.
- `GET /chat` serves a Gradio chat UI.

## Request Pipeline

1. **Intent analysis** (one LLM call) returns structured segments: each has `text`,
   `intent`, `language`, `confidence`, `reasoning`, `weather_location`.
2. **Per-segment policy** (segments processed in parallel):
   - `weather`: resolve/normalize the location → Open-Meteo (geocoding + forecast) →
     LLM-formatted localized description. A separate segment is created per requested city.
   - `technical_question` / `small_talk`: a second LLM call generates the answer in the
     user's language.
   - `other`: a localized fixed refusal (no LLM — safe for adversarial content).
3. **Overall** is computed deterministically (intent = unanimous class or `mixed`,
   confidence = min across segments) and the API returns the joined `answer` plus
   per-segment detail.

Unsupported (`other`) requests return a localized refusal, e.g. (English):
`I can tell you about weather, technology, and keep up a little conversation. I do not discuss other topics.`

## Local Run

```bash
cp .env.example .env
# set LLM_PROVIDER and the matching provider key (e.g. OPENROUTER_API_KEY)
uv sync
uv run uvicorn app.main:app --reload
```

API: `http://localhost:8000` · Chat UI: `http://localhost:8000/chat`

## Docker

```bash
cp .env.example .env   # set LLM_PROVIDER + provider key
docker compose up --build
```

Switching provider or credentials only needs `docker compose up -d` (no rebuild);
rebuild (`--build`) is required when code changes.

## Example Request

```bash
curl -X POST http://localhost:8000/api/v1/message \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Какая погода в Москве и столице Японии?",
    "history": []
  }'
```

Returns `intent`, `confidence`, `answer` (localized, weather for both cities), and a
`segments` array with per-unit classification.
