import os
import sys
import tempfile
import unittest


PROJECT_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app_final_gui_1"))
sys.path.insert(0, PROJECT_APP)

from core import database, irrigation, sensor


class FakeSerial:
    def __init__(self):
        self.commands = []

    def write(self, payload):
        text = payload.decode("ascii").strip()
        self.commands.append(text)
        if text.startswith("PUMP:"):
            _, sequence, states = text.split(":")
            sensor.process_serial_line(f"PUMP OK:{sequence}:{states}")
        return len(payload)

    def flush(self):
        pass


class CompleteCycleIntegrationTest(unittest.TestCase):
    def test_sensor_to_decision_to_pump_to_history(self):
        tempdir = tempfile.TemporaryDirectory()
        original_db = database.DB_FILE
        original_serial = sensor.serial_port
        original_verified = sensor.device_verified
        try:
            database.DB_FILE = os.path.join(tempdir.name, "cycle.db")
            database.init_database()
            sensor.serial_port = FakeSerial()
            sensor.current_port_name = "/dev/fake"
            sensor.device_verified = True
            sensor.enable_pump_commands()
            sensor.set_system_state(sensor.STATE_COLLECT)
            sensor.soil_samples.clear()
            for line in ("20,50,50,50", "22,51,49,50", "21,50,50,49"):
                sensor.process_serial_line(line)
            samples = list(sensor.soil_samples)
            values = [sum(row[i] for row in samples) / len(samples) for i in range(4)]
            ordered = sorted(values)
            soil = (*values, (ordered[1] + ordered[2]) / 2)
            weather = {
                "et0": [4, 3], "rain": [0, 0], "tmin": [10, 11],
                "tmax": [20, 21], "source": "TEST",
            }
            plant = {"name": "Plant", "Kc": 1, "area": 4, "L": 40, "U": 60}
            decision = irrigation.make_decision(
                soil[4], plant, weather, "Field", 0.2, soil[:4]
            )
            decision["location_name"] = "Test"
            states, times = irrigation.zone_irrigation_control(
                soil, decision["water_final"], plant["L"], decision["zone_water_liters"]
            )
            record_id = database.db_save_record(
                decision, soil, weather, "TEST", 1, 2, plant["name"], "Field", 0.2,
                {"count": len(samples)}, states, times,
            )
            self.assertTrue(sensor.send_pump_command(*states))
            schedule = irrigation.PumpSchedule(tuple(times))
            delivered = schedule.delivered_liters(schedule.duration_seconds)
            self.assertTrue(sensor.safe_stop_pumps())
            database.db_update_irrigation_result(
                record_id, delivered, "completed", states, times, True
            )
            record = database.db_get_record_by_id(record_id)
            self.assertEqual(states, [1, 0, 0, 0])
            self.assertEqual(record[25], "completed")
            self.assertGreater(record[24], 0)
            self.assertTrue(sensor.serial_port.commands[-1].endswith(":0,0,0,0"))
        finally:
            sensor.disable_pump_commands()
            sensor.serial_port = original_serial
            sensor.current_port_name = None
            sensor.device_verified = original_verified
            database.DB_FILE = original_db
            tempdir.cleanup()


if __name__ == "__main__":
    unittest.main()
