import unittest
from datetime import date, timedelta
from unittest.mock import Mock

from providers.weather.open_meteo import OpenMeteoClient
from providers.weather.context import build_context, weather_signals

TODAY = date(2026, 11, 8)

class OpenMeteoTests(unittest.TestCase):
    def test_offline_zero_requests(self):
        output = build_context(city="Xi'an", today=TODAY)
        self.assertEqual(output['usage']['open_meteo_requests_attempted'], 0)
        self.assertEqual(output['usage']['llm_tokens'], 0)
        self.assertEqual(output['mode'], 'offline_synthetic')
        self.assertFalse(output['context']['weather']['source']['is_real_forecast'])

    def test_invalid_city_without_network(self):
        with self.assertRaises(ValueError):
            build_context(city='Unknown', today=TODAY, live=True)

    def test_out_of_range_skips_request(self):
        never_called = Mock(side_effect=AssertionError('should not call'))
        client = OpenMeteoClient(http_get=never_called)
        result = build_context(city='Xi\'an', travel_date=(TODAY+timedelta(days=20)).isoformat(),
                               today=TODAY, live=True, client=client)
        self.assertEqual(result['usage']['open_meteo_requests_attempted'], 0)
        self.assertEqual(result['context']['weather']['status'], 'forecast_unavailable')
        never_called.assert_not_called()

    def test_mocked_one_live_request(self):
        response = Mock()
        response.json.return_value = {
            'timezone': 'Asia/Shanghai',
            'daily': {'time': [TODAY.isoformat()],
                      'weather_code': [61], 'temperature_2m_max': [22.5],
                      'temperature_2m_min': [10.5],
                      'precipitation_probability_max': [64],
                      'precipitation_sum': [2.5]}}
        http_get = Mock(return_value=response)
        result = build_context(city='Xi\'an', today=TODAY, live=True,
                               client=OpenMeteoClient(http_get=http_get))
        self.assertEqual(http_get.call_count, 1)
        self.assertEqual(http_get.call_args.kwargs['params']['forecast_days'], 1)
        self.assertEqual(result['usage']['open_meteo_requests_attempted'], 1)
        self.assertEqual(result['usage']['llm_tokens'], 0)
        self.assertEqual(result['context']['weather']['precipitation_probability_max_pct'], 64)
        self.assertIn('rain', result['context']['weather']['signals'])

    def test_missing_fields_remain_null(self):
        response = Mock()
        response.json.return_value = {'daily': {'time': [TODAY.isoformat()]}}
        http_get = Mock(return_value=response)
        result = build_context(city='Beijing', today=TODAY, live=True,
                               client=OpenMeteoClient(http_get=http_get))
        self.assertIsNone(result['context']['weather']['temperature_day_c'])

    def test_no_double_call_when_response_missing_date(self):
        response = Mock()
        response.json.return_value = {'daily': {'time': ['2026-11-07']}}
        http_get = Mock(return_value=response)
        result = build_context(city='Shanghai', today=TODAY, live=True,
                               client=OpenMeteoClient(http_get=http_get))
        self.assertEqual(http_get.call_count, 1)
        self.assertEqual(result['context']['weather']['status'], 'forecast_unavailable')

    def test_weather_signals(self):
        self.assertEqual(weather_signals({'weather_code': 71}), ['snow'])
        self.assertIn('possible_storm', weather_signals({'weather_code': 95}))
        self.assertIn('hot', weather_signals({'temperature_2m_max': 34}))

    def test_invalid_date(self):
        with self.assertRaises(ValueError):
            build_context(city='Xi\'an', travel_date='2026-14-88', today=TODAY, live=True)

if __name__ == '__main__': unittest.main()
