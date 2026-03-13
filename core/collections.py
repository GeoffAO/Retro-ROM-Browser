"""
Collections manager for Retro Browser.

Supports:
  - Built-in: All Games, Favorites, Recent (last 50 played)
  - Custom: user-created, stored as text files in <retrobat>/collections/
  - Rented: the Virtual Rental Shop's currently-rented titles

Custom collection files use the EmulationStation text format:
  one absolute ROM path per line.  File names follow the ES convention:
  "custom-<name>.cfg"

All collections operate on the same shared RomEntry objects from the Library,
so no data is duplicated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from .models import RomEntry


RECENT_MAX = 50
RENTED_FILE = "retrobrowser-rented.cfg"


class CollectionManager:
    """
    Manages all named collections.

    Instantiate once, pass in the library's full entry list via set_all_entries()
    whenever the library is loaded or refreshed.
    """

    def __init__(self, collections_dir: Optional[Path] = None):
        """
        collections_dir: the directory to store custom collection files.
        If None, custom collections are stored in ~/.retrobat_browser/collections/.
        """
        if collections_dir is None:
            collections_dir = Path.home() / ".retrobat_browser" / "collections"
        self._dir = collections_dir
        self._dir.mkdir(parents=True, exist_ok=True)

        self._all: List[RomEntry] = []
        # {name: set of rom path strings}
        self._custom_paths: Dict[str, set] = {}
        self._rented_paths: set = set()

        self._load_all_custom()
        self._load_rented()

    # ── Entry list ────────────────────────────────────────────────────────────

    def set_all_entries(self, entries: List[RomEntry]):
        """Call this whenever the library is loaded / refreshed."""
        self._all = list(entries)

    # ── Built-in collections ──────────────────────────────────────────────────

    def get_all(self) -> List[RomEntry]:
        return list(self._all)

    def get_favorites(self) -> List[RomEntry]:
        return [e for e in self._all if e.favorite]

    def get_recent(self) -> List[RomEntry]:
        """Return up to RECENT_MAX entries that have been played, most recent first."""
        played = [e for e in self._all if e.last_played]
        played.sort(key=lambda e: e.last_played, reverse=True)
        return played[:RECENT_MAX]

    # ── Custom collections ────────────────────────────────────────────────────

    def list_custom(self) -> List[str]:
        """Return all custom collection names (not including built-ins or Rented)."""
        return sorted(self._custom_paths.keys())

    def create_custom(self, name: str) -> bool:
        """Create a new empty collection.  Returns False if name already exists."""
        if name in self._custom_paths:
            return False
        self._custom_paths[name] = set()
        self._save_custom(name)
        return True

    def delete_custom(self, name: str):
        if name in self._custom_paths:
            del self._custom_paths[name]
            cfg = self._custom_cfg_path(name)
            if cfg.exists():
                cfg.unlink()

    def rename_custom(self, old_name: str, new_name: str) -> bool:
        if old_name not in self._custom_paths or new_name in self._custom_paths:
            return False
        self._custom_paths[new_name] = self._custom_paths.pop(old_name)
        old_cfg = self._custom_cfg_path(old_name)
        if old_cfg.exists():
            old_cfg.unlink()
        self._save_custom(new_name)
        return True

    def get_custom(self, name: str) -> List[RomEntry]:
        paths = self._custom_paths.get(name, set())
        return [e for e in self._all if str(e.rom_path) in paths]

    def add_to_custom(self, name: str, entry: RomEntry):
        if name not in self._custom_paths:
            self._custom_paths[name] = set()
        self._custom_paths[name].add(str(entry.rom_path))
        self._save_custom(name)

    def remove_from_custom(self, name: str, entry: RomEntry):
        if name in self._custom_paths:
            self._custom_paths[name].discard(str(entry.rom_path))
            self._save_custom(name)

    def is_in_custom(self, name: str, entry: RomEntry) -> bool:
        return str(entry.rom_path) in self._custom_paths.get(name, set())

    # ── Rented collection ─────────────────────────────────────────────────────

    def get_rented(self) -> List[RomEntry]:
        return [e for e in self._all if str(e.rom_path) in self._rented_paths]

    def rent(self, entry: RomEntry):
        self._rented_paths.add(str(entry.rom_path))
        self._save_rented()

    def return_game(self, entry: RomEntry):
        self._rented_paths.discard(str(entry.rom_path))
        self._save_rented()

    def is_rented(self, entry: RomEntry) -> bool:
        return str(entry.rom_path) in self._rented_paths

    def clear_rented(self):
        self._rented_paths.clear()
        self._save_rented()

    # ── Persistence helpers ───────────────────────────────────────────────────

    def _custom_cfg_path(self, name: str) -> Path:
        safe = name.replace("/", "_").replace("\\", "_")
        return self._dir / f"custom-{safe}.cfg"

    def _load_all_custom(self):
        for cfg in self._dir.glob("custom-*.cfg"):
            name = cfg.stem[len("custom-"):]
            self._custom_paths[name] = _load_path_set(cfg)

    def _save_custom(self, name: str):
        _save_path_set(self._custom_cfg_path(name), self._custom_paths.get(name, set()))

    def _load_rented(self):
        self._rented_paths = _load_path_set(self._dir / RENTED_FILE)

    def _save_rented(self):
        _save_path_set(self._dir / RENTED_FILE, self._rented_paths)

    # ── Summary ───────────────────────────────────────────────────────────────

    def collection_entries(self, collection_name: str) -> List[RomEntry]:
        """
        Get entries for any collection by name.
        Built-in names: "all", "favorites", "recent", "rented".
        Everything else is treated as a custom collection name.
        """
        lname = collection_name.lower()
        if lname == "all":
            return self.get_all()
        if lname == "favorites":
            return self.get_favorites()
        if lname == "recent":
            return self.get_recent()
        if lname == "rented":
            return self.get_rented()
        return self.get_custom(collection_name)

    def all_collection_names(self) -> List[str]:
        """Return ordered list of all collection names for display."""
        built_in = ["All Games", "Favorites", "Recent", "Rented"]
        custom = self.list_custom()
        return built_in + custom


# ── File I/O helpers ─────────────────────────────────────────────────────────

def _load_path_set(path: Path) -> set:
    if not path.exists():
        return set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return {line.strip() for line in lines if line.strip()}
    except Exception as e:
        print(f"[WARN] Could not load collection {path}: {e}")
        return set()


def _save_path_set(path: Path, paths: set):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(sorted(paths)) + "\n", encoding="utf-8")
    except Exception as e:
        print(f"[WARN] Could not save collection {path}: {e}")
