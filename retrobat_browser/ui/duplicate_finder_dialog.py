"""
Duplicate ROM finder.

Groups ROMs on the same system whose base titles (stripped of parenthetical
tags like (USA), (En,Fr), (Rev 1), etc.) are sufficiently similar.
Presents each group so the user can tick which entries to DELETE and which
to keep, then deletes the ticked ones.
"""

import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QCheckBox, QSizePolicy,
    QProgressBar, QDialogButtonBox, QMessageBox, QSplitter,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView, QHeaderView,
    QToolButton, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QSize
from PyQt6.QtGui import QColor, QFont, QBrush, QPixmap

from ..core.models import RomEntry, get_system_color


# ── Title normalisation ────────────────────────────────────────────────────────

# Parenthetical / bracketed tags to strip before comparison
_STRIP_PARENS = re.compile(r'\s*[\(\[][^\)\]]*[\)\]]\s*')
# Punctuation/whitespace normalisation
_NORM_PUNCT   = re.compile(r"[^a-z0-9]+")


def _base_title(name: str) -> str:
    """
    Strip parenthetical region/language/revision tags and normalise to
    a lowercase alphanumeric key for fuzzy comparison.

    'Alfred Chicken (USA)'        → 'alfredchicken'
    'Mega Man 2 (USA, Europe)'    → 'megaman2'
    'Sonic The Hedgehog (Rev A)'  → 'sonicthehedgehog'
    """
    t = _STRIP_PARENS.sub(" ", name)
    t = _NORM_PUNCT.sub("", t.lower())
    return t.strip()


def _similarity(a: str, b: str) -> float:
    """
    Simple normalised edit-distance similarity in [0, 1].
    Returns 1.0 for identical strings, lower for more different.
    Fast enough for O(n²) over a few thousand ROMs.
    """
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    # Use longest-common-subsequence length as a cheap proxy
    la, lb = len(a), len(b)
    if la > 40 or lb > 40:
        # For long strings just check prefix/exact
        return 1.0 if a == b else (len(os.path.commonprefix([a, b])) / max(la, lb))
    # DP LCS
    prev = [0] * (lb + 1)
    for ca in a:
        curr = [0] * (lb + 1)
        for j, cb in enumerate(b, 1):
            curr[j] = prev[j-1] + 1 if ca == cb else max(curr[j-1], prev[j])
        prev = curr
    lcs = prev[lb]
    return (2 * lcs) / (la + lb)


import os


def find_duplicate_groups(
    entries: List[RomEntry],
    threshold: float = 0.85,
) -> List[List[RomEntry]]:
    """
    Return groups of 2+ ROMs on the same system whose normalised base
    titles are sufficiently similar (similarity ≥ threshold).

    Groups are sorted largest-first; within each group entries are sorted
    by name length (shortest = most likely "clean" version first).
    """
    # Bucket by system first — duplicates can only exist within a system
    by_system: Dict[str, List[RomEntry]] = {}
    for e in entries:
        by_system.setdefault(e.system, []).append(e)

    groups: List[List[RomEntry]] = []

    for system_entries in by_system.values():
        n = len(system_entries)
        if n < 2:
            continue

        # Pre-compute base titles
        bases = [_base_title(e.name) for e in system_entries]

        # Union-Find for grouping
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # O(n²) pairwise similarity — fast because base titles are short
        for i in range(n):
            for j in range(i + 1, n):
                if bases[i] == bases[j]:
                    union(i, j)
                elif _similarity(bases[i], bases[j]) >= threshold:
                    union(i, j)

        # Collect groups
        buckets: Dict[int, List[RomEntry]] = {}
        for i, e in enumerate(system_entries):
            buckets.setdefault(find(i), []).append(e)

        for group in buckets.values():
            if len(group) >= 2:
                group.sort(key=lambda e: len(e.name))
                groups.append(group)

    groups.sort(key=len, reverse=True)
    return groups


# ── Background scan thread ─────────────────────────────────────────────────────

class _ScanWorker(QThread):
    finished = pyqtSignal(list)   # list of groups

    def __init__(self, entries: List[RomEntry], threshold: float = 0.85):
        super().__init__()
        self.entries   = entries
        self.threshold = threshold

    def run(self):
        groups = find_duplicate_groups(self.entries, self.threshold)
        self.finished.emit(groups)


# ── Main Dialog ────────────────────────────────────────────────────────────────

class DuplicateFinderDialog(QDialog):
    """
    Shows duplicate groups.  User ticks which entries to DELETE; unticked
    entries are kept.  Emits deleted_entries(list[RomEntry]) on confirm.
    """

    deleted_entries = pyqtSignal(list)

    _MENU_STYLE = """
        QMenu {
            background: #0e1824; color: #9ab0cc;
            border: 1px solid #2a3a55; padding: 4px 0; font-size: 12px;
        }
        QMenu::item { padding: 5px 20px; }
        QMenu::item:selected { background: #1a2a40; color: #c8ffd0; }
    """

    def __init__(self, all_entries: List[RomEntry], parent=None):
        super().__init__(parent)
        self.all_entries = all_entries
        self._groups: List[List[RomEntry]] = []
        # maps entry id → QTreeWidgetItem for fast lookup
        self._item_map: Dict[int, QTreeWidgetItem] = {}

        self.setWindowTitle("Find Duplicate ROMs")
        self.setMinimumSize(860, 620)
        self.resize(1000, 700)
        self._build_ui()
        self._start_scan()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QLabel(
            "  🔍  Duplicate ROM Finder\n"
            "  ROMs on the same system with similar base titles (ignoring region/language tags) are grouped below.\n"
            "  Tick the entries you want to DELETE, leave unticked to keep.  At least one entry per group must remain."
        )
        hdr.setStyleSheet("""
            QLabel {
                background: #0a1020; color: #7a9abb;
                font-size: 11px; padding: 10px 14px;
                border-bottom: 1px solid #1a2535;
            }
        """)
        outer.addWidget(hdr)

        # ── Toolbar ───────────────────────────────────────────────────────────
        tb = QHBoxLayout()
        tb.setContentsMargins(10, 6, 10, 6)
        tb.setSpacing(8)

        self._status_lbl = QLabel("Scanning…")
        self._status_lbl.setStyleSheet("color: #40c070; font-size: 12px; font-weight: bold;")

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate
        self._progress.setFixedHeight(12)
        self._progress.setMaximumWidth(180)
        self._progress.setStyleSheet(
            "QProgressBar { border: 1px solid #2a3a55; border-radius: 3px; background: #0c1018; }"
            "QProgressBar::chunk { background: #2a9a5a; border-radius: 2px; }"
        )

        def _tbtn(text, tip, slot):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFixedHeight(26)
            b.setStyleSheet("""
                QPushButton {
                    background: #101820; border: 1px solid #2a3a55;
                    border-radius: 4px; padding: 0 10px;
                    color: #8899bb; font-size: 11px;
                }
                QPushButton:hover { background: #162030; border-color: #2a9a5a; color: #c8ffd0; }
                QPushButton:disabled { color: #2a3a55; border-color: #1a2030; }
            """)
            b.clicked.connect(slot)
            return b

        self._btn_select_older  = _tbtn("Select Older Versions",
            "Auto-tick all entries except the shortest (cleanest) name in each group",
            self._auto_select_older)
        self._btn_select_all    = _tbtn("Select All",    "Tick every entry in every group", self._select_all)
        self._btn_select_none   = _tbtn("Select None",   "Untick everything", self._select_none)
        self._btn_expand_all    = _tbtn("Expand All",    "Expand all groups", self._expand_all)
        self._btn_collapse_all  = _tbtn("Collapse All",  "Collapse all groups", self._collapse_all)

        for w in (self._status_lbl, self._progress,
                  self._btn_select_older, self._btn_select_all,
                  self._btn_select_none, self._btn_expand_all,
                  self._btn_collapse_all):
            tb.addWidget(w)
        tb.addStretch()

        tb_frame = QFrame()
        tb_frame.setStyleSheet("QFrame { background: #0c1018; border-bottom: 1px solid #1a2535; }")
        tb_frame.setLayout(tb)
        outer.addWidget(tb_frame)

        # ── Tree ──────────────────────────────────────────────────────────────
        self._tree = QTreeWidget()
        self._tree.setColumnCount(5)
        self._tree.setHeaderLabels(["Delete?", "Name", "System", "Size", "File"])
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setDefaultSectionSize(100)
        self._tree.setColumnWidth(0, 64)
        self._tree.setColumnWidth(2, 120)
        self._tree.setColumnWidth(3, 70)
        self._tree.setColumnWidth(4, 220)
        self._tree.setAlternatingRowColors(True)
        self._tree.setUniformRowHeights(True)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._tree.setRootIsDecorated(True)
        self._tree.setStyleSheet("""
            QTreeWidget {
                background: #0c1018; alternate-background-color: #0e1420;
                color: #9ab0cc; border: none; font-size: 12px;
            }
            QTreeWidget::item { padding: 3px 0; }
            QTreeWidget::item:hover { background: #141e2c; }
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                image: url(none); border-image: none;
            }
        """)
        outer.addWidget(self._tree, 1)

        # ── Footer ────────────────────────────────────────────────────────────
        foot = QHBoxLayout()
        foot.setContentsMargins(12, 8, 12, 12)
        foot.setSpacing(8)

        self._del_lbl = QLabel("0 ROMs marked for deletion")
        self._del_lbl.setStyleSheet("color: #ff7070; font-size: 12px;")

        self._btn_delete = QPushButton("🗑  Delete Marked ROMs")
        self._btn_delete.setEnabled(False)
        self._btn_delete.setFixedHeight(30)
        self._btn_delete.setStyleSheet("""
            QPushButton {
                background: #2a0808; border: 1px solid #7a1010; border-radius: 4px;
                color: #ff7070; font-size: 12px; padding: 0 14px;
            }
            QPushButton:hover { background: #3a1010; border-color: #cc2222; color: #ffaaaa; }
            QPushButton:disabled { background: #111820; border-color: #1a2535; color: #2a3a55; }
        """)
        self._btn_delete.clicked.connect(self._on_delete)

        btn_close = QPushButton("Close")
        btn_close.setFixedHeight(30)
        btn_close.setStyleSheet("""
            QPushButton {
                background: #101820; border: 1px solid #2a3a55; border-radius: 4px;
                color: #8899bb; font-size: 12px; padding: 0 14px;
            }
            QPushButton:hover { background: #162030; color: #c8ffd0; }
        """)
        btn_close.clicked.connect(self.accept)

        foot.addWidget(self._del_lbl)
        foot.addStretch()
        foot.addWidget(self._btn_delete)
        foot.addWidget(btn_close)
        outer.addLayout(foot)

        self._set_buttons_enabled(False)

    # ── Scan ──────────────────────────────────────────────────────────────────

    def _start_scan(self):
        self._worker = _ScanWorker(self.all_entries)
        self._worker.finished.connect(self._on_scan_done)
        self._worker.start()

    def _on_scan_done(self, groups: List[List[RomEntry]]):
        self._groups = groups
        self._progress.setRange(0, 1)
        self._progress.setValue(1)
        self._progress.setVisible(False)
        self._populate_tree(groups)
        total_dups = sum(len(g) for g in groups)
        self._status_lbl.setText(
            f"{len(groups)} duplicate group{'s' if len(groups) != 1 else ''} "
            f"· {total_dups} ROMs" if groups
            else "No duplicates found 🎉"
        )
        self._set_buttons_enabled(bool(groups))

    # ── Tree population ───────────────────────────────────────────────────────

    def _populate_tree(self, groups: List[List[RomEntry]]):
        self._tree.clear()
        self._item_map.clear()

        for g_idx, group in enumerate(groups):
            system = group[0].system
            color  = get_system_color(system)

            base = _base_title(group[0].name)

            # Group header row
            header = QTreeWidgetItem(self._tree)
            header.setText(1, f'{group[0].system_full_name}  \u2014  "{base}"  ({len(group)} versions)')
            header.setForeground(1, QBrush(QColor(color)))
            header.setFont(1, QFont("Segoe UI", 11, QFont.Weight.Bold))
            header.setFlags(header.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            header.setExpanded(True)

            for entry in group:
                child = QTreeWidgetItem(header)
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, Qt.CheckState.Unchecked)
                child.setText(1, entry.name)
                child.setText(2, entry.system_full_name)
                size_str = f"{entry.file_size_mb:.1f} MB" if entry.file_size_mb > 0 else "—"
                child.setData(3, Qt.ItemDataRole.DisplayRole, size_str)
                child.setText(4, entry.rom_path.name if entry.rom_path else "")
                child.setForeground(1, QBrush(QColor("#9ab0cc")))
                child.setForeground(2, QBrush(QColor(color).lighter(130)))
                child.setForeground(3, QBrush(QColor("#5a7a9a")))
                child.setForeground(4, QBrush(QColor("#3a5570")))
                child.setData(0, Qt.ItemDataRole.UserRole, entry)
                self._item_map[id(entry)] = child

        self._tree.itemChanged.connect(self._on_item_changed)
        self._update_delete_count()

    # ── Check-state helpers ───────────────────────────────────────────────────

    def _on_item_changed(self, item: QTreeWidgetItem, col: int):
        if col != 0:
            return
        self._update_delete_count()

    def _update_delete_count(self):
        marked = self._get_marked_entries()
        n = len(marked)
        self._del_lbl.setText(
            f"{n} ROM{'s' if n != 1 else ''} marked for deletion"
        )
        self._del_lbl.setStyleSheet(
            f"color: {'#ff7070' if n > 0 else '#3a5570'}; font-size: 12px;"
        )
        self._btn_delete.setEnabled(n > 0)

    def _get_marked_entries(self) -> List[RomEntry]:
        """Return all entries whose checkbox is ticked."""
        marked = []
        root = self._tree.invisibleRootItem()
        for gi in range(root.childCount()):
            group_item = root.child(gi)
            checked = []
            total   = group_item.childCount()
            for ci in range(total):
                child = group_item.child(ci)
                entry = child.data(0, Qt.ItemDataRole.UserRole)
                if child.checkState(0) == Qt.CheckState.Checked:
                    checked.append(entry)
            # Safety: if all entries in a group are ticked, auto-untick the first one
            if len(checked) == total and total > 0:
                first_child = group_item.child(0)
                self._tree.itemChanged.disconnect(self._on_item_changed)
                first_child.setCheckState(0, Qt.CheckState.Unchecked)
                self._tree.itemChanged.connect(self._on_item_changed)
                checked = checked[1:]   # first entry is no longer marked
            marked.extend(checked)
        return marked

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _set_check_all(self, state: Qt.CheckState):
        self._tree.itemChanged.disconnect(self._on_item_changed)
        root = self._tree.invisibleRootItem()
        for gi in range(root.childCount()):
            group_item = root.child(gi)
            for ci in range(group_item.childCount()):
                group_item.child(ci).setCheckState(0, state)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._update_delete_count()

    def _select_all(self):
        self._set_check_all(Qt.CheckState.Checked)
        # Safety: re-run get_marked so the first-child guard fires
        self._update_delete_count()

    def _select_none(self):
        self._set_check_all(Qt.CheckState.Unchecked)

    def _auto_select_older(self):
        """Tick everything EXCEPT the first (shortest-name, likely cleanest) entry per group."""
        self._tree.itemChanged.disconnect(self._on_item_changed)
        root = self._tree.invisibleRootItem()
        for gi in range(root.childCount()):
            group_item = root.child(gi)
            for ci in range(group_item.childCount()):
                child = group_item.child(ci)
                # First child = shortest name = keep; rest = mark for deletion
                child.setCheckState(0,
                    Qt.CheckState.Unchecked if ci == 0 else Qt.CheckState.Checked)
        self._tree.itemChanged.connect(self._on_item_changed)
        self._update_delete_count()

    def _expand_all(self):
        self._tree.expandAll()

    def _collapse_all(self):
        self._tree.collapseAll()

    def _set_buttons_enabled(self, enabled: bool):
        for btn in (self._btn_select_older, self._btn_select_all,
                    self._btn_select_none, self._btn_expand_all,
                    self._btn_collapse_all):
            btn.setEnabled(enabled)

    # ── Delete ────────────────────────────────────────────────────────────────

    def _on_delete(self):
        to_delete = self._get_marked_entries()
        if not to_delete:
            return

        names = "\n".join(f"  • {e.name}  ({e.system})" for e in to_delete[:12])
        if len(to_delete) > 12:
            names += f"\n  … and {len(to_delete) - 12} more"

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(to_delete)} ROM(s) and all associated media files?\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        from .main_window import _delete_rom
        deleted, errors = [], []
        for entry in to_delete:
            try:
                _delete_rom(entry)
                deleted.append(entry)
            except Exception as e:
                errors.append(f"{entry.name}: {e}")

        if errors:
            QMessageBox.warning(self, "Delete Errors",
                f"{len(errors)} ROM(s) could not be fully deleted:\n" +
                "\n".join(errors[:8]))

        self.deleted_entries.emit(deleted)

        # Remove deleted items from the tree
        for entry in deleted:
            item = self._item_map.pop(id(entry), None)
            if item:
                parent = item.parent()
                if parent:
                    parent.removeChild(item)
                    # If group is now a single entry, remove the whole group
                    if parent.childCount() <= 1:
                        idx = self._tree.indexOfTopLevelItem(parent)
                        if idx >= 0:
                            self._tree.takeTopLevelItem(idx)

        self._update_delete_count()

        # Update group count in status
        remaining = sum(
            1 for i in range(self._tree.topLevelItemCount())
            if self._tree.topLevelItem(i).childCount() > 1
        )
        self._status_lbl.setText(
            f"{remaining} duplicate group{'s' if remaining != 1 else ''} remaining"
            if remaining else "All duplicates resolved 🎉"
        )
