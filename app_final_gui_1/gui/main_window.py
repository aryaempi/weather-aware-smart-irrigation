import copy
import time
import threading

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QFrame, QMessageBox,
    QComboBox, QDoubleSpinBox, QDialog, QFormLayout
)
from PySide6.QtCore import Qt, QTimer, Signal

from gui.styles import Theme
from gui.widgets.toast import ToastNotification
from gui.pages.dashboard import DashboardPage
from gui.pages.plants import PlantsPage
from gui.pages.locations import LocationsPage
from gui.pages.weather_page import WeatherPage
from gui.pages.irrigation_page import IrrigationPage
from gui.pages.history import HistoryPage
from gui.pages.settings import SettingsPage


class StartAnalysisDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle("Configure Irrigation Analysis")
        self.setMinimumSize(450, 480)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {Theme.c('bg_card')}; }}
            QLabel {{ font-size: 13px; }}
        """)

        layout = QFormLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(28, 28, 28, 28)

        title = QLabel("Start Irrigation Analysis")
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 8px;")
        layout.addRow(title)

        from core.database import db_get_all_plants, db_get_all_locations

        plants = db_get_all_plants()
        self.plant_combo = QComboBox()
        self.plant_combo.setFixedWidth(260)
        self._plant_data = {}
        for p in plants:
            self.plant_combo.addItem(f"{p[1]} (Kc={p[2]:.2f})")
            self._plant_data[p[1]] = p
        layout.addRow("Plant:", self.plant_combo)

        locations = db_get_all_locations()
        self.loc_combo = QComboBox()
        self.loc_combo.setFixedWidth(260)
        self._loc_data = {}
        for loc in locations:
            self.loc_combo.addItem(loc[1])
            self._loc_data[loc[1]] = loc
        layout.addRow("Location:", self.loc_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Field", "Container"])
        self.mode_combo.setFixedWidth(260)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        layout.addRow("Cultivation Mode:", self.mode_combo)

        self.area_spin = QDoubleSpinBox()
        self.area_spin.setRange(0.1, 10000.0)
        self.area_spin.setValue(main_window._plant.get("area", 4.0))
        self.area_spin.setDecimals(5)
        self.area_spin.setSuffix(" m\u00b2")
        self.area_spin.setFixedWidth(260)
        layout.addRow("Cultivated Area:", self.area_spin)

        self.soil_depth_spin = QDoubleSpinBox()
        self.soil_depth_spin.setRange(0.01, 10.0)
        self.soil_depth_spin.setValue(main_window._settings.get("soil_depth", 0.20))
        self.soil_depth_spin.setDecimals(5)
        self.soil_depth_spin.setSuffix(" m")
        self.soil_depth_spin.setFixedWidth(260)
        self.soil_depth_row = QFrame()
        sd_layout = QHBoxLayout(self.soil_depth_row)
        sd_layout.setContentsMargins(0, 0, 0, 0)
        self.soil_depth_label = QLabel("Soil Depth:")
        sd_layout.addWidget(self.soil_depth_label)
        sd_layout.addWidget(self.soil_depth_spin)
        sd_layout.addStretch()
        layout.addRow(self.soil_depth_row)

        saved_mode = main_window._settings.get("cultivation_mode", "Field")
        self.mode_combo.setCurrentText(saved_mode)
        self._on_mode_changed(saved_mode)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(f"background-color: {Theme.c('border')}; color: {Theme.c('text')}; padding: 8px 20px; border-radius: 6px;")
        cancel_btn.clicked.connect(self.reject)

        start_btn = QPushButton("Start Analysis")
        start_btn.setStyleSheet(f"background-color: {Theme.c('primary')}; color: white; padding: 8px 20px; border-radius: 6px; font-weight: bold;")
        start_btn.clicked.connect(self._start)

        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(start_btn)
        layout.addRow(btn_layout)

    def _on_mode_changed(self, mode):
        label = "Container Soil Depth:" if mode == "Container" else "Root Zone Depth:"
        self.soil_depth_label.setText(label)
        self.soil_depth_row.setVisible(True)

    def _start(self):
        plant_name = self.plant_combo.currentText().split(" (")[0]
        loc_name = self.loc_combo.currentText()
        area = self.area_spin.value()

        if not plant_name or plant_name not in self._plant_data:
            QMessageBox.warning(self, "Error", "Please select a valid plant.")
            return
        if not loc_name or loc_name not in self._loc_data:
            QMessageBox.warning(self, "Error", "Please select a valid location.")
            return
        if area <= 0:
            QMessageBox.warning(self, "Error", "Land area must be a positive number.")
            return

        p = self._plant_data[plant_name]
        self.result_plant = {"name": p[1], "Kc": p[2], "area": area, "L": p[3], "U": p[4]}
        self.result_location = self._loc_data[loc_name]
        self.result_mode = self.mode_combo.currentText()
        self.result_soil_depth = self.soil_depth_spin.value()
        self.accept()


class MainWindow(QMainWindow):
    status_signal = Signal(str)
    sensor_signal = Signal(float, float, float, float, float)
    weather_signal = Signal(dict, str)
    decision_signal = Signal(str, float, float, float, float, str)
    pump_signal = Signal(int, bool, float, str)
    countdown_signal = Signal(str)
    collection_progress_signal = Signal(float)
    irrigation_progress_signal = Signal(float)
    serial_connection_signal = Signal(str, bool)
    toast_signal = Signal(str)
    running_signal = Signal(bool)
    history_refresh_signal = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Irrigation System")
        self.setMinimumSize(1366, 768)
        self.resize(1440, 900)

        self._settings = self._load_initial_settings()
        self._plant = {
            "name": self._settings.get("active_plant", "Wheat"),
            "Kc": 1.15,
            "area": self._settings.get("land_area", 4.0),
            "L": 45,
            "U": 70,
        }
        self._location = None
        self._weather = None
        self._running = False
        self._worker_thread = None
        self._stop_event = threading.Event()
        self._analysis_config = None
        self._system_state = "STOPPED"
        self._cultivation_mode = self._settings.get("cultivation_mode", "Field")
        self._soil_depth = self._settings.get("soil_depth", 0.20)

        self._load_plant_from_settings()
        self._load_location_from_settings()

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._sidebar = self._create_sidebar()
        main_layout.addWidget(self._sidebar)

        separator = QFrame()
        separator.setFixedWidth(1)
        separator.setStyleSheet(f"background-color: {Theme.c('border')};")
        main_layout.addWidget(separator)

        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(0, 0, 0, 0)
        right_panel.setSpacing(0)

        self._stack = QStackedWidget()
        self._create_pages()
        right_panel.addWidget(self._stack)

        self._footer = self._create_footer()
        right_panel.addWidget(self._footer)

        main_layout.addLayout(right_panel)

        self._toast = ToastNotification(self)

        self._connect_signals()
        self._start_clock()
        self._init_dashboard_from_settings()
        self._apply_settings_to_modules(reconnect=False)

        QTimer.singleShot(500, self._start_sensor)

        self._select_page(0)

    def _start_sensor(self):
        from core.sensor import start_sensor_reader
        start_sensor_reader()

    def _load_initial_settings(self):
        try:
            from core.database import db_load_all_settings
            return db_load_all_settings()
        except Exception:
            return {}

    def _load_plant_from_settings(self):
        from core.database import db_get_plant_by_name
        name = self._settings.get("active_plant", "Wheat")
        p = db_get_plant_by_name(name)
        if p:
            self._plant = {
                "name": p[1], "Kc": p[2],
                "area": self._settings.get("land_area", 4.0),
                "L": p[3], "U": p[4],
            }

    def _load_location_from_settings(self):
        from core.database import db_get_location_by_name
        name = self._settings.get("active_location", "")
        if name:
            loc = db_get_location_by_name(name)
            if loc:
                self._location = {"name": loc[1], "lat": loc[2], "lon": loc[3]}
                if hasattr(self, "_locations_page"):
                    self._locations_page.sync_active_location(loc)

    def _init_dashboard_from_settings(self):
        self._dashboard_page.update_plant(self._plant["name"])
        self._dashboard_page.update_area(self._plant["area"])
        self._dashboard_page.update_thresholds(self._plant["L"], self._plant["U"])
        self._dashboard_page.update_system_status("Idle")
        if self._location:
            self._dashboard_page.update_location(self._location["name"])
        if self._weather:
            src = self._settings.get("weather_source", "None")
            self._dashboard_page.update_weather_source(src)

    def _create_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        logo_frame = QFrame()
        logo_layout = QVBoxLayout(logo_frame)
        logo_layout.setContentsMargins(16, 20, 16, 20)

        logo_icon = QLabel("\U0001f331")
        logo_icon.setStyleSheet("font-size: 28px;")
        logo_layout.addWidget(logo_icon)

        logo_text = QLabel("Smart Irrigation")
        logo_text.setObjectName("sidebar_title")
        logo_layout.addWidget(logo_text)

        subtitle = QLabel("IoT Dashboard")
        subtitle.setStyleSheet("color: #607D8B; font-size: 11px;")
        logo_layout.addWidget(subtitle)

        layout.addWidget(logo_frame)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {Theme.c('border')}; margin: 0 16px;")
        layout.addWidget(sep)

        self._nav_buttons = []
        nav_items = [
            ("\U0001f3e0  Dashboard", 0),
            ("\U0001f331  Plants", 1),
            ("\U0001f4cd  Locations", 2),
            ("\U0001f326\ufe0f  Weather", 3),
            ("\U0001f4a7  Irrigation", 4),
            ("\U0001f4c8  History", 5),
            ("\u2699\ufe0f  Settings", 6),
        ]

        for text, index in nav_items:
            btn = QPushButton(text)
            btn.setObjectName("sidebar_btn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, idx=index: self._select_page(idx))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        layout.addStretch()

        exit_btn = QPushButton("\U0001f6aa  Exit")
        exit_btn.setObjectName("sidebar_btn")
        exit_btn.clicked.connect(self.close)
        layout.addWidget(exit_btn)

        return sidebar

    def _create_pages(self):
        self._dashboard_page = DashboardPage(self)
        self._plants_page = PlantsPage(self)
        self._locations_page = LocationsPage(self)
        self._weather_page = WeatherPage(self)
        self._irrigation_page = IrrigationPage(self)
        self._history_page = HistoryPage(self)
        self._settings_page = SettingsPage(self)

        self._pages = [
            self._dashboard_page,
            self._plants_page,
            self._locations_page,
            self._weather_page,
            self._irrigation_page,
            self._history_page,
            self._settings_page,
        ]

        for page in self._pages:
            self._stack.addWidget(page)

    def _create_footer(self):
        footer = QFrame()
        footer.setFixedHeight(32)
        footer.setStyleSheet(f"background-color: {Theme.c('bg_card')}; border-top: 1px solid {Theme.c('border')};")

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(16, 0, 16, 0)

        from core.database import db_health_check
        db_ok = db_health_check()
        self._db_status = QLabel(
            "\u25cf Database: Connected" if db_ok else "\u25cf Database: Error"
        )
        self._db_status.setObjectName("footer_label")
        self._db_status.setStyleSheet(
            f"color: {'#4CAF50' if db_ok else '#D32F2F'}; font-size: 11px;"
        )
        layout.addWidget(self._db_status)

        layout.addStretch()

        self._serial_status = QLabel("\u25cf Serial: Disconnected")
        self._serial_status.setObjectName("footer_label")
        self._serial_status.setStyleSheet("color: #D32F2F; font-size: 11px;")
        layout.addWidget(self._serial_status)

        layout.addSpacing(20)

        self._time_label = QLabel("")
        self._time_label.setObjectName("footer_label")
        layout.addWidget(self._time_label)

        return footer

    def _connect_signals(self):
        self.status_signal.connect(self._on_status)
        self.sensor_signal.connect(self._on_sensor)
        self.weather_signal.connect(self._on_weather)
        self.decision_signal.connect(self._on_decision)
        self.pump_signal.connect(self._on_pump)
        self.countdown_signal.connect(self._on_countdown)
        self.collection_progress_signal.connect(self._on_collection_progress)
        self.irrigation_progress_signal.connect(self._on_irrigation_progress)
        self.serial_connection_signal.connect(self._on_serial_connection)
        self.toast_signal.connect(self._on_toast)
        self.running_signal.connect(self._on_running_changed)
        self.history_refresh_signal.connect(self._history_page.refresh_data)

    def _on_running_changed(self, running):
        self._running = bool(running)
        self._irrigation_page.set_buttons_enabled(
            start=not running, stop=running, restart=True
        )

    def _on_toast(self, message):
        self.show_toast(message)

    def _select_page(self, index):
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setProperty("active", str(i == index).lower())
            btn.setChecked(i == index)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _start_clock(self):
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    def _update_clock(self):
        now = time.localtime()
        time_str = time.strftime("%H:%M:%S", now)
        date_str = time.strftime("%Y-%m-%d", now)
        self._time_label.setText(f"{date_str}  {time_str}")

    def show_toast(self, message):
        self._toast.show_toast(message)

    def configuration_locked(self):
        return bool(
            self._running
            or (self._worker_thread and self._worker_thread.is_alive())
        )

    def set_serial_connected(self, connected, port=""):
        self.serial_connection_signal.emit(port, connected)

    def _on_serial_connection(self, port, connected):
        if connected:
            self._serial_status.setText(f"\u25cf Serial: {port}")
            self._serial_status.setStyleSheet("color: #4CAF50; font-size: 11px;")
        else:
            self._serial_status.setText("\u25cf Serial: Disconnected")
            self._serial_status.setStyleSheet("color: #D32F2F; font-size: 11px;")

    def set_active_location(self, loc):
        self._location = {"name": loc[1], "lat": loc[2], "lon": loc[3]}
        self._dashboard_page.update_location(loc[1])
        if hasattr(self, "_locations_page"):
            self._locations_page.sync_active_location(loc)

    def _on_status(self, state):
        self._system_state = state
        dashboard_labels = {
            "STOPPED": "Stopped",
            "COLLECT": "Collecting",
            "DECIDE": "Analyzing",
            "IRRIGATE": "Irrigating",
            "WAIT": "Idle",
            "ERROR": "Error",
        }
        self._dashboard_page.update_system_status(dashboard_labels.get(state, state.title()))
        self._irrigation_page.update_state(state)

    def _on_sensor(self, s1, s2, s3, s4, median):
        self._dashboard_page.update_sensor_data(s1, s2, s3, s4, median)
        for i, v in enumerate([s1, s2, s3, s4]):
            self._irrigation_page.update_sensor(i, v)

    def _on_weather(self, weather, source):
        self._weather = weather
        self._dashboard_page.update_weather_source(source)
        rain48 = 0
        if weather and len(weather.get("rain", [])) >= 2:
            rain48 = weather["rain"][0] + weather["rain"][1]
        self._dashboard_page.update_weather(
            weather["et0"][0], weather["rain"][0], rain48,
            weather["tmin"][0], weather["tmax"][0], source
        )
        self._weather_page.update_weather(weather, source)

    def _on_decision(self, plant_name, kc, area, water_today, water_final, note):
        self._dashboard_page.update_decision(plant_name, kc, area, water_today, water_final, note)

    def _on_pump(self, index, on, flow, time_str):
        self._dashboard_page.update_pump(index, on, flow, time_str)
        self._irrigation_page.update_pump(index, on, time_str)

    def _on_countdown(self, text):
        self._irrigation_page.update_countdown(text)

    def _on_collection_progress(self, value):
        self._irrigation_page.update_collection_progress(value)

    def _on_irrigation_progress(self, value):
        self._irrigation_page.update_irrigation_progress(value)

    def start_analysis(self):
        if self._running or (self._worker_thread and self._worker_thread.is_alive()):
            self.show_toast("Analysis already running")
            return

        dlg = StartAnalysisDialog(self, self)
        if dlg.exec() != QDialog.Accepted:
            return

        self._plant = dlg.result_plant
        loc = dlg.result_location
        self._location = {"name": loc[1], "lat": loc[2], "lon": loc[3]}
        self._cultivation_mode = dlg.result_mode
        self._soil_depth = dlg.result_soil_depth

        self._dashboard_page.update_plant(self._plant["name"])
        self._dashboard_page.update_area(self._plant["area"])
        self._dashboard_page.update_thresholds(self._plant["L"], self._plant["U"])
        self._dashboard_page.update_location(self._location["name"])

        self._settings["active_plant"] = self._plant["name"]
        self._settings["active_location"] = self._location["name"]
        self._settings["land_area"] = self._plant["area"]
        self._settings["cultivation_mode"] = self._cultivation_mode
        self._settings["soil_depth"] = self._soil_depth
        from core.database import db_save_all_settings
        db_save_all_settings(self._settings)

        self._analysis_config = {
            "plant": copy.deepcopy(self._plant),
            "location": copy.deepcopy(self._location),
            "cultivation_mode": self._cultivation_mode,
            "soil_depth": self._soil_depth,
            "settings": copy.deepcopy(self._settings),
        }
        self._stop_event = threading.Event()
        from core import sensor as sens
        sens.enable_pump_commands()
        self.running_signal.emit(True)
        self._worker_thread = threading.Thread(
            target=self._run_analysis_loop,
            args=(self._stop_event, copy.deepcopy(self._analysis_config)),
            daemon=True,
            name="irrigation-analysis",
        )
        self._worker_thread.start()

    def stop_analysis(self):
        from core import sensor as sens
        self._stop_event.set()
        sens.disable_pump_commands()
        sens.set_system_state(sens.STATE_STOPPED)
        sens.send_serial_command("SENSOR:STOP")
        sens.safe_stop_pumps(retries=3, wait_ack=False)
        self.status_signal.emit("STOPPED")
        self.running_signal.emit(False)
        self.show_toast("Analysis stopped")

    def wait_for_worker(self, timeout=5.0):
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=max(0.0, float(timeout)))
        return not (self._worker_thread and self._worker_thread.is_alive())

    def restart_analysis(self):
        self.stop_analysis()
        self._wait_then_restart()

    def _wait_then_restart(self):
        if self._worker_thread and self._worker_thread.is_alive():
            QTimer.singleShot(100, self._wait_then_restart)
        else:
            self.start_analysis()

    def emergency_stop(self):
        from core import sensor as sens
        self._stop_event.set()
        sens.disable_pump_commands()
        stopped = sens.safe_stop_pumps(retries=5, wait_ack=False)
        sens.send_serial_command("SENSOR:STOP")
        sens.set_system_state(sens.STATE_STOPPED)
        self.status_signal.emit("STOPPED")
        self.running_signal.emit(False)
        for i in range(4):
            self.pump_signal.emit(i, False, 0, "0:00")
        message = "Emergency stop command sent" if stopped else "Emergency stop: serial link unavailable"
        self.show_toast(message)

    def refresh_weather(self):
        if not self._location:
            self.show_toast("No location selected")
            return
        location = copy.deepcopy(self._location)
        settings = copy.deepcopy(self._settings)

        def worker():
            from core.weather import get_weather_cached
            try:
                weather = get_weather_cached(
                    location["lat"],
                    location["lon"],
                    force_refresh=True,
                    allow_simulation=settings.get("allow_simulated_weather", False),
                    simulation_seed=settings.get("simulation_seed", 1),
                )
                self.weather_signal.emit(weather, weather.get("source", "UNKNOWN"))
            except Exception as exc:
                self.toast_signal.emit(f"Weather fetch failed: {exc}")

        threading.Thread(target=worker, daemon=True, name="weather-refresh").start()

    def apply_settings(self):
        values = self._settings_page.get_settings()
        values["active_plant"] = self._plant["name"]
        values["active_location"] = self._location["name"] if self._location else ""
        self._settings = values
        self._apply_settings_to_modules()
        self._plant["area"] = self._settings.get("land_area", self._plant["area"])
        self._cultivation_mode = self._settings.get("cultivation_mode", self._cultivation_mode)
        self._soil_depth = self._settings.get("soil_depth", self._soil_depth)
        self._dashboard_page.update_area(self._plant["area"])

    def _apply_settings_to_modules(self, reconnect=True):
        from core import sensor as sens
        sens.configure_serial(
            self._settings.get("serial_port", "auto"),
            self._settings.get("baud_rate", 115200),
            reconnect=reconnect,
        )

        from core import irrigation as irr
        flows = self._settings.get("pump_flows", [1.6, 1.6, 1.6, 1.6])
        if not isinstance(flows, list) or len(flows) != 4 or any(float(v) <= 0 for v in flows):
            raise ValueError("Four positive pump flow rates are required")
        irr.PUMP_FLOW = [float(value) for value in flows]

        from core import weather as w_mod
        w_mod.WEATHER_REFRESH_HOURS = self._settings.get("weather_refresh", 1)

    def _apply_sidebar_theme(self):
        self._sidebar.setStyleSheet(f"""
            QFrame#sidebar {{
                background-color: {Theme.c('bg_sidebar')};
            }}
        """)
        for btn in self._nav_buttons:
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._footer.setStyleSheet(
            f"background-color: {Theme.c('bg_card')}; border-top: 1px solid {Theme.c('border')};"
        )

    def _run_analysis_loop(self, stop_event, config):
        from core import sensor as sens
        try:
            while not stop_event.is_set():
                self._run_single_cycle(stop_event, config)
                if stop_event.is_set():
                    break
                interval = max(1.0, float(config["settings"].get("cycle_interval", 300)))
                self.status_signal.emit("WAIT")
                self.countdown_signal.emit(f"Next collection in {int(interval)}s")
                if stop_event.wait(interval):
                    break
        except Exception as exc:
            print(f"  [ANALYSIS ERROR] {exc}")
            sens.set_system_state(sens.STATE_ERROR)
            sens.safe_stop_pumps(retries=5, wait_ack=False)
            self.status_signal.emit("ERROR")
            self.toast_signal.emit(f"Analysis stopped: {exc}")
        finally:
            sens.send_serial_command("SENSOR:STOP")
            sens.disable_pump_commands()
            sens.safe_stop_pumps(retries=5, wait_ack=False)
            sens.set_system_state(sens.STATE_STOPPED)
            self.running_signal.emit(False)

    def _run_single_cycle(self, stop_event, config):
        from core import sensor as sens
        from core.database import db_save_record, db_update_irrigation_result
        from core.irrigation import (
            PumpSchedule, format_minutes_to_mmss,
            make_decision, zone_irrigation_control,
        )
        from core.weather import get_weather_cached

        plant = config["plant"]
        location = config["location"]
        settings = config["settings"]
        pump_flows = [float(value) for value in settings.get("pump_flows", [1.6] * 4)]
        lat, lon = location["lat"], location["lon"]
        record_id = None
        sample_started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")

        self.status_signal.emit("COLLECT")
        sens.set_system_state(sens.STATE_COLLECT)
        sens.clear_latest_soil_data()
        with sens.soil_samples_lock:
            sens.soil_samples.clear()
        if not sens.send_serial_command("SENSOR:START"):
            raise RuntimeError("sensor serial link is not available")

        duration = max(1.0, float(settings.get("collect_duration", 60)))
        started = time.monotonic()
        while time.monotonic() - started < duration:
            if stop_event.wait(0.2):
                return
            elapsed = time.monotonic() - started
            self.collection_progress_signal.emit(min(100.0, elapsed / duration * 100.0))
            self.countdown_signal.emit(f"Collecting: {max(0, int(duration - elapsed))}s remaining")

        sens.send_serial_command("SENSOR:STOP")
        sens.set_system_state(sens.STATE_DECIDE)
        self.status_signal.emit("DECIDE")
        self.countdown_signal.emit("Analyzing data...")
        if stop_event.is_set():
            return

        with sens.soil_samples_lock:
            samples = list(sens.soil_samples)
        minimum_samples = max(1, int(settings.get("minimum_samples", 3)))
        soil = sens.aggregate_soil_samples(samples, minimum_samples)
        self.sensor_signal.emit(*soil)

        weather = get_weather_cached(
            lat,
            lon,
            allow_simulation=settings.get("allow_simulated_weather", False),
            simulation_seed=settings.get("simulation_seed", 1),
        )
        source = weather.get("source", "UNKNOWN")
        self.weather_signal.emit(weather, source)
        if stop_event.is_set():
            return

        decision = make_decision(
            soil[4],
            plant,
            weather,
            config["cultivation_mode"],
            config["soil_depth"],
            soil_values=soil[:4],
            irrigation_efficiency=settings.get("irrigation_efficiency", 0.85),
            soil_water_capacity=settings.get("soil_water_capacity", 0.20),
            rainfall_efficiency=settings.get("rainfall_efficiency", 0.80),
        )
        decision["location_name"] = location["name"]
        decision["pump_flows"] = list(pump_flows)
        pump_states, pump_times = zone_irrigation_control(
            soil,
            decision["water_final"],
            plant["L"],
            zone_water_liters=decision["zone_water_liters"],
            max_runtime_minutes=settings.get("max_pump_runtime", 30.0),
            pump_flows=pump_flows,
        )
        self.decision_signal.emit(
            plant["name"], decision["kc"], plant["area"],
            decision["water_today"], decision["water_final"], decision["note"],
        )
        sample_meta = {
            "count": len(samples),
            "started_at": sample_started_at,
            "ended_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        record_id = db_save_record(
            decision, soil, weather, source, lat, lon, plant["name"],
            config["cultivation_mode"], config["soil_depth"], sample_meta,
            pump_states, pump_times,
        )

        schedule = PumpSchedule(tuple(pump_times))
        if not any(pump_states) or schedule.duration_seconds <= 0:
            db_update_irrigation_result(record_id, 0.0, "not_required", pump_states, pump_times, True)
            self.countdown_signal.emit("No irrigation needed")
            self.history_refresh_signal.emit()
            self.collection_progress_signal.emit(0)
            return

        if stop_event.is_set():
            db_update_irrigation_result(
                record_id, 0.0, "canceled_before_start", pump_states, pump_times, True
            )
            self.history_refresh_signal.emit()
            return

        sens.set_system_state(sens.STATE_IRRIGATE)
        self.status_signal.emit("IRRIGATE")
        acknowledged = sens.send_pump_command(*pump_states, wait_ack=True)
        if not acknowledged:
            sens.safe_stop_pumps(retries=5, wait_ack=False)
            db_update_irrigation_result(record_id, 0.0, "command_failed", pump_states, pump_times, False)
            self.history_refresh_signal.emit()
            raise RuntimeError("pump command was not acknowledged")

        started = time.monotonic()
        last_states = list(pump_states)
        last_heartbeat = started
        all_acknowledged = True
        irrigation_error = None
        try:
            while True:
                if sens.safety_stop_event.is_set():
                    reason = sens.last_safety_stop_reason or "UNKNOWN"
                    raise RuntimeError(f"firmware safety stop: {reason}")
                elapsed = time.monotonic() - started
                states = schedule.states_at(elapsed)
                if states != last_states:
                    if not sens.send_pump_command(*states, wait_ack=True):
                        all_acknowledged = False
                        raise RuntimeError("pump state change was not acknowledged")
                    last_states = states
                for index in range(4):
                    remaining = max(0.0, pump_times[index] * 60.0 - elapsed)
                    self.pump_signal.emit(
                        index, bool(states[index]), pump_flows[index],
                        format_minutes_to_mmss(remaining / 60.0),
                    )
                progress = min(100.0, elapsed / schedule.duration_seconds * 100.0)
                self.irrigation_progress_signal.emit(progress)
                remaining_total = max(0, int(round(schedule.duration_seconds - elapsed)))
                self.countdown_signal.emit(
                    f"Irrigating: {remaining_total // 60}:{remaining_total % 60:02d} remaining"
                )
                if not any(states):
                    break
                if stop_event.wait(0.2):
                    break
                if time.monotonic() - last_heartbeat >= 5.0:
                    if not sens.send_heartbeat():
                        all_acknowledged = False
                        raise RuntimeError("pump heartbeat failed")
                    last_heartbeat = time.monotonic()
        except Exception as exc:
            irrigation_error = exc
            all_acknowledged = False
        finally:
            stopped = sens.safe_stop_pumps(retries=5, wait_ack=True)
            all_acknowledged = all_acknowledged and stopped
            for index in range(4):
                self.pump_signal.emit(index, False, 0.0, "0:00")

        elapsed = min(time.monotonic() - started, schedule.duration_seconds)
        delivered = schedule.delivered_liters(elapsed, pump_flows)
        if irrigation_error is not None:
            status = "error"
        elif stop_event.is_set():
            status = "stopped"
        else:
            requested_runtime = [
                liters / flow if flow > 0 else 0.0
                for liters, flow in zip(decision["zone_water_liters"], pump_flows)
            ]
            was_capped = any(
                requested > actual + 1e-9
                for requested, actual in zip(requested_runtime, pump_times)
            )
            status = "completed_capped" if was_capped else "completed"
        db_update_irrigation_result(
            record_id, delivered, status, pump_states, pump_times, all_acknowledged
        )
        self.history_refresh_signal.emit()
        if irrigation_error is not None:
            raise irrigation_error
        completed = status in ("completed", "completed_capped")
        self.irrigation_progress_signal.emit(100 if completed else 0)
        self.countdown_signal.emit(
            "Irrigation complete (safety limit applied)"
            if status == "completed_capped"
            else "Irrigation complete" if completed else "Irrigation stopped"
        )
        if completed:
            self.toast_signal.emit("Irrigation cycle completed")
        sens.set_system_state(sens.STATE_COLLECT)
        self.collection_progress_signal.emit(0)

    def closeEvent(self, event):
        from core import sensor as sens
        self._stop_event.set()
        sens.disable_pump_commands()
        sens.send_serial_command("SENSOR:STOP")
        sens.safe_stop_pumps(retries=5, wait_ack=False)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        sens.disconnect_serial(send_stop=False)
        event.accept()
