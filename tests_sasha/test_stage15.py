"""No network/token tests for TravelMind stage 15."""
from __future__ import annotations
from copy import deepcopy
from datetime import date, timedelta
import unittest
from unittest.mock import patch

from integration.team_handoff import run_offline_handoff, compose_handoff, SCHEMA_VERSION


class TestStage15(unittest.TestCase):
    def base(self, **kwargs):
        options = {"text": "I love history and museums in Xi'an",
                   "city": "西安市", "category": "museum", "limit": 5}
        options.update(kwargs)
        return run_offline_handoff(**options)

    def test_offline_quota_free(self):
        result = self.base()
        self.assertEqual(result["usage"]["external_requests_attempted_total"], 0)
        self.assertEqual(result["usage"]["llm_tokens"], 0)
        self.assertEqual(result["usage"]["llm_requests_attempted"], 0)

    def test_no_external_requests_even_when_mocked_to_fail(self):
        with patch("requests.get", side_effect=AssertionError("network used")), \
             patch("requests.post", side_effect=AssertionError("network used")):
            self.base()
            self.base(weather_demo=True, inventory_demo=True)

    def test_selection_is_candidates_not_final(self):
        result = self.base()
        self.assertEqual(result["destination"]["selection_scope"], "candidates_only")
        self.assertEqual(result["destination"]["final_selection_owner"], "itinerary_agent")
        self.assertTrue(result["destination"]["places"])

    def test_cost_is_per_person_zero_is_valid_with_evidence(self):
        result = self.base()
        museum = next(p for p in result["destination"]["places"] if p["name_zh"] == "陕西历史博物馆")
        self.assertEqual(museum["estimated_cost_cny"], 0)
        self.assertEqual(museum["cost_basis"], "per_person")
        self.assertTrue(museum["field_provenance"]["ticket_price_cny"])

    def test_unknown_prices_remain_null(self):
        result = self.base()
        for p in result["destination"]["places"]:
            if not p["field_provenance"].get("ticket_price_cny"):
                self.assertIsNone(p["estimated_cost_cny"])
                self.assertEqual(p["cost_status"], "unknown")

    def test_evidence_field_specific(self):
        result = self.base()
        evidence = result["field_evidence_provisional"]
        self.assertTrue(evidence)
        self.assertTrue(all(row["url"].startswith("https://") for row in evidence))
        self.assertTrue(all(row["field"] for row in evidence))

    def test_context_default_not_fake_forecast(self):
        result = self.base()
        self.assertEqual(result["context"]["weather"]["status"], "not_checked")
        self.assertIsNone(result["context"]["weather"]["source"])

    def test_explicit_weather_demo_labeled(self):
        result = self.base(weather_demo=True)
        weather = result["context"]["weather"]
        self.assertEqual(weather["status"], "simulated_not_verified")
        self.assertFalse(weather["is_real_forecast"])
        self.assertEqual(result["usage"]["external_requests_attempted_total"], 0)

    def test_inventory_demo_unconnected_and_no_booking(self):
        result = self.base(inventory_demo=True)
        self.assertEqual(result["inventory"]["flights"]["status"], "provider_not_connected")
        self.assertEqual(result["inventory"]["accommodation"]["status"], "provider_not_connected")
        self.assertFalse(result["inventory"]["booking_actions_supported"])
        self.assertEqual(result["usage"]["external_requests_attempted_total"], 0)

    def test_not_requested_inventory_default(self):
        result = self.base()
        self.assertEqual(result["inventory"]["flights"]["status"], "not_requested")

    def test_quality_filter_ancillary_names(self):
        result = self.base(keyword="陕西历史博物馆")
        self.assertTrue(result["destination"]["places"])
        self.assertTrue(all(p["name_zh"] == "陕西历史博物馆" for p in result["destination"]["places"]))

    def test_schema_is_provisional(self):
        result = self.base()
        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertIn("provisional", result["contract_status"])

    def test_invalid_date(self):
        with self.assertRaises(ValueError):
            self.base(travel_date="bad-date")

    def test_max_places(self):
        with self.assertRaises(ValueError):
            self.base(limit=11)

    def test_invalid_inventory_departure_before_network(self):
        with self.assertRaises(ValueError):
            self.base(inventory_demo=True, departure_date=(date.today() - timedelta(days=1)).isoformat())

    def test_sandbox_cannot_claim_real_availability(self):
        original = self.base()
        dest = {"places": deepcopy(original["destination"]["places"]), "request": {"city": "西安市"}, "usage": {}}
        ctx = {"context": deepcopy(original["context"]), "usage": {}}
        inv = {"flights": {"status": "sandbox_results", "real_availability_verified": True, "options": []},
               "accommodation": {"status": "provider_not_connected", "options": []}, "usage": {}}
        result = compose_handoff(destination=dest, context=ctx, inventory=inv)
        self.assertFalse(result["inventory"]["flights"]["real_availability_verified"])

    def test_usage_aggregates_without_double_count(self):
        original = self.base()
        dest = {"places": deepcopy(original["destination"]["places"]), "request": {"city": "西安市"},
                "usage": {"amap_v5_requests_attempted": 1, "baidu_v3_requests_attempted": 0}}
        ctx = {"context": deepcopy(original["context"]), "usage": {"open_meteo_requests_attempted": 1}}
        inv = {"flights": {"status": "provider_not_connected", "options": []},
               "accommodation": {"status": "provider_not_connected", "options": []},
               "usage": {"external_requests_attempted_total": 1, "flight_requests_attempted": 1,
                         "accommodation_requests_attempted": 0}}
        result = compose_handoff(destination=dest, context=ctx, inventory=inv)
        self.assertEqual(result["usage"]["external_requests_attempted_total"], 3)


if __name__ == "__main__":
    unittest.main()
