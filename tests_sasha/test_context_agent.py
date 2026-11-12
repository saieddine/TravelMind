import unittest
from pathlib import Path
from unittest.mock import patch


from agents.context_agent import ContextAgent, forecast_signals


class ContextAgentTests(unittest.TestCase):
    @patch("providers.amap.weather.get_daily_forecast", side_effect=AssertionError("NO LIVE WEATHER"))
    def test_default_is_zero_cost(self, _mock):
        result = ContextAgent().run(city="Xi'an")
        self.assertEqual(result["mode"], "offline_unavailable")
        self.assertEqual(result["context"]["weather"]["status"], "not_checked")
        self.assertEqual(result["usage"]["amap_weather_requests_attempted"], 0)
        self.assertEqual(result["usage"]["llm_requests_attempted"], 0)

    @patch("providers.amap.weather.get_daily_forecast", side_effect=AssertionError("NO LIVE WEATHER"))
    def test_simulation_is_clearly_labeled(self, _mock):
        result = ContextAgent().run(city="Xi'an", scenario="rain")
        w = result["context"]["weather"]
        self.assertEqual(w["status"], "simulated_scenario")
        self.assertEqual(w["signals"], ["rain"])
        self.assertTrue(any("simulated" in s.lower() for s in result["warnings"]))
        self.assertGreater(len(result["context"]["itinerary_hints"]), 0)
        self.assertEqual(result["usage"]["amap_weather_requests_attempted"], 0)

    def test_no_unverified_official_alerts(self):
        result = ContextAgent().run(city="西安", scenario="storm")
        self.assertTrue(all(v == "not_checked" for v in result["context"]["checks"].values()))

    def test_live_and_scenario_conflict(self):
        with self.assertRaises(ValueError):
            ContextAgent().run(city="西安", live=True, scenario="rain", adcode="610100")

    @patch("providers.amap.weather.get_daily_forecast", side_effect=AssertionError("NO LIVE WEATHER"))
    def test_no_adcode_prevents_call(self, _mock):
        with self.assertRaises(ValueError):
            ContextAgent().run(city="西安", live=True)

    @patch("providers.amap.weather.get_daily_forecast", side_effect=AssertionError("NO LIVE WEATHER"))
    def test_far_future_does_not_call_api(self, _mock):
        result = ContextAgent().run(city="西安", live=True, adcode="610100", travel_date="2099-12-12")
        self.assertEqual(result["mode"], "live_skipped_no_request")
        self.assertEqual(result["usage"]["amap_weather_requests_attempted"], 0)

    @patch("providers.amap.weather.get_daily_forecast")
    def test_live_at_most_one_call(self, weather_mock):
        from agents.context_agent import china_today
        today = china_today().isoformat()
        weather_mock.return_value = {
            "days": [{"date": today, "day_weather_zh": "小雨",
                      "night_weather_zh": "多云", "temperature_day_c": 21,
                      "temperature_night_c": 12}],
            "provider_report_time": "fixture-time", "retrieved_at": "fixture-time",
            "adcode": "610100", "city_zh": "西安市", "provider": "amap",
        }
        result = ContextAgent().run(city="Xi'an", live=True, adcode="610100")
        weather_mock.assert_called_once_with("610100")
        self.assertEqual(result["context"]["weather"]["status"], "provider_forecast")
        self.assertIn("rain", result["context"]["weather"]["signals"])
        self.assertEqual(result["usage"]["amap_weather_requests_attempted"], 1)
        self.assertEqual(result["usage"]["llm_output_tokens"], 0)

    @patch("providers.amap.weather.get_daily_forecast")
    def test_live_absent_date_is_unavailable(self, weather_mock):
        weather_mock.return_value = {
            "days": [], "provider_report_time": None,
            "retrieved_at": "fixture-time", "adcode": "610100",
        }
        result = ContextAgent().run(city="西安", live=True, adcode="610100")
        self.assertEqual(result["context"]["weather"]["status"], "forecast_unavailable_for_date")
        self.assertEqual(result["context"]["weather"]["signals"], [])

    def test_chinese_weather_tags(self):
        item = {"day_weather_zh": "雷阵雨", "night_weather_zh": "小雨",
                "temperature_day_c": 35.0, "temperature_night_c": -1.0}
        self.assertEqual(set(forecast_signals(item)), {"possible_storm", "rain", "hot", "cold"})

    def test_invalid_date(self):
        with self.assertRaises(ValueError):
            ContextAgent().run(city="Xi'an", travel_date="tomorrow")


if __name__ == "__main__":
    unittest.main()
