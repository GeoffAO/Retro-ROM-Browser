"""
Scanner and parser for RetroBat ROM libraries.
Reads gamelist.xml files and resolves media paths.

Performance notes:
- Each system directory's media sub-folders are scanned ONCE into a set,
  eliminating thousands of individual Path.exists() calls.
- lxml is used if available for faster XML parsing; falls back to stdlib ET.
"""

import os
import re
from pathlib import Path
from typing import List, Optional, Dict, Callable, Set

try:
    from lxml import etree as _lxml_et
    _USE_LXML = True
except ImportError:
    import xml.etree.ElementTree as ET
    _USE_LXML = False

from .models import RomEntry, SYSTEM_NAMES

# Media folder name → RomEntry attribute
# ORDER MATTERS: for attributes with multiple possible folders,
# the more specific/preferred folder must come first.
MEDIA_FOLDERS: Dict[str, str] = {
    # Box art: prefer dedicated boxart folder over generic images mix
    "named_boxarts":    "image",
    "images":           "image",
    # Thumbnail
    "named_thumbnails": "thumbnail",
    "thumbnails":       "thumbnail",
    # Marquee / wheel
    "named_wheels":     "marquee",
    "named_marquees":   "marquee",
    "marquees":         "marquee",
    # Screenshots
    "named_snaps":      "screenshot",
    "screenshots":      "screenshot",
    # Title screens
    "named_titles":     "titleshot",
    "titlescreens":     "titleshot",
    # Other
    "videos":           "video",
    "manuals":          "manual",
    "maps":             "map",
}

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
MANUAL_EXTS = (".pdf",)
# Attrs that accept non-image files (uses MANUAL_EXTS instead of IMAGE_EXTS)
_MANUAL_ATTRS = {"manual"}


def _clean_path(raw: str) -> str:
    return raw.strip().replace("\\", "/")


def _build_media_index(gamelist_dir: Path) -> Dict[str, Dict[str, Path]]:
    """
    Scan all media sub-folders ONCE and return a nested dict:
      { attr_name: { stem_lower: Path } }

    Also scans one level of named sub-folders within each media folder
    (e.g. images/Named_Boxarts/, images/Named_Snaps/) which RetroBat
    uses for dedicated box art vs. mix images.
    """
    index: Dict[str, Dict[str, Path]] = {}
    seen_attrs: Set[str] = set()

    # Named sub-folder overrides: if a recognised named subfolder exists
    # inside a media folder, its files take priority for a specific attr.
    NAMED_SUBFOLDER_ATTRS: Dict[str, str] = {
        "named_boxarts":    "image",
        "named_snaps":      "screenshot",
        "named_titles":     "titleshot",
        "named_marquees":   "marquee",
        "named_wheels":     "marquee",
        "named_thumbnails": "thumbnail",
    }

    def _scan_folder_into(folder: Path, attr: str, dest: Dict[str, Path]):
        """Add all media files from folder into dest dict (stem_lower → path)."""
        exts = MANUAL_EXTS if attr in _MANUAL_ATTRS else IMAGE_EXTS
        try:
            for f in folder.iterdir():
                if f.is_file() and f.suffix.lower() in exts:
                    dest[f.stem.lower()] = f
        except PermissionError:
            pass

    # First pass: scan top-level media folders
    for folder_name, attr in MEDIA_FOLDERS.items():
        folder = gamelist_dir / folder_name
        if not folder.is_dir():
            continue

        if attr not in index:
            index[attr] = {}

        # Second pass: check for named sub-folders inside this folder first
        # (they contain more specific/preferred art than the parent folder)
        for subfolder in folder.iterdir() if folder.is_dir() else []:
            if not subfolder.is_dir():
                continue
            sub_name = subfolder.name.lower()
            sub_attr = NAMED_SUBFOLDER_ATTRS.get(sub_name)
            if sub_attr:
                if sub_attr not in index:
                    index[sub_attr] = {}
                # Named subfolder files go into their specific attr dict
                # but only if it hasn't been filled by a top-level dedicated folder
                sub_map: Dict[str, Path] = {}
                _scan_folder_into(subfolder, sub_attr, sub_map)
                # Merge: sub_map values fill any gaps in the existing index
                for stem, path in sub_map.items():
                    if stem not in index[sub_attr]:
                        index[sub_attr][stem] = path

        if attr not in seen_attrs:
            seen_attrs.add(attr)
            _scan_folder_into(folder, attr, index[attr])

        # Special case: RetroBat stores box art as "<stem>-thumb.png" inside
        # the images/ folder.  Index those files under "thumbnail" as well so
        # _lookup_media can find them via the -thumb stem variant.
        if folder_name == "images":
            if "thumbnail" not in index:
                index["thumbnail"] = {}
            try:
                for f in folder.iterdir():
                    if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                        if f.stem.lower().endswith("-thumb"):
                            index["thumbnail"][f.stem.lower()] = f
            except PermissionError:
                pass

    return index


def _lookup_media(index: Dict[str, Dict[str, Path]], attr: str, stems: List[str]) -> Optional[Path]:
    """Look up a media file by trying each stem in order.

    For the thumbnail attribute (box art in RetroBat), also try the
    '<stem>-thumb' naming convention used by RetroBat's scraper, e.g.
    'Alfred Chicken (USA)-thumb.png'.
    """
    stem_map = index.get(attr)
    if not stem_map:
        return None
    candidates = list(stems)
    if attr == "thumbnail":
        # Add -thumb variants right after each base stem
        extra = []
        for s in stems:
            extra.append(s + "-thumb")
        candidates = [x for pair in zip(stems, extra) for x in pair]
    for stem in candidates:
        result = stem_map.get(stem.lower())
        if result:
            return result
    return None


def _fast_parse(gamelist_path: Path):
    """Parse XML, returning an iterable of game elements."""
    if _USE_LXML:
        try:
            tree = _lxml_et.parse(str(gamelist_path))
            return tree.getroot().findall("game")
        except Exception:
            pass
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(str(gamelist_path))
        return tree.getroot().findall("game")
    except Exception as e:
        print(f"[WARN] Could not parse {gamelist_path}: {e}")
        return []



# Maps folder name → the attribute the file SHOULD be in
_FOLDER_TO_ATTR: Dict[str, str] = {
    "images":        "image",
    "named_boxarts": "image",
    "thumbnails":    "thumbnail",
    "named_thumbnails": "thumbnail",
    "marquees":      "marquee",
    "named_marquees": "marquee",
    "named_wheels":  "marquee",
    "screenshots":   "screenshot",
    "named_snaps":   "screenshot",
    "titlescreens":  "titleshot",
    "named_titles":  "titleshot",
    "videos":        "video",
    "manuals":       "manual",
    "maps":          "map",
}

def _reassign_by_folder(entry: RomEntry, gamelist_dir: Path):
    """
    Re-examine every resolved media path and move it to the attribute
    that matches its parent folder name — BUT respect the RetroBat
    convention that files ending in '-thumb' are always box-art thumbnails
    regardless of which folder they live in.
    """
    all_attrs = ("image", "thumbnail", "marquee", "screenshot",
                 "titleshot", "video", "manual", "map")

    assigned: Dict[str, Path] = {}
    for attr in all_attrs:
        val = getattr(entry, attr)
        if val:
            assigned[attr] = val

    if not assigned:
        return

    corrections: Dict[str, Path] = {}
    for current_attr, path in assigned.items():
        stem_lower = path.stem.lower()
        folder_name = path.parent.name.lower()

        # -thumb files are always box-art thumbnails
        if stem_lower.endswith("-thumb"):
            correct_attr = "thumbnail"
        else:
            correct_attr = _FOLDER_TO_ATTR.get(folder_name, current_attr)

        if correct_attr != current_attr:
            corrections[correct_attr] = path
            setattr(entry, current_attr, None)

    for correct_attr, path in corrections.items():
        if getattr(entry, correct_attr) is None:
            setattr(entry, correct_attr, path)


def _parse_gamelist(gamelist_path: Path, system: str, roms_root: Path) -> List[RomEntry]:
    gamelist_dir = gamelist_path.parent
    system_full = SYSTEM_NAMES.get(system.lower(), system.upper())

    # Build media index ONCE for this system directory
    media_index = _build_media_index(gamelist_dir)

    entries: List[RomEntry] = []

    for game in _fast_parse(gamelist_path):
        def g(tag: str, default: str = "") -> str:
            el = game.find(tag)
            return el.text.strip() if el is not None and el.text else default

        entry = RomEntry()
        entry.system = system
        entry.system_full_name = system_full

        entry.name = g("name") or g("sortname")
        if not entry.name:
            continue

        raw_path = _clean_path(g("path", ""))
        entry.path = raw_path
        if raw_path.startswith("./"):
            entry.rom_path = (gamelist_dir / raw_path[2:]).resolve()
        elif raw_path.startswith("/") or (len(raw_path) > 1 and raw_path[1] == ":"):
            entry.rom_path = Path(raw_path)
        else:
            entry.rom_path = (gamelist_dir / raw_path).resolve()

        entry.description  = g("desc")
        entry.developer    = g("developer")
        entry.publisher    = g("publisher")
        entry.genre        = g("genre")
        entry.players      = g("players", "1")
        entry.release_date = g("releasedate")
        if entry.release_date and len(entry.release_date) >= 4:
            entry.release_year = entry.release_date[:4]
        try:
            entry.rating = float(g("rating", "0"))
        except ValueError:
            entry.rating = 0.0
        try:
            entry.play_count = int(g("playcount", "0"))
        except ValueError:
            entry.play_count = 0
        entry.last_played    = g("lastplayed")
        entry.favorite       = g("favorite", "false").lower() in ("true", "1", "yes")
        entry.hidden         = g("hidden", "false").lower() in ("true", "1", "yes")
        entry.lang           = g("lang")
        entry.region         = g("region")
        entry.scraper_id     = g("id")
        entry.scraper_source = g("source")

        raw_genre = g("genre")
        if raw_genre:
            entry.genres = [x.strip() for x in re.split(r"[,/;]", raw_genre) if x.strip()]

        # ── Media: try XML-embedded paths first ─────────────────────────
        def try_xml_media(tag: str) -> Optional[Path]:
            raw = _clean_path(g(tag, ""))
            if not raw:
                return None
            if raw.startswith("./"):
                p = (gamelist_dir / raw[2:]).resolve()
            elif os.path.isabs(raw):
                p = Path(raw)
            else:
                p = (gamelist_dir / raw).resolve()
            return p if p.exists() else None

        entry.image      = try_xml_media("image")
        entry.thumbnail  = try_xml_media("thumbnail")
        entry.marquee    = try_xml_media("marquee")
        entry.screenshot = try_xml_media("screenshot")
        entry.titleshot  = try_xml_media("titlescreen")
        entry.video      = try_xml_media("video")

        # ── Media: fall back to indexed folder scan ─────────────────────
        rom_stem = entry.rom_path.stem if entry.rom_path else Path(raw_path).stem
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", entry.name)
        stems = [rom_stem, safe_name]

        for attr in ("image", "thumbnail", "marquee", "screenshot", "titleshot", "video", "manual", "map"):
            if getattr(entry, attr) is None:
                found = _lookup_media(media_index, attr, stems)
                if found:
                    setattr(entry, attr, found)

        # ── Correct any XML mis-assignments by actual folder location ────
        # Run AFTER the folder scan so scan results don't undo corrections.
        _reassign_by_folder(entry, gamelist_dir)

        entries.append(entry)

    return entries


def scan_library(
    roms_root: Path,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    include_hidden: bool = False,
) -> List[RomEntry]:
    all_entries: List[RomEntry] = []
    if not roms_root.exists():
        return all_entries

    system_dirs = sorted([
        d for d in roms_root.iterdir()
        if d.is_dir() and (d / "gamelist.xml").exists()
    ])
    total = len(system_dirs)

    for idx, system_dir in enumerate(system_dirs):
        system_name = system_dir.name
        if progress_callback:
            progress_callback(system_name, idx + 1, total)

        entries = _parse_gamelist(system_dir / "gamelist.xml", system_name, roms_root)
        if not include_hidden:
            entries = [e for e in entries if not e.hidden]
        all_entries.extend(entries)

    return all_entries


def get_systems(roms_root: Path) -> List[Dict]:
    systems = []
    if not roms_root.exists():
        return systems
    for system_dir in sorted(roms_root.iterdir()):
        if not system_dir.is_dir():
            continue
        gamelist = system_dir / "gamelist.xml"
        if not gamelist.exists():
            continue
        try:
            import xml.etree.ElementTree as ET
            count = len(ET.parse(str(gamelist)).getroot().findall("game"))
        except Exception:
            count = 0
        systems.append({
            "name": system_dir.name,
            "full_name": SYSTEM_NAMES.get(system_dir.name.lower(), system_dir.name.upper()),
            "count": count,
            "path": system_dir,
        })
    return systems
