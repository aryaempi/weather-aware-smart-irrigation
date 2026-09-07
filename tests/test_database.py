import os
import math
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing


PROJECT_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app_final_gui_1"))
sys.path.insert(0, PROJECT_APP)

from core import database, irrigation


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_file = database.DB_FILE
        database.DB_FILE = os.path.join(self.tempdir.name, "test.db")
        database.init_database()

    def tearDown(self):
        database.DB_FILE = self.original_file
        self.tempdir.cleanup()

    def test_schema_and_missing_defaults_migrate(self):
        self.assertTrue(database.db_health_check())
        self.assertEqual(database.db_load_setting("pump_flows"), [1.6] * 4)
        with database._connect(readonly=True) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_legacy_schema_migrates_without_losing_history(self):
        legacy_path = os.path.join(self.tempdir.name, "legacy.db")
        with closing(sqlite3.connect(legacy_path)) as con:
            con.execute("""
                CREATE TABLE irrigation_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT,
                    plant_name TEXT, s1 REAL, s2 REAL, s3 REAL, s4 REAL,
                    soil_median REAL, et0_today REAL, rain_today REAL,
                    rain_next48 REAL, temp_min REAL, temp_max REAL, kc REAL,
                    area REAL, soil_depth REAL, water_needed_liters REAL,
                    water_final_liters REAL, decision_note TEXT,
                    weather_source TEXT, location_name TEXT, latitude REAL,
                    longitude REAL, cultivation_mode TEXT
                )
            """)
            con.execute(
                "INSERT INTO irrigation_records (timestamp, plant_name) VALUES (?, ?)",
                ("2025-01-01 00:00:00+0000", "Legacy Plant"),
            )
            con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            for index, value in enumerate((1.1, 1.2, 1.3, 1.4), 1):
                con.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)",
                    (f"pump_flow_{index}", str(value)),
                )
            con.commit()

        database.DB_FILE = legacy_path
        database.init_database()
        with database._connect(readonly=True) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM irrigation_records").fetchone()[0], 1)
            columns = {row[1] for row in con.execute("PRAGMA table_info(irrigation_records)")}
            self.assertIn("water_delivered_estimate_liters", columns)
        self.assertEqual(database.db_load_setting("pump_flows"), [1.1, 1.2, 1.3, 1.4])

    def test_settings_round_trip_preserves_types(self):
        database.db_save_setting("test_value", {"a": [1, True]})
        self.assertEqual(database.db_load_setting("test_value"), {"a": [1, True]})

    def test_plant_and_location_crud(self):
        self.assertTrue(database.db_add_plant("Test Plant", 1.0, 20, 60))
        self.assertTrue(database.db_update_plant("Test Plant", "Test Plant", 1.1, 25, 65))
        self.assertEqual(database.db_get_plant_by_name("Test Plant")[2], 1.1)
        self.assertTrue(database.db_delete_plant("Test Plant"))
        self.assertTrue(database.db_add_location("Test", 1, 2))
        self.assertTrue(database.db_update_location("Test", "Test 2", 3, 4))
        self.assertTrue(database.db_delete_location("Test 2"))

    def test_invalid_database_values_are_rejected(self):
        with self.assertRaises(ValueError):
            database.db_add_plant("Bad", 1, 70, 20)
        with self.assertRaises(ValueError):
            database.db_add_location("Bad", 100, 0)
        with self.assertRaises(ValueError):
            database.db_add_plant("Bad Kc", math.inf, 20, 60)
        with self.assertRaises(ValueError):
            database.db_save_setting("pump_flows", [1, 1, math.nan, 1])
        with self.assertRaises(ValueError):
            database.db_save_setting("max_pump_runtime", 31)

    def test_corrupt_known_setting_uses_safe_default(self):
        with database._connect() as con:
            con.execute(
                "UPDATE settings SET value=? WHERE key='pump_flows'",
                ('[1, 2, "bad", 4]',),
            )
        loaded = database.db_load_all_settings()
        self.assertEqual(loaded["pump_flows"], database.DEFAULT_SETTINGS["pump_flows"])

    def test_record_tracks_planned_and_execution_result(self):
        weather = {
            "et0": [4, 3], "rain": [0, 0], "tmin": [10, 11], "tmax": [20, 21],
            "source": "TEST",
        }
        plant = {"Kc": 1, "area": 4, "L": 40, "U": 60}
        soil = (20, 50, 50, 50, 50)
        decision = irrigation.make_decision(50, plant, weather, soil_values=soil[:4])
        decision["location_name"] = "Test"
        record_id = database.db_save_record(
            decision, soil, weather, "TEST", 1, 2, "Plant", "Field", 0.2,
            {"count": 10}, [1, 0, 0, 0], [1, 0, 0, 0],
        )
        database.db_update_irrigation_result(
            record_id, 1.5, "completed", [1, 0, 0, 0], [1, 0, 0, 0], True
        )
        record = database.db_get_record_by_id(record_id)
        self.assertGreater(record[9], 0)
        self.assertEqual(record[24], 1.5)
        self.assertEqual(record[25], "completed")
        self.assertEqual(record[28], 1)
        self.assertEqual(record[33], 10)

    def test_backup_and_restore(self):
        database.db_save_setting("marker", "before")
        backup = os.path.join(self.tempdir.name, "backup.db")
        database.db_backup(backup)
        database.db_save_setting("marker", "after")
        database.db_restore(backup)
        self.assertEqual(database.db_load_setting("marker"), "before")

    def test_filtered_export_uses_given_rows(self):
        output = os.path.join(self.tempdir.name, "history.csv")
        count = database.db_export_csv(output, [])
        self.assertEqual(count, 0)
        self.assertTrue(os.path.exists(output))


if __name__ == "__main__":
    unittest.main()
