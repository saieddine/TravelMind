"""TravelMind Stage 15 — offline-first *provisional* team handoff.

- No network, LLM, booking or filesystem writes in this module.
- compose_handoff() accepts already-retrieved in-memory adapter results, including
  transient live results, without persisting provider data.
- run_offline_handoff() calls only local-source operations and accepts NO live flags.
- This is NOT a substitute for Saieddine's authoritative TripRequest and
  EvidenceRecord Pydantic definitions, which must be aligned before release.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from typing import Any

SCHEMA_VERSION = "travelmind-stage15-provisional-v1"


def _nonnegative_int(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _usage_attempts(usage: dict[str, Any]) -> int:
    """Count attempted network calls without counting summary totals twice."""
    if "external_requests_attempted_total" in usage:
        return _nonnegative_int(usage["external_requests_attempted_total"], "external_requests_attempted_total")
    total = 0
    for key, value in usage.items():
        if key.endswith("_requests_attempted") and not key.startswith("llm_"):
            total += _nonnegative_int(value, key)
        elif key == "official_website_http_attempts":
            total += _nonnegative_int(value, key)
    return total


def _source_evidence(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only map existing field-specific evidence. Never infer from POI discovery."""
    records = []
    for p in places:
        prov = p.get("field_provenance") or {}
        if not isinstance(prov, dict):
            continue
        for field_name, items in prov.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or not item.get("url"):
                    continue
                records.append({
                    "attraction_id": p.get("attraction_id"),
                    "field": field_name,
                    "provider": item.get("provider"),
                    "publisher": item.get("publisher"),
                    "url": item.get("url"),
                    "checked_at": item.get("checked_at"),
                    "valid_through": item.get("valid_through"),
                    "status": "previously_checked_not_live_availability",
                })
    return records


def _sanitize_place(place: dict[str, Any]) -> dict[str, Any]:
    """Small candidate record matching Nirmin's confirmed field semantics."""
    p = deepcopy(place)
    cost = p.get("estimated_cost_cny")
    price_sources = (p.get("field_provenance") or {}).get("ticket_price_cny")
    if cost is not None and (type(cost) not in (int, float) or cost < 0 or not price_sources):
        # Amap cost or Baidu average price is NOT official admission price.
        cost = None
    return {
        "attraction_id": p.get("attraction_id"),
        "name": p.get("name"),
        "name_zh": p.get("name_zh"),
            "name_en": p.get("name_en"),
        "city_zh": p.get("city_zh"),
        "address_zh": p.get("address_zh"),
        "location": p.get("location"),
        "coordinate_system": p.get("coordinate_system"),
        "duration_minutes": p.get("duration_minutes"),
        "duration_status": p.get("duration_status") or "unknown",
        "estimated_cost_cny": cost,
        "cost_status": (p.get("cost_status") or "unknown") if cost is not None else "unknown",
        "cost_basis": "per_person",
        "opening_hours": p.get("opening_hours"),
        "opening_hours_today": p.get("opening_hours_today"),
        "opening_hours_status": p.get("opening_hours_status") or "unknown",
        "selection_reason": p.get("selection_reason"),
        "verification_status": p.get("verification_status"),
        "source": p.get("source"),
        "field_provenance": p.get("field_provenance") or {},
    }


def _empty_inventory() -> dict[str, Any]:
    item = {"status": "not_requested", "provider": None, "options": [],
            "real_availability_verified": False}
    return {"flights": deepcopy(item), "accommodation": deepcopy(item),
            "booking_actions_supported": False}


def compose_handoff(*, destination: dict[str, Any], context: dict[str, Any],
                    inventory: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pure composition of existing adapter results. No API/LLM calls.

    Live provider results may be passed IN MEMORY by Saieddine's coordinator;
    this function does not persist them or turn sandbox inventory into real.
    """
    if not isinstance(destination, dict) or not isinstance(context, dict):
        raise TypeError("destination and context must be dicts")
    raw_places = destination.get("places")
    if not isinstance(raw_places, list) or not all(isinstance(p, dict) for p in raw_places):
        raise ValueError("Destination must have a list of candidate place records")
    if len(raw_places) > 10:
        raise ValueError("At most 10 candidate places per handoff")
    if not isinstance(context.get("context"), dict):
        raise ValueError("Context Agent response must include a context object")
    inventory = deepcopy(inventory) if inventory is not None else None
    if inventory is not None and not isinstance(inventory.get("flights"), dict):
        raise ValueError("Inventory gateway response must include flights")
    if inventory is not None and not isinstance(inventory.get("accommodation"), dict):
        raise ValueError("Inventory gateway response must include accommodation")

    candidates = [_sanitize_place(p) for p in raw_places]
    for item in candidates:
        if not item.get("attraction_id") or not item.get("name"):
            raise ValueError("Candidate attraction must have an ID and a name")

    d_usage = deepcopy(destination.get("usage") or {})
    c_usage = deepcopy(context.get("usage") or {})
    i_usage = deepcopy((inventory or {}).get("usage") or {})
    for value in (d_usage, c_usage, i_usage):
        if not isinstance(value, dict):
            raise ValueError("Component usage must be an object")

    attempted = sum(_usage_attempts(u) for u in (d_usage, c_usage, i_usage))
    llm_attempted = sum(_nonnegative_int(u.get("llm_requests_attempted", 0), "llm_requests_attempted")
                        for u in (d_usage, c_usage, i_usage))
    llm_tokens = sum(_nonnegative_int(u.get("llm_tokens", 0), "llm_tokens")
                     if "llm_tokens" in u else
                     _nonnegative_int(u.get("llm_input_tokens", 0) or 0, "llm_input_tokens")
                     + _nonnegative_int(u.get("llm_output_tokens", 0) or 0, "llm_output_tokens")
                     for u in (d_usage, c_usage, i_usage))
    raw_context = deepcopy(context["context"])
    weather = raw_context.get("weather") or {}
    if weather.get("status") in {"simulated_not_verified", "simulated_scenario"}:
        # Do not silently imply synthetic weather is a real forecast.
        weather["is_real_forecast"] = False
    raw_context["weather"] = weather
    inv = _empty_inventory() if inventory is None else {
        "flights": deepcopy(inventory["flights"]),
        "accommodation": deepcopy(inventory["accommodation"]),
        "booking_actions_supported": False,
    }
    # Never trust a sandbox's self-description as real inventory.
    for name in ("flights", "accommodation"):
        obj = inv[name]
        if obj.get("status") in {"sandbox_results", "no_sandbox_results"}:
            obj["real_availability_verified"] = False

    request = deepcopy(destination.get("request") or {})
    output = {
        "schema_version": SCHEMA_VERSION,
        "contract_status": "provisional_awaiting_saieddine_pydantic_models",
        "request": request,
        "destination": {
            "agent": "destination_agent",
            "selection_scope": "candidates_only",
            "final_selection_owner": "itinerary_agent",
            "places": candidates,
            "quality": deepcopy(destination.get("quality") or {}),
        },
        "context": raw_context,
        "inventory": inv,
        "field_evidence_provisional": _source_evidence(candidates),
        "trace": [
            {"component": "destination_agent", "steps": deepcopy(destination.get("trace") or [])},
            {"component": "context_agent", "steps": deepcopy(context.get("trace") or [])},
            {"component": "travel_inventory_gateway", "steps": deepcopy((inventory or {}).get("trace") or [])},
            {"component": "team_handoff", "steps": [{"step": "compose", "external_requests": 0}]},
        ],
        "usage": {
            "external_requests_attempted_total": attempted,
            "llm_requests_attempted": llm_attempted,
            "llm_tokens": llm_tokens,
            "component_usage": {
                "destination": d_usage,
                "context": c_usage,
                "inventory": i_usage,
            },
        },
        "warnings": list(dict.fromkeys([
            *(destination.get("warnings") or []),
            *(context.get("warnings") or []),
            *((inventory or {}).get("warnings") or []),
            "PROVISIONAL: not validated against the team's authoritative TripRequest/EvidenceRecord models.",
            "Candidates require final selection, scheduling, and date-specific availability checks.",
            "Unknown costs remain null; verified admission cost references are per person.",
            "No booking or payment action is performed by this handoff.",
        ])),
    }
    return output


def run_offline_handoff(*, text: str, city: str = "西安市", category: str = "museum",
                        keyword: str | None = None, travel_date: str | None = None,
                        limit: int = 4, weather_demo: bool = False,
                        inventory_demo: bool = False,
                        origin_iata: str = "PEK", destination_iata: str = "XIY",
                        departure_date: str | None = None,
                        stay_nights: int = 3) -> dict[str, Any]:
    """Execute only existing offline tools. NO live flags are accepted."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Non-empty travel request text required")
    if not isinstance(city, str) or not city.strip():
        raise ValueError("City is required")
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    if travel_date:
        date.fromisoformat(travel_date)
    if type(stay_nights) is not int or not 1 <= stay_nights <= 30:
        raise ValueError("stay_nights must be 1–30")
    if inventory_demo and departure_date:
        date.fromisoformat(departure_date)

    # Late imports make it clear that the existing, tested stage modules are used.
    from data.provider_router import run_provider_search
    from data.poi_quality import filter_candidates
    from integration.candidate_handoff import provisional_itinerary_handoff

    raw = run_provider_search(text, city=city, category=category,
                              keyword=keyword, limit=limit, travel_date=travel_date,
                              live_amap=False, with_baidu=False)
    cleaned = filter_candidates(raw, keyword=keyword)
    destination = provisional_itinerary_handoff(cleaned)
    destination["trace"] = cleaned.get("trace", [])
    destination["quality"] = cleaned.get("quality")

    if weather_demo:
        from providers.weather.context import build_context
        context = build_context(city=city, travel_date=travel_date, live=False)
    else:
        from agents.context_agent import ContextAgent
        context = ContextAgent().run(city=city, travel_date=travel_date, live=False)

    inventory = None
    if inventory_demo:
        from providers.inventory.gateway import (FlightRequest, StayRequest, TravelInventoryGateway)
        when = date.fromisoformat(departure_date) if departure_date else date.today() + timedelta(days=30)
        checkout = (when + timedelta(days=stay_nights)).isoformat()
        flight = FlightRequest(origin_iata, destination_iata, when.isoformat(), 1)
        stay = StayRequest(city, when.isoformat(), checkout, 1, 1)
        inventory = TravelInventoryGateway().search(flight, stay)
    return compose_handoff(destination=destination, context=context, inventory=inventory)
