"""Amap weather forecast adapter for TravelMind.

No network activity at import. Call get_daily_forecast only after explicit
user permission; it attempts one HTTPS request and never caches response data.
"""

from __future__ import annotations
from providers.config import environment_file

import os
from datetime import datetime, timezone
from typing import Any

WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"


def _safe_temp(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_daily_forecast(data: dict[str, Any], requested_adcode: str) -> dict[str, Any]:
    """Normalize Amap's `extensions=all` payload without inventing missing data."""
    if str(data.get("status")) != "1":
        info = str(data.get("info", "unknown"))[:100]
        code = str(data.get("infocode", "unknown"))[:30]
        raise RuntimeError(f"Amap weather API rejected request: {info} ({code})")

    forecasts = data.get("forecasts") or []
    forecast = forecasts[0] if forecasts and isinstance(forecasts[0], dict) else {}
    casts = forecast.get("casts") or []
    daily = []
    for cast in casts:
        if not isinstance(cast, dict):
            continue
        date_str = cast.get("date")
        if not isinstance(date_str, str) or len(date_str) != 10:
            continue
        daily.append({
            "date": date_str,
            "day_weather_zh": cast.get("dayweather") or None,
            "night_weather_zh": cast.get("nightweather") or None,
            "temperature_day_c": _safe_temp(cast.get("daytemp")),
            "temperature_night_c": _safe_temp(cast.get("nighttemp")),
        })

    return {
        "city_zh": forecast.get("city"),
        "adcode": forecast.get("adcode") or requested_adcode,
        "provider_report_time": forecast.get("reporttime"),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "days": daily,
        "provider": "amap",
        "data_type": "daily_forecast",
    }


def get_daily_forecast(adcode: str) -> dict[str, Any]:
    """Attempt exactly ONE GET. No retry, no pagination and no disk storage."""
    if not (isinstance(adcode, str) and len(adcode) == 6 and adcode.isascii() and adcode.isdigit()):
        raise ValueError("Provide a valid six-digit Amap city/district adcode")

    # Only load an API key when an explicit live operation has been requested.
    try:
        from dotenv import load_dotenv
        load_dotenv(environment_file())
    except ImportError:
        pass
    key = os.getenv("AMAP_API_KEY")
    if not key:
        raise ValueError("Missing AMAP_API_KEY; configure .env or environment")

    import requests
    try:
        response = requests.get(
            WEATHER_URL,
            params={"key": key, "city": adcode, "extensions": "all", "output": "JSON"},
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        # Do NOT include request URLs or exceptions; those can expose query keys.
        raise RuntimeError(f"Weather network request failed ({type(exc).__name__})") from None
    except ValueError:
        raise RuntimeError("Weather API did not return valid JSON") from None
    if not isinstance(data, dict):
        raise RuntimeError("Weather API returned unexpected payload")
    return parse_daily_forecast(data, requested_adcode=adcode)
