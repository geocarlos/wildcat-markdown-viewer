"""Persistent per-user settings stored as JSON in %APPDATA%."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import config_dir

THEMES = ("auto", "light", "dark")
MAX_RECENT = 12


@dataclass
class Settings:
    theme: str = "auto"
    recent: list[str] = field(default_factory=list)
    width: int = 1100
    height: int = 850
    show_outline: bool = False

    _lock = threading.Lock()

    @classmethod
    def file(cls) -> Path:
        return config_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(cls.file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        s = cls()
        if data.get("theme") in THEMES:
            s.theme = data["theme"]
        if isinstance(data.get("recent"), list):
            s.recent = [str(p) for p in data["recent"] if isinstance(p, str)][:MAX_RECENT]
        for key in ("width", "height"):
            if isinstance(data.get(key), int) and 300 <= data[key] <= 10000:
                setattr(s, key, data[key])
        s.show_outline = bool(data.get("show_outline", False))
        return s

    def save(self) -> None:
        with self._lock:
            try:
                tmp = self.file().with_suffix(".tmp")
                tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
                tmp.replace(self.file())
            except OSError:
                pass

    def add_recent(self, path: str) -> None:
        norm = str(Path(path).resolve())
        self.recent = [norm] + [p for p in self.recent if p.lower() != norm.lower()]
        del self.recent[MAX_RECENT:]
        self.save()
