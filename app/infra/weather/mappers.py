from typing import Any

from app.infra.weather.exceptions import WeatherClientError
from app.infra.weather.models import CurrentWeather, GeocodedLocation


def parse_geocoded_location(payload: dict[str, Any], original_location: str) -> GeocodedLocation:
    results = payload.get("results")
    if not results:
        raise WeatherClientError(f"Could not find weather location: {original_location}")

    first_result = results[0]
    return GeocodedLocation(
        name=str(first_result["name"]),
        latitude=float(first_result["latitude"]),
        longitude=float(first_result["longitude"]),
        country=_optional_str(first_result.get("country")),
    )


def parse_current_weather(
    payload: dict[str, Any],
    location: GeocodedLocation,
) -> CurrentWeather:
    current = payload.get("current")
    if not isinstance(current, dict):
        raise WeatherClientError("Open-Meteo returned no current weather data")

    return CurrentWeather(
        location_name=location.name,
        country=location.country,
        temperature_c=float(current["temperature_2m"]),
        apparent_temperature_c=_optional_float(current.get("apparent_temperature")),
        relative_humidity_percent=_optional_int(current.get("relative_humidity_2m")),
        precipitation_mm=_optional_float(current.get("precipitation")),
        wind_speed_kmh=_optional_float(current.get("wind_speed_10m")),
        weather_code=_optional_int(current.get("weather_code")),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
