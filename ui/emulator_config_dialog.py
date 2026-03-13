"""
Emulator Configuration Dialog.

Allows selecting the emulator and core for a specific system or game,
using the options defined in es_systems.cfg.

Changes are written to es_settings.cfg as:
  {system}.emulator = <name>
  {system}.core     = <name>

These settings are read by both EmulationStation and emulatorLauncher.exe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QDialogButtonBox, QGroupBox,
    QWidget, QFrame, QMessageBox, QCheckBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ..core.models import RomEntry, get_system_color
from ..core.retrobat import RetroBatInstall


class EmulatorConfigDialog(QDialog):
    """
    Configure which emulator and core to use for a system (or for a single ROM).

    If entry is provided:  title is "Configure {game} — {system}"
                           saved values affect the whole system unless a
                           per-game override is requested (future work).
    If entry is None:      generic system configurator.
    """

    def __init__(self, retrobat: RetroBatInstall, system: str,
                 entry: Optional[RomEntry] = None, parent=None):
        super().__init__(parent)
        self._rb = retrobat
        self._system = system.lower()
        self._entry = entry
        self._sdef = retrobat.system_def(self._system)

        title = f"Emulator Config — {system.upper()}"
        if entry:
            title = f"Emulator Config — {entry.name}"
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        color = get_system_color(self._system)

        # Header
        hdr = QLabel(f"  🎮  {self._system.upper()}")
        hdr.setStyleSheet(f"""
            QLabel {{
                background: #0a1020;
                color: {color};
                font-size: 14px; font-weight: bold;
                padding: 8px 12px;
                border-bottom: 1px solid {color}44;
            }}
        """)
        layout.addWidget(hdr)

        # Current saved values
        cur_emu = self._rb.get_setting(f"{self._system}.emulator", "")
        cur_core = self._rb.get_setting(f"{self._system}.core", "")

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def _lbl(text):
            l = QLabel(text)
            l.setStyleSheet("color: #6688aa; font-size: 12px;")
            return l

        # Emulator combo
        self._emu_combo = QComboBox()
        self._emu_combo.setMinimumWidth(200)
        self._emu_combo.addItem("(use default)", "")

        emulators: List[str] = []
        if self._sdef:
            emulators = list(self._sdef.emulators.keys())
        for emu in emulators:
            self._emu_combo.addItem(emu, emu)

        # Set current selection
        if cur_emu:
            idx = self._emu_combo.findData(cur_emu)
            if idx >= 0:
                self._emu_combo.setCurrentIndex(idx)
        elif self._sdef and self._sdef.default_emulator:
            idx = self._emu_combo.findData(self._sdef.default_emulator)
            if idx >= 0:
                self._emu_combo.setCurrentIndex(idx)

        self._emu_combo.currentIndexChanged.connect(self._on_emulator_changed)
        form.addRow(_lbl("Emulator"), self._emu_combo)

        # Core combo (only relevant for libretro)
        self._core_combo = QComboBox()
        self._core_combo.setMinimumWidth(200)
        self._core_combo.addItem("(use default)", "")
        form.addRow(_lbl("Core"), self._core_combo)

        self._core_lbl = _lbl("Core")

        layout.addLayout(form)

        # Info box
        self._info_lbl = QLabel()
        self._info_lbl.setWordWrap(True)
        self._info_lbl.setStyleSheet(
            "color: #3a6a5a; font-size: 10px; font-style: italic; padding: 4px 0;"
        )
        layout.addWidget(self._info_lbl)

        # Populate cores for current emulator
        self._populate_cores(cur_core)

        # Separator
        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background: #1a2535; max-height: 1px;")
        layout.addWidget(div)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Save).setText("Save to RetroBat")
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_emulator_changed(self, _idx):
        self._populate_cores("")

    def _populate_cores(self, select_core: str = ""):
        self._core_combo.clear()
        self._core_combo.addItem("(use default)", "")
        emu = self._emu_combo.currentData() or ""
        cores: List[str] = []
        if self._sdef and emu in self._sdef.emulators:
            cores = self._sdef.emulators[emu]
        for c in cores:
            self._core_combo.addItem(c, c)
        if select_core:
            idx = self._core_combo.findData(select_core)
            if idx >= 0:
                self._core_combo.setCurrentIndex(idx)
        self._core_combo.setEnabled(bool(cores))
        if not cores:
            self._info_lbl.setText("No configurable cores for this emulator.")
        else:
            self._info_lbl.setText(
                f"{len(cores)} core{'s' if len(cores) != 1 else ''} available for {emu}."
            )

    def _on_save(self):
        emu = self._emu_combo.currentData() or ""
        core = self._core_combo.currentData() or ""

        # Write to es_settings.cfg
        try:
            _write_es_setting(self._rb, f"{self._system}.emulator", emu)
            _write_es_setting(self._rb, f"{self._system}.core", core)
            self._rb.invalidate_settings_cache()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Save Failed",
                f"Could not write to es_settings.cfg:\n\n{e}")


# ── es_settings.cfg writer ────────────────────────────────────────────────────

def _write_es_setting(rb: RetroBatInstall, name: str, value: str):
    """
    Update or add a <string> entry in es_settings.cfg.
    If value is empty, remove the entry (restore default behaviour).
    """
    cfg_path = rb.es_settings_path
    if not cfg_path.exists():
        raise FileNotFoundError(f"es_settings.cfg not found: {cfg_path}")

    try:
        import xml.etree.ElementTree as ET
        ET.register_namespace("", "")
        tree = ET.parse(str(cfg_path))
        root = tree.getroot()

        # Look for existing entry
        existing = None
        for el in root:
            if el.get("name") == name:
                existing = el
                break

        if value:
            if existing is None:
                existing = ET.SubElement(root, "string")
                existing.set("name", name)
            existing.set("value", value)
        else:
            # Remove the entry to restore default
            if existing is not None:
                root.remove(existing)

        ET.indent(tree, space="\t")
        tree.write(str(cfg_path), encoding="utf-8", xml_declaration=True)
    except Exception as e:
        raise RuntimeError(f"Failed to write es_settings.cfg: {e}") from e
