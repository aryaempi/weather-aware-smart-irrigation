import os
import sys
import threading
import unittest


PROJECT_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app_final_gui_1"))
sys.path.insert(0, PROJECT_APP)

from core import sensor


class FakeSerial:
    def __init__(self):
        self.writes = []
        self.closed = False

    def write(self, payload):
        self.writes.append(payload)
        text = payload.decode("ascii").strip()
        if text.startswith("PUMP:"):
            _, sequence, states = text.split(":")
            sensor.process_serial_line(f"PUMP OK:{sequence}:{states}")
        return len(payload)

    def flush(self):
        pass

    def close(self):
        self.closed = True


class NonAcknowledgingSerial(FakeSerial):
    def write(self, payload):
        self.writes.append(payload)
        return len(payload)


class SensorTests(unittest.TestCase):
    def setUp(self):
        sensor._connection_callbacks.clear()
        sensor._pending_pump_acks.clear()
        sensor.serial_port = FakeSerial()
        sensor.current_port_name = "/dev/fake"
        sensor.device_verified = True
        sensor.enable_pump_commands()
        sensor.safety_stop_event.clear()
        sensor.last_safety_stop_reason = None
        sensor.set_system_state(sensor.STATE_STOPPED)

    def tearDown(self):
        sensor.disable_pump_commands()
        sensor.serial_port = None
        sensor.current_port_name = None

    def test_valid_sensor_line_and_median(self):
        self.assertEqual(sensor.parse_sensor_line("10,20,30,40"), (10, 20, 30, 40, 25))

    def test_invalid_sensor_lines_are_rejected(self):
        for value in ("1,2,3", "1,2,nan,4", "1,2,101,4", "1,2,inf,4"):
            with self.subTest(value=value):
                with self.assertRaises(sensor.SerialProtocolError):
                    sensor.parse_sensor_line(value)

    def test_connection_callback_order(self):
        calls = []
        sensor.on_connection_change(lambda connected, port: calls.append((connected, port)))
        sensor.process_serial_line("PONG:STM32_IRRIGATION_V1")
        self.assertEqual(calls[-1], (True, "/dev/fake"))

    def test_pump_command_requires_matching_ack(self):
        self.assertTrue(sensor.send_pump_command(1, 0, 1, 0, wait_ack=True))
        self.assertIn(b"PUMP:", sensor.serial_port.writes[-1])

    def test_safe_stop_sends_all_off(self):
        self.assertTrue(sensor.safe_stop_pumps())
        self.assertTrue(sensor.serial_port.writes[-1].endswith(b":0,0,0,0\n"))

    def test_missing_ack_fails_command(self):
        sensor.serial_port = NonAcknowledgingSerial()
        self.assertFalse(sensor.send_pump_command(1, 0, 0, 0, wait_ack=True, timeout=0.05))

    def test_sensor_stop_disables_expected_stream(self):
        sensor.send_serial_command("SENSOR:START")
        self.assertTrue(sensor.sensor_stream_expected)
        sensor.send_serial_command("SENSOR:STOP")
        self.assertFalse(sensor.sensor_stream_expected)

    def test_on_command_is_rejected_after_control_is_disabled(self):
        sensor.disable_pump_commands()
        self.assertFalse(sensor.send_pump_command(1, 0, 0, 0))
        self.assertTrue(sensor.send_pump_command(0, 0, 0, 0))

    def test_heartbeat_requires_acknowledgement(self):
        sensor.serial_port = NonAcknowledgingSerial()
        self.assertFalse(sensor.send_heartbeat(wait_ack=True, timeout=0.05))
        sensor.serial_port = FakeSerial()
        original_write = sensor.serial_port.write

        def heartbeat_write(payload):
            result = original_write(payload)
            if payload == b"HEARTBEAT\n":
                sensor.process_serial_line("HEARTBEAT OK")
            return result

        sensor.serial_port.write = heartbeat_write
        self.assertTrue(sensor.send_heartbeat(wait_ack=True, timeout=0.05))

    def test_sample_aggregation_requires_minimum_valid_data(self):
        with self.assertRaises(sensor.SerialProtocolError):
            sensor.aggregate_soil_samples([], 3)
        aggregated = sensor.aggregate_soil_samples(
            [(10, 20, 30, 40), (20, 30, 40, 50), (30, 40, 50, 60)], 3
        )
        self.assertEqual(aggregated, (20, 30, 40, 50, 35))

    def test_firmware_safety_stop_is_exposed_to_controller(self):
        result = sensor.process_serial_line("SAFETY STOP:WATCHDOG")
        self.assertEqual(result, "safety_stop")
        self.assertTrue(sensor.safety_stop_event.is_set())
        self.assertEqual(sensor.last_safety_stop_reason, "WATCHDOG")


if __name__ == "__main__":
    unittest.main()
