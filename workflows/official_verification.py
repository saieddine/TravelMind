"""TravelMind Stage 9 official-source verifier. Offline by default.

`--sample` uses intentionally fabricated test HTML (never merges as verified).
`--fetch-official` requests exactly one fixed official page, after robots check.
`--live-amap` is separate and still explicitly opt-in (max one map call).
"""
import argparse
import json
from providers.config import RESOURCE_ROOT

from providers.official_sources.client import fetch_official, load_registry
from providers.official_sources.extract import extract_published_claims, enrich_from_official_claims
from data.provider_router import run_provider_search
from data.poi_quality import filter_candidates
from integration.candidate_handoff import diagnostic_summary, provisional_itinerary_handoff

SAMPLES = {
    "bmy-guide": "bmy_guide_demo.html",
    "bmy-tickets": "bmy_tickets_demo.html",
    "sxhm-extended-2026": "sxhm_2026_demo.html",
}


def run_stage9(*, text, city, keyword, category="museum", limit=5, date=None,
               source_id=None, sample=False, fetch_official_page=False,
               live_amap=False, view="report", official_fetcher=None,
               provider_runner=None):
    sources = load_registry()
    if bool(sample) and bool(fetch_official_page):
        raise ValueError("Choose either --sample OR --fetch-official, not both")
    if source_id is None and (sample or fetch_official_page):
        raise ValueError("An --source is required")
    if source_id and source_id not in sources:
        raise ValueError("Unknown source; see --list-sources")
    if source_id and not (sample or fetch_official_page):
        raise ValueError("Use --sample (offline) or --fetch-official (live)")
    if source_id and (keyword != sources[source_id]["attraction_name_zh"]
                      or city != sources[source_id]["city_zh"]):
        raise ValueError("--keyword and --city must match the reviewed official source")
    # Validate date before any provider calls.
    if date:
        from datetime import date as date_class
        date_class.fromisoformat(date)
    runner = provider_runner or run_provider_search
    base = runner(text, city=city, keyword=keyword,
                  category=category, limit=limit, travel_date=date,
                  live_amap=live_amap, with_baidu=False)
    filtered = filter_candidates(base, keyword=keyword)
    filtered.setdefault("usage", {})["official_website_http_attempts"] = 0
    filtered["usage"]["llm_tokens"] = 0
    filtered.setdefault("official_verification", {"status": "not_requested", "fields_added": 0})
    claims = None
    if source_id:
        entry = sources[source_id]
        exact = any(p.get("name_zh") == keyword and p.get("city_zh") == city
                    for p in filtered["places"])
        if not exact:
            filtered["official_verification"] = {
                "status": "no_exact_place_match_no_page_request", "fields_added": 0}
        elif sample:
            fixture = RESOURCE_ROOT / "fixtures" / SAMPLES[source_id]
            claims = extract_published_claims(entry, fixture.read_text(encoding="utf-8"),
                                              mode="synthetic_fixture", travel_date=date)
            filtered = enrich_from_official_claims(filtered, claims)
        else:
            fetcher = official_fetcher or fetch_official
            fetch_result = fetcher(source_id)
            filtered["usage"]["official_website_http_attempts"] = fetch_result["http_attempts"]
            if fetch_result["status"] == "fetched":
                claims = extract_published_claims(entry, fetch_result["html"],
                                                  mode="live_official", travel_date=date)
                filtered = enrich_from_official_claims(filtered, claims)
            else:
                filtered["official_verification"] = {
                    "status": fetch_result["status"], "fields_added": 0,
                    "note": fetch_result.get("note")}
    output = (provisional_itinerary_handoff(filtered)
              if view == "handoff" else diagnostic_summary(filtered, target_name=keyword))
    output["stage"] = 9
    output["quality"] = filtered["quality"]
    output["official_verification"] = filtered["official_verification"]
    if claims is not None:
        output["official_claims"] = claims
    if view == "handoff":
        output["usage"] = filtered["usage"]
    output.setdefault("warnings", []).append(
        "Official extraction is source-specific and does not confirm live admission or date-specific closures.")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description="TravelMind Stage 9, offline by default")
    parser.add_argument("--text")
    parser.add_argument("--city", default="西安市")
    parser.add_argument("--keyword")
    parser.add_argument("--category", default="museum", choices=["museum", "attraction", "restaurant", "hotel"])
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--date", help="Travel date YYYY-MM-DD")
    parser.add_argument("--source", help="Official source_id from --list-sources")
    parser.add_argument("--list-sources", action="store_true")
    parser.add_argument("--sample", action="store_true", help="Synthetic local HTML; 0 requests and cannot verify facts")
    parser.add_argument("--fetch-official", action="store_true", help="Explicitly allow a robots check + ONE official page")
    parser.add_argument("--live-amap", action="store_true", help="Explicitly allow ONE Amap V5 request")
    parser.add_argument("--view", choices=["report", "handoff"], default="report")
    a = parser.parse_args(argv)
    if a.list_sources:
        print(json.dumps([{"source_id": sid, "attraction": val["attraction_name_zh"],
                           "url": val["url"]} for sid, val in load_registry().items()],
                         ensure_ascii=False, indent=2))
        return
    if not a.text:
        parser.error("--text is required")
    try:
        result = run_stage9(text=a.text, city=a.city, keyword=a.keyword,
                            category=a.category, limit=a.limit, date=a.date,
                            source_id=a.source, sample=a.sample,
                            fetch_official_page=a.fetch_official,
                            live_amap=a.live_amap, view=a.view)
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Stage 9 failed: {type(exc).__name__}: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
