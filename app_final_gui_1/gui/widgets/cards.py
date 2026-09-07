from PySide6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont


class StatusCard(QFrame):
    def __init__(self, title="", value="", icon="", color="#2E7D32", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumHeight(100)
        self.setMaximumHeight(130)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        top = QHBoxLayout()
        if icon:
            icon_lbl = QLabel(icon)
            icon_lbl.setFont(QFont("Segoe UI Emoji", 18))
            icon_lbl.setFixedWidth(32)
            top.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("card_title")
        top.addWidget(title_lbl)
        top.addStretch()
        layout.addLayout(top)

        val_lbl = QLabel(value)
        val_lbl.setObjectName("card_value")
        val_lbl.setStyleSheet(f"color: {color};")
        layout.addWidget(val_lbl)

        self._title_label = title_lbl
        self._value_label = val_lbl

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 25))
        self.setGraphicsEffect(shadow)

    def set_value(self, value, color=None):
        self._value_label.setText(str(value))
        if color:
            self._value_label.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold;")

    def set_title(self, title):
        self._title_label.setText(title)


class InfoRow(QHBoxLayout):
    def __init__(self, label_text, value_text, parent=None):
        super().__init__()
        self.setSpacing(8)
        self.setContentsMargins(0, 2, 0, 2)

        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #9E9E9E; font-size: 12px;")
        self.addWidget(lbl)

        self.val = QLabel(value_text)
        self.val.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.addStretch()
        self.addWidget(self.val)

    def set_value(self, text):
        self.val.setText(str(text))


class PumpStatusCard(QFrame):
    def __init__(self, pump_number=1, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumHeight(120)
        self.setMaximumHeight(160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        header = QHBoxLayout()
        self._number_label = QLabel(f"Pump {pump_number}")
        self._number_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        header.addWidget(self._number_label)

        self._status_badge = QLabel("OFF")
        self._status_badge.setAlignment(Qt.AlignCenter)
        self._status_badge.setFixedSize(50, 22)
        header.addStretch()
        header.addWidget(self._status_badge)
        layout.addLayout(header)

        self._flow_label = QLabel("Flow: 0.0 L/min")
        self._flow_label.setStyleSheet("font-size: 12px; color: #757575;")
        layout.addWidget(self._flow_label)

        self._time_label = QLabel("Time: 0:00")
        self._time_label.setStyleSheet("font-size: 12px; color: #757575;")
        layout.addWidget(self._time_label)

        self._anim_label = QLabel("\u25cb")
        self._anim_label.setAlignment(Qt.AlignCenter)
        self._anim_label.setStyleSheet("font-size: 24px; color: #E0E0E0;")
        layout.addWidget(self._anim_label)

        self._set_badge_style(False)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(16)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 20))
        self.setGraphicsEffect(shadow)

    def _set_badge_style(self, on):
        if on:
            self._status_badge.setText("ON")
            self._status_badge.setStyleSheet(
                "background-color: #4CAF50; color: white; border-radius: 4px; font-size: 11px; font-weight: bold;"
            )
            self._anim_label.setStyleSheet("font-size: 28px; color: #2196F3;")
        else:
            self._status_badge.setText("OFF")
            self._status_badge.setStyleSheet(
                "background-color: #9E9E9E; color: white; border-radius: 4px; font-size: 11px; font-weight: bold;"
            )
            self._anim_label.setStyleSheet("font-size: 28px; color: #E0E0E0;")

    def set_state(self, on, flow_rate=0, remaining_time="0:00"):
        self._set_badge_style(on)
        if on:
            self._flow_label.setText(f"Flow: {flow_rate:.1f} L/min")
            self._time_label.setText(f"Time: {remaining_time}")
            self._anim_label.setText("\u2756")
        else:
            self._flow_label.setText(f"Flow: {flow_rate:.1f} L/min")
            self._time_label.setText(f"Time: {remaining_time}")
            self._anim_label.setText("\u25cb")


class DecisionCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumHeight(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        title = QLabel("Irrigation Decision")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        self._plant_row = InfoRow("Plant:", "-")
        self._kc_row = InfoRow("Kc:", "-")
        self._area_row = InfoRow("Area:", "-")
        self._water_today_row = InfoRow("Water Required:", "-")
        self._water_final_row = InfoRow("Final Volume:", "-")

        for row in [self._plant_row, self._kc_row, self._area_row, self._water_today_row, self._water_final_row]:
            layout.addLayout(row)

        layout.addSpacing(4)
        self._note_label = QLabel("-")
        self._note_label.setWordWrap(True)
        self._note_label.setStyleSheet("font-size: 13px; padding: 8px; border-radius: 6px; background-color: #F5F7FA;")
        layout.addWidget(self._note_label)

        layout.addStretch()

        self._badge = QLabel("")
        self._badge.setAlignment(Qt.AlignCenter)
        self._badge.setFixedHeight(28)
        self._badge.setStyleSheet("font-size: 12px; font-weight: bold; border-radius: 4px; color: white;")
        layout.addWidget(self._badge)

    def set_decision(self, plant_name, kc, area, water_today, water_final, note):
        self._plant_row.set_value(plant_name)
        self._kc_row.set_value(f"{kc:.2f}")
        self._area_row.set_value(f"{area:.5f} m\u00b2")
        self._water_today_row.set_value(f"{water_today:.1f} L")
        self._water_final_row.set_value(f"{water_final:.1f} L")
        self._note_label.setText(note)

        note_lower = note.lower()
        if "no irrigation" in note_lower:
            color = "#4CAF50"
            badge_text = "No Irrigation Needed"
        elif "monitoring" in note_lower:
            color = "#FB8C00"
            badge_text = "Monitoring"
        elif "normal" in note_lower:
            color = "#1976D2"
            badge_text = "Normal Irrigation"
        elif "reduced" in note_lower:
            color = "#26C6DA"
            badge_text = "Irrigation Reduced"
        elif "canceled" in note_lower:
            color = "#D32F2F"
            badge_text = "Irrigation Canceled"
        else:
            color = "#757575"
            badge_text = "Unknown"

        self._badge.setText(badge_text)
        self._badge.setStyleSheet(
            f"background-color: {color}; color: white; font-size: 12px; font-weight: bold; "
            f"border-radius: 4px; padding: 4px;"
        )


class WeatherCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumHeight(180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        title = QLabel("Weather Overview")
        title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(title)

        self._et0_row = InfoRow("Today ET\u2080:", "-")
        self._rain_row = InfoRow("Today Rain:", "-")
        self._rain48_row = InfoRow("Rain Forecast (48h):", "-")
        self._tmin_row = InfoRow("Min Temp:", "-")
        self._tmax_row = InfoRow("Max Temp:", "-")
        self._source_row = InfoRow("Source:", "-")

        for row in [self._et0_row, self._rain_row, self._rain48_row, self._tmin_row, self._tmax_row, self._source_row]:
            layout.addLayout(row)

        layout.addStretch()

    def set_weather(self, et0, rain, rain48, tmin, tmax, source, icon=""):
        self._et0_row.set_value(f"{et0:.2f} mm/day")
        self._rain_row.set_value(f"{rain:.1f} mm")
        self._rain48_row.set_value(f"{rain48:.1f} mm")
        self._tmin_row.set_value(f"{tmin:.1f}\u00b0C")
        self._tmax_row.set_value(f"{tmax:.1f}\u00b0C")
        self._source_row.set_value(f"{icon} {source}")
