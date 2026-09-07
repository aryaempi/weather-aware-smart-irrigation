import os
import re
import sys
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT_APP = os.path.join(ROOT, "app_final_gui_1")
sys.path.insert(0, PROJECT_APP)

from core import irrigation, sensor


class FirmwareContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        firmware_path = os.path.join(ROOT, "soil_moisture_final_stm", "soil_moisture_10.ino")
        with open(firmware_path, "r", encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_serial_identity_and_baud_match_host(self):
        self.assertIn('PONG:STM32_IRRIGATION_V1', self.source)
        baud = int(re.search(r"Serial\.begin\((\d+)\)", self.source).group(1))
        self.assertEqual(baud, sensor.BAUD)

    def test_host_and_firmware_runtime_limits_match(self):
        minutes = int(
            re.search(r"MAX_CONTINUOUS_PUMP_MS\s*=\s*(\d+)UL\s*\*\s*60UL", self.source).group(1)
        )
        self.assertEqual(minutes, int(irrigation.MAX_SAFE_PUMP_RUNTIME_MINUTES))

    def test_sensor_sample_interval_matches_host_assumption(self):
        milliseconds = int(
            re.search(r"SEND_INTERVAL\s*=\s*(\d+)", self.source).group(1)
        )
        self.assertEqual(milliseconds / 1000, sensor.SENSOR_SAMPLE_INTERVAL_SECONDS)

    def test_safety_and_acknowledgement_protocol_is_present(self):
        for required in (
            "COMMAND_WATCHDOG_MS",
            "SAFETY STOP:WATCHDOG",
            "SAFETY STOP:MAX_RUNTIME",
            "PUMP OK:",
            "HEARTBEAT OK",
            "analogReadResolution(12)",
            "RELAY_INACTIVE_LEVEL",
        ):
            with self.subTest(required=required):
                self.assertIn(required, self.source)

    def test_firmware_rejects_trailing_pump_values(self):
        self.assertIn('cmd.endsWith(",")', self.source)
        self.assertIn('part != "0" && part != "1"', self.source)


if __name__ == "__main__":
    unittest.main()
