"""
Game launcher for RetroBat.

Launches games via RetroBat's emulatorLauncher.exe, monitors the process,
and writes play_count / last_played back to gamelist.xml when the game exits.

Usage:
    launcher = GameLauncher(retrobat_install)
    launcher.launch(entry)          # fire and forget
    launcher.game_exited.connect(my_slot)   # notified when process ends
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal, QObject

from .models import RomEntry
from .retrobat import RetroBatInstall


# ── Background watcher thread ────────────────────────────────────────────────

class _WatcherThread(QThread):
    """Waits for the emulatorLauncher process to exit, then emits a signal."""

    game_exited = pyqtSignal(object, int)  # (RomEntry, return_code)

    def __init__(self, entry: RomEntry, proc: subprocess.Popen, parent=None):
        super().__init__(parent)
        self._entry = entry
        self._proc = proc

    def run(self):
        rc = self._proc.wait()
        self.game_exited.emit(self._entry, rc)


# ── GameLauncher ─────────────────────────────────────────────────────────────

class GameLauncher(QObject):
    """
    Manages game launches through RetroBat's emulatorLauncher.exe.

    Signals:
        game_launched(entry)    — process started successfully
        game_exited(entry, rc)  — process exited (rc = return code)
        launch_failed(entry, msg) — could not start the process
    """

    game_launched  = pyqtSignal(object)        # RomEntry
    game_exited    = pyqtSignal(object, int)   # RomEntry, return_code
    launch_failed  = pyqtSignal(object, str)   # RomEntry, error_message

    def __init__(self, retrobat: RetroBatInstall, parent=None):
        super().__init__(parent)
        self._retrobat = retrobat
        self._watchers: list = []

    def can_launch(self, entry: RomEntry) -> bool:
        """True if we have a launcher executable and a ROM file."""
        return (
            self._retrobat.launcher_exe.exists()
            and bool(entry.rom_path)
            and entry.rom_path.exists()
        )

    def launch(self, entry: RomEntry, emulator: str = "", core: str = ""):
        """
        Launch entry using emulatorLauncher.exe.

        emulator/core override the system defaults.  Leave empty to let
        RetroBat pick the configured defaults.
        """
        if not self.can_launch(entry):
            msg = "ROM file not found." if not entry.rom_path.exists() else "emulatorLauncher.exe not found."
            self.launch_failed.emit(entry, msg)
            return

        # Find the gamelist.xml for this ROM (emulatorLauncher uses it for metadata)
        gamelist_xml: Optional[Path] = None
        if entry.rom_path.parent:
            gl = entry.rom_path.parent / "gamelist.xml"
            if gl.exists():
                gamelist_xml = gl

        args = self._retrobat.build_launch_args(
            system=entry.system,
            rom_path=entry.rom_path,
            gamelist_xml=gamelist_xml,
            emulator=emulator,
            core=core,
        )

        try:
            proc = subprocess.Popen(
                args,
                cwd=str(self._retrobat.es_home),
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
        except Exception as e:
            self.launch_failed.emit(entry, str(e))
            return

        self.game_launched.emit(entry)

        # Spawn a watcher thread; keep a reference so it is not GC'd
        watcher = _WatcherThread(entry, proc, self)
        watcher.game_exited.connect(self._on_game_exited)
        watcher.finished.connect(lambda w=watcher: self._watchers.remove(w))
        self._watchers.append(watcher)
        watcher.start()

    def _on_game_exited(self, entry: RomEntry, rc: int):
        """Called in the main thread after the game process exits."""
        _write_play_stats(entry)
        self.game_exited.emit(entry, rc)

    @property
    def retrobat(self) -> RetroBatInstall:
        return self._retrobat

    @retrobat.setter
    def retrobat(self, value: RetroBatInstall):
        self._retrobat = value


# ── Save-state discovery ─────────────────────────────────────────────────────

def find_save_states(entry: RomEntry, retrobat: RetroBatInstall) -> list[dict]:
    """
    Return a list of save-state dicts for entry.

    Each dict: { "slot": int, "path": Path, "modified": datetime }

    RetroArch stores states at:
        <retroarch>/states/<core>/<game>.state0
        <retroarch>/states/<core>/<game>.state1
        ...
        <retroarch>/states/<core>/<game>.state  (quick-save)

    If we don't know the core we scan all sub-dirs.
    """
    states_root = retrobat.retroarch_states_dir
    if not states_root.is_dir() or not entry.rom_path:
        return []

    stem = entry.rom_path.stem
    results = []

    search_dirs = []
    # If we know the system, narrow to likely cores
    sdef = retrobat.system_def(entry.system)
    if sdef and sdef.default_core:
        core_dir = states_root / sdef.default_core
        if core_dir.is_dir():
            search_dirs.append(core_dir)

    # Always fall back to scanning all core dirs
    try:
        search_dirs += [d for d in states_root.iterdir() if d.is_dir()]
    except Exception:
        pass

    seen: set = set()
    for core_dir in search_dirs:
        try:
            for f in core_dir.iterdir():
                key = str(f)
                if key in seen:
                    continue
                if f.stem != stem:
                    continue
                suffix = f.suffix  # ".state", ".state0", ".state1", …
                if not (suffix == ".state" or suffix.startswith(".state")):
                    continue
                seen.add(key)
                slot_str = suffix.lstrip(".state") or "Q"  # Q = quick save
                try:
                    slot = int(slot_str)
                except ValueError:
                    slot = -1  # quick save
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                results.append({"slot": slot, "path": f, "modified": mtime, "core": core_dir.name})
        except Exception:
            pass

    results.sort(key=lambda d: d["slot"])
    return results


# ── gamelist.xml writeback ───────────────────────────────────────────────────

def _write_play_stats(entry: RomEntry):
    """
    Increment play_count and update last_played on entry,
    then write the change to the game's gamelist.xml.
    """
    entry.play_count = (entry.play_count or 0) + 1
    entry.last_played = datetime.now().strftime("%Y%m%dT%H%M%S")

    if not entry.rom_path:
        return
    gamelist = entry.rom_path.parent / "gamelist.xml"
    if not gamelist.exists():
        return

    try:
        import xml.etree.ElementTree as ET
        ET.register_namespace("", "")
        tree = ET.parse(str(gamelist))
        root = tree.getroot()

        rom_name = entry.rom_path.name
        for game_el in root.findall("game"):
            path_el = game_el.find("path")
            if path_el is None or not path_el.text:
                continue
            if rom_name not in path_el.text:
                continue

            # Update or create playcount / lastplayed elements
            _set_el(game_el, "playcount", str(entry.play_count))
            _set_el(game_el, "lastplayed", entry.last_played)
            break

        # Write back preserving encoding
        ET.indent(tree, space="  ")
        tree.write(str(gamelist), encoding="utf-8", xml_declaration=True)
    except Exception as e:
        print(f"[WARN] Could not write play stats for {entry.name}: {e}")


def _set_el(parent, tag: str, value: str):
    el = parent.find(tag)
    if el is None:
        import xml.etree.ElementTree as ET
        el = ET.SubElement(parent, tag)
    el.text = value
