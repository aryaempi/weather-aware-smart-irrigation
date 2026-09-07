from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QBrush, QConicalGradient, QRadialGradient


class CircularGauge(QWidget):
    def __init__(self, label="Sensor", parent=None):
        super().__init__(parent)
        self._value = 0
        self._has_data = False
        self._min_val = 0
        self._max_val = 100
        self._label = label
        self._color = QColor("#4CAF50")
        self._bg_color = QColor("#E0E0E0")
        self._text_color = QColor("#333333")
        self.setMinimumSize(140, 140)
        self.setMaximumSize(200, 200)

    def set_value(self, value, color=None):
        self._value = max(self._min_val, min(self._max_val, value))
        self._has_data = True
        if color:
            self._color = QColor(color)
        self.update()

    def clear_data(self):
        self._has_data = False
        self._value = 0
        self.update()

    def set_label(self, label):
        self._label = label
        self.update()

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        side = min(w, h)
        pen_width = side * 0.07
        margin = side * 0.05

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(margin, margin, side - 2 * margin, side - 2 * margin)
        center = rect.center()
        radius = rect.width() / 2 - pen_width / 2

        bg_pen = QPen(self._bg_color, pen_width, Qt.SolidLine, Qt.RoundCap)
        p.setPen(bg_pen)
        p.drawArc(rect, 225 * 16, -270 * 16)

        if self._has_data:
            span = (self._value - self._min_val) / (self._max_val - self._min_val)
            angle = int(-270 * span * 16)

            grad = QConicalGradient(center, 135)
            grad.setColorAt(0.0, self._color)
            grad.setColorAt(1.0, self._color.lighter(130))
            val_pen = QPen(QBrush(grad), pen_width, Qt.SolidLine, Qt.RoundCap)
            p.setPen(val_pen)
            p.drawArc(rect, 225 * 16, angle)

        p.setPen(Qt.NoPen)
        inner_rect = QRectF(
            center.x() - radius * 0.62,
            center.y() - radius * 0.62,
            radius * 1.24,
            radius * 1.24,
        )
        gradient = QRadialGradient(center, radius * 0.62)
        gradient.setColorAt(0, QColor(255, 255, 255, 30))
        gradient.setColorAt(1, QColor(0, 0, 0, 10))
        p.setBrush(gradient)
        p.drawEllipse(inner_rect)

        if self._has_data:
            p.setPen(self._text_color)
            val_font = QFont("Segoe UI", int(side * 0.15), QFont.Bold)
            p.setFont(val_font)
            p.drawText(
                QRectF(rect.left(), center.y() - side * 0.1, rect.width(), side * 0.18),
                Qt.AlignCenter, f"{self._value:.0f}%"
            )
        else:
            p.setPen(QColor("#BDBDBD"))
            no_data_font = QFont("Segoe UI", int(side * 0.10))
            p.setFont(no_data_font)
            p.drawText(
                QRectF(rect.left(), center.y() - side * 0.08, rect.width(), side * 0.16),
                Qt.AlignCenter, "---"
            )

        pct_font = QFont("Segoe UI", int(side * 0.07))
        p.setFont(pct_font)
        p.setPen(QColor("#9E9E9E"))
        p.drawText(
            QRectF(rect.left(), center.y() + side * 0.06, rect.width(), side * 0.1),
            Qt.AlignCenter, self._label
        )

        p.end()
