from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame
)
from PySide6.QtCore import Qt, QTimer

from gui.styles import Theme
from gui.widgets.cards import StatusCard, DecisionCard, WeatherCard, PumpStatusCard
from gui.widgets.circular_gauge import CircularGauge


class DashboardPage(QWidget):
    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._plant_L = 45
        self._plant_U = 70
        self._setup_ui()
        self._start_live_update()

    def _setup_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        self._page_layout = QVBoxLayout(container)
        self._page_layout.setContentsMargins(24, 20, 24, 20)
        self._page_layout.setSpacing(16)

        title = QLabel("\U0001f3e1 Dashboard")
        title.setObjectName("page_title")
        self._page_layout.addWidget(title)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.card_plant = StatusCard("Selected Plant", "Not Set", "\U0001f331", Theme.c("primary"))
        self.card_location = StatusCard("Current Location", "Not Set", "\U0001f4cd", Theme.c("secondary"))
        self.card_area = StatusCard("Land Area", "0 m\u00b2", "\U0001f33e", Theme.c("accent"))
        self.card_weather = StatusCard("Weather Source", "None", "\U0001f326", Theme.c("warning"))
        self.card_status = StatusCard("System Status", "Idle", "\u2699\ufe0f", Theme.c("text_secondary"))

        for card in [self.card_plant, self.card_location, self.card_area, self.card_weather, self.card_status]:
            cards_layout.addWidget(card)
        self._page_layout.addLayout(cards_layout)

        soil_section = QLabel("Soil Moisture")
        soil_section.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 8px;")
        self._page_layout.addWidget(soil_section)

        gauges_layout = QHBoxLayout()
        gauges_layout.setSpacing(20)
        gauges_layout.setAlignment(Qt.AlignCenter)

        self.gauges = []
        for i in range(4):
            gauge = CircularGauge(f"Sensor {i+1}")
            self.gauges.append(gauge)
            gauges_layout.addWidget(gauge)

        self._page_layout.addLayout(gauges_layout)

        info_row = QHBoxLayout()
        info_row.setSpacing(16)

        self.median_card = QFrame()
        self.median_card.setObjectName("card")
        median_layout = QVBoxLayout(self.median_card)
        median_layout.setContentsMargins(16, 12, 16, 12)
        ml = QLabel("Median Moisture")
        ml.setStyleSheet("color: #9E9E9E; font-size: 12px;")
        median_layout.addWidget(ml)
        self.median_val = QLabel("---")
        self.median_val.setStyleSheet("font-size: 22px; font-weight: bold; color: #9E9E9E;")
        median_layout.addWidget(self.median_val)
        info_row.addWidget(self.median_card)

        thresh_card = QFrame()
        thresh_card.setObjectName("card")
        thresh_layout = QVBoxLayout(thresh_card)
        thresh_layout.setContentsMargins(16, 12, 16, 12)
        tl = QLabel("Thresholds (L / U)")
        tl.setStyleSheet("color: #9E9E9E; font-size: 12px;")
        thresh_layout.addWidget(tl)
        self.thresh_val = QLabel("45 / 70")
        self.thresh_val.setStyleSheet("font-size: 22px; font-weight: bold; color: #FB8C00;")
        thresh_layout.addWidget(self.thresh_val)
        info_row.addWidget(thresh_card)

        info_row.addStretch()
        self._page_layout.addLayout(info_row)

        lower_row = QHBoxLayout()
        lower_row.setSpacing(16)

        self.weather_card_widget = WeatherCard()
        lower_row.addWidget(self.weather_card_widget)

        self.decision_card_widget = DecisionCard()
        lower_row.addWidget(self.decision_card_widget)

        self._page_layout.addLayout(lower_row)

        pump_section = QLabel("Pump Status")
        pump_section.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 8px;")
        self._page_layout.addWidget(pump_section)

        pumps_layout = QHBoxLayout()
        pumps_layout.setSpacing(12)
        self.pump_cards = []
        for i in range(4):
            pc = PumpStatusCard(i + 1)
            self.pump_cards.append(pc)
            pumps_layout.addWidget(pc)
        self._page_layout.addLayout(pumps_layout)

        self._page_layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _start_live_update(self):
        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._poll_sensor_data)
        self._live_timer.start(500)

    def _poll_sensor_data(self):
        try:
            from core.sensor import get_latest_soil_age, get_latest_soil_data
            data = get_latest_soil_data()
            age = get_latest_soil_age()
            if data is not None and age is not None and age <= 10.0:
                s1, s2, s3, s4, median = data
                values = [s1, s2, s3, s4]
                for i, g in enumerate(self.gauges):
                    color = Theme.gauge_color(values[i], self._plant_L, self._plant_U)
                    g.set_value(values[i], color)
                self.median_val.setText(f"{median:.1f}%")
                m_color = Theme.gauge_color_by_moisture(median)
                self.median_val.setStyleSheet(
                    f"font-size: 22px; font-weight: bold; color: {m_color};"
                )
            else:
                for gauge in self.gauges:
                    gauge.clear_data()
                self.median_val.setText("---")
        except Exception:
            pass

    def update_sensor_data(self, s1, s2, s3, s4, median):
        values = [s1, s2, s3, s4]
        for i, g in enumerate(self.gauges):
            color = Theme.gauge_color(values[i], self._plant_L, self._plant_U)
            g.set_value(values[i], color)
        self.median_val.setText(f"{median:.1f}%")
        m_color = Theme.gauge_color_by_moisture(median)
        self.median_val.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {m_color};"
        )

    def update_plant(self, name):
        self.card_plant.set_value(name, Theme.c("primary"))

    def update_location(self, name):
        self.card_location.set_value(name, Theme.c("secondary"))

    def update_area(self, area):
        self.card_area.set_value(f"{area:.5f} m\u00b2", Theme.c("accent"))

    def update_weather_source(self, source):
        self.card_weather.set_value(source, Theme.c("warning"))

    def update_system_status(self, status):
        colors = {
            "Idle": Theme.c("text_secondary"),
            "Collecting": Theme.c("warning"),
            "Analyzing": Theme.c("secondary"),
            "Irrigating": Theme.c("primary"),
            "Stopped": Theme.c("danger"),
            "Error": Theme.c("danger"),
        }
        self.card_status.set_value(status, colors.get(status, Theme.c("text_secondary")))

    def update_thresholds(self, low, high):
        self._plant_L = low
        self._plant_U = high
        self.thresh_val.setText(f"{low} / {high}")

    def update_weather(self, et0, rain, rain48, tmin, tmax, source):
        icon = "\u2614" if rain > 5 else ("\u2601" if rain > 0 else "\u2600")
        self.weather_card_widget.set_weather(et0, rain, rain48, tmin, tmax, source, icon)

    def update_decision(self, plant_name, kc, area, water_today, water_final, note):
        self.decision_card_widget.set_decision(plant_name, kc, area, water_today, water_final, note)

    def update_pump(self, index, on, flow_rate, remaining_time):
        if 0 <= index < len(self.pump_cards):
            self.pump_cards[index].set_state(on, flow_rate, remaining_time)
