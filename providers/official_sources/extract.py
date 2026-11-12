"""Conservative, deterministic extraction of *published claims* from a known official page.

No web access, no LLM, no automatic confirmation of date-specific availability.
Each parser is specific to a reviewed source and returns nothing if its expected
labels are absent. Synthetic fixtures are never represented as real evidence.
"""
from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timezone, date
from html.parser import HTMLParser


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.ignored += 1
        if tag in ("p", "div", "h1", "h2", "li", "td", "tr", "br", "section"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.ignored:
            self.ignored -= 1
        if tag in ("p", "div", "h1", "h2", "li", "td", "tr", "section"):
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def visible_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


HOUR_RANGE = r"((?:[01]?\d|2[0-3]):[0-5]\d\s*[-—–~至]\s*(?:[01]?\d|2[0-3]):[0-5]\d)"


def _bmy_guide(text: str) -> dict:
    # Both seasons must be present; prevent mistaking a closing time for admission hours.
    summer = re.search(r"旺季.{0,130}?" + HOUR_RANGE, text)
    winter = re.search(r"淡季.{0,130}?" + HOUR_RANGE, text)
    if not (summer and winter and "3月16日" in text and "11月16日" in text):
        return {}
    return {
        "opening_hours": (
            f"3月16日–11月15日 {summer.group(1)}; "
            f"11月16日–次年3月15日 {winter.group(1)} (官方页面公布的检票/入园时段，假期需复核)"
        )
    }


def _bmy_tickets(text: str) -> dict:
    ticket = re.search(r"普通成人票\s*(\d+(?:\.\d+)?)\s*元", text)
    if not ("秦始皇帝陵博物院" in text and ticket):
        return {}
    number = float(ticket.group(1))
    if not 0 <= number <= 5000:
        return {}
    fields = {"ticket_price_cny": int(number) if number.is_integer() else number}
    if "预约" in text and ("官方网站" in text or "官方微信公众号" in text):
        fields["booking_required"] = True
    return fields


def _sxhm_hours(text: str) -> dict:
    # This is an explicit dated *2026 announcement*, not a generic weekly schedule.
    if "2026年3月15日" not in text or "2026年11月14日" not in text:
        return {}
    if "陕西历史博物馆" not in text:
        return {}
    hours = re.search(r"(?:本馆|开放时间调整为).{0,80}?" + HOUR_RANGE, text)
    if not hours:
        return {}
    return {
        "opening_hours": f"2026-03-15–2026-11-14: {hours.group(1)} (本馆; 期外及节假日另查公告)"
    }


PARSERS = {
    "bmy_guide_seasonal_hours": _bmy_guide,
    "bmy_tickets_adult": _bmy_tickets,
    "sxhm_2026_hours": _sxhm_hours,
}


def extract_published_claims(entry: dict, html: str, *, mode: str,
                             travel_date: str | None = None, now: str | None = None) -> dict:
    """Extract source-specific fields, retaining evidence and applicability warnings.

    `mode` must be either `live_official` or `synthetic_fixture`.
    No extracted claim is represented as confirmed future-date access.
    """
    if mode not in ("live_official", "synthetic_fixture"):
        raise ValueError("Unknown extraction mode")
    when = date.fromisoformat(travel_date) if travel_date else None
    parser = PARSERS.get(entry.get("parser"))
    if parser is None:
        raise ValueError("Source parser not implemented")
    text = visible_text(html)
    if entry["attraction_name_zh"] not in text:
        fields = {}
        warning = "Official page did not contain exact attraction name; no facts extracted"
    else:
        fields = parser(text)
        warning = None
    # Source-specific validity. An already ended special schedule must never be
    # presented as valid for a trip outside its announced date range.
    applicable = True
    if entry["parser"] == "sxhm_2026_hours" and when:
        applicable = date(2026, 3, 15) <= when <= date(2026, 11, 14)
        if not applicable:
            warning = "The published 2026 special hours do NOT cover this travel date"
    if not applicable:
        fields.pop("opening_hours", None)
    timestamp = now or datetime.now(timezone.utc).isoformat()
    notes = []
    if warning:
        notes.append(warning)
    if not fields:
        notes.append("No safely extractable current facts; source may use JS or changed its page layout")
    if mode == "synthetic_fixture":
        notes.append("SYNTHETIC TEST DOCUMENT: claims must never be treated as verified live facts")
    notes.append("Published hours are not guaranteed on holidays, closures or future dates")
    per_field = {}
    for field, val in fields.items():
        per_field[field] = {
            "provider": "official_attraction_website",
            "publisher": entry["publisher"],
            "url": entry["url"] if mode == "live_official" else None,
            "retrieved_at": timestamp if mode == "live_official" else None,
            "method": "source_specific_rule",
            "status": "official_page_auto_extracted" if mode == "live_official" else "synthetic_test_only",
            "scope": "adult_general_reference_not_booking" if field == "ticket_price_cny" else
                     "general_or_announced_hours_not_future_confirmation" if field == "opening_hours" else
                     "published_reservation_rule",
        }
    return {
        "source_id": entry["source_id"], "source_url": entry["url"] if mode == "live_official" else None,
        "publisher": entry["publisher"], "attraction_name_zh": entry["attraction_name_zh"],
        "city_zh": entry["city_zh"], "extraction_mode": mode,
        "fields": fields, "field_provenance": per_field,
        "warnings": notes,
        "future_date_confirmed": False,
        "claims_are_live": mode == "live_official",
    }


def enrich_from_official_claims(result: dict, claims: dict) -> dict:
    """Apply only live published facts to an exact same-name, same-city POI.

    Never overwrite existing facts, never turn unknown price into zero, and never
    merge Amap/Baidu POI identities. No network calls.
    """
    out = deepcopy(result)
    out.setdefault("official_verification", {})
    if not claims.get("claims_are_live"):
        out["official_verification"] = {"status": "synthetic_not_applied", "fields_added": 0}
        return out
    count = 0
    for place in out.get("places", []):
        if (place.get("name_zh") != claims.get("attraction_name_zh")
                or place.get("city_zh") != claims.get("city_zh")):
            continue
        place.setdefault("field_provenance", {})
        place.setdefault("verified_detail_sources", [])
        for field, value in claims["fields"].items():
            if place.get(field) is not None:
                continue
            place[field] = value
            prov = claims["field_provenance"][field]
            place["field_provenance"][field] = [deepcopy(prov)]
            count += 1
            if field == "ticket_price_cny":
                place["estimated_cost_cny"] = value
                place["cost_status"] = "official_published_adult_reference_check_eligibility"
                place["cost_basis"] = "per_person"
            if field == "opening_hours":
                place["opening_hours_status"] = "official_page_auto_extracted_not_date_confirmed"
        if claims["fields"]:
            src = {"provider": "official_attraction_website", "url": claims["source_url"],
                   "retrieved_at": next(iter(claims["field_provenance"].values()))["retrieved_at"]}
            if src not in place["verified_detail_sources"]:
                place["verified_detail_sources"].append(src)
    out["official_verification"] = {"status": "live_page_processed", "fields_added": count,
                                    "source_id": claims["source_id"], "warnings": claims["warnings"]}
    out.setdefault("trace", []).append({"step": "official_source_extraction", "llm_calls": 0})
    return out
