"""
Main application window — Calibre-inspired 3-pane layout.
"""

from pathlib import Path
from typing import Optional, List

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QStackedWidget,
    QFileDialog, QMessageBox, QApplication, QLabel,
    QVBoxLayout, QHBoxLayout, QDialog, QDialogButtonBox,
    QCheckBox, QLineEdit, QPushButton, QStatusBar, QToolBar, QFrame, QMenu
)
from PyQt6.QtCore import Qt, QSize, QThread, pyqtSlot, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QFont

from ..core.library import Library
from ..core.settings import Settings
from ..core.models import RomEntry
from .sidebar import SidebarPanel
from .grid_view import GridView
from .list_view import ListView
from .detail_panel import DetailPanel
from .toolbar import MainToolbar
from .loading import LoadWorker, LoadingDialog
from .styles import DARK_STYLE
from .edit_dialog import EditDialog
from .batch_edit_dialog import BatchEditDialog
from .duplicate_finder_dialog import DuplicateFinderDialog
from .grouped_view import GroupedView
from .full_detail_view import FullDetailView
from .rental_shop import VirtualRentalShopPanel
from .sync_dialog import SyncDialog


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("RetroBat ROM Browser")
        self.setMinimumSize(1000, 650)

        self._settings = Settings()
        self._library  = Library()
        self._worker: Optional[LoadWorker] = None
        self._loading_dlg: Optional[LoadingDialog] = None
        self._current_selection: List[RomEntry] = []
        self._prev_stack_index: int = 0   # remembers which view was shown before full-detail

        self._refresh_timer = QTimer()
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(50)
        self._refresh_timer.timeout.connect(self._do_refresh)

        self._build_ui()
        self._build_menus()
        self._restore_geometry()

        last = self._settings.roms_root
        if last and Path(last).exists():
            self._load_library(Path(last))
        else:
            self._show_welcome()

    # ── UI Construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        # Main toolbar
        self._toolbar = MainToolbar(self)
        self.addToolBar(self._toolbar)
        self._toolbar.search_changed.connect(self._on_search)
        self._toolbar.view_grid.connect(self._show_grid)
        self._toolbar.view_list.connect(self._show_list)
        self._toolbar.view_rental.connect(self._show_rental)
        self._toolbar.grid_size_changed.connect(self._on_grid_size)
        self._toolbar.sort_changed.connect(self._on_sort)
        self._toolbar.refresh_requested.connect(self._on_refresh)

        # Bulk-action toolbar (shown when selection > 0)
        self._bulk_bar = QToolBar("Selection Actions", self)
        self._bulk_bar.setMovable(False)
        self._bulk_bar.setStyleSheet("""
            QToolBar {
                background: #0a1820;
                border-top: 1px solid #1a3040;
                border-bottom: 1px solid #1a3040;
                padding: 3px 8px;
                spacing: 6px;
            }
        """)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._bulk_bar)

        self._bulk_lbl = QLabel("0 selected")
        self._bulk_lbl.setStyleSheet("color: #40c070; font-size: 12px; font-weight: bold; padding: 0 8px;")
        self._bulk_bar.addWidget(self._bulk_lbl)

        def _bulk_btn(text, tip, slot, danger=False):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFixedHeight(26)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {'#2a0808' if danger else '#101820'};
                    border: 1px solid {'#6a1010' if danger else '#2a3a55'};
                    border-radius: 4px; padding: 0 10px;
                    color: {'#ff7070' if danger else '#8899bb'};
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: {'#3a1010' if danger else '#162030'};
                    border-color: {'#cc2222' if danger else '#2a9a5a'};
                    color: {'#ffaaaa' if danger else '#c8ffd0'};
                }}
            """)
            b.clicked.connect(slot)
            return b

        self._bulk_bar.addWidget(_bulk_btn("⇄ Sync Selected",   "Copy to external device",
                                           self._on_bulk_sync))
        self._bulk_bar.addWidget(_bulk_btn("✕ Delete Selected", "Delete ROMs and media",
                                           self._on_bulk_delete, danger=True))

        spacer = QWidget(); spacer.setFixedWidth(8)
        self._bulk_bar.addWidget(spacer)
        self._bulk_bar.addWidget(_bulk_btn("✕ Clear Selection", "Deselect all",
                                           self._on_clear_selection))

        self._bulk_bar.setVisible(False)

        # Central splitter
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(3)

        self._sidebar = SidebarPanel()
        self._sidebar.filter_changed.connect(self._on_filter)
        self._splitter.addWidget(self._sidebar)

        self._stack = QStackedWidget()
        self._grid_view = GridView()
        self._list_view = ListView()
        self._grouped_view = GroupedView()
        self._full_detail = FullDetailView()
        self._rental_panel = VirtualRentalShopPanel()
        self._stack.addWidget(self._grid_view)     # index 0
        self._stack.addWidget(self._list_view)     # index 1
        self._stack.addWidget(self._grouped_view)  # index 2
        self._stack.addWidget(self._full_detail)   # index 3
        self._stack.addWidget(self._rental_panel)  # index 4
        self._splitter.addWidget(self._stack)

        self._grid_view.entry_selected.connect(self._on_entry_selected)
        self._grid_view.selection_changed.connect(self._on_selection_changed)
        self._grid_view.context_menu_requested.connect(self._show_context_menu)
        self._grid_view.entry_activated.connect(self._on_entry_activated)
        self._list_view.entry_selected.connect(self._on_entry_selected)
        self._list_view.selection_changed.connect(self._on_selection_changed)
        self._list_view.context_menu_requested.connect(self._show_context_menu)
        self._list_view.entry_activated.connect(self._on_entry_activated)
        self._grouped_view.entry_selected.connect(self._on_entry_selected)
        self._grouped_view.selection_changed.connect(self._on_selection_changed)
        self._grouped_view.context_menu_requested.connect(self._show_context_menu)
        self._grouped_view.entry_activated.connect(self._on_entry_activated)
        self._rental_panel.entry_selected.connect(self._on_entry_selected)
        self._rental_panel.entry_activated.connect(self._on_entry_activated)
        self._rental_panel.selection_changed.connect(self._on_selection_changed)

        self._full_detail.close_requested.connect(self._on_full_detail_close)
        self._full_detail.edit_requested.connect(self._on_edit)
        self._full_detail.delete_requested.connect(lambda e: self._delete_entries([e]))
        self._full_detail.sync_requested.connect(self._on_sync)
        self._full_detail.image_changed.connect(self._on_image_changed)

        self._detail = DetailPanel()
        self._detail.edit_requested.connect(self._on_edit)
        self._detail.delete_requested.connect(lambda e: self._delete_entries([e]))
        self._detail.sync_requested.connect(self._on_sync)
        self._splitter.addWidget(self._detail)

        sl = self._settings.get("splitter_left", 220)
        sd = self._settings.get("splitter_detail", 320)
        self._splitter.setSizes([sl, 1400 - sl - sd, sd])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)

        self.setCentralWidget(self._splitter)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status_label = QLabel("No library loaded.  Use  File → Open Library  to get started.")
        self._status_label.setStyleSheet("color: #4a6688;")
        self._status.addWidget(self._status_label)

        vm = self._settings.get("view_mode", "grid")
        if vm == "list":
            self._show_list()
            self._toolbar.set_view_mode("list")
        else:
            self._show_grid()

    def _build_menus(self):
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")
        open_act = QAction("&Open Library…", self); open_act.setShortcut("Ctrl+O")
        open_act.triggered.connect(self._on_open_library); file_menu.addAction(open_act)
        refresh_act = QAction("&Refresh Library", self); refresh_act.setShortcut("F5")
        refresh_act.triggered.connect(self._on_refresh); file_menu.addAction(refresh_act)
        self._recent_menu = file_menu.addMenu("Recent Libraries")
        self._rebuild_recent_menu()
        file_menu.addSeparator()
        quit_act = QAction("&Quit", self); quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close); file_menu.addAction(quit_act)

        # Edit
        edit_menu = mb.addMenu("&Edit")
        edit_act = QAction("&Edit Metadata…", self); edit_act.setShortcut("Ctrl+E")
        edit_act.triggered.connect(lambda: self._on_edit(self._current_selection)
                                   if self._current_selection else None)
        edit_menu.addAction(edit_act)
        edit_menu.addSeparator()
        sync_act = QAction("S&ync Selected…", self)
        sync_act.triggered.connect(self._on_bulk_sync); edit_menu.addAction(sync_act)
        edit_menu.addSeparator()
        del_act = QAction("&Delete ROM(s)…", self); del_act.setShortcut("Delete")
        del_act.triggered.connect(self._on_bulk_delete); edit_menu.addAction(del_act)
        selall_act = QAction("Select &All", self); selall_act.setShortcut("Ctrl+A")
        selall_act.triggered.connect(self._on_select_all); edit_menu.addAction(selall_act)

        # View
        view_menu = mb.addMenu("&View")
        for text, shortcut, slot in [
            ("Cover &Grid", "Ctrl+G", self._show_grid),
            ("&List View",  "Ctrl+L", self._show_list),
        ]:
            a = QAction(text, self); a.setShortcut(shortcut)
            a.triggered.connect(slot); view_menu.addAction(a)
        view_menu.addSeparator()
        for text, size in [("Small Covers","small"),("Medium Covers","medium"),("Large Covers","large")]:
            a = QAction(text, self)
            a.triggered.connect(lambda _, s=size: self._on_grid_size(s))
            view_menu.addAction(a)

        # Tools
        tools_menu = mb.addMenu("&Tools")
        dup_act = QAction("🔍  Find Duplicate ROMs…", self)
        dup_act.setShortcut("Ctrl+D")
        dup_act.triggered.connect(self._on_find_duplicates)
        tools_menu.addAction(dup_act)
        tools_menu.addSeparator()
        rental_act = QAction("🎮  Virtual Rental Shop…", self)
        rental_act.setShortcut("Ctrl+R")
        rental_act.triggered.connect(self._show_rental)
        tools_menu.addAction(rental_act)

        # Help
        help_menu = mb.addMenu("&Help")
        about_act = QAction("&About", self)
        about_act.triggered.connect(self._on_about)
        help_menu.addAction(about_act)

    def _rebuild_recent_menu(self):
        self._recent_menu.clear()
        for path in self._settings.get("recent_libraries", []):
            act = QAction(path, self)
            act.triggered.connect(lambda checked, p=path: self._load_library(Path(p)))
            self._recent_menu.addAction(act)

    # ── Library Loading ────────────────────────────────────────────────────────

    def _on_open_library(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select RetroBat ROMs Folder",
            self._settings.roms_root or str(Path.home()),
            QFileDialog.Option.ShowDirsOnly,
        )
        if path:
            self._load_library(Path(path))

    def _load_library(self, roms_root: Path):
        if not roms_root.exists():
            QMessageBox.warning(self, "Not Found", f"Path does not exist:\n{roms_root}")
            return
        self._settings.roms_root = str(roms_root)
        self._settings.save()
        self._rebuild_recent_menu()

        self._loading_dlg = LoadingDialog(self)
        self._worker = LoadWorker(roms_root, self._settings.get("show_hidden", False))
        self._worker.progress.connect(self._loading_dlg.update_progress)
        self._worker.finished.connect(self._on_load_finished)
        self._worker.error.connect(self._on_load_error)
        self._loading_dlg.cancelled.connect(self._worker.terminate)
        self._loading_dlg.cancelled.connect(self._loading_dlg.close)
        self._worker.start()
        self._loading_dlg.exec()

    @pyqtSlot(list)
    def _on_load_finished(self, entries):
        if self._loading_dlg:
            self._loading_dlg.close(); self._loading_dlg = None
        self._library._all_entries = entries
        self._library.roms_root = Path(self._settings.roms_root)
        self._sidebar.populate(self._library.get_systems(),
                               self._library.get_genres(),
                               self._library.get_years())
        for attr in ("filter_system","filter_genre","filter_year","filter_search","filter_favorites_only"):
            setattr(self._library, attr, None if "filter_" in attr else False if "only" in attr else "")
        self._library.filter_search = ""
        self._library.filter_favorites_only = False
        self._refresh_view()
        s = self._library.get_stats()
        self._status_label.setText(
            f"  {s['total']:,} ROMs  ·  {s['systems']} systems  ·  "
            f"{s['with_images']:,} with cover art  ·  {s['total_size_gb']:.1f} GB"
        )

    @pyqtSlot(str)
    def _on_load_error(self, msg):
        if self._loading_dlg: self._loading_dlg.close()
        QMessageBox.critical(self, "Load Error", f"Failed to load library:\n{msg}")

    def _on_refresh(self):
        if self._settings.roms_root:
            self._load_library(Path(self._settings.roms_root))

    # ── Filters & Refresh ─────────────────────────────────────────────────────

    def _on_filter(self, filter_type: str, value):
        if filter_type == "system":
            self._library.filter_system = value
            self._library.filter_genre = None
            self._library.filter_year = None
        elif filter_type == "genre":
            self._library.filter_genre = value
            self._library.filter_system = None
        elif filter_type == "year":
            self._library.filter_year = value
            self._library.filter_system = None
        elif filter_type == "all":
            self._library.filter_system = None
            self._library.filter_genre = None
            self._library.filter_year = None
            self._library.filter_favorites_only = False
        elif filter_type == "favorites":
            self._library.filter_favorites_only = bool(value)
            self._library.filter_system = None
        elif filter_type == "hidden":
            self._settings.set("show_hidden", bool(value))
            self._on_refresh(); return
        self._refresh_view()

    def _on_search(self, text):
        self._library.filter_search = text
        self._refresh_view()

    def _on_sort(self, field, reverse):
        self._library.sort_field = field
        self._library.sort_reverse = reverse
        self._settings.set("sort_field", field)
        self._settings.set("sort_reverse", reverse)
        self._refresh_view()

    def _refresh_view(self):
        self._refresh_timer.start()

    def _do_refresh(self):
        entries = self._library.get_filtered()
        self._toolbar.set_count(len(entries))
        self._detail.show_empty()

        # Use grouped view when filtering by genre or year (not system)
        use_grouped = (
            (self._library.filter_genre or self._library.filter_year)
            and not self._library.filter_system
        )

        if use_grouped:
            self._stack.setCurrentIndex(2)
            self._grouped_view.populate(entries)
        else:
            view_mode = self._settings.get("view_mode", "grid")
            if view_mode == "list":
                self._stack.setCurrentIndex(1)
                self._list_view.populate(entries)
            else:
                self._stack.setCurrentIndex(0)
                self._grid_view.populate(entries)

    # ── Selection ─────────────────────────────────────────────────────────────

    def _on_entry_selected(self, entry: RomEntry):
        self._detail.show_entry(entry)

    def _on_selection_changed(self, entries: List[RomEntry]):
        self._current_selection = entries
        n = len(entries)
        self._bulk_bar.setVisible(n > 0)
        if n == 1:
            self._bulk_lbl.setText("1 ROM selected")
            self._detail.show_entry(entries[0])
        elif n > 1:
            self._bulk_lbl.setText(f"{n} ROMs selected")

    def _on_entry_activated(self, entry: RomEntry):
        """Double-click: switch to Steam-style full detail view."""
        cur = self._stack.currentIndex()
        if cur != 3:   # 3 = full_detail itself
            self._prev_stack_index = cur
        entries = self._library.get_filtered()
        # If coming from rental panel, use shop entries as the browsable list
        if self._prev_stack_index == 4:
            entries = self._rental_panel._shop_entries or entries
        self._full_detail.show_entry(entry, entries)
        self._stack.setCurrentIndex(3)
        self._splitter.widget(0).hide()
        self._splitter.widget(2).hide()

    def _on_full_detail_close(self):
        """Return from full detail view back to the library."""
        self._stack.setCurrentIndex(self._prev_stack_index)
        self._restore_panels()
        # Restore toolbar checked state
        if self._prev_stack_index == 4:
            self._toolbar.set_view_mode("rental")
        elif self._prev_stack_index == 1:
            self._toolbar.set_view_mode("list")
        else:
            self._toolbar.set_view_mode(self._settings.get("view_mode", "grid"))

    def _on_clear_selection(self):
        self._grid_view.clear_selection()
        self._list_view.clearSelection()
        self._current_selection = []
        self._bulk_bar.setVisible(False)

    def _on_select_all(self):
        if self._stack.currentIndex() == 0:
            entries = self._library.get_filtered()
            self._grid_view._selection = set(range(len(entries)))
            self._grid_view.viewport().update()
            self._current_selection = entries
            self._bulk_lbl.setText(f"{len(entries)} ROMs selected")
            self._bulk_bar.setVisible(bool(entries))
        else:
            self._list_view.selectAll()

    # ── View Mode ─────────────────────────────────────────────────────────────

    def _restore_panels(self):
        """Ensure sidebar and detail panel are visible (undo full-detail hide)."""
        self._splitter.widget(0).show()
        self._splitter.widget(2).show()

    def _show_grid(self):
        self._restore_panels()
        self._settings.set("view_mode", "grid")
        self._toolbar.set_view_mode("grid")
        self._do_refresh()

    def _show_list(self):
        self._restore_panels()
        self._settings.set("view_mode", "list")
        self._toolbar.set_view_mode("list")
        self._do_refresh()

    def _show_rental(self):
        """Switch main panel to the Virtual Rental Shop."""
        self._restore_panels()
        all_entries = self._library.get_all()
        if not all_entries:
            QMessageBox.information(self, "No Library",
                "Open a ROM library first (File → Open Library).")
            self._toolbar.set_view_mode(self._settings.get("view_mode", "grid"))
            return
        self._rental_panel.load(all_entries)
        self._stack.setCurrentIndex(4)
        self._toolbar.set_view_mode("rental")

    def _on_grid_size(self, size):
        self._grid_view.set_grid_size(size)
        self._settings.set("grid_size", size)

    # ── Context menu ──────────────────────────────────────────────────────────

    def _show_context_menu(self, entries: List[RomEntry]):
        """Build and show a right-click context menu for the given entries."""
        n = len(entries)
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #0e1824; color: #9ab0cc;
                border: 1px solid #2a3a55; padding: 4px 0;
                font-size: 12px;
            }
            QMenu::item { padding: 5px 24px 5px 14px; }
            QMenu::item:selected { background: #1a2a40; color: #c8ffd0; }
            QMenu::separator { height: 1px; background: #1a2535; margin: 3px 0; }
        """)

        label = f"{n} ROM{'s' if n != 1 else ''}"

        # Edit metadata
        if n == 1:
            act_edit = menu.addAction(f"✏  Edit Metadata — {entries[0].name}")
            act_edit.triggered.connect(lambda: self._on_edit(entries))
        else:
            edit_menu = menu.addMenu(f"✏  Edit Metadata — {label}")
            edit_menu.setStyleSheet(menu.styleSheet())
            act_each = edit_menu.addAction("Edit Each Individually…")
            act_each.triggered.connect(lambda: self._on_edit_each(entries))
            act_batch = edit_menu.addAction("Batch Edit (shared fields)…")
            act_batch.triggered.connect(lambda: self._on_batch_edit(entries))

        # Change images (single ROM only)
        if n == 1:
            menu.addSeparator()
            act_box = menu.addAction("🖼  Change Box Art…")
            act_box.triggered.connect(lambda: self._on_change_box_art(entries[0]))
            act_hero = menu.addAction("🖼  Change Hero / Background…")
            act_hero.triggered.connect(lambda: self._on_change_hero_image(entries[0]))

        menu.addSeparator()

        # Open file location
        if n == 1:
            act_loc = menu.addAction("📂  Open File Location")
            act_loc.triggered.connect(lambda: self._on_open_file_location(entries[0]))
            menu.addSeparator()

        act_sync = menu.addAction(f"⇄  Sync to Device — {label}")
        act_sync.triggered.connect(lambda: self._on_sync(entries))

        menu.addSeparator()

        act_fav = menu.addAction("★  Mark as Favourite")
        act_fav.triggered.connect(lambda: self._set_flag(entries, "favorite", True))
        act_unfav = menu.addAction("☆  Remove Favourite")
        act_unfav.triggered.connect(lambda: self._set_flag(entries, "favorite", False))

        act_hide = menu.addAction("◉  Hide from Library")
        act_hide.triggered.connect(lambda: self._set_flag(entries, "hidden", True))
        act_show = menu.addAction("○  Unhide")
        act_show.triggered.connect(lambda: self._set_flag(entries, "hidden", False))

        menu.addSeparator()

        act_del = menu.addAction(f"✕  Delete {label}…")
        act_del.triggered.connect(lambda: self._delete_entries(entries))

        menu.exec(self.cursor().pos())

    # ── Edit ──────────────────────────────────────────────────────────────────

    def _on_edit(self, entries_or_entry):
        """Called from detail panel (single RomEntry) or context menu (list)."""
        if isinstance(entries_or_entry, RomEntry):
            entries = [entries_or_entry]
        else:
            entries = list(entries_or_entry)

        if len(entries) == 1:
            dlg = EditDialog(entries[0], self)
            dlg.metadata_saved.connect(lambda e: self._detail.show_entry(e))
            dlg.exec()
        else:
            # Ask: edit each individually or batch?
            msg = QMessageBox(self)
            msg.setWindowTitle("Edit Multiple ROMs")
            msg.setText(f"You have {len(entries)} ROMs selected.\nHow would you like to edit them?")
            btn_each  = msg.addButton("Edit Each Individually", QMessageBox.ButtonRole.AcceptRole)
            btn_batch = msg.addButton("Batch Edit (shared fields)", QMessageBox.ButtonRole.ActionRole)
            msg.addButton(QMessageBox.StandardButton.Cancel)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == btn_each:
                self._on_edit_each(entries)
            elif clicked == btn_batch:
                self._on_batch_edit(entries)

    def _on_edit_each(self, entries: List[RomEntry]):
        """Open EditDialog for each entry in sequence."""
        for entry in entries:
            dlg = EditDialog(entry, self)
            dlg.metadata_saved.connect(lambda e: self._detail.show_entry(e))
            result = dlg.exec()
            if result == QDialog.DialogCode.Rejected:
                # User cancelled — offer to stop
                if len(entries) > 1:
                    reply = QMessageBox.question(
                        self, "Stop Editing?",
                        "Stop editing the remaining ROMs?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        break

    def _on_batch_edit(self, entries: List[RomEntry]):
        """Open BatchEditDialog to apply shared field values to all entries."""
        dlg = BatchEditDialog(entries, self)
        dlg.batch_saved.connect(lambda saved: (
            self._detail.show_entry(saved[0]) if saved else None
        ))
        dlg.exec()

    def _set_flag(self, entries: List[RomEntry], attr: str, value):
        """Quick-set a boolean flag (favorite/hidden) on all selected entries."""
        from .edit_dialog import _write_gamelist_entry
        for entry in entries:
            setattr(entry, attr, value)
            try:
                _write_gamelist_entry(entry)
            except Exception:
                pass
        if entries:
            self._detail.show_entry(entries[-1])
        self._do_refresh()

    # ── Delete ────────────────────────────────────────────────────────────────

    def _on_bulk_delete(self):
        entries = self._current_selection or []
        if not entries:
            QMessageBox.information(self, "No Selection", "Select one or more ROMs first.")
            return
        self._delete_entries(entries)

    def _delete_entries(self, entries: List[RomEntry]):
        names = "\n".join(f"  • {e.name}" for e in entries[:10])
        if len(entries) > 10:
            names += f"\n  … and {len(entries)-10} more"
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Permanently delete {len(entries)} ROM(s) and all associated media?\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted, errors = 0, 0
        for entry in entries:
            try:
                _delete_rom(entry)
                self._library._all_entries.remove(entry)
                deleted += 1
            except Exception as e:
                errors += 1
                print(f"[WARN] Delete failed for {entry.name}: {e}")

        self._on_clear_selection()
        self._do_refresh()
        self._detail.show_empty()
        msg = f"Deleted {deleted} ROM(s)."
        if errors:
            msg += f"  {errors} error(s) — see console."
        self._status_label.setText(msg)

    # ── Sync ──────────────────────────────────────────────────────────────────

    def _on_sync(self, entries: List[RomEntry]):
        # If the triggered entry is part of a larger current selection, use all of it
        if len(entries) == 1 and entries[0] in self._current_selection:
            entries = self._current_selection
        if not entries:
            QMessageBox.information(self, "No Selection", "Select one or more ROMs to sync.")
            return
        dlg = SyncDialog(entries, self._settings, self)
        dlg.exec()

    def _on_bulk_sync(self):
        entries = self._current_selection or []
        if not entries:
            QMessageBox.information(self, "No Selection", "Select one or more ROMs first.")
            return
        self._on_sync(entries)

    # ── Image replacement (context menu) ─────────────────────────────────────

    def _on_change_box_art(self, entry: RomEntry):
        """Pick a new box art image for a ROM from the context menu."""
        from .full_detail_view import _replace_image, IMAGE_FILTER
        path, _ = QFileDialog.getOpenFileName(self, "Choose Box Art Image", "", IMAGE_FILTER)
        if not path:
            return
        if _replace_image(entry, "thumbnail", Path(path), self):
            self._on_image_changed(entry)

    def _on_change_hero_image(self, entry: RomEntry):
        """Pick a new hero/background screenshot for a ROM from the context menu."""
        from .full_detail_view import _replace_image, IMAGE_FILTER
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Hero / Background Image", "", IMAGE_FILTER)
        if not path:
            return
        if _replace_image(entry, "screenshot", Path(path), self):
            self._on_image_changed(entry)

    def _on_image_changed(self, entry: RomEntry):
        """Called after any image replacement — refresh grid and detail panel."""
        from .image_loader import IMAGE_CACHE
        IMAGE_CACHE.clear()
        self._do_refresh()
        self._detail.show_entry(entry)

    # ── Open file location ────────────────────────────────────────────────────

    def _on_open_file_location(self, entry: RomEntry):
        """Open the ROM's containing folder in the system file explorer."""
        import subprocess, sys
        if not entry.rom_path:
            QMessageBox.warning(self, "Unknown Path", "ROM file path is not set.")
            return
        folder = entry.rom_path.parent
        if not folder.exists():
            QMessageBox.warning(self, "Folder Not Found",
                                f"Folder does not exist:\n{folder}")
            return
        try:
            if sys.platform == "win32":
                # Select (highlight) the file itself in Explorer
                subprocess.Popen(["explorer", "/select,", str(entry.rom_path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as e:
            QMessageBox.warning(self, "Cannot Open Folder", str(e))

    def _on_find_duplicates(self):
        all_entries = self._library.get_all()
        if not all_entries:
            QMessageBox.information(self, "No Library",
                "Open a ROM library first (File → Open Library).")
            return
        dlg = DuplicateFinderDialog(all_entries, self)
        dlg.deleted_entries.connect(self._on_duplicates_deleted)
        dlg.exec()

    def _on_duplicates_deleted(self, deleted: List[RomEntry]):
        for entry in deleted:
            try:
                self._library._all_entries.remove(entry)
            except ValueError:
                pass
        self._on_clear_selection()
        self._do_refresh()
        self._detail.show_empty()
        self._status_label.setText(f"Deleted {len(deleted)} duplicate ROM(s).")

    def _show_welcome(self):
        self._grid_view.populate([])

    def _restore_geometry(self):
        w = self._settings.get("window_width", 1400)
        h = self._settings.get("window_height", 900)
        x = self._settings.get("window_x", -1)
        y = self._settings.get("window_y", -1)
        self.resize(w, h)
        if x >= 0 and y >= 0:
            self.move(x, y)

    def closeEvent(self, event):
        geo = self.geometry()
        self._settings.set("window_width", geo.width())
        self._settings.set("window_height", geo.height())
        self._settings.set("window_x", geo.x())
        self._settings.set("window_y", geo.y())
        sizes = self._splitter.sizes()
        if sizes:
            self._settings.set("splitter_left", sizes[0])
            self._settings.set("splitter_detail", sizes[2] if len(sizes) > 2 else 320)
        self._settings.save()
        super().closeEvent(event)

    def _on_about(self):
        QMessageBox.about(self, "About RetroBat ROM Browser",
            "<h3>RetroBat ROM Browser</h3><p>Version 1.3.0</p>"
            "<p>A Calibre-inspired ROM library manager for RetroBat / EmulationStation.</p>"
            "<p>Features: cover grid, list view, grouped genre/year view, "
            "Steam-style full detail view, Virtual Rental Shop, "
            "metadata editing, duplicate finder, sync to device.</p>"
        )


# ── Helper: delete a ROM from disk ────────────────────────────────────────────

def _delete_rom(entry: RomEntry):
    """Delete the ROM file, all its associated media, and its gamelist.xml entry."""
    import xml.etree.ElementTree as ET

    # Delete ROM file
    if entry.rom_path and entry.rom_path.exists():
        entry.rom_path.unlink()

    # Delete all media files
    for attr in ("image","thumbnail","marquee","screenshot","titleshot","video","manual","map"):
        p = getattr(entry, attr)
        if p and Path(p).exists():
            Path(p).unlink()

    # Remove from gamelist.xml
    if not entry.rom_path:
        return
    gamelist = entry.rom_path.parent / "gamelist.xml"
    if not gamelist.exists():
        return
    try:
        tree = ET.parse(str(gamelist))
        root = tree.getroot()
        for game in root.findall("game"):
            path_el = game.find("path")
            if path_el is not None and path_el.text:
                if entry.rom_path.name in path_el.text:
                    root.remove(game)
                    break
        ET.indent(tree, space="  ")
        tree.write(str(gamelist), encoding="utf-8", xml_declaration=True)
    except Exception as e:
        print(f"[WARN] Could not update gamelist.xml: {e}")
