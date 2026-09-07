from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QGridLayout, QPushButton
)
from PySide6.QtCore import Qt

from gui.styles import Theme


class ForecastCard(QFrame):
    def __init__(self, day_label="Today", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumHeight(140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self._day = QLabel(day_label)
        self._day.setStyleSheet("font-size: 12px; font-weight: bold; color: #9E9E9E;")
        layout.addWidget(self._day)

        self._icon = QLabel("\u2600")
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet("font-size: 32px;")
        layout.addWidget(self._icon)

        self._temp = QLabel("- / -")
        self._temp.setAlignment(Qt.AlignCenter)
        self._temp.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self._temp)

        self._rain = QLabel("Rain: - mm")
        self._rain.setAlignment(Qt.AlignCenter)
        self._rain.setStyleSheet("font-size: 12px; color: #1976D2;")
        layout.addWidget(self._rain)

        self._et0 = QLabel("ET\u2080: - mm")
        self._et0.setAlignment(Qt.AlignCenter)
        self._et0.setStyleSheet("font-size: 12px; color: #FB8C00;")
        layout.addWidget(self._et0)

    def set_data(self, tmin, tmax, rain, et0, icon="\u2600"):
        self._icon.setText(icon)
        self._temp.setText(f"{tmin:.1f}\u00b0 / {tmax:.1f}\u00b0C")
        self._rain.setText(f"Rain: {rain:.1f} mm")
        self._et0.setText(f"ET\u2080: {et0:.2f} mm")


class WeatherPage(QWidget):
    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._setup_ui()

    def _setup_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(24, 20, 24, 20)
        self._layout.setSpacing(16)

        title = QLabel("\U0001f326\ufe0f Weather")
        title.setObjectName("page_title")
        self._layout.addWidget(title)

        refresh_btn = QPushButton("\U0001f504 Refresh Weather")
        refresh_btn.setObjectName("primary_btn")
        refresh_btn.setFixedWidth(180)
        refresh_btn.clicked.connect(self._refresh)
        self._layout.addWidget(refresh_btn)

        forecasts_label = QLabel("Forecast")
        forecasts_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 8px;")
        self._layout.addWidget(forecasts_label)

        self._forecast_cards_layout = QHBoxLayout()
        self._forecast_cards_layout.setSpacing(12)
        self._forecast_cards = []
        for i in range(2):
            card = ForecastCard(f"Day {i+1}")
            self._forecast_cards.append(card)
            self._forecast_cards_layout.addWidget(card)
        self._forecast_cards_layout.addStretch()
        self._layout.addLayout(self._forecast_cards_layout)

        charts_label = QLabel("Trends")
        charts_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 16px;")
        self._layout.addWidget(charts_label)

        self._chart_frame = QFrame()
        self._chart_frame.setObjectName("card")
        self._chart_frame.setMinimumHeight(200)
        chart_layout = QVBoxLayout(self._chart_frame)
        chart_layout.setContentsMargins(16, 16, 16, 16)

        self._chart_label = QLabel("Chart data will appear after weather data is loaded.")
        self._chart_label.setAlignment(Qt.AlignCenter)
        self._chart_label.setStyleSheet("color: #9E9E9E; font-size: 13px;")
        chart_layout.addWidget(self._chart_label)
        self._layout.addWidget(self._chart_frame)

        self._source_label = QLabel("")
        self._source_label.setStyleSheet("font-size: 12px; color: #9E9E9E; margin-top: 8px;")
        self._layout.addWidget(self._source_label)

        self._layout.addStretch()
        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _refresh(self):
        if self.main_window and hasattr(self.main_window, 'refresh_weather'):
            self.main_window.refresh_weather()

    def update_weather(self, weather, source="", rain48=0):
        if not weather:
            return
        days = min(len(weather.get("et0", [])), 2)
        labels = ["Today", "Tomorrow"]
        for i in range(days):
            if i < len(self._forecast_cards):
                tmin = weather["tmin"][i] if i < len(weather.get("tmin", [])) else 0
                tmax = weather["tmax"][i] if i < len(weather.get("tmax", [])) else 0
                rain = weather["rain"][i] if i < len(weather.get("rain", [])) else 0
                et0 = weather["et0"][i] if i < len(weather.get("et0", [])) else 0

                if rain > 5:
                    icon = "\u2614"
                elif rain > 0:
                    icon = "\u2601"
                elif tmax > 30:
                    icon = "\u2600"
                else:
                    icon = "\u26c5"

                self._forecast_cards[i].set_data(tmin, tmax, rain, et0, icon)

        rain48_total = sum(weather.get("rain", [])[:2])
        chart_lines = [
            f"Rain Forecast (48h): {rain48_total:.1f} mm",
            ""
        ]
        for i in range(days):
            chart_lines.append(
                f"Day {i+1}: ET\u2080={weather['et0'][i]:.2f}mm  "
                f"Rain={weather['rain'][i]:.1f}mm  "
                f"Temp={weather['tmin'][i]:.1f}\u00b0-{weather['tmax'][i]:.1f}\u00b0C"
            )
        self._chart_label.setText("\n".join(chart_lines))
        self._chart_label.setStyleSheet("font-size: 13px; font-family: monospace;")
        self._source_label.setText(f"Weather Source: {source}")
