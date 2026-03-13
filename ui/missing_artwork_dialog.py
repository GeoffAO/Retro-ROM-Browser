"""
Missing Artwork Report dialog.

Lists all ROMs that are missing cover art (box art / thumbnail).
Shows system, title, and which media types are present.
Provides a "Scrape Selected" shortcut to open the scrape dialog for those entries.
"""

from __future__ import annotations

from typing import List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialogButtonBox,
    QAbstractItemView, QCheckBox, QWidget, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from ..core.models import RomEntry, get_system_color


class MissingArtworkDialog(QDialog):
    def __init__(self, entries: List[RomEntry], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Missing Artwork Report")
        self.setMinimumSize(800, 540)
        self.resize(880, 600)

        self._all_entries = entries
        self._missing = self._find_missing(entries)

        self._build_ui()

    def _find_missing(self, entries: List[RomEntry]) -> List[RomEntry]:
        """Return entries with no box art (image or thumbnail)."""
        return [
            e for e in entries
            if not (
                (e.image and e.image.exists()) or
                (e.thumbnail and e.thumbnail.exists())
            )
        ]

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # Summary
        total = len(self._all_entries)
        missing = len(self._missing)
        pct = missing * 100 // max(total, 1)
        hdr = QLabel(
            f"<b>{missing:,}</b> of {total:,} ROMs ({pct}%) are missing box art or thumbnail."
        )
        hdr.setStyleSheet("color: #c8e0ff; font-size: 13px; padding: 4px 0;")
        layout.addWidget(hdr)

        # Filter row
        filter_row = QHBoxLayout()
        self._chk_show_all = QCheckBox("Show all missing (no art of any kind)")
        self._chk_show_all.setChecked(True)
        self._chk_show_all.stateChanged.connect(self._populate_table)
        filter_row.addWidget(self._chk_show_all)
        filter_row.addStretch()
        count_lbl = QLabel(f"{missing:,} entries")
        count_lbl.setStyleSheet("color: #3a5570; font-size: 11px;")
        filter_row.addWidget(count_lbl)
        layout.addLayout(filter_row)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["System", "Title", "Box Art", "Screenshot", "Video", "Manual"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(24)

        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in (2, 3, 4, 5):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self._table, 1)

        # Button row
        btn_row = QHBoxLayout()
        self._btn_scrape = QPushButton("Scrape Selected…")
        self._btn_scrape.setToolTip("Open the scraper for the selected ROMs")
        self._btn_scrape.setStyleSheet("""
            QPushButton {
                background: #0a2010; border: 1px solid #1a6030;
                border-radius: 4px; color: #40e080;
                font-size: 12px; padding: 4px 14px;
            }
            QPushButton:hover { background: #0e3018; border-color: #30c060; }
        """)
        self._btn_scrape.clicked.connect(self._on_scrape_selected)
        btn_row.addWidget(self._btn_scrape)
        btn_row.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        btn_row.addWidget(btns)
        layout.addLayout(btn_row)

        self._populate_table()

    def _populate_table(self):
        self._table.setRowCount(0)
        for entry in self._missing:
            row = self._table.rowCount()
            self._table.insertRow(row)

            sys_item = QTableWidgetItem(entry.system_full_name or entry.system)
            sys_item.setForeground(QBrush(QColor(get_system_color(entry.system)).lighter(130)))
            self._table.setItem(row, 0, sys_item)

            name_item = QTableWidgetItem(entry.name)
            name_item.setForeground(QBrush(QColor("#9ab0cc")))
            name_item.setData(Qt.ItemDataRole.UserRole, entry)
            self._table.setItem(row, 1, name_item)

            def _check(val, col):
                has = bool(val and val.exists())
                itm = QTableWidgetItem("✓" if has else "✗")
                itm.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                itm.setForeground(QBrush(QColor("#40c060" if has else "#3a3a4a")))
                self._table.setItem(row, col, itm)

            _check(entry.image or entry.thumbnail, 2)
            _check(entry.screenshot, 3)
            _check(entry.video, 4)
            _check(entry.manual, 5)

    def _get_selected_entries(self) -> List[RomEntry]:
        rows = sorted(set(idx.row() for idx in self._table.selectedIndexes()))
        result = []
        for r in rows:
            item = self._table.item(r, 1)
            if item:
                entry = item.data(Qt.ItemDataRole.UserRole)
                if entry:
                    result.append(entry)
        return result

    def _on_scrape_selected(self):
        entries = self._get_selected_entries()
        if not entries:
            entries = self._missing  # if nothing selected, use all missing
        if not entries:
            return
        try:
            from .scrape_dialog import ScrapeDialog
            dlg = ScrapeDialog(entries, self)
            dlg.exec()
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Scrape Error", str(e))
