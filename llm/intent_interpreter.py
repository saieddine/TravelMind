"""Conservative LLM intent interpreter. Outputs *selection hints*, never travel facts."""
from __future__ import annotations

import json
import re
from typing import Any

INTERESTS = frozenset({"history", "archaeology", "culture", "museum", "architecture",
                       "photography", "food", "nightlife", "shopping"})
CATEGORIES = frozenset({"museum", "attraction", "restaurant", "hotel", "heritage", "cultural_district"})
# This demo supports only recognized destinations; expansion requires an agreed city resolver.
CITIES = {"西安市": "西安市", "西安": "西安市", "xi'an": "西安市", "xian": "西安市",
          "北京市": "北京市", "北京": "北京市", "beijing": "北京市",
          "上海市": "上海市", "上海": "上海市", "shanghai": "上海市",
          "成都市": "成都市", "成都": "成都市", "chengdu": "成都市",
          "杭州市": "杭州市", "杭州": "杭州市", "hangzhou": "杭州市",
          "广州市": "广州市", "广州": "广州市", "guangzhou": "广州市",
          "深圳市": "深圳市", "深圳": "深圳市", "shenzhen": "深圳市"}
SYSTEM = (
    "Extract travel planning intent. Return only a compact JSON object with keys "
    "city, interests, category. City must be one of Xi'an, Beijing, Shanghai, "
    "Chengdu, Hangzhou, Guangzhou, Shenzhen (Chinese or English) or null. "
    "Interests is a list chosen only from history, archaeology, culture, museum, "
    "architecture, photography, food, nightlife, shopping. Category must be "
    "museum, attraction, restaurant, hotel, heritage, cultural_district, or null. "
    "No invented prices, opening times, facts, citations, tools or recommendations."
)


class IntentValidationError(ValueError):
    """Structurally invalid intent; callers may handle it as ordinary ValueError."""
    code = "invalid_intent"


class ClarificationRequired(ValueError):
    """Valid intent lacks a destination; no attraction retrieval was attempted."""
    code = "clarification_required"

    def __init__(self, *, usage=None, trace=None):
        from copy import deepcopy
        super().__init__("LLM intent has no destination; clarification required")
        self.field = "city"
        self.places = []
        self.usage = deepcopy(usage or {})
        self.trace = deepcopy(trace or [])


def validate_intent(value: Any, *, allow_metadata: bool = True) -> dict[str, Any]:
    """Validate all fields before normalization, accepting only known parser metadata."""
    required = {"city", "interests", "category"}
    metadata = {"status", "contains_verified_travel_facts"} if allow_metadata else set()
    if not isinstance(value, dict) or not required <= value.keys() or value.keys() - required - metadata:
        raise IntentValidationError("LLM intent must contain city, interests, category and no unexpected fields")
    city, interests, category = value["city"], value["interests"], value["category"]
    if (city is not None and (not isinstance(city, str) or not city.strip())
            or not isinstance(interests, list)
            or any(not isinstance(x, str) for x in interests)
            or category is not None and not isinstance(category, str)):
        raise IntentValidationError("LLM intent fields failed validation; no retry made")
    if ("status" in value and value["status"] != "parsed_whitelisted_intent"
            or "contains_verified_travel_facts" in value and value["contains_verified_travel_facts"] is not False):
        raise IntentValidationError("LLM intent metadata failed validation")
    if (city is not None and city.casefold().strip() not in CITIES
            or any(x not in INTERESTS for x in interests)
            or category is not None and category not in CATEGORIES):
        raise IntentValidationError("LLM intent values are outside the supported whitelist")
    return {"city": CITIES[city.casefold().strip()] if city is not None else None,
            "interests": list(dict.fromkeys(interests))[:6], "category": category,
            "status": "parsed_whitelisted_intent", "contains_verified_travel_facts": False}


def parse_intent(text: str, *, strict: bool = False) -> dict[str, Any]:
    if not isinstance(text, str):
        raise IntentValidationError("LLM intent output must be text")
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        raise IntentValidationError("LLM intent output was not valid JSON; no retry made") from None
    if strict:
        return validate_intent(parsed, allow_metadata=False)
    if not isinstance(parsed, dict):
        raise IntentValidationError("LLM intent must be an object")
    city_raw = parsed.get("city")
    city = CITIES.get(city_raw.casefold().strip()) if isinstance(city_raw, str) else None
    raw_interests = parsed.get("interests")
    interests = list(dict.fromkeys(x for x in (raw_interests if isinstance(raw_interests, list) else [])
                                   if isinstance(x, str) and x in INTERESTS))[:6]
    category = parsed.get("category")
    if not isinstance(category, str) or category not in CATEGORIES:
        category = None
    return {"city": city, "interests": interests, "category": category,
            "status": "parsed_whitelisted_intent", "contains_verified_travel_facts": False}
