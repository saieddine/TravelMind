import os
import unittest
from pathlib import Path
from unittest.mock import patch, Mock


from providers.amap.weather import get_daily_forecast, parse_daily_forecast


class AmapWeatherTests(unittest.TestCase):
    @patch.dict(os.environ, {"AMAP_API_KEY": "fake_test_secret_key"})
    @patch("requests.get")
    def test_http_once_and_no_key_leak_in_output(self, get_mock):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "1", "forecasts": [{
                "city": "西安市", "adcode": "610100", "reporttime": "fixture-time",
                "casts": [{"date": "2026-11-02", "dayweather": "小雨",
                           "nightweather": "多云", "daytemp": "18", "nighttemp": "10"}]
            }]
        }
        get_mock.return_value = response
        result = get_daily_forecast("610100")
        self.assertEqual(get_mock.call_count, 1)
        self.assertEqual(result["days"][0]["temperature_day_c"], 18.0)
        self.assertNotIn("fake_test_secret_key", str(result))
        self.assertEqual(get_mock.call_args.kwargs["params"]["extensions"], "all")

    @patch("requests.get", side_effect=AssertionError("NO HTTP"))
    def test_invalid_adcode_cannot_call(self, get_mock):
        with self.assertRaises(ValueError):
            get_daily_forecast("Xi'an")
        get_mock.assert_not_called()

    def test_api_error_is_explicit(self):
        with self.assertRaises(RuntimeError):
            parse_daily_forecast({"status": "0", "info": "INVALID_USER_KEY", "infocode": "10001"}, "610100")

    def test_empty_forecast_no_fabrication(self):
        parsed = parse_daily_forecast({"status": "1", "forecasts": []}, "610100")
        self.assertEqual(parsed["days"], [])


if __name__ == "__main__":
    unittest.main()
