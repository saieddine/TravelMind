"""TravelMind Context Agent — Stage 4.

Default mode: offline, zero external APIs, zero LLM tokens.
Offline scenarios are simulated conditions, NEVER live weather observations.
Live mode: explicit --live + --adcode, maximum ONE Amap weather request.
The module does not check attraction closures, visa rules or official alerts.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from agents.destination_agent import canonical_city  # Shares Stage 3 city conventions.

CHINA_TZ = timezone(timedelta(hours=8))
SCENARIOS = {
    "rain": "Simulated rainy conditions",
    "sunny": "Simulated sunny conditions",
    "hot": "Simulated hot conditions",
    "cold": "Simulated cold conditions",
    "storm": "Simulated storm-like conditions",
}


def china_today() -> date:
    return datetime.now(CHINA_TZ).date()


def forecast_signals(weather: dict[str, Any]) -> list[str]:
    """Deterministic interpretation of weather, NOT official warnings."""
    signals: list[str] = []
    description = " ".join(str(weather.get(k) or "") for k in ("day_weather_zh", "night_weather_zh"))
    if "雷" in description or "暴" in description or "storm" in description.casefold():
        signals.append("possible_storm")
    if "雨" in description or "rain" in description.casefold():
        signals.append("rain")
    if "雪" in description or "snow" in description.casefold():
        signals.append("snow")
    temp = weather.get("temperature_day_c")
    if isinstance(temp, (int, float)) and temp >= 32:
        signals.append("hot")
    lows = weather.get("temperature_night_c")
    if isinstance(lows, (int, float)) and lows <= 0:
        signals.append("cold")
    return signals


def itinerary_hints(signals: list[str]) -> list[dict[str, str]]:
    """Guidance only. Itinerary design remains the other teammate's task."""
    results = []
    if "possible_storm" in signals:
        results.append({"priority": "high", "suggestion": "Check official weather alerts before outdoor activities; consider indoor alternatives."})
    if "rain" in signals or "snow" in signals:
        results.append({"priority": "medium", "suggestion": "Prefer flexible indoor visits and allow extra time for outdoor transfers."})
    if "hot" in signals:
        results.append({"priority": "medium", "suggestion": "Prefer indoor or shaded activities during peak afternoon heat."})
    if "cold" in signals:
        results.append({"priority": "low", "suggestion": "Account for cold conditions during outdoor stops and transfers."})
    return results


class ContextAgent:
    """Weather-context tool routing with strict opt-in network access."""

    def run(self, *, city: str, travel_date: str | None = None,
            scenario: str | None = None, live: bool = False,
            adcode: str | None = None) -> dict[str, Any]:
        if not isinstance(city, str) or not city.strip():
            raise ValueError("city is required")
        if live and scenario:
            raise ValueError("Use either --live OR --scenario, not both")
        if scenario and scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario}; choose {sorted(SCENARIOS)}")

        today = china_today()
        requested = date.fromisoformat(travel_date) if travel_date else today
        city_zh = canonical_city(city)
        usage = {"amap_weather_requests_attempted": 0,
                 "llm_requests_attempted": 0, "llm_input_tokens": 0,
                 "llm_output_tokens": 0}
        trace = [{"step": "identify_context", "city": city_zh,
                  "date": requested.isoformat()}]
        warnings = ["Official weather alerts, visa/entry rules, and attraction closures have NOT been checked."]
        status = "not_checked"
        weather: dict[str, Any] = {
            "date": requested.isoformat(), "status": status,
            "day_weather_zh": None, "night_weather_zh": None,
            "temperature_day_c": None, "temperature_night_c": None,
            "signals": [], "source": None,
        }
        mode = "offline_unavailable"

        if scenario:
            signals = {
                "rain": ["rain"], "sunny": [], "hot": ["hot"],
                "cold": ["cold"], "storm": ["possible_storm", "rain"],
            }[scenario]
            weather.update({"status": "simulated_scenario", "signals": signals,
                            "scenario": SCENARIOS[scenario],
                            "source": {"provider": "user_selected_test_scenario", "verified": False}})
            mode = "offline_simulation"
            trace.append({"step": "weather_context", "tool": "local_scenario", "external_requests": 0})
            warnings.append("Weather scenario is deliberately simulated; it is NOT a real forecast.")

        elif live:
            if not (isinstance(adcode, str) and len(adcode) == 6 and adcode.isascii() and adcode.isdigit()):
                raise ValueError("--live requires a six-digit Amap --adcode; no lookup call is made")
            # Amap's basic multi-day forecast is short-range; avoid waste for future dates.
            days_ahead = (requested - today).days
            if not 0 <= days_ahead <= 3:
                warnings.append("Travel date is outside the expected short Amap forecast window; skipped API call.")
                trace.append({"step": "weather_context", "tool": "none", "reason": "out_of_forecast_window"})
                mode = "live_skipped_no_request"
            else:
                from providers.amap.weather import get_daily_forecast
                usage["amap_weather_requests_attempted"] = 1  # Counts attempted requests, even on failure.
                trace.append({"step": "weather_context", "tool": "amap_weather_forecast",
                              "reason": "explicit --live", "max_calls": 1})
                info = get_daily_forecast(adcode)
                matching = next((d for d in info["days"] if d["date"] == requested.isoformat()), None)
                mode = "live_amap_transient"
                if matching:
                    signals = forecast_signals(matching)
                    weather.update(matching)
                    weather.update({"status": "provider_forecast", "signals": signals,
                                    "source": {
                                        "provider": "amap",
                                        "endpoint": "/v3/weather/weatherInfo",
                                        "provider_report_time": info["provider_report_time"],
                                        "retrieved_at": info["retrieved_at"],
                                        "adcode": info["adcode"],
                                    }})
                else:
                    weather["status"] = "forecast_unavailable_for_date"
                    warnings.append("Amap returned no daily forecast for that date; no weather conditions were inferred.")
                warnings.append("Provider weather data is temporary; check terms before retaining or redistributing it.")

        else:
            trace.append({"step": "weather_context", "tool": "none", "reason": "offline_default"})
            warnings.append("No weather scenario selected and no live API authorized; weather is unknown.")

        hints = itinerary_hints(weather["signals"])
        trace.append({"step": "handoff", "target": "itinerary_agent",
                      "weather_status": weather["status"], "hint_count": len(hints)})
        return {
            "schema_version": "1.1-draft",
            "agent": "context_agent",
            "mode": mode,
            "request": {"city": city_zh, "travel_date": requested.isoformat()},
            "context": {
                "weather": weather,
                "itinerary_hints": hints,
                "checks": {
                    "official_weather_alerts": "not_checked",
                    "travel_entry_requirements": "not_checked",
                    "attraction_closures": "not_checked",
                },
            },
            "warnings": warnings,
            "trace": trace,
            "usage": usage,
        }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="TravelMind Stage 4 Context Agent (offline by default)")
    parser.add_argument("--city", required=True, help='e.g. Xi\'an, 北京')
    parser.add_argument("--date", dest="travel_date", help="YYYY-MM-DD; default China-local today")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS),
                        help="SIMULATED weather: rain, sunny, hot, cold, storm")
    parser.add_argument("--live", action="store_true", help="Authorize at most one real Amap forecast call")
    parser.add_argument("--adcode", help="Six-digit Amap city adcode; REQUIRED with --live")
    args = parser.parse_args(argv)
    try:
        output = ContextAgent().run(city=args.city, travel_date=args.travel_date,
                                    scenario=args.scenario, live=args.live, adcode=args.adcode)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"Context Agent failed: {type(exc).__name__}: {exc}\n")
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
