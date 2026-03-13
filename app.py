"""
Application entry point.
"""

import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIcon

from .ui.main_window import MainWindow
from .ui.styles import DARK_STYLE


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RetroBat ROM Browser")
    app.setOrganizationName("RetroBatBrowser")
    app.setStyle("Fusion")

    # App icon — look for icon.ico next to main.py
    icon_path = Path(sys.argv[0]).parent / "icon.ico"
    if not icon_path.exists():
        icon_path = Path(__file__).parent.parent.parent / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Apply dark stylesheet
    app.setStyleSheet(DARK_STYLE)

    # Default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
