import unittest
from pathlib import Path
from unittest.mock import patch

from data.enrichment import enrich_places, load_curated
from workflows.enrichment import run


class EnrichmentTests(unittest.TestCase):
    def test_curated_records_are_source_covered(self):
        rows = load_curated()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row.get("sources") for row in rows))

    @patch("agents.destination_agent.search_amap_live", side_effect=AssertionError("NO AMAP"))
    @patch("agents.destination_agent.ai_interpret_request", side_effect=AssertionError("NO LLM"))
    def test_offline_run_adds_official_facts_with_zero_calls(self, _ai, _amap):
        output = run("I love history and museums in Xi'an", limit=5)
        self.assertEqual(output["usage"]["amap_api_requests_attempted"], 0)
        self.assertEqual(output["usage"]["llm_requests_attempted"], 0)
        self.assertEqual(output["enrichment"]["network_calls_attempted_by_enrichment"], 0)
        qin = next(p for p in output["places"] if p["name_zh"] == "秦始皇帝陵博物院")
        self.assertEqual(qin["ticket_price_cny"], 120)
        self.assertTrue(qin["address_zh"])
        self.assertIn("ticket_price_cny", qin["field_provenance"])
        self.assertIsNone(qin["coordinates"])

    def test_dont_claim_full_verification(self):
        item = {"name_zh": "陕西历史博物馆", "city_zh": "西安市",
                "source": {"provider": "manually_authored_demo"}}
        enriched, _ = enrich_places([item])
        self.assertEqual(enriched[0]["ticket_price_cny"], 0)
        self.assertIn("coordinates", enriched[0]["missing_fields"])
        self.assertEqual(enriched[0]["verification_status"], "some_fields_verified_from_official_sources")
        self.assertEqual(enriched[0]["source"]["provider"], "official_attraction_website")
        self.assertEqual(enriched[0]["discovery_source"]["provider"], "manually_authored_demo")
        self.assertTrue(enriched[0]["source"]["url"])

    def test_no_matching_city_or_name(self):
        places = [{"name_zh": "陕西历史博物馆", "city_zh": "北京市"}]
        enriched, usage = enrich_places(places)
        self.assertIsNone(enriched[0].get("address_zh"))
        self.assertEqual(usage["records_enriched"], 0)

    def test_does_not_mutate_source_or_override_existing_fields(self):
        original = {"name_zh": "秦始皇帝陵博物院", "city_zh": "西安市",
                    "address_zh": "already_provided", "source": {"provider": "amap"}}
        enriched, _ = enrich_places([original])
        self.assertEqual(enriched[0]["address_zh"], "already_provided")
        self.assertEqual(original, {"name_zh": "秦始皇帝陵博物院", "city_zh": "西安市",
                                    "address_zh": "already_provided", "source": {"provider": "amap"}})
        self.assertIn("opening_hours", enriched[0]["field_provenance"])

    def test_skip_2026_expired_museum_hours(self):
        original = [{"name_zh": "陕西历史博物馆", "city_zh": "西安市"}]
        enriched, _ = enrich_places(original, travel_date="2026-11-20")
        self.assertIsNone(enriched[0].get("opening_hours"))
        self.assertIn("opening_hours", enriched[0]["needs_recheck"])
        self.assertEqual(enriched[0]["ticket_price_cny"], 0)

    def test_wont_export_live_results_to_disk(self):
        with patch("agents.destination_agent.search_amap_live", return_value=[{
            "id": "poi-1", "name_zh": "陕西历史博物馆", "city_zh": "西安市",
            "address_zh": "Amap address", "source": {"provider": "amap"}
        }]) as mocked:
            output = run("Xi'an museum", live=True, limit=1)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(output["usage"]["amap_api_requests_attempted"], 1)
        self.assertEqual(output["places"][0]["address_zh"], "Amap address")
        self.assertEqual(output["places"][0]["ticket_price_cny"], 0)
        self.assertEqual(output["places"][0]["source"]["provider"], "amap")

    def test_reject_bad_date_before_network(self):
        with patch("agents.destination_agent.search_amap_live", side_effect=AssertionError("NO AMAP")):
            with self.assertRaises(ValueError):
                run("Xi'an history", travel_date="tomorrow", live=True)

if __name__ == "__main__":
    unittest.main()
