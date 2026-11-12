"""Stage 7: inspect provider coverage and build a provisional itinerary handoff.

This module NEVER sends HTTP requests or calls an LLM. It only transforms an
already obtained Stage 6 result in memory. Do not persist provider content
without authorization under the applicable provider agreement.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Any


def _has(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def evaluate_place(place: dict, *, target_name: str | None = None) -> dict:
    """Return a compact coverage assessment without changing the record."""
    from data.provider_router import same_place_name

    fields = {
        "address": _has(place.get("address_zh")),
        "coordinates": _has(place.get("location")) or _has(place.get("coordinates")),
        "weekly_opening_hours": _has(place.get("opening_hours")),
        "today_only_hours": _has(place.get("opening_hours_today")),
        "verified_ticket_price": (
            _has(place.get("ticket_price_cny"))
            and bool((place.get("field_provenance") or {}).get("ticket_price_cny"))
        ),
    }
    missing = [key for key, present in fields.items() if not present]
    return {
        "name": place.get("name_zh") or place.get("name_en"),
        "provider": (place.get("source") or {}).get("provider"),
        "exact_name_match": (
            same_place_name(place.get("name_zh"), target_name)
            if target_name else None
        ),
        "fields_available": fields,
        "missing_fields": missing,
        "hours_for_requested_future_date_confirmed": False,
        "ticket_price_cny": (
            place.get("ticket_price_cny") if fields["verified_ticket_price"] else None
        ),
        "average_spend_is_ticket_price": False,
    }


def diagnostic_summary(result: dict, *, target_name: str | None = None) -> dict:
    """Minimal safe diagnostic: no API keys and no raw POI payload."""
    places = result.get("places") or []
    covered = [evaluate_place(p, target_name=target_name) for p in places]
    metrics = {k: sum(int(p["fields_available"][k]) for p in covered)
               for k in ("address", "coordinates", "weekly_opening_hours",
                         "today_only_hours", "verified_ticket_price")}
    return {
        "stage": 7,
        "mode": result.get("mode"),
        "city": (result.get("request") or {}).get("city"),
        "places_returned": len(covered),
        "requested_exact_name": target_name,
        "coverage_counts": metrics,
        "places": covered,
        "usage": deepcopy(result.get("usage") or {}),
        "warnings": [
            "Business hours may not apply to holidays or future trip dates.",
            "Provider average-spend/price is NOT verified admission cost.",
            "These counts measure returned fields, not completeness or correctness.",
        ],
    }


def provisional_itinerary_handoff(result: dict) -> dict:
    """Create a minimal candidate list; itinerary agent decides final selection.

    The team's authoritative TripRequest/EvidenceRecord models must be used
    when available; this schema is explicitly provisional and non-binding.
    """
    candidates = []
    for p in result.get("places") or []:
        coords = p.get("location")
        if not isinstance(coords, dict) or not {"latitude", "longitude"} <= coords.keys():
            coords = None
        prov = deepcopy(p.get("field_provenance") or {})
        cost = p.get("estimated_cost_cny")
        # Our upstream module guarantees per-person verified admission only;
        # double-check provenance here so no average spend leaks into budget.
        if not prov.get("ticket_price_cny"):
            cost = None
        candidates.append({
            "attraction_id": p.get("attraction_id") or p.get("id"),
            "name": p.get("name_en") or p.get("name_zh"),
            "name_zh": p.get("name_zh"),
            "name_en": p.get("name_en"),
            "city_zh": p.get("city_zh"),
            "address_zh": p.get("address_zh"),
            "location": deepcopy(coords),
            "coordinate_system": (p.get("coordinates") or {}).get("system")
                                  if isinstance(p.get("coordinates"), dict) else None,
            "duration_minutes": p.get("duration_minutes"),
            "duration_status": p.get("duration_status") or "unknown",
            "estimated_cost_cny": cost,
            "cost_status": p.get("cost_status") if cost is not None else "unknown",
            "cost_basis": "per_person",
            "opening_hours": p.get("opening_hours"),
            "opening_hours_today": p.get("opening_hours_today"),
            "opening_hours_status": p.get("opening_hours_status") or "unknown",
            "selection_reason": p.get("selection_reason"),
            "source": deepcopy(p.get("source")),
            "field_provenance": prov,
            "verification_status": p.get("verification_status"),
        })
    return {
        "schema_version": "stage7-provisional-handoff",
        "agent": "destination_agent",
        "selection_scope": "candidates_only",
        "final_selection_owner": "itinerary_agent",
        "request": deepcopy(result.get("request")),
        "places": candidates,
        "usage": deepcopy(result.get("usage") or {}),
        "warnings": [
            "Not a replacement for the team's authoritative Pydantic contract.",
            "Unknown prices are null, never zero; cost is per person when verified.",
            "Provider hours do not confirm access on a specific travel date.",
        ],
    }
