"""
ScreenScraper scraping dialog.

Lets the user enter their ScreenScraper credentials and scrapes
metadata + media for selected ROMs via the ScreenScraper API v2.

API docs: https://www.screenscraper.fr/webapi2.php
"""

import hashlib
import json
import re
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QProgressBar, QTextEdit, QDialogButtonBox,
    QCheckBox, QFormLayout, QWidget, QFrame, QMessageBox,
    QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot

from ..core.models import RomEntry
from ..core.settings import Settings

SS_API_BASE  = "https://www.screenscraper.fr/api2"
SS_SOFT_NAME = "RetroBat ROM Browser"
# ScreenScraper requires a registered devid/devpassword for API access.
# Without registration the API still responds but with stricter rate limits.
# Users can register a developer account at https://www.screenscraper.fr/
# and enter their dev credentials in settings to raise their limit.
# The User-Agent must look like a real browser or SS returns 403.
SS_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class ScrapeWorker(QThread):
    """Background thread that scrapes a list of ROMs."""

    progress  = pyqtSignal(int, int, str)   # current, total, message
    log_line  = pyqtSignal(str)             # log text line
    finished  = pyqtSignal(int, int)        # success_count, fail_count

    def __init__(self, entries: List[RomEntry], username: str, password: str,
                 media_types: List[str], dev_id: str = "", dev_pwd: str = "", parent=None):
        super().__init__(parent)
        self.entries    = entries
        self.username   = username
        self.password   = password
        self.media_types = media_types
        self.dev_id     = dev_id
        self.dev_pwd    = dev_pwd
        self._cancel    = False

    def cancel(self):
        self._cancel = True

    def run(self):
        success, fail = 0, 0
        total = len(self.entries)

        for i, entry in enumerate(self.entries):
            if self._cancel:
                self.log_line.emit("⚠  Cancelled by user.")
                break

            self.progress.emit(i, total, f"Scraping: {entry.name}")
            try:
                ok = self._scrape_one(entry)
                if ok:
                    success += 1
                    self.log_line.emit(f"✓  {entry.name}")
                else:
                    fail += 1
                    self.log_line.emit(f"✗  {entry.name} — not found on ScreenScraper")
            except Exception as e:
                fail += 1
                self.log_line.emit(f"✗  {entry.name} — {e}")

        self.progress.emit(total, total, "Done")
        self.finished.emit(success, fail)

    def _scrape_one(self, entry: RomEntry) -> bool:
        """Query ScreenScraper for one ROM and write metadata + media."""
        rom_path = entry.rom_path
        if not rom_path or not rom_path.exists():
            return False

        md5 = _md5_file(rom_path)

        params = {
            "output":      "json",
            "devid":       self.dev_id,
            "devpassword": self.dev_pwd,
            "ssid":        self.username,
            "sspassword":  self.password,
            "softname":    SS_SOFT_NAME,
            "romtype":     "rom",
            "romnom":      rom_path.name,
            "rommd5":      md5,
            "systemeid":   _system_to_ss_id(entry.system),
        }

        url = f"{SS_API_BASE}/jeuInfos.php?" + urllib.parse.urlencode(params)

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": SS_USER_AGENT,
                    "Accept": "application/json",
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            if e.code == 403:
                raise Exception(
                    "403 Forbidden — check your ScreenScraper username/password. "
                    "Make sure you are using your screenscraper.fr login credentials."
                )
            if e.code == 430:
                raise Exception("API quota exceeded for today. Try again tomorrow.")
            if e.code == 431:
                raise Exception("Too many concurrent requests. Slow down and retry.")
            raise Exception(f"HTTP {e.code}: {e.reason}")

        game = data.get("response", {}).get("jeu")
        if not game:
            return False

        # ── Parse metadata ──────────────────────────────────
        entry.name      = _ss_text(game, "noms", "nom_en") or entry.name
        entry.developer = _ss_company(game, "developpeur")
        entry.publisher = _ss_company(game, "editeur")
        entry.genre     = _ss_genre(game)
        entry.description = _ss_text(game, "synopsis", "synopsis_en") or entry.description

        dates = game.get("dates", {})
        ww    = dates.get("date_ww") or dates.get("date_us") or dates.get("date_eu") or ""
        if ww:
            entry.release_date = re.sub(r"[^0-9]", "", ww[:10]).ljust(8, "0") + "T000000"
            entry.release_year = ww[:4]

        note = game.get("note", {})
        if note.get("valeur"):
            try:
                entry.rating = float(note["valeur"]) / 20.0   # SS gives 0-100 → 0-1
            except (ValueError, TypeError):
                pass

        players = game.get("joueurs", {})
        if players.get("valeur"):
            entry.players = str(players["valeur"])

        # ── Download media ───────────────────────────────────
        medias = game.get("medias", [])
        gamelist_dir = entry.rom_path.parent

        # Folders match scanner.py MEDIA_FOLDERS so artwork is found on next reload.
        _try_download_media(entry, medias, "box-2D",       gamelist_dir, "named_boxarts", "image",      self.media_types)
        _try_download_media(entry, medias, "screenshot",   gamelist_dir, "named_snaps",   "screenshot", self.media_types)
        _try_download_media(entry, medias, "wheel",        gamelist_dir, "named_wheels",  "marquee",    self.media_types)
        _try_download_media(entry, medias, "title-screen", gamelist_dir, "named_titles",  "titleshot",  self.media_types)

        # Write gamelist.xml
        try:
            from .edit_dialog import _write_gamelist_entry
            _write_gamelist_entry(entry)
        except Exception:
            pass   # best effort

        return True


# ── Helpers ────────────────────────────────────────────────────────────────────

def _md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ss_text(game: dict, key: str, lang_key: str) -> str:
    obj = game.get(key, {})
    if isinstance(obj, dict):
        return obj.get(lang_key) or obj.get("nom_ww") or next(iter(obj.values()), "")
    return ""


def _ss_company(game: dict, key: str) -> str:
    obj = game.get(key, {})
    if isinstance(obj, dict):
        return obj.get("text", "")
    return ""


def _ss_genre(game: dict) -> str:
    genres = game.get("genres", [])
    if not genres:
        return ""
    first = genres[0] if isinstance(genres, list) else genres
    if isinstance(first, dict):
        names = first.get("noms", [])
        for n in names:
            if isinstance(n, dict) and n.get("langue") == "en":
                return n.get("text", "")
        return names[0].get("text", "") if names else ""
    return str(first)


def _try_download_media(entry: RomEntry, medias: list, media_type: str,
                         gamelist_dir: Path, subfolder: str, attr: str,
                         allowed_types: List[str]):
    if attr not in allowed_types:
        return
    for m in medias:
        if not isinstance(m, dict):
            continue
        if m.get("type") != media_type:
            continue
        url = m.get("url")
        if not url:
            continue
        ext = Path(urllib.parse.urlparse(url).path).suffix or ".png"
        dest_dir = gamelist_dir / subfolder
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / (entry.rom_path.stem + ext)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": SS_USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:
                dest.write_bytes(resp.read())
            setattr(entry, attr, dest)
        except Exception:
            pass
        return   # only download first match


# ScreenScraper system IDs for common platforms
_SS_SYSTEM_MAP = {
    "nes": "3", "snes": "4", "n64": "14", "gb": "9", "gbc": "10", "gba": "12",
    "nds": "15", "genesis": "1", "megadrive": "1", "mastersystem": "2",
    "gamegear": "21", "sega32x": "19", "segacd": "20", "saturn": "22",
    "dreamcast": "23", "psx": "57", "ps2": "58", "psp": "61",
    "arcade": "75", "mame": "75", "neogeo": "142", "fba": "75",
    "atari2600": "26", "atari7800": "41", "lynx": "28", "jaguar": "27",
    "c64": "116", "amiga": "64", "pcengine": "31", "wonderswan": "45",
    "ngp": "25", "ngpc": "82",
}

def _system_to_ss_id(system: str) -> str:
    return _SS_SYSTEM_MAP.get(system.lower(), "")


# ── Dialog ─────────────────────────────────────────────────────────────────────

class ScrapeDialog(QDialog):
    scrape_completed = pyqtSignal()

    def __init__(self, entries: List[RomEntry], settings: Settings, parent=None):
        super().__init__(parent)
        self.entries  = entries
        self.settings = settings
        self._worker: Optional[ScrapeWorker] = None
        self.setWindowTitle(f"Scrape from ScreenScraper — {len(entries)} ROM(s)")
        self.setMinimumSize(540, 560)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)

        # Credentials
        cred_box = QGroupBox("ScreenScraper Account")
        cred_box.setStyleSheet("QGroupBox { color: #6688aa; font-size: 12px; }")
        cred_form = QFormLayout(cred_box)
        cred_form.setSpacing(6)

        self.f_user = QLineEdit(self.settings.get("ss_username", ""))
        self.f_user.setPlaceholderText("Your ScreenScraper username")
        self.f_pass = QLineEdit(self.settings.get("ss_password", ""))
        self.f_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.f_pass.setPlaceholderText("Your ScreenScraper password")

        self.f_devid  = QLineEdit(self.settings.get("ss_devid", ""))
        self.f_devid.setPlaceholderText("Developer ID (optional — raises rate limits)")
        self.f_devpwd = QLineEdit(self.settings.get("ss_devpwd", ""))
        self.f_devpwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.f_devpwd.setPlaceholderText("Developer password (optional)")

        note = QLabel(
            'Use your <a href="https://www.screenscraper.fr" '
            'style="color:#40c070">screenscraper.fr</a> login credentials. '
            'Register a free account if you do not have one. '
            'For higher rate limits, apply for a developer account at '
            'screenscraper.fr and enter your dev ID/password below.'
        )
        note.setWordWrap(True)
        note.setOpenExternalLinks(True)
        note.setStyleSheet("color: #556688; font-size: 11px;")

        cred_form.addRow(QLabel("Username:"), self.f_user)
        cred_form.addRow(QLabel("Password:"), self.f_pass)
        cred_form.addRow(QLabel("Dev ID:"), self.f_devid)
        cred_form.addRow(QLabel("Dev Pwd:"), self.f_devpwd)
        cred_form.addRow(note)
        layout.addWidget(cred_box)

        # Media options
        media_box = QGroupBox("Download Media")
        media_box.setStyleSheet("QGroupBox { color: #6688aa; font-size: 12px; }")
        media_layout = QHBoxLayout(media_box)
        self.cb_boxart     = QCheckBox("Box Art")
        self.cb_screenshot = QCheckBox("Screenshots")
        self.cb_marquee    = QCheckBox("Marquees")
        self.cb_titleshot  = QCheckBox("Title Screens")
        for cb in (self.cb_boxart, self.cb_screenshot, self.cb_marquee, self.cb_titleshot):
            cb.setChecked(True)
            media_layout.addWidget(cb)
        layout.addWidget(media_box)

        # ROM list summary
        summary = QLabel(
            f"ROMs to scrape:  {len(self.entries)}\n" +
            "\n".join(f"  • {e.name}  ({e.system})" for e in self.entries[:8]) +
            (f"\n  … and {len(self.entries) - 8} more" if len(self.entries) > 8 else "")
        )
        summary.setStyleSheet("color: #7a9abb; font-size: 11px; background: #0c1018; "
                              "border: 1px solid #1a2535; border-radius: 4px; padding: 8px;")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, len(self.entries))
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.progress_lbl = QLabel("")
        self.progress_lbl.setStyleSheet("color: #6688aa; font-size: 11px;")
        self.progress_lbl.setVisible(False)
        layout.addWidget(self.progress_lbl)

        # Log
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(140)
        self.log.setStyleSheet(
            "background: #080c14; color: #5a8a6a; font-size: 11px; "
            "font-family: monospace; border: 1px solid #1a2535;"
        )
        self.log.setVisible(False)
        layout.addWidget(self.log)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_start  = QPushButton("▶  Start Scraping")
        self.btn_start.setObjectName("primary")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

    def _on_start(self):
        user = self.f_user.text().strip()
        pwd  = self.f_pass.text().strip()

        if not user or not pwd:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Credentials Required",
                "Please enter your ScreenScraper username and password.\n\n"
                "Register a free account at screenscraper.fr if you don't have one.")
            return

        self.settings.set("ss_username", user)
        self.settings.set("ss_devid",   self.f_devid.text().strip())
        self.settings.set("ss_devpwd",  self.f_devpwd.text().strip())
        self.settings.save()

        media_types = []
        if self.cb_boxart.isChecked():     media_types.append("image")
        if self.cb_screenshot.isChecked(): media_types.append("screenshot")
        if self.cb_marquee.isChecked():    media_types.append("marquee")
        if self.cb_titleshot.isChecked():  media_types.append("titleshot")

        self.btn_start.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_lbl.setVisible(True)
        self.log.setVisible(True)

        self._worker = ScrapeWorker(
            self.entries, user, pwd, media_types,
            dev_id=self.f_devid.text().strip(),
            dev_pwd=self.f_devpwd.text().strip(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.log_line.connect(self._on_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
        else:
            self.reject()

    @pyqtSlot(int, int, str)
    def _on_progress(self, current, total, msg):
        self.progress_bar.setValue(current)
        self.progress_lbl.setText(msg)

    @pyqtSlot(str)
    def _on_log(self, line):
        self.log.append(line)

    @pyqtSlot(int, int)
    def _on_finished(self, success, fail):
        self.btn_cancel.setText("Close")
        self.btn_start.setEnabled(True)
        self.progress_lbl.setText(f"Done — {success} succeeded, {fail} failed.")
        self.scrape_completed.emit()
