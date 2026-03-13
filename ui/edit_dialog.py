"""
Metadata editor dialog — edit a RomEntry's fields and write back to gamelist.xml.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QDialogButtonBox,
    QPushButton, QScrollArea, QWidget, QSpinBox,
    QDoubleSpinBox, QCheckBox, QFrame, QFileDialog,
    QSizePolicy, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QFont

from ..core.models import RomEntry, get_system_color


class EditDialog(QDialog):
    """Full metadata editor for a single ROM."""

    metadata_saved = pyqtSignal(object)   # emits updated RomEntry

    def __init__(self, entry: RomEntry, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(f"Edit — {entry.name}")
        self.setMinimumSize(580, 620)
        self.resize(640, 700)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        color = get_system_color(self.entry.system)
        header = QLabel(f"  ✏  Editing: {self.entry.name}")
        header.setStyleSheet(f"""
            QLabel {{
                background: #0a1020;
                color: {color};
                font-size: 13px;
                font-weight: bold;
                padding: 10px 14px;
                border-bottom: 1px solid #1a2535;
            }}
        """)
        layout.addWidget(header)

        # Scrollable form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        def _field(value="", multiline=False, width=None):
            if multiline:
                w = QTextEdit()
                w.setPlainText(value)
                w.setMinimumHeight(100)
                w.setMaximumHeight(200)
            else:
                w = QLineEdit(value)
                if width:
                    w.setMaximumWidth(width)
            return w

        def _lbl(text):
            l = QLabel(text)
            l.setStyleSheet("color: #6688aa; font-size: 12px;")
            return l

        self.f_name      = _field(self.entry.name)
        self.f_developer = _field(self.entry.developer)
        self.f_publisher = _field(self.entry.publisher)
        self.f_genre     = _field(self.entry.genre)
        self.f_players   = _field(self.entry.players, width=80)
        self.f_year      = _field(self.entry.year, width=80)
        self.f_region    = _field(self.entry.region, width=120)
        self.f_lang      = _field(self.entry.lang, width=120)
        self.f_desc      = _field(self.entry.description, multiline=True)

        self.f_rating = QDoubleSpinBox()
        self.f_rating.setRange(0.0, 1.0)
        self.f_rating.setSingleStep(0.1)
        self.f_rating.setDecimals(2)
        self.f_rating.setValue(self.entry.rating)
        self.f_rating.setMaximumWidth(90)
        self.f_rating.setToolTip("0.0 = unrated, 1.0 = 5 stars")

        self.f_favorite = QCheckBox("Mark as favourite")
        self.f_favorite.setChecked(self.entry.favorite)
        self.f_hidden   = QCheckBox("Hide from library")
        self.f_hidden.setChecked(self.entry.hidden)

        form.addRow(_lbl("Title"),       self.f_name)
        form.addRow(_lbl("Developer"),   self.f_developer)
        form.addRow(_lbl("Publisher"),   self.f_publisher)
        form.addRow(_lbl("Genre"),       self.f_genre)
        form.addRow(_lbl("Players"),     self.f_players)
        form.addRow(_lbl("Year"),        self.f_year)
        form.addRow(_lbl("Region"),      self.f_region)
        form.addRow(_lbl("Language"),    self.f_lang)
        form.addRow(_lbl("Rating"),      self.f_rating)
        form.addRow(_lbl("Flags"),       self.f_favorite)
        form.addRow(_lbl(""),            self.f_hidden)
        form.addRow(_lbl("Description"), self.f_desc)

        # Backlog status
        self.f_backlog = QComboBox()
        self.f_backlog.addItems(["", "Unplayed", "In Progress", "Completed"])
        _bl_map = {"": 0, "unplayed": 1, "in_progress": 2, "completed": 3}
        self.f_backlog.setCurrentIndex(_bl_map.get(self.entry.backlog_status, 0))
        self.f_backlog.setMaximumWidth(160)
        form.addRow(_lbl("Backlog"), self.f_backlog)

        # Personal notes
        self.f_notes = _field(self.entry.notes, multiline=True)
        self.f_notes.setMinimumHeight(60)
        self.f_notes.setMaximumHeight(120)
        self.f_notes.setPlaceholderText("Personal notes, tips, thoughts…")
        form.addRow(_lbl("Notes"), self.f_notes)

        # Media paths section
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background: #1a2535; max-height: 1px;")
        form.addRow(div)

        media_hdr = QLabel("MEDIA PATHS")
        media_hdr.setStyleSheet("color: #3a7a55; font-size: 10px; font-weight: bold; letter-spacing: 1px;")
        form.addRow(media_hdr)

        self._media_fields = {}
        for attr, label in [
            ("image", "Box Art"), ("screenshot", "Screenshot"),
            ("titleshot", "Title Screen"), ("marquee", "Marquee"),
            ("thumbnail", "Thumbnail"),
        ]:
            val = getattr(self.entry, attr)
            row_w = QWidget()
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(4)
            le = QLineEdit(str(val) if val else "")
            le.setStyleSheet("font-size: 11px; font-family: monospace;")
            btn = QPushButton("…")
            btn.setFixedWidth(28)
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda _, a=attr, f=le: self._browse_media(a, f))
            row_l.addWidget(le, 1)
            row_l.addWidget(btn)
            self._media_fields[attr] = le
            form.addRow(_lbl(label), row_w)

        scroll.setWidget(form_widget)
        layout.addWidget(scroll, 1)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        btns.setContentsMargins(12, 8, 12, 12)
        layout.addWidget(btns)

    def _browse_media(self, attr: str, field: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select {attr} image",
            field.text() or str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.gif)",
        )
        if path:
            field.setText(path)

    def _on_save(self):
        # Update entry fields from form
        self.entry.name       = self.f_name.text().strip()
        self.entry.developer  = self.f_developer.text().strip()
        self.entry.publisher  = self.f_publisher.text().strip()
        self.entry.genre      = self.f_genre.text().strip()
        self.entry.players    = self.f_players.text().strip()
        self.entry.region     = self.f_region.text().strip()
        self.entry.lang       = self.f_lang.text().strip()
        self.entry.rating     = self.f_rating.value()
        self.entry.favorite   = self.f_favorite.isChecked()
        self.entry.hidden     = self.f_hidden.isChecked()
        self.entry.description = self.f_desc.toPlainText().strip()
        self.entry.notes      = self.f_notes.toPlainText().strip()
        _bl_reverse = {"": "", "Unplayed": "unplayed", "In Progress": "in_progress", "Completed": "completed"}
        self.entry.backlog_status = _bl_reverse.get(self.f_backlog.currentText(), "")

        year = self.f_year.text().strip()
        if year:
            self.entry.release_year = year
            if not self.entry.release_date or self.entry.release_date[:4] != year:
                self.entry.release_date = year + "0101T000000"

        for attr, le in self._media_fields.items():
            txt = le.text().strip()
            setattr(self.entry, attr, Path(txt) if txt else None)

        # Write back to gamelist.xml
        try:
            _write_gamelist_entry(self.entry)
        except Exception as e:
            QMessageBox.warning(self, "Save Warning",
                f"Metadata saved in memory but could not write gamelist.xml:\n{e}")

        self.metadata_saved.emit(self.entry)
        self.accept()


def _write_gamelist_entry(entry: RomEntry):
    """Persist one RomEntry's changes back to its gamelist.xml."""
    gamelist_path: Optional[Path] = None

    # Find the gamelist for this entry's system
    if entry.rom_path:
        candidate = entry.rom_path.parent / "gamelist.xml"
        if candidate.exists():
            gamelist_path = candidate

    if not gamelist_path or not gamelist_path.exists():
        raise FileNotFoundError(f"Cannot locate gamelist.xml for {entry.name}")

    ET.register_namespace("", "")
    tree = ET.parse(str(gamelist_path))
    root = tree.getroot()

    # Find matching game element by path
    target = None
    for game in root.findall("game"):
        path_el = game.find("path")
        if path_el is not None and path_el.text:
            raw = path_el.text.strip().replace("\\", "/")
            if raw.endswith(entry.rom_path.name) or raw == entry.path:
                target = game
                break

    if target is None:
        raise ValueError(f"ROM entry '{entry.name}' not found in {gamelist_path}")

    def _set(tag: str, value: str):
        el = target.find(tag)
        if value:
            if el is None:
                el = ET.SubElement(target, tag)
            el.text = value
        else:
            if el is not None:
                target.remove(el)

    _set("name",        entry.name)
    _set("developer",   entry.developer)
    _set("publisher",   entry.publisher)
    _set("genre",       entry.genre)
    _set("players",     entry.players)
    _set("releasedate", entry.release_date)
    _set("region",      entry.region)
    _set("lang",        entry.lang)
    _set("desc",        entry.description)
    _set("rating",      str(entry.rating) if entry.rating > 0 else "")
    _set("favorite",    "true" if entry.favorite else "false")
    _set("hidden",      "true" if entry.hidden else "false")

    for attr, tag in [
        ("image", "image"), ("screenshot", "screenshot"),
        ("titleshot", "titlescreen"), ("marquee", "marquee"),
        ("thumbnail", "thumbnail"),
    ]:
        val = getattr(entry, attr)
        if val:
            # Store as relative path if inside same dir
            try:
                rel = val.relative_to(gamelist_path.parent)
                _set(tag, "./" + str(rel).replace("\\", "/"))
            except ValueError:
                _set(tag, str(val).replace("\\", "/"))

    # Write with indentation
    ET.indent(tree, space="  ")
    tree.write(str(gamelist_path), encoding="utf-8", xml_declaration=True)
