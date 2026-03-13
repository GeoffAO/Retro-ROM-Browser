"""
RetroBat installation discovery and configuration parsing.

Provides:
  - RetroBatInstall: wraps a RetroBat root folder, gives typed access to all
    derived paths and parsed configs (es_settings.cfg, es_systems.cfg).
  - find_retrobat_installs(): scan common drive roots for RetroBat installs.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple  # noqa: F401 (Tuple used in method signatures)

try:
    from lxml import etree as ET
    def _parse_xml(path: Path):
        return ET.parse(str(path)).getroot()
except ImportError:
    import xml.etree.ElementTree as ET  # type: ignore
    def _parse_xml(path: Path):
        return ET.parse(str(path)).getroot()


# ── System definition as read from es_systems.cfg ──────────────────────────

@dataclass
class SystemDef:
    name: str
    fullname: str
    path: str                     # raw path from XML (may use ~ prefix)
    extensions: List[str] = field(default_factory=list)
    command: str = ""
    emulators: Dict[str, List[str]] = field(default_factory=dict)  # {emulator: [cores]}
    default_emulator: str = ""
    default_core: str = ""
    platform: str = ""

    def roms_path(self, retrobat_root: Path) -> Path:
        """Resolve ~ to retrobat_root and return absolute roms path."""
        raw = self.path.replace("~", str(retrobat_root / "emulationstation"))
        return Path(raw.replace("\\", "/"))


# ── RetroBat install wrapper ────────────────────────────────────────────────

class RetroBatInstall:
    """
    Wraps a validated RetroBat installation directory.

    Usage:
        rb = RetroBatInstall(Path("D:/RetroBat"))
        rb.ss_username        # ScreenScraper credentials from es_settings.cfg
        rb.systems["snes"]    # SystemDef for a system
        rb.launcher_exe       # Path to emulatorLauncher.exe
    """

    def __init__(self, root: Path):
        self.root = root.resolve()
        self._systems: Optional[Dict[str, SystemDef]] = None
        self._settings: Optional[Dict[str, str]] = None

    # ── Core paths ──────────────────────────────────────────────────────────

    @property
    def es_home(self) -> Path:
        """emulationstation folder inside RetroBat."""
        return self.root / "emulationstation"

    @property
    def es_config_dir(self) -> Path:
        """Hidden .emulationstation config dir."""
        return self.es_home / ".emulationstation"

    @property
    def es_input_cfg(self) -> Path:
        """Controller mapping config used by emulatorLauncher."""
        return self.es_config_dir / "es_input.cfg"

    @property
    def es_settings_path(self) -> Path:
        return self.es_config_dir / "es_settings.cfg"

    @property
    def es_systems_path(self) -> Path:
        return self.es_config_dir / "es_systems.cfg"

    @property
    def roms_root(self) -> Path:
        return self.root / "roms"

    @property
    def launcher_exe(self) -> Path:
        return self.es_home / "emulatorLauncher.exe"

    @property
    def retroarch_exe(self) -> Path:
        return self.root / "emulators" / "retroarch" / "retroarch.exe"

    @property
    def retroarch_saves_dir(self) -> Path:
        return self.root / "emulators" / "retroarch" / "saves"

    @property
    def retroarch_states_dir(self) -> Path:
        return self.root / "emulators" / "retroarch" / "states"

    @property
    def retroarch_cfg(self) -> Path:
        return self.root / "emulators" / "retroarch" / "retroarch.cfg"

    @property
    def collections_dir(self) -> Path:
        """ES custom collections directory."""
        return self.es_config_dir / "collections"

    # ── Validation ──────────────────────────────────────────────────────────

    def is_valid(self) -> bool:
        """Return True if this looks like a real RetroBat install."""
        return (
            self.es_home.is_dir()
            and self.launcher_exe.exists()
        )

    # ── es_settings.cfg ─────────────────────────────────────────────────────

    @property
    def _raw_settings(self) -> Dict[str, str]:
        if self._settings is None:
            self._settings = _parse_es_settings(self.es_settings_path)
        return self._settings

    @property
    def ss_username(self) -> str:
        return self._raw_settings.get("ScreenScraperUser", "")

    @property
    def ss_password(self) -> str:
        return self._raw_settings.get("ScreenScraperPass", "")

    def get_setting(self, name: str, default: str = "") -> str:
        return self._raw_settings.get(name, default)

    def invalidate_settings_cache(self):
        self._settings = None

    # ── es_systems.cfg ──────────────────────────────────────────────────────

    @property
    def systems(self) -> Dict[str, SystemDef]:
        if self._systems is None:
            self._systems = _parse_es_systems(self.es_systems_path)
        return self._systems

    def system_def(self, system_name: str) -> Optional[SystemDef]:
        return self.systems.get(system_name.lower())

    def invalidate_systems_cache(self):
        self._systems = None

    # ── Launch command building ──────────────────────────────────────────────

    def resolve_emulator_core(self, system: str, emulator: str = "", core: str = "") -> Tuple[str, str]:
        """
        Return (emulator, core) for the system, filling in defaults from:
          1. Caller-supplied values (highest priority)
          2. es_settings.cfg  per-system overrides:  {system}.emulator / {system}.core
          3. es_systems.cfg  first emulator / first core declared for that system

        Returns ("", "") if nothing can be resolved — emulatorLauncher will use
        its own internal defaults in that case.
        """
        sname = system.lower()

        # 1. Caller values
        emu = emulator.strip()
        cor = core.strip()

        # 2. es_settings.cfg overrides
        if not emu:
            emu = self.get_setting(f"{sname}.emulator", "")
        if not cor:
            cor = self.get_setting(f"{sname}.core", "")

        # 3. es_systems.cfg defaults
        sdef = self.system_def(sname)
        if sdef:
            if not emu:
                emu = sdef.default_emulator
            if not cor:
                # if emulator is libretro, use the first configured core; otherwise leave blank
                if emu == "libretro" and sdef.emulators.get("libretro"):
                    cor = sdef.emulators["libretro"][0]

        return emu, cor

    def build_launch_args(
        self,
        system: str,
        rom_path: Path,
        gamelist_xml: Optional[Path] = None,
        emulator: str = "",
        core: str = "",
    ) -> List[str]:
        """
        Return the argv list to launch rom_path for the given system.

        Resolves emulator/core from system defaults when not explicitly provided.
        emulatorLauncher.exe is called directly — no EmulationStation required.
        """
        emu, cor = self.resolve_emulator_core(system, emulator, core)

        args = [str(self.launcher_exe), "-system", system]

        # Only pass -emulator / -core when we have valid names
        if emu:
            args += ["-emulator", emu]
        if cor:
            args += ["-core", cor]

        args += ["-rom", str(rom_path)]

        if gamelist_xml and gamelist_xml.exists():
            args += ["-gameinfo", str(gamelist_xml)]

        # Pass controller config so gamepads are recognised
        if self.es_input_cfg.exists():
            args += ["-controllers", str(self.es_input_cfg)]

        return args

    def __repr__(self) -> str:
        return f"RetroBatInstall({self.root})"


# ── Discovery ───────────────────────────────────────────────────────────────

def find_retrobat_installs() -> List[RetroBatInstall]:
    """
    Scan all drive letters for RetroBat installations.
    Returns a list of valid installs ordered by likelihood (real drives first).
    """
    candidates: List[Path] = []

    # Common explicit names to try on each drive
    FOLDER_NAMES = ["RetroBat", "retrobat", "RETROBAT"]

    import platform
    if platform.system() == "Windows":
        # Check every available drive letter
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:/")
            if not drive.exists():
                continue
            for name in FOLDER_NAMES:
                candidates.append(drive / name)
            # Also check root of drive itself if it looks like a portable install
            candidates.append(drive)
    else:
        # Linux / macOS: common mount points
        for base in [Path.home(), Path("/opt"), Path("/mnt")]:
            for name in FOLDER_NAMES:
                candidates.append(base / name)

    results: List[RetroBatInstall] = []
    seen: set = set()
    for path in candidates:
        try:
            rb = RetroBatInstall(path)
            key = str(rb.root)
            if key not in seen and rb.is_valid():
                seen.add(key)
                results.append(rb)
        except Exception:
            pass
    return results


# ── Parsers ─────────────────────────────────────────────────────────────────

def _parse_es_settings(path: Path) -> Dict[str, str]:
    """
    Parse es_settings.cfg XML into a flat {name: value} dict.

    Handles <bool>, <int>, and <string> elements, returning all values as str.
    """
    result: Dict[str, str] = {}
    if not path.exists():
        return result
    try:
        root = _parse_xml(path)
        for elem in root:
            name = elem.get("name", "")
            value = elem.get("value", "")
            if name:
                result[name] = value
    except Exception as e:
        print(f"[WARN] Could not parse es_settings.cfg: {e}")
    return result


def _parse_es_systems(path: Path) -> Dict[str, SystemDef]:
    """
    Parse es_systems.cfg and return {system_name: SystemDef}.
    """
    result: Dict[str, SystemDef] = {}
    if not path.exists():
        return result
    try:
        root = _parse_xml(path)
        for sys_el in root.findall("system"):
            name = _text(sys_el, "name")
            if not name:
                continue
            fullname = _text(sys_el, "fullname") or name
            path_raw = _text(sys_el, "path") or ""
            command = _text(sys_el, "command") or ""
            platform = _text(sys_el, "platform") or ""

            # Extensions
            ext_raw = _text(sys_el, "extension") or ""
            extensions = [e.lower() for e in ext_raw.split() if e.startswith(".")]

            # Emulators
            emulators: Dict[str, List[str]] = {}
            default_emulator = ""
            default_core = ""
            emulators_el = sys_el.find("emulators")
            if emulators_el is not None:
                for emu_el in emulators_el.findall("emulator"):
                    emu_name = emu_el.get("name", "")
                    if not emu_name:
                        continue
                    cores: List[str] = []
                    cores_el = emu_el.find("cores")
                    if cores_el is not None:
                        for core_el in cores_el.findall("core"):
                            core_name = (core_el.text or "").strip()
                            if core_name:
                                cores.append(core_name)
                    emulators[emu_name] = cores
                    if not default_emulator:
                        default_emulator = emu_name
                        if cores:
                            default_core = cores[0]

            sdef = SystemDef(
                name=name,
                fullname=fullname,
                path=path_raw,
                extensions=extensions,
                command=command,
                emulators=emulators,
                default_emulator=default_emulator,
                default_core=default_core,
                platform=platform,
            )
            result[name.lower()] = sdef
    except Exception as e:
        print(f"[WARN] Could not parse es_systems.cfg: {e}")
    return result


def _text(el, tag: str) -> str:
    child = el.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return ""
