import unittest
from unittest.mock import Mock
from urllib.parse import unquote

from providers.wikimedia.content import fetch_background, title_for, contact_user_agent, clean_text


class TestWikimediaStage12(unittest.TestCase):
    def test_offline_cost_and_fixture(self):
        result = fetch_background("Xi'an")
        self.assertEqual(result["usage"]["wikimedia_requests_attempted"], 0)
        self.assertEqual(result["usage"]["llm_tokens"], 0)
        self.assertEqual(result["content"]["status"], "simulated_not_verified")
        self.assertIn("[SYNTHETIC]", result["content"]["summary"])

    def test_all_cities_map(self):
        self.assertEqual(title_for("西安市"), "Xi'an")
        self.assertEqual(title_for("BEIJING"), "Beijing")

    def test_unknown_city_rejected(self):
        with self.assertRaises(ValueError):
            title_for("neverland")

    def test_contact_required_no_request(self):
        mockget = Mock()
        with self.assertRaises(ValueError):
            fetch_background("Xi'an", live=True, contact="", http_get=mockget)
        mockget.assert_not_called()

    def test_one_live_wikipedia_request(self):
        payload = {"title": "Xi'an", "extract": "Xi'an is a Chinese city of major historical importance.",
                   "revision": "123", "timestamp": "2026-11-01T00:00:00Z"}
        response = Mock(status_code=200)
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        getter = Mock(return_value=response)
        result = fetch_background("Xi'an", live=True, contact="project@example.org", http_get=getter)
        getter.assert_called_once()
        self.assertIn("/Xi%27an", getter.call_args.args[0])
        self.assertEqual(result["content"]["status"], "community_content_retrieved")
        self.assertEqual(result["usage"]["wikimedia_requests_attempted"], 1)
        self.assertEqual(result["usage"]["llm_tokens"], 0)
        self.assertEqual(result["content"]["source"]["revision"], "123")
        self.assertFalse(result["content"]["opening_hours_verified"])

    def test_wikivoyage_one_live_request(self):
        html = "<html><body><p>Xi'an is an ancient city in Shaanxi with historical landmarks.</p><h2>See</h2><p>Other info.</p></body></html>"
        response = Mock(status_code=200, text=html)
        response.raise_for_status.return_value = None
        getter = Mock(return_value=response)
        result = fetch_background("Xi'an", source="wikivoyage", live=True,
                                  contact="https://github.com/example/project", http_get=getter)
        getter.assert_called_once()
        self.assertEqual(result["content"]["status"], "community_content_retrieved")
        self.assertNotIn("Other info", result["content"]["summary"])

    def test_404_no_retry(self):
        response = Mock(status_code=404)
        getter = Mock(return_value=response)
        result = fetch_background("Chengdu", live=True, contact="project@example.org", http_get=getter)
        self.assertEqual(result["content"]["status"], "page_not_found")
        self.assertEqual(getter.call_count, 1)

    def test_redirect_no_follow(self):
        response = Mock(status_code=301)
        getter = Mock(return_value=response)
        result = fetch_background("Xi'an", live=True, contact="project@example.org", http_get=getter)
        self.assertEqual(result["content"]["status"], "redirect_not_followed")
        self.assertEqual(getter.call_count, 1)

    def test_rate_limit_no_retry(self):
        response = Mock(status_code=429)
        getter = Mock(return_value=response)
        result = fetch_background("Chengdu", live=True, contact="project@example.org", http_get=getter)
        self.assertEqual(result["content"]["status"], "unavailable")
        self.assertEqual(getter.call_count, 1)
        self.assertTrue(any("rate-limited" in warn for warn in result["warnings"]))

    def test_clean_text(self):
        self.assertEqual(clean_text("hello   world\n"), "hello world")
        self.assertLessEqual(len(clean_text("long text " * 100, 120)), 121)

    def test_no_key_needed(self):
        self.assertEqual(contact_user_agent("test@example.com"),
                         "TravelMindStudentProject/0.1 (test@example.com) PythonRequests")

if __name__ == '__main__':
    unittest.main()
