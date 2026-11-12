import unittest
from providers.weather.context import weather_signals, itinerary_hints

class Stage11WeatherProbabilityTests(unittest.TestCase):
    def test_high_probability_generates_possible_rain_not_certain_rain(self):
        signals = weather_signals({'weather_code': 3, 'precipitation_probability_max': 72,
                                   'precipitation_sum': 0.0})
        self.assertIn('possible_rain', signals)
        self.assertNotIn('rain', signals)
        self.assertTrue(any('rain' in h['suggestion'].lower() for h in itinerary_hints(signals)))

    def test_low_probability_does_not_trigger(self):
        self.assertNotIn('possible_rain', weather_signals({
            'weather_code': 3, 'precipitation_probability_max': 25}))

    def test_rain_code_remains_rain(self):
        signals = weather_signals({'weather_code': 61, 'precipitation_probability_max': 72})
        self.assertIn('rain', signals)
        self.assertNotIn('possible_rain', signals)

if __name__ == '__main__': unittest.main()
