"""
Persistent application settings using QSettings.
"""

import json
from pathlib import Path
from typing import Optional


class Settings:
    """Manages persistent application configuration."""

    CONFIG_FILE = Path.home() / ".retrobat_browser" / "config.json"

    DEFAULTS = {
        "retrobat_path": "",          # root RetroBat install folder (e.g. D:/RetroBat)
        "roms_root": "",              # explicit ROMs root override (legacy / standalone use)
        "window_width": 1400,
        "window_height": 900,
        "window_x": -1,
        "window_y": -1,
        "splitter_left": 220,
        "splitter_detail": 340,
        "view_mode": "grid",          # "grid" or "list"
        "grid_size": "medium",        # "small", "medium", "large"
        "show_hidden": False,
        "sort_field": "name",
        "sort_reverse": False,
        "theme": "dark",
        "recent_libraries": [],
        # ScreenScraper credentials (may be auto-imported from es_settings.cfg)
        "ss_username": "",
        "ss_password": "",
        "ss_devid": "",
        "ss_devpwd": "",
    }

    def __init__(self):
        self._data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        try:
            if self.CONFIG_FILE.exists():
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._data.update(loaded)
        except Exception as e:
            print(f"[WARN] Could not load settings: {e}")

    def save(self):
        try:
            self.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            print(f"[WARN] Could not save settings: {e}")

    def get(self, key: str, default=None):
        return self._data.get(key, default if default is not None else self.DEFAULTS.get(key))

    def set(self, key: str, value):
        self._data[key] = value

    @property
    def retrobat_path(self) -> str:
        return self._data.get("retrobat_path", "")

    @retrobat_path.setter
    def retrobat_path(self, value: str):
        self._data["retrobat_path"] = value

    @property
    def roms_root(self) -> str:
        """
        Return the effective ROMs root.
        If a RetroBat path is configured, derive it from there.
        Otherwise fall back to the explicit roms_root setting.
        """
        rb = self._data.get("retrobat_path", "")
        if rb:
            from pathlib import Path
            derived = str(Path(rb) / "roms")
            return derived
        return self._data.get("roms_root", "")

    @roms_root.setter
    def roms_root(self, value: str):
        self._data["roms_root"] = value
        # Update recent libraries
        recent = self._data.get("recent_libraries", [])
        if value and value not in recent:
            recent.insert(0, value)
            self._data["recent_libraries"] = recent[:10]

    def import_ss_credentials_from_retrobat(self) -> bool:
        """
        Read ScreenScraper credentials from the configured RetroBat install's
        es_settings.cfg and store them in settings.  Returns True on success.
        """
        rb_path = self._data.get("retrobat_path", "")
        if not rb_path:
            return False
        try:
            from pathlib import Path
            from .retrobat import RetroBatInstall
            rb = RetroBatInstall(Path(rb_path))
            user = rb.ss_username
            pwd = rb.ss_password
            if user:
                self._data["ss_username"] = user
                self._data["ss_password"] = pwd
                return True
        except Exception as e:
            print(f"[WARN] Could not import SS credentials: {e}")
        return False
