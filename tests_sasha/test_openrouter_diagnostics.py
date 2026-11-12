import unittest
from unittest.mock import patch, Mock
from llm.openrouter_client import _read_content, _default_transport, LLMCallError


class OpenRouterDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        guard = patch("requests.post", side_effect=AssertionError("Network forbidden"))
        guard.start()
        self.addCleanup(guard.stop)

    def test_http_429_metadata_and_headers(self):
        response = Mock(ok=False, status_code=429, headers={
            "Retry-After": "30", "X-RateLimit-Reset": "1794441600"})
        response.json.return_value = {"error": {"metadata": {
            "limit_source": "provider", "provider_name": "ExampleProvider",
            "remedy_hint": "Wait before trying manually"}}}
        with patch("requests.post", return_value=response) as post:
            with self.assertRaises(LLMCallError) as caught:
                _default_transport({"model": "example:free"}, "test-secret", 90)
        for value in ("provider", "ExampleProvider", "Wait before trying manually",
                      '"Retry-After": "30"', '"X-RateLimit-Reset": "1794441600"', "no retry made"):
            self.assertIn(value, str(caught.exception))
        post.assert_called_once()

    def test_http_429_missing_or_malformed_json(self):
        for payload in ({}, [], {"error": None}, {"error": {"metadata": []}}, "non-json"):
            with self.subTest(payload=payload):
                response = Mock(ok=False, status_code=429, headers={})
                if payload == "non-json":
                    response.json.side_effect = ValueError("bad JSON")
                else:
                    response.json.return_value = payload
                with patch("requests.post", return_value=response) as post:
                    with self.assertRaises(LLMCallError) as caught:
                        _default_transport({}, "test-secret", 90)
                self.assertIn("HTTP 429", str(caught.exception))
                self.assertIn('"Retry-After": null', str(caught.exception))
                post.assert_called_once()

    def test_http_429_redacts_secrets_and_ignores_raw_error(self):
        response = Mock(ok=False, status_code=429, headers={"Retry-After": "test-secret"})
        response.json.return_value = {"error": {"message": "RAW_PRIVATE", "metadata": {
            "limit_source": {"private": "RAW_PRIVATE"}, "provider_name": "sk-other-secret",
            "remedy_hint": "test-secret Bearer OTHER_SECRET\nwait"}}}
        with patch("requests.post", return_value=response):
            with self.assertRaises(LLMCallError) as caught:
                _default_transport({}, "test-secret", 90)
        for private in ("test-secret", "sk-other-secret", "OTHER_SECRET", "RAW_PRIVATE"):
            self.assertNotIn(private, str(caught.exception))
        self.assertIn("[REDACTED]", str(caught.exception))

    def test_no_final_text(self):
        for content, state in [({}, "missing"), ({"content": None}, "null"),
                               ({"content": "  "}, "empty"), ({"content": []}, "empty")]:
            for reason in ("length", "stop"):
                with self.subTest(state=state, reason=reason):
                    response = {"choices": [{"message": {**content, "reasoning": "PRIVATE_REASONING"},
                                              "finish_reason": reason}],
                                "usage": {"completion_tokens": 256,
                                          "completion_tokens_details": {"reasoning_tokens": 250}}}
                    with self.assertRaises(LLMCallError) as caught:
                        _read_content(response)
                    error = str(caught.exception)
                    for expected in (f"message.content={state}", f"finish_reason={reason}",
                                     "completion_tokens=256", "reasoning_tokens=250", "reasoning_present=True"):
                        self.assertIn(expected, error)
                    self.assertNotIn("PRIVATE_REASONING", error)

    def test_optional_usage_and_reasoning_field_presence(self):
        for extra, present in [({}, False), ({"reasoning": None}, True),
                               ({"reasoning_details": []}, True)]:
            with self.subTest(extra=extra):
                with self.assertRaises(LLMCallError) as caught:
                    _read_content({"choices": [{"message": {"content": None, **extra},
                                                "finish_reason": "stop"}]})
                self.assertIn(f"reasoning_present={present}", str(caught.exception))
                self.assertIn("reasoning_tokens=None", str(caught.exception))

    def test_reasoning_content_part_is_not_final_text(self):
        with self.assertRaises(LLMCallError):
            _read_content({"choices": [{"message": {"content": [
                {"type": "reasoning", "text": "PRIVATE"}]}, "finish_reason": "stop"}]})

    def test_valid_final_text(self):
        for content in (" Final answer ", [{"type": "text", "text": " Final answer "}]):
            self.assertEqual(_read_content({"choices": [{"message": {"content": content},
                                                         "finish_reason": "stop"}]}), "Final answer")


if __name__ == "__main__":
    unittest.main()
