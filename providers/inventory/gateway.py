"""TravelMind Stage 14: provider-neutral flight/stay gateway.

Zero external calls by default. No live credentials needed. This is a draft
team-handoff schema, not an airline/hotel booking product.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Protocol
import re

SCHEMA_VERSION = "1.1-draft"
IATA_RE = re.compile(r"^[A-Z]{3}$", re.ASCII)

PROVIDER_STATUS = {
    "qunar": {
        "access": "approval_pending",
        "supported_workflows_to_evaluate": ["domestic_flights", "trains", "hotels"],
        "currently_callable": False,
        "note": "Educational partner API inquiry sent; no credentials or contracted interface yet.",
    },
    "duffel_flights_test": {
        "access": "test_token_optional",
        "supported_workflows_to_evaluate": ["flight_search_sandbox"],
        "currently_callable": "only_with_explicit_flag_and_test_token",
        "note": "Sandbox offers are not real availability or price quotations.",
    },
    "hotels": {
        "access": "no_approved_live_provider",
        "supported_workflows_to_evaluate": ["hotel_search"],
        "currently_callable": False,
        "note": "Hotel results stay unavailable until an authorized provider is connected.",
    },
}


def _iso_future(value: str, field: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be ISO YYYY-MM-DD") from None
    if parsed <= date.today():
        raise ValueError(f"{field} must be after today; no request made")
    return parsed.isoformat()


@dataclass(frozen=True)
class FlightRequest:
    origin_iata: str
    destination_iata: str
    departure_date: str
    adults: int = 1

    def validated(self) -> "FlightRequest":
        origin = self.origin_iata.strip().upper()
        destination = self.destination_iata.strip().upper()
        if not IATA_RE.fullmatch(origin) or not IATA_RE.fullmatch(destination):
            raise ValueError("Airport codes must contain exactly 3 ASCII letters")
        if origin == destination:
            raise ValueError("Origin and destination must be different")
        if not isinstance(self.adults, int) or isinstance(self.adults, bool) or not 1 <= self.adults <= 8:
            raise ValueError("adults must be an integer from 1 to 8")
        return FlightRequest(origin, destination, _iso_future(self.departure_date, "departure_date"), self.adults)

    def to_dict(self) -> dict[str, Any]:
        return {"origin_iata": self.origin_iata, "destination_iata": self.destination_iata,
                "departure_date": self.departure_date, "adults": self.adults}


@dataclass(frozen=True)
class StayRequest:
    city: str
    check_in: str
    check_out: str
    guests: int = 1
    rooms: int = 1

    def validated(self) -> "StayRequest":
        city = self.city.strip()
        if not city or len(city) > 100:
            raise ValueError("Accommodation city must be 1-100 characters")
        start = _iso_future(self.check_in, "check_in")
        end = _iso_future(self.check_out, "check_out")
        if end <= start:
            raise ValueError("check_out must be later than check_in")
        if not isinstance(self.guests, int) or isinstance(self.guests, bool) or not 1 <= self.guests <= 8:
            raise ValueError("guests must be an integer from 1 to 8")
        if not isinstance(self.rooms, int) or isinstance(self.rooms, bool) or not 1 <= self.rooms <= 4:
            raise ValueError("rooms must be an integer from 1 to 4")
        if self.rooms > self.guests:
            raise ValueError("rooms cannot exceed guests in this prototype")
        return StayRequest(city, start, end, self.guests, self.rooms)

    def to_dict(self) -> dict[str, Any]:
        return {"city": self.city, "check_in": self.check_in, "check_out": self.check_out,
                "guests": self.guests, "rooms": self.rooms}


class FlightProvider(Protocol):
    provider_id: str

    def search(self, request: FlightRequest) -> dict[str, Any]:
        """Return standardized flight result (no booking actions)."""
        ...


class StayProvider(Protocol):
    provider_id: str

    def search(self, request: StayRequest) -> dict[str, Any]:
        """Return standardized accommodation result (no booking actions)."""
        ...


def _empty_flights(reason: str = "no_approved_live_provider") -> dict[str, Any]:
    return {"status": "provider_not_connected", "provider": None, "options": [],
            "reason": reason, "real_availability_verified": False,
            "source": None, "external_requests_attempted": 0}


def _empty_stays(reason: str = "no_approved_live_provider") -> dict[str, Any]:
    return {"status": "provider_not_connected", "provider": None, "options": [],
            "reason": reason, "real_availability_verified": False,
            "source": None, "external_requests_attempted": 0}


class DuffelSandboxFlightProvider:
    """Explicit adapter for Stage 13's 1-POST Duffel test-mode function.

    Test tokens only. No real flight inventory, bookings or payments.
    """
    provider_id = "duffel_flights_test"

    def __init__(self, *, token: str | None = None, search_function: Callable[..., dict[str, Any]] | None = None):
        self.token = token
        self.search_function = search_function

    def search(self, request: FlightRequest) -> dict[str, Any]:
        import os
        token = self.token or os.getenv("DUFFEL_TEST_TOKEN", "")
        if not token.startswith("duffel_test_"):
            raise ValueError("A DUFFEL_TEST_TOKEN is required; no request was made")
        if self.search_function is None:
            from providers.inventory.sandbox import search_duffel_test_flights
            search_function = search_duffel_test_flights
        else:
            search_function = self.search_function
        response = search_function(
            origin=request.origin_iata,
            destination=request.destination_iata,
            departure_date=request.departure_date,
            adults=request.adults,
            token=token,
            max_displayed_offers=5,
        )
        raw = (response.get("flights") or {})
        offers = raw.get("offers") or []
        options = []
        for offer in offers[:5]:
            if not isinstance(offer, dict):
                continue
            options.append({
                "provider_offer_id": offer.get("offer_id"),
                "origin_iata": request.origin_iata,
                "destination_iata": request.destination_iata,
                "departure_date": request.departure_date,
                "adult_count": request.adults,
                "total_amount": offer.get("total_amount"),
                "currency": offer.get("total_currency"),
                "price_scope": "total_for_requested_passengers",
                "operating_carriers": offer.get("operating_carriers") or [],
                "segment_count": offer.get("segment_count"),
                "quote_expires_at": offer.get("expires_at"),
                "data_kind": "sandbox_not_real_inventory",
                "real_availability_verified": False,
                "booking_permitted": False,
            })
        request_count = int((response.get("usage") or {}).get("duffel_requests_attempted", 0))
        request_count = min(max(request_count, 0), 1)
        return {
            "status": "sandbox_results" if options else ("request_failed" if raw.get("status") == "request_failed" else "no_sandbox_results"),
            "provider": self.provider_id, "options": options,
            "real_availability_verified": False,
            "source": {"provider": "duffel", "environment": "test", "is_real_inventory": False,
                       "retrieved_at": (response.get("source") or {}).get("retrieved_at")},
            "external_requests_attempted": request_count,
        }


def _validate_provider_result(payload: dict[str, Any], *, kind: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError(f"{kind} provider must return dict")
    status = payload.get("status")
    if status not in {"sandbox_results", "no_sandbox_results", "provider_results", "no_results", "request_failed"}:
        raise ValueError(f"Unsupported {kind} provider status: {status}")
    options = payload.get("options")
    if not isinstance(options, list):
        raise ValueError(f"{kind} options must be a list")
    calls = payload.get("external_requests_attempted", 0)
    if type(calls) is not int or calls < 0:
        raise ValueError("external_requests_attempted must be nonnegative integer")
    if not isinstance(payload.get("provider"), str) or not payload.get("provider"):
        raise ValueError("Provider identifier is required")
    if payload.get("real_availability_verified") and status != "provider_results":
        raise ValueError("Sandbox records cannot claim real inventory")
    return payload


class TravelInventoryGateway:
    """Deterministic offline-first integration layer for team handoff.

    No agent/LLM calls here; flight/stay providers are passed explicitly.
    """

    def __init__(self, flight_provider: FlightProvider | None = None,
                 stay_provider: StayProvider | None = None):
        self.flight_provider = flight_provider
        self.stay_provider = stay_provider

    def search(self, flight: FlightRequest, stay: StayRequest) -> dict[str, Any]:
        # Validate all inputs before touching any provider. No partial requests.
        validated_flight = flight.validated()
        validated_stay = stay.validated()
        trace = [{"step": "validate_requests", "external_requests": 0}]
        flights = _empty_flights("Qunar partnership pending; optional Duffel test mode only")
        accommodation = _empty_stays("Hotel live provider not connected")

        if self.flight_provider is not None:
            flights = _validate_provider_result(self.flight_provider.search(validated_flight), kind="flight")
            trace.append({"step": "flight_search", "provider": flights["provider"],
                          "external_requests": flights.get("external_requests_attempted", 0)})
        else:
            trace.append({"step": "flight_search_skipped", "reason": "no_flight_provider", "external_requests": 0})
        if self.stay_provider is not None:
            accommodation = _validate_provider_result(self.stay_provider.search(validated_stay), kind="stay")
            trace.append({"step": "stay_search", "provider": accommodation["provider"],
                          "external_requests": accommodation.get("external_requests_attempted", 0)})
        else:
            trace.append({"step": "stay_search_skipped", "reason": "no_stay_provider", "external_requests": 0})

        flight_calls = flights["external_requests_attempted"]
        stay_calls = accommodation["external_requests_attempted"]
        return {
            "schema_version": SCHEMA_VERSION,
            "component": "travel_inventory_gateway",
            "mode": "offline_no_providers" if not (self.flight_provider or self.stay_provider) else "explicit_provider_adapter",
            "request": {"flight": validated_flight.to_dict(), "accommodation": validated_stay.to_dict()},
            "flights": flights,
            "accommodation": accommodation,
            "trace": trace,
            "usage": {
                "external_requests_attempted_total": flight_calls + stay_calls,
                "flight_requests_attempted": flight_calls,
                "accommodation_requests_attempted": stay_calls,
                "llm_requests_attempted": 0,
                "llm_tokens": 0,
            },
            "integration_notes": {
                "qunar_status": "approval_pending_not_connected",
                "real_flight_prices_available": bool(flights["real_availability_verified"]),
                "real_hotel_availability_available": bool(accommodation["real_availability_verified"]),
                "booking_actions_supported": False,
                "schema_authority": "draft_pending_saieddine_pydantic_alignment",
            },
            "warnings": [
                "Provider test offers are not real flight or hotel availability.",
                "No booking or payment actions are supported.",
            ],
        }


def default_demo_requests() -> tuple[FlightRequest, StayRequest]:
    departure = date.today() + timedelta(days=30)
    return (FlightRequest("XIY", "PVG", departure.isoformat(), 1),
            StayRequest("Shanghai", departure.isoformat(), (departure + timedelta(days=3)).isoformat(), 1, 1))
