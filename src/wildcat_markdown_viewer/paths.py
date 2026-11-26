"""Filesystem locations.

The app is installed read-only under Program Files, so anything writable goes
to per-user locations (%APPDATA% for settings, %LOCALAPPDATA% for caches).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Wildcat Markdown Viewer"
APP_DIR_NAME = "WildcatMarkdownViewer"

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd", ".mkdn", ".mdwn", ".mdtxt", ".mdtext"}


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def install_dir() -> Path:
    """Directory containing the executable (frozen) or the package (dev)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def assets_dir() -> Path:
    if is_frozen():
        # PyInstaller one-folder: data lives under _internal (sys._MEIPASS).
        base = Path(getattr(sys, "_MEIPASS", install_dir()))
        return base / "wildcat_markdown_viewer" / "assets"
    return Path(__file__).resolve().parent / "assets"


def _env_dir(var: str, fallback: Path) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else fallback


def config_dir() -> Path:
    d = _env_dir("APPDATA", Path.home() / "AppData" / "Roaming") / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    d = _env_dir("LOCALAPPDATA", Path.home() / "AppData" / "Local") / APP_DIR_NAME / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_d2() -> str | None:
    """Prefer the d2.exe bundled next to the app, then PATH, then default install dirs."""
    candidates = [install_dir() / "d2" / "d2.exe", install_dir() / "d2.exe"]
    for c in candidates:
        if c.is_file():
            return str(c)
    found = shutil.which("d2")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            for sub in ("D2", r"Programs\D2"):
                p = Path(base) / sub / "d2.exe"
                if p.is_file():
                    return str(p)
    return None


def is_markdown(path: Path) -> bool:
    return path.suffix.lower() in MARKDOWN_EXTENSIONS
