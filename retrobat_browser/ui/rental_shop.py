"""
Virtual Rental Shop — discover new games from your library.

VirtualRentalShopPanel is an embeddable QWidget (lives in the main stack).
It emits entry_selected (single-click) and entry_activated (double-click)
so the right-side detail panel and full-detail view work normally.
Renting is toggled via a dedicated button on each card (not single-click).
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QGridLayout, QMessageBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QLinearGradient, QBrush,
    QFont, QFontMetrics, QPen, QPainterPath,
)

from ..core.models import RomEntry, get_system_color

# ── Persistence ───────────────────────────────────────────────────────────────

STATE_FILE = Path.home() / ".retrobat_browser" / "rental_state.json"
MAX_RENTED  = 5
REFRESH_DAYS = 7
SHOP_SIZE_PER_SYSTEM = 10
MAX_DISPLAYED = 60


def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(state: dict):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] rental state save: {e}")


# ── Card widget ───────────────────────────────────────────────────────────────

class _RentalCard(QWidget):
    """
    Single game card.
    - Single click  → entry_selected
    - Double click  → entry_activated
    - Rent button   → rented_changed
    """

    entry_selected  = pyqtSignal(object)        # RomEntry
    entry_activated = pyqtSignal(object)        # RomEntry
    rented_changed  = pyqtSignal(object, bool)  # (entry, want_rent)

    CARD_W = 152
    CARD_H = 248
    COVER_H = 168

    def __init__(self, entry: RomEntry, is_rented: bool = False, parent=None):
        super().__init__(parent)
        self.entry = entry
        self._rented   = is_rented
        self._selected = False
        self._cover_pm: Optional[QPixmap] = None
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._load_cover()
        self.setToolTip(
            f"{entry.name}\n{entry.system_full_name}"
            + (f"\n{entry.year}"  if entry.year  else "")
            + (f"\n{entry.genre}" if entry.genre else "")
        )

    def _load_cover(self):
        for attr in ("thumbnail", "image", "marquee", "screenshot", "titleshot"):
            v = getattr(self.entry, attr)
            if v and Path(str(v)).exists():
                pm = QPixmap(str(v))
                if not pm.isNull():
                    self._cover_pm = pm.scaled(
                        self.CARD_W - 4, self.COVER_H,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
                    return

    def set_rented(self, v: bool):
        self._rented = v
        self.update()

    def set_selected(self, v: bool):
        self._selected = v
        self.update()

    @property
    def is_rented(self): return self._rented

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        color = QColor(get_system_color(self.entry.system))
        W, H = self.CARD_W, self.CARD_H
        CH = self.COVER_H

        path = QPainterPath()
        path.addRoundedRect(1, 1, W-2, H-2, 7, 7)

        if self._selected:
            p.fillPath(path, QBrush(QColor(
                color.red()//4+10, color.green()//4+8, color.blue()//4+6)))
            p.setPen(QPen(color.lighter(140), 2))
        elif self._rented:
            p.fillPath(path, QBrush(QColor(
                color.red()//5+8, color.green()//5+6, color.blue()//5+4)))
            p.setPen(QPen(color, 2))
        else:
            p.fillPath(path, QBrush(QColor("#0c1828")))
            p.setPen(QPen(QColor("#1e2e42"), 1))
        p.drawPath(path)

        # Cover area
        p.fillRect(2, 2, W-4, CH, QColor("#080e1a"))
        if self._cover_pm and not self._cover_pm.isNull():
            pm = self._cover_pm
            dx = (W - pm.width()) // 2
            dy = (CH - pm.height()) // 2 + 2
            p.drawPixmap(dx, max(2, dy), pm)
        else:
            pg = QLinearGradient(2, 2, 2, CH)
            pg.setColorAt(0, QColor(color.red()//6, color.green()//6, color.blue()//6))
            pg.setColorAt(1, QColor("#080e1a"))
            p.fillRect(2, 2, W-4, CH, QBrush(pg))
            p.setPen(QPen(QColor(color).lighter(70)))
            p.setFont(QFont("Segoe UI", 26, QFont.Weight.Bold))
            p.drawText(2, 2, W-4, CH, Qt.AlignmentFlag.AlignCenter,
                       self.entry.system[:1].upper())

        # Cover bottom fade
        g = QLinearGradient(0, CH-35, 0, CH+2)
        g.setColorAt(0, QColor(8,14,26,0)); g.setColorAt(1, QColor(8,14,26,160))
        p.fillRect(2, CH-35, W-4, 37, QBrush(g))

        # System label
        sys_y = CH + 4
        p.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        p.setPen(QPen(QColor(color).lighter(120)))
        fm = QFontMetrics(p.font())
        p.drawText(5, sys_y, W-10, 13, Qt.AlignmentFlag.AlignLeft,
                   fm.elidedText(self.entry.system_full_name,
                                  Qt.TextElideMode.ElideRight, W-10))

        # Title
        p.setFont(QFont("Segoe UI", 9))
        p.setPen(QPen(QColor("#bccfe0")))
        p.drawText(5, sys_y+15, W-10, H - sys_y - 15 - 26,
                   Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft |
                   Qt.TextFlag.TextWordWrap,
                   self.entry.name)

        # Rented badge strip at bottom
        badge_y = H - 24
        bp = QPainterPath()
        bp.addRoundedRect(2, badge_y, W-4, 22, 0, 0)
        bp.addRoundedRect(2, badge_y, W-4, 22, 4, 4)
        if self._rented:
            p.fillRect(2, badge_y, W-4, 22,
                       QColor(color.red()//3+30, color.green()//3+30, color.blue()//3+15, 210))
            p.setPen(QPen(color, 1))
            p.drawLine(2, badge_y, W-2, badge_y)
            p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            p.setPen(QPen(QColor("#ffffff")))
            p.drawText(2, badge_y, W-4, 22, Qt.AlignmentFlag.AlignCenter, "✓  RENTED")
        else:
            p.fillRect(2, badge_y, W-4, 22, QColor("#080e1a"))
            p.setPen(QPen(QColor("#1a2840"), 1))
            p.drawLine(2, badge_y, W-2, badge_y)
            p.setFont(QFont("Segoe UI", 7))
            p.setPen(QPen(QColor("#253545")))
            p.drawText(2, badge_y, W-4, 22, Qt.AlignmentFlag.AlignCenter,
                       "right-click to rent")
        p.end()

    # ── interaction ───────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.entry_selected.emit(self.entry)
        elif event.button() == Qt.MouseButton.RightButton:
            self.rented_changed.emit(self.entry, not self._rented)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.entry_activated.emit(self.entry)


# ── Section header ────────────────────────────────────────────────────────────

class _SectionHeader(QWidget):
    def __init__(self, system_name, count, color, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(f"""
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #0e1a2e, stop:1 #080e1a);
            border-left: 3px solid {color}; border-radius:3px;
        """)
        lay = QHBoxLayout(self); lay.setContentsMargins(12,0,12,0)
        nl = QLabel(system_name)
        nl.setStyleSheet(f"color:{color};font-size:13px;font-weight:bold;background:transparent;")
        cl = QLabel(f"{count} game{'s' if count!=1 else ''}")
        cl.setStyleSheet("color:#2a4060;font-size:11px;background:transparent;")
        lay.addWidget(nl); lay.addWidget(cl); lay.addStretch()


# ── Panel (embeddable widget) ─────────────────────────────────────────────────

class VirtualRentalShopPanel(QWidget):
    """
    Embeddable panel — lives as an index in the main stack.
    Emits entry_selected / entry_activated for integration with
    the sidebar detail panel and full-detail view.
    Right-click a card to toggle its rented status.
    """

    entry_selected   = pyqtSignal(object)   # RomEntry — single click
    entry_activated  = pyqtSignal(object)   # RomEntry — double click
    selection_changed = pyqtSignal(list)    # [RomEntry] — for bulk bar

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_entries: List[RomEntry] = []
        self._state = _load_state()
        self._cards: List[_RentalCard] = []
        self._shop_entries: List[RomEntry] = []
        self._selected_card: Optional[_RentalCard] = None

        self.setStyleSheet("""
            QWidget { background:#06090f; }
            QScrollBar:vertical { background:#0a1020; width:10px; border-radius:5px; }
            QScrollBar::handle:vertical { background:#1a2a40; border-radius:5px; min-height:30px; }
            QScrollBar::handle:vertical:hover { background:#2a4060; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
        """)
        self._build_ui()

        # Debounce resize
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self._reflow_cards)

    def load(self, all_entries: List[RomEntry]):
        """Call this when a library is loaded or refreshed."""
        self._all_entries = all_entries
        self._state = _load_state()
        self._refresh_shop()

    # ── UI skeleton ───────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header band
        hdr = QWidget()
        hdr.setStyleSheet("""
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #08101e, stop:0.5 #0a1428, stop:1 #08101e);
            border-bottom: 1px solid #1a2840;
        """)
        hdr.setFixedHeight(96)
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(24, 12, 24, 10)
        hl.setSpacing(6)

        title_row = QHBoxLayout()
        title_lbl = QLabel("📼  VIRTUAL RENTAL SHOP")
        title_lbl.setStyleSheet(
            "color:#4a9ade; font-size:20px; font-weight:bold; letter-spacing:3px;")
        self._sub_lbl = QLabel()
        self._sub_lbl.setStyleSheet("color:#3a5a7a; font-size:11px;")
        self._rented_lbl = QLabel()
        self._rented_lbl.setStyleSheet(
            "color:#4a8aba; font-size:12px; font-weight:bold;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        title_row.addWidget(self._rented_lbl)

        btn_row = QHBoxLayout(); btn_row.setSpacing(10)

        def _hbtn(text, tip, color_accent, slot):
            b = QPushButton(text); b.setToolTip(tip); b.setFixedHeight(26)
            b.setStyleSheet(f"""
                QPushButton {{ background:#0a1420; border:1px solid {color_accent}55;
                    border-radius:4px; color:{color_accent}; font-size:11px; padding:0 14px; }}
                QPushButton:hover {{ background:#122030; border-color:{color_accent};
                    color:#ffffff; }}
                QPushButton:disabled {{ background:#060c14; border-color:#151f2e;
                    color:#1e3040; }}
            """)
            b.clicked.connect(slot); return b

        self._refresh_btn = _hbtn("↻  Restock Shop",
            f"Restock randomly — available every {REFRESH_DAYS} days after returning all games",
            "#4a8aba", self._on_refresh)
        self._return_btn  = _hbtn("⏎  Return All",
            "Return all rented games", "#3a8a5a", self._on_return_all)

        btn_row.addWidget(self._sub_lbl)
        btn_row.addStretch()
        btn_row.addWidget(self._refresh_btn)
        btn_row.addWidget(self._return_btn)

        hl.addLayout(title_row)
        hl.addLayout(btn_row)
        root.addWidget(hdr)

        # Instructions strip
        instr = QLabel(
            "  Single-click a game to preview it in the detail panel  ·  "
            "Double-click to open full view  ·  Right-click to rent / return  ·  "
            f"Rent up to {MAX_RENTED} games"
        )
        instr.setFixedHeight(26)
        instr.setStyleSheet(
            "background:#080e18; color:#253545; font-size:10px; "
            "border-bottom:1px solid #111a28; padding-left:24px;")
        root.addWidget(instr)

        # Scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea{border:none;background:#06090f;}")

        self._content = QWidget()
        self._content.setStyleSheet("background:#06090f;")
        self._cl = QVBoxLayout(self._content)
        self._cl.setContentsMargins(20, 16, 20, 24)
        self._cl.setSpacing(20)
        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll, 1)

        # Status bar
        sb = QWidget(); sb.setFixedHeight(32)
        sb.setStyleSheet("background:#080e1a; border-top:1px solid #111a28;")
        sbl = QHBoxLayout(sb); sbl.setContentsMargins(24,0,24,0)
        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet("color:#253545; font-size:10px;")
        sbl.addWidget(self._status_lbl); sbl.addStretch()
        root.addWidget(sb)

    # ── Shop data ─────────────────────────────────────────────────────────────

    def _can_refresh(self):
        rented = self._state.get("rented_paths", [])
        if rented:
            return False, "Return all rented games before restocking."
        last = self._state.get("last_refresh")
        if last:
            last_dt = datetime.fromisoformat(last)
            nxt = last_dt + timedelta(days=REFRESH_DAYS)
            if datetime.now() < nxt:
                secs = (nxt - datetime.now()).total_seconds()
                days = int(secs // 86400)
                hrs  = int((secs % 86400) // 3600)
                if days > 0:
                    return False, f"Shop restocks in {days}d {hrs}h."
                else:
                    return False, f"Shop restocks in {hrs}h."
        return True, ""

    def _sample_shop(self):
        by_sys: Dict[str, List[RomEntry]] = {}
        for e in self._all_entries:
            by_sys.setdefault(e.system, []).append(e)
        result = []
        for es in by_sys.values():
            result.extend(random.sample(es, min(SHOP_SIZE_PER_SYSTEM, len(es))))
        random.shuffle(result)
        return result[:MAX_DISPLAYED]

    def _refresh_shop(self):
        saved = self._state.get("shop_paths", [])
        rented = set(self._state.get("rented_paths", []))
        pm = {str(e.rom_path): e for e in self._all_entries if e.rom_path}
        if saved:
            self._shop_entries = [pm[p] for p in saved if p in pm]
        if not self._shop_entries:
            self._shop_entries = self._sample_shop()
            self._state["shop_paths"] = [str(e.rom_path) for e in self._shop_entries]
            if not self._state.get("last_refresh"):
                self._state["last_refresh"] = datetime.now().isoformat()
            _save_state(self._state)
        self._render_cards(rented)
        self._update_header()

    def _render_cards(self, rented_paths: set):
        while self._cl.count():
            item = self._cl.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._cards.clear()
        self._selected_card = None

        by_sys: Dict[str, List[RomEntry]] = {}
        for e in self._shop_entries:
            by_sys.setdefault(e.system_full_name, []).append(e)

        cols = max(1, (self.width() - 60) // (_RentalCard.CARD_W + 12))

        for sys_name in sorted(by_sys.keys()):
            entries = by_sys[sys_name]
            color = get_system_color(entries[0].system)
            self._cl.addWidget(_SectionHeader(sys_name, len(entries), color))

            gw = QWidget(); gw.setStyleSheet("background:transparent;")
            grid = QGridLayout(gw)
            grid.setContentsMargins(0,4,0,4); grid.setSpacing(12)

            for i, entry in enumerate(entries):
                card = _RentalCard(entry, str(entry.rom_path) in rented_paths)
                card.entry_selected.connect(self._on_card_selected)
                card.entry_activated.connect(self.entry_activated)
                card.rented_changed.connect(self._on_rent_toggle)
                grid.addWidget(card, i // cols, i % cols)
                self._cards.append(card)

            self._cl.addWidget(gw)
        self._cl.addStretch()

    def _reflow_cards(self):
        """Re-render cards with updated column count after resize."""
        rented = set(self._state.get("rented_paths", []))
        self._render_cards(rented)

    def _update_header(self):
        n = len(self._shop_entries)
        n_sys = len({e.system for e in self._shop_entries})
        rented = set(self._state.get("rented_paths", []))
        n_r = len(rented)

        last = self._state.get("last_refresh")
        date_str = ""
        if last:
            date_str = f"  ·  stocked {datetime.fromisoformat(last).strftime('%b %d, %Y')}"
        self._sub_lbl.setText(f"{n} games across {n_sys} systems{date_str}")

        self._rented_lbl.setText(
            f"📼  {n_r} / {MAX_RENTED} rented" if n_r
            else f"📼  0 / {MAX_RENTED}  — right-click to rent")

        can, reason = self._can_refresh()
        self._refresh_btn.setEnabled(can)
        self._refresh_btn.setToolTip("" if can else reason)
        self._return_btn.setEnabled(bool(rented))

        self._status_lbl.setText(
            f"🔒  {reason}" if (not can and reason)
            else f"Shop restocks every {REFRESH_DAYS} days · return all games first")

    # ── Interaction ───────────────────────────────────────────────────────────

    def _on_card_selected(self, entry: RomEntry):
        # Deselect previous
        if self._selected_card:
            self._selected_card.set_selected(False)
        # Find and select new card
        for card in self._cards:
            if card.entry is entry:
                card.set_selected(True)
                self._selected_card = card
                break
        self.entry_selected.emit(entry)
        self.selection_changed.emit([entry])

    def _on_rent_toggle(self, entry: RomEntry, want_rent: bool):
        rented = set(self._state.get("rented_paths", []))
        ps = str(entry.rom_path)
        if want_rent:
            if len(rented) >= MAX_RENTED:
                QMessageBox.information(
                    self, "Limit Reached",
                    f"You can only rent {MAX_RENTED} games at a time.\n"
                    "Return one before renting another.")
                return
            rented.add(ps)
        else:
            rented.discard(ps)
        self._state["rented_paths"] = list(rented)
        _save_state(self._state)
        for card in self._cards:
            if str(card.entry.rom_path) == ps:
                card.set_rented(ps in rented); break
        self._update_header()

    def _on_return_all(self):
        rented = self._state.get("rented_paths", [])
        if not rented: return
        if QMessageBox.question(
                self, "Return All Games",
                f"Return all {len(rented)} rented game(s)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        self._state["rented_paths"] = []
        _save_state(self._state)
        for card in self._cards: card.set_rented(False)
        self._update_header()

    def _on_refresh(self):
        can, reason = self._can_refresh()
        if not can:
            QMessageBox.information(self, "Can't Restock Yet", reason); return
        if QMessageBox.question(
                self, "Restock Shop",
                f"Pick {MAX_DISPLAYED} new random games?\n"
                f"The shop can only be restocked every {REFRESH_DAYS} days.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        self._shop_entries = self._sample_shop()
        self._state["shop_paths"] = [str(e.rom_path) for e in self._shop_entries]
        self._state["rented_paths"] = []
        self._state["last_refresh"] = datetime.now().isoformat()
        _save_state(self._state)
        self._render_cards(set())
        self._update_header()

    def get_selected_entries(self):
        return [self._selected_card.entry] if self._selected_card else []

    def clear_selection(self):
        if self._selected_card:
            self._selected_card.set_selected(False)
            self._selected_card = None
        self.selection_changed.emit([])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()
