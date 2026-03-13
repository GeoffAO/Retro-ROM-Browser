"""
Virtual grid view — renders only the visible portion of the ROM grid.

Instead of creating one QWidget per ROM (which kills performance at 3000+),
this widget paints cells directly onto the canvas using QPainter.
Only visible rows are rendered. Images are loaded asynchronously.
"""

from typing import List, Optional, Dict, Tuple
import math

from PyQt6.QtWidgets import QAbstractScrollArea, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint, QSize, QTimer, QRectF
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QFont, QFontMetrics,
    QBrush, QPixmap, QPainterPath
)

from ..core.models import RomEntry, get_system_color
from .image_loader import ImageLoader, IMAGE_CACHE, make_placeholder

GRID_SIZES = {
    "small":  (100, 130, 28,  9),
    "medium": (150, 195, 34, 10),
    "large":  (200, 260, 40, 11),
}

CELL_PAD_H = 10
CELL_PAD_V = 12
MARGIN      = 12


class VirtualGridView(QAbstractScrollArea):
    entry_selected = pyqtSignal(object)
    entry_activated = pyqtSignal(object)
    selection_changed = pyqtSignal(list)
    context_menu_requested = pyqtSignal(list)   # list of RomEntry

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.viewport().setMouseTracking(True)

        self._entries: List[RomEntry] = []
        self._grid_size = "medium"
        self._selected_idx: int = -1
        self._hover_idx: int = -1

        self._cols: int = 1
        self._cell_w: int = 160
        self._cell_h: int = 230
        self._cover_w: int = 150
        self._cover_h: int = 195
        self._label_h: int = 34
        self._font_size: int = 10
        self._total_rows: int = 0
        self._total_height: int = 0

        self._pending: Dict[str, bool] = {}
        self._selection: set = set()   # set of selected indices (multi-select)
        self._last_clicked: int = -1   # anchor for shift-click range

        self._loader = ImageLoader.instance()
        self._loader.image_ready.connect(self._on_image_ready)

        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(80)
        self._resize_timer.timeout.connect(self._recalculate)

        self.verticalScrollBar().valueChanged.connect(
            lambda _: self.viewport().update()
        )

    def populate(self, entries: List[RomEntry]):
        self._entries = entries
        self._selected_idx = -1
        self._hover_idx = -1
        self._selection.clear()
        self._last_clicked = -1
        self._pending.clear()
        self._recalculate()
        self.verticalScrollBar().setValue(0)
        self.viewport().update()

    def set_grid_size(self, size: str):
        if size in GRID_SIZES and size != self._grid_size:
            self._grid_size = size
            IMAGE_CACHE.clear()
            self._pending.clear()
            self._recalculate()
            self.viewport().update()

    def _recalculate(self):
        cw, ch, lh, fs = GRID_SIZES[self._grid_size]
        self._cover_w = cw
        self._cover_h = ch
        self._label_h = lh
        self._font_size = fs
        self._cell_w = cw + CELL_PAD_H
        self._cell_h = ch + lh + CELL_PAD_V

        vp_w = self.viewport().width()
        usable = max(vp_w - MARGIN * 2, self._cell_w)
        self._cols = max(1, usable // self._cell_w)

        n = len(self._entries)
        self._total_rows = math.ceil(n / self._cols) if n else 0
        self._total_height = self._total_rows * self._cell_h + MARGIN * 2

        self.verticalScrollBar().setRange(
            0, max(0, self._total_height - self.viewport().height())
        )
        self.verticalScrollBar().setPageStep(self.viewport().height())
        self.verticalScrollBar().setSingleStep(self._cell_h // 3)

    def _x_offset(self) -> int:
        total_grid_w = self._cols * self._cell_w - CELL_PAD_H
        return MARGIN + max(0, (self.viewport().width() - total_grid_w - MARGIN * 2) // 2)

    def _pos_to_index(self, pos: QPoint) -> int:
        scroll = self.verticalScrollBar().value()
        x_off = self._x_offset()
        rel_x = pos.x() - x_off
        rel_y = pos.y() + scroll - MARGIN
        if rel_x < 0 or rel_y < 0:
            return -1
        col = int(rel_x // self._cell_w)
        row = int(rel_y // self._cell_h)
        if col >= self._cols:
            return -1
        cell_local_x = rel_x % self._cell_w
        cell_local_y = rel_y % self._cell_h
        if cell_local_x > self._cover_w or cell_local_y > self._cover_h + self._label_h:
            return -1
        idx = row * self._cols + col
        return idx if idx < len(self._entries) else -1

    def _visible_row_range(self) -> Tuple[int, int]:
        scroll = self.verticalScrollBar().value()
        vp_h = self.viewport().height()
        first = max(0, (scroll - MARGIN) // self._cell_h)
        last = min(self._total_rows - 1, (scroll + vp_h - MARGIN) // self._cell_h + 1)
        return int(first), int(last)

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Background
        painter.fillRect(self.viewport().rect(), QColor("#0c1018"))

        if not self._entries:
            painter.setPen(QPen(QColor("#334455")))
            painter.setFont(QFont("Segoe UI", 14))
            painter.drawText(
                self.viewport().rect(), Qt.AlignmentFlag.AlignCenter,
                "No ROMs found.\nAdjust filters or load a different library.",
            )
            painter.end()
            return

        scroll = self.verticalScrollBar().value()
        first_row, last_row = self._visible_row_range()
        x_off = self._x_offset()

        for row in range(first_row, last_row + 1):
            for col in range(self._cols):
                idx = row * self._cols + col
                if idx >= len(self._entries):
                    break
                x = x_off + col * self._cell_w
                y = MARGIN + row * self._cell_h - scroll
                self._paint_cell(painter, idx, x, y)

        painter.end()

    def _paint_cell(self, painter: QPainter, idx: int, x: int, y: int):
        entry = self._entries[idx]
        cw, ch, lh = self._cover_w, self._cover_h, self._label_h
        is_sel = (idx in self._selection) or (idx == self._selected_idx)
        is_hov = (idx == self._hover_idx)

        # Background highlight
        if is_sel or is_hov:
            bg = QColor("#0e2218") if is_sel else QColor("#141e2c")
            border = QColor("#2abf60") if is_sel else QColor("#2a3a55")
            bw = 2 if is_sel else 1
            path = QPainterPath()
            path.addRoundedRect(QRectF(x - 3, y - 3, cw + 6, ch + lh + 6), 5, 5)
            painter.fillPath(path, QBrush(bg))
            painter.setPen(QPen(border, bw))
            painter.drawPath(path)

        # Cover image
        pm = self._get_pixmap(idx)
        if pm and not pm.isNull():
            dx = (cw - pm.width()) // 2
            dy = (ch - pm.height()) // 2
            painter.drawPixmap(x + dx, y + dy, pm)
        else:
            ph = make_placeholder(cw, ch, entry.name, entry.system)
            painter.drawPixmap(x, y, ph)

        # Cover border
        painter.setPen(QPen(QColor("#1e3050"), 1))
        painter.drawRect(QRect(x, y, cw, ch))

        # Favourite star
        if entry.favorite:
            painter.setPen(QPen(QColor("#ffdd44")))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(x + 4, y + 16, "★")

        # Title
        title_color = QColor("#60ffaa") if is_sel else QColor("#9ab0cc")
        painter.setPen(QPen(title_color))
        tf = QFont("Segoe UI", self._font_size)
        if entry.favorite:
            tf.setBold(True)
        painter.setFont(tf)
        title_rect = QRect(x, y + ch + 2, cw, lh - 2)
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop |
            Qt.TextFlag.TextWordWrap,
            self._elide_title(entry.name, cw, lh, tf),
        )

    def _elide_title(self, title: str, max_w: int, max_h: int, font: QFont) -> str:
        fm = QFontMetrics(font)
        line_h = fm.height() + 2
        max_lines = max(1, max_h // line_h)
        words = title.split()
        lines, current = [], ""
        for word in words:
            test = (current + " " + word).strip()
            if fm.horizontalAdvance(test) <= max_w:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = fm.elidedText(lines[-1], Qt.TextElideMode.ElideRight, max_w)
        return "\n".join(lines)

    def _get_pixmap(self, idx: int) -> Optional[QPixmap]:
        entry = self._entries[idx]
        img_path = entry.best_image
        if not img_path:
            return None
        cache_key = f"{img_path}:{self._cover_w}x{self._cover_h}"
        pm = IMAGE_CACHE.get(cache_key)
        if pm:
            return pm
        if cache_key not in self._pending:
            self._pending[cache_key] = True
            self._loader.request(img_path, self._cover_w, self._cover_h)
        return None

    def _on_image_ready(self, cache_key: str, pm: QPixmap):
        self._pending.pop(cache_key, None)
        self.viewport().update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_timer.start()

    def mouseMoveEvent(self, event):
        idx = self._pos_to_index(event.pos())
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.viewport().update()

    def leaveEvent(self, event):
        if self._hover_idx != -1:
            self._hover_idx = -1
            self.viewport().update()

    def get_selected_entries(self):
        """Return all currently selected RomEntry objects."""
        return [self._entries[i] for i in sorted(self._selection)
                if i < len(self._entries)]

    def clear_selection(self):
        self._selection.clear()
        self._selected_idx = -1
        self.viewport().update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            idx = self._pos_to_index(event.pos())
            if idx >= 0:
                # If right-clicked item isn't already selected, select it alone
                if idx not in self._selection:
                    self._selection = {idx}
                    self._selected_idx = idx
                    self._last_clicked = idx
                    self.viewport().update()
                    self.entry_selected.emit(self._entries[idx])
                    self.selection_changed.emit(self.get_selected_entries())
                self.context_menu_requested.emit(self.get_selected_entries())
            return

        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._pos_to_index(event.pos())
            mods = event.modifiers()
            ctrl  = bool(mods & Qt.KeyboardModifier.ControlModifier)
            shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

            if idx >= 0:
                if ctrl:
                    # Toggle this item while keeping everything else selected
                    if idx in self._selection:
                        self._selection.discard(idx)
                        # Move focus to another selected item if available
                        self._selected_idx = max(self._selection, default=-1)
                    else:
                        self._selection.add(idx)
                        self._selected_idx = idx
                    self._last_clicked = idx

                elif shift and self._last_clicked >= 0:
                    # Extend/replace selection with contiguous range
                    lo, hi = sorted((self._last_clicked, idx))
                    self._selection = set(range(lo, hi + 1))
                    self._selected_idx = idx
                    # Don't update _last_clicked for shift — anchor stays fixed

                else:
                    # Plain click: select only this item
                    self._selection = {idx}
                    self._selected_idx = idx
                    self._last_clicked = idx

                self.viewport().update()

                # Always show the most-recently-clicked entry in the detail panel
                if self._selected_idx >= 0:
                    self.entry_selected.emit(self._entries[self._selected_idx])
                self.selection_changed.emit(self.get_selected_entries())

            else:
                # Clicked empty space — clear unless modifier held
                if not ctrl and not shift:
                    self._selection.clear()
                    self._selected_idx = -1
                    self.viewport().update()
                    self.selection_changed.emit([])

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._pos_to_index(event.pos())
            if idx >= 0:
                self.entry_activated.emit(self._entries[idx])

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        step = self._cell_h if abs(delta) >= 120 else self._cell_h // 3
        val = self.verticalScrollBar().value()
        if delta > 0:
            self.verticalScrollBar().setValue(max(0, val - step))
        else:
            self.verticalScrollBar().setValue(
                min(self.verticalScrollBar().maximum(), val + step))

    def keyPressEvent(self, event):
        n = len(self._entries)
        if n == 0:
            return
        idx = self._selected_idx
        key = event.key()
        if key == Qt.Key.Key_Right:   idx = min(n - 1, idx + 1)
        elif key == Qt.Key.Key_Left:  idx = max(0, idx - 1)
        elif key == Qt.Key.Key_Down:  idx = min(n - 1, idx + self._cols)
        elif key == Qt.Key.Key_Up:    idx = max(0, idx - self._cols)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if idx >= 0: self.entry_activated.emit(self._entries[idx])
            return
        else:
            super().keyPressEvent(event)
            return
        if idx != self._selected_idx and idx >= 0:
            self._selected_idx = idx
            self._scroll_to_index(idx)
            self.viewport().update()
            self.entry_selected.emit(self._entries[idx])

    def _scroll_to_index(self, idx: int):
        row = idx // self._cols
        y_top = MARGIN + row * self._cell_h
        y_bot = y_top + self._cell_h
        scroll = self.verticalScrollBar().value()
        vp_h = self.viewport().height()
        if y_top < scroll:
            self.verticalScrollBar().setValue(y_top - MARGIN)
        elif y_bot > scroll + vp_h:
            self.verticalScrollBar().setValue(y_bot - vp_h + MARGIN)


# Alias so main_window.py import still works
GridView = VirtualGridView
