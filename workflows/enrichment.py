"""Stage 5 demo: destination retrieval -> curated official-source enrichment.

Offline by default. --live delegates at most one Amap query to the existing
Stage 3 DestinationAgent. No OpenRouter/LLM mode is exposed here.
"""

import argparse
import json
from agents.destination_agent import DestinationAgent
from data.enrichment import enrich_places
from datetime import date


def run(text: str, *, city: str | None = None, limit: int = 5,
        travel_date: str | None = None, live: bool = False) -> dict:
    # Validate before any optional provider request. A malformed date must
    # never consume a user's Amap quota.
    if travel_date:
        date.fromisoformat(travel_date)
    output = DestinationAgent(max_places=limit).run_candidates(
        text, city=city, live=live, ai=False
    )
    output["places"], summary = enrich_places(output["places"], travel_date=travel_date)
    output["schema_version"] = "1.2-draft"
    output["enrichment"] = summary
    output["trace"].insert(-1, {
        "step": "enrich_official_details",
        "tool": "curated_official_sources_local",
        "network_calls": 0,
        "llm_requests": 0,
    })
    output["warnings"].append(
        "Verified fields are sourced snapshots. Travel date, opening hours, "
        "prices and ticket availability require rechecking before actual visits."
    )
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description="TravelMind Stage 5 verified-facts enrichment")
    parser.add_argument("--text", required=True)
    parser.add_argument("--city", help="Explicit destination city, if not in text")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--date", dest="travel_date", help="Travel date YYYY-MM-DD")
    parser.add_argument("--live", action="store_true", help="Authorize at most one Amap request")
    args = parser.parse_args(argv)
    try:
        output = run(args.text, city=args.city, limit=args.limit,
                     travel_date=args.travel_date, live=args.live)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Enrichment failed: {type(exc).__name__}: {exc}\n")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return output


if __name__ == "__main__":
    main()
