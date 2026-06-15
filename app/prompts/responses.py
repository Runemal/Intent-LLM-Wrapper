def _localized(language: str, table: dict[str, str]) -> str:
    """Pick a localized string by ISO 639-1 code, falling back to English."""
    return table.get(language.lower(), table["en"])


def unsupported_topic_answer(language: str) -> str:
    return _localized(
        language.lower(),
        {
            "en": (
                "I can tell you about weather, technology, and keep up a little "
                "conversation. I do not discuss other topics."
            ),
            "ru": (
                "Я могу рассказать о погоде, технологиях и немного поддержать беседу. "
                "Другие темы я не обсуждаю."
            ),
        },
    )


def weather_clarification(language: str) -> str:
    return _localized(
        language.lower(),
        {
            "en": "Which location should I check the weather for?",
            "ru": "Для какого города узнать погоду?",
        },
    )


def weather_unavailable(language: str, location: str) -> str:
    return _localized(
        language.lower(),
        {
            "en": f"I could not retrieve weather for {location}. Try another city.",
            "ru": f"Не удалось получить погоду для {location}. Попробуйте другой город.",
        },
    )
