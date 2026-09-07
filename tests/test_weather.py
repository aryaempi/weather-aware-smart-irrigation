import os
import sys
import unittest
from unittest.mock import patch


PROJECT_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app_final_gui_1"))
sys.path.insert(0, PROJECT_APP)

from core import weather


def payload(et0=4.0):
    return {
        "daily": {
            "et0_fao_evapotranspiration": [et0, et0 + 1],
            "precipitation_sum": [0, 1],
            "temperature_2m_min": [10, 11],
            "temperature_2m_max": [20, 21],
        }
    }


class WeatherTests(unittest.TestCase):
    def setUp(self):
        weather.clear_weather_cache()
        weather.WEATHER_REFRESH_HOURS = 1

    def test_api_payload_validation(self):
        with patch.object(weather, "_fetch_json", return_value=payload()):
            result = weather.get_weather(37.2, 49.6)
        self.assertEqual(result["source"], "API")
        self.assertEqual(len(result["et0"]), 2)

    def test_short_or_null_payload_is_rejected(self):
        bad = payload()
        bad["daily"]["temperature_2m_max"] = [None, 20]
        with patch.object(weather, "_fetch_json", return_value=bad):
            with self.assertRaises(weather.WeatherError):
                weather.get_weather(37.2, 49.6)

    def test_simulation_requires_explicit_permission(self):
        with patch.object(weather, "_fetch_json", side_effect=OSError("offline")):
            with self.assertRaises(weather.WeatherError):
                weather.get_weather(37.2, 49.6, allow_simulation=False)
            simulated = weather.get_weather(
                37.2, 49.6, allow_simulation=True, simulation_seed=123
            )
        self.assertTrue(simulated["simulated"])
        self.assertEqual(simulated["simulation_seed"], 123)

    def test_cache_is_keyed_by_location_and_force_refreshes(self):
        with patch.object(
            weather, "_fetch_json", side_effect=[payload(1), payload(2), payload(3)]
        ) as fetch:
            first = weather.get_weather_cached(1, 1)
            cached = weather.get_weather_cached(1, 1)
            other = weather.get_weather_cached(2, 2)
            refreshed = weather.get_weather_cached(1, 1, force_refresh=True)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(first["et0"], cached["et0"])
        self.assertNotEqual(first["et0"], other["et0"])
        self.assertNotEqual(first["et0"], refreshed["et0"])

    def test_coordinates_are_validated(self):
        with self.assertRaises(weather.WeatherError):
            weather.get_weather(91, 0)

    def test_negative_water_values_and_inverted_temperatures_are_rejected(self):
        bad = payload()
        bad["daily"]["et0_fao_evapotranspiration"] = [-1, 2]
        with patch.object(weather, "_fetch_json", return_value=bad):
            with self.assertRaises(weather.WeatherError):
                weather.get_weather(37.2, 49.6)

        bad = payload()
        bad["daily"]["temperature_2m_min"] = [30, 10]
        with patch.object(weather, "_fetch_json", return_value=bad):
            with self.assertRaises(weather.WeatherError):
                weather.get_weather(37.2, 49.6)


if __name__ == "__main__":
    unittest.main()
