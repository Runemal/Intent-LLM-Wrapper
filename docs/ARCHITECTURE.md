# Intent LLM Wrapper — Техническая документация

> Версия документа: 2.0 · дата: 2026-06-15
> Документ описывает архитектуру, потоки данных и связи между компонентами проекта.

## 1. Назначение проекта

**Intent LLM Wrapper** — FastAPI-сервис, который сегментирует запрос пользователя на
смысловые единицы, классифицирует каждую и формирует ответ по строгой политике, на
языке пользователя:

- `weather` — запрос погоды → **Open-Meteo** (геокодинг + прогноз), затем локализованное
  описание через LLM. Поддерживает несколько городов в одном запросе и разрешает косвенные
  описания («столица Зимбабве»→Harare).
- `technical_question` — технический вопрос (включая математику) → ответ через LLM.
- `small_talk` — беседа/юмор/приветствия → ответ через LLM.
- `other` — неподдерживаемая/враждебная тема → локализованная заглушка **без** LLM.

Общее намерение (overall) вычисляется детерминированно из сегментов. LLM-вызовы идут через
один из трёх провайдеров — **OpenRouter**, **Yandex Cloud (YandexGPT)**, **Xiaomi MiMo** —
выбираемых настройкой `LLM_PROVIDER`. Сервис также отдаёт веб-чат на **Gradio** (`/chat`).

## 2. Технологический стек

| Слой | Технология |
|------|-----------|
| Web-фреймворк | FastAPI + Uvicorn |
| UI | Gradio (монтируется в FastAPI) |
| LLM-клиент | `openai` SDK (chat.completions, structured output) — OpenAI-совместимые провайдеры |
| Погода | Open-Meteo (REST через `httpx`) |
| Валидация / конфиг | Pydantic v2 + `pydantic-settings` |
| Шаблоны промптов | Jinja2 |
| Управление зависимостями | `uv` (`pyproject.toml` + `uv.lock`) |
| Контейнеризация | Docker + docker-compose |
| Требуется Python | `>=3.12` |

## 3. Структура каталогов

```
lesson0/
├── app/
│   ├── main.py                  # создание FastAPI, lifespan, /health, /chat, обработчик 502
│   ├── api/
│   │   ├── routes.py            # POST /api/v1/message
│   │   └── dependencies.py      # DI: IntentAnalysisService
│   ├── services/
│   │   └── intent_service.py    # оркестрация: анализ→сегменты→политика→overall
│   ├── infra/
│   │   ├── llm/
│   │   │   ├── client.py        # OpenAICompatibleLLMClient + StructuredOutputMode + ретрай
│   │   │   └── factory.py       # build_llm_client: выбор openrouter/yandex/mimo
│   │   └── weather/
│   │       ├── open_meteo_client.py   # геокодинг + прогноз
│   │       ├── mappers.py / models.py / constants.py / exceptions.py
│   ├── prompts/
│   │   ├── system.py            # 3 системных промпта (анализ / генерация / погода)
│   │   ├── intent_analysis.py   # шаблон пользовательского промпта анализа
│   │   ├── response_generation.py # шаблон генерации ответа (technical/small_talk)
│   │   ├── weather_generation.py   # шаблон: факты погоды → локализованное описание
│   │   └── responses.py         # локализованные шаблоны (отказ/уточнение/нет погоды)
│   ├── schemas/
│   │   └── intent.py            # Pydantic-схемы (DTO + structured output)
│   ├── core/
│   │   ├── config.py            # Settings (.env), в т.ч. llm_provider и per-provider поля
│   │   └── container.py         # сборка зависимостей
│   └── ui/
│       └── chat.py              # Gradio-чат (настраиваемый таймаут)
├── pyproject.toml               # зависимости, ruff (RUF001-003 отключены), pytest
├── uv.lock / Dockerfile / docker-compose.yml / .env.example
└── README.md
```

## 4. Архитектура слоёв и направление зависимостей

Зависимости направлены **внутрь**: наружные слои зависят от внутренних, но не наоборот.
`services` и `infra` не знают ни про FastAPI, ни про Gradio.

```
        ┌──────────────────────────────────────────────┐
        │                  app/main.py                  │  сборка приложения + /chat
        └───────────────┬──────────────────────────────┘
                        │ создаёт и хранит
                        ▼
        ┌──────────────────────────────────────────────┐
        │            core/container.py (DI)            │  ← core/config.py (Settings)
        │  build_llm_client(settings)  → llm_client     │
        │  OpenMeteoWeatherClient      → weather_client │
        │  IntentAnalysisService(llm, weather)          │
        └───────────────┬──────────────────────────────┘
                        │ отдаёт по Depends
        ┌───────────────┴──────────┐
        ▼                          ▼
   api/routes.py            ui/chat.py          (оба в итоге вызывают
   (HTTP)                   (Gradio, HTTP→бэкенд)  IntentAnalysisService.analyze)
        ▼
   services/intent_service.py            ← бизнес-логика (сегментация, политика, overall)
        │ использует
        ├──────────────────────────────────────────────────────┐
        ▼                          ▼                           ▼
   infra/llm/                  infra/weather/               prompts/
   client.py + factory.py      open_meteo_client.py         system / *_prompt /
   (3 провайдера)              (геокодинг+прогноз)          responses (локализ.)
        │                          │                         schemas/intent.py
        ▼                          ▼
   OpenRouter / Yandex / MiMo  Open-Meteo
```

## 5. Поток обработки запроса `POST /api/v1/message`

```
Клиент ──► FastAPI ──► api/routes.py::analyze_intent(payload)
                                 │ Depends → app.state.container.intent_service
                                 ▼
            services/intent_service.py::analyze(payload)
                                 │
   ┌─────────────────────────────┼─────────────────────────────────────┐
   │  ШАГ 1. _analyze_intent — ОДИН LLM-вызов                            │
   │  • intent_analysis_prompt(query, history)                            │
   │  • complete_structured(INTENT_ANALYSIS_SYSTEM_PROMPT,                │
   │       SegmentedIntentAnalysisLLMResponse)                            │
   │  → segments[]: каждый = {text, intent, language, confidence,         │
   │       reasoning, weather_location}                                   │
   │  (1..5 сегментов; по сегменту на каждый запрошенный город)           │
   └─────────────────────────────┬─────────────────────────────────────┘
                                 │
   ┌─────────────────────────────┼─────────────────────────────────────┐
   │  ШАГ 2. _process_segments — ПАРАЛЛЕЛЬНО (asyncio.gather)            │
   │  Каждый сегмент → _generate_segment_answer:                          │
   │                                                                       │
   │  intent == OTHER ─► unsupported_topic_answer(language)  ← шаблон ru/en
   │                     (без LLM — безопасно для adversarial)            │
   │                                                                       │
   │  intent == WEATHER ─► _generate_weather_answer:                      │
   │     • weather_location пуст? → weather_clarification(lang), clarify  │
   │     • Open-Meteo ошибка?       → weather_unavailable(lang, loc), clar │
   │     • успех: geocode + forecast → facts dict → LLM                    │
   │         WEATHER_FORMATTING_SYSTEM_PROMPT + weather_generation_prompt  │
   │         → естественное описание на языке segment.language (точные числа)│
   │                                                                       │
   │  intent == TECHNICAL_QUESTION | SMALL_TALK ─► LLM-генерация:          │
   │     • response_generation_prompt(query=segment.text, history,         │
   │         intent_analysis=segment, language=segment.language)           │
   │     • RESPONSE_GENERATION_SYSTEM_PROMPT → ответ на языке пользователя │
   └─────────────────────────────┬─────────────────────────────────────┘
                                 │
   ┌─────────────────────────────┼─────────────────────────────────────┐
   │  ШАГ 3. _compute_overall — детерминированно (без LLM)               │
   │  • intent: все сегменты одного класса → он; иначе MIXED              │
   │  • confidence: минимум по сегментам                                  │
   │  • reasoning: join через " | "                                       │
   │  • weather_location: единственный weather-сегмент → его локация;     │
   │    иначе None                                                        │
   │  • answer: join ответов сегментов через "\n\n"                       │
   └─────────────────────────────┬─────────────────────────────────────┘
                                 ▼
                 IntentAnalysisResponse → JSON клиенту
```

## 6. Мультипровайдер LLM (ключевая подсистема)

Все три провайдера — **OpenAI-совместимые** chat-completions, поэтому используется один
generic-класс `OpenAICompatibleLLMClient` (`app/infra/llm/client.py`). Различия
(base_url, аутентификация, режим structured output) задаются в **фабрике**
`build_llm_client(settings)` (`app/infra/llm/factory.py`) по `settings.llm_provider`:

| Провайдер | base_url (по умолч.) | Auth | Structured режим |
|-----------|----------------------|------|------------------|
| `openrouter` | `https://openrouter.ai/api/v1` | `Bearer <key>` (+ опц. `HTTP-Referer`/`X-OpenRouter-Title`) | `json_schema` (strict) |
| `yandex` | `https://ai.api.cloud.yandex.net/v1` | `Authorization: Api-Key <key>` + `x-folder-id` (через `default_headers`, перекрывает Bearer) | `json_object` (fallback) |
| `mimo` | `https://api.xiaomimimo.com/v1` | `Bearer <key>` | `json_object` (fallback) |

**StructuredOutputMode** (`client.py`):
- `JSON_SCHEMA` — `chat.completions.parse(response_format=PydanticModel)`, провайдер
  сам обеспечивает схему (OpenRouter).
- `JSON_OBJECT` — схема инжектируется в системный промпт (`model_json_schema()`),
  `chat.completions.create(response_format={"type":"json_object"})`, затем
  `model_validate_json(content)` (Yandex/MiMo — у них нет строгого json_schema).

**Yandex: полный model URI.** Yandex требует `gpt://<folder>/<model>/<version>`, простое
имя даёт `400 "Failed to parse model URI"`. Поэтому `_yandex_model_uri()` собирает URI из
`YANDEX_FOLDER_ID` + `YANDEX_MODEL` автоматически (passthrough, если уже `gpt://`/`cls://`/`ds://`).
Пример: `YANDEX_MODEL=yandexgpt-5.1/latest` → `gpt://<folder>/yandexgpt-5.1/latest`.

**Ретрай (3 попытки)** в `complete_structured` ловит `pydantic.ValidationError`, **`TypeError`**
(SDK падает на `choices=None` — частый кейс free-моделей) и пустые ответы → после исчерпания
`LLMClientError`. Сетевые/HTTP-ошибки (`APIStatusError`/`APITimeoutError`/`APIConnectionError`)
→ сразу `LLMClientError` (без ретрая).

`openrouter_require_parameters` (default `False`) при `True` добавляет
`extra_body={"provider":{"require_parameters":True}}` — для free-моделей ломает маршрутизацию,
поэтому выключен по умолчанию.

## 7. Внедрение зависимостей (DI)

Реализовано вручную через `dataclass Container` (`app/core/container.py`):
1. `get_settings()` (`@lru_cache`) читает `.env`.
2. `lifespan` (`main.py`) на старте создаёт `Container.from_settings(settings)` →
   `app.state.container`; на остановке `container.close()` закрывает HTTP-клиенты.
3. `Container.from_settings`:
   - `llm_client = build_llm_client(settings)` (фабрика);
   - `weather_client = OpenMeteoWeatherClient(httpx.AsyncClient(timeout=...))`;
   - `intent_service = IntentAnalysisService(llm_client, weather_client)`.
4. `get_intent_service` (`api/dependencies.py`) достаёт сервис из
   `request.app.state.container` → `IntentServiceDep = Annotated[..., Depends(...)]`.

## 8. Конфигурация и переменные окружения

`Settings` (`app/core/config.py`, `BaseSettings`, читает `.env`, `extra="ignore"`).

| Переменная | По умолчанию | Назначение |
|-----------|--------------|-----------|
| `LLM_PROVIDER` | `openrouter` | Активный провайдер: `openrouter\|yandex\|mimo` |
| `OPENROUTER_API_KEY` | — | Ключ OpenRouter |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Базовый URL |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | Модель |
| `OPENROUTER_REFERER` / `OPENROUTER_TITLE` | `None` | Опц. заголовки OpenRouter |
| `OPENROUTER_REQUIRE_PARAMETERS` | `false` | Строгий роутинг (осторожно с free) |
| `YANDEX_API_KEY` | — | Ключ Yandex (Api-Key) |
| `YANDEX_FOLDER_ID` | — | Folder ID (для model URI и заголовка) |
| `YANDEX_MODEL` | `yandexgpt` | Модель (будет обёрнута в `gpt://<folder>/...`) |
| `YANDEX_BASE_URL` | `https://ai.api.cloud.yandex.net/v1` | Endpoint |
| `MIMO_API_KEY` | — | Ключ MiMo |
| `MIMO_MODEL` | `xiaomi/MiMo-7B-RL` | Модель |
| `MIMO_BASE_URL` | `https://api.xiaomimimo.com/v1` | Endpoint |
| `REQUEST_TIMEOUT_SECONDS` | `60.0` | Таймаут бэкенд→провайдер (на вызов) |
| `CHAT_REQUEST_TIMEOUT_SECONDS` | `120.0` | Таймаут UI Gradio→бэкенд (под составные запросы) |
| `INTERNAL_API_BASE_URL` | `http://127.0.0.1:8000` | URL бэкенда для Gradio-чата |
| `APP_NAME` / `APP_VERSION` / `APP_ENV` | — | Метаданные приложения |

Шаблон — `.env.example`. Смена провайдера/ключей — правка `.env` + `docker compose up -d`
(пересборка нужна только при смене кода, `.env` читается при старте).

## 9. Схемы данных (`app/schemas/intent.py`)

| Класс | Назначение |
|-------|-----------|
| `IntentClass(StrEnum)` | `weather`, `technical_question`, `small_talk`, `other`, `mixed` (mixed — только overall) |
| `DialogMessage` | Сообщение истории: `role` + `content` |
| `IntentAnalysisRequest` | Тело запроса API: `query` (1..10 000) + `history` (≤50) |
| `IntentSegment` | Сегмент (structured output): `text`, `intent`, **`language`** (ISO 639-1), `confidence`, `reasoning`, `weather_location`. `extra="forbid"` |
| `SegmentedIntentAnalysisLLMResponse` | Structured output Шага 1: `segments` (1..5) |
| `ResponseGenerationLLMResponse` | Structured output генерации: `answer` |
| `SegmentResponse(IntentSegment)` | Сегмент + `answer` + `needs_clarification` (в API-ответе) |
| `IntentAnalysisResponse` | Итог: `intent`/`confidence`/`reasoning`/`weather_location`/`answer`/`needs_clarification` + `segments[]` |

## 10. LLM-клиент (`app/infra/llm/client.py`)

`OpenAICompatibleLLMClient(client: AsyncOpenAI, model, *, mode, extra_body)`:
- `complete_structured(system_prompt, user_prompt, text_format, max_output_tokens=500, temperature=0.0)`
  с ретраем (см. §6); ветвление по `mode` (`_request_json_schema` / `_request_json_object`).
- Все ошибки LLM → `LLMClientError` → глобальный обработчик в `main.py` → **HTTP 502**.

## 11. Погодный клиент (`app/infra/weather/`)

`OpenMeteoWeatherClient.get_current_weather(location)`:
1. **Геокодинг** (`OPEN_METEO_GEOCODING_URL`, `language=en`) — имя→`latitude/longitude`/`country`.
2. **Прогноз** (`OPEN_METEO_FORECAST_URL`) — текущие поля (`temperature_2m`, `relative_humidity_2m`,
   `apparent_temperature`, `precipitation`, `weather_code`, `wind_speed_10m`).
Разбор — `mappers.py` → `CurrentWeather` (`@dataclass(frozen=True)`); `condition` через
`WEATHER_CODE_LABELS`. Любая `httpx.HTTPError`/некорректный JSON → `WeatherClientError`.
Геокодер намеренно остаётся с `language=en`: модель нормализует город в каноничное английское
имя → надёжный мэтч и английское имя/страна в фактах (LLM потом локализует описание).

## 12. Промпты (`app/prompts/`)

- `system.py`:
  - `INTENT_ANALYSIS_SYSTEM_PROMPT` — разбивка на 1..5 сегментов; правила классов (см. §13);
    мультиязычная нормализация + **мульти-город** (отдельный сегмент на город) + **разрешение
    описаний**; инструкция для `language`; блок `### Worked examples` (главный рычаг единообразия).
  - `RESPONSE_GENERATION_SYSTEM_PROMPT` — ответ на языке пользователя; technical (вкл. математику)
    / small_talk (вкл. юмор).
  - `WEATHER_FORMATTING_SYSTEM_PROMPT` — описать погоду на языке пользователя ТОЛЬКО заданными
    значениями (не искажать числа).
- `intent_analysis.py` — пользовательский промпт анализа (query + history).
- `response_generation.py` — `response_generation_prompt(query, history, intent_analysis, language)`.
- `weather_generation.py` — `weather_generation_prompt(place, facts, language)` (факты dict, без импорта из infra).
- `responses.py` — локализованные шаблоны `unsupported_topic_answer(lang)` /
  `weather_clarification(lang)` / `weather_unavailable(lang, location)` (en/ru + English fallback).

## 13. Единая классификация (правила для всех провайдеров)

Чтобы все модели трактовали спорные кейсы одинаково, в `INTENT_ANALYSIS_SYSTEM_PROMPT` закреплено:
- **юмор/шутки/загадки → `small_talk`** (отвечать);
- **математика/арифметика → `technical_question`** (отвечать);
- общая эрудиция/география/история/здоровье → `other` (заглушка);
- явное указание: юмор и математику **не** отправлять в `other`.

## 14. Локализация и мультиязычность

- **Язык ответа = язык запроса.** Модель определяет `language` (ISO 639-1) на уровне сегмента.
- technical/small_talk/weather — формируются LLM на этом языке (погода — из фактов, числа точные).
- `other`/уточнение/«нет погоды» — локализованные шаблоны en/ru (+fallback English), **без LLM**
  (безопасно: adversarial-контент не уходит обратно в модель).
- Локация распознаётся на любом языке/скрипте и нормализуется в каноничное английское имя для
  геокодинга (Москва→Moscow, Warszawa→Warsaw, Прага→Prague).

## 15. Gradio-чат (`app/ui/chat.py`)

- `build_chat_ui(api_base_url, *, request_timeout_seconds=120.0)` → `gr.Blocks`, монтируется на
  `/chat` (`gr.mount_gradio_app`). `submit_message` ходит по HTTP в собственный бэкенд
  (`INTERNAL_API_BASE_URL + /api/v1/message`), передаёт последние 20 сообщений.
- Ответ чата = `answer` + служебные строки (`intent:`/`confidence:`/`needs_clarification:`);
  `_clean_content` вырезает их из прошлых ответов, не загрязняя контекст.

## 16. Карта импортов (кто от кого зависит напрямую)

```
main.py
 ├─ api/routes.py ── api/dependencies.py ── services/intent_service.py
 ├─ core/config.py
 ├─ core/container.py ── core/config.py
 │                    ├─ infra/llm/factory.py ── infra/llm/client.py
 │                    ├─ infra/weather/open_meteo_client.py ── mappers/models/constants/exceptions
 │                    └─ services/intent_service.py
 ├─ infra/llm/client.py (LLMClientError)
 └─ ui/chat.py

services/intent_service.py
 ├─ infra/llm/client.py
 ├─ infra/weather/{open_meteo_client, exceptions}
 ├─ prompts/{system, intent_analysis, response_generation, weather_generation, responses}
 └─ schemas/intent.py
```

`schemas/intent.py` — фундамент: на него опираются `services`, `prompts`, `api`.

## 17. Маршруты

| Метод | Путь | Назначение |
|-------|------|-----------|
| `POST` | `/api/v1/message` | Основной эндпоинт: анализ + ответ (с `segments`) |
| `GET` | `/health` | `{"status":"ok","env":<app_env>}` |
| `(UI)` | `/chat` | Gradio-чат |

## 18. Запуск

**Локально (uv):**
```bash
cp .env.example .env          # заполнить ключ нужного провайдера + LLM_PROVIDER
uv sync
uv run uvicorn app.main:app --reload
```
**Docker** (смена кода требует `--build`; смена `.env` — только `up -d`):
```bash
cp .env.example .env          # заполнить ключ + LLM_PROVIDER
docker compose up --build
```
API: `http://localhost:8000` · Чат: `http://localhost:8000/chat`.

**Линтер:** `uv run ruff check app/`. В `pyproject.toml` отключены `RUF001/002/003`
(кириллические омоглифы — ложные срабатывания для мультиязычного приложения).
**Тесты:** `pytest` настроен (`testpaths=["tests"]`), но директории `tests/` пока нет.

## 19. Обработка ошибок (сводка)

| Ситуация | Исключение | HTTP |
|----------|-----------|------|
| Сбой LLM (статус/таймаут/соединение) | `LLMClientError` | **502** |
| LLM вернул непарсимый/битый JSON (после 3 ретраев) | `LLMClientError` | **502** |
| Сбой погоды (HTTP/JSON/нет геокода) | `WeatherClientError` | не пробрасывается → `weather_unavailable(lang)` + `needs_clarification=True` |
| Некорректный запрос (валидация Pydantic) | — | **422** (автоматически) |

## 20. Замечания и нюансы

- **Число LLM-вызовов**: 1 анализ + 1 на каждый technical/small_talk/weather сегмент (параллельно
  через `gather`); `other` — без LLM. «Погода в N городах» = N вызовов генерации + 1 анализ.
- **Лимит сегментов = 5** → максимум 5 городов погоды в одном запросе (`max_length` в схеме).
- **Температуры**: анализ `0.0`, генерация `0.3`, погода `0.2`.
- **`max_output_tokens`**: анализ `1500`, генерация/погода `500`.
- **Параллельность сегментов** убирает суммирование времени между ними; худший случай на вызов ≈
  3×`REQUEST_TIMEOUT_SECONDS` (ретраи). UI-таймаут `CHAT_REQUEST_TIMEOUT_SECONDS=120` покрывает типичные составные запросы.
- **Responses API не используется** — только chat.completions (Responses API недоступен для многих
  моделей, включая free). Переключение провайдера/SDK требует перепроверки structured-output режима.
- **Поведение моделей** может слегка отличаться по «мягким» кейсам, но спорные (юмор/математика)
  унифицированы промптом; числа погоды модель не искажает (передаются явно).
