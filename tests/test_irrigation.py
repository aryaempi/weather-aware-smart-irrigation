import math
import os
import sys
import unittest


PROJECT_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app_final_gui_1"))
sys.path.insert(0, PROJECT_APP)

from core import irrigation


WEATHER = {
    "et0": [4.0, 3.0],
    "rain": [0.0, 0.0],
    "tmin": [10.0, 11.0],
    "tmax": [20.0, 21.0],
}
PLANT = {"name": "Test", "Kc": 1.0, "area": 4.0, "L": 40.0, "U": 60.0}


class IrrigationTests(unittest.TestCase):
    def setUp(self):
        irrigation.PUMP_FLOW = [1.0, 2.0, 1.0, 2.0]

    def test_two_dry_zones_are_not_suppressed_by_median(self):
        soil = (0.0, 0.0, 100.0, 100.0, 50.0)
        decision = irrigation.make_decision(
            soil[4], PLANT, WEATHER, "Field", 0.2, soil_values=soil[:4]
        )
        self.assertEqual(decision["active_zones"], [0, 1])
        self.assertGreater(decision["water_final"], 0)
        states, times = irrigation.zone_irrigation_control(
            soil,
            decision["water_final"],
            PLANT["L"],
            decision["zone_water_liters"],
        )
        self.assertEqual(states, [1, 1, 0, 0])
        self.assertGreater(times[0], times[1])

    def test_only_dry_zone_gets_its_own_area_share(self):
        soil = (20.0, 50.0, 50.0, 50.0, 50.0)
        decision = irrigation.make_decision(
            soil[4], PLANT, WEATHER, soil_values=soil[:4]
        )
        self.assertEqual(decision["active_zones"], [0])
        self.assertEqual(sum(v > 0 for v in decision["zone_water_liters"]), 1)

    def test_water_balance_formula_has_expected_units(self):
        soil = (20.0, 50.0, 50.0, 50.0)
        decision = irrigation.make_decision(
            50, PLANT, WEATHER, "Field", 0.2, soil,
            irrigation_efficiency=0.8, soil_water_capacity=0.2,
        )
        # Zone area is 1 m². Storage deficit is 12 L and one-day ETc is 4 L.
        self.assertAlmostEqual(decision["zone_water_liters"][0], 20.0)
        self.assertAlmostEqual(decision["water_today"], 16.0)

    def test_inconsistent_median_and_zone_values_are_rejected(self):
        with self.assertRaises(irrigation.IrrigationInputError):
            irrigation.make_decision(10, PLANT, WEATHER, soil_values=(20, 50, 50, 50))

    def test_container_uses_depth_and_calibrated_capacity(self):
        soil = (20.0, 50.0, 50.0, 50.0, 50.0)
        shallow = irrigation.make_decision(
            soil[4], PLANT, WEATHER, "Container", 0.1, soil[:4],
            soil_water_capacity=0.2,
        )
        deep = irrigation.make_decision(
            soil[4], PLANT, WEATHER, "Container", 0.3, soil[:4],
            soil_water_capacity=0.2,
        )
        self.assertGreater(deep["water_final"], shallow["water_final"])

    def test_effective_rain_reduces_continuously(self):
        dry = (20.0, 20.0, 20.0, 20.0)
        no_rain = irrigation.make_decision(20, PLANT, WEATHER, soil_values=dry)
        rainy = irrigation.make_decision(
            20,
            PLANT,
            {**WEATHER, "rain": [2.0, 2.0]},
            soil_values=dry,
        )
        self.assertLess(rainy["water_final"], no_rain["water_final"])

    def test_nan_and_out_of_range_are_rejected(self):
        with self.assertRaises(irrigation.IrrigationInputError):
            irrigation.make_decision(math.nan, PLANT, WEATHER)
        with self.assertRaises(irrigation.IrrigationInputError):
            irrigation.zone_irrigation_control((101, 1, 1, 1, 1), 1, 40)

    def test_tiny_runtime_does_not_turn_pump_on(self):
        states, times = irrigation.zone_irrigation_control(
            (10, 50, 50, 50, 50), 0.0001, 40, [0.0001, 0, 0, 0]
        )
        self.assertEqual(states, [0, 0, 0, 0])
        self.assertEqual(times, [0.0, 0.0, 0.0, 0.0])

    def test_runtime_is_capped(self):
        states, times = irrigation.zone_irrigation_control(
            (0, 0, 0, 0, 0), 1000, 40, [250] * 4, max_runtime_minutes=2
        )
        self.assertEqual(states, [1, 1, 1, 1])
        self.assertTrue(all(value <= 2 for value in times))

    def test_runtime_cannot_exceed_firmware_safety_limit(self):
        _, times = irrigation.zone_irrigation_control(
            (0, 0, 0, 0, 0), 1000, 40, [250] * 4, max_runtime_minutes=120
        )
        self.assertTrue(
            all(value <= irrigation.MAX_SAFE_PUMP_RUNTIME_MINUTES for value in times)
        )

    def test_area_scales_zone_water(self):
        soil = (20.0, 50.0, 50.0, 50.0)
        small = irrigation.make_decision(50, PLANT, WEATHER, soil_values=soil)
        large_plant = {**PLANT, "area": PLANT["area"] * 2}
        large = irrigation.make_decision(50, large_plant, WEATHER, soil_values=soil)
        self.assertAlmostEqual(large["water_final"], small["water_final"] * 2)

    def test_invalid_area_and_depth_are_rejected(self):
        with self.assertRaises(irrigation.IrrigationInputError):
            irrigation.make_decision(20, {**PLANT, "area": 0}, WEATHER)
        with self.assertRaises(irrigation.IrrigationInputError):
            irrigation.make_decision(20, PLANT, WEATHER, soil_depth=0)

    def test_invalid_weather_physics_are_rejected(self):
        with self.assertRaises(irrigation.IrrigationInputError):
            irrigation.make_decision(20, PLANT, {**WEATHER, "rain": [-1, 0]})
        with self.assertRaises(irrigation.IrrigationInputError):
            irrigation.make_decision(
                20, PLANT, {**WEATHER, "tmin": [30, 11], "tmax": [20, 21]}
            )

    def test_fallback_water_is_split_only_between_active_zones(self):
        states, times = irrigation.zone_irrigation_control(
            (10, 50, 50, 50, 50), 8, 40, pump_flows=[2, 2, 2, 2]
        )
        self.assertEqual(states, [1, 0, 0, 0])
        self.assertEqual(times[0], 4)

    def test_cycle_uses_explicit_flow_snapshot(self):
        irrigation.PUMP_FLOW = [100, 100, 100, 100]
        _, times = irrigation.zone_irrigation_control(
            (10, 50, 50, 50, 50), 8, 40,
            zone_water_liters=[8, 0, 0, 0], pump_flows=[2, 2, 2, 2],
        )
        self.assertEqual(times[0], 4)

    def test_schedule_stops_each_pump_separately(self):
        schedule = irrigation.PumpSchedule((1.0, 2.0, 0.0, 3.0))
        self.assertEqual(schedule.states_at(30), [1, 1, 0, 1])
        self.assertEqual(schedule.states_at(90), [0, 1, 0, 1])
        self.assertEqual(schedule.states_at(181), [0, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
