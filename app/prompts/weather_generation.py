from jinja2 import Template


def weather_generation_prompt(
    *,
    place: str,
    facts: dict[str, object],
    language: str,
) -> str:
    """Build the user prompt that feeds raw Open-Meteo facts to the LLM so it can
    produce a natural, localized weather description. The facts dict is built by the
    service from a CurrentWeather instance, keeping this module decoupled from infra.
    """
    template_string = """\
### Weather data (use ONLY these exact values)

place: {{ place }}
condition: {{ facts.condition }}
temperature_c: {{ facts.temperature_c }}
feels_like_c: {{ facts.feels_like_c }}
humidity_percent: {{ facts.humidity_percent }}
wind_speed_kmh: {{ facts.wind_speed_kmh }}
precipitation_mm: {{ facts.precipitation_mm }}

### Language

Respond in: {{ language }}

Describe the current weather in {{ place }} in the language above, using only the
provided values. Do not round or change any number.
"""
    template = Template(template_string)
    return template.render(place=place, facts=facts, language=language).strip()
