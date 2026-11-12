import unittest
from pathlib import Path
from unittest.mock import patch


from agents.destination_agent import DestinationAgent, understand_locally


class AgentTests(unittest.TestCase):
    def test_detect_city_and_interests(self):
        request = understand_locally("I love history and architecture in Xi'an")
        self.assertEqual(request["city"], "西安市")
        self.assertIn("history", request["interests"])
        self.assertIn("architecture", request["interests"])

    def test_english_term_boundaries(self):
        request = understand_locally("Photography in Xi'an")
        self.assertEqual(request["interests"], ["photography"])

    @patch("agents.destination_agent.search_amap_live", side_effect=AssertionError("NO LIVE CALL"))
    @patch("agents.destination_agent.ai_interpret_request", side_effect=AssertionError("NO LLM CALL"))
    def test_offline_does_not_call_apis(self, _ai_mock, _amap_mock):
        result = DestinationAgent().run_candidates("Historic attractions in Xi'an")
        self.assertGreater(len(result["places"]), 0)
        self.assertEqual(result["mode"], "offline_demo")
        self.assertEqual(result["usage"]["amap_api_requests_attempted"], 0)
        self.assertEqual(result["usage"]["llm_requests_attempted"], 0)

    @patch("agents.destination_agent.search_amap_live", return_value=[{
        "id": "test_id", "name_zh": "测试景点", "city_zh": "西安市",
        "category": "attraction", "source": {"provider": "amap"},
    }])
    def test_live_at_most_one_call(self, mock_search):
        result = DestinationAgent().run_candidates("Visit Xi'an", live=True)
        self.assertEqual(mock_search.call_count, 1)
        self.assertEqual(result["usage"]["amap_api_requests_attempted"], 1)
        self.assertEqual(result["places"][0]["name_zh"], "测试景点")
        self.assertEqual(result["places"][0]["verification_status"], "poi_found_unverified_details")

    @patch("agents.destination_agent.ai_interpret_request", return_value=(
        {"city": "成都市", "interests": ["culture"], "category": None},
        {"model": "mock-model", "llm_input_tokens": 41, "llm_output_tokens": 17},
    ))
    @patch("agents.destination_agent.search_amap_live", side_effect=AssertionError("NO LIVE CALL"))
    def test_ai_optional_and_usage_reported(self, _amap_mock, mock_ai):
        result = DestinationAgent().run_candidates("Suggest cultural places", ai=True)
        self.assertEqual(mock_ai.call_count, 1)
        self.assertEqual(result["request"]["city"], "成都市")
        self.assertEqual(result["usage"]["llm_requests_attempted"], 1)
        self.assertEqual(result["usage"]["llm_input_tokens"], 41)
        self.assertEqual(result["usage"]["llm_output_tokens"], 17)
        self.assertEqual(result["usage"]["amap_api_requests_attempted"], 0)

    def test_unknown_city_does_not_trigger_fallback(self):
        result = DestinationAgent().run_candidates("Tourist attractions in Beijing")
        self.assertEqual(result["places"], [])
        self.assertEqual(result["usage"]["amap_api_requests_attempted"], 0)
        self.assertTrue(any("No matching local records" in w for w in result["warnings"]))

    def test_max_limit_guard(self):
        with self.assertRaises(ValueError):
            DestinationAgent(max_places=50).run_candidates("Xi'an museums")


if __name__ == "__main__":
    unittest.main()
