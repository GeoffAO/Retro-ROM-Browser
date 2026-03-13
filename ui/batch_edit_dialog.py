"""
Batch metadata editor — edit shared fields across multiple ROMs at once.

Each field has a checkbox; only checked fields are written to all entries.
Fields left blank + checked will clear that value on all entries.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QDialogButtonBox,
    QPushButton, QScrollArea, QWidget, QDoubleSpinBox,
    QCheckBox, QFrame, QSizePolicy, QMessageBox, QProgressDialog
)
from PyQt6.QtCore import Qt, pyqtSignal

from ..core.models import RomEntry


class BatchEditDialog(QDialog):
    """
    Edit one or more fields across a list of RomEntry objects simultaneously.
    Only fields whose checkbox is ticked will be applied.
    """

    batch_saved = pyqtSignal(list)   # emits updated list of RomEntry

    def __init__(self, entries: List[RomEntry], parent=None):
        super().__init__(parent)
        self.entries = entries
        n = len(entries)
        self.setWindowTitle(f"Batch Edit — {n} ROM{'s' if n != 1 else ''}")
        self.setMinimumSize(600, 560)
        self.resize(660, 640)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QLabel(
            f"  ✏  Batch Edit — {len(self.entries)} ROMs\n"
            f"  Check a field to overwrite it on ALL selected ROMs."
        )
        header.setStyleSheet("""
            QLabel {
                background: #0a1020; color: #40c080;
                font-size: 12px; padding: 10px 14px;
                border-bottom: 1px solid #1a2535;
            }
        """)
        layout.addWidget(header)

        # ROM list preview
        names = "  " + ",  ".join(e.name for e in self.entries[:6])
        if len(self.entries) > 6:
            names += f"  … +{len(self.entries) - 6} more"
        preview = QLabel(names)
        preview.setWordWrap(True)
        preview.setStyleSheet(
            "background: #0c1018; color: #3a5570; font-size: 10px; "
            "padding: 6px 14px; border-bottom: 1px solid #1a2535;"
        )
        layout.addWidget(preview)

        # Scrollable form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        def _lbl(text):
            l = QLabel(text)
            l.setStyleSheet("color: #6688aa; font-size: 12px;")
            return l

        # Each row: [checkbox] [field widget]
        self._fields = {}   # attr → (checkbox, widget)

        def _row(attr, label, multiline=False, width=None):
            cb = QCheckBox()
            cb.setToolTip(f"Apply {label} to all selected ROMs")
            cb.setFixedWidth(20)

            if multiline:
                w = QTextEdit()
                w.setMinimumHeight(80)
                w.setMaximumHeight(140)
                w.setEnabled(False)
                cb.toggled.connect(w.setEnabled)
            else:
                w = QLineEdit()
                if width:
                    w.setMaximumWidth(width)
                w.setEnabled(False)
                cb.toggled.connect(w.setEnabled)

            container = QWidget()
            hl = QHBoxLayout(container)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(6)
            hl.addWidget(cb)
            hl.addWidget(w, 1)

            form.addRow(_lbl(label), container)
            self._fields[attr] = (cb, w)

        _row("developer", "Developer")
        _row("publisher", "Publisher")
        _row("genre",     "Genre")
        _row("players",   "Players",  width=80)
        _row("region",    "Region",   width=120)
        _row("lang",      "Language", width=120)
        _row("description", "Description", multiline=True)

        # Rating row
        cb_rating = QCheckBox()
        cb_rating.setFixedWidth(20)
        self.f_rating = QDoubleSpinBox()
        self.f_rating.setRange(0.0, 1.0)
        self.f_rating.setSingleStep(0.1)
        self.f_rating.setDecimals(2)
        self.f_rating.setValue(0.0)
        self.f_rating.setMaximumWidth(90)
        self.f_rating.setEnabled(False)
        cb_rating.toggled.connect(self.f_rating.setEnabled)
        rating_container = QWidget()
        rl = QHBoxLayout(rating_container)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        rl.addWidget(cb_rating)
        rl.addWidget(self.f_rating)
        rl.addStretch()
        form.addRow(_lbl("Rating"), rating_container)
        self._fields["rating"] = (cb_rating, self.f_rating)

        # Favorite / Hidden flags
        cb_fav = QCheckBox()
        cb_fav.setFixedWidth(20)
        self.f_favorite = QCheckBox("Mark as favourite")
        self.f_favorite.setEnabled(False)
        cb_fav.toggled.connect(self.f_favorite.setEnabled)
        fav_container = QWidget()
        fl = QHBoxLayout(fav_container)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)
        fl.addWidget(cb_fav)
        fl.addWidget(self.f_favorite)
        fl.addStretch()
        form.addRow(_lbl("Favourite"), fav_container)
        self._fields["favorite"] = (cb_fav, self.f_favorite)

        cb_hid = QCheckBox()
        cb_hid.setFixedWidth(20)
        self.f_hidden = QCheckBox("Hide from library")
        self.f_hidden.setEnabled(False)
        cb_hid.toggled.connect(self.f_hidden.setEnabled)
        hid_container = QWidget()
        hl2 = QHBoxLayout(hid_container)
        hl2.setContentsMargins(0, 0, 0, 0)
        hl2.setSpacing(6)
        hl2.addWidget(cb_hid)
        hl2.addWidget(self.f_hidden)
        hl2.addStretch()
        form.addRow(_lbl("Hidden"), hid_container)
        self._fields["hidden"] = (cb_hid, self.f_hidden)

        scroll.setWidget(form_widget)
        layout.addWidget(scroll, 1)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Save).setText(
            f"Apply to {len(self.entries)} ROMs"
        )
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        btns.setContentsMargins(12, 8, 12, 12)
        layout.addWidget(btns)

    def _get_value(self, attr: str, widget):
        """Extract the typed value from a field widget."""
        if attr == "rating":
            return widget.value()
        if attr == "favorite":
            return widget.isChecked()
        if attr == "hidden":
            return widget.isChecked()
        if attr == "description":
            return widget.toPlainText().strip()
        return widget.text().strip()

    def _on_save(self):
        # Collect which fields to apply
        to_apply = {}
        for attr, (cb, widget) in self._fields.items():
            if cb.isChecked():
                to_apply[attr] = self._get_value(attr, widget)

        if not to_apply:
            QMessageBox.information(self, "Nothing Selected",
                "Tick at least one field checkbox to apply changes.")
            return

        # Apply to all entries
        errors = []
        for entry in self.entries:
            for attr, value in to_apply.items():
                setattr(entry, attr, value)
            try:
                from .edit_dialog import _write_gamelist_entry
                _write_gamelist_entry(entry)
            except Exception as e:
                errors.append(f"{entry.name}: {e}")

        if errors:
            QMessageBox.warning(self, "Save Warnings",
                f"{len(errors)} entries could not be written to disk:\n" +
                "\n".join(errors[:8]) +
                ("\n…" if len(errors) > 8 else ""))

        self.batch_saved.emit(self.entries)
        self.accept()
