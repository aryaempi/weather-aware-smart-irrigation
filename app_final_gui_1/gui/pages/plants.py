from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QDialog, QFormLayout, QDoubleSpinBox, QMessageBox,
    QFrame, QGraphicsDropShadowEffect, QScrollArea
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont

from gui.styles import Theme
from core.database import db_get_all_plants, db_add_plant, db_update_plant, db_delete_plant


class PlantDialog(QDialog):
    def __init__(self, parent=None, plant=None):
        super().__init__(parent)
        self.plant = plant
        self.setWindowTitle("Edit Plant" if plant else "Add Plant")
        self.setFixedSize(400, 300)
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
        self.kc_spin = QDoubleSpinBox()
        self.kc_spin.setRange(0.1, 2.0)
        self.kc_spin.setSingleStep(0.05)
        self.kc_spin.setDecimals(2)
        self.l_spin = QDoubleSpinBox()
        self.l_spin.setRange(0, 100)
        self.u_spin = QDoubleSpinBox()
        self.u_spin.setRange(0, 100)

        if plant:
            self.name_edit.setText(plant[1])
            self.name_edit.setReadOnly(True)
            self.kc_spin.setValue(plant[2])
            self.l_spin.setValue(plant[3])
            self.u_spin.setValue(plant[4])

        layout.addRow("Plant Name:", self.name_edit)
        layout.addRow("Crop Coefficient (Kc):", self.kc_spin)
        layout.addRow("Lower Threshold (L):", self.l_spin)
        layout.addRow("Upper Threshold (U):", self.u_spin)

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
            QMessageBox.warning(self, "Error", "Plant name cannot be empty.")
            return
        kc = self.kc_spin.value()
        l_val = self.l_spin.value()
        u_val = self.u_spin.value()
        if u_val <= l_val:
            QMessageBox.warning(self, "Error", "Upper threshold must be greater than lower threshold.")
            return
        self.result_data = (name, kc, l_val, u_val)
        self.accept()


class PlantsPage(QWidget):
    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._setup_ui()
        self.refresh_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("\U0001f331 Plants")
        title.setObjectName("page_title")
        layout.addWidget(title)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("\U0001f50d Search plants...")
        self.search.setObjectName("search_input")
        self.search.setFixedWidth(280)
        self.search.textChanged.connect(self._filter)
        toolbar.addWidget(self.search)

        toolbar.addStretch()

        select_btn = QPushButton("\u2705 Select Plant")
        select_btn.setObjectName("success_btn")
        select_btn.clicked.connect(self._select_plant)
        toolbar.addWidget(select_btn)

        add_btn = QPushButton("\u2795 Add Plant")
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

        refresh_btn = QPushButton("\U0001f504 Refresh")
        refresh_btn.setObjectName("outline_btn")
        refresh_btn.clicked.connect(self.refresh_data)
        toolbar.addWidget(refresh_btn)

        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Kc", "Lower Threshold", "Upper Threshold"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self._select_plant)
        layout.addWidget(self.table)

        self._active_label = QLabel("Active Plant: Wheat")
        self._active_label.setStyleSheet("font-size: 13px; color: #4CAF50; padding: 4px; font-weight: bold;")
        layout.addWidget(self._active_label)

    def refresh_data(self):
        self._all_plants = db_get_all_plants()
        self._populate_table(self._all_plants)
        self._update_active_label()

    def _update_active_label(self):
        if self.main_window and hasattr(self.main_window, '_plant'):
            name = self.main_window._plant.get("name", "Not Set")
            self._active_label.setText(f"Active Plant: {name}")

    def _select_plant(self, index=None):
        if self.main_window and self.main_window.configuration_locked():
            QMessageBox.warning(self, "Analysis Running", "Stop the analysis before selecting a plant.")
            return
        plant = self._get_selected()
        if not plant:
            return
        self.main_window._plant = {
            "name": plant[1], "Kc": plant[2],
            "area": self.main_window._plant.get("area", 4.0),
            "L": plant[3], "U": plant[4],
        }
        self.main_window._dashboard_page.update_plant(plant[1])
        self.main_window._dashboard_page.update_thresholds(plant[3], plant[4])
        from core.database import db_save_setting
        db_save_setting("active_plant", plant[1])
        self._update_active_label()
        self.main_window.show_toast(f"Plant '{plant[1]}' selected (Kc={plant[2]:.2f})")

    def _populate_table(self, plants):
        self.table.setRowCount(len(plants))
        for i, p in enumerate(plants):
            name_item = QTableWidgetItem(p[1])
            name_item.setFont(QFont("Segoe UI", 12))
            self.table.setItem(i, 0, name_item)

            kc_item = QTableWidgetItem(f"{p[2]:.2f}")
            kc_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, kc_item)

            l_item = QTableWidgetItem(f"{p[3]:.1f}")
            l_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 2, l_item)

            u_item = QTableWidgetItem(f"{p[4]:.1f}")
            u_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, u_item)

    def _filter(self, text):
        filtered = [p for p in self._all_plants if text.lower() in p[1].lower()]
        self._populate_table(filtered)

    def _get_selected(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Info", "Please select a plant.")
            return None
        name = self.table.item(row, 0).text()
        for p in self._all_plants:
            if p[1] == name:
                return p
        return None

    def _add(self):
        dlg = PlantDialog(self)
        if dlg.exec() == QDialog.Accepted:
            name, kc, l_val, u_val = dlg.result_data
            if db_add_plant(name, kc, l_val, u_val):
                if self.main_window and hasattr(self.main_window, 'show_toast'):
                    self.main_window.show_toast(f"Plant '{name}' added")
                self.refresh_data()
            else:
                QMessageBox.warning(self, "Error", f"Plant '{name}' already exists.")

    def _edit(self):
        plant = self._get_selected()
        if not plant:
            return
        if (
            self.main_window
            and self.main_window.configuration_locked()
            and self.main_window._plant.get("name") == plant[1]
        ):
            QMessageBox.warning(self, "Analysis Running", "Stop the analysis before editing the active plant.")
            return
        dlg = PlantDialog(self, plant)
        if dlg.exec() == QDialog.Accepted:
            name, kc, l_val, u_val = dlg.result_data
            if not db_update_plant(plant[1], name, kc, l_val, u_val):
                QMessageBox.warning(self, "Error", "The plant could not be updated.")
                return
            if self.main_window and self.main_window._plant.get("name") == plant[1]:
                area = self.main_window._plant.get("area", 4.0)
                self.main_window._plant = {
                    "name": name, "Kc": kc, "area": area, "L": l_val, "U": u_val
                }
                self.main_window._dashboard_page.update_plant(name)
                self.main_window._dashboard_page.update_thresholds(l_val, u_val)
            self.refresh_data()

    def _delete(self):
        plant = self._get_selected()
        if not plant:
            return
        if self.main_window and self.main_window._plant.get("name") == plant[1]:
            QMessageBox.warning(self, "Error", "Select another active plant before deletion.")
            return
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete plant '{plant[1]}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if not db_delete_plant(plant[1]):
                QMessageBox.warning(self, "Error", "The plant could not be deleted.")
                return
            if self.main_window and hasattr(self.main_window, 'show_toast'):
                self.main_window.show_toast(f"Plant '{plant[1]}' deleted")
            self.refresh_data()

    def refresh_plants(self):
        self.refresh_data()
