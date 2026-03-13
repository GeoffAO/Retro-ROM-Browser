"""
Right-side detail panel — scales fully with available space.
Cover art, metadata, description, media tabs, and action buttons.
"""

from pathlib import Path
from typing import Optional, List

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QWidget, QTabWidget, QPushButton, QSizePolicy, QGridLayout,
    QTextEdit, QToolButton, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QColor, QFont, QPainter, QPen, QLinearGradient, QBrush

from ..core.models import RomEntry, get_system_color


class CoverWidget(QWidget):
    """
    Displays a cover image that scales with the widget's width.
    Uses paintEvent so Qt never sees the image dimensions as a size
    constraint — the widget can shrink to any width without clipping.

    Height is derived from width × image aspect ratio, clamped to
    [min_h, max_h].  If no image is set, a fixed placeholder height
    is used instead.
    """

    def __init__(self, min_h: int = 100, max_h: int = 360, parent=None):
        super().__init__(parent)
        self._pm: Optional[QPixmap] = None
        self._min_h = min_h
        self._max_h = max_h
        self._placeholder_text = ""
        self._placeholder_color = "#334455"
        self._border_color = "#1a3050"
        # Never impose a minimum width — let the splitter control it
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def setImage(self, pm: QPixmap):
        self._pm = pm
        self.updateGeometry()
        self.update()

    def setPlaceholder(self, text: str, color: str = "#334455", border: str = "#1a3050"):
        self._pm = None
        self._placeholder_text = text
        self._placeholder_color = color
        self._border_color = border
        self.updateGeometry()
        self.update()

    def setColors(self, border_color: str):
        self._border_color = border_color

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        if self._pm and not self._pm.isNull() and self._pm.width() > 0:
            ratio = self._pm.height() / self._pm.width()
            h = int(w * ratio)
        else:
            h = 140  # placeholder height
        return max(self._min_h, min(h, self._max_h))

    def sizeHint(self) -> QSize:
        w = max(1, self.width())
        return QSize(w, self.heightForWidth(w))

    def minimumSizeHint(self) -> QSize:
        return QSize(0, self._min_h)

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if self._pm and not self._pm.isNull():
            # Scale to fit inside (w, h) preserving aspect ratio
            scaled = self._pm.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            # Gradient placeholder
            from PyQt6.QtGui import QLinearGradient, QBrush
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0, QColor("#0c1825"))
            grad.setColorAt(1, QColor("#06090f"))
            painter.fillRect(0, 0, w, h, QBrush(grad))
            if self._placeholder_text:
                painter.setPen(QPen(QColor(self._placeholder_color)))
                painter.setFont(QFont("Segoe UI", 12))
                painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter,
                                 self._placeholder_text)

        # Border
        painter.setPen(QPen(QColor(self._border_color), 1))
        painter.drawRoundedRect(0, 0, w - 1, h - 1, 5, 5)
        painter.end()


def _make_video_widget(path: Path) -> QWidget:
    """
    Return an inline video player widget for the media tab.
    Uses PyQt6.QtMultimedia (QMediaPlayer + QVideoWidget) when available.
    Falls back to a still-frame extractor using Pillow/ffmpeg, then a plain label.
    """
    # ── Attempt 1: QMediaPlayer (requires PyQt6-Qt6-Multimedia) ─────────────
    try:
        from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PyQt6.QtMultimediaWidgets import QVideoWidget
        from PyQt6.QtCore import QUrl

        container = QWidget()
        container.setStyleSheet("background: #080c14;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        video_widget = QVideoWidget()
        video_widget.setMinimumHeight(120)
        video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        player = QMediaPlayer()
        # No audio output — silent playback as requested
        player.setVideoOutput(video_widget)
        player.setSource(QUrl.fromLocalFile(str(path)))
        player.setLoops(QMediaPlayer.Loops.Infinite)

        # Controls row
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)

        btn_play = QPushButton("▶ Play")
        btn_play.setFixedHeight(24)
        btn_play.setStyleSheet("""
            QPushButton {
                background: #0e2030; border: 1px solid #2a4a60;
                border-radius: 3px; color: #60c090; font-size: 11px; padding: 0 10px;
            }
            QPushButton:hover { background: #162840; border-color: #3a9a70; }
        """)

        btn_stop = QPushButton("■ Stop")
        btn_stop.setFixedHeight(24)
        btn_stop.setStyleSheet(btn_play.styleSheet().replace("#60c090", "#8899bb"))

        name_lbl = QLabel(path.name)
        name_lbl.setStyleSheet("color: #3a5570; font-size: 10px; font-family: monospace;")
        name_lbl.setWordWrap(True)

        def _toggle_play():
            if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                player.pause()
                btn_play.setText("▶ Play")
            else:
                player.play()
                btn_play.setText("⏸ Pause")

        btn_play.clicked.connect(_toggle_play)
        btn_stop.clicked.connect(lambda: (player.stop(), btn_play.setText("▶ Play")))

        ctrl_row.addWidget(btn_play)
        ctrl_row.addWidget(btn_stop)
        ctrl_row.addStretch()
        ctrl_row.addWidget(name_lbl, 1)

        layout.addWidget(video_widget, 1)
        layout.addLayout(ctrl_row)

        # Keep player alive with the widget
        container._player = player
        return container

    except ImportError:
        pass

    # ── Fallback: extract first frame with opencv if available ───────────────
    try:
        import cv2
        cap = cv2.VideoCapture(str(path))
        ret, frame = cap.read()
        cap.release()
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame_rgb.shape
            from PyQt6.QtGui import QImage
            qi = QImage(frame_rgb.data, w, h, w * ch, QImage.Format.Format_RGB888)
            pm = QPixmap.fromImage(qi)
            widget = CoverWidget(min_h=100, max_h=240)
            widget.setColors("#1a2535")
            widget.setImage(pm)
            return widget
    except Exception:
        pass

    # ── Final fallback: filename label ───────────────────────────────────────
    lbl = QLabel(
        f"🎬  {path.name}\n\n"
        "Install PyQt6-Qt6-Multimedia for inline playback.\n"
        f"pip install PyQt6-Qt6-Multimedia"
    )
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: #5a8a7a; font-size: 11px; background: #0a0e18; padding: 12px;")
    return lbl


def _make_manual_widget(path: Path) -> QWidget:
    """
    Return a widget for a PDF manual tab.
    Shows the file name with an "Open" button that launches the system PDF viewer.
    """
    container = QWidget()
    container.setStyleSheet("background: #080c14;")
    layout = QVBoxLayout(container)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)
    layout.addStretch(1)

    icon_lbl = QLabel("📄")
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon_lbl.setStyleSheet("font-size: 32px;")
    layout.addWidget(icon_lbl)

    name_lbl = QLabel(path.name)
    name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    name_lbl.setWordWrap(True)
    name_lbl.setStyleSheet("color: #6a8aaa; font-size: 11px; font-family: monospace;")
    layout.addWidget(name_lbl)

    open_btn = QPushButton("Open PDF Manual")
    open_btn.setFixedHeight(26)
    open_btn.setStyleSheet("""
        QPushButton {
            background: #0e2030; border: 1px solid #2a4a60;
            border-radius: 3px; color: #60a0d0; font-size: 11px; padding: 0 12px;
        }
        QPushButton:hover { background: #162840; border-color: #3a80b0; color: #90d0ff; }
    """)

    def _open_pdf():
        import subprocess, sys
        try:
            if sys.platform == "win32":
                import os
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            print(f"[WARN] Could not open PDF: {e}")

    open_btn.clicked.connect(_open_pdf)
    layout.addWidget(open_btn, 0, Qt.AlignmentFlag.AlignCenter)
    layout.addStretch(1)
    return container


class MetaRow(QWidget):
    """Single key-value metadata row with wrapping value."""

    def __init__(self, key: str, value: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(6)

        lbl_key = QLabel(key)
        lbl_key.setFixedWidth(78)
        lbl_key.setStyleSheet(
            "color: #446688; font-size: 11px; font-weight: bold;"
        )
        lbl_key.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        lbl_val = QLabel(value or "—")
        lbl_val.setWordWrap(True)
        lbl_val.setStyleSheet("color: #b0c8e0; font-size: 12px;")
        lbl_val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lbl_val.setMinimumWidth(0)

        layout.addWidget(lbl_key)
        layout.addWidget(lbl_val, 1)


class DetailPanel(QFrame):
    """Full details for a selected ROM, with edit/sync/launch actions."""

    # Signals for actions
    edit_requested   = pyqtSignal(object)   # RomEntry
    delete_requested = pyqtSignal(object)   # RomEntry
    sync_requested   = pyqtSignal(list)     # [RomEntry]
    launch_requested = pyqtSignal(object)   # RomEntry

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detail-panel")
        self.setMinimumWidth(220)
        # No max width — let the splitter control it
        self._current_entry: Optional[RomEntry] = None
        self._build_ui()
        self.show_empty()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        # Content widget expands to fill scroll area width
        self._content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(10, 10, 10, 14)
        self._layout.setSpacing(5)
        scroll.setWidget(self._content)
        outer.addWidget(scroll, 1)

    def show_empty(self):
        self._clear()
        lbl = QLabel("Select a ROM\nto see details")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #334455; font-size: 14px;")
        self._layout.addStretch(1)
        self._layout.addWidget(lbl)
        self._layout.addStretch(1)

    def show_entry(self, entry: RomEntry):
        self._current_entry = entry
        self._clear()
        color = get_system_color(entry.system)

        # ── Action buttons row ───────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        def _btn(label, tip, slot, danger=False):
            b = QPushButton(label)
            b.setToolTip(tip)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setFixedHeight(26)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {'#2a0a0a' if danger else '#111820'};
                    border: 1px solid {'#7a1010' if danger else '#2a3a55'};
                    border-radius: 4px;
                    color: {'#ff7070' if danger else '#8899bb'};
                    font-size: 11px; padding: 0 6px;
                }}
                QPushButton:hover {{
                    background: {'#3a1010' if danger else '#1a2a40'};
                    border-color: {'#cc2222' if danger else '#2a9a5a'};
                    color: {'#ffaaaa' if danger else '#c8ffd0'};
                }}
            """)
            b.clicked.connect(slot)
            return b

        # Launch button — green, prominent
        launch_btn = QPushButton("▶ Launch")
        launch_btn.setToolTip("Launch game in RetroBat")
        launch_btn.setFixedHeight(30)
        launch_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        launch_btn.setStyleSheet("""
            QPushButton {
                background: #0a2010;
                border: 1px solid #1a6030;
                border-radius: 4px;
                color: #40e080;
                font-size: 13px;
                font-weight: bold;
                padding: 0 8px;
            }
            QPushButton:hover {
                background: #0e3018;
                border-color: #30c060;
                color: #80ffa0;
            }
            QPushButton:pressed {
                background: #061008;
            }
        """)
        launch_btn.clicked.connect(lambda: self.launch_requested.emit(entry))
        self._layout.addWidget(launch_btn)

        btn_row.addWidget(_btn("✏ Edit",   "Edit metadata",           lambda: self.edit_requested.emit(entry)))
        btn_row.addWidget(_btn("⇄ Sync",   "Copy to external device", lambda: self.sync_requested.emit([entry])))
        btn_row.addWidget(_btn("✕ Delete", "Delete ROM and media",    lambda: self.delete_requested.emit(entry), danger=True))
        self._layout.addLayout(btn_row)

        # ── Cover image — use marquee, fall back to thumbnail then best_image ─
        self.cover = CoverWidget(min_h=100, max_h=360)
        self.cover.setColors(f"{color}55")
        cover_path = None
        for attr in ("marquee", "thumbnail", "image", "titleshot", "screenshot"):
            val = getattr(entry, attr)
            if val and Path(val).exists():
                cover_path = val
                break
        if cover_path:
            pm = QPixmap(str(cover_path))
            if not pm.isNull():
                self.cover.setImage(pm)
            else:
                self.cover.setPlaceholder("No Art", f"{color}66", f"{color}33")
        else:
            self.cover.setPlaceholder("No Art", f"{color}66", f"{color}33")
        self._layout.addWidget(self.cover)

        # ── Title + System ───────────────────────────────────
        title_lbl = QLabel(entry.name)
        title_lbl.setObjectName("game-title")
        title_lbl.setWordWrap(True)
        title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._layout.addWidget(title_lbl)

        sys_lbl = QLabel(entry.system_full_name)
        sys_lbl.setWordWrap(True)
        sys_lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: bold; letter-spacing: 1px;"
        )
        self._layout.addWidget(sys_lbl)

        if entry.rating > 0:
            rating_lbl = QLabel(entry.display_rating)
            rating_lbl.setStyleSheet("color: #ffdd44; font-size: 15px; letter-spacing: 2px;")
            self._layout.addWidget(rating_lbl)

        if entry.favorite:
            fav_lbl = QLabel("★  Favourite")
            fav_lbl.setStyleSheet("color: #ffdd44; font-size: 11px;")
            self._layout.addWidget(fav_lbl)

        self._divider()

        # ── Metadata ─────────────────────────────────────────
        for key, val in [
            ("Year",      entry.year),
            ("Developer", entry.developer),
            ("Publisher", entry.publisher),
            ("Genre",     entry.genre),
            ("Players",   entry.players),
            ("Region",    entry.region),
            ("Language",  entry.lang),
        ]:
            if val:
                self._layout.addWidget(MetaRow(key, val))

        if entry.play_count > 0:
            self._layout.addWidget(MetaRow("Plays", str(entry.play_count)))
        if entry.file_extension:
            size_str = f"{entry.file_size_mb:.1f} MB" if entry.file_size_mb > 0 else ""
            self._layout.addWidget(MetaRow("Format", f"{entry.file_extension}  {size_str}".strip()))

        # ── Description ──────────────────────────────────────
        if entry.description:
            self._divider()
            self._section_header("DESCRIPTION")
            desc = QLabel(entry.description)
            desc.setWordWrap(True)
            desc.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            desc.setStyleSheet("color: #7a9abb; font-size: 11px; line-height: 1.4;")
            desc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._layout.addWidget(desc)

        # ── Personal notes ────────────────────────────────────
        if entry.notes:
            self._divider()
            self._section_header("NOTES")
            notes_lbl = QLabel(entry.notes)
            notes_lbl.setWordWrap(True)
            notes_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            notes_lbl.setStyleSheet(
                "color: #b0c8a0; font-size: 11px; font-style: italic; line-height: 1.4;"
            )
            notes_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._layout.addWidget(notes_lbl)

        if entry.backlog_status:
            status_colors = {
                "unplayed":    "#5a6a8a",
                "in_progress": "#c8a020",
                "completed":   "#40c060",
            }
            status_labels = {
                "unplayed":    "◌  Unplayed",
                "in_progress": "◑  In Progress",
                "completed":   "◉  Completed",
            }
            color = status_colors.get(entry.backlog_status, "#9ab0cc")
            text  = status_labels.get(entry.backlog_status, entry.backlog_status)
            bs_lbl = QLabel(text)
            bs_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
            self._layout.addWidget(bs_lbl)

        # ── Media tabs ───────────────────────────────────────
        # thumbnail = -thumb box art, image = mix, marquee, video
        media_items = []
        for attr, label in [
            ("thumbnail",  "Box Art"),
            ("marquee",    "Marquee"),
            ("image",      "Mix Image"),
            ("screenshot", "Screenshot"),
            ("titleshot",  "Title Screen"),
            ("video",      "Video"),
        ]:
            val = getattr(entry, attr)
            if val and Path(val).exists():
                media_items.append((label, attr, Path(val)))

        # PDF manual
        manual_val = entry.manual
        if manual_val and Path(manual_val).exists() and str(manual_val).lower().endswith(".pdf"):
            media_items.append(("Manual", "manual", Path(manual_val)))

        if media_items:
            self._divider()
            self._section_header("MEDIA")
            tabs = QTabWidget()
            tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            tabs.setMinimumHeight(120)
            tabs.setMaximumHeight(280)
            for label, attr, path in media_items:
                if attr == "video":
                    tabs.addTab(_make_video_widget(path), label)
                elif attr == "manual":
                    tabs.addTab(_make_manual_widget(path), label)
                else:
                    img_w = CoverWidget(min_h=100, max_h=240)
                    img_w.setColors("#1a2535")
                    pm = QPixmap(str(path))
                    if not pm.isNull():
                        img_w.setImage(pm)
                    tabs.addTab(img_w, label)
            self._layout.addWidget(tabs)

        # ── File path ────────────────────────────────────────
        self._divider()
        path_lbl = QLabel(str(entry.rom_path))
        path_lbl.setWordWrap(True)
        path_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        path_lbl.setStyleSheet(
            "color: #2a4055; font-size: 10px; font-family: 'Consolas', 'Courier New', monospace;"
        )
        path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._layout.addWidget(path_lbl)

        self._layout.addStretch(1)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _divider(self):
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background: #1a2535; max-height: 1px; margin: 3px 0;")
        self._layout.addWidget(div)

    def _section_header(self, text: str):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            "color: #3a7a55; font-size: 10px; font-weight: bold; letter-spacing: 1px;"
        )
        self._layout.addWidget(lbl)

    def _clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # clean nested layouts
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()
