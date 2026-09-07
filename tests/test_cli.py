import argparse
import importlib.util
import os
import signal
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT_APP = os.path.join(ROOT, "app_final_gui_1")
sys.path.insert(0, PROJECT_APP)

from core import database, irrigation, sensor, weather


CLI_PATH = os.path.join(PROJECT_APP, "app_6.0.py")
SPEC = importlib.util.spec_from_file_location("smart_irrigation_cli", CLI_PATH)
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


WEATHER = {
    "et0": [4.0, 3.0],
    "rain": [0.0, 0.0],
    "tmin": [10.0, 11.0],
    "tmax": [20.0, 21.0],
    "source": "TEST",
    "simulated": True,
}


class CaptureOutput:
    def __init__(self):
        self.parts = []

    def __call__(self, value="", end="\n"):
        self.parts.append(str(value) + end)

    @property
    def text(self):
        return "".join(self.parts)


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += max(0.0, float(seconds))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_db = database.DB_FILE
        self.original_serial = sensor.serial_port
        self.original_verified = sensor.device_verified
        database.DB_FILE = os.path.join(self.tempdir.name, "cli.db")
        database.init_database()
        database.db_add_location("Test Location", 37.2, 49.6)
        database.db_save_setting("active_location", "Test Location")
        database.db_save_setting("active_plant", "Wheat")
        self.output = CaptureOutput()
        self.controller = cli.TerminalController(output=self.output)
        self.controller.initialize()
        sensor.serial_port = None
        sensor.device_verified = False
        sensor.disable_pump_commands()
        sensor.safety_stop_event.clear()
        sensor.set_system_state(sensor.STATE_STOPPED)

    def tearDown(self):
        sensor.disable_pump_commands()
        sensor.serial_port = self.original_serial
        sensor.device_verified = self.original_verified
        sensor.set_system_state(sensor.STATE_STOPPED)
        database.DB_FILE = self.original_db
        self.tempdir.cleanup()

    def test_soil_cli_argument_is_validated(self):
        self.assertEqual(cli.parse_soil_values("10,20,30,40"), (10, 20, 30, 40))
        with self.assertRaises(argparse.ArgumentTypeError):
            cli.parse_soil_values("10,20,300,40")

    def test_complete_simulated_cycle_and_repeat(self):
        with patch.object(sensor, "send_serial_command") as send:
            results = self.controller.run_cycles(
                count=2,
                interval=0,
                simulate_hardware=True,
                simulated_soil=(20, 50, 50, 50),
                weather_override=WEATHER,
                area=8,
                cultivation_mode="Container",
                soil_depth=0.3,
            )
        self.assertEqual(len(results), 2)
        self.assertTrue(all(item["status"].startswith("simulation_only") for item in results))
        self.assertTrue(all(item["pump_states"] == [1, 0, 0, 0] for item in results))
        self.assertFalse(send.called)
        history = database.db_get_history(10)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0][23], "Container")
        self.assertEqual(history[0][7], 0.3)
        self.assertEqual(history[0][33], 3)
        self.assertEqual(history[0][28], 0)
        self.assertEqual(history[0][24], 0)

    def test_wet_soil_saves_not_required_without_pumps(self):
        result = self.controller.run_cycle(
            simulate_hardware=True,
            simulated_soil=(80, 80, 80, 80),
            weather_override=WEATHER,
        )
        self.assertEqual(result["status"], "not_required")
        self.assertEqual(result["pump_states"], [0, 0, 0, 0])
        self.assertEqual(result["delivered_liters"], 0)

    def test_invalid_override_is_rejected_before_collection(self):
        with patch.object(self.controller, "_collect_hardware_samples") as collect:
            with self.assertRaises(cli.CliError):
                self.controller.run_cycle(area=float("nan"), weather_override=WEATHER)
        collect.assert_not_called()
        self.assertEqual(database.db_get_history(10), [])
        self.assertEqual(sensor.get_system_state(), sensor.STATE_ERROR)

    def test_weather_failure_stops_safely_and_does_not_save_partial_record(self):
        with patch.object(self.controller, "_get_weather", side_effect=weather.WeatherError("offline")):
            with self.assertRaises(weather.WeatherError):
                self.controller.run_cycle(
                    simulate_hardware=True,
                    simulated_soil=(20, 50, 50, 50),
                )
        self.assertEqual(sensor.get_system_state(), sensor.STATE_ERROR)
        self.assertEqual(database.db_get_history(10), [])

    def test_missing_location_is_reported(self):
        database.db_save_setting("active_location", "")
        with self.assertRaises(cli.CliError):
            self.controller.run_cycle(
                simulate_hardware=True,
                weather_override=WEATHER,
            )

    def test_real_schedule_protocol_and_independent_stop_are_exercised(self):
        clock = FakeClock()
        controller = cli.TerminalController(
            output=self.output, monotonic=clock.monotonic, sleeper=clock.sleep
        )
        schedule = irrigation.PumpSchedule((0.02, 0.04, 0, 0))
        commands = []

        def pump_command(*states, **kwargs):
            commands.append(list(states))
            return True

        with patch.object(sensor, "send_pump_command", side_effect=pump_command), \
             patch.object(sensor, "safe_stop_pumps", return_value=True), \
             patch.object(sensor, "send_heartbeat", return_value=True):
            delivered, status, acknowledged = controller._execute_real_schedule(
                schedule, [1, 1, 0, 0], [1, 1, 1, 1]
            )
        self.assertEqual(commands[0], [1, 1, 0, 0])
        self.assertIn([0, 1, 0, 0], commands)
        self.assertIn([0, 0, 0, 0], commands)
        self.assertAlmostEqual(delivered, 0.06, places=6)
        self.assertEqual(status, "completed")
        self.assertTrue(acknowledged)

    def test_real_schedule_ack_failure_is_safe(self):
        schedule = irrigation.PumpSchedule((0.02, 0, 0, 0))
        with patch.object(sensor, "send_pump_command", return_value=False), \
             patch.object(sensor, "safe_stop_pumps", return_value=True) as stop:
            with self.assertRaises(cli.CliError):
                self.controller._execute_real_schedule(schedule, [1, 0, 0, 0], [1] * 4)
        stop.assert_called()

    def test_partial_delivery_is_saved_when_real_execution_fails(self):
        failure = cli.PumpExecutionError("heartbeat failed", 1.25, False)
        with patch.object(
            self.controller, "_collect_hardware_samples", return_value=((20, 50, 50, 50, 50), 3)
        ), patch.object(
            self.controller, "_execute_real_schedule", side_effect=failure
        ):
            with self.assertRaises(cli.PumpExecutionError):
                self.controller.run_cycle(weather_override=WEATHER)
        record = database.db_get_history(1)[0]
        self.assertEqual(record[25], "error")
        self.assertEqual(record[24], 1.25)
        self.assertEqual(record[28], 0)

    def test_interrupt_saves_partial_delivery_and_stops_state(self):
        failure = cli.PumpExecutionInterrupted(0.75, False)
        with patch.object(
            self.controller, "_collect_hardware_samples", return_value=((20, 50, 50, 50, 50), 3)
        ), patch.object(
            self.controller, "_execute_real_schedule", side_effect=failure
        ):
            with self.assertRaises(cli.PumpExecutionInterrupted):
                self.controller.run_cycle(weather_override=WEATHER)
        record = database.db_get_history(1)[0]
        self.assertEqual(record[25], "interrupted")
        self.assertEqual(record[24], 0.75)
        self.assertEqual(sensor.get_system_state(), sensor.STATE_STOPPED)

    def test_real_schedule_sends_heartbeat(self):
        clock = FakeClock()
        controller = cli.TerminalController(
            output=self.output, monotonic=clock.monotonic, sleeper=clock.sleep
        )
        schedule = irrigation.PumpSchedule((0.11, 0, 0, 0))
        with patch.object(sensor, "send_pump_command", return_value=True), \
             patch.object(sensor, "safe_stop_pumps", return_value=True), \
             patch.object(sensor, "send_heartbeat", return_value=True) as heartbeat:
            _, status, acknowledged = controller._execute_real_schedule(
                schedule, [1, 0, 0, 0], [1] * 4
            )
        self.assertGreaterEqual(heartbeat.call_count, 1)
        self.assertEqual(status, "completed")
        self.assertTrue(acknowledged)

    def test_unconfirmed_stop_raises_when_cycle_is_interrupted(self):
        clock = FakeClock()
        stop_event = threading.Event()

        def interrupting_sleep(seconds):
            clock.sleep(seconds)
            stop_event.set()

        controller = cli.TerminalController(
            output=self.output,
            monotonic=clock.monotonic,
            sleeper=interrupting_sleep,
            stop_event=stop_event,
        )
        schedule = irrigation.PumpSchedule((0.1, 0, 0, 0))
        with patch.object(sensor, "send_pump_command", return_value=True), \
             patch.object(sensor, "safe_stop_pumps", return_value=False), \
             patch.object(sensor, "send_heartbeat", return_value=True):
            with self.assertRaises(cli.CliError):
                controller._execute_real_schedule(schedule, [1, 0, 0, 0], [1] * 4)

    def test_hardware_collection_uses_start_stop_and_minimum_samples(self):
        clock = FakeClock()
        controller = cli.TerminalController(
            output=self.output, monotonic=clock.monotonic, sleeper=clock.sleep
        )
        commands = []

        def serial_command(command):
            commands.append(command)
            if command == "SENSOR:START":
                with sensor.soil_samples_lock:
                    sensor.soil_samples.extend(
                        [(10, 20, 30, 40), (20, 30, 40, 50), (30, 40, 50, 60)]
                    )
            return True

        sensor.device_verified = True
        with patch.object(sensor, "start_sensor_reader", return_value=True), \
             patch.object(sensor, "send_serial_command", side_effect=serial_command):
            soil, count = controller._collect_hardware_samples(1.0, 3)
        self.assertEqual(soil, (20, 30, 40, 50, 35))
        self.assertEqual(count, 3)
        self.assertEqual(commands, ["SENSOR:START", "SENSOR:STOP"])

    def test_interactive_plant_and_location_management(self):
        plant_inputs = iter(["add", "CLI Plant", "1.1", "30", "70"])
        menu = cli.InteractiveTerminal(
            self.controller, input_fn=lambda prompt: next(plant_inputs), output=self.output
        )
        menu._plants_menu()
        self.assertIsNotNone(database.db_get_plant_by_name("CLI Plant"))

        select_inputs = iter(["select", "CLI Plant"])
        menu.input = lambda prompt: next(select_inputs)
        menu._plants_menu()
        self.assertEqual(database.db_load_setting("active_plant"), "CLI Plant")

        location_inputs = iter(["add", "CLI Location", "10", "20"])
        menu.input = lambda prompt: next(location_inputs)
        menu._locations_menu()
        self.assertIsNotNone(database.db_get_location_by_name("CLI Location"))

        select_location = iter(["select", "CLI Location"])
        menu.input = lambda prompt: next(select_location)
        menu._locations_menu()
        self.assertEqual(database.db_load_setting("active_location"), "CLI Location")

    def test_interactive_area_mode_and_depth_settings(self):
        values = iter(["y", "12.5", "Container", "0.4", "N"])
        menu = cli.InteractiveTerminal(
            self.controller, input_fn=lambda prompt: next(values), output=self.output
        )
        menu._settings_menu()
        settings = database.db_load_all_settings()
        self.assertEqual(settings["land_area"], 12.5)
        self.assertEqual(settings["cultivation_mode"], "Container")
        self.assertEqual(settings["soil_depth"], 0.4)

    def test_interactive_advanced_settings_are_applied(self):
        values = iter([
            "y", "4", "Field", "0.25", "y",
            "auto", "115200", "20", "60", "5", "2", "y",
            "1.1,1.2,1.3,1.4", "10", "0.8", "0.25", "0.7", "100",
        ])
        menu = cli.InteractiveTerminal(
            self.controller, input_fn=lambda prompt: next(values), output=self.output
        )
        menu._settings_menu()
        settings = database.db_load_all_settings()
        self.assertEqual(settings["collect_duration"], 20)
        self.assertEqual(settings["minimum_samples"], 5)
        self.assertTrue(settings["allow_simulated_weather"])
        self.assertEqual(settings["pump_flows"], [1.1, 1.2, 1.3, 1.4])
        self.assertEqual(irrigation.PUMP_FLOW, [1.1, 1.2, 1.3, 1.4])

    def test_cli_weather_fallback_requires_saved_permission(self):
        database.db_save_setting("allow_simulated_weather", True)
        weather.clear_weather_cache()
        config = self.controller._load_configuration()
        with patch.object(weather, "_fetch_json", side_effect=OSError("offline")):
            result = self.controller._get_weather(config)
        self.assertEqual(result["source"], "SIMULATED")

    def test_noninteractive_main_and_history_output(self):
        original_sigint = signal.getsignal(signal.SIGINT)
        result = cli.main(
            [
                "--database", database.DB_FILE,
                "--run", "--simulate", "--simulate-weather",
                "--cycles", "1", "--location", "Test Location",
                "--soil", "20,50,50,50",
            ],
            output=self.output,
        )
        self.assertEqual(result, cli.EXIT_OK)
        self.assertIn("Status: simulation_only", self.output.text)
        self.assertIs(signal.getsignal(signal.SIGINT), original_sigint)
        self.output.parts.clear()
        result = cli.main(
            ["--database", database.DB_FILE, "--history", "5"], output=self.output
        )
        self.assertEqual(result, cli.EXIT_OK)
        self.assertIn("Planned L", self.output.text)

    def test_interactive_weather_error_returns_to_menu(self):
        answers = iter(["6", "N", "0"])
        menu = cli.InteractiveTerminal(
            self.controller, input_fn=lambda prompt: next(answers), output=self.output
        )
        with patch.object(
            self.controller, "_get_weather", side_effect=weather.WeatherError("offline")
        ), patch.object(self.controller, "stop", side_effect=self.controller.stop):
            result = menu.run()
        self.assertEqual(result, cli.EXIT_OK)
        self.assertIn("Error: offline", self.output.text)

    def test_real_noninteractive_run_requires_explicit_confirmation(self):
        result = cli.main(
            ["--database", database.DB_FILE, "--run", "--location", "Test Location"],
            output=self.output,
        )
        self.assertEqual(result, cli.EXIT_ERROR)
        self.assertIn("--yes", self.output.text)


if __name__ == "__main__":
    unittest.main()
