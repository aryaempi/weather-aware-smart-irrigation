from PySide6.QtWidgets import QLabel, QHBoxLayout, QGraphicsDropShadowEffect, QWidget
from PySide6.QtCore import Qt, QPropertyAnimation, QTimer, QEasingCurve, QPoint
from PySide6.QtGui import QColor


class ToastNotification(QWidget):
    _instance = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(320)
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._container = QLabel("")
        self._container.setWordWrap(True)
        self._container.setAlignment(Qt.AlignCenter)
        self._container.setStyleSheet(
            "background-color: #333333; color: white; border-radius: 10px; "
            "padding: 12px 16px; font-size: 13px;"
        )
        layout.addWidget(self._container)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 80))
        self._container.setGraphicsEffect(shadow)

        self._animation = QPropertyAnimation(self, b"pos")
        self._animation.setDuration(300)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._fade_out)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_toast(self, message, duration=3000):
        colors = {
            "success": "#2E7D32",
            "info": "#1976D2",
            "warning": "#FB8C00",
            "danger": "#D32F2F",
            "default": "#333333",
        }
        color = colors.get("default")
        for key in colors:
            if key in message.lower():
                color = colors[key]
                break

        self._container.setStyleSheet(
            f"background-color: {color}; color: white; border-radius: 10px; "
            f"padding: 12px 16px; font-size: 13px;"
        )
        self._container.setText(message)
        self.adjustSize()

        if self.parent():
            pw = self.parent().width()
            self.move(pw - self.width() - 20, -self.height())

        self.show()
        self.raise_()

        self._animation.setStartValue(self.pos())
        self._animation.setEndValue(QPoint(self.x(), 20))
        self._animation.start()

        self._fade_timer.start(duration)
        self._hide_timer.start(duration + 400)

    def _fade_out(self):
        self._animation.setStartValue(self.pos())
        self._animation.setEndValue(QPoint(self.x(), -self.height()))
        self._animation.start()
