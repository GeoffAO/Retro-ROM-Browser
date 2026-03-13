"""
Full-screen detail view — Steam-style immersive game page.
Activated on double-click. Sidebar + right panel are hidden while shown.
Left/Right keys + buttons navigate the current list. Escape returns.
Right-click hero banner → set custom hero image.
"""
import shutil
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QFileDialog, QMenu, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter, QColor, QLinearGradient, QBrush, QCursor

from ..core.models import RomEntry, get_system_color

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.gif)"


# ──────────────────────────────────────────────────────────────────────────────
# Hero banner — right-click to set custom image
# ──────────────────────────────────────────────────────────────────────────────

class _HeroBanner(QWidget):
    change_image_requested = pyqtSignal()   # user right-clicked "Set Hero Image…"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pm: Optional[QPixmap] = None
        self._color = "#2a5a9a"
        self.setFixedHeight(360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_ctx)

    def set_content(self, pm, color):
        self._pm = pm
        self._color = color
        self.update()

    def _show_ctx(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#0e1824; color:#9ab0cc; border:1px solid #2a3a55;
                    padding:4px 0; font-size:12px; }
            QMenu::item { padding:5px 24px 5px 14px; }
            QMenu::item:selected { background:#1a2a40; color:#c8ffd0; }
        """)
        act = menu.addAction("🖼  Set Hero / Background Image…")
        act.triggered.connect(self.change_image_requested)
        menu.exec(QCursor.pos())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        p.fillRect(0, 0, w, h, QColor("#060c16"))
        if self._pm and not self._pm.isNull():
            s = self._pm.scaled(w, h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap((w-s.width())//2, (h-s.height())//2, s)
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.0, QColor(6,12,22,30))
        g.setColorAt(0.5, QColor(6,12,22,120))
        g.setColorAt(1.0, QColor(6,12,22,248))
        p.fillRect(0, 0, w, h, QBrush(g))
        c = QColor(self._color)
        tg = QLinearGradient(0, h-80, 0, h)
        tg.setColorAt(0, QColor(c.red(),c.green(),c.blue(),0))
        tg.setColorAt(1, QColor(c.red(),c.green(),c.blue(),45))
        p.fillRect(0, h-80, w, 80, QBrush(tg))
        # Hint text bottom-right
        p.setPen(QColor("#1e2e42"))
        from PyQt6.QtGui import QFont
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(0, h-20, w-8, 18, Qt.AlignmentFlag.AlignRight, "right-click to set hero image")
        p.end()


class _NavBtn(QPushButton):
    def __init__(self, t, parent=None):
        super().__init__(t, parent)
        self.setFixedSize(36, 36)
        self.setStyleSheet("""
            QPushButton { background:rgba(8,16,30,200); border:1px solid #253545;
                border-radius:18px; color:#6a9abb; font-size:17px; font-weight:bold; }
            QPushButton:hover { background:rgba(20,40,70,230); border-color:#3a8a5a; color:#b8f0c8; }
            QPushButton:disabled { color:#1a2535; border-color:#1a2535; }
        """)


# ──────────────────────────────────────────────────────────────────────────────
# Main view
# ──────────────────────────────────────────────────────────────────────────────

class FullDetailView(QWidget):
    close_requested  = pyqtSignal()
    edit_requested   = pyqtSignal(object)
    delete_requested = pyqtSignal(object)
    sync_requested   = pyqtSignal(list)
    image_changed    = pyqtSignal(object)   # RomEntry — after any image update

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: List[RomEntry] = []
        self._idx = 0
        self._hero_widget: Optional[_HeroBanner] = None
        self.setStyleSheet("background:#060c16;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QWidget()
        top.setFixedHeight(46)
        top.setStyleSheet("background:#040a12; border-bottom:1px solid #141e2c;")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(12, 0, 16, 0)
        tl.setSpacing(10)

        self._back_btn = QPushButton("◀  Back to Library")
        self._back_btn.setFixedHeight(30)
        self._back_btn.setStyleSheet("""
            QPushButton { background:#0a1420; border:1px solid #253545; border-radius:5px;
                color:#6a8aaa; font-size:12px; padding:0 14px; }
            QPushButton:hover { background:#102030; border-color:#3a7a4a; color:#b0f0c0; }
        """)
        self._back_btn.clicked.connect(self.close_requested)

        self._prev_btn = _NavBtn("‹")
        self._next_btn = _NavBtn("›")
        self._prev_btn.clicked.connect(self._go_prev)
        self._next_btn.clicked.connect(self._go_next)

        self._top_title = QLabel()
        self._top_title.setStyleSheet("color:#3a5a7a; font-size:12px;")

        self._pos_lbl = QLabel()
        self._pos_lbl.setStyleSheet("color:#253545; font-size:11px; min-width:55px;")
        self._pos_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        tl.addWidget(self._back_btn)
        tl.addWidget(self._prev_btn)
        tl.addWidget(self._next_btn)
        tl.addSpacing(6)
        tl.addWidget(self._top_title, 1)
        tl.addWidget(self._pos_lbl)
        root.addWidget(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:#060c16;}")
        self._scroll_bar = scroll.verticalScrollBar()

        self._body = QWidget()
        self._body.setStyleSheet("background:#060c16;")
        self._bl = QVBoxLayout(self._body)
        self._bl.setContentsMargins(0, 0, 0, 60)
        self._bl.setSpacing(0)
        scroll.setWidget(self._body)
        root.addWidget(scroll, 1)

    def show_entry(self, entry: RomEntry, entries: List[RomEntry]):
        self._entries = entries
        try:
            self._idx = entries.index(entry)
        except ValueError:
            self._idx = 0
        self._render()
        self.setFocus()

    def _clear(self):
        self._hero_widget = None
        while self._bl.count():
            item = self._bl.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _render(self):
        self._clear()
        self._scroll_bar.setValue(0)
        if not self._entries:
            return
        entry = self._entries[self._idx]
        color = get_system_color(entry.system)

        # Hero
        hero = _HeroBanner()
        self._hero_widget = hero
        hero_pm = None
        for attr in ("screenshot", "titleshot", "image", "marquee", "thumbnail"):
            v = getattr(entry, attr)
            if v and Path(str(v)).exists():
                pm = QPixmap(str(v))
                if not pm.isNull():
                    hero_pm = pm
                    break
        hero.set_content(hero_pm, color)
        hero.change_image_requested.connect(lambda: self._on_set_hero_image(entry))
        self._bl.addWidget(hero)

        # Title band
        tb_w = QWidget(); tb_w.setStyleSheet("background:#060c16;")
        tbl = QHBoxLayout(tb_w)
        tbl.setContentsMargins(48, 20, 48, 16)
        tbl.setSpacing(24)

        box = QLabel()
        box.setFixedSize(130, 168)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setStyleSheet(f"QLabel{{background:#0a1828;border:2px solid {color}44;"
                          f"border-radius:4px;color:#2a4060;font-size:11px;}}")
        for attr in ("thumbnail", "image"):
            v = getattr(entry, attr)
            if v and Path(str(v)).exists():
                pm = QPixmap(str(v))
                if not pm.isNull():
                    box.setPixmap(pm.scaled(126,164,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation))
                    break
        else:
            box.setText("No Art")

        ti = QVBoxLayout(); ti.setSpacing(6)

        sl = QLabel(entry.system_full_name.upper())
        sl.setStyleSheet(f"color:{color};font-size:11px;font-weight:bold;letter-spacing:2px;")
        nl = QLabel(entry.name); nl.setWordWrap(True)
        nl.setStyleSheet("color:#ddeeff;font-size:27px;font-weight:bold;")
        ti.addWidget(sl); ti.addWidget(nl)

        if entry.rating > 0:
            rl = QLabel(f"{entry.display_rating}   {entry.rating*5:.1f} / 5")
            rl.setStyleSheet("color:#ffdd44;font-size:13px;letter-spacing:1px;")
            ti.addWidget(rl)
        if entry.favorite:
            ti.addWidget(self._lbl("★  Favourite","color:#ffdd44;font-size:12px;"))

        parts = [p for p in [entry.year, entry.developer, entry.genre,
                 (f"{entry.players} players") if entry.players else None] if p]
        if parts:
            ml = QLabel("   ·   ".join(parts)); ml.setWordWrap(True)
            ml.setStyleSheet("color:#3a5a7a;font-size:12px;")
            ti.addWidget(ml)
        ti.addSpacing(10)

        def _abtn(label, tip, slot, danger=False):
            b = QPushButton(label); b.setToolTip(tip); b.setFixedHeight(32)
            cbrd = "#7a1010" if danger else f"{color}77"
            cbg  = "#200808" if danger else "#0a1828"
            ccol = "#ff7070" if danger else color
            b.setStyleSheet(f"""
                QPushButton{{background:{cbg};border:1px solid {cbrd};border-radius:5px;
                    color:{ccol};font-size:12px;padding:0 18px;}}
                QPushButton:hover{{background:{'#2a0808' if danger else '#142840'};
                    border-color:{'#cc2222' if danger else color};
                    color:{'#ffaaaa' if danger else '#ccffcc'};}}
            """)
            b.clicked.connect(slot); return b

        br = QHBoxLayout(); br.setSpacing(8)
        br.addWidget(_abtn("✏  Edit Metadata","Edit",lambda:self.edit_requested.emit(entry)))
        br.addWidget(_abtn("🖼  Change Box Art","Replace box art image",
                           lambda: self._on_change_box_art(entry)))
        br.addWidget(_abtn("⇄  Sync to Device","Sync",lambda:self.sync_requested.emit([entry])))
        br.addWidget(_abtn("✕  Delete","Delete",lambda:self.delete_requested.emit(entry),True))
        br.addStretch()
        ti.addLayout(br); ti.addStretch()

        tbl.addWidget(box); tbl.addLayout(ti, 1)
        self._bl.addWidget(tb_w)

        dv = QFrame(); dv.setFrameShape(QFrame.Shape.HLine)
        dv.setStyleSheet(f"background:{color}22;max-height:1px;margin:0 48px;")
        self._bl.addWidget(dv)

        # Two-column content
        cw = QWidget(); cw.setStyleSheet("background:#060c16;")
        cl = QHBoxLayout(cw)
        cl.setContentsMargins(48, 28, 48, 28); cl.setSpacing(36)

        left = QVBoxLayout(); left.setSpacing(20)

        if entry.description:
            left.addWidget(self._sect_hdr("ABOUT THIS GAME", color))
            dl = QLabel(entry.description); dl.setWordWrap(True)
            dl.setStyleSheet("color:#6888a8;font-size:13px;line-height:1.5;")
            dl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            left.addWidget(dl)

        media_pms = []
        seen = set()
        for attr in ("screenshot","titleshot","image","marquee","thumbnail"):
            v = getattr(entry, attr)
            if v and str(v) not in seen:
                p = Path(str(v))
                if p.exists():
                    pm = QPixmap(str(p))
                    if not pm.isNull():
                        media_pms.append(pm); seen.add(str(v))
        if len(media_pms) > 1:
            left.addWidget(self._sect_hdr("SCREENSHOTS & MEDIA", color))
            sr = QHBoxLayout(); sr.setSpacing(8)
            for pm in media_pms[:5]:
                t = QLabel(); t.setFixedSize(168,108)
                t.setAlignment(Qt.AlignmentFlag.AlignCenter)
                t.setStyleSheet(f"QLabel{{background:#0a1828;border:1px solid {color}30;border-radius:3px;}}")
                t.setPixmap(pm.scaled(164,104,Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
                sr.addWidget(t)
            sr.addStretch(); left.addLayout(sr)
        left.addStretch()

        card = QFrame(); card.setFixedWidth(230)
        card.setStyleSheet(f"QFrame{{background:#0a1828;border:1px solid {color}28;border-radius:6px;}}")
        mcl = QVBoxLayout(card); mcl.setContentsMargins(18,18,18,18); mcl.setSpacing(0)

        def _mrow(k, v):
            if not v: return
            rw = QWidget(); rw.setStyleSheet("background:transparent;")
            rl = QVBoxLayout(rw); rl.setContentsMargins(0,6,0,6); rl.setSpacing(2)
            kl = QLabel(k.upper())
            kl.setStyleSheet(f"color:{color}66;font-size:9px;font-weight:bold;"
                             f"letter-spacing:1px;background:transparent;")
            vl = QLabel(str(v)); vl.setWordWrap(True)
            vl.setStyleSheet("color:#7a9ab8;font-size:12px;background:transparent;")
            rl.addWidget(kl); rl.addWidget(vl); mcl.addWidget(rw)
            sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"background:{color}15;max-height:1px;")
            mcl.addWidget(sep)

        _mrow("Developer", entry.developer)
        _mrow("Publisher", entry.publisher)
        _mrow("Year", entry.year)
        _mrow("Genre", entry.genre)
        _mrow("Players", entry.players)
        _mrow("Region", entry.region)
        _mrow("Language", entry.lang)
        _mrow("Format", entry.file_extension)
        if entry.play_count: _mrow("Times Played", str(entry.play_count))
        if entry.file_size_mb > 0: _mrow("File Size", f"{entry.file_size_mb:.1f} MB")
        mcl.addStretch()

        right = QVBoxLayout(); right.addWidget(card); right.addStretch()
        cl.addLayout(left,1); cl.addLayout(right)
        self._bl.addWidget(cw)

        self._top_title.setText(entry.name)
        n = len(self._entries)
        self._pos_lbl.setText(f"{self._idx+1} / {n}")
        self._prev_btn.setEnabled(self._idx > 0)
        self._next_btn.setEnabled(self._idx < n-1)

    # ── Image change helpers ───────────────────────────────────────────────────

    def _on_set_hero_image(self, entry: RomEntry):
        """Right-click on hero → pick an image to use as the screenshot/hero."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Hero / Background Image", "", IMAGE_FILTER)
        if not path:
            return
        _replace_image(entry, "screenshot", Path(path), self)
        self.image_changed.emit(entry)
        # Live-update the hero banner without full re-render
        if self._hero_widget:
            pm = QPixmap(str(entry.screenshot))
            self._hero_widget.set_content(pm if not pm.isNull() else None,
                                          get_system_color(entry.system))

    def _on_change_box_art(self, entry: RomEntry):
        """Replace box art (thumbnail) for this entry."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Box Art Image", "", IMAGE_FILTER)
        if not path:
            return
        _replace_image(entry, "thumbnail", Path(path), self)
        self.image_changed.emit(entry)
        self._render()   # full re-render to update box art thumbnail

    # helpers
    def _lbl(self, text, style):
        l = QLabel(text); l.setStyleSheet(style); return l

    def _sect_hdr(self, text, color):
        l = QLabel(text)
        l.setStyleSheet(f"color:{color};font-size:9px;font-weight:bold;letter-spacing:2px;")
        return l

    def _go_prev(self):
        if self._idx > 0:
            self._idx -= 1; self._render()

    def _go_next(self):
        if self._idx < len(self._entries)-1:
            self._idx += 1; self._render()

    def keyPressEvent(self, event):
        k = event.key()
        if k in (Qt.Key.Key_Left, Qt.Key.Key_Backspace): self._go_prev()
        elif k == Qt.Key.Key_Right: self._go_next()
        elif k == Qt.Key.Key_Escape: self.close_requested.emit()
        else: super().keyPressEvent(event)


# ──────────────────────────────────────────────────────────────────────────────
# Shared image-replacement utility
# ──────────────────────────────────────────────────────────────────────────────

def _replace_image(entry: RomEntry, attr: str, src: Path, parent_widget=None) -> bool:
    """
    Copy src into the appropriate media folder next to gamelist.xml,
    named to match the ROM stem (RetroBat convention), then update
    entry.<attr> and write gamelist.xml.

    attr: "thumbnail" → images/<stem>-thumb.png
          "screenshot" → screenshots/<stem>.png
          "image"      → images/<stem>.png
          "marquee"    → marquees/<stem>.png
          "titleshot"  → titlescreens/<stem>.png

    Returns True on success.
    """
    import xml.etree.ElementTree as ET

    if not entry.rom_path:
        if parent_widget:
            QMessageBox.warning(parent_widget, "Cannot Save",
                "Cannot determine ROM path to save image.")
        return False

    gamelist_path = entry.rom_path.parent / "gamelist.xml"
    if not gamelist_path.exists():
        if parent_widget:
            QMessageBox.warning(parent_widget, "Cannot Save",
                f"gamelist.xml not found at:\n{gamelist_path}")
        return False

    rom_stem = entry.rom_path.stem

    # Determine destination folder and filename
    ATTR_FOLDER = {
        "thumbnail":  ("images",       f"{rom_stem}-thumb"),
        "screenshot": ("screenshots",  rom_stem),
        "image":      ("images",       rom_stem),
        "marquee":    ("marquees",     rom_stem),
        "titleshot":  ("titlescreens", rom_stem),
    }
    if attr not in ATTR_FOLDER:
        return False

    folder_name, dest_stem = ATTR_FOLDER[attr]
    dest_dir = entry.rom_path.parent / folder_name
    dest_dir.mkdir(exist_ok=True)

    # Determine extension: keep source ext if it's a supported format, else .png
    src_ext = src.suffix.lower()
    if src_ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        src_ext = ".png"
    dest_path = dest_dir / f"{dest_stem}{src_ext}"

    # Remove old file for this attr if it differs
    old = getattr(entry, attr)
    if old and Path(str(old)).exists() and Path(str(old)) != dest_path:
        try:
            Path(str(old)).unlink()
        except Exception:
            pass

    # Copy the new image
    try:
        shutil.copy2(str(src), str(dest_path))
    except Exception as e:
        if parent_widget:
            QMessageBox.critical(parent_widget, "Copy Failed", f"Could not copy image:\n{e}")
        return False

    # Update entry in memory
    setattr(entry, attr, dest_path)

    # Write back to gamelist.xml
    try:
        from ..ui.edit_dialog import _write_gamelist_entry
        _write_gamelist_entry(entry)
    except Exception as e:
        if parent_widget:
            QMessageBox.warning(parent_widget, "XML Update Failed",
                f"Image saved but gamelist.xml could not be updated:\n{e}")

    return True
