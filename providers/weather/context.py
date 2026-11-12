"""TravelMind Stage 10 weather bridge for the existing Context Agent contract.

Default mode: synthetic fixture (never live data). Explicit --live enables
ONE forecast request to Open-Meteo. No LLM calls. No persistent caching.
"""
from __future__ import annotations
import argparse
import json
from datetime import date, datetime, timedelta, timezone
from providers.weather.open_meteo import OpenMeteoClient

CHINA_TZ = timezone(timedelta(hours=8))
# Approximate WGS84 city centers for weather queries; NOT Amap GCJ-02 POIs.
CITY_CENTERS_WGS84 = {
    "xi'an": (34.3416, 108.9398), "xian": (34.3416, 108.9398),
    "西安": (34.3416, 108.9398), "西安市": (34.3416, 108.9398),
    "beijing": (39.9042, 116.4074), "北京": (39.9042, 116.4074), "北京市": (39.9042, 116.4074),
    "shanghai": (31.2304, 121.4737), "上海": (31.2304, 121.4737), "上海市": (31.2304, 121.4737),
    "chengdu": (30.5728, 104.0668), "成都": (30.5728, 104.0668), "成都市": (30.5728, 104.0668),
    "hangzhou": (30.2741, 120.1551), "杭州": (30.2741, 120.1551), "杭州市": (30.2741, 120.1551),
}

# Deliberately fabricated weather example, only to test schema/decisions.
SYNTHETIC_WEATHER = {
    "weather_code": 61, "temperature_2m_max": 19.0,
    "temperature_2m_min": 9.0, "precipitation_probability_max": 65,
    "precipitation_sum": 4.2,
}


def weather_signals(values: dict) -> list[str]:
    """Interpret daily *forecast* codes, not verified weather alerts."""
    signals = []
    code = values.get("weather_code")
    try:
        code = int(code) if code is not None else None
    except (TypeError, ValueError):
        code = None
    if code in (95, 96, 99):
        signals.append("possible_storm")
    if code is not None and (51 <= code <= 67 or 80 <= code <= 82 or 95 <= code <= 99):
        signals.append("rain")
    # Daily maximum precipitation probability is a *chance* of precipitation,
    # not a guaranteed rainfall amount. Warn cautiously even when sum is 0.0mm.
    chance = values.get("precipitation_probability_max")
    if "rain" not in signals and isinstance(chance, (int, float)) and chance >= 50:
        signals.append("possible_rain")
    if code is not None and (71 <= code <= 77 or code in (85, 86)):
        signals.append("snow")
    hot = values.get("temperature_2m_max")
    cold = values.get("temperature_2m_min")
    if isinstance(hot, (int, float)) and hot >= 32:
        signals.append("hot")
    if isinstance(cold, (int, float)) and cold <= 0:
        signals.append("cold")
    return signals


def itinerary_hints(signals: list[str]) -> list[dict[str, str]]:
    hints = []
    if "possible_storm" in signals:
        hints.append({"priority": "high", "suggestion": "Verify official warnings and prepare indoor alternatives."})
    if "possible_rain" in signals:
        hints.append({"priority": "low", "suggestion": "Rain is possible; consider an umbrella and flexible indoor options."})
    if "rain" in signals or "snow" in signals:
        hints.append({"priority": "medium", "suggestion": "Prefer flexible indoor visits and allow transfer time."})
    if "hot" in signals:
        hints.append({"priority": "medium", "suggestion": "Avoid long outdoor activities during the hottest hours."})
    if "cold" in signals:
        hints.append({"priority": "low", "suggestion": "Plan warm clothing and shorter outdoor stops."})
    return hints


def build_context(*, city: str, travel_date: str | None = None,
                  live: bool = False, client: OpenMeteoClient | None = None,
                  today: date | None = None) -> dict:
    today = today or datetime.now(CHINA_TZ).date()
    requested = date.fromisoformat(travel_date) if travel_date else today
    city_norm = city.strip().lower()
    if city_norm not in CITY_CENTERS_WGS84:
        raise ValueError("Unknown city: supply a supported city; no geocoding request is made")
    latitude, longitude = CITY_CENTERS_WGS84[city_norm]
    days_ahead = (requested - today).days
    usage = {"open_meteo_requests_attempted": 0, "amap_requests_attempted": 0,
             "baidu_requests_attempted": 0, "llm_requests_attempted": 0, "llm_tokens": 0}
    warnings = ["Official alerts, attraction closures and entry rules were not checked."]
    trace = [{"step": "resolve_city", "source": "built_in_wgs84_city_centers", "external_requests": 0}]
    values = {}
    source = None
    if not live:
        mode, status = "offline_synthetic", "simulated_not_verified"
        values = dict(SYNTHETIC_WEATHER)
        source = {"provider": "synthetic_fixture", "is_real_forecast": False}
        trace.append({"step": "weather", "tool": "synthetic_fixture", "external_requests": 0})
        warnings.append("Values are fabricated test fixtures, NOT real weather forecasts.")
    elif not 0 <= days_ahead <= 15:
        mode, status = "live_skipped_outside_window", "forecast_unavailable"
        trace.append({"step": "weather", "tool": "none", "reason": "outside_16_day_window"})
        warnings.append("Open-Meteo forecast window does not cover the travel date; no HTTP call was made.")
    else:
        mode, status = "live_open_meteo_transient", "provider_forecast"
        usage["open_meteo_requests_attempted"] = 1  # count before request, even if it fails
        trace.append({"step": "weather", "tool": "open_meteo_forecast", "external_requests": 1})
        forecast = (client or OpenMeteoClient()).fetch_daily(
            latitude=latitude, longitude=longitude, travel_date=requested, today=today)
        if forecast["available"]:
            values = forecast["values"]
        else:
            status = "forecast_unavailable"
        source = {"provider": "open_meteo", "url": "https://open-meteo.com/en/docs",
                  "endpoint": forecast["source_endpoint"],
                  "retrieved_at": datetime.now(timezone.utc).isoformat(),
                  "is_real_forecast": forecast["available"],
                  "attribution": "Weather data by Open-Meteo.com (CC BY 4.0)"}
    signals = weather_signals(values) if status != "forecast_unavailable" else []
    weather = {
        "date": requested.isoformat(), "status": status,
        "temperature_day_c": values.get("temperature_2m_max"),
        "temperature_night_c": values.get("temperature_2m_min"),
        "precipitation_probability_max_pct": values.get("precipitation_probability_max"),
        "precipitation_sum_mm": values.get("precipitation_sum"),
        "weather_code": values.get("weather_code"), "signals": signals,
        "source": source,
    }
    return {
        "schema_version": "1.1-draft", "agent": "context_agent", "mode": mode,
        "request": {"city": city, "travel_date": requested.isoformat()},
        "context": {
            "weather": weather, "itinerary_hints": itinerary_hints(signals),
            "checks": {"official_weather_alerts": "not_checked",
                       "travel_entry_requirements": "not_checked",
                       "attraction_closures": "not_checked"}},
        "trace": trace, "warnings": warnings, "usage": usage,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="TravelMind Open-Meteo Context Agent (offline by default)")
    p.add_argument("--city", default="Xi'an", help="Xi'an, Beijing, Shanghai, Chengdu or Hangzhou")
    p.add_argument("--date", help="YYYY-MM-DD; default today in China")
    p.add_argument("--live", action="store_true", help="Explicitly permit at most one Open-Meteo request")
    args = p.parse_args(argv)
    try:
        result = build_context(city=args.city, travel_date=args.date, live=args.live)
    except (ValueError, RuntimeError) as exc:
        p.exit(1, f"Error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
