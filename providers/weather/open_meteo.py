"""Open-Meteo forecast HTTP adapter. Never calls the network during import.

Live calls only happen through `fetch_daily` when the caller explicitly opts in.
One logical GET attempt; no application-level retries; no credentials needed.
"""
from __future__ import annotations
from datetime import date
from typing import Callable, Any
import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FIELDS = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "precipitation_sum",
)

class OpenMeteoClient:
    def __init__(self, http_get: Callable[..., Any] | None = None):
        self._http_get = http_get or requests.get

    def fetch_daily(self, *, latitude: float, longitude: float,
                    travel_date: date, today: date) -> dict:
        days_ahead = (travel_date - today).days
        if not 0 <= days_ahead <= 15:
            raise ValueError("Travel date outside the 16-day forecast window: no request made")
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("Invalid WGS84 coordinates: no request made")
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join(FIELDS),
            "timezone": "Asia/Shanghai",
            "forecast_days": days_ahead + 1,  # request only as many days as needed
        }
        try:
            response = self._http_get(FORECAST_URL, params=params, timeout=12)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"Open-Meteo weather request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict) or payload.get("error") is True:
            raise RuntimeError("Open-Meteo returned an error response")
        daily = payload.get("daily")
        if not isinstance(daily, dict) or not isinstance(daily.get("time"), list):
            raise RuntimeError("Open-Meteo response lacks daily timestamps")
        dates = daily["time"]
        expected = travel_date.isoformat()
        if expected not in dates:
            return {"date": expected, "available": False, "values": {},
                    "source_endpoint": FORECAST_URL}
        ix = dates.index(expected)
        values = {}
        for name in FIELDS:
            seq = daily.get(name)
            values[name] = seq[ix] if isinstance(seq, list) and ix < len(seq) else None
        return {"date": expected, "available": True, "values": values,
                "source_endpoint": FORECAST_URL,
                "provider_timezone": payload.get("timezone")}
