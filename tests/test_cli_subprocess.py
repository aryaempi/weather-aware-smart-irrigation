import os
import subprocess
import sys
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT_APP = os.path.join(ROOT, "app_final_gui_1")
sys.path.insert(0, PROJECT_APP)

from core import database


class CliSubprocessTests(unittest.TestCase):
    def test_executable_file_runs_two_complete_simulated_cycles(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = os.path.join(tempdir, "subprocess.db")
            original_db = database.DB_FILE
            try:
                database.DB_FILE = db_path
                database.init_database()
                database.db_add_location("Subprocess Location", 37.2, 49.6)
                database.db_save_setting("active_location", "Subprocess Location")
            finally:
                database.DB_FILE = original_db

            command = [
                sys.executable,
                "-B",
                os.path.join(PROJECT_APP, "app_6.0.py"),
                "--database",
                db_path,
                "--run",
                "--simulate",
                "--simulate-weather",
                "--soil",
                "20,50,50,50",
                "--cycles",
                "2",
                "--interval",
                "0",
                "--location",
                "Subprocess Location",
            ]
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=30, check=False
            )
            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertEqual(completed.stdout.count("=== Irrigation cycle"), 2)
            self.assertIn("Status: simulation_only", completed.stdout)

            database.DB_FILE = db_path
            try:
                rows = database.db_get_history(10)
            finally:
                database.DB_FILE = original_db
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row[25].startswith("simulation_only") for row in rows))
            self.assertTrue(all(row[24] == 0 for row in rows))


if __name__ == "__main__":
    unittest.main()
