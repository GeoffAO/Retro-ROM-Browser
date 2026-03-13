"""
Main toolbar — search bar, view toggles, sort options.
"""

from PyQt6.QtWidgets import (
    QToolBar, QLabel, QLineEdit, QComboBox,
    QToolButton, QWidget, QSizePolicy, QHBoxLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon, QFont


class SearchBar(QLineEdit):
    search_triggered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("  🔍  Search ROMs by title, developer, genre…")
        self.setMinimumWidth(280)
        self.setMaximumWidth(500)
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(lambda: self.search_triggered.emit(self.text()))
        self.textChanged.connect(lambda _: self._timer.start())


class MainToolbar(QToolBar):
    """Main application toolbar."""

    search_changed = pyqtSignal(str)
    view_grid = pyqtSignal()
    view_list = pyqtSignal()
    view_rental = pyqtSignal()
    grid_size_changed = pyqtSignal(str)
    sort_changed = pyqtSignal(str, bool)
    refresh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMovable(False)
        self.setFloatable(False)
        self._build()

    def _build(self):
        # Refresh button
        self.btn_refresh = QToolButton()
        self.btn_refresh.setText("⟳  Refresh")
        self.btn_refresh.setToolTip("Reload ROM library")
        self.btn_refresh.clicked.connect(self.refresh_requested)
        self.addWidget(self.btn_refresh)

        self.addSeparator()

        # View toggle
        self.btn_grid = QToolButton()
        self.btn_grid.setText("⊞  Grid")
        self.btn_grid.setCheckable(True)
        self.btn_grid.setChecked(True)
        self.btn_grid.setToolTip("Cover grid view")
        self.btn_grid.clicked.connect(self._on_grid)

        self.btn_list = QToolButton()
        self.btn_list.setText("☰  List")
        self.btn_list.setCheckable(True)
        self.btn_list.setToolTip("Table list view")
        self.btn_list.clicked.connect(self._on_list)

        self.btn_rental = QToolButton()
        self.btn_rental.setText("📼  Rental Shop")
        self.btn_rental.setCheckable(True)
        self.btn_rental.setToolTip("Virtual Rental Shop — discover random games")
        self.btn_rental.clicked.connect(self._on_rental)

        self.addWidget(self.btn_grid)
        self.addWidget(self.btn_list)
        self.addWidget(self.btn_rental)
        self.addSeparator()

        # Grid size
        size_lbl = QLabel(" Size: ")
        size_lbl.setStyleSheet("color: #556688; font-size: 12px;")
        self.addWidget(size_lbl)

        self.combo_size = QComboBox()
        self.combo_size.addItems(["Small", "Medium", "Large"])
        self.combo_size.setCurrentIndex(1)
        self.combo_size.setFixedWidth(90)
        self.combo_size.currentTextChanged.connect(
            lambda t: self.grid_size_changed.emit(t.lower())
        )
        self.addWidget(self.combo_size)
        self.addSeparator()

        # Sort
        sort_lbl = QLabel(" Sort: ")
        sort_lbl.setStyleSheet("color: #556688; font-size: 12px;")
        self.addWidget(sort_lbl)

        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["Name", "System", "Year", "Developer", "Publisher", "Genre", "Rating", "Play Count"])
        self.combo_sort.setFixedWidth(120)
        self.combo_sort.currentTextChanged.connect(self._emit_sort)
        self.addWidget(self.combo_sort)

        self.btn_sort_dir = QToolButton()
        self.btn_sort_dir.setText("▲")
        self.btn_sort_dir.setCheckable(True)
        self.btn_sort_dir.setToolTip("Reverse sort order")
        self.btn_sort_dir.clicked.connect(self._emit_sort)
        self.addWidget(self.btn_sort_dir)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)

        # Search
        self.search = SearchBar()
        self.search.search_triggered.connect(self.search_changed)
        self.addWidget(self.search)

        # Count label
        self.count_label = QLabel("  0 ROMs")
        self.count_label.setStyleSheet("color: #3a6a4a; font-size: 12px; margin-right: 8px;")
        self.addWidget(self.count_label)

    def set_count(self, n: int):
        self.count_label.setText(f"  {n:,} ROMs")

    def _on_grid(self):
        self.btn_list.setChecked(False)
        self.btn_rental.setChecked(False)
        self.btn_grid.setChecked(True)
        self.view_grid.emit()

    def _on_list(self):
        self.btn_grid.setChecked(False)
        self.btn_rental.setChecked(False)
        self.btn_list.setChecked(True)
        self.view_list.emit()

    def _on_rental(self):
        self.btn_grid.setChecked(False)
        self.btn_list.setChecked(False)
        self.btn_rental.setChecked(True)
        self.view_rental.emit()

    def _emit_sort(self):
        mapping = {
            "Name": "name", "System": "system", "Year": "year",
            "Developer": "developer", "Publisher": "publisher",
            "Genre": "genre", "Rating": "rating", "Play Count": "play_count"
        }
        field = mapping.get(self.combo_sort.currentText(), "name")
        reverse = self.btn_sort_dir.isChecked()
        if reverse:
            self.btn_sort_dir.setText("▼")
        else:
            self.btn_sort_dir.setText("▲")
        self.sort_changed.emit(field, reverse)

    def set_view_mode(self, mode: str):
        self.btn_grid.setChecked(mode == "grid")
        self.btn_list.setChecked(mode == "list")
        self.btn_rental.setChecked(mode == "rental")
        self.combo_size.setEnabled(mode == "grid")
