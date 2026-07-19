"""
Weather tool — uses Open-Meteo, which is fully free and needs no API key.
Docs: https://open-meteo.com/en/docs
"""
from __future__ import annotations
import requests
from datetime import date, timedelta
from typing import List, Optional

from backend.models import WeatherDay

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo's WMO weather codes, simplified to plain-English conditions.
_WEATHER_CODE_MAP = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog", 51: "Light drizzle", 61: "Light rain",
    63: "Moderate rain", 65: "Heavy rain", 71: "Light snow", 73: "Moderate snow",
    80: "Rain showers", 95: "Thunderstorm",
}


def _geocode(city: str) -> Optional[tuple[float, float]]:
    resp = requests.get(GEOCODE_URL, params={"name": city, "count": 1}, timeout=15)
    resp.raise_for_status()
    results = resp.json().get("results")
    if not results:
        return None
    return results[0]["latitude"], results[0]["longitude"]


def get_forecast(city: str, start_date: date, end_date: date) -> List[WeatherDay]:
    """
    Open-Meteo's free forecast only reliably covers ~16 days ahead. For trips
    further out, this returns an empty list rather than guessing — the agent
    should treat missing weather as 'unknown' and not block planning on it.
    """
    days_out = (start_date - date.today()).days
    if days_out > 16:
        return []

    coords = _geocode(city)
    if not coords:
        return []
    lat, lon = coords

    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "weathercode,temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    resp = requests.get(FORECAST_URL, params=params, timeout=15)
    resp.raise_for_status()
    daily = resp.json().get("daily", {})

    forecasts = []
    dates = daily.get("time", [])
    codes = daily.get("weathercode", [])
    tmax = daily.get("temperature_2m_max", [])
    tmin = daily.get("temperature_2m_min", [])
    for i, d in enumerate(dates):
        forecasts.append(WeatherDay(
            date=date.fromisoformat(d),
            condition=_WEATHER_CODE_MAP.get(codes[i], "Unknown") if i < len(codes) else "Unknown",
            temp_max_c=tmax[i] if i < len(tmax) else 0.0,
            temp_min_c=tmin[i] if i < len(tmin) else 0.0,
        ))
    return forecasts
