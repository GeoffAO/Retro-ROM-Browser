"""
In-memory library database with filtering, sorting, and search.
"""

from typing import List, Optional, Dict, Set
from pathlib import Path

from .models import RomEntry
from .scanner import scan_library, get_systems


class Library:
    """Manages the full ROM collection with filtering and sorting."""

    SORT_FIELDS = ["name", "system", "year", "developer", "publisher", "genre", "rating", "play_count"]

    def __init__(self):
        self._all_entries: List[RomEntry] = []
        self.roms_root: Optional[Path] = None
        self._loading = False

        # Filter state
        self.filter_system: Optional[str] = None
        self.filter_genre: Optional[str] = None
        self.filter_year: Optional[str] = None
        self.filter_search: str = ""
        self.filter_favorites_only: bool = False
        self.filter_has_image: bool = False
        self.filter_collection: Optional[str] = None
        self.sort_field: str = "name"
        self.sort_reverse: bool = False

    @property
    def total_count(self) -> int:
        return len(self._all_entries)

    def get_all(self) -> List[RomEntry]:
        """Return all loaded entries (unfiltered)."""
        return list(self._all_entries)

    def load(self, roms_root: Path, progress_callback=None, include_hidden=False):
        """Load (or reload) the full library from disk."""
        self.roms_root = roms_root
        self._all_entries = scan_library(roms_root, progress_callback, include_hidden)
        self._all_entries.sort(key=lambda e: e.name.lower())

    def get_systems(self) -> List[Dict]:
        """Return list of systems with counts from loaded entries."""
        system_counts: Dict[str, int] = {}
        system_names: Dict[str, str] = {}
        for e in self._all_entries:
            system_counts[e.system] = system_counts.get(e.system, 0) + 1
            system_names[e.system] = e.system_full_name
        return sorted([
            {"name": k, "full_name": system_names[k], "count": v}
            for k, v in system_counts.items()
        ], key=lambda x: x["full_name"])

    def get_genres(self) -> List[Dict]:
        """Return genres with counts, sorted by name. Genres split by / are each counted separately."""
        counts: Dict[str, int] = {}
        for e in self._all_entries:
            for g in e.genres:
                if g:
                    counts[g] = counts.get(g, 0) + 1
        return sorted(
            [{"name": g, "count": c} for g, c in counts.items()],
            key=lambda x: x["name"]
        )

    def get_years(self) -> List[Dict]:
        """Return years with counts, sorted newest first."""
        counts: Dict[str, int] = {}
        for e in self._all_entries:
            if e.year:
                counts[e.year] = counts.get(e.year, 0) + 1
        return sorted(
            [{"name": y, "count": c} for y, c in counts.items()],
            key=lambda x: x["name"],
            reverse=True
        )

    def get_developers(self) -> List[str]:
        devs: Set[str] = set()
        for e in self._all_entries:
            if e.developer:
                devs.add(e.developer)
        return sorted(devs)

    def get_filtered(self) -> List[RomEntry]:
        """Return filtered and sorted list of entries."""
        results = self._all_entries

        if self.filter_system:
            results = [e for e in results if e.system == self.filter_system]

        if self.filter_genre:
            fg = self.filter_genre.lower()
            results = [e for e in results if any(fg in g.lower() for g in e.genres)]

        if self.filter_year:
            results = [e for e in results if e.year == self.filter_year]

        if self.filter_favorites_only:
            results = [e for e in results if e.favorite]

        if self.filter_has_image:
            results = [e for e in results if e.best_image is not None]

        if self.filter_search:
            q = self.filter_search.lower()
            results = [
                e for e in results
                if q in e.name.lower()
                or q in e.description.lower()
                or q in e.developer.lower()
                or q in e.publisher.lower()
                or q in e.genre.lower()
            ]

        # Sort
        key_map = {
            "name": lambda e: e.name.lower(),
            "system": lambda e: (e.system_full_name.lower(), e.name.lower()),
            "year": lambda e: (e.year or "0000", e.name.lower()),
            "developer": lambda e: (e.developer.lower(), e.name.lower()),
            "publisher": lambda e: (e.publisher.lower(), e.name.lower()),
            "genre": lambda e: (e.genre.lower(), e.name.lower()),
            "rating": lambda e: (-e.rating, e.name.lower()),
            "play_count": lambda e: (-e.play_count, e.name.lower()),
        }
        key_fn = key_map.get(self.sort_field, key_map["name"])
        results = sorted(results, key=key_fn, reverse=self.sort_reverse)

        return results

    def get_stats(self) -> Dict:
        """Return library statistics."""
        total = len(self._all_entries)
        with_images = sum(1 for e in self._all_entries if e.best_image)
        with_desc = sum(1 for e in self._all_entries if e.description)
        favorites = sum(1 for e in self._all_entries if e.favorite)
        systems = len(set(e.system for e in self._all_entries))
        total_size = sum(e.file_size_mb for e in self._all_entries)
        return {
            "total": total,
            "with_images": with_images,
            "with_descriptions": with_desc,
            "favorites": favorites,
            "systems": systems,
            "total_size_gb": total_size / 1024,
        }
