"""Stage 14 automated tests: no network connections, no model calls."""
import unittest
from datetime import date, timedelta
from unittest.mock import Mock

from providers.inventory.gateway import (FlightRequest, StayRequest, TravelInventoryGateway,
                                     DuffelSandboxFlightProvider, default_demo_requests)


def date_at(days):
    return (date.today() + timedelta(days=days)).isoformat()


class Stage14Tests(unittest.TestCase):
    def setUp(self):
        self.flight = FlightRequest("xiy", "pvg", date_at(30), 2)
        self.stay = StayRequest("Shanghai", date_at(30), date_at(33), 2, 1)

    def test_zero_usage_default(self):
        result = TravelInventoryGateway().search(self.flight, self.stay)
        self.assertEqual(result["usage"]["external_requests_attempted_total"], 0)
        self.assertEqual(result["usage"]["llm_tokens"], 0)

    def test_no_real_availability_or_prices_by_default(self):
        result = TravelInventoryGateway().search(self.flight, self.stay)
        self.assertFalse(result["integration_notes"]["real_flight_prices_available"])
        self.assertFalse(result["integration_notes"]["real_hotel_availability_available"])
        self.assertEqual(result["flights"]["options"], [])
        self.assertEqual(result["accommodation"]["options"], [])

    def test_normalizes_iata_codes(self):
        result = TravelInventoryGateway().search(self.flight, self.stay)
        self.assertEqual(result["request"]["flight"]["origin_iata"], "XIY")

    def test_rejects_invalid_iata(self):
        with self.assertRaises(ValueError):
            TravelInventoryGateway().search(FlightRequest("XIAN", "PVG", date_at(30)), self.stay)

    def test_rejects_same_airport(self):
        with self.assertRaises(ValueError):
            TravelInventoryGateway().search(FlightRequest("XIY", "XIY", date_at(30)), self.stay)

    def test_rejects_past_dates(self):
        with self.assertRaises(ValueError):
            TravelInventoryGateway().search(FlightRequest("XIY", "PVG", "2020-01-01"), self.stay)

    def test_rejects_checkout_before_checkin(self):
        stay = StayRequest("Shanghai", date_at(30), date_at(29))
        with self.assertRaises(ValueError):
            TravelInventoryGateway().search(self.flight, stay)

    def test_rejects_more_rooms_than_guests(self):
        stay = StayRequest("Shanghai", date_at(30), date_at(33), guests=1, rooms=2)
        with self.assertRaises(ValueError):
            TravelInventoryGateway().search(self.flight, stay)

    def test_validation_before_provider_called(self):
        fake = Mock()
        bad_stay = StayRequest("Shanghai", date_at(30), date_at(28))
        with self.assertRaises(ValueError):
            TravelInventoryGateway(flight_provider=fake).search(self.flight, bad_stay)
        fake.search.assert_not_called()

    def test_uses_test_token_only(self):
        spy = Mock()
        provider = DuffelSandboxFlightProvider(token="duffel_live_123", search_function=spy)
        with self.assertRaises(ValueError):
            TravelInventoryGateway(flight_provider=provider).search(self.flight, self.stay)
        spy.assert_not_called()

    def test_duffel_adapter_one_mock_request(self):
        fake = Mock(return_value={
            "source": {"retrieved_at": "2026-11-08T00:00:00+00:00"},
            "flights": {"status": "sandbox_offers_returned", "offers": [
                {"offer_id": "fake_001", "total_amount": "280.00", "total_currency": "USD", "operating_carriers": ["Example Air"],
                 "segment_count": 1, "expires_at": None}
            ]},
            "usage": {"duffel_requests_attempted": 1},
        })
        provider = DuffelSandboxFlightProvider(token="duffel_test_FAKE", search_function=fake)
        result = TravelInventoryGateway(flight_provider=provider).search(self.flight, self.stay)
        fake.assert_called_once()
        self.assertEqual(result["usage"]["external_requests_attempted_total"], 1)
        self.assertFalse(result["flights"]["options"][0]["booking_permitted"])
        self.assertFalse(result["flights"]["options"][0]["real_availability_verified"])
        self.assertEqual(result["flights"]["options"][0]["price_scope"], "total_for_requested_passengers")
        self.assertEqual(result["flights"]["options"][0]["total_amount"], "280.00")

    def test_sandbox_never_marks_real(self):
        fake = Mock(return_value={"flights": {"status": "no_sandbox_offers", "offers": []},
                                  "usage": {"duffel_requests_attempted": 1}})
        res = TravelInventoryGateway(flight_provider=DuffelSandboxFlightProvider(
            token="duffel_test_FAKE", search_function=fake)).search(self.flight, self.stay)
        self.assertFalse(res["integration_notes"]["real_flight_prices_available"])

    def test_inject_future_real_provider_shape(self):
        class ExampleAuthorizedStayProvider:
            provider_id = "authorized_demo"
            def search(self, request):
                return {"status": "provider_results", "provider": self.provider_id, "options": [
                    {"hotel_id": "fake", "is_bookable": False, "source": {"provider": "test_stub"}}
                ], "real_availability_verified": True, "external_requests_attempted": 0, "source": {"provider": "test_stub"}}
        # A test fixture only, not real authorization or live inventory.
        result = TravelInventoryGateway(stay_provider=ExampleAuthorizedStayProvider()).search(self.flight, self.stay)
        self.assertEqual(result["accommodation"]["options"][0]["hotel_id"], "fake")

    def test_date_defaults_future(self):
        f, s = default_demo_requests()
        self.assertGreater(date.fromisoformat(f.departure_date), date.today())
        self.assertGreater(date.fromisoformat(s.check_out), date.fromisoformat(s.check_in))


if __name__ == "__main__":
    unittest.main()
