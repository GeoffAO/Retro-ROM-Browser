"""
Data models for ROM entries and system definitions.
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class RomEntry:
    """Represents a single ROM with all its metadata from gamelist.xml."""

    # Identity
    system: str = ""
    system_full_name: str = ""
    name: str = ""
    path: str = ""           # path to ROM file (relative in XML)
    rom_path: Path = field(default_factory=Path)  # absolute resolved path

    # Metadata
    description: str = ""
    developer: str = ""
    publisher: str = ""
    genre: str = ""
    genres: list = field(default_factory=list)
    players: str = ""
    release_date: str = ""   # raw YYYYMMDDTHHMMSS format
    release_year: str = ""
    rating: float = 0.0      # 0.0 – 1.0
    play_count: int = 0
    last_played: str = ""
    favorite: bool = False
    hidden: bool = False
    lang: str = ""
    region: str = ""

    # Media paths (absolute)
    image: Optional[Path] = None        # box art / front cover
    thumbnail: Optional[Path] = None    # small thumbnail
    marquee: Optional[Path] = None      # marquee / wheel art
    screenshot: Optional[Path] = None   # in-game screenshot
    titleshot: Optional[Path] = None    # title screen
    video: Optional[Path] = None        # video snap
    manual: Optional[Path] = None       # PDF manual
    map: Optional[Path] = None          # map image

    # Scraper info
    scraper_id: str = ""
    scraper_source: str = ""

    # Personal / library management
    notes: str = ""                  # free-text personal notes
    backlog_status: str = ""         # "unplayed" | "in_progress" | "completed" | ""

    @property
    def display_rating(self) -> str:
        """Return rating as star count string."""
        if self.rating <= 0:
            return ""
        stars = round(self.rating * 5)
        return "★" * stars + "☆" * (5 - stars)

    @property
    def year(self) -> str:
        """Extract year from release_date."""
        if self.release_year:
            return self.release_year
        if self.release_date and len(self.release_date) >= 4:
            return self.release_date[:4]
        return ""

    @property
    def best_image(self) -> Optional[Path]:
        """Return the best available image for the grid/cover display.

        In RetroBat, <thumbnail> in gamelist.xml reliably holds the box art
        (named_boxarts / dedicated cover scan), while <image> holds a scraper
        mix composite.  Try thumbnail first so the grid always shows the clean
        box art; fall back through image → marquee → titleshot → screenshot.
        """
        for attr in ("thumbnail", "image", "marquee", "titleshot", "screenshot"):
            val = getattr(self, attr)
            if val and val.exists():
                return val
        return None

    @property
    def file_size_mb(self) -> float:
        """Return ROM file size in MB."""
        try:
            if self.rom_path and self.rom_path.exists():
                return self.rom_path.stat().st_size / (1024 * 1024)
        except Exception:
            pass
        return 0.0

    @property
    def file_extension(self) -> str:
        """Return ROM file extension."""
        if self.rom_path:
            return self.rom_path.suffix.lstrip(".").upper()
        return ""


# Well-known RetroBat system names → human-readable
SYSTEM_NAMES = {
    "3do": "3DO Interactive Multiplayer",
    "amstradcpc": "Amstrad CPC",
    "apple2": "Apple II",
    "arcade": "Arcade",
    "atari2600": "Atari 2600",
    "atari5200": "Atari 5200",
    "atari7800": "Atari 7800",
    "atarist": "Atari ST",
    "c64": "Commodore 64",
    "colecovision": "ColecoVision",
    "dreamcast": "Sega Dreamcast",
    "ds": "Nintendo DS",
    "fba": "FinalBurn Alpha",
    "fds": "Famicom Disk System",
    "gb": "Game Boy",
    "gba": "Game Boy Advance",
    "gbc": "Game Boy Color",
    "gamegear": "Sega Game Gear",
    "genesis": "Sega Genesis / Mega Drive",
    "gw": "Game & Watch",
    "intellivision": "Intellivision",
    "jaguar": "Atari Jaguar",
    "lynx": "Atari Lynx",
    "mame": "MAME Arcade",
    "mastersystem": "Sega Master System",
    "megadrive": "Sega Mega Drive",
    "msx": "MSX",
    "n64": "Nintendo 64",
    "naomi": "Sega NAOMI",
    "nds": "Nintendo DS",
    "neogeo": "SNK Neo Geo",
    "nes": "Nintendo Entertainment System",
    "ngp": "Neo Geo Pocket",
    "ngpc": "Neo Geo Pocket Color",
    "odyssey2": "Magnavox Odyssey 2",
    "pcengine": "PC Engine / TurboGrafx-16",
    "pcfx": "NEC PC-FX",
    "ports": "PC Ports",
    "ps2": "PlayStation 2",
    "ps3": "PlayStation 3",
    "psp": "PlayStation Portable",
    "psx": "PlayStation",
    "saturn": "Sega Saturn",
    "scummvm": "ScummVM",
    "sega32x": "Sega 32X",
    "segacd": "Sega CD / Mega-CD",
    "sg1000": "Sega SG-1000",
    "snes": "Super Nintendo",
    "supergrafx": "PC Engine SuperGrafx",
    "switch": "Nintendo Switch",
    "vectrex": "Vectrex",
    "vic20": "Commodore VIC-20",
    "virtualboy": "Virtual Boy",
    "wii": "Nintendo Wii",
    "wiiu": "Nintendo Wii U",
    "wonderswan": "WonderSwan",
    "wonderswancolor": "WonderSwan Color",
    "x68000": "Sharp X68000",
    "xbox": "Microsoft Xbox",
    "xbox360": "Microsoft Xbox 360",
    "zxspectrum": "ZX Spectrum",
}

# System → color accent (for theming)
SYSTEM_COLORS = {
    "nes": "#E4000F",
    "snes": "#7B47A3",
    "n64": "#2E6DB4",
    "gb": "#8BAC0F",
    "gba": "#8B1A7A",
    "gbc": "#009B48",
    "nds": "#CC0000",
    "genesis": "#1A67B2",
    "megadrive": "#1A67B2",
    "mastersystem": "#CC0000",
    "dreamcast": "#FF6600",
    "saturn": "#2244AA",
    "psx": "#003087",
    "ps2": "#003087",
    "psp": "#003087",
    "arcade": "#FF2222",
    "mame": "#FF2222",
    "neogeo": "#BF0000",
    "atari2600": "#AA4400",
    "c64": "#7B7B9B",
    "default": "#4A90D9",
}


def get_system_color(system: str) -> str:
    return SYSTEM_COLORS.get(system.lower(), SYSTEM_COLORS["default"])
