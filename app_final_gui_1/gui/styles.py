from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

COLORS = {
    "primary": "#2E7D32",
    "primary_light": "#4CAF50",
    "primary_dark": "#1B5E20",
    "secondary": "#1976D2",
    "secondary_light": "#42A5F5",
    "accent": "#26C6DA",
    "warning": "#FB8C00",
    "danger": "#D32F2F",
    "success": "#4CAF50",
    "bg": "#F5F7FA",
    "bg_card": "#FFFFFF",
    "bg_sidebar": "#1A1A2E",
    "bg_sidebar_hover": "#16213E",
    "bg_sidebar_active": "#0F3460",
    "text": "#333333",
    "text_secondary": "#757575",
    "text_light": "#B0BEC5",
    "text_sidebar": "#E0E0E0",
    "text_sidebar_active": "#FFFFFF",
    "border": "#E0E0E0",
    "border_light": "#F0F0F0",
    "shadow": "rgba(0,0,0,0.08)",
    "gauge_green": "#4CAF50",
    "gauge_orange": "#FB8C00",
    "gauge_red": "#D32F2F",
    "gauge_bg": "#E8E8E8",
    "gauge_track": "#F0F0F0",
}

DARK_COLORS = {
    **COLORS,
    "bg": "#121212",
    "bg_card": "#1E1E1E",
    "bg_sidebar": "#0A0A1A",
    "bg_sidebar_hover": "#1A1A3E",
    "bg_sidebar_active": "#0F3460",
    "text": "#E0E0E0",
    "text_secondary": "#9E9E9E",
    "border": "#333333",
    "border_light": "#2A2A2A",
    "shadow": "rgba(0,0,0,0.3)",
    "gauge_bg": "#333333",
    "gauge_track": "#2A2A2A",
}


class Theme:
    _dark = False

    @classmethod
    def is_dark(cls):
        return cls._dark

    @classmethod
    def set_dark(cls, dark):
        cls._dark = dark

    @classmethod
    def c(cls, key):
        if cls._dark:
            return DARK_COLORS.get(key, COLORS.get(key, "#000000"))
        return COLORS.get(key, "#000000")

    @classmethod
    def gauge_color(cls, value, low, high):
        if value < low:
            return cls.c("gauge_red")
        elif value > high:
            return cls.c("gauge_green")
        else:
            mid = (low + high) / 2
            if value < mid:
                return cls.c("gauge_orange")
            return cls.c("gauge_green")

    @classmethod
    def gauge_color_by_moisture(cls, value):
        if value < 30:
            return cls.c("gauge_red")
        elif value < 50:
            return cls.c("gauge_orange")
        else:
            return cls.c("gauge_green")

    @classmethod
    def get_stylesheet(cls):
        bg = cls.c("bg")
        card = cls.c("bg_card")
        text = cls.c("text")
        text2 = cls.c("text_secondary")
        border = cls.c("border")
        primary = cls.c("primary")
        sidebar_bg = cls.c("bg_sidebar")
        sidebar_hover = cls.c("bg_sidebar_hover")
        sidebar_active = cls.c("bg_sidebar_active")
        text_sidebar = cls.c("text_sidebar")
        text_sidebar_active = cls.c("text_sidebar_active")

        return f"""
        * {{
            font-family: 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
        }}
        QMainWindow {{
            background-color: {bg};
        }}
        QWidget {{
            color: {text};
            background-color: transparent;
        }}
        QStackedWidget {{
            background-color: {bg};
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {border};
            min-height: 30px;
            border-radius: 4px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 8px;
        }}
        QScrollBar::handle:horizontal {{
            background: {border};
            min-width: 30px;
            border-radius: 4px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}
        QTableWidget {{
            background-color: {card};
            border: 1px solid {border};
            border-radius: 8px;
            gridline-color: {cls.c("border_light")};
            selection-background-color: {primary}22;
            selection-color: {text};
        }}
        QTableWidget::item {{
            padding: 8px 12px;
            border-bottom: 1px solid {cls.c("border_light")};
        }}
        QTableWidget::item:selected {{
            background-color: {primary}22;
        }}
        QTableWidget::item:hover {{
            background-color: {cls.c("bg")}88;
        }}
        QHeaderView::section {{
            background-color: {card};
            color: {text2};
            padding: 10px 12px;
            border: none;
            border-bottom: 2px solid {border};
            font-weight: bold;
            font-size: 12px;
            text-transform: uppercase;
        }}
        QPushButton {{
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: 600;
            font-size: 13px;
        }}
        QPushButton:hover {{
            opacity: 0.85;
        }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            border: 1px solid {border};
            border-radius: 6px;
            padding: 8px 12px;
            background-color: {card};
            color: {text};
            font-size: 13px;
            selection-background-color: {primary};
        }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
            border-color: {primary};
        }}
        QComboBox::drop-down {{
            border: none;
            padding-right: 8px;
        }}
        QLabel {{
            color: {text};
        }}
        QToolTip {{
            background-color: {cls.c("bg_sidebar")};
            color: {text_sidebar_active};
            border: none;
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 12px;
        }}
        QFrame#sidebar {{
            background-color: {sidebar_bg};
        }}
        QPushButton#sidebar_btn {{
            background-color: transparent;
            color: {text_sidebar};
            text-align: left;
            padding: 12px 16px;
            border-radius: 0px;
            border-left: 3px solid transparent;
            font-size: 13px;
        }}
        QPushButton#sidebar_btn:hover {{
            background-color: {sidebar_hover};
        }}
        QPushButton#sidebar_btn[active="true"] {{
            background-color: {sidebar_active};
            color: {text_sidebar_active};
            border-left: 3px solid {cls.c("accent")};
            font-weight: bold;
        }}
        QPushButton#primary_btn {{
            background-color: {primary};
            color: white;
        }}
        QPushButton#primary_btn:hover {{
            background-color: {cls.c("primary_light")};
        }}
        QPushButton#danger_btn {{
            background-color: {cls.c("danger")};
            color: white;
        }}
        QPushButton#warning_btn {{
            background-color: {cls.c("warning")};
            color: white;
        }}
        QPushButton#accent_btn {{
            background-color: {cls.c("accent")};
            color: white;
        }}
        QPushButton#success_btn {{
            background-color: {cls.c("success")};
            color: white;
        }}
        QPushButton#outline_btn {{
            background-color: transparent;
            border: 1px solid {border};
            color: {text};
        }}
        QPushButton#outline_btn:hover {{
            background-color: {cls.c("bg")};
        }}
        QFrame#card {{
            background-color: {card};
            border: 1px solid {cls.c("border_light")};
            border-radius: 12px;
        }}
        QLabel#card_title {{
            color: {text2};
            font-size: 12px;
            font-weight: 600;
        }}
        QLabel#card_value {{
            color: {text};
            font-size: 20px;
            font-weight: bold;
        }}
        QLabel#page_title {{
            color: {text};
            font-size: 24px;
            font-weight: bold;
        }}
        QLabel#sidebar_title {{
            color: {cls.c("accent")};
            font-size: 16px;
            font-weight: bold;
        }}
        QLabel#footer_label {{
            color: {text2};
            font-size: 11px;
        }}
        QProgressBar {{
            border: none;
            border-radius: 4px;
            background-color: {cls.c("gauge_track")};
            text-align: center;
            color: {text};
            font-size: 11px;
            min-height: 8px;
            max-height: 8px;
        }}
        QProgressBar::chunk {{
            border-radius: 4px;
            background-color: {primary};
        }}
        QLineEdit#search_input {{
            padding-left: 32px;
            border: 1px solid {border};
            border-radius: 20px;
            background-color: {card};
        }}
        """


def apply_theme(app, dark=False):
    Theme.set_dark(dark)
    app.setStyleSheet(Theme.get_stylesheet())
    palette = QPalette()
    if dark:
        palette.setColor(QPalette.Window, QColor(DARK_COLORS["bg"]))
        palette.setColor(QPalette.WindowText, QColor(DARK_COLORS["text"]))
        palette.setColor(QPalette.Base, QColor(DARK_COLORS["bg_card"]))
        palette.setColor(QPalette.AlternateBase, QColor(DARK_COLORS["bg"]))
        palette.setColor(QPalette.Text, QColor(DARK_COLORS["text"]))
        palette.setColor(QPalette.Button, QColor(DARK_COLORS["bg_card"]))
        palette.setColor(QPalette.ButtonText, QColor(DARK_COLORS["text"]))
        palette.setColor(QPalette.Highlight, QColor(COLORS["primary"]))
        palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    else:
        palette.setColor(QPalette.Window, QColor(COLORS["bg"]))
        palette.setColor(QPalette.WindowText, QColor(COLORS["text"]))
        palette.setColor(QPalette.Base, QColor("#FFFFFF"))
        palette.setColor(QPalette.AlternateBase, QColor(COLORS["bg"]))
        palette.setColor(QPalette.Text, QColor(COLORS["text"]))
        palette.setColor(QPalette.Button, QColor("#FFFFFF"))
        palette.setColor(QPalette.ButtonText, QColor(COLORS["text"]))
        palette.setColor(QPalette.Highlight, QColor(COLORS["primary"]))
        palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)
