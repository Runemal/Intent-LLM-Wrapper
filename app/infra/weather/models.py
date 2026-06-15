from dataclasses import dataclass

from app.infra.weather.constants import UNKNOWN_WEATHER_CONDITION, WEATHER_CODE_LABELS


@dataclass(frozen=True, slots=True)
class GeocodedLocation:
    name: str
    latitude: float
    longitude: float
    country: str | None


@dataclass(frozen=True, slots=True)
class CurrentWeather:
    location_name: str
    country: str | None
    temperature_c: float
    apparent_temperature_c: float | None
    relative_humidity_percent: int | None
    precipitation_mm: float | None
    wind_speed_kmh: float | None
    weather_code: int | None

    @property
    def condition(self) -> str:
        if self.weather_code is None:
            return UNKNOWN_WEATHER_CONDITION
        return WEATHER_CODE_LABELS.get(self.weather_code, UNKNOWN_WEATHER_CONDITION)
