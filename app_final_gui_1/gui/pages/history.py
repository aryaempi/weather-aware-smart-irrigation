from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QDateEdit, QComboBox, QDialog, QScrollArea, QFrame,
    QMessageBox
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QFont, QColor

from gui.styles import Theme
from core.database import (
    db_get_history, db_get_history_filtered,
    db_get_record_by_id, db_get_all_locations,
    db_export_csv
)


class DetailDialog(QDialog):
    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Record #{record[0]}")
        self.setMinimumSize(520, 620)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {Theme.c('bg')}; }}
            QLabel {{ font-size: 13px; }}
        """)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(6)

        header = QLabel(f"Irrigation Record #{record[0]}")
        header.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        ts = QLabel(f"Timestamp: {record[1]}")
        ts.setStyleSheet("font-size: 13px; color: #757575;")
        layout.addWidget(ts)

        def safe_float(val):
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        sections = [
            ("Plant", [
                ("Name", str(record[2]) if record[2] else "-"),
            ]),
            ("Cultivation", [
                ("Mode", str(record[23]) if record[23] else "Field"),
                ("Soil Depth", f"{safe_float(record[7]):.5f} m" if safe_float(record[7]) is not None else "-"),
            ]),
            ("Soil Data", [
                ("Sensor 1", f"{safe_float(record[11]):.1f}%" if safe_float(record[11]) is not None else "-"),
                ("Sensor 2", f"{safe_float(record[12]):.1f}%" if safe_float(record[12]) is not None else "-"),
                ("Sensor 3", f"{safe_float(record[13]):.1f}%" if safe_float(record[13]) is not None else "-"),
                ("Sensor 4", f"{safe_float(record[14]):.1f}%" if safe_float(record[14]) is not None else "-"),
                ("Median", f"{safe_float(record[4]):.1f}%" if safe_float(record[4]) is not None else "-"),
            ]),
            ("Weather", [
                ("ET\u2080", f"{safe_float(record[15]):.2f} mm" if safe_float(record[15]) is not None else "-"),
                ("Rain Today", f"{safe_float(record[16]):.1f} mm" if safe_float(record[16]) is not None else "-"),
                ("Rain 48h", f"{safe_float(record[17]):.1f} mm" if safe_float(record[17]) is not None else "-"),
                ("Min Temp", f"{safe_float(record[18]):.1f}\u00b0C" if safe_float(record[18]) is not None else "-"),
                ("Max Temp", f"{safe_float(record[19]):.1f}\u00b0C" if safe_float(record[19]) is not None else "-"),
                ("Source", str(record[20]) if record[20] else "-"),
            ]),
            ("Irrigation Decision", [
                ("Kc", f"{safe_float(record[5]):.2f}" if safe_float(record[5]) is not None else "-"),
                ("Area", f"{safe_float(record[6]):.5f} m\u00b2" if safe_float(record[6]) is not None else "-"),
                ("Water Needed", f"{safe_float(record[8]):.1f} L" if safe_float(record[8]) is not None else "-"),
                ("Water Planned", f"{safe_float(record[9]):.1f} L" if safe_float(record[9]) is not None else "-"),
                ("Estimated Delivered", f"{safe_float(record[24]):.1f} L" if len(record) > 24 and safe_float(record[24]) is not None else "-"),
                ("Execution Status", str(record[25]) if len(record) > 25 and record[25] else "-"),
                ("Pump Acknowledged", "Yes" if len(record) > 28 and record[28] else "No"),
                ("Decision", str(record[10]) if record[10] else "-"),
            ]),
            ("Location", [
                ("Name", str(record[3]) if record[3] else "-"),
                ("Latitude", f"{safe_float(record[21]):.6f}" if safe_float(record[21]) is not None else "-"),
                ("Longitude", f"{safe_float(record[22]):.6f}" if safe_float(record[22]) is not None else "-"),
            ]),
        ]

        for section_title, items in sections:
            sec = QLabel(section_title)
            sec.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 12px; color: #1976D2;")
            layout.addWidget(sec)

            for label_text, value in items:
                row = QHBoxLayout()
                lbl = QLabel(label_text)
                lbl.setStyleSheet("color: #9E9E9E; font-size: 12px;")
                row.addWidget(lbl)
                row.addStretch()
                val = QLabel(value)
                val.setStyleSheet("font-size: 13px; font-weight: 600;")
                row.addWidget(val)
                layout.addLayout(row)

        layout.addStretch()
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.addWidget(scroll)


class HistoryPage(QWidget):
    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._all_records = []
        self._displayed_records = []
        self._setup_ui()
        self.refresh_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("\U0001f4c8 History")
        title.setObjectName("page_title")
        layout.addWidget(title)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("\U0001f50d Search...")
        self.search.setObjectName("search_input")
        self.search.setFixedWidth(200)
        self.search.textChanged.connect(self._filter_by_text)
        toolbar.addWidget(self.search)

        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        self.date_from.setFixedWidth(140)
        toolbar.addWidget(QLabel("From:"))
        toolbar.addWidget(self.date_from)

        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setFixedWidth(140)
        toolbar.addWidget(QLabel("To:"))
        toolbar.addWidget(self.date_to)

        self.loc_filter = QComboBox()
        self.loc_filter.setFixedWidth(150)
        self.loc_filter.addItem("All Locations")
        toolbar.addWidget(self.loc_filter)

        toolbar.addStretch()

        filter_btn = QPushButton("\U0001f50d Filter")
        filter_btn.setObjectName("primary_btn")
        filter_btn.clicked.connect(self._apply_filters)
        toolbar.addWidget(filter_btn)

        export_csv_btn = QPushButton("\U0001f4e4 Export CSV")
        export_csv_btn.setObjectName("outline_btn")
        export_csv_btn.clicked.connect(self._export_csv)
        toolbar.addWidget(export_csv_btn)

        refresh_btn = QPushButton("\U0001f504 Refresh")
        refresh_btn.setObjectName("outline_btn")
        refresh_btn.clicked.connect(self.refresh_data)
        toolbar.addWidget(refresh_btn)

        layout.addLayout(toolbar)

        self.table = QTableWidget()
        self.table.setColumnCount(14)
        self.table.setHorizontalHeaderLabels([
            "ID", "Date", "Plant", "Mode", "Location", "Soil Median", "Kc", "Area",
            "Water Needed", "Water Planned", "Decision", "Soil Depth",
            "Estimated Delivered", "Execution Status"
        ])
        self.table.setColumnHidden(0, True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self._view_detail)
        layout.addWidget(self.table)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet("font-size: 12px; color: #9E9E9E;")
        layout.addWidget(self._count_label)

    def _load_locations_filter(self):
        locations = db_get_all_locations()
        current = self.loc_filter.currentText()
        self.loc_filter.clear()
        self.loc_filter.addItem("All Locations")
        for loc in locations:
            self.loc_filter.addItem(loc[1])
        idx = self.loc_filter.findText(current)
        if idx >= 0:
            self.loc_filter.setCurrentIndex(idx)

    def refresh_data(self):
        self._load_locations_filter()
        self._all_records = db_get_history(500)
        self._populate_table(self._all_records)

    def _apply_filters(self):
        loc = self.loc_filter.currentText()
        d_from = self.date_from.date().toString("yyyy-MM-dd")
        d_to = self.date_to.date().toString("yyyy-MM-dd")
        self._all_records = db_get_history_filtered(
            location=loc if loc != "All Locations" else None,
            date_from=d_from,
            date_to=d_to,
            limit=500
        )
        self._populate_table(self._all_records)

    def _filter_by_text(self, text):
        if not text.strip():
            self._populate_table(self._all_records)
            return
        filtered = []
        for r in self._all_records:
            searchable = " ".join(str(x) for x in r if x is not None)
            if text.lower() in searchable.lower():
                filtered.append(r)
        self._populate_table(filtered)

    def _populate_table(self, records):
        self._displayed_records = list(records)
        records = self._displayed_records
        self.table.setRowCount(len(records))
        for i, r in enumerate(records):
            id_item = QTableWidgetItem(str(r[0]))
            id_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, id_item)

            date_item = QTableWidgetItem(str(r[1])[:16] if r[1] else "-")
            date_item.setFont(QFont("Segoe UI", 11))
            self.table.setItem(i, 1, date_item)

            plant_item = QTableWidgetItem(str(r[2]) if r[2] else "-")
            self.table.setItem(i, 2, plant_item)

            mode_item = QTableWidgetItem(str(r[23]) if r[23] else "Field")
            mode_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, mode_item)

            loc_item = QTableWidgetItem(str(r[3]) if r[3] else "-")
            self.table.setItem(i, 4, loc_item)

            sm = r[4] if r[4] is not None else 0
            sm_item = QTableWidgetItem(f"{sm:.1f}%")
            sm_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 5, sm_item)

            kc = r[5] if r[5] is not None else 0
            kc_item = QTableWidgetItem(f"{kc:.2f}")
            kc_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 6, kc_item)

            area = r[6] if r[6] is not None else 0
            area_item = QTableWidgetItem(f"{area:.5f}")
            area_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 7, area_item)

            wn = r[8] if r[8] is not None else 0
            wn_item = QTableWidgetItem(f"{wn:.1f} L")
            wn_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 8, wn_item)

            wf = r[9] if r[9] is not None else 0
            wf_item = QTableWidgetItem(f"{wf:.1f} L")
            wf_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 9, wf_item)

            decision = str(r[10]) if r[10] else "-"
            dec_item = QTableWidgetItem(decision)
            note_lower = decision.lower()
            if "no irrigation" in note_lower:
                dec_item.setForeground(QColor("#4CAF50"))
            elif "monitoring" in note_lower:
                dec_item.setForeground(QColor("#FB8C00"))
            elif "normal" in note_lower:
                dec_item.setForeground(QColor("#1976D2"))
            elif "reduced" in note_lower:
                dec_item.setForeground(QColor("#26C6DA"))
            elif "canceled" in note_lower:
                dec_item.setForeground(QColor("#D32F2F"))
            self.table.setItem(i, 10, dec_item)

            sd = r[7] if r[7] is not None else 0
            sd_item = QTableWidgetItem(f"{sd:.5f}")
            sd_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 11, sd_item)

            delivered = r[24] if len(r) > 24 and r[24] is not None else 0
            delivered_item = QTableWidgetItem(f"{delivered:.1f} L")
            delivered_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 12, delivered_item)

            status = str(r[25]) if len(r) > 25 and r[25] else "-"
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 13, status_item)

        self._count_label.setText(f"Showing {len(records)} records")

    def _view_detail(self, index):
        row = index.row()
        if row < 0:
            return
        id_item = self.table.item(row, 0)
        if not id_item:
            return
        try:
            record_id = int(id_item.text())
        except (ValueError, TypeError):
            return
        full = db_get_record_by_id(record_id)
        if full:
            dlg = DetailDialog(full, self)
            dlg.exec()

    def _export_csv(self):
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "irrigation_history.csv", "CSV Files (*.csv)"
        )
        if path:
            try:
                exported = db_export_csv(path, self._displayed_records)
                if self.main_window and hasattr(self.main_window, 'show_toast'):
                    self.main_window.show_toast(f"Exported {exported} records")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", str(e))
