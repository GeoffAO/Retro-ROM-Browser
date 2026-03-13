"""
Application-wide Qt stylesheet.
Dark arcade cabinet theme — deep navy/charcoal with phosphor-green accents.
"""

DARK_STYLE = """
/* ── Global ─────────────────────────────────────────────── */
QWidget {
    background-color: #0f1117;
    color: #d0d8e8;
    font-family: "Segoe UI", "Ubuntu", "Helvetica Neue", sans-serif;
    font-size: 13px;
    selection-background-color: #1a6e3c;
    selection-color: #e8ffe8;
}

QMainWindow {
    background-color: #0a0c12;
}

/* ── Menu Bar ────────────────────────────────────────────── */
QMenuBar {
    background-color: #080a10;
    color: #a0b0c8;
    border-bottom: 1px solid #1a2030;
    padding: 2px 4px;
    font-size: 12px;
}
QMenuBar::item:selected {
    background-color: #1a2535;
    color: #c8ffd0;
    border-radius: 3px;
}
QMenu {
    background-color: #10141e;
    border: 1px solid #2a3550;
    border-radius: 4px;
    padding: 4px 0;
}
QMenu::item {
    padding: 6px 28px 6px 12px;
    color: #c0cce0;
}
QMenu::item:selected {
    background-color: #1a3a28;
    color: #b0ffb8;
}
QMenu::separator {
    height: 1px;
    background: #2a3550;
    margin: 4px 8px;
}

/* ── Tool Bar ────────────────────────────────────────────── */
QToolBar {
    background-color: #080c14;
    border-bottom: 1px solid #1a2535;
    spacing: 4px;
    padding: 4px 8px;
}
QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 5px 10px;
    color: #8899bb;
    font-size: 12px;
}
QToolButton:hover {
    background-color: #1a2535;
    border-color: #2a3a55;
    color: #c8ffd0;
}
QToolButton:checked {
    background-color: #0e2a1a;
    border-color: #1a6e3c;
    color: #40ff80;
}

/* ── Status Bar ──────────────────────────────────────────── */
QStatusBar {
    background-color: #080a10;
    color: #556688;
    border-top: 1px solid #1a2030;
    font-size: 11px;
    padding: 2px 8px;
}

/* ── Splitter ────────────────────────────────────────────── */
QSplitter::handle {
    background-color: #1a2030;
    width: 3px;
    height: 3px;
}
QSplitter::handle:hover {
    background-color: #2a9a5a;
}

/* ── Scroll Bars ─────────────────────────────────────────── */
QScrollBar:vertical {
    background: #0f1117;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #2a3a55;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #3a7a50;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #0f1117;
    height: 8px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #2a3a55;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover { background: #3a7a50; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── Search / Line Edit ──────────────────────────────────── */
QLineEdit {
    background-color: #161c28;
    border: 1px solid #2a3550;
    border-radius: 5px;
    color: #d0e0f0;
    padding: 5px 10px;
    font-size: 13px;
    selection-background-color: #1a5a30;
}
QLineEdit:focus {
    border-color: #2a9a5a;
    background-color: #111820;
}
QLineEdit::placeholder {
    color: #445566;
}

/* ── Combo Box ───────────────────────────────────────────── */
QComboBox {
    background-color: #161c28;
    border: 1px solid #2a3550;
    border-radius: 4px;
    color: #c0d0e8;
    padding: 4px 8px;
    min-width: 80px;
}
QComboBox:hover { border-color: #3a5a7a; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #10141e;
    border: 1px solid #2a3550;
    selection-background-color: #1a3a28;
    color: #c0d0e8;
    outline: none;
}

/* ── Push Buttons ────────────────────────────────────────── */
QPushButton {
    background-color: #161c28;
    border: 1px solid #2a3a55;
    border-radius: 5px;
    color: #9ab0cc;
    padding: 6px 16px;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #1a2a40;
    border-color: #2a9a5a;
    color: #c8ffd0;
}
QPushButton:pressed { background-color: #0e1e30; }
QPushButton#primary {
    background-color: #0e3a20;
    border-color: #1a9a4a;
    color: #60ffaa;
    font-weight: bold;
}
QPushButton#primary:hover { background-color: #155030; border-color: #2abf60; }

/* ── List / Tree Views ───────────────────────────────────── */
QListView, QTreeView {
    background-color: #0c1018;
    border: none;
    outline: none;
    alternate-background-color: #0e1220;
    show-decoration-selected: 1;
}
QListView::item, QTreeView::item {
    padding: 4px 8px;
    border-radius: 3px;
}
QListView::item:hover, QTreeView::item:hover {
    background-color: #141e2c;
}
QListView::item:selected, QTreeView::item:selected {
    background-color: #0e2a1a;
    color: #b0ffcc;
    border-left: 2px solid #2abf60;
}

/* ── Table View ──────────────────────────────────────────── */
QTableView {
    background-color: #0c1018;
    gridline-color: #1a2030;
    border: none;
    alternate-background-color: #0e1220;
    outline: none;
}
QTableView::item {
    padding: 3px 8px;
    border: none;
}
QTableView::item:hover { background-color: #141e2c; }
QTableView::item:selected {
    background-color: #0e2a1a;
    color: #b0ffcc;
}
QHeaderView::section {
    background-color: #080c14;
    color: #6688aa;
    border: none;
    border-right: 1px solid #1a2030;
    border-bottom: 1px solid #1a2030;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
QHeaderView::section:hover {
    background-color: #10182a;
    color: #88bbdd;
}

/* ── Tab Widget ──────────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid #1a2535;
    border-radius: 4px;
    background: #0c1018;
}
QTabBar::tab {
    background: #0c1018;
    color: #6688aa;
    border: 1px solid #1a2535;
    border-bottom: none;
    padding: 6px 16px;
    border-radius: 4px 4px 0 0;
    margin-right: 2px;
    font-size: 12px;
}
QTabBar::tab:hover { color: #90c0aa; background: #10181e; }
QTabBar::tab:selected {
    background: #0e2218;
    color: #60e090;
    border-color: #1a4a2a;
    font-weight: bold;
}

/* ── Labels ──────────────────────────────────────────────── */
QLabel#game-title {
    color: #f0fff8;
    font-size: 18px;
    font-weight: bold;
    letter-spacing: 0.3px;
}
QLabel#game-system {
    color: #40c070;
    font-size: 12px;
    font-weight: bold;
    letter-spacing: 1px;
    text-transform: uppercase;
}
QLabel#game-meta {
    color: #7a9abb;
    font-size: 12px;
}
QLabel#section-header {
    color: #3a8a5a;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 6px 12px 4px 12px;
    border-bottom: 1px solid #1a2535;
}
QLabel#stat-value {
    color: #60d090;
    font-size: 22px;
    font-weight: bold;
}
QLabel#stat-label {
    color: #4a6688;
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
}

/* ── Frame / Group ───────────────────────────────────────── */
QFrame#sidebar {
    background-color: #09101a;
    border-right: 1px solid #1a2535;
}
QFrame#detail-panel {
    background-color: #09101a;
    border-left: 1px solid #1a2535;
}
QFrame#cover-frame {
    background-color: #0c1825;
    border: 1px solid #1e3050;
    border-radius: 6px;
}

/* ── Progress Bar ────────────────────────────────────────── */
QProgressBar {
    background: #1a2030;
    border: 1px solid #2a3550;
    border-radius: 3px;
    height: 8px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1a9a4a, stop:1 #30cf70);
    border-radius: 3px;
}

/* ── Tooltip ─────────────────────────────────────────────── */
QToolTip {
    background-color: #101820;
    color: #c0d8f0;
    border: 1px solid #2a3550;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}

/* ── Dialog ──────────────────────────────────────────────── */
QDialog {
    background-color: #0f1520;
}
QDialogButtonBox QPushButton { min-width: 80px; }

/* ── Checkbox ────────────────────────────────────────────── */
QCheckBox {
    color: #8899bb;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #2a3a55;
    border-radius: 3px;
    background: #10181e;
}
QCheckBox::indicator:checked {
    background: #1a6e3c;
    border-color: #2abf60;
    image: none;
}
QCheckBox:hover { color: #b0d0c0; }

/* ── Miscellaneous ───────────────────────────────────────── */
QSizeGrip { image: none; width: 8px; height: 8px; }
"""
