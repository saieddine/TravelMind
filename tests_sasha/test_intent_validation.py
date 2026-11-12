"""Regression cases: malformed intent vs unresolved destination; no live calls."""
import json
import unittest
from unittest.mock import Mock, patch
from agents.destination_agent import DestinationAgent, canonical_city
from integration.coordinator_adapter import collect_agent_results
from llm.intent_interpreter import (validate_intent, parse_intent,
                                    IntentValidationError, ClarificationRequired)
from llm.openrouter_client import OpenRouterClient
from models import TripRequest
from orchestrator import TravelMindOrchestrator
from scripts.llm import run


def plan(**overrides):
    return {"city": "Xi'an", "interests": ["museum"], "category": "museum", **overrides}


def trip():
    return TripRequest(origin="Beijing", destination="Xi'an", days=2, budget=3000)


def malformed_plans():
    base = plan()
    return [[], "not an object", 123, {},
            {k:v for k,v in base.items() if k != "city"},
            plan(city=123), plan(city=""), plan(city="  "), plan(city=[]),
            {k:v for k,v in base.items() if k != "interests"},
            plan(interests="museum"), plan(interests=None), plan(interests=[1]), plan(interests=[""]),
            {k:v for k,v in base.items() if k != "category"},
            plan(category=[]), plan(category=""), plan(category="unsupported"),
            {**base, "unexpected": "field"}]


class IntentValidationTests(unittest.TestCase):
    def setUp(self):
        guard = patch("requests.sessions.Session.request", side_effect=AssertionError("No live HTTP"))
        guard.start()
        self.addCleanup(guard.stop)

    def test_malformed_intent_is_controlled_before_rules_or_retrieval(self):
        for value in malformed_plans():
            with self.subTest(value=value), \
                 patch("agents.destination_agent.understand_locally", side_effect=AssertionError("rules called")), \
                 patch("agents.destination_agent.search_demo", side_effect=AssertionError("retrieval called")), \
                 patch("agents.destination_agent.search_amap_live", side_effect=AssertionError("API called")):
                with self.assertRaises(IntentValidationError) as caught:
                    DestinationAgent().run_candidates("request", interpreted_intent=value)
                self.assertEqual(caught.exception.code, "invalid_intent")

    def test_coordinator_validates_before_normalization_or_agent_call(self):
        for value in malformed_plans():
            with self.subTest(value=value), \
                 patch("integration.coordinator_adapter.canonical_city", side_effect=AssertionError("normalized invalid intent")), \
                 patch("agents.destination_agent.DestinationAgent.run_candidates", side_effect=AssertionError("agent called")):
                with self.assertRaises(IntentValidationError):
                    collect_agent_results(trip(), interpreted_intent=value)

    def test_structured_valid_intent_and_parser_metadata_remain_compatible(self):
        parsed = validate_intent(plan())
        self.assertEqual(validate_intent(parsed), parsed)
        self.assertEqual(parse_intent(json.dumps(plan()), strict=True), parsed)
        with patch("agents.destination_agent.understand_locally", side_effect=AssertionError("rules called")):
            result = DestinationAgent().run_candidates("food in Beijing", interpreted_intent=parsed)
        self.assertTrue(result["places"])
        self.assertEqual(result["request"]["interests"], ["museum"])
        self.assertEqual(result["request"]["city"], canonical_city("Xi'an"))

    def test_null_city_is_valid_but_requires_clarification_without_explicit_city(self):
        value = validate_intent(plan(city=None))
        self.assertIsNone(value["city"])
        with patch("agents.destination_agent.search_demo") as search:
            with self.assertRaises(ClarificationRequired) as caught:
                DestinationAgent().run_candidates("request", interpreted_intent=value)
        self.assertEqual(caught.exception.code, "clarification_required")
        self.assertEqual(caught.exception.field, "city")
        self.assertEqual(caught.exception.places, [])
        self.assertIsInstance(caught.exception, ValueError)
        search.assert_not_called()

    def test_direct_ai_null_city_never_retrieves_even_with_live_flag(self):
        for live in (False, True):
            with self.subTest(live=live), \
                 patch("agents.destination_agent.ai_interpret_request", return_value=(plan(city=None),
                       {"llm_input_tokens": 4, "llm_output_tokens": 2})), \
                 patch("agents.destination_agent.search_demo") as local_search, \
                 patch("agents.destination_agent.search_amap_live") as amap:
                with self.assertRaises(ClarificationRequired) as caught:
                    DestinationAgent().run_candidates("Choose a museum destination", ai=True, live=live)
            self.assertEqual(caught.exception.places, [])
            self.assertEqual(caught.exception.usage["amap_api_requests_attempted"], 0)
            self.assertEqual(caught.exception.usage["llm_requests_attempted"], 1)
            self.assertEqual(caught.exception.usage["llm_output_tokens"], 2)
            local_search.assert_not_called()
            amap.assert_not_called()

    def test_malformed_mocked_ai_plan_never_reaches_search(self):
        for value in malformed_plans():
            with self.subTest(value=value), \
                 patch("agents.destination_agent.ai_interpret_request", return_value=(value, {})), \
                 patch("agents.destination_agent.search_demo") as search:
                with self.assertRaises(IntentValidationError):
                    DestinationAgent().run_candidates("Choose a museum destination", ai=True)
                search.assert_not_called()

    def test_direct_ai_null_city_respects_explicit_valid_city(self):
        with patch("agents.destination_agent.ai_interpret_request", return_value=(plan(city=None), {})):
            result = DestinationAgent().run_candidates("Choose a museum", ai=True, city="Xi'an")
        self.assertTrue(result["places"])
        self.assertFalse(result["request"]["city_assumed"])
        self.assertEqual(result["request"]["city"], canonical_city("Xi'an"))

    def test_direct_ai_null_city_uses_recognized_text_city_not_demo_default(self):
        with patch("agents.destination_agent.ai_interpret_request", return_value=(plan(city=None), {})), \
             patch("agents.destination_agent.search_demo", return_value=[]) as search:
            result = DestinationAgent().run_candidates("Museums in Chengdu", ai=True)
        self.assertEqual(search.call_args.kwargs["city"], canonical_city("Chengdu"))
        self.assertFalse(result["request"]["city_assumed"])

    def test_valid_xian_ai_intent_returns_actual_offline_candidates(self):
        with patch("agents.destination_agent.ai_interpret_request", return_value=(plan(), {})):
            result = DestinationAgent().run_candidates("Choose a museum", ai=True)
        self.assertTrue(result["places"])
        self.assertTrue(all(p["city_zh"] == canonical_city("Xi'an") for p in result["places"]))

    def test_valid_chengdu_ai_intent_queries_chengdu_fixture(self):
        fixture = {"attraction_id": "fixture-chengdu", "name_en": "Fixture museum",
                   "city_zh": canonical_city("Chengdu"), "source": {"provider": "synthetic_test"}}
        with patch("agents.destination_agent.ai_interpret_request", return_value=(plan(city="Chengdu"), {})), \
             patch("agents.destination_agent.search_demo", return_value=[fixture]) as search:
            result = DestinationAgent().run_candidates("Choose a museum", ai=True)
        self.assertEqual(search.call_args.kwargs["city"], canonical_city("Chengdu"))
        self.assertEqual(result["places"][0]["city_zh"], canonical_city("Chengdu"))

    def test_non_ai_demo_default_and_shared_chengdu_behavior_unchanged(self):
        demo = DestinationAgent().run_candidates("Suggest attractions")
        self.assertTrue(demo["request"]["city_assumed"])
        self.assertTrue(demo["places"])
        self.assertTrue(DestinationAgent().run("Chengdu", ["nature"]))

    def test_valid_coordinator_plan_reaches_destination(self):
        result = TravelMindOrchestrator().collect_agent_results(trip(), interpreted_intent=plan())
        self.assertTrue(result["destination"]["places"])
        self.assertEqual(result["destination"]["request"]["interests"], ["museum"])

    def test_coordinator_can_resolve_null_city_from_authoritative_request(self):
        result = collect_agent_results(trip(), interpreted_intent=plan(city=None))
        self.assertEqual(result["destination"]["request"]["city"], canonical_city(trip().destination))
        self.assertFalse(result["destination"]["request"]["city_assumed"])

    def test_coordinator_propagates_clarification_as_valueerror(self):
        error = ClarificationRequired()
        agent = Mock()
        agent.run_candidates.side_effect = error
        with self.assertRaises(ClarificationRequired) as caught:
            collect_agent_results(trip(), destination_agent=agent)
        self.assertIs(caught.exception, error)
        self.assertIsInstance(caught.exception, ValueError)

    def test_stage17_null_city_preserves_actual_mock_usage_and_trace(self):
        def transport(*args):
            return {"model": "fixture/free-model", "choices": [{"message": {"content": json.dumps(plan(city=None))}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}
        client = OpenRouterClient(model="openrouter/free", api_key="mock-key", transport=transport)
        with patch("agents.destination_agent.search_demo") as search:
            with self.assertRaises(ClarificationRequired) as caught:
                run("destination", "Choose a museum", live_llm=True, client=client)
        search.assert_not_called()
        self.assertEqual(caught.exception.usage["llm_requests_attempted"], 1)
        self.assertEqual(caught.exception.usage["llm_total_tokens"], 10)
        self.assertTrue(any(t.get("step") == "openrouter_chat_completion" for t in caught.exception.trace))

    def test_incorrect_explicit_ai_city_is_invalid_not_defaulted(self):
        for city in ("", " ", 123):
            with self.subTest(city=city), patch("agents.destination_agent.ai_interpret_request") as ai:
                with self.assertRaises(IntentValidationError):
                    DestinationAgent().run_candidates("Museums", ai=True, city=city)
                ai.assert_not_called()
