"""
Play Statistics Dashboard.

Shows library-wide play stats: most-played games, most-played systems,
play count distribution, total library size, and recently played history.
Rendered as a scrollable widget that can be embedded in a dialog or panel.
"""

from __future__ import annotations

from typing import List

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QGridLayout, QDialog, QDialogButtonBox, QSizePolicy,
    QProgressBar
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from ..core.models import RomEntry, get_system_color


# ── Helper widgets ────────────────────────────────────────────────────────────

def _card(title: str, value: str, subtitle: str = "", color: str = "#4a90d9") -> QFrame:
    frame = QFrame()
    frame.setStyleSheet(f"""
        QFrame {{
            background: #0c1825;
            border: 1px solid {color}44;
            border-radius: 6px;
            padding: 8px;
        }}
    """)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(2)

    val_lbl = QLabel(value)
    val_lbl.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: bold;")
    layout.addWidget(val_lbl)

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet("color: #446688; font-size: 10px; letter-spacing: 1px;")
    layout.addWidget(title_lbl)

    if subtitle:
        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet("color: #3a5570; font-size: 9px;")
        layout.addWidget(sub_lbl)

    return frame


def _section(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: #3a7a55; font-size: 10px; font-weight: bold; "
        "letter-spacing: 1px; margin-top: 12px;"
    )
    return lbl


def _bar_row(label: str, count: int, max_count: int, color: str) -> QWidget:
    w = QWidget()
    layout = QHBoxLayout(w)
    layout.setContentsMargins(0, 1, 0, 1)
    layout.setSpacing(6)

    lbl = QLabel(label)
    lbl.setFixedWidth(180)
    lbl.setStyleSheet("color: #8899bb; font-size: 11px;")
    lbl.setElideMode = lambda *_: None  # QLabel doesn't have this; ignore
    lbl.setWordWrap(False)
    layout.addWidget(lbl)

    bar = QProgressBar()
    bar.setRange(0, max(max_count, 1))
    bar.setValue(count)
    bar.setFixedHeight(14)
    bar.setTextVisible(False)
    bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    bar.setStyleSheet(f"""
        QProgressBar {{
            background: #0e1825;
            border: 1px solid #1a2535;
            border-radius: 3px;
        }}
        QProgressBar::chunk {{
            background: {color};
            border-radius: 2px;
        }}
    """)
    layout.addWidget(bar, 1)

    count_lbl = QLabel(str(count))
    count_lbl.setFixedWidth(36)
    count_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    count_lbl.setStyleSheet("color: #4a6688; font-size: 10px;")
    layout.addWidget(count_lbl)

    return w


# ── Dashboard widget ──────────────────────────────────────────────────────────

class StatsDashboard(QScrollArea):
    """
    Scrollable stats dashboard.  Call refresh(entries) to populate.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { border: none; background: #080c14; }")

        self._inner = QWidget()
        self._inner.setStyleSheet("background: #080c14;")
        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(16, 16, 16, 24)
        self._layout.setSpacing(4)
        self.setWidget(self._inner)

    def refresh(self, entries: List[RomEntry]):
        # Clear
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total = len(entries)
        played = [e for e in entries if e.play_count > 0]
        total_plays = sum(e.play_count for e in entries)
        favorites = sum(1 for e in entries if e.favorite)
        with_art = sum(1 for e in entries if e.image or e.thumbnail)

        # ── Header ────────────────────────────────────────────
        h_lbl = QLabel("Play Statistics")
        h_lbl.setStyleSheet(
            "color: #c8e8ff; font-size: 18px; font-weight: bold; margin-bottom: 8px;"
        )
        self._layout.addWidget(h_lbl)

        # ── Summary cards ─────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)
        cards_row.addWidget(_card("TOTAL ROMS",  f"{total:,}",        color="#4a90d9"))
        cards_row.addWidget(_card("TOTAL PLAYS", f"{total_plays:,}",  color="#c8a020"))
        cards_row.addWidget(_card("PLAYED",      f"{len(played):,}",  color="#40c060",
                                  subtitle=f"{len(played)*100//max(total,1)}% of library"))
        cards_row.addWidget(_card("FAVOURITES",  f"{favorites:,}",    color="#ffdd44"))
        cards_row.addWidget(_card("WITH ART",    f"{with_art:,}",     color="#a060c0",
                                  subtitle=f"{with_art*100//max(total,1)}%"))
        self._layout.addLayout(cards_row)

        # ── Most played games ─────────────────────────────────
        self._layout.addWidget(_section("MOST PLAYED GAMES"))
        top_games = sorted(played, key=lambda e: e.play_count, reverse=True)[:15]
        if top_games:
            max_plays = top_games[0].play_count
            for e in top_games:
                color = get_system_color(e.system)
                self._layout.addWidget(
                    _bar_row(f"{e.name}  ({e.system_full_name})", e.play_count, max_plays, color)
                )
        else:
            self._layout.addWidget(QLabel("No games played yet.") )

        # ── Most played systems ───────────────────────────────
        self._layout.addWidget(_section("PLAYS BY SYSTEM"))
        sys_plays: dict = {}
        for e in entries:
            if e.play_count > 0:
                key = e.system_full_name or e.system
                sys_plays[key] = sys_plays.get(key, 0) + e.play_count
        top_sys = sorted(sys_plays.items(), key=lambda x: x[1], reverse=True)[:10]
        if top_sys:
            max_sp = top_sys[0][1]
            for sys_name, count in top_sys:
                # find system key for color
                sys_key = next(
                    (e.system for e in entries if (e.system_full_name or e.system) == sys_name),
                    "default"
                )
                self._layout.addWidget(
                    _bar_row(sys_name, count, max_sp, get_system_color(sys_key))
                )

        # ── Recently played ───────────────────────────────────
        self._layout.addWidget(_section("RECENTLY PLAYED"))
        recent = sorted(
            [e for e in entries if e.last_played],
            key=lambda e: e.last_played, reverse=True
        )[:20]
        if recent:
            grid = QGridLayout()
            grid.setSpacing(2)
            grid.setContentsMargins(0, 0, 0, 0)
            for i, e in enumerate(recent):
                date_str = _fmt_date(e.last_played)
                name_lbl = QLabel(e.name)
                name_lbl.setStyleSheet("color: #8899bb; font-size: 11px;")
                sys_lbl = QLabel(e.system_full_name or e.system)
                sys_lbl.setStyleSheet(
                    f"color: {get_system_color(e.system)}; font-size: 10px;"
                )
                date_lbl = QLabel(date_str)
                date_lbl.setStyleSheet("color: #3a5570; font-size: 10px;")
                grid.addWidget(name_lbl, i, 0)
                grid.addWidget(sys_lbl,  i, 1)
                grid.addWidget(date_lbl, i, 2)
            self._layout.addLayout(grid)
        else:
            self._layout.addWidget(QLabel("No recently played games."))

        # ── Backlog summary ───────────────────────────────────
        unplayed    = sum(1 for e in entries if e.backlog_status == "unplayed")
        in_progress = sum(1 for e in entries if e.backlog_status == "in_progress")
        completed   = sum(1 for e in entries if e.backlog_status == "completed")
        if unplayed + in_progress + completed > 0:
            self._layout.addWidget(_section("BACKLOG"))
            bl_row = QHBoxLayout()
            bl_row.setSpacing(8)
            bl_row.addWidget(_card("UNPLAYED",    str(unplayed),    color="#5a6a8a"))
            bl_row.addWidget(_card("IN PROGRESS", str(in_progress), color="#c8a020"))
            bl_row.addWidget(_card("COMPLETED",   str(completed),   color="#40c060"))
            bl_row.addStretch()
            self._layout.addLayout(bl_row)

        self._layout.addStretch(1)


def _fmt_date(raw: str) -> str:
    """Format YYYYMMDDTHHMMSS to YYYY-MM-DD."""
    try:
        if len(raw) >= 8:
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    except Exception:
        pass
    return raw


# ── Standalone dialog ─────────────────────────────────────────────────────────

class StatsDashboardDialog(QDialog):
    def __init__(self, entries: List[RomEntry], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Play Statistics")
        self.setMinimumSize(820, 600)
        self.resize(900, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._dashboard = StatsDashboard()
        self._dashboard.refresh(entries)
        layout.addWidget(self._dashboard, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.setStyleSheet("padding: 6px;")
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
