from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QDialog, QFormLayout, QDoubleSpinBox, QMessageBox,
    QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from gui.styles import Theme
from core.database import (
    db_get_all_locations, db_add_location,
    db_update_location, db_delete_location
)


class LocationDialog(QDialog):
    def __init__(self, parent=None, location=None):
        super().__init__(parent)
        self.location = location
        self.setWindowTitle("Edit Location" if location else "Add Location")
        self.setFixedSize(400, 260)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {Theme.c('bg_card')}; }}
            QLabel {{ font-size: 13px; }}
            QDoubleSpinBox {{ padding: 6px; }}
            QPushButton {{ padding: 8px 16px; font-weight: bold; border-radius: 6px; }}
        """)

        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        self.name_edit = QLineEdit()
        self.lat_spin = QDoubleSpinBox()
        self.lat_spin.setRange(-90, 90)
        self.lat_spin.setDecimals(6)
        self.lon_spin = QDoubleSpinBox()
        self.lon_spin.setRange(-180, 180)
        self.lon_spin.setDecimals(6)

        if location:
            self.name_edit.setText(location[1])
            self.lat_spin.setValue(location[2])
            self.lon_spin.setValue(location[3])

        layout.addRow("Location Name:", self.name_edit)
        layout.addRow("Latitude:", self.lat_spin)
        layout.addRow("Longitude:", self.lon_spin)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(f"background-color: {Theme.c('border')}; color: {Theme.c('text')};")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(f"background-color: {Theme.c('primary')}; color: white;")
        save_btn.clicked.connect(self._save)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addRow(btn_layout)

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Error", "Location name cannot be empty.")
            return
        self.result_data = (name, self.lat_spin.value(), self.lon_spin.value())
        self.accept()


class LocationsPage(QWidget):
    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        if main_window and getattr(main_window, "_location", None):
            loc = main_window._location
            self._active_location = (None, loc["name"], loc["lat"], loc["lon"])
        else:
            self._active_location = None
        self._setup_ui()
        self.refresh_data()
        if self._active_location:
            loc = self._active_location
            self._active_label.setText(
                f"Active Location: {loc[1]} ({loc[2]:.4f}, {loc[3]:.4f})"
            )

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("\U0001f4cd Locations")
        title.setObjectName("page_title")
        layout.addWidget(title)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        add_btn = QPushButton("\u2795 Add Location")
        add_btn.setObjectName("primary_btn")
        add_btn.clicked.connect(self._add)
        toolbar.addWidget(add_btn)

        edit_btn = QPushButton("\u270f\ufe0f Edit")
        edit_btn.setObjectName("outline_btn")
        edit_btn.clicked.connect(self._edit)
        toolbar.addWidget(edit_btn)

        delete_btn = QPushButton("\U0001f5d1\ufe0f Delete")
        delete_btn.setObjectName("danger_btn")
        delete_btn.clicked.connect(self._delete)
        toolbar.addWidget(delete_btn)

        select_btn = QPushButton("\u2705 Select Active")
        select_btn.setObjectName("success_btn")
        select_btn.clicked.connect(self._select_active)
        toolbar.addWidget(select_btn)

        refresh_btn = QPushButton("\U0001f504 Refresh")
        refresh_btn.setObjectName("outline_btn")
        refresh_btn.clicked.connect(self.refresh_data)
        toolbar.addWidget(refresh_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Latitude", "Longitude", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        layout.addWidget(self.table)

        self._active_label = QLabel("Active Location: None")
        self._active_label.setStyleSheet("font-size: 13px; color: #757575; padding: 4px;")
        layout.addWidget(self._active_label)

    def refresh_data(self):
        self._all_locations = db_get_all_locations()
        self._populate_table()

    def _populate_table(self):
        self.table.setRowCount(len(self._all_locations))
        for i, loc in enumerate(self._all_locations):
            name_item = QTableWidgetItem(loc[1])
            name_item.setFont(QFont("Segoe UI", 12))
            self.table.setItem(i, 0, name_item)

            lat_item = QTableWidgetItem(f"{loc[2]:.6f}")
            lat_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, lat_item)

            lon_item = QTableWidgetItem(f"{loc[3]:.6f}")
            lon_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, lon_item)

            status = "\u2705 Active" if self._active_location and self._active_location[1] == loc[1] else ""
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, status_item)

    def _get_selected(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Info", "Please select a location.")
            return None
        name = self.table.item(row, 0).text()
        for loc in self._all_locations:
            if loc[1] == name:
                return loc
        return None

    def _add(self):
        dlg = LocationDialog(self)
        if dlg.exec() == QDialog.Accepted:
            name, lat, lon = dlg.result_data
            if db_add_location(name, lat, lon):
                if self.main_window and hasattr(self.main_window, 'show_toast'):
                    self.main_window.show_toast(f"Location '{name}' added")
                self.refresh_data()
            else:
                QMessageBox.warning(self, "Error", f"Location '{name}' already exists.")

    def _edit(self):
        loc = self._get_selected()
        if not loc:
            return
        if (
            self.main_window
            and self.main_window.configuration_locked()
            and self._active_location
            and self._active_location[1] == loc[1]
        ):
            QMessageBox.warning(self, "Analysis Running", "Stop the analysis before editing the active location.")
            return
        dlg = LocationDialog(self, loc)
        if dlg.exec() == QDialog.Accepted:
            name, lat, lon = dlg.result_data
            if not db_update_location(loc[1], name, lat, lon):
                QMessageBox.warning(self, "Error", "The location could not be updated.")
                return
            if self._active_location and self._active_location[1] == loc[1]:
                self._active_location = (loc[0], name, lat, lon)
                if self.main_window:
                    self.main_window.set_active_location(self._active_location)
                from core.database import db_save_setting
                db_save_setting("active_location", name)
            self.refresh_data()

    def _delete(self):
        loc = self._get_selected()
        if not loc:
            return
        if self._active_location and self._active_location[1] == loc[1]:
            QMessageBox.warning(self, "Error", "Select another active location before deletion.")
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete location '{loc[1]}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if not db_delete_location(loc[1]):
                QMessageBox.warning(self, "Error", "The location could not be deleted.")
                return
            if self.main_window and hasattr(self.main_window, 'show_toast'):
                self.main_window.show_toast(f"Location '{loc[1]}' deleted")
            self.refresh_data()

    def _select_active(self):
        if self.main_window and self.main_window.configuration_locked():
            QMessageBox.warning(self, "Analysis Running", "Stop the analysis before selecting a location.")
            return
        loc = self._get_selected()
        if not loc:
            return
        self._active_location = loc
        self._active_label.setText(f"Active Location: {loc[1]} ({loc[2]:.4f}, {loc[3]:.4f})")
        if self.main_window and hasattr(self.main_window, 'set_active_location'):
            self.main_window.set_active_location(loc)
        from core.database import db_save_setting
        db_save_setting("active_location", loc[1])
        self._populate_table()
        if self.main_window and hasattr(self.main_window, 'show_toast'):
            self.main_window.show_toast(f"Location '{loc[1]}' selected")

    def get_active_location(self):
        return self._active_location

    def sync_active_location(self, loc):
        self._active_location = loc
        if hasattr(self, "_active_label"):
            self._active_label.setText(
                f"Active Location: {loc[1]} ({loc[2]:.4f}, {loc[3]:.4f})"
            )
        if hasattr(self, "table"):
            self._populate_table()
