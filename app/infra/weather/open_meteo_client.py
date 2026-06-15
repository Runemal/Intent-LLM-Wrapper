from typing import Any

import httpx

from app.infra.weather.constants import (
    CURRENT_WEATHER_FIELDS,
    OPEN_METEO_FORECAST_URL,
    OPEN_METEO_GEOCODING_URL,
)
from app.infra.weather.exceptions import WeatherClientError
from app.infra.weather.mappers import parse_current_weather, parse_geocoded_location
from app.infra.weather.models import CurrentWeather, GeocodedLocation


class OpenMeteoWeatherClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def get_current_weather(self, location: str) -> CurrentWeather:
        geocoded_location = await self._geocode(location)
        forecast_payload = await self._forecast(
            latitude=geocoded_location.latitude,
            longitude=geocoded_location.longitude,
        )
        return parse_current_weather(forecast_payload, geocoded_location)

    async def close(self) -> None:
        await self._client.aclose()

    async def _geocode(self, location: str) -> GeocodedLocation:
        payload = await self._get_json(
            OPEN_METEO_GEOCODING_URL,
            params={"name": location, "count": 1, "language": "en", "format": "json"},
            error_message="Open-Meteo geocoding request failed",
        )
        return parse_geocoded_location(payload, original_location=location)

    async def _forecast(self, *, latitude: float, longitude: float) -> dict[str, Any]:
        return await self._get_json(
            OPEN_METEO_FORECAST_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": CURRENT_WEATHER_FIELDS,
                "timezone": "auto",
            },
            error_message="Open-Meteo forecast request failed",
        )

    async def _get_json(
        self,
        url: str,
        *,
        params: dict[str, object],
        error_message: str,
    ) -> dict[str, Any]:
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise WeatherClientError(error_message) from exc

        data = response.json()
        if not isinstance(data, dict):
            raise WeatherClientError("Open-Meteo returned an invalid JSON payload")
        return data
