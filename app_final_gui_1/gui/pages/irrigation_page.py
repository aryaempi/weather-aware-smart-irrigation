from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QProgressBar, QGridLayout, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt

from gui.styles import Theme


class IrrigationPage(QWidget):
    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("\U0001f4a7 Irrigation Control")
        title.setObjectName("page_title")
        layout.addWidget(title)

        status_frame = QFrame()
        status_frame.setObjectName("card")
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(20, 16, 20, 16)

        lbl = QLabel("Current State:")
        lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        status_layout.addWidget(lbl)

        self._state_label = QLabel("STOPPED")
        self._state_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #D32F2F;")
        status_layout.addWidget(self._state_label)
        status_layout.addStretch()

        self._countdown_label = QLabel("")
        self._countdown_label.setStyleSheet("font-size: 14px; color: #757575;")
        status_layout.addWidget(self._countdown_label)
        layout.addWidget(status_frame)

        progress_frame = QFrame()
        progress_frame.setObjectName("card")
        prog_layout = QVBoxLayout(progress_frame)
        prog_layout.setContentsMargins(20, 16, 20, 16)
        prog_layout.setSpacing(8)

        collect_label = QLabel("Sensor Collection:")
        collect_label.setStyleSheet("font-size: 12px; color: #9E9E9E;")
        prog_layout.addWidget(collect_label)
        self._collect_progress = QProgressBar()
        self._collect_progress.setRange(0, 100)
        self._collect_progress.setValue(0)
        self._collect_progress.setTextVisible(True)
        prog_layout.addWidget(self._collect_progress)

        irrigate_label = QLabel("Irrigation Progress:")
        irrigate_label.setStyleSheet("font-size: 12px; color: #9E9E9E;")
        prog_layout.addWidget(irrigate_label)
        self._irrigate_progress = QProgressBar()
        self._irrigate_progress.setRange(0, 100)
        self._irrigate_progress.setValue(0)
        self._irrigate_progress.setTextVisible(True)
        prog_layout.addWidget(self._irrigate_progress)
        layout.addWidget(progress_frame)

        sensor_frame = QFrame()
        sensor_frame.setObjectName("card")
        sensor_layout = QGridLayout(sensor_frame)
        sensor_layout.setContentsMargins(20, 16, 20, 16)
        sensor_layout.setSpacing(10)

        sl = QLabel("Sensor Status")
        sl.setStyleSheet("font-size: 14px; font-weight: bold;")
        sensor_layout.addWidget(sl, 0, 0, 1, 4)

        self._sensor_labels = []
        for i in range(4):
            lbl = QLabel(f"S{i+1}: ---")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 13px; padding: 8px; background-color: #F5F7FA; border-radius: 6px;")
            sensor_layout.addWidget(lbl, 1, i)
            self._sensor_labels.append(lbl)
        layout.addWidget(sensor_frame)

        pump_frame = QFrame()
        pump_frame.setObjectName("card")
        pump_layout = QGridLayout(pump_frame)
        pump_layout.setContentsMargins(20, 16, 20, 16)
        pump_layout.setSpacing(10)

        pl = QLabel("Pump Status")
        pl.setStyleSheet("font-size: 14px; font-weight: bold;")
        pump_layout.addWidget(pl, 0, 0, 1, 4)

        self._pump_labels = []
        for i in range(4):
            lbl = QLabel(f"P{i+1}: OFF")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-size: 13px; padding: 8px; background-color: #F5F7FA; border-radius: 6px;")
            pump_layout.addWidget(lbl, 1, i)
            self._pump_labels.append(lbl)
        layout.addWidget(pump_frame)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self._start_btn = QPushButton("\u25b6 Start Analysis")
        self._start_btn.setObjectName("primary_btn")
        self._start_btn.setFixedHeight(42)
        self._start_btn.clicked.connect(self._start)
        btn_layout.addWidget(self._start_btn)

        self._stop_btn = QPushButton("\u23f9 Stop")
        self._stop_btn.setObjectName("danger_btn")
        self._stop_btn.setFixedHeight(42)
        self._stop_btn.clicked.connect(self._stop)
        btn_layout.addWidget(self._stop_btn)

        self._restart_btn = QPushButton("\U0001f504 Restart")
        self._restart_btn.setObjectName("warning_btn")
        self._restart_btn.setFixedHeight(42)
        self._restart_btn.clicked.connect(self._restart)
        btn_layout.addWidget(self._restart_btn)

        self._emergency_btn = QPushButton("\u26d4 Emergency Stop")
        self._emergency_btn.setObjectName("danger_btn")
        self._emergency_btn.setFixedHeight(42)
        self._emergency_btn.setStyleSheet(
            f"background-color: {Theme.c('danger')}; color: white; font-size: 14px; font-weight: bold;"
        )
        self._emergency_btn.clicked.connect(self._emergency_stop)
        btn_layout.addWidget(self._emergency_btn)

        layout.addLayout(btn_layout)
        layout.addStretch()

    def _start(self):
        if self.main_window and hasattr(self.main_window, 'start_analysis'):
            self.main_window.start_analysis()

    def _stop(self):
        if self.main_window and hasattr(self.main_window, 'stop_analysis'):
            self.main_window.stop_analysis()

    def _restart(self):
        if self.main_window and hasattr(self.main_window, 'restart_analysis'):
            self.main_window.restart_analysis()

    def _emergency_stop(self):
        if self.main_window and hasattr(self.main_window, 'emergency_stop'):
            self.main_window.emergency_stop()

    def update_state(self, state):
        colors = {
            "STOPPED": "#D32F2F",
            "COLLECT": "#FB8C00",
            "DECIDE": "#1976D2",
            "IRRIGATE": "#2E7D32",
            "WAIT": "#757575",
            "ERROR": "#D32F2F",
        }
        labels = {
            "STOPPED": "STOPPED",
            "COLLECT": "COLLECTING",
            "DECIDE": "ANALYZING",
            "IRRIGATE": "IRRIGATING",
            "WAIT": "WAITING",
            "ERROR": "ERROR",
        }
        color = colors.get(state, "#757575")
        label = labels.get(state, state)
        self._state_label.setText(label)
        self._state_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {color};")

    def update_countdown(self, text):
        self._countdown_label.setText(text)

    def update_collection_progress(self, value):
        self._collect_progress.setValue(int(value))

    def update_irrigation_progress(self, value):
        self._irrigate_progress.setValue(int(value))

    def update_sensor(self, index, value):
        if 0 <= index < 4:
            color = Theme.gauge_color_by_moisture(value)
            self._sensor_labels[index].setText(f"S{index+1}: {value:.1f}%")
            self._sensor_labels[index].setStyleSheet(
                f"font-size: 13px; padding: 8px; background-color: {color}22; "
                f"color: {color}; border-radius: 6px; font-weight: bold;"
            )

    def update_pump(self, index, on, time_str=""):
        if 0 <= index < 4:
            if on:
                self._pump_labels[index].setText(f"P{index+1}: ON {time_str}")
                self._pump_labels[index].setStyleSheet(
                    "font-size: 13px; padding: 8px; background-color: #4CAF5022; "
                    "color: #4CAF50; border-radius: 6px; font-weight: bold;"
                )
            else:
                self._pump_labels[index].setText(f"P{index+1}: OFF")
                self._pump_labels[index].setStyleSheet(
                    "font-size: 13px; padding: 8px; background-color: #F5F7FA; "
                    "border-radius: 6px;"
                )

    def set_buttons_enabled(self, start=True, stop=True, restart=True):
        self._start_btn.setEnabled(start)
        self._stop_btn.setEnabled(stop)
        self._restart_btn.setEnabled(restart)
