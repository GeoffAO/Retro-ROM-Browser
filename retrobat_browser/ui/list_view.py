"""
List/table view — shows ROMs in a sortable table, Calibre-style.
"""

from typing import List, Optional
from PyQt6.QtWidgets import (
    QTableView, QHeaderView, QAbstractItemView, QSizePolicy, QMenu
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QAbstractTableModel, QModelIndex,
    QSortFilterProxyModel
)
from PyQt6.QtGui import QColor, QFont, QBrush

from ..core.models import RomEntry, get_system_color


COLUMNS = [
    ("name",        "Title",        300, True),
    ("system",      "System",       130, True),
    ("year",        "Year",          60, True),
    ("developer",   "Developer",    150, True),
    ("publisher",   "Publisher",    150, False),
    ("genre",       "Genre",        120, True),
    ("rating",      "Rating",        80, True),
    ("play_count",  "Plays",         55, False),
    ("file_ext",    "Format",        60, False),
    ("file_size",   "Size (MB)",     75, False),
]

# Sort key functions per column attr
def _sort_key(entry: RomEntry, col: str):
    if col == "name":       return (entry.name or "").lower()
    if col == "system":     return (entry.system_full_name or "").lower()
    if col == "year":       return entry.year or "0000"
    if col == "developer":  return (entry.developer or "").lower()
    if col == "publisher":  return (entry.publisher or "").lower()
    if col == "genre":      return (entry.genre or "").lower()
    if col == "rating":     return entry.rating
    if col == "play_count": return entry.play_count
    if col == "file_ext":   return (entry.file_extension or "").lower()
    if col == "file_size":  return entry.file_size_mb
    return ""


class RomTableModel(QAbstractTableModel):
    """Qt table model for ROM entries — supports in-model sorting."""

    def __init__(self):
        super().__init__()
        self._entries: List[RomEntry] = []
        self._sort_col: int = 0
        self._sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder

    def set_entries(self, entries: List[RomEntry]):
        self.beginResetModel()
        self._entries = list(entries)
        self._apply_sort()
        self.endResetModel()

    def entry_at(self, row: int) -> Optional[RomEntry]:
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    def rowCount(self, parent=QModelIndex()):
        return len(self._entries)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole:
                return COLUMNS[section][1]
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder):
        self._sort_col = column
        self._sort_order = order
        self.layoutAboutToBeChanged.emit()
        self._apply_sort()
        self.layoutChanged.emit()

    def _apply_sort(self):
        if not self._entries:
            return
        col_attr = COLUMNS[self._sort_col][0]
        reverse = (self._sort_order == Qt.SortOrder.DescendingOrder)
        self._entries.sort(key=lambda e: _sort_key(e, col_attr), reverse=reverse)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        entry = self._entries[index.row()]
        col = COLUMNS[index.column()][0]

        if role == Qt.ItemDataRole.DisplayRole:
            if col == "name":      return entry.name
            if col == "system":    return entry.system_full_name
            if col == "year":      return entry.year
            if col == "developer": return entry.developer
            if col == "publisher": return entry.publisher
            if col == "genre":     return entry.genre
            if col == "rating":    return entry.display_rating or ""
            if col == "play_count":return str(entry.play_count) if entry.play_count else ""
            if col == "file_ext":  return entry.file_extension
            if col == "file_size": return f"{entry.file_size_mb:.1f}" if entry.file_size_mb > 0 else ""
            return ""

        if role == Qt.ItemDataRole.ForegroundRole:
            if col == "system":
                return QBrush(QColor(get_system_color(entry.system)).lighter(130))
            if col == "rating" and entry.rating > 0:
                return QBrush(QColor("#ffdd44"))
            if col == "name" and entry.favorite:
                return QBrush(QColor("#d0f0c0"))
            return QBrush(QColor("#9ab0cc"))

        if role == Qt.ItemDataRole.FontRole:
            if col == "name":
                f = QFont("Segoe UI", 12)
                if entry.favorite:
                    f.setBold(True)
                return f
            return QFont("Segoe UI", 11)

        if role == Qt.ItemDataRole.ToolTipRole:
            if col == "name":
                return entry.description[:200] + ("…" if len(entry.description) > 200 else "")

        if role == Qt.ItemDataRole.UserRole:
            return entry

        return None


class ListView(QTableView):
    """Sortable table view for ROM entries."""

    entry_selected    = pyqtSignal(object)
    entry_activated   = pyqtSignal(object)
    selection_changed = pyqtSignal(list)
    context_menu_requested = pyqtSignal(list)   # list of RomEntry

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = RomTableModel()

        self.setModel(self._model)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)          # enables header click → model.sort()
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(26)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        hh = self.horizontalHeader()
        hh.setSectionsMovable(True)
        hh.setStretchLastSection(False)
        hh.setSortIndicatorShown(True)
        hh.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        for i, (_, _, width, visible) in enumerate(COLUMNS):
            self.setColumnWidth(i, width)
            if not visible:
                self.hideColumn(i)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        self.clicked.connect(self._on_clicked)
        self.doubleClicked.connect(self._on_double_clicked)
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def populate(self, entries):
        self._model.set_entries(entries)

    def get_selected_entries(self):
        rows = sorted(set(idx.row() for idx in self.selectedIndexes()))
        return [e for e in (self._model.entry_at(r) for r in rows) if e]

    def _on_clicked(self, index: QModelIndex):
        entry = self._model.entry_at(index.row())
        if entry:
            self.entry_selected.emit(entry)

    def _on_double_clicked(self, index: QModelIndex):
        entry = self._model.entry_at(index.row())
        if entry:
            self.entry_activated.emit(entry)

    def _on_selection_changed(self, *_):
        self.selection_changed.emit(self.get_selected_entries())

    def _on_context_menu(self, pos):
        entries = self.get_selected_entries()
        if entries:
            self.context_menu_requested.emit(entries)
