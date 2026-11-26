"""Desktop window (pywebview / Edge WebView2) and the JS bridge API."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import webview
from webview.dom import DOMEventHandler

from . import __version__
from .paths import APP_NAME, assets_dir, cache_dir, is_markdown
from .server import ViewerServer
from .settings import THEMES, Settings

MD_FILTER = ("Markdown files (*.md;*.markdown;*.mdown;*.mkd;*.mkdn;*.mdwn;*.mdtxt;*.mdtext)",
             "All files (*.*)")


class Api:
    """Methods callable from JavaScript as window.pywebview.api.<name>(...)."""

    def __init__(self, app: "ViewerApp") -> None:
        self._app = app

    def open_dialog(self) -> str | None:
        w = self._app.window
        start_dir = ""
        if self._app.settings.recent:
            start_dir = str(Path(self._app.settings.recent[0]).parent)
        result = w.create_file_dialog(webview.FileDialog.OPEN, directory=start_dir,
                                      file_types=MD_FILTER)
        if not result:
            return None
        return self._app.server.doc_url(result[0])

    def open_external(self, url: str) -> None:
        if isinstance(url, str) and url.lower().startswith(("http://", "https://", "mailto:")):
            webbrowser.open(url)

    def open_path(self, path: str) -> None:
        """Open a linked non-markdown local file with its default Windows handler."""
        p = Path(path)
        if p.exists():
            try:
                os.startfile(str(p))  # noqa: S606 - user clicked a local link
            except OSError:
                self.reveal(str(p))

    def edit(self, path: str) -> None:
        p = Path(path)
        if not p.is_file():
            return
        try:
            os.startfile(str(p), "edit")
        except OSError:
            subprocess.Popen(["notepad.exe", str(p)])

    def reveal(self, path: str) -> None:
        subprocess.Popen(["explorer.exe", "/select,", str(Path(path))])

    def set_theme(self, theme: str) -> None:
        if theme in THEMES:
            self._app.settings.theme = theme
            self._app.settings.save()

    def set_outline(self, show: bool) -> None:
        self._app.settings.show_outline = bool(show)
        self._app.settings.save()

    def set_title(self, title: str) -> None:
        if isinstance(title, str):
            self._app.window.title = f"{title} - {APP_NAME}" if title != APP_NAME else APP_NAME


class ViewerApp:
    def __init__(self, initial: Path | None) -> None:
        self.settings = Settings.load()
        self.server = ViewerServer(self.settings)
        self.server.start()
        self.window: webview.Window | None = None
        self._initial = initial
        self._size_timer: threading.Timer | None = None

    def start_url(self) -> str:
        if self._initial is not None:
            return self.server.doc_url(self._initial)
        return self.server.home_url()

    # -- events ---------------------------------------------------------------------
    def _on_loaded(self, window: webview.Window) -> None:
        # DOM handlers must be re-bound after every navigation.
        try:
            doc = window.dom.document
            doc.events.dragover += DOMEventHandler(_noop, prevent_default=True)
            doc.events.drop += DOMEventHandler(self._on_drop, prevent_default=True)
        except Exception:
            pass

    def _on_drop(self, event: dict) -> None:
        files = (event.get("dataTransfer") or {}).get("files") or []
        for f in files:
            full = f.get("pywebviewFullPath")
            if full:
                p = Path(full)
                if p.is_dir() or is_markdown(p) or p.suffix.lower() == ".txt":
                    self.window.load_url(self.server.doc_url(p))
                    return

    def _on_resized(self, width: int, height: int) -> None:
        if self.window is None or width < 300 or height < 300:
            return
        self.settings.width, self.settings.height = int(width), int(height)
        if self._size_timer:
            self._size_timer.cancel()
        self._size_timer = threading.Timer(1.0, self.settings.save)
        self._size_timer.daemon = True
        self._size_timer.start()

    def run(self, debug: bool = False) -> None:
        self.window = webview.create_window(
            APP_NAME,
            url=self.start_url(),
            js_api=Api(self),
            width=self.settings.width,
            height=self.settings.height,
            min_size=(480, 360),
            text_select=True,
            zoomable=False,
            background_color="#0d1117" if self.settings.theme == "dark" else "#FFFFFF",
        )
        self.window.events.loaded += self._on_loaded
        self.window.events.resized += self._on_resized
        icon = assets_dir() / "icon.ico"
        webview.start(
            gui="edgechromium",
            debug=debug,
            private_mode=False,
            storage_path=str(cache_dir().parent / "webview"),
            icon=str(icon) if icon.is_file() else None,
        )
        self.settings.save()
        self.server.stop()


def _noop(_event) -> None:
    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wildcat-md", description=f"{APP_NAME} {__version__}")
    parser.add_argument("file", nargs="?", help="Markdown file or folder to open")
    parser.add_argument("--debug", action="store_true", help="enable WebView developer tools")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)

    initial = None
    if args.file:
        p = Path(args.file).expanduser()
        initial = p.resolve() if p.exists() else None
    ViewerApp(initial).run(debug=args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
