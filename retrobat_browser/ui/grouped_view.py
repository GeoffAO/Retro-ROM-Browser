"""
Grouped view — when filtering by genre or year, shows ROMs subdivided by system.
Each system gets a collapsible header banner followed by a mini grid of its ROMs.
"""

from typing import List, Dict
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QPushButton,
    QHBoxLayout, QFrame, QSizePolicy, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QColor, QFont, QPixmap, QPainter, QBrush, QPen, QPainterPath, QFontMetrics

from ..core.models import RomEntry, get_system_color
from .image_loader import ImageLoader, IMAGE_CACHE, make_placeholder

THUMB_W = 90
THUMB_H = 117
THUMB_PAD = 8
LABEL_H = 24


class _MiniGrid(QWidget):
    """A compact cover grid for one system's ROMs within a grouped view."""

    entry_selected  = pyqtSignal(object)
    entry_activated = pyqtSignal(object)
    selection_changed = pyqtSignal(list)
    context_menu_requested = pyqtSignal(list)

    def __init__(self, entries: List[RomEntry], parent=None):
        super().__init__(parent)
        self._entries = entries
        self._selected: set = set()
        self._last_clicked = -1
        self._hover = -1
        self._cols = 1
        self._loader = ImageLoader.instance()
        self._loader.image_ready.connect(self._on_image_ready)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self._recalc()

    def _recalc(self):
        vp_w = self.parent().width() if self.parent() else 600
        self._cols = max(1, (vp_w - 16) // (THUMB_W + THUMB_PAD))
        rows = max(1, -(-len(self._entries) // self._cols))  # ceil div
        h = rows * (THUMB_H + LABEL_H + THUMB_PAD) + THUMB_PAD
        self.setFixedHeight(h)

    def resizeEvent(self, event):
        self._recalc()
        self.update()

    def _cell_rect(self, idx):
        col = idx % self._cols
        row = idx // self._cols
        x = THUMB_PAD + col * (THUMB_W + THUMB_PAD)
        y = THUMB_PAD + row * (THUMB_H + LABEL_H + THUMB_PAD)
        return x, y

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#0c1018"))

        for idx, entry in enumerate(self._entries):
            x, y = self._cell_rect(idx)
            is_sel = idx in self._selected
            is_hov = idx == self._hover

            # Background highlight
            if is_sel or is_hov:
                bg = QColor("#0e2218") if is_sel else QColor("#141e2c")
                brd = QColor("#2abf60") if is_sel else QColor("#2a3a55")
                path = QPainterPath()
                path.addRoundedRect(x-2, y-2, THUMB_W+4, THUMB_H+LABEL_H+4, 4, 4)
                painter.fillPath(path, QBrush(bg))
                painter.setPen(QPen(brd, 2 if is_sel else 1))
                painter.drawPath(path)

            # Cover image
            cache_key = None
            img_path = entry.best_image
            if img_path:
                cache_key = f"{img_path}:{THUMB_W}x{THUMB_H}"
                pm = IMAGE_CACHE.get(cache_key)
                if pm and not pm.isNull():
                    dx = (THUMB_W - pm.width()) // 2
                    dy = (THUMB_H - pm.height()) // 2
                    painter.drawPixmap(x + dx, y + dy, pm)
                else:
                    if cache_key not in getattr(self, '_pending', {}):
                        if not hasattr(self, '_pending'):
                            self._pending = {}
                        self._pending[cache_key] = True
                        self._loader.request(img_path, THUMB_W, THUMB_H)
                    painter.drawPixmap(x, y, make_placeholder(THUMB_W, THUMB_H, entry.name, entry.system))
            else:
                painter.drawPixmap(x, y, make_placeholder(THUMB_W, THUMB_H, entry.name, entry.system))

            # Border
            painter.setPen(QPen(QColor("#1e3050"), 1))
            painter.drawRect(x, y, THUMB_W, THUMB_H)

            # Favourite
            if entry.favorite:
                painter.setPen(QPen(QColor("#ffdd44")))
                painter.setFont(QFont("Segoe UI", 9))
                painter.drawText(x+3, y+11, "★")

            # Title
            title_col = QColor("#60ffaa") if is_sel else QColor("#9ab0cc")
            painter.setPen(QPen(title_col))
            tf = QFont("Segoe UI", 8)
            painter.setFont(tf)
            fm = QFontMetrics(tf)
            elided = fm.elidedText(entry.name, Qt.TextElideMode.ElideRight, THUMB_W)
            painter.drawText(x, y + THUMB_H + 2, THUMB_W, LABEL_H - 2,
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                             elided)

        painter.end()

    def _on_image_ready(self, cache_key, pm):
        if hasattr(self, '_pending'):
            self._pending.pop(cache_key, None)
        self.update()

    def _idx_at(self, pos) -> int:
        for i in range(len(self._entries)):
            x, y = self._cell_rect(i)
            if x <= pos.x() <= x + THUMB_W and y <= pos.y() <= y + THUMB_H + LABEL_H:
                return i
        return -1

    def mouseMoveEvent(self, event):
        idx = self._idx_at(event.pos())
        if idx != self._hover:
            self._hover = idx
            self.update()

    def leaveEvent(self, event):
        self._hover = -1
        self.update()

    def mousePressEvent(self, event):
        idx = self._idx_at(event.pos())
        if event.button() == Qt.MouseButton.RightButton:
            if idx >= 0:
                if idx not in self._selected:
                    self._selected = {idx}
                    self._last_clicked = idx
                    self.update()
                    self.entry_selected.emit(self._entries[idx])
                    self.selection_changed.emit(self.get_selected_entries())
                self.context_menu_requested.emit(self.get_selected_entries())
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        mods = event.modifiers()
        ctrl  = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        if idx >= 0:
            if ctrl:
                if idx in self._selected:
                    self._selected.discard(idx)
                else:
                    self._selected.add(idx)
                self._last_clicked = idx
            elif shift and self._last_clicked >= 0:
                lo, hi = sorted((self._last_clicked, idx))
                self._selected = set(range(lo, hi + 1))
            else:
                self._selected = {idx}
                self._last_clicked = idx
            self.update()
            self.entry_selected.emit(self._entries[idx])
            self.selection_changed.emit(self.get_selected_entries())
        else:
            if not ctrl and not shift:
                self._selected.clear()
                self.update()
                self.selection_changed.emit([])

    def mouseDoubleClickEvent(self, event):
        idx = self._idx_at(event.pos())
        if idx >= 0:
            self.entry_activated.emit(self._entries[idx])

    def get_selected_entries(self):
        return [self._entries[i] for i in sorted(self._selected) if i < len(self._entries)]

    def _on_context_menu(self, pos):
        entries = self.get_selected_entries()
        if entries:
            self.context_menu_requested.emit(entries)


class GroupedView(QScrollArea):
    """
    Shows ROMs grouped by system under collapsible headers.
    Used when filtering by genre or year.
    """

    entry_selected        = pyqtSignal(object)
    entry_activated       = pyqtSignal(object)
    selection_changed     = pyqtSignal(list)
    context_menu_requested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { border: none; background: #0c1018; }")

        self._container = QWidget()
        self._container.setStyleSheet("background: #0c1018;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(12)
        self._layout.addStretch()
        self.setWidget(self._container)

        self._grids: List[_MiniGrid] = []
        self._collapsed: Dict[str, bool] = {}  # system → collapsed

    def populate(self, entries: List[RomEntry]):
        """Group entries by system and render sections."""
        # Clear existing
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._grids.clear()

        # Group by system preserving order
        groups: Dict[str, List[RomEntry]] = {}
        for e in entries:
            groups.setdefault(e.system, []).append(e)

        for system, sys_entries in groups.items():
            color = get_system_color(system)
            full_name = sys_entries[0].system_full_name

            # Section header
            header = _SystemHeader(full_name, len(sys_entries), color,
                                   collapsed=self._collapsed.get(system, False))
            header.toggle_requested.connect(
                lambda s=system, h=header, entries_ref=sys_entries:
                    self._toggle_section(s, h, entries_ref)
            )

            # Mini grid
            grid = _MiniGrid(sys_entries)
            grid.entry_selected.connect(self.entry_selected)
            grid.entry_activated.connect(self.entry_activated)
            grid.selection_changed.connect(self.selection_changed)
            grid.context_menu_requested.connect(self.context_menu_requested)

            if self._collapsed.get(system, False):
                grid.setVisible(False)

            insert_pos = self._layout.count() - 1  # before the stretch
            self._layout.insertWidget(insert_pos, header)
            self._layout.insertWidget(insert_pos + 1, grid)
            self._grids.append(grid)

    def _toggle_section(self, system: str, header: '_SystemHeader', entries: List[RomEntry]):
        currently_collapsed = self._collapsed.get(system, False)
        self._collapsed[system] = not currently_collapsed
        header.set_collapsed(not currently_collapsed)

        # Find the grid that follows this header
        idx = self._layout.indexOf(header)
        if idx >= 0:
            grid_item = self._layout.itemAt(idx + 1)
            if grid_item and grid_item.widget():
                grid_item.widget().setVisible(currently_collapsed)

    def get_selected_entries(self):
        result = []
        for g in self._grids:
            result.extend(g.get_selected_entries())
        return result

    def clear_selection(self):
        for g in self._grids:
            g._selected.clear()
            g.update()


class _SystemHeader(QFrame):
    """Collapsible section banner for a system group."""

    toggle_requested = pyqtSignal()

    def __init__(self, system_name: str, count: int, color: str, collapsed: bool = False, parent=None):
        super().__init__(parent)
        self._collapsed = collapsed
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    from: #0e1a2a, to: #0c1018);
                border-left: 3px solid {color};
                border-radius: 3px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        self._arrow_lbl = QLabel()
        self._arrow_lbl.setStyleSheet("color: #3a8a5a; font-size: 11px; background: transparent; border: none;")
        self._arrow_lbl.setFixedWidth(14)

        name_lbl = QLabel(system_name)
        name_lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold; background: transparent; border: none;")

        count_lbl = QLabel(f"{count} ROM{'s' if count != 1 else ''}")
        count_lbl.setStyleSheet("color: #3a5570; font-size: 11px; background: transparent; border: none;")

        layout.addWidget(self._arrow_lbl)
        layout.addWidget(name_lbl)
        layout.addWidget(count_lbl)
        layout.addStretch()

        self._update_arrow()

    def _update_arrow(self):
        self._arrow_lbl.setText("▶" if self._collapsed else "▼")

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        self._update_arrow()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_requested.emit()
