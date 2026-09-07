import importlib.util
import os
import sys
import tempfile
import unittest


PROJECT_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app_final_gui_1"))
sys.path.insert(0, PROJECT_APP)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PYSIDE_AVAILABLE = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(PYSIDE_AVAILABLE, "PySide6 is not installed in this environment")
class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from core import database

        cls.tempdir = tempfile.TemporaryDirectory()
        cls.original_db = database.DB_FILE
        database.DB_FILE = os.path.join(cls.tempdir.name, "gui.db")
        database.init_database()
        database.db_add_location("GUI Test", 37.2, 49.6)
        database.db_save_setting("active_location", "GUI Test")
        cls.app = QApplication.instance() or QApplication([])

        from gui.main_window import MainWindow
        cls.window = MainWindow()

    @classmethod
    def tearDownClass(cls):
        from core import database, sensor

        sensor.disable_pump_commands()
        cls.window.close()
        cls.window.deleteLater()
        database.DB_FILE = cls.original_db
        cls.tempdir.cleanup()

    def test_all_pages_and_settings_are_constructed(self):
        self.assertEqual(self.window._stack.count(), 7)
        settings = self.window._settings_page.get_settings()
        self.assertEqual(settings["cultivation_mode"], "Field")
        self.assertEqual(len(settings["pump_flows"]), 4)
        self.assertLessEqual(settings["max_pump_runtime"], 30)

    def test_analysis_dialog_handles_plant_area_location_and_modes(self):
        from gui.main_window import StartAnalysisDialog

        dialog = StartAnalysisDialog(self.window, self.window)
        dialog.mode_combo.setCurrentText("Field")
        self.assertFalse(dialog.soil_depth_row.isHidden())
        self.assertIn("Root Zone", dialog.soil_depth_label.text())
        dialog.mode_combo.setCurrentText("Container")
        self.assertFalse(dialog.soil_depth_row.isHidden())
        self.assertIn("Container", dialog.soil_depth_label.text())
        dialog.area_spin.setValue(12.5)
        dialog.soil_depth_spin.setValue(0.35)
        dialog._start()
        self.assertEqual(dialog.result_mode, "Container")
        self.assertEqual(dialog.result_plant["area"], 12.5)
        self.assertEqual(dialog.result_soil_depth, 0.35)
        self.assertEqual(dialog.result_location[1], "GUI Test")

    def test_state_and_sensor_updates_reach_both_pages(self):
        self.window._on_status("COLLECT")
        self.assertEqual(self.window._system_state, "COLLECT")
        self.assertEqual(self.window._irrigation_page._state_label.text(), "COLLECTING")
        self.window._on_sensor(10, 20, 30, 40, 25)
        self.assertIn("10.0%", self.window._irrigation_page._sensor_labels[0].text())


if __name__ == "__main__":
    unittest.main()
