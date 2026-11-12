"""Minimal field adapters; authoritative teammate schemas are supplied, never copied."""
from copy import deepcopy
from math import isfinite


def to_itinerary_places(places, *, attraction_model=None):
    if not isinstance(places, list):
        raise ValueError("places must be a list")
    output = []
    for index, original in enumerate(places):
        if not isinstance(original, dict):
            raise ValueError(f"places[{index}] must be an object")
        p = deepcopy(original)
        p["id"] = p.get("id") or p.get("attraction_id")
        p["attraction_id"] = p.get("attraction_id") or p["id"]
        if not isinstance(p.get("coordinates"), dict) and isinstance(p.get("location"), dict):
            p["coordinates"] = deepcopy(p["location"])
            if p.get("coordinate_system"):
                p["coordinates"].setdefault("system", p["coordinate_system"])
        if p.get("estimated_cost_cny") is not None and p.get("cost_basis", "per_person") != "per_person":
            raise ValueError("Only per-person candidate costs may enter the itinerary")
        p["cost_basis"] = "per_person"
        for value_key, status_key in (("duration_minutes", "duration_status"), ("estimated_cost_cny", "cost_status")):
            value = p.get(value_key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not isfinite(value) or value < 0
                                      or value_key == "duration_minutes" and (not isinstance(value, int) or value <= 0)):
                raise ValueError(f"Invalid {value_key} at places[{index}]")
            status = p.get(status_key)
            status = status if isinstance(status, str) else "unknown"
            p[status_key] = ("unknown" if value is None else status
                             if status in {"verified", "estimated", "unknown"} else
                             "estimated" if status == "official_admission_reference_check_eligibility" else "unknown")
            if p[status_key] == "unknown":
                p[value_key] = None
        if not isinstance(p.get("source"), dict):
            p["source"] = {"provider": p["source"]} if isinstance(p.get("source"), str) else {}
        if attraction_model is not None:
            # Validates the actual teammate type, including required names. No synthetic translations.
            attraction_model.model_validate(p)
        output.append(p)
    return output


def to_legacy_itinerary_places(places):
    """The main-branch planner requires known numeric values; null never means zero."""
    output = []
    for p in to_itinerary_places(places):
        duration, cost = p.get("duration_minutes"), p.get("estimated_cost_cny")
        if duration is None or cost is None or p["duration_status"] == "unknown" or p["cost_status"] == "unknown":
            raise ValueError("Legacy itinerary requires known duration and per-person cost; clarification required")
        name = p.get("name_en") or p.get("name_zh") or p.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Legacy itinerary requires an attraction name")
        output.append({**p, "name": name, "duration_hours": duration / 60, "entry_cost": cost})
    return output
