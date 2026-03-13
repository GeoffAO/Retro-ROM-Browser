"""
Background loading thread and progress dialog.
"""

from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar,
    QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot


class LoadWorker(QThread):
    """Background thread that scans the ROM library."""

    progress = pyqtSignal(str, int, int)   # system, current, total
    finished = pyqtSignal(list)            # list of RomEntry
    error = pyqtSignal(str)

    def __init__(self, roms_root: Path, include_hidden: bool = False):
        super().__init__()
        self.roms_root = roms_root
        self.include_hidden = include_hidden

    def run(self):
        try:
            from ..core.scanner import scan_library
            entries = scan_library(
                self.roms_root,
                progress_callback=lambda s, c, t: self.progress.emit(s, c, t),
                include_hidden=self.include_hidden,
            )
            self.finished.emit(entries)
        except Exception as e:
            self.error.emit(str(e))


class LoadingDialog(QDialog):
    """Progress dialog shown while scanning the library."""

    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Loading Library")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint
        )
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        self.title_lbl = QLabel("Scanning ROM Library…")
        self.title_lbl.setStyleSheet("color: #c0d8f0; font-size: 14px; font-weight: bold;")
        layout.addWidget(self.title_lbl)

        self.sys_lbl = QLabel("Initialising…")
        self.sys_lbl.setStyleSheet("color: #7a9abb; font-size: 12px;")
        layout.addWidget(self.sys_lbl)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("color: #4a6688; font-size: 11px;")
        layout.addWidget(self.count_lbl)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.cancelled)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    @pyqtSlot(str, int, int)
    def update_progress(self, system: str, current: int, total: int):
        self.sys_lbl.setText(f"Loading:  {system}")
        pct = int(current / total * 100) if total else 0
        self.progress.setValue(pct)
        self.count_lbl.setText(f"System {current} of {total}")
