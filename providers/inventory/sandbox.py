"""TravelMind Stage 13: guarded flight sandbox and offline accommodation examples.

No external call occurs unless explicitly requested by the CLI.
The fixtures below are synthetic and are NOT bookable offers.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Any

DUFFEL_FLIGHTS_URL = "https://api.duffel.com/air/offer_requests"


def validate_search(origin: str, destination: str, departure_date: str, adults: int) -> dict[str, Any]:
    origin, destination = origin.upper().strip(), destination.upper().strip()
    if len(origin) != 3 or len(destination) != 3 or not origin.isalpha() or not destination.isalpha():
        raise ValueError("Flight origin/destination must be three-letter IATA airport codes")
    if origin == destination:
        raise ValueError("Flight origin and destination must differ")
    parsed_date = date.fromisoformat(departure_date)
    if parsed_date <= date.today():
        raise ValueError("Departure must be a future date; no request was made")
    if not 1 <= adults <= 8:
        raise ValueError("Adults must be in the range 1–8")
    return {"origin": origin, "destination": destination, "departure_date": parsed_date.isoformat(), "adults": adults}


def normalize_duffel_offer(offer: dict[str, Any], *, sandbox: bool) -> dict[str, Any]:
    slices = offer.get("slices") or []
    segments = [segment for s in slices for segment in (s.get("segments") or [])]
    carriers = sorted({str((seg.get("operating_carrier") or {}).get("name")) for seg in segments
                       if (seg.get("operating_carrier") or {}).get("name")})
    return {
        "offer_id": offer.get("id"),
        "total_amount": offer.get("total_amount"),
        "total_currency": offer.get("total_currency"),
        "expires_at": offer.get("expires_at"),
        "operating_carriers": carriers,
        "segment_count": len(segments),
        "is_sandbox": sandbox,
        "is_real_quote": not sandbox,
        "status": "sandbox_test_data" if sandbox else "provider_offer_unconfirmed",
        "booking_permitted": False,  # We do not support booking in Stage 13.
    }


def offline_demo(origin: str = "XIY", destination: str = "PVG", departure_date: str = "2026-12-10", adults: int = 1) -> dict[str, Any]:
    search = validate_search(origin, destination, departure_date, adults)
    return {
        "schema_version": "1.1-draft", "component": "travel_inventory_adapter",
        "mode": "offline_synthetic",
        "request": search,
        "flights": {
            "status": "synthetic_contract_example",
            "offers": [{"offer_id": "demo_flight_001", "total_amount": None, "total_currency": None,
                        "operating_carriers": [], "segment_count": None, "expires_at": None,
                        "is_sandbox": True, "is_real_quote": False, "booking_permitted": False}],
            "message": "No flight price or schedule is asserted by this synthetic example."
        },
        "accommodation": {
            "status": "synthetic_contract_example",
            "city": "Xi'an", "hotel_name": "Demo hotel (not a real listing)",
            "check_in": None, "check_out": None,
            "total_price": None, "currency": None,
            "availability_verified": False,
            "source": {"provider": "manually_authored_demo", "is_live": False},
            "message": "Live hotel API is not connected; Duffel Stays needs separate access approval."
        },
        "usage": {"duffel_requests_attempted": 0, "amap_requests_attempted": 0,
                  "baidu_requests_attempted": 0, "llm_requests_attempted": 0, "llm_tokens": 0},
        "warnings": ["Offline example only; do not show as real flight or hotel inventory."]
    }


def search_duffel_test_flights(*, origin: str, destination: str, departure_date: str,
                               adults: int = 1, max_displayed_offers: int = 5,
                               token: str | None = None, post=None) -> dict[str, Any]:
    """At most one Duffel TEST-mode HTTP POST; no retries or booking actions."""
    search = validate_search(origin, destination, departure_date, adults)
    if not 1 <= max_displayed_offers <= 10:
        raise ValueError("max_displayed_offers must be between 1 and 10")
    token = token or os.environ.get("DUFFEL_TEST_TOKEN", "")
    if not token.startswith("duffel_test_"):
        raise ValueError("DUFFEL_TEST_TOKEN is required and must be a test-mode token; no call made")
    if post is None:
        import requests
        post = requests.post

    body = {"data": {
        "slices": [{"origin": search["origin"], "destination": search["destination"],
                    "departure_date": search["departure_date"]}],
        "passengers": [{"type": "adult"} for _ in range(search["adults"])],
        "cabin_class": "economy",
    }}
    headers = {"Authorization": f"Bearer {token}", "Duffel-Version": "v2",
               "Content-Type": "application/json", "Accept": "application/json",
               "Accept-Encoding": "gzip"}
    usage = {"duffel_requests_attempted": 1, "amap_requests_attempted": 0,
             "baidu_requests_attempted": 0, "llm_requests_attempted": 0, "llm_tokens": 0}
    try:
        response = post(DUFFEL_FLIGHTS_URL,
                        params={"return_offers": "true", "supplier_timeout": 10000},
                        json=body, headers=headers, timeout=35)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        # Do not render an exception body, which could inadvertently reveal headers or tokens.
        return {"schema_version": "1.1-draft", "component": "travel_inventory_adapter",
                "mode": "live_duffel_test_sandbox", "request": search,
                "flights": {"status": "request_failed", "offers": []}, "usage": usage,
                "warnings": [f"Duffel test request failed ({type(exc).__name__}). No real booking was attempted."]}
    data = payload.get("data") or {}
    offers = data.get("offers") or []
    if not isinstance(offers, list):
        offers = []
    normalized = [normalize_duffel_offer(o, sandbox=True) for o in offers[:max_displayed_offers] if isinstance(o, dict)]
    return {
        "schema_version": "1.1-draft", "component": "travel_inventory_adapter",
        "mode": "live_duffel_test_sandbox", "request": search,
        "flights": {"status": "sandbox_offers_returned" if normalized else "no_sandbox_offers",
                    "offers": normalized, "provider_offer_count": len(offers),
                    "provider": "duffel", "is_real_inventory": False,
                    "request_id": data.get("id")},
        "accommodation": {"status": "not_connected_requires_access_approval", "availability_verified": False},
        "source": {"provider": "duffel", "endpoint": DUFFEL_FLIGHTS_URL,
                   "retrieved_at": datetime.now(timezone.utc).isoformat(), "is_live": False,
                   "environment": "developer_test_mode"},
        "usage": usage,
        "warnings": ["Duffel test offers may use fictional flights, schedules or prices and MUST NOT be displayed as real availability.",
                     "China domestic-route coverage cannot be established from a single sandbox search."]
    }
