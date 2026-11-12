import os
import unittest
from unittest.mock import patch

from llm.openrouter_client import OpenRouterClient, LLMConfigurationError, LLMCallError
from llm.intent_interpreter import parse_intent
from scripts.llm import run


class Stage17Tests(unittest.TestCase):
    def test_offline_smoke_no_network(self):
        with patch("requests.post", side_effect=AssertionError("network call")):
            result = run("smoke", "hello")
        self.assertEqual(result["usage"]["llm_requests_attempted"], 0)

    def test_offline_destination_no_network(self):
        with patch("requests.post", side_effect=AssertionError("network call")):
            result = run("destination", "history museums in Xi'an")
        self.assertEqual(result["stage"], 17)
        self.assertEqual(result["usage"]["llm_requests_attempted"], 0)
        self.assertEqual(result["usage"]["amap_requests_attempted"], 0)

    def test_client_blocks_without_live_consent(self):
        client = OpenRouterClient(model="openrouter/free", api_key="mock-key",
                                  transport=lambda *a: self.fail("must not be called"))
        with self.assertRaises(LLMConfigurationError):
            client.complete(system="hi", user="there")

    def test_paid_model_blocked_without_override(self):
        client = OpenRouterClient(model="vendor/paid", api_key="mock-key",
                                  transport=lambda *a: self.fail("must not be called"))
        with self.assertRaises(LLMConfigurationError):
            client.complete(system="hi", user="there", live=True)

    def test_client_limits_length_without_call(self):
        client = OpenRouterClient(model="openrouter/free", api_key="mock-key",
                                  transport=lambda *a: self.fail("must not be called"))
        with self.assertRaises(ValueError):
            client.complete(system="system", user="x"*1200, live=True)

    def test_single_mocked_smoke_tracks_usage(self):
        calls = []
        def transport(body, key, timeout):
            calls.append(body)
            return {"model": "openrouter/free", "choices": [{"message": {"content": "OK"}}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 1,
                              "total_tokens": 13, "cost": 0}}
        client = OpenRouterClient(model="openrouter/free", api_key="mock-key", transport=transport)
        result = run("smoke", "hi", live_llm=True, client=client)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["usage"]["llm_total_tokens"], 13)
        self.assertEqual(result["response"], "OK")
        self.assertEqual(calls[0]["max_completion_tokens"], 512)
        self.assertEqual(result["trace"][0]["max_completion_tokens"], 512)

    def test_mocked_llm_intent_feeds_agent_without_second_call(self):
        calls = []
        def transport(body, key, timeout):
            calls.append(body)
            return {"model": "openrouter/free", "choices": [{"message": {
                "content": '{"city":"Xi\'an", "interests":["history","museum"],"category":"museum"}'
            }}], "usage": {"prompt_tokens": 41, "completion_tokens": 29, "total_tokens": 70}}
        client = OpenRouterClient(model="openrouter/free", api_key="mock-key", transport=transport)
        with patch("requests.post", side_effect=AssertionError("network should only be mocked")):
            result = run("destination", "history museums in Xi'an", live_llm=True, client=client)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["usage"]["llm_requests_attempted"], 1)
        self.assertEqual(result["usage"]["amap_requests_attempted"], 0)
        self.assertEqual(result["request"]["city"], "西安市")
        self.assertEqual(result["llm_intent"]["category"], "museum")
        self.assertEqual(calls[0]["max_completion_tokens"], 256)
        self.assertNotIn("reasoning", calls[0])

    def test_nemotron_payload_and_reasoning_only_response(self):
        calls = []
        def transport(body, key, timeout):
            calls.append(body)
            return {"choices": [{"message": {"content": None, "reasoning": "PRIVATE"},
                                 "finish_reason": "stop"}],
                    "usage": {"completion_tokens": 176,
                              "completion_tokens_details": {"reasoning_tokens": 176}}}
        client = OpenRouterClient(model="nvidia/nemotron-3-ultra-550b-a55b:free",
                                  api_key="mock-secret", transport=transport)
        with patch("requests.post", side_effect=AssertionError("No network")):
            for smoke in (False, True):
                with self.subTest(smoke=smoke):
                    with self.assertRaises(LLMCallError) as caught:
                        client.complete(system="Reply OK", user="test", live=True, smoke_test=smoke)
                    self.assertEqual(calls[-1]["reasoning"], {"effort": "low"})
                    self.assertEqual(calls[-1]["max_completion_tokens"], 512 if smoke else 256)
                    self.assertIn("finish_reason=stop", str(caught.exception))
                    self.assertIn("reasoning_tokens=176", str(caught.exception))
                    self.assertNotIn("PRIVATE", str(caught.exception))
                    self.assertNotIn("mock-secret", str(caught.exception))
        self.assertEqual(len(calls), 2)

    def test_gemma_selected_from_environment(self):
        calls = []
        def transport(body, key, timeout):
            calls.append(body)
            self.assertEqual(key, "mock-key")
            return {"choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 1, "total_tokens": 13}}
        model = "google/gemma-4-26b-a4b-it:free"
        with patch.dict(os.environ, {"OPENROUTER_MODEL": model, "OPENROUTER_API_KEY": "mock-key"}), \
             patch("requests.post", side_effect=AssertionError("No network")):
            client = OpenRouterClient(transport=transport)
            result = run("smoke", "hi", live_llm=True, client=client)
            self.assertEqual(result["response"], "OK")
            self.assertEqual(result["model"], model)
            self.assertEqual(result["usage"]["llm_total_tokens"], 13)
            self.assertEqual(result["trace"][0]["max_completion_tokens"], 256)
            self.assertIsNone(result["trace"][0]["diagnostics"]["returned_model"])
            self.assertTrue(result["trace"][0]["diagnostics"]["final_text_present"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["model"], model)
            self.assertEqual(calls[0]["max_completion_tokens"], 256)
            self.assertEqual(calls[0]["reasoning"], {"enabled": False})
            self.assertNotIn("models", calls[0])
            client.complete(system="hi", user="there", live=True)
            self.assertEqual(calls[1]["max_completion_tokens"], 256)
            self.assertEqual(calls[1]["reasoning"], {"enabled": False})

    def test_explicit_model_overrides_environment_and_reports_returned_model(self):
        gemma = "google/gemma-4-26b-a4b-it:free"
        calls = []
        def transport(body, key, timeout):
            calls.append(body)
            return {"model": "google/gemma-4-26b-a4b-it", "choices": [{
                "message": {"content": None, "reasoning": "PRIVATE"}, "finish_reason": "stop"}],
                "usage": {"completion_tokens": 1, "completion_tokens_details": {"reasoning_tokens": 1}}}
        with patch.dict(os.environ, {"OPENROUTER_MODEL": "nvidia/nemotron-3-ultra-550b-a55b:free"}), \
             patch("requests.post", side_effect=AssertionError("No network")):
            client = OpenRouterClient(model="  " + gemma + "  ", api_key="mock-secret", transport=transport)
            with self.assertRaises(LLMCallError) as caught:
                run("smoke", "hi", live_llm=True, client=client)
        error = str(caught.exception)
        for expected in ('"requested_model": "' + gemma + '"',
                         '"returned_model": "google/gemma-4-26b-a4b-it"',
                         '"final_text_present": false', '"stop": null',
                         '"completion_tokens": 1', '"reasoning_tokens": 1'):
            self.assertIn(expected, error)
        self.assertNotIn("mock-secret", error)
        self.assertNotIn("PRIVATE", error)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["reasoning"], {"enabled": False})

    def test_free_router_tracks_actual_model_without_reasoning_override(self):
        calls = []
        def transport(body, key, timeout):
            calls.append(body)
            return {"model": "vendor/selected-free-model", "choices": [{
                "message": {"content": "OK"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}}
        with patch.dict(os.environ, {"OPENROUTER_MODEL": "openrouter/free"}), \
             patch("requests.post", side_effect=AssertionError("No network")):
            client = OpenRouterClient(api_key="mock-key", transport=transport)
            result = run("smoke", "hi", live_llm=True, client=client)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], "openrouter/free")
        self.assertNotIn("reasoning", calls[0])
        self.assertNotIn("models", calls[0])
        diag = result["trace"][0]["diagnostics"]
        self.assertEqual(diag["requested_model"], "openrouter/free")
        self.assertEqual(diag["returned_model"], "vendor/selected-free-model")
        self.assertEqual(result["model"], "vendor/selected-free-model")
        self.assertEqual(result["usage"]["llm_total_tokens"], 3)

    def test_paid_models_rejected_even_with_legacy_override(self):
        for model in ("vendor/paid", "openrouter/free-other", "vendor/model:free:paid"):
            client = OpenRouterClient(model=model, api_key="mock-key",
                                      transport=lambda *args: self.fail("must not call transport"))
            with self.subTest(model=model), self.assertRaises(LLMConfigurationError):
                client.complete(system="hi", user="hi", live=True, allow_paid_model=True)

    def test_router_invalid_destination_output_is_rejected_before_agent(self):
        for content in ("not JSON", "[]", "{}", '{"city":null,"interests":"museum","category":null}',
                        '{"city":"Atlantis","interests":[],"category":null}'):
            calls = []
            def transport(*args):
                calls.append(1)
                return {"model": "vendor/selected", "choices": [{"message": {"content": content}}]}
            client = OpenRouterClient(model="openrouter/free", api_key="mock-key", transport=transport)
            with self.subTest(content=content), \
                 patch("agents.destination_agent.DestinationAgent.run_candidates", side_effect=AssertionError("invalid intent reached agent")), \
                 patch("requests.post", side_effect=AssertionError("No network")):
                with self.assertRaises(ValueError):
                    run("destination", "museums", live_llm=True, client=client)
                self.assertEqual(len(calls), 1)

    def test_invalid_json_fails_without_retry(self):
        with self.assertRaises(ValueError):
            parse_intent("This is not JSON")

    def test_unrecognized_values_are_rejected(self):
        result = parse_intent('{"city":"Atlantis", "interests":["museum","fake"],"category":"spaceport"}')
        self.assertEqual(result["city"], None)
        self.assertEqual(result["interests"], ["museum"])
        self.assertIsNone(result["category"])

    def test_json_fence_parsed(self):
        result = parse_intent('```json\n{"city":"Beijing","interests":[],"category":null}\n```')
        self.assertEqual(result["city"], "北京市")

    def test_response_without_choices_rejected(self):
        client = OpenRouterClient(model="openrouter/free", api_key="mock-key",
                                  transport=lambda *args: {})
        with self.assertRaises(LLMCallError):
            client.complete(system="x", user="y", live=True)

    def test_no_auto_retries_on_response_error(self):
        attempts = []
        def transport(*args):
            attempts.append(1)
            raise LLMCallError("simulated rate limit")
        client = OpenRouterClient(model="openrouter/free", api_key="mock-key", transport=transport)
        with self.assertRaises(LLMCallError):
            client.complete(system="a", user="b", live=True)
        self.assertEqual(len(attempts), 1)


if __name__ == "__main__":
    unittest.main()
