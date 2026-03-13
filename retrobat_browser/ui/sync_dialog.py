"""
Sync dialog — copy selected ROMs (and optionally their media) to an
external destination, e.g. a retro handheld SD card or network share.

Mirrors the source system folder structure under the destination.
"""

import shutil
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QProgressBar, QTextEdit, QCheckBox,
    QFileDialog, QGroupBox, QWidget, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot

from ..core.models import RomEntry
from ..core.settings import Settings


class SyncWorker(QThread):
    progress = pyqtSignal(int, int, str)
    log_line = pyqtSignal(str)
    finished = pyqtSignal(int, int, int)   # copied, skipped, errors

    def __init__(self, entries: List[RomEntry], dest_root: Path,
                 copy_media: bool, copy_saves: bool, overwrite: bool):
        super().__init__()
        self.entries     = entries
        self.dest_root   = dest_root
        self.copy_media  = copy_media
        self.copy_saves  = copy_saves
        self.overwrite   = overwrite
        self._cancel     = False

    def cancel(self):
        self._cancel = True

    def run(self):
        copied, skipped, errors = 0, 0, 0
        total = len(self.entries)

        for i, entry in enumerate(self.entries):
            if self._cancel:
                self.log_line.emit("⚠  Cancelled.")
                break

            self.progress.emit(i, total, f"Syncing: {entry.name}")

            try:
                result = self._sync_one(entry)
                if result == "copied":
                    copied += 1
                    self.log_line.emit(f"✓  {entry.name}")
                elif result == "skipped":
                    skipped += 1
                    self.log_line.emit(f"–  {entry.name}  (skipped, already exists)")
            except Exception as e:
                errors += 1
                self.log_line.emit(f"✗  {entry.name} — {e}")

        self.progress.emit(total, total, "Done")
        self.finished.emit(copied, skipped, errors)

    def _sync_one(self, entry: RomEntry) -> str:
        if not entry.rom_path or not entry.rom_path.exists():
            raise FileNotFoundError("ROM file not found")

        # Destination system folder, e.g. <dest>/roms/snes/
        dest_sys_dir = self.dest_root / entry.system
        dest_sys_dir.mkdir(parents=True, exist_ok=True)

        dest_rom = dest_sys_dir / entry.rom_path.name

        if dest_rom.exists() and not self.overwrite:
            return "skipped"

        shutil.copy2(str(entry.rom_path), str(dest_rom))

        if self.copy_media:
            for attr in ("image", "screenshot", "marquee", "titleshot", "thumbnail"):
                src = getattr(entry, attr)
                if src and src.exists():
                    # Mirror the subfolder name
                    rel = src.relative_to(entry.rom_path.parent)
                    dest_media = dest_sys_dir / rel
                    dest_media.parent.mkdir(parents=True, exist_ok=True)
                    if not dest_media.exists() or self.overwrite:
                        shutil.copy2(str(src), str(dest_media))

        return "copied"


class SyncDialog(QDialog):
    sync_completed = pyqtSignal()

    def __init__(self, entries: List[RomEntry], settings: Settings, parent=None):
        super().__init__(parent)
        self.entries  = entries
        self.settings = settings
        self._worker: Optional[SyncWorker] = None
        self.setWindowTitle(f"Sync to Device — {len(entries)} ROM(s)")
        self.setMinimumSize(520, 500)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)

        # Destination
        dest_box = QGroupBox("Destination")
        dest_box.setStyleSheet("QGroupBox { color: #6688aa; font-size: 12px; }")
        dest_layout = QVBoxLayout(dest_box)

        dest_row = QHBoxLayout()
        self.f_dest = QLineEdit(self.settings.get("sync_dest", ""))
        self.f_dest.setPlaceholderText("e.g. E:\\roms  or  /media/sdcard/roms")
        btn_browse = QPushButton("Browse…")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self._browse_dest)
        dest_row.addWidget(self.f_dest, 1)
        dest_row.addWidget(btn_browse)
        dest_layout.addLayout(dest_row)

        note = QLabel(
            "ROMs will be copied to:  <dest>/<system>/<rom_file>\n"
            "This mirrors the standard RetroBat folder structure."
        )
        note.setStyleSheet("color: #445566; font-size: 11px;")
        dest_layout.addWidget(note)
        layout.addWidget(dest_box)

        # Options
        opts_box = QGroupBox("Options")
        opts_box.setStyleSheet("QGroupBox { color: #6688aa; font-size: 12px; }")
        opts_layout = QVBoxLayout(opts_box)
        self.cb_media     = QCheckBox("Also copy media files (box art, screenshots, etc.)")
        self.cb_media.setChecked(True)
        self.cb_overwrite = QCheckBox("Overwrite existing files")
        opts_layout.addWidget(self.cb_media)
        opts_layout.addWidget(self.cb_overwrite)
        layout.addWidget(opts_box)

        # ROM summary
        rom_list = "\n".join(
            f"  • [{e.system}]  {e.name}" for e in self.entries[:10]
        ) + (f"\n  … and {len(self.entries)-10} more" if len(self.entries) > 10 else "")
        summary = QLabel(f"ROMs selected:  {len(self.entries)}\n{rom_list}")
        summary.setStyleSheet("color: #7a9abb; font-size: 11px; background: #0c1018; "
                              "border: 1px solid #1a2535; border-radius: 4px; padding: 8px;")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, len(self.entries))
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.progress_lbl = QLabel("")
        self.progress_lbl.setStyleSheet("color: #6688aa; font-size: 11px;")
        self.progress_lbl.setVisible(False)
        layout.addWidget(self.progress_lbl)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        self.log.setStyleSheet(
            "background: #080c14; color: #5a8a6a; font-size: 11px; "
            "font-family: monospace; border: 1px solid #1a2535;"
        )
        self.log.setVisible(False)
        layout.addWidget(self.log)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_start  = QPushButton("▶  Start Sync")
        self.btn_start.setObjectName("primary")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

    def _browse_dest(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Destination Folder",
            self.f_dest.text() or str(Path.home()),
        )
        if path:
            self.f_dest.setText(path)

    def _on_start(self):
        dest = self.f_dest.text().strip()
        if not dest:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Destination", "Please choose a destination folder.")
            return

        self.settings.set("sync_dest", dest)
        self.settings.save()

        self.btn_start.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_lbl.setVisible(True)
        self.log.setVisible(True)

        self._worker = SyncWorker(
            self.entries, Path(dest),
            copy_media=self.cb_media.isChecked(),
            copy_saves=False,
            overwrite=self.cb_overwrite.isChecked(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log_line.connect(self._on_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
        else:
            self.reject()

    @pyqtSlot(int, int, str)
    def _on_progress(self, current, total, msg):
        self.progress_bar.setValue(current)
        self.progress_lbl.setText(msg)

    @pyqtSlot(str)
    def _on_log(self, line):
        self.log.append(line)

    @pyqtSlot(int, int, int)
    def _on_finished(self, copied, skipped, errors):
        self.btn_cancel.setText("Close")
        self.btn_start.setEnabled(True)
        self.progress_lbl.setText(
            f"Done — {copied} copied, {skipped} skipped, {errors} errors."
        )
        self.sync_completed.emit()
