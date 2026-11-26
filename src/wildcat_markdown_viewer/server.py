"""Loopback HTTP server that feeds the WebView.

URL layout (everything sits under a random per-process token):

    /<tok>/doc/C:/dir/file.md     rendered markdown page (relative links/images resolve naturally)
    /<tok>/doc/C:/dir/img.png     raw local file (images, media, ...)
    /<tok>/fragment/C:/dir/x.md   JSON {html, title, mtime} for live reload
    /<tok>/stat/C:/dir/x.md       JSON {mtime}
    /<tok>/home                   start page
    /<tok>/_app/...               bundled assets (CSS/JS/fonts)
    /<tok>/pygments.css           syntax-highlighting theme

Markdown can contain raw HTML, so every page is served with a strict CSP:
only <script> tags carrying the per-response nonce may run.
"""

from __future__ import annotations

import json
import mimetypes
import secrets
import threading
from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from . import __version__
from .paths import APP_NAME, assets_dir, find_d2, is_markdown
from .renderer import RenderEnv, first_heading, pygments_css, render_markdown
from .settings import Settings

GITHUB_CSS = {"auto": "github-markdown.css", "light": "github-markdown-light.css",
              "dark": "github-markdown-dark.css"}

mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/webp", ".webp")
mimetypes.add_type("image/avif", ".avif")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")


def path_to_url_part(path: Path) -> str:
    s = str(path).replace("\\", "/")
    return quote(s, safe="/:")


def url_part_to_path(part: str) -> Path | None:
    s = unquote(part)
    if len(s) >= 3 and s[0].isalpha() and s[1] == ":" and s[2] == "/":
        return Path(s)
    if s.startswith("//") and len(s) > 2:  # UNC share
        return Path(s)
    if len(s) == 2 and s[0].isalpha() and s[1] == ":":
        return Path(s + "/")
    return None


@dataclass
class _Rendered:
    key: tuple
    html: str
    title: str


class ViewerServer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.token = secrets.token_urlsafe(16)
        self._cache: dict[str, _Rendered] = {}
        self._cache_lock = threading.Lock()
        self._pyg_css = pygments_css().encode("utf-8")
        handler = type("Handler", (_Handler,), {"app": self})
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="wmv-http", daemon=True)

    # -- URLs ---------------------------------------------------------------
    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def prefix(self) -> str:
        return f"/{self.token}"

    def doc_url(self, path: Path | str) -> str:
        return f"{self.origin}{self.prefix}/doc/{path_to_url_part(Path(path).resolve())}"

    def home_url(self) -> str:
        return f"{self.origin}{self.prefix}/home"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()

    # -- rendering ------------------------------------------------------------
    def render(self, path: Path) -> _Rendered:
        st = path.stat()
        key = (st.st_mtime_ns, st.st_size, self.settings.theme)
        cache_key = str(path).lower()
        with self._cache_lock:
            hit = self._cache.get(cache_key)
            if hit and hit.key == key:
                return hit
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
        env = RenderEnv(theme=self.settings.theme, base_dir=path.parent,
                        doc_prefix=f"{self.prefix}/doc/")
        html = render_markdown(text, env)
        title = first_heading(text) or path.name
        result = _Rendered(key, html, title)
        with self._cache_lock:
            self._cache[cache_key] = result
            if len(self._cache) > 64:
                self._cache.pop(next(iter(self._cache)))
        return result

    def page(self, *, title: str, body: str, nonce: str, doc: Path | None = None,
             mtime: int = 0, body_class: str = "") -> str:
        a = f"{self.prefix}/_app"
        theme = self.settings.theme
        config = {
            "prefix": self.prefix,
            "doc": str(doc) if doc else None,
            "docUrlPart": path_to_url_part(doc) if doc else None,
            "mtime": mtime,
            "theme": theme,
            "outline": self.settings.show_outline,
            "version": __version__,
        }
        config_json = json.dumps(config).replace("<", "\\u003c")
        return f"""<!DOCTYPE html>
<html lang="en" data-theme="{theme}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="stylesheet" href="{a}/github/{GITHUB_CSS.get(theme, GITHUB_CSS['auto'])}">
<link rel="stylesheet" href="{a}/katex/katex.min.css">
<link rel="stylesheet" href="{self.prefix}/pygments.css">
<link rel="stylesheet" href="{a}/app.css">
<script type="application/json" id="wmv-config">{config_json}</script>
</head>
<body class="{body_class}">
<header id="toolbar" role="toolbar">
  <button data-cmd="open" title="Open file (Ctrl+O)">📂 Open</button>
  <button data-cmd="back" title="Back (Alt+←)">◀</button>
  <button data-cmd="forward" title="Forward (Alt+→)">▶</button>
  <button data-cmd="reload" title="Reload (F5)">⟳</button>
  <button data-cmd="outline" title="Outline (Ctrl+Shift+O)">☰ Outline</button>
  <span id="docpath" title="{escape(str(doc) if doc else '')}">{escape(str(doc) if doc else '')}</span>
  <span class="spacer"></span>
  <span id="status"></span>
  <button data-cmd="edit" title="Open in editor (Ctrl+E)" {'' if doc else 'hidden'}>✎ Edit</button>
  <button data-cmd="reveal" title="Show in Explorer" {'' if doc else 'hidden'}>📁</button>
  <button data-cmd="find" title="Find (Ctrl+F)">🔍</button>
  <button data-cmd="print" title="Print / Save as PDF (Ctrl+P)">🖶</button>
  <select id="theme" title="Theme (Ctrl+T)">
    <option value="auto">Auto</option><option value="light">Light</option><option value="dark">Dark</option>
  </select>
</header>
<div id="findbar" hidden>
  <input id="findinput" type="search" placeholder="Find in page" autocomplete="off">
  <button data-cmd="findprev" title="Previous (Shift+Enter)">▲</button>
  <button data-cmd="findnext" title="Next (Enter)">▼</button>
  <button data-cmd="findclose" title="Close (Esc)">✕</button>
</div>
<div id="layout">
  <nav id="outline" aria-label="Outline"></nav>
  <main id="main">
    <article id="content" class="markdown-body">
{body}
    </article>
  </main>
</div>
<script nonce="{nonce}" src="{a}/app.js"></script>
</body>
</html>"""

    def home_body(self) -> str:
        items = []
        for p in self.settings.recent:
            path = Path(p)
            if path.exists():
                items.append(
                    f'<li><a href="{self.prefix}/doc/{path_to_url_part(path)}">{escape(path.name)}</a>'
                    f' <span class="muted">{escape(str(path.parent))}</span></li>'
                )
        recent = (f"<h2>Recent files</h2><ul class=\"recent\">{''.join(items)}</ul>" if items else "")
        d2 = find_d2()
        d2_note = (f'<p class="muted">D2: <code>{escape(d2)}</code></p>' if d2 else
                   '<div class="markdown-alert markdown-alert-warning"><p class="markdown-alert-title">Warning</p>'
                   "<p>The <code>d2</code> executable was not found; D2 diagrams will not render.</p></div>")
        return f"""
<div class="brand"><img src="{self.prefix}/_app/logo.svg" alt="" width="96" height="96">
<h1>{escape(APP_NAME)}</h1></div>
<p>Open a Markdown file with <kbd>Ctrl</kbd>+<kbd>O</kbd>, or drag &amp; drop one onto this window.</p>
<p><button class="primary" data-cmd="open">Open a file…</button></p>
{recent}
<h2>Supports</h2>
<p>GitHub Flavored Markdown (tables, task lists, strikethrough, autolinks, footnotes, alerts, emoji),
syntax highlighting, math (KaTeX), Mermaid and D2 diagrams, live reload on save.</p>
{d2_note}
<p class="muted">Version {escape(__version__)}</p>
"""

    def dir_body(self, path: Path) -> str:
        rows = []
        if path.parent != path:
            rows.append(f'<li><a href="{self.prefix}/doc/{path_to_url_part(path.parent)}/">..</a></li>')
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as e:
            return f"<h1>{escape(str(path))}</h1><p>{escape(str(e))}</p>"
        for e in entries:
            if e.name.startswith("."):
                continue
            if e.is_dir():
                rows.append(f'<li>📁 <a href="{self.prefix}/doc/{path_to_url_part(e)}/">{escape(e.name)}/</a></li>')
            elif is_markdown(e):
                rows.append(f'<li>📄 <a href="{self.prefix}/doc/{path_to_url_part(e)}">{escape(e.name)}</a></li>')
        return f"<h1>{escape(str(path))}</h1><ul class=\"dirlist\">{''.join(rows)}</ul>"


class _Handler(BaseHTTPRequestHandler):
    app: ViewerServer
    server_version = "WildcatMarkdownViewer"
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # silence console logging
        pass

    # -- helpers ----------------------------------------------------------------
    def _send(self, status: int, body: bytes, ctype: str, *, nonce: str | None = None,
              cache: bool = False, sandbox: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-store")
        if nonce is not None:
            self.send_header(
                "Content-Security-Policy",
                f"default-src 'self'; script-src 'nonce-{nonce}'; "
                "style-src 'self' 'unsafe-inline'; img-src * data: blob:; media-src *; "
                "font-src 'self' data:; connect-src 'self'; object-src 'none'; "
                "frame-src 'none'; base-uri 'none'; form-action 'none'",
            )
        elif sandbox:
            self.send_header("Content-Security-Policy",
                             "sandbox; default-src 'none'; img-src 'self' data:; "
                             "media-src 'self'; style-src 'unsafe-inline'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data) -> None:
        self._send(200, json.dumps(data).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        nonce = secrets.token_urlsafe(12)
        body = self.app.page(title="Error", nonce=nonce,
                             body=f"<h1>{status}</h1><p>{escape(message)}</p>")
        self._send(status, body.encode("utf-8"), "text/html; charset=utf-8", nonce=nonce)

    def _html_page(self, **kw) -> None:
        nonce = secrets.token_urlsafe(12)
        body = self.app.page(nonce=nonce, **kw)
        self._send(200, body.encode("utf-8"), "text/html; charset=utf-8", nonce=nonce)

    def _file(self, path: Path, *, cache: bool = False) -> None:
        try:
            data = path.read_bytes()
        except OSError:
            self._error(404, f"Not found: {path}")
            return
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        # Raw local files (not our own assets) never get to run script.
        self._send(200, data, ctype, cache=cache, sandbox=not cache)

    # -- routing ------------------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        host = self.headers.get("Host", "")
        if host not in (f"127.0.0.1:{self.app.port}", f"localhost:{self.app.port}"):
            self._send(403, b"forbidden", "text/plain")
            return
        url = urlsplit(self.path)
        prefix = self.app.prefix + "/"
        if not url.path.startswith(prefix):
            self._send(404, b"not found", "text/plain")
            return
        route, _, rest = url.path[len(prefix):].partition("/")
        try:
            if route == "home":
                self._html_page(title="Wildcat Markdown Viewer", body=self.app.home_body(),
                                body_class="home")
            elif route == "_app":
                self._asset(unquote(rest))
            elif route == "pygments.css":
                self._send(200, self.app._pyg_css, "text/css; charset=utf-8")
            elif route in ("doc", "fragment", "stat"):
                path = url_part_to_path(rest)
                if path is None:
                    self._error(404, f"Invalid path: {unquote(rest)}")
                    return
                getattr(self, f"_route_{route}")(path, url.path.endswith("/"))
            else:
                self._send(404, b"not found", "text/plain")
        except (ConnectionError, TimeoutError):
            pass
        except Exception as e:  # pragma: no cover - last-resort error page
            self._error(500, f"{type(e).__name__}: {e}")

    def _asset(self, rel: str) -> None:
        base = assets_dir().resolve()
        target = (base / rel).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            self._send(404, b"not found", "text/plain")
            return
        self._file(target, cache=True)

    def _route_doc(self, path: Path, trailing_slash: bool) -> None:
        if path.is_dir():
            for name in ("README.md", "readme.md", "index.md", "Readme.md"):
                if (path / name).is_file():
                    self.send_response(302)
                    self.send_header("Location", f"{self.app.prefix}/doc/{path_to_url_part(path / name)}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
            self._html_page(title=str(path), body=self.app.dir_body(path), body_class="dir")
            return
        if not path.is_file():
            self._error(404, f"File not found: {path}")
            return
        if is_markdown(path):
            r = self.app.render(path)
            self.app.settings.add_recent(str(path))
            self._html_page(title=r.title, body=r.html, doc=path, mtime=r.key[0])
            return
        self._file(path)

    def _route_fragment(self, path: Path, _slash: bool) -> None:
        if not path.is_file():
            self._json({"error": "missing"})
            return
        r = self.app.render(path)
        self._json({"html": r.html, "title": r.title, "mtime": r.key[0]})

    def _route_stat(self, path: Path, _slash: bool) -> None:
        try:
            self._json({"mtime": path.stat().st_mtime_ns})
        except OSError:
            self._json({"mtime": None})
