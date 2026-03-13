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
        "roms_root": "",
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
    def roms_root(self) -> str:
        return self._data.get("roms_root", "")

    @roms_root.setter
    def roms_root(self, value: str):
        self._data["roms_root"] = value
        # Update recent libraries
        recent = self._data.get("recent_libraries", [])
        if value and value not in recent:
            recent.insert(0, value)
            self._data["recent_libraries"] = recent[:10]
