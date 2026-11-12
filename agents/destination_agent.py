"""TravelMind Destination Agent prototype.

Default: deterministic offline processing (0 Amap calls, 0 AI tokens).
--live: authorize at most ONE Amap call, never cache its results.
--ai: authorize at most ONE OpenRouter call for request interpretation.

This module is not an itinerary planner or booking agent.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from typing import Any

from data.attractions import ATTRACTIONS
from data.dataset import normalize_city, search_amap_live, search_demo

CITY_NAMES = {
    "西安市": ("xi'an", "xian", "西安市", "西安"),
    "北京市": ("beijing", "北京市", "北京"),
    "上海市": ("shanghai", "上海市", "上海"),
    "成都市": ("chengdu", "成都市", "成都"),
    "杭州市": ("hangzhou", "杭州市", "杭州"),
    "广州市": ("guangzhou", "广州市", "广州"),
    "深圳市": ("shenzhen", "深圳市", "深圳"),
}

# Whitelist: never treat arbitrary input text as an API query/URL.
INTEREST_WORDS = {
    "history": ("history", "historical", "历史", "古迹"),
    "archaeology": ("archaeology", "archaeological", "考古"),
    "culture": ("culture", "cultural", "文化"),
    "museum": ("museum", "museums", "博物馆"),
    "architecture": ("architecture", "architectural", "建筑"),
    "photography": ("photography", "photo", "photogenic", "拍照", "摄影"),
    "food": ("food", "restaurant", "restaurants", "street food", "美食", "小吃", "餐厅"),
    "nightlife": ("nightlife", "night market", "夜景", "夜生活"),
    "shopping": ("shopping", "shops", "购物", "商场"),
}

SUPPORTED_CATEGORIES = {"museum", "attraction", "restaurant", "hotel", "heritage", "cultural_district"}
AMAP_CATEGORIES = {"museum", "attraction", "restaurant", "hotel"}


def canonical_city(city: str) -> str:
    """Normalize city labels for both offline dataset and the Amap service."""
    normalized = normalize_city(city)
    lower = normalized.casefold().replace("’", "'")
    for canonical, aliases in CITY_NAMES.items():
        if lower == canonical.casefold() or any(lower == a for a in aliases):
            return canonical
    return normalized


def contains_term(text: str, term: str) -> bool:
    """Match English whole phrases or Chinese substrings, not English fragments."""
    if re.search(r"[a-z]", term):
        return bool(re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", text))
    return term in text


def understand_locally(text: str, city: str | None = None,
                       interests: list[str] | None = None,
                       category: str | None = None) -> dict[str, Any]:
    """Small, explainable parser. No external calls; no claim of full language understanding."""
    message = text.casefold().replace("’", "'")
    matches = []
    for canonical, aliases in CITY_NAMES.items():
        if any(contains_term(message, alias) for alias in aliases):
            matches.append(canonical)
    warnings: list[str] = []
    if city:
        selected_city = canonical_city(city)
        assumed = False
    elif matches:
        selected_city = matches[0]
        assumed = False
        if len(matches) > 1:
            warnings.append("Multiple cities mentioned; using first recognized city. Confirm destination.")
    else:
        selected_city = "西安市"
        assumed = True
        warnings.append("No supported city found; defaulted to Xi'an for demonstration.")

    inferred = [tag for tag, terms in INTEREST_WORDS.items()
                if any(contains_term(message, term) for term in terms)]
    if interests:
        inferred = list(dict.fromkeys(inferred + [t.strip().casefold() for t in interests if t.strip()]))
    if category and category not in SUPPORTED_CATEGORIES:
        raise ValueError(f"Unsupported category: {category}")
    if not inferred:
        warnings.append("No recognized interests; returning general places from the local dataset.")
    # The itinerary agent is a different teammate's responsibility.
    if any(contains_term(message, term) for term in ("flight", "flights", "plane ticket", "机票")):
        warnings.append("Flight information is outside Destination Agent scope.")
    if any(contains_term(message, term) for term in ("book hotel", "hotel booking", "酒店预订")):
        warnings.append("Hotel booking is outside Destination Agent scope.")

    return {
        "city": selected_city,
        "city_assumed": assumed,
        "interests": inferred,
        "category": category,
        "warnings": warnings,
        "method": "deterministic_rules",
    }


def ai_interpret_request(text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Exactly one opt-in OpenRouter request; no agent loop, no tool-use permissions."""
    from llm.openrouter_client import OpenRouterClient, load_local_env
    from llm.intent_interpreter import parse_intent, SYSTEM
    load_local_env()
    result = OpenRouterClient().complete(system=SYSTEM, user=text, live=True)
    plan = parse_intent(result["text"], strict=True)
    return plan, {"model": result["model"], **result["usage"], "llm_trace": result["trace"]}


def normalize_live_places(records: list[dict], city: str) -> list[dict]:
    """Adapt previous AmapClient output to the shared minimal place shape."""
    normalized = []
    for item in records:
        normalized.append({
            "attraction_id": item.get("id"),
            "name_zh": item.get("name_zh") or item.get("name"),
            "name_en": item.get("name_en"),
            "city_zh": item.get("city_zh") or city,
            "category": item.get("category"),
            "tags": item.get("tags", []),
            "address_zh": item.get("address_zh") or item.get("address"),
            "coordinates": item.get("coordinates"),
            "opening_hours": item.get("opening_hours"),
            "ticket_price_cny": item.get("ticket_price_cny"),
            "source": item.get("source"),
            "verification_status": "poi_found_unverified_details",
        })
    return normalized


@dataclass
class DestinationAgent:
    """Small single-step agent with explicit budget and provider gates."""
    max_places: int = 5
    trace: list[dict[str, Any]] = field(default_factory=list)

    def run(self, destination: str, interests: list[str]) -> list[dict]:
        if destination.strip().casefold() != "chengdu":
            return []

        requested = {
            interest.strip().casefold()
            for interest in interests
            if interest.strip()
        }

        ranked = sorted(
            ATTRACTIONS,
            key=lambda place: sum(
                interest.casefold() in requested
                for interest in place["interests"]
            ),
            reverse=True,
        )

        if not requested:
            return ranked

        matches = [
            place for place in ranked
            if any(
                interest.casefold() in requested
                for interest in place["interests"]
            )
        ]

        return matches if matches else ranked

    def run_candidates(self, text: str, *, city: str | None = None,
            interests: list[str] | None = None,
            category: str | None = None,
            live: bool = False,
            ai: bool = False,
            interpreted_intent: dict[str, Any] | None = None) -> dict[str, Any]:
        if not 1 <= self.max_places <= 10:
            raise ValueError("max_places must be 1..10 to conserve output and provider quota")
        if interpreted_intent is not None and ai:
            raise ValueError("Provide parsed intent or request AI interpretation, not both")
        from llm.intent_interpreter import validate_intent, ClarificationRequired
        # Validate the complete external plan before any field access or rule parsing.
        intent = validate_intent(interpreted_intent) if interpreted_intent is not None else None
        explicit_city = None
        if city is not None and (ai or intent is not None):
            explicit_city = validate_intent({"city": city, "interests": [], "category": None})["city"]
        self.trace = []
        self.trace.append({"step": "interpret_request", "strategy": "provided_llm_intent" if intent is not None else "ai" if ai else "rules"})
        usage = {"amap_api_requests_attempted": 0, "llm_requests_attempted": 0,
                 "llm_input_tokens": 0, "llm_output_tokens": 0}
        if intent is None:
            parsed = understand_locally(text, city=city, interests=interests, category=category)
        else:
            resolved_city = intent["city"] or explicit_city
            if resolved_city is None:
                raise ClarificationRequired(usage=usage, trace=self.trace)
            parsed = {**intent, "city": resolved_city, "city_assumed": False,
                      "warnings": [], "method": "provided_llm_intent"}
        if ai:
            usage["llm_requests_attempted"] = 1
            ai_plan, measured = ai_interpret_request(text)
            ai_plan = validate_intent(ai_plan)
            usage.update(measured)
            # A rule-derived *recognized* city may resolve the request; demo defaults may not.
            resolved_city = explicit_city or ai_plan["city"] or (
                parsed["city"] if not parsed["city_assumed"] else None)
            if resolved_city is None:
                raise ClarificationRequired(usage=usage, trace=self.trace)
            parsed["city"] = resolved_city
            parsed["city_assumed"] = False
            parsed["warnings"] = [w for w in parsed["warnings"]
                                  if not w.startswith("No supported city found")]
            if not interests:
                parsed["interests"] = ai_plan["interests"]
            if not category:
                parsed["category"] = ai_plan["category"]
            parsed["method"] = "single_llm_classification"

        if live:
            # Never call Amap implicitly, never search extra pages, never request POI details.
            c = parsed["category"]
            if c not in AMAP_CATEGORIES:
                c = "museum" if parsed["interests"] == ["museum"] else "attraction"
            usage["amap_api_requests_attempted"] = 1
            self.trace.append({"step": "retrieve_places", "tool": "amap_live_search",
                               "reason": "explicit --live flag", "max_calls": 1})
            raw = search_amap_live(city=parsed["city"], category=c,
                                   keyword=None, limit=self.max_places)
            places = normalize_live_places(raw, parsed["city"])
            mode = "live_amap_transient"
            notes = ["Amap results must not be stored or added to a dataset without permission.",
                     "POI discovery does not verify opening hours, prices or availability."]
        else:
            self.trace.append({"step": "retrieve_places", "tool": "local_seed_search",
                               "reason": "offline-first default", "max_calls": 0})
            places = search_demo(city=parsed["city"], interests=parsed["interests"],
                                 category=parsed["category"], limit=self.max_places)
            mode = "offline_demo"
            notes = ["All offline records are manually authored, unverified demonstration data."]
            if not places:
                notes.append("No matching local records; no fallback to paid/live APIs was triggered.")

        for place in places:
            # Provisional candidate contract: unknown costs/durations stay null.
            for key, value in {"duration_minutes": None, "duration_status": "unknown",
                               "estimated_cost_cny": None, "cost_status": "unknown",
                               "cost_basis": "per_person", "selection_reason": "Matches requested destination and filters"}.items():
                place.setdefault(key, value)
        self.trace.append({"step": "handoff", "target": "itinerary_agent",
                           "place_count": len(places)})
        return {
            "schema_version": "1.1-draft",
            "agent": "destination_agent",
            "mode": mode,
            "request": {"text": text, "city": parsed["city"],
                        "city_assumed": parsed["city_assumed"],
                        "interests": parsed["interests"], "category": parsed["category"]},
            "places": places,
            "warnings": parsed["warnings"] + notes,
            "trace": list(self.trace),
            "usage": usage,
        }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="TravelMind cost-controlled Destination Agent")
    parser.add_argument("--text", required=True, help="Traveler's request in English or Chinese")
    parser.add_argument("--city", help="Explicit city override (optional)")
    parser.add_argument("--interests", nargs="*", default=[], help="Explicit interest tags")
    parser.add_argument("--category", choices=sorted(SUPPORTED_CATEGORIES))
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--live", action="store_true", help="Authorize one Amap live API request")
    parser.add_argument("--ai", action="store_true", help="Authorize one OpenRouter LLM request")
    args = parser.parse_args(argv)
    try:
        result = DestinationAgent(max_places=args.limit).run_candidates(
            args.text, city=args.city, interests=args.interests,
            category=args.category, live=args.live, ai=args.ai,
        )
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Destination agent failed: {type(exc).__name__}: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
