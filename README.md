<p align="center"><img src="src/wildcat_markdown_viewer/assets/logo.svg" width="128" alt="Wildcat logo"></p>

# Wildcat Markdown Viewer

A fast, GitHub-style Markdown viewer for Windows with built-in **D2** diagram support.

## Features

- **GitHub look**: GitHub's own `github-markdown-css`, with light, dark and auto (follow Windows) themes
- **GitHub Flavored Markdown**: tables, task lists, strikethrough, autolinks, footnotes, raw HTML
  (`<details>`, `<kbd>`, `<sub>` …), heading anchors, YAML front matter
- **Alerts**: `> [!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`, `[!CAUTION]`
- **Emoji** shortcodes (`:tada:`)
- **Syntax highlighting** for ~600 languages (Pygments), with copy buttons
- **Math**: `$inline$`, `$$display$$` and ` ```math ` blocks (KaTeX)
- **Mermaid** diagrams (` ```mermaid `)
- **D2** diagrams (` ```d2 `), rendered with the bundled `d2.exe`; follows the app theme
- **Live reload** when the file changes on disk, preserving the scroll position
- Relative images and links, links between `.md` files (with Back/Forward), folder browsing
- Outline sidebar, find in page, zoom, print / Save as PDF, open in editor, show in Explorer
- Drag & drop files onto the window; recent files on the start page
- Works fully offline; all JS/CSS is bundled

### D2 fence options (viewer extension)

````markdown
```d2 sketch layout=elk theme=101 pad=40 center
a -> b
```
````

| Option         | Effect                                               |
| -------------- | ---------------------------------------------------- |
| `sketch`       | hand-drawn look                                      |
| `layout=<eng>` | layout engine (`dagre`, `elk`)                       |
| `theme=<id>`   | fixed D2 theme id (overrides the app theme)          |
| `dark-theme=<id>` | dark-mode theme id                                |
| `pad=<px>`     | padding (default 20)                                 |
| `center`       | center the diagram in its viewbox                    |

D2 imports (`...@other.d2`) resolve relative to the Markdown file's folder.

## Keyboard shortcuts

| Keys                        | Action                    |
| --------------------------- | ------------------------- |
| <kbd>Ctrl</kbd>+<kbd>O</kbd> | Open file                |
| <kbd>F5</kbd> / <kbd>Ctrl</kbd>+<kbd>R</kbd> | Reload   |
| <kbd>Alt</kbd>+<kbd>←</kbd> / <kbd>→</kbd> | Back / Forward |
| <kbd>Ctrl</kbd>+<kbd>F</kbd>, <kbd>F3</kbd> | Find / next |
| <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>O</kbd> | Toggle outline |
| <kbd>Ctrl</kbd>+<kbd>T</kbd> | Cycle theme (auto/light/dark) |
| <kbd>Ctrl</kbd>+<kbd>E</kbd> | Open in editor           |
| <kbd>Ctrl</kbd>+<kbd>P</kbd> | Print / Save as PDF      |
| <kbd>Ctrl</kbd>+<kbd>+</kbd>/<kbd>-</kbd>/<kbd>0</kbd>, <kbd>Ctrl</kbd>+wheel | Zoom |

Command line: `WildcatMD.exe [file.md | folder]`

## Install

Run `WildcatMD-Setup-<version>.exe`. It installs per machine (for all users) into
`C:\Program Files\Wildcat Markdown Viewer`, adds Start-menu shortcuts and, optionally, an
"Open with" entry for `.md` / `.markdown` files. To make it the default viewer, right-click a
`.md` file → *Open with* → *Choose another app* → **Wildcat Markdown Viewer** → *Always*.

Silent install: `WildcatMD-Setup-0.1.1.exe /VERYSILENT /SUPPRESSMSGBOXES`

Requires Windows 10 1809+ (x64) and the Microsoft Edge WebView2 Runtime (preinstalled on Windows 11).

Per-user data: settings in `%APPDATA%\WildcatMarkdownViewer`, caches in
`%LOCALAPPDATA%\WildcatMarkdownViewer`.

## Development

Requires [uv](https://docs.astral.sh/uv/). D2 and Inno Setup 6 are needed for a full build.

```powershell
uv sync
uv run wildcat-markdown-viewer samples\feature-tour.md   # run from source
uv run wildcat-markdown-viewer --debug README.md         # with WebView DevTools
./build.ps1                                              # exe + installer -> dist\installer\
./build.ps1 -SkipInstaller                               # exe only -> dist\WildcatMD\
```

### Architecture

```d2
direction: right
md: Markdown file {shape: page}
py: Python process {
  srv: loopback HTTP server
  r: markdown-it-py + plugins
  pyg: Pygments
  d2: d2.exe
  srv -> r -> pyg
  r -> d2: d2 fences
}
wv: WebView2 window (pywebview) {
  css: GitHub CSS
  js: KaTeX + Mermaid + app.js
}
md -> py.srv: read
py.srv -> wv: HTML
wv -> py.srv: poll for changes
```

- `src/wildcat_markdown_viewer/renderer.py`: Markdown → HTML (GFM features, alerts, emoji, fences)
- `d2render.py`: D2 → SVG via the CLI, cached in `%LOCALAPPDATA%`
- `server.py`: loopback server (random port and secret path token, strict nonce CSP so scripts
  embedded in documents can't run)
- `app.py`: pywebview window and the JS ↔ Python bridge
- `assets/`: vendored github-markdown-css 5.8.1, KaTeX 0.16.11, Mermaid 11.4.1, app JS/CSS
- `installer/`: PyInstaller spec and Inno Setup script

## License

Wildcat Markdown Viewer is licensed under the [Apache License 2.0](LICENSE).

Bundled third-party components keep their own licenses:

| Component | License |
| --- | --- |
| [D2](https://github.com/terrastruct/d2) (`d2.exe`, in the installer) | MPL-2.0 |
| [github-markdown-css](https://github.com/sindresorhus/github-markdown-css) | MIT |
| [KaTeX](https://github.com/KaTeX/KaTeX) | MIT |
| [Mermaid](https://github.com/mermaid-js/mermaid) | MIT |
| Python dependencies (pywebview, markdown-it-py, Pygments, …) | see each package |
