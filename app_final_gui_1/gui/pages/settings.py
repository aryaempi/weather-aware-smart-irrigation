import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QSpinBox, QDoubleSpinBox, QScrollArea,
    QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt

from gui.styles import Theme, apply_theme


class SettingsPage(QWidget):
    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        self._outer_layout = QVBoxLayout(container)
        self._outer_layout.setContentsMargins(24, 20, 24, 20)
        self._outer_layout.setSpacing(16)

        title = QLabel("\u2699\ufe0f Settings")
        title.setObjectName("page_title")
        self._outer_layout.addWidget(title)

        irrigation_frame, igl = self._make_section("Irrigation Defaults")
        igl.setSpacing(10)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Cultivation Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Field", "Container"])
        self.mode_combo.setFixedWidth(160)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch()
        igl.addLayout(mode_row)

        area_row = QHBoxLayout()
        area_row.addWidget(QLabel("Cultivated Area (m\u00b2):"))
        self.area_spin = QDoubleSpinBox()
        self.area_spin.setRange(0.1, 10000.0)
        self.area_spin.setValue(4.0)
        self.area_spin.setSingleStep(0.5)
        self.area_spin.setDecimals(5)
        self.area_spin.setFixedWidth(120)
        self.area_spin.setSuffix(" m\u00b2")
        area_row.addWidget(self.area_spin)
        area_row.addStretch()
        igl.addLayout(area_row)

        self.soil_depth_widget = QWidget()
        soil_depth_layout = QHBoxLayout(self.soil_depth_widget)
        soil_depth_layout.setContentsMargins(0, 0, 0, 0)
        self.soil_depth_label = QLabel("Soil Depth (m):")
        soil_depth_layout.addWidget(self.soil_depth_label)
        self.soil_depth_spin = QDoubleSpinBox()
        self.soil_depth_spin.setRange(0.01, 10.0)
        self.soil_depth_spin.setValue(0.20)
        self.soil_depth_spin.setSingleStep(0.01)
        self.soil_depth_spin.setDecimals(5)
        self.soil_depth_spin.setFixedWidth(120)
        self.soil_depth_spin.setSuffix(" m")
        soil_depth_layout.addWidget(self.soil_depth_spin)
        soil_depth_layout.addStretch()
        igl.addWidget(self.soil_depth_widget)

        self._outer_layout.addWidget(irrigation_frame)

        serial_frame, sl = self._make_section("Serial Port Configuration")
        sl.setSpacing(10)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("Serial Port:"))
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.addItems(["auto", "/dev/ttyUSB0", "/dev/ttyACM0", "/dev/ttyUSB1"])
        self.port_combo.setFixedWidth(200)
        port_row.addWidget(self.port_combo)
        port_row.addStretch()
        sl.addLayout(port_row)

        baud_row = QHBoxLayout()
        baud_row.addWidget(QLabel("Baud Rate:"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.baud_combo.setCurrentText("115200")
        self.baud_combo.setFixedWidth(150)
        baud_row.addWidget(self.baud_combo)
        baud_row.addStretch()
        sl.addLayout(baud_row)

        self._outer_layout.addWidget(serial_frame)

        sensor_frame, senl = self._make_section("Sensor Settings")
        senl.setSpacing(10)

        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("Collection Duration (seconds):"))
        self.dur_spin = QSpinBox()
        self.dur_spin.setRange(10, 300)
        self.dur_spin.setValue(60)
        self.dur_spin.setFixedWidth(100)
        dur_row.addWidget(self.dur_spin)
        dur_row.addStretch()
        senl.addLayout(dur_row)

        cycle_row = QHBoxLayout()
        cycle_row.addWidget(QLabel("Cycle Interval (seconds):"))
        self.cycle_spin = QSpinBox()
        self.cycle_spin.setRange(1, 86400)
        self.cycle_spin.setValue(300)
        self.cycle_spin.setFixedWidth(100)
        cycle_row.addWidget(self.cycle_spin)
        cycle_row.addStretch()
        senl.addLayout(cycle_row)

        samples_row = QHBoxLayout()
        samples_row.addWidget(QLabel("Minimum Valid Samples:"))
        self.samples_spin = QSpinBox()
        self.samples_spin.setRange(1, 150)
        self.samples_spin.setValue(3)
        self.samples_spin.setFixedWidth(100)
        samples_row.addWidget(self.samples_spin)
        samples_row.addStretch()
        senl.addLayout(samples_row)

        self._outer_layout.addWidget(sensor_frame)

        weather_frame, wl = self._make_section("Weather Settings")
        wl.setSpacing(10)

        refresh_row = QHBoxLayout()
        refresh_row.addWidget(QLabel("Refresh Interval (hours):"))
        self.weather_refresh = QSpinBox()
        self.weather_refresh.setRange(1, 24)
        self.weather_refresh.setValue(1)
        self.weather_refresh.setFixedWidth(80)
        refresh_row.addWidget(self.weather_refresh)
        refresh_row.addStretch()
        wl.addLayout(refresh_row)

        simulation_row = QHBoxLayout()
        simulation_row.addWidget(QLabel("Allow Simulated Weather:"))
        self.simulation_combo = QComboBox()
        self.simulation_combo.addItems(["Disabled", "Enabled"])
        self.simulation_combo.setFixedWidth(120)
        simulation_row.addWidget(self.simulation_combo)
        simulation_row.addStretch()
        wl.addLayout(simulation_row)

        self._outer_layout.addWidget(weather_frame)

        pump_frame, pl = self._make_section("Pump Flow Rates (L/min)")
        pl.setSpacing(8)
        self.pump_spins = []
        for i in range(4):
            row = QHBoxLayout()
            row.addWidget(QLabel(f"Pump {i+1}:"))
            spin = QDoubleSpinBox()
            spin.setRange(0.1, 10.0)
            spin.setValue(1.6)
            spin.setSingleStep(0.1)
            spin.setDecimals(5)
            spin.setFixedWidth(100)
            row.addWidget(spin)
            row.addStretch()
            pl.addLayout(row)
            self.pump_spins.append(spin)

        runtime_row = QHBoxLayout()
        runtime_row.addWidget(QLabel("Maximum Continuous Runtime:"))
        self.max_runtime_spin = QDoubleSpinBox()
        self.max_runtime_spin.setRange(0.1, 30.0)
        self.max_runtime_spin.setValue(30.0)
        self.max_runtime_spin.setSuffix(" min")
        self.max_runtime_spin.setFixedWidth(120)
        runtime_row.addWidget(self.max_runtime_spin)
        runtime_row.addStretch()
        pl.addLayout(runtime_row)
        self._outer_layout.addWidget(pump_frame)

        model_frame, ml = self._make_section("Irrigation Model")
        self.efficiency_spin = QDoubleSpinBox()
        self.efficiency_spin.setRange(0.01, 1.0)
        self.efficiency_spin.setDecimals(3)
        self.efficiency_spin.setValue(0.85)
        self.capacity_spin = QDoubleSpinBox()
        self.capacity_spin.setRange(0.001, 1.0)
        self.capacity_spin.setDecimals(3)
        self.capacity_spin.setValue(0.20)
        self.rain_efficiency_spin = QDoubleSpinBox()
        self.rain_efficiency_spin.setRange(0.0, 1.0)
        self.rain_efficiency_spin.setDecimals(3)
        self.rain_efficiency_spin.setValue(0.80)
        for label, widget in [
            ("Application Efficiency:", self.efficiency_spin),
            ("Calibrated Soil Water Capacity:", self.capacity_spin),
            ("Effective Rain Fraction:", self.rain_efficiency_spin),
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            widget.setFixedWidth(120)
            row.addWidget(widget)
            row.addStretch()
            ml.addLayout(row)
        self._outer_layout.addWidget(model_frame)

        theme_frame, tl = self._make_section("Appearance")
        tl.setSpacing(10)

        dark_row = QHBoxLayout()
        dark_row.addWidget(QLabel("Dark Mode:"))
        self.dark_combo = QComboBox()
        self.dark_combo.addItems(["Light", "Dark"])
        self.dark_combo.setFixedWidth(120)
        dark_row.addWidget(self.dark_combo)
        dark_row.addStretch()

        apply_theme_btn = QPushButton("Apply Theme")
        apply_theme_btn.setObjectName("primary_btn")
        apply_theme_btn.setFixedWidth(150)
        apply_theme_btn.clicked.connect(self._apply_theme)
        dark_row.addWidget(apply_theme_btn)

        tl.addLayout(dark_row)
        self._outer_layout.addWidget(theme_frame)

        lang_frame, langl = self._make_section("Language")
        langl.setSpacing(10)
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["English"])
        self.lang_combo.setToolTip("Only English is currently installed.")
        self.lang_combo.setFixedWidth(200)
        lang_row.addWidget(self.lang_combo)
        lang_row.addStretch()
        langl.addLayout(lang_row)
        self._outer_layout.addWidget(lang_frame)

        db_frame, dbl = self._make_section("Database")
        dbl.setSpacing(10)

        retention_row = QHBoxLayout()
        retention_row.addWidget(QLabel("History Retention (days):"))
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 3650)
        self.retention_spin.setValue(365)
        self.retention_spin.setFixedWidth(100)
        retention_row.addWidget(self.retention_spin)
        retention_row.addStretch()
        dbl.addLayout(retention_row)

        btn_row = QHBoxLayout()
        backup_btn = QPushButton("\U0001f4be Backup Database")
        backup_btn.setObjectName("outline_btn")
        backup_btn.clicked.connect(self._backup)
        btn_row.addWidget(backup_btn)

        restore_btn = QPushButton("\U0001f504 Restore Database")
        restore_btn.setObjectName("outline_btn")
        restore_btn.clicked.connect(self._restore)
        btn_row.addWidget(restore_btn)
        btn_row.addStretch()
        dbl.addLayout(btn_row)

        self._outer_layout.addWidget(db_frame)

        save_frame = QFrame()
        save_frame.setObjectName("card")
        save_layout = QHBoxLayout(save_frame)
        save_layout.setContentsMargins(16, 12, 16, 12)
        save_layout.addStretch()
        self._save_btn = QPushButton("\U0001f4be Save All Settings")
        self._save_btn.setObjectName("success_btn")
        self._save_btn.setFixedHeight(40)
        self._save_btn.clicked.connect(self._save_settings)
        save_layout.addWidget(self._save_btn)
        self._outer_layout.addWidget(save_frame)

        self._outer_layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _make_section(self, title):
        frame = QFrame()
        frame.setObjectName("card")
        header = QLabel(title)
        header.setStyleSheet("font-size: 14px; font-weight: bold; padding: 12px 16px 4px 16px;")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.addWidget(header)
        return frame, layout

    def _on_mode_changed(self, mode):
        label = "Container Soil Depth (m):" if mode == "Container" else "Root Zone Depth (m):"
        self.soil_depth_label.setText(label)
        self.soil_depth_widget.setVisible(True)

    def _load_settings(self):
        try:
            from core.database import db_load_all_settings
            s = db_load_all_settings()
            self.area_spin.setValue(float(s.get("land_area", 4.0)))
            self.port_combo.setCurrentText(s.get("serial_port", "auto"))
            self.baud_combo.setCurrentText(str(int(s.get("baud_rate", 115200))))
            self.dur_spin.setValue(int(s.get("collect_duration", 60)))
            self.cycle_spin.setValue(int(s.get("cycle_interval", 300)))
            self.samples_spin.setValue(int(s.get("minimum_samples", 3)))
            self.weather_refresh.setValue(int(s.get("weather_refresh", 1)))
            self.simulation_combo.setCurrentText(
                "Enabled" if s.get("allow_simulated_weather", False) else "Disabled"
            )
            flows = s.get("pump_flows", [1.6, 1.6, 1.6, 1.6])
            if isinstance(flows, list):
                for i, spin in enumerate(self.pump_spins):
                    if i < len(flows):
                        spin.setValue(float(flows[i]))
            self.max_runtime_spin.setValue(float(s.get("max_pump_runtime", 30.0)))
            self.efficiency_spin.setValue(float(s.get("irrigation_efficiency", 0.85)))
            self.capacity_spin.setValue(float(s.get("soil_water_capacity", 0.20)))
            self.rain_efficiency_spin.setValue(float(s.get("rainfall_efficiency", 0.80)))
            self.dark_combo.setCurrentText("Dark" if s.get("dark_mode", False) else "Light")
            self.lang_combo.setCurrentText(s.get("language", "English"))
            mode = s.get("cultivation_mode", "Field")
            self.mode_combo.setCurrentText(mode)
            self.soil_depth_spin.setValue(float(s.get("soil_depth", 0.20)))
            self.retention_spin.setValue(int(s.get("history_retention_days", 365)))
            self._on_mode_changed(mode)
        except Exception as e:
            print(f"  [Settings] Load error: {e}")

    def _save_settings(self):
        if self.main_window and self.main_window.configuration_locked():
            QMessageBox.warning(
                self, "Analysis Running",
                "Stop the irrigation analysis before changing control settings.",
            )
            return
        settings = self.get_settings()
        from core.sensor import SENSOR_SAMPLE_INTERVAL_SECONDS
        expected_samples = int(
            settings["collect_duration"] / SENSOR_SAMPLE_INTERVAL_SECONDS
        )
        if settings["minimum_samples"] > max(1, expected_samples):
            QMessageBox.warning(
                self, "Invalid Sensor Settings",
                "Minimum valid samples exceeds the samples expected during the collection time.",
            )
            return
        try:
            from core.database import db_save_all_settings
            db_save_all_settings(settings)
        except Exception as e:
            print(f"  [Settings] DB save error: {e}")
            if self.main_window:
                self.main_window.show_toast(f"Failed to save: {e}")
            return

        if self.main_window:
            self.main_window.apply_settings()
            self._apply_theme()
            self.main_window.show_toast("Settings saved successfully")

    def _apply_theme(self):
        dark = self.dark_combo.currentText() == "Dark"
        from PySide6.QtWidgets import QApplication
        qapp = QApplication.instance()
        if qapp:
            apply_theme(qapp, dark)
            from core.database import db_save_setting
            db_save_setting("dark_mode", dark)
            if self.main_window:
                self.main_window._apply_sidebar_theme()
                self.main_window.show_toast(f"Theme changed to {'Dark' if dark else 'Light'} mode")

    def _backup(self):
        from core.database import db_backup
        path, _ = QFileDialog.getSaveFileName(
            self, "Backup Database", "irrigation_backup.db", "Database Files (*.db)"
        )
        if path:
            try:
                db_backup(path)
                if self.main_window:
                    self.main_window.show_toast(f"Database backed up to {os.path.basename(path)}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Backup failed: {e}")

    def _restore(self):
        from core.database import db_restore
        path, _ = QFileDialog.getOpenFileName(
            self, "Restore Database", "", "Database Files (*.db)"
        )
        if path:
            reply = QMessageBox.question(
                self, "Confirm Restore",
                "This will overwrite the current database. Continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                try:
                    if self.main_window:
                        self.main_window.stop_analysis()
                        if not self.main_window.wait_for_worker(5.0):
                            raise RuntimeError("Analysis worker did not stop before database restore")
                    db_restore(path)
                    self._load_settings()
                    if self.main_window:
                        from core.database import db_load_all_settings
                        self.main_window._settings = db_load_all_settings()
                        self.main_window._load_plant_from_settings()
                        self.main_window._load_location_from_settings()
                        self.main_window._init_dashboard_from_settings()
                        self.main_window._plants_page.refresh_data()
                        self.main_window._locations_page.refresh_data()
                        self.main_window._history_page.refresh_data()
                        self.main_window._apply_settings_to_modules()
                        self.main_window.show_toast("Database restored successfully")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Restore failed: {e}")

    def get_settings(self):
        return {
            "serial_port": self.port_combo.currentText(),
            "baud_rate": int(self.baud_combo.currentText()),
            "collect_duration": self.dur_spin.value(),
            "cycle_interval": self.cycle_spin.value(),
            "minimum_samples": self.samples_spin.value(),
            "weather_refresh": self.weather_refresh.value(),
            "allow_simulated_weather": self.simulation_combo.currentText() == "Enabled",
            "simulation_seed": 1,
            "pump_flows": [s.value() for s in self.pump_spins],
            "max_pump_runtime": self.max_runtime_spin.value(),
            "irrigation_efficiency": self.efficiency_spin.value(),
            "soil_water_capacity": self.capacity_spin.value(),
            "rainfall_efficiency": self.rain_efficiency_spin.value(),
            "dark_mode": self.dark_combo.currentText() == "Dark",
            "language": self.lang_combo.currentText(),
            "land_area": self.area_spin.value(),
            "cultivation_mode": self.mode_combo.currentText(),
            "soil_depth": self.soil_depth_spin.value(),
            "history_retention_days": self.retention_spin.value(),
        }
