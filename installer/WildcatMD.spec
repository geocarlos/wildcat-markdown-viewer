# PyInstaller spec - one-folder, windowed build of Wildcat Markdown Viewer.
# Build with:  uv run pyinstaller installer/WildcatMD.spec --noconfirm
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
PKG = ROOT / "src" / "wildcat_markdown_viewer"

datas = [(str(PKG / "assets"), "wildcat_markdown_viewer/assets")]
datas += collect_data_files("webview")          # pywebview's injected JS + .NET interop DLLs
datas += collect_data_files("emoji")

hiddenimports = collect_submodules("pygments.lexers") + collect_submodules("pygments.styles")
hiddenimports += collect_submodules("mdit_py_plugins")
hiddenimports += ["clr", "webview.platforms.edgechromium", "webview.platforms.winforms"]

a = Analysis(
    [str(ROOT / "installer" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "PIL", "numpy", "webview.platforms.qt", "webview.platforms.gtk",
              "webview.platforms.cocoa", "webview.platforms.android"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WildcatMD",
    icon=str(PKG / "assets" / "icon.ico"),
    console=False,
    upx=False,
    version=str(ROOT / "installer" / "version_info.txt"),
)

coll = COLLECT(exe, a.binaries, a.datas, name="WildcatMD", upx=False)
