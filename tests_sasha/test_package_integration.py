import json
import unittest
from unittest.mock import patch
from agents.destination_agent import DestinationAgent
from scripts.llm import run
from llm.openrouter_client import OpenRouterClient

class PackageIntegrationTests(unittest.TestCase):
    def test_llm_intent_is_authoritative_not_merged_with_rules(self):
        def transport(*args):
            return {"model": "fixture/model:free", "choices": [{"message": {"content": json.dumps({
                "city": "Beijing", "interests": ["food"], "category": "restaurant"})}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9}}
        client = OpenRouterClient(model="openrouter/free", api_key="fixture", transport=transport)
        with patch("agents.destination_agent.understand_locally", side_effect=AssertionError("rules invoked")), \
             patch("agents.destination_agent.search_demo", return_value=[]) as search:
            result = run("destination", "history museums in Xi'an", live_llm=True, client=client)
        self.assertEqual(search.call_args.kwargs["interests"], ["food"])
        self.assertEqual(search.call_args.kwargs["category"], "restaurant")
        self.assertEqual(search.call_args.kwargs["city"], result["llm_intent"]["city"])
        self.assertEqual(result["usage"]["llm_requests_attempted"], 1)
        self.assertEqual(result["usage"]["llm_total_tokens"], 9)
        self.assertTrue(any(t.get("strategy") == "provided_llm_intent" for t in result["trace"]))

    def test_empty_llm_interests_stay_empty(self):
        with patch("agents.destination_agent.search_demo", return_value=[]) as search:
            DestinationAgent().run_candidates("history museum", interpreted_intent={
                "city": "Beijing", "interests": [], "category": None})
        self.assertEqual(search.call_args.kwargs["interests"], [])

    def test_missing_llm_city_requires_clarification(self):
        with self.assertRaises(ValueError):
            DestinationAgent().run_candidates("Xi'an", interpreted_intent={"city": None, "interests": [], "category": None})

    def test_candidate_fields_and_unknown_cost(self):
        result = DestinationAgent().run_candidates("museums in Xi'an")
        self.assertTrue(result["places"])
        for p in result["places"]:
            for key in ("duration_minutes", "duration_status", "estimated_cost_cny", "cost_status", "selection_reason"):
                self.assertIn(key, p)
            self.assertIsNone(p["estimated_cost_cny"])
