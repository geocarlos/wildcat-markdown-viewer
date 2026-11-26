"""Wildcat Markdown Viewer - a GitHub-style Markdown viewer for Windows with D2 support."""

__version__ = "0.1.1"


def main() -> None:
    import sys

    from .app import main as _main

    sys.exit(_main())
