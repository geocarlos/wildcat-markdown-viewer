"""Render D2 diagram source to SVG by shelling out to the d2 CLI, with caching."""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .paths import cache_dir, find_d2

D2_TIMEOUT_SECONDS = 60
CREATE_NO_WINDOW = 0x08000000  # don't flash a console window from the GUI app

LIGHT_THEME = "0"     # Neutral default
DARK_THEME = "200"    # Dark Mauve


@dataclass
class D2Result:
    svg: str | None
    error: str | None


def parse_options(info_words: list[str]) -> dict[str, str]:
    """Options from the fence info string, e.g. ```d2 sketch layout=elk theme=101 pad=20"""
    opts: dict[str, str] = {}
    for word in info_words:
        if "=" in word:
            k, v = word.split("=", 1)
            opts[k.strip().lower()] = v.strip()
        elif word:
            opts[word.strip().lower()] = "true"
    return opts


def build_args(opts: dict[str, str], theme_mode: str) -> list[str]:
    args: list[str] = []
    if "theme" in opts:
        args.append(f"--theme={opts['theme']}")
        if "dark-theme" in opts:
            args.append(f"--dark-theme={opts['dark-theme']}")
    elif theme_mode == "dark":
        args.append(f"--theme={DARK_THEME}")
    elif theme_mode == "light":
        args.append(f"--theme={LIGHT_THEME}")
    else:  # auto: d2 embeds a prefers-color-scheme media query
        args += [f"--theme={LIGHT_THEME}", f"--dark-theme={opts.get('dark-theme', DARK_THEME)}"]
    if opts.get("sketch") == "true":
        args.append("--sketch")
    if "layout" in opts and opts["layout"].isalnum():
        args.append(f"--layout={opts['layout']}")
    pad = opts.get("pad", "20")
    if pad.isdigit():
        args.append(f"--pad={pad}")
    if opts.get("center") == "true":
        args.append("--center")
    return args


_INNER_SIZE_RE = re.compile(r'<svg[^>]*\bclass="[^"]*d2-svg[^"]*"[^>]*?\bwidth="(\d+(?:\.\d+)?)"\s+height="(\d+(?:\.\d+)?)"')


def _set_intrinsic_size(svg: str) -> str:
    """d2's outer <svg> only has a viewBox, so it stretches to fill the page.
    Copy the inner diagram's size onto it so small diagrams stay small."""
    m = _INNER_SIZE_RE.search(svg)
    if not m or not svg.lstrip().startswith("<svg"):
        return svg
    start = svg.index("<svg")
    return (svg[:start] + f'<svg width="{m.group(1)}" height="{m.group(2)}"'
            + svg[start + 4:])


def render_d2(source: str, info_words: list[str], theme_mode: str, cwd: Path | None) -> D2Result:
    exe = find_d2()
    if exe is None:
        return D2Result(None, "The d2 executable was not found. Install D2 from https://d2lang.com "
                              "or reinstall Wildcat Markdown Viewer.")
    args = build_args(parse_options(info_words), theme_mode)
    key = hashlib.sha256(
        "\0".join([exe, str(cwd or ""), *args, source]).encode("utf-8")
    ).hexdigest()
    cached = cache_dir() / f"d2v2-{key}.svg"
    if cached.is_file():
        try:
            return D2Result(cached.read_text(encoding="utf-8"), None)
        except OSError:
            pass
    try:
        proc = subprocess.run(
            [exe, *args, "-", "-"],
            input=source.encode("utf-8"),
            capture_output=True,
            timeout=D2_TIMEOUT_SECONDS,
            cwd=str(cwd) if cwd and cwd.is_dir() else None,
            creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return D2Result(None, f"d2 timed out after {D2_TIMEOUT_SECONDS}s")
    except OSError as e:
        return D2Result(None, f"Failed to run d2: {e}")
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip() or f"d2 exited with code {proc.returncode}"
        return D2Result(None, msg)
    svg = proc.stdout.decode("utf-8", "replace")
    # Strip the XML prolog so the SVG can be inlined into HTML.
    if svg.startswith("<?xml"):
        svg = svg[svg.index("?>") + 2:]
    svg = _set_intrinsic_size(svg)
    try:
        cached.write_text(svg, encoding="utf-8")
    except OSError:
        pass
    return D2Result(svg, None)
