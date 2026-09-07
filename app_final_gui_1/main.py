#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from core.database import init_database
from gui.styles import apply_theme


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Smart Irrigation System")
    app.setOrganizationName("AgriTech")

    try:
        init_database()
    except Exception as e:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "Database Error", f"Database initialization failed: {e}")
        return 1

    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    from core.database import db_load_setting
    dark = db_load_setting("dark_mode", False)
    apply_theme(app, dark=dark)

    from gui.main_window import MainWindow
    window = MainWindow()

    from core.sensor import on_connection_change
    on_connection_change(window.set_serial_connected)

    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
