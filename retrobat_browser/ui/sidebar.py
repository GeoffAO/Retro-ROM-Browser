"""
Left sidebar panel — system browser, genre, year tags, quick filters.
Inspired by Calibre's tag browser.
"""

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHBoxLayout, QSizePolicy,
    QLineEdit, QCheckBox, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QColor, QBrush, QIcon

from ..core.models import get_system_color

_ARROW_OPEN   = "▼ "
_ARROW_CLOSED = "▶ "


class TagItem(QTreeWidgetItem):
    """Tree item representing a filterable tag."""

    def __init__(self, label: str, count: int, tag_type: str, tag_value: str):
        super().__init__()
        self.tag_type = tag_type
        self.tag_value = tag_value
        self.setText(0, label)
        self.setText(1, str(count) if count > 0 else "")
        self.setFont(1, QFont("Segoe UI", 10))


class SectionHeader(QTreeWidgetItem):
    """Non-selectable collapsible section header with arrow indicator."""

    def __init__(self, label: str):
        super().__init__()
        self._base_label = label
        self.setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.setForeground(0, QBrush(QColor("#3a8a5a")))
        self.setFlags(self.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self._update_arrow(expanded=True)

    def _update_arrow(self, expanded: bool):
        arrow = _ARROW_OPEN if expanded else _ARROW_CLOSED
        self.setText(0, arrow + self._base_label)
        self.setText(1, "")

    def set_expanded(self, expanded: bool):
        self._update_arrow(expanded)


class SidebarPanel(QFrame):
    """Left panel with browseable tags and quick-access filters."""

    filter_changed = pyqtSignal(str, object)  # (filter_type, value_or_None)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setMinimumWidth(180)
        self.setMaximumWidth(320)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel("LIBRARY")
        header.setObjectName("section-header")
        layout.addWidget(header)

        # Quick filters
        qf_widget = QWidget()
        qf_layout = QVBoxLayout(qf_widget)
        qf_layout.setContentsMargins(8, 6, 8, 6)
        qf_layout.setSpacing(4)

        self.all_btn = QPushButton("  ▣  All Games")
        self.all_btn.setCheckable(True)
        self.all_btn.setChecked(True)
        self.all_btn.setStyleSheet("""
            QPushButton { text-align: left; padding: 6px 10px; background: #0e2218;
                          border: 1px solid #1a4a2a; border-radius: 4px; color: #60e090; font-weight: bold; }
            QPushButton:hover { background: #152e22; }
        """)
        self.all_btn.clicked.connect(lambda: self._quick_filter("all"))
        qf_layout.addWidget(self.all_btn)

        self.fav_btn = QPushButton("  ★  Favorites")
        self.fav_btn.setCheckable(True)
        self.fav_btn.setStyleSheet("""
            QPushButton { text-align: left; padding: 6px 10px; background: transparent;
                          border: 1px solid transparent; border-radius: 4px; color: #8899bb; }
            QPushButton:hover { background: #1a1e2c; border-color: #2a3550; color: #c0d0e8; }
            QPushButton:checked { background: #1a1a0a; border-color: #8a7a00; color: #ffdd44; }
        """)
        self.fav_btn.clicked.connect(lambda: self._quick_filter("favorites"))
        qf_layout.addWidget(self.fav_btn)

        layout.addWidget(qf_widget)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background: #1a2535; max-height: 1px;")
        layout.addWidget(div)

        # Tag browser tree
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setColumnWidth(0, 155)
        self.tree.setColumnWidth(1, 45)
        self.tree.setIndentation(12)
        self.tree.setAnimated(True)
        self.tree.setRootIsDecorated(False)   # hide Qt's own branch arrows
        self.tree.setStyleSheet("""
            QTreeWidget { background: transparent; border: none; }
            QTreeWidget::item { padding: 3px 6px; border-radius: 3px; }
            QTreeWidget::item:hover { background: #141e2c; }
            QTreeWidget::item:selected { background: #0e2a1a; color: #80ffb0;
                                         border-left: 2px solid #2abf60; }
            QTreeWidget::branch { background: transparent; width: 0px; }
        """)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemExpanded.connect(self._on_expanded)
        self.tree.itemCollapsed.connect(self._on_collapsed)
        layout.addWidget(self.tree, 1)

        # Show hidden checkbox
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(10, 6, 10, 8)
        self.hidden_cb = QCheckBox("Show hidden ROMs")
        self.hidden_cb.setStyleSheet("color: #445566; font-size: 11px;")
        self.hidden_cb.stateChanged.connect(
            lambda s: self.filter_changed.emit("hidden", s == Qt.CheckState.Checked.value)
        )
        footer_layout.addWidget(self.hidden_cb)
        layout.addWidget(footer)

    def populate(self, systems: list, genres: list, years: list):
        """Fill the tag browser with data from the library."""
        self.tree.clear()

        # ── Systems ────────────────────────────────────────
        sys_root = SectionHeader("SYSTEMS")
        for s in systems:
            item = TagItem(s["full_name"], s["count"], "system", s["name"])
            item.setForeground(0, QBrush(QColor(get_system_color(s["name"])).lighter(130)))
            item.setForeground(1, QBrush(QColor("#446655")))
            sys_root.addChild(item)
        self.tree.addTopLevelItem(sys_root)
        sys_root.setExpanded(True)

        # ── Genres ─────────────────────────────────────────
        if genres:
            genre_root = SectionHeader(f"GENRES  ({len(genres)})")
            for g in genres:
                name  = g["name"]  if isinstance(g, dict) else g
                count = g["count"] if isinstance(g, dict) else 0
                item = TagItem(name, count, "genre", name)
                item.setForeground(0, QBrush(QColor("#8899bb")))
                item.setForeground(1, QBrush(QColor("#446655")))
                genre_root.addChild(item)
            self.tree.addTopLevelItem(genre_root)
            genre_root.setExpanded(False)

        # ── Years ──────────────────────────────────────────
        if years:
            year_root = SectionHeader(f"RELEASE YEAR  ({len(years)})")
            for y in years:
                name  = y["name"]  if isinstance(y, dict) else y
                count = y["count"] if isinstance(y, dict) else 0
                item = TagItem(name, count, "year", name)
                item.setForeground(0, QBrush(QColor("#7788aa")))
                item.setForeground(1, QBrush(QColor("#446655")))
                year_root.addChild(item)
            self.tree.addTopLevelItem(year_root)
            year_root.setExpanded(False)

    def _on_expanded(self, item: QTreeWidgetItem):
        if isinstance(item, SectionHeader):
            item.set_expanded(True)

    def _on_collapsed(self, item: QTreeWidgetItem):
        if isinstance(item, SectionHeader):
            item.set_expanded(False)

    def _on_item_clicked(self, item: QTreeWidgetItem, col: int):
        if isinstance(item, SectionHeader):
            # Toggle expand/collapse on header click
            item.setExpanded(not item.isExpanded())
            return
        if not hasattr(item, "tag_type"):
            return
        self.filter_changed.emit(item.tag_type, item.tag_value)
        self.all_btn.setChecked(False)
        self.fav_btn.setChecked(False)

    def _quick_filter(self, which: str):
        self.tree.clearSelection()
        if which == "all":
            self.fav_btn.setChecked(False)
            self.all_btn.setChecked(True)
            self.filter_changed.emit("all", None)
        elif which == "favorites":
            self.all_btn.setChecked(False)
            self.fav_btn.setChecked(self.fav_btn.isChecked())
            self.filter_changed.emit("favorites", self.fav_btn.isChecked())
