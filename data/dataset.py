"""TravelMind destination data layer.

Offline by default. Does not write Amap data to disk.
The bundled seed is independently authored, unverified DEMO data.
"""

import argparse
import json
from providers.config import RESOURCE_ROOT

SEED_PATH = RESOURCE_ROOT / "attractions_seed.json"
CITY_ALIASES = {
    "xian": "西安市", "xi'an": "西安市", "xi’an": "西安市",
    "xi'an city": "西安市", "西安": "西安市", "西安市": "西安市",
}


def normalize_city(city):
    stripped = city.strip()
    return CITY_ALIASES.get(stripped.casefold(), stripped)


def load_demo_attractions():
    """Load our own offline demonstration records: zero network traffic."""
    records = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    ids = [p["attraction_id"] for p in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate attraction_id in seed dataset")
    return records


def search_demo(city, interests=(), category=None, limit=5):
    """Deterministic, local matching: zero tokens and zero API calls."""
    canonical_city = normalize_city(city)
    interests_set = {t.strip().casefold() for t in interests if t.strip()}
    candidates = []
    for place in load_demo_attractions():
        if place["city_zh"] != canonical_city:
            continue
        if category and place["category"] != category:
            continue
        tags = {t.casefold() for t in place["tags"]}
        matches = len(tags & interests_set)
        if interests_set and matches == 0:
            continue
        candidates.append((matches, place))

    # Stable tie order: curated seed order.
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    places = []
    for matches, place in candidates[:limit]:
        # Make a shallow copy so we don't mutate seed objects.
        places.append({**place, "interest_match_count": matches})
    return places


def search_amap_live(city, category, keyword, limit):
    """Exactly one explicit API search. Returns live results only in memory.

    No caching, local database write, or dataset export. Apply Amap's
    terms and service presentation requirements to any integration.
    """
    from providers.amap.client import AmapClient  # Imported only with --live.

    # AmapClient.search_places() from the previous stage makes one request.
    # We do not call a details endpoint or request more pages.
    return AmapClient().search_places(
        city=normalize_city(city),
        category=category,
        keyword=keyword,
        limit=limit,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="TravelMind destination search (offline by default)."
    )
    parser.add_argument("--city", default="西安市")
    parser.add_argument("--interests", nargs="*", default=[])
    parser.add_argument("--category", default=None)
    parser.add_argument("--keyword", default=None)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--live", action="store_true",
        help="Explicitly make ONE live Amap search request; never saves results.",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= 25:
        parser.error("--limit must be between 1 and 25")

    if args.live:
        live_category = args.category or "attraction"
        try:
            places = search_amap_live(
                city=args.city,
                category=live_category,
                keyword=args.keyword,
                limit=args.limit,
            )
        except (RuntimeError, ValueError) as err:
            parser.exit(1, f"Amap search failed: {err}\n")
        source = "amap_live"
        calls = 1
        note = "Live data: shown temporarily; not saved or cached."
    else:
        places = search_demo(
            city=args.city,
            interests=args.interests,
            category=args.category,
            limit=args.limit,
        )
        source = "manually_authored_demo"
        calls = 0
        note = (
            "Offline demo records; details are not independently verified. "
            "Do not treat as live availability, price, or opening hours."
        )

    result = {
        "schema_version": "1.0",
        "city": normalize_city(args.city),
        "mode": source,
        "places": places,
        "usage": {"amap_api_requests_attempted": calls, "llm_tokens": 0},
        "note": note,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
