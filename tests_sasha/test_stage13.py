"""All tests are offline. Never access a real network."""
import unittest
from unittest.mock import Mock
from providers.inventory.sandbox import (
    offline_demo, normalize_duffel_offer, search_duffel_test_flights, validate_search)


class Stage13Tests(unittest.TestCase):
    def test_default_zero_calls(self):
        r = offline_demo()
        self.assertEqual(r["usage"]["duffel_requests_attempted"], 0)
        self.assertEqual(r["usage"]["llm_tokens"], 0)

    def test_no_prices_are_invented(self):
        r = offline_demo()
        self.assertIsNone(r["flights"]["offers"][0]["total_amount"])
        self.assertIsNone(r["accommodation"]["total_price"])

    def test_no_liveness_claim(self):
        r = offline_demo()
        self.assertFalse(r["accommodation"]["availability_verified"])

    def test_validates_iata(self):
        with self.assertRaises(ValueError):
            validate_search("XI'AN", "PVG", "2026-12-10", 1)

    def test_validates_future_date(self):
        with self.assertRaises(ValueError):
            validate_search("XIY", "PVG", "2020-01-01", 1)

    def test_validates_route_not_same(self):
        with self.assertRaises(ValueError):
            validate_search("XIY", "XIY", "2026-12-10", 1)

    def test_refuses_non_test_token_without_request(self):
        fake_post = Mock()
        with self.assertRaises(ValueError):
            search_duffel_test_flights(origin="XIY", destination="PVG", departure_date="2026-12-10",
                                       token="duffel_live_123", post=fake_post)
        fake_post.assert_not_called()

    def test_normalization_does_not_invent_carrier(self):
        r = normalize_duffel_offer({"id": "offer_demo"}, sandbox=True)
        self.assertEqual(r["operating_carriers"], [])
        self.assertFalse(r["is_real_quote"])

    def test_fake_response_one_post_and_normalized(self):
        fake_post = Mock()
        fake_response = Mock()
        fake_response.json.return_value = {"data": {"id": "orq_test", "offers": [
            {"id": "off_demo", "total_amount": "200.00", "total_currency": "USD",
             "slices": [{"segments": [{"operating_carrier": {"name": "Demo Airline"}}]}]}
        ]}}
        fake_post.return_value = fake_response
        r = search_duffel_test_flights(origin="XIY", destination="PVG", departure_date="2026-12-10",
                                       token="duffel_test_NOT_REAL", post=fake_post)
        self.assertEqual(fake_post.call_count, 1)
        self.assertEqual(r["flights"]["status"], "sandbox_offers_returned")
        self.assertEqual(r["flights"]["offers"][0]["operating_carriers"], ["Demo Airline"])
        self.assertFalse(r["flights"]["offers"][0]["is_real_quote"])
        self.assertEqual(r["usage"]["duffel_requests_attempted"], 1)

    def test_request_failure_counts_attempt(self):
        fake_post = Mock(side_effect=OSError("fake"))
        r = search_duffel_test_flights(origin="XIY", destination="PVG", departure_date="2026-12-10",
                                       token="duffel_test_NOT_REAL", post=fake_post)
        self.assertEqual(r["usage"]["duffel_requests_attempted"], 1)
        self.assertEqual(r["flights"]["status"], "request_failed")

    def test_no_booking_permitted(self):
        r = normalize_duffel_offer({"id": "test"}, sandbox=True)
        self.assertFalse(r["booking_permitted"])


if __name__ == "__main__":
    unittest.main()
