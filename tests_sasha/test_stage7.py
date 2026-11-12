import copy
import unittest
from unittest.mock import patch

from providers.amap.poi_v5 import AmapV5Client
from data.provider_router import run_provider_search
from integration.candidate_handoff import evaluate_place, diagnostic_summary, provisional_itinerary_handoff


class FakeResponse:
    def raise_for_status(self):
        pass
    def json(self):
        return {"status": "1", "pois": [
            {"id": "EXAMPLE_ID", "name": "陕西历史博物馆", "cityname": "西安市",
             "address": "示例街道", "location": "108.95,34.22",
             "business": {"opentime_today": "09:00-17:00", "opentime_week": "周二至周日 09:00-17:00",
                          "cost": "55"}}
        ]}


class Stage7Tests(unittest.TestCase):
    def sample(self):
        return {"mode": "live_provider_transient", "request": {"city": "西安市"},
                "places": [{"attraction_id": "A", "name_zh": "陕西历史博物馆",
                            "location": {"latitude": 34.22, "longitude": 108.95},
                            "coordinates": {"latitude": 34.22, "longitude": 108.95,
                                            "system": "GCJ-02"},
                            "address_zh": "示例地址", "opening_hours": "09:00-17:00",
                            "opening_hours_today": None, "ticket_price_cny": None,
                            "average_spend_raw": "55", "estimated_cost_cny": None,
                            "duration_minutes": None, "duration_status": "unknown",
                            "source": {"provider": "amap"},
                            "field_provenance": {"opening_hours": [{"provider": "amap"}]}}],
                "usage": {"amap_v5_requests_attempted": 1, "llm_tokens": 0}}

    def test_coverage(self):
        x = diagnostic_summary(self.sample(), target_name="陕西历史博物馆")
        self.assertEqual(x["coverage_counts"]["weekly_opening_hours"], 1)
        self.assertEqual(x["coverage_counts"]["verified_ticket_price"], 0)
        self.assertTrue(x["places"][0]["exact_name_match"])

    def test_cost_unknown_stays_null(self):
        handoff = provisional_itinerary_handoff(self.sample())
        self.assertIsNone(handoff["places"][0]["estimated_cost_cny"])
        self.assertEqual(handoff["places"][0]["cost_basis"], "per_person")
        self.assertEqual(handoff["selection_scope"], "candidates_only")

    def test_no_source_price_with_spend(self):
        data = self.sample()
        data["places"][0]["estimated_cost_cny"] = 55
        handoff = provisional_itinerary_handoff(data)
        self.assertIsNone(handoff["places"][0]["estimated_cost_cny"])

    def test_verified_ticket_price(self):
        data = self.sample()
        p = data["places"][0]
        p["estimated_cost_cny"] = 120
        p["field_provenance"]["ticket_price_cny"] = [{"provider": "official_source"}]
        p["cost_status"] = "official_admission_reference_check_eligibility"
        self.assertEqual(provisional_itinerary_handoff(data)["places"][0]["estimated_cost_cny"],120)

    def test_no_mutation(self):
        a = self.sample()
        before = copy.deepcopy(a)
        diagnostic_summary(a)
        provisional_itinerary_handoff(a)
        self.assertEqual(a,before)

    def test_one_injected_http_request_and_hours(self):
        calls = []
        def fake_get(url, params, timeout):
            calls.append((url, params))
            return FakeResponse()
        client = AmapV5Client(key="TEST_ONLY", http_get=fake_get)
        with patch('data.provider_router.enrich_places', side_effect=lambda x, travel_date: (x, {})):
            output = run_provider_search(
                "I like museums in Xi'an", keyword="陕西历史博物馆", city="西安市",
                category="museum", limit=3, live_amap=True, amap_client=client)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]["show_fields"],"business")
        self.assertEqual(output['usage']['amap_v5_requests_attempted'],1)
        self.assertIsNone(output['places'][0]['ticket_price_cny'])
        self.assertEqual(output['places'][0]['opening_hours'],'周二至周日 09:00-17:00')

    def test_unknown_hours(self):
        p = {"name_zh":"示例景点", "source":{"provider":"amap"}}
        self.assertIn('weekly_opening_hours', evaluate_place(p)['missing_fields'])

    def test_offline_without_network(self):
        with patch('providers.amap.poi_v5.requests.get', side_effect=AssertionError('network forbidden')):
            output = run_provider_search("I love history in Xi'an", limit=2)
        report = diagnostic_summary(output)
        self.assertEqual(report['usage']['amap_v5_requests_attempted'],0)
        self.assertEqual(report['usage']['llm_tokens'],0)

if __name__ == '__main__':
    unittest.main()
