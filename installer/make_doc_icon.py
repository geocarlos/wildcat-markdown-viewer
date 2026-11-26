"""Generate the Explorer icon for Markdown files (assets/md-file.ico).

A document page with a folded corner and the Markdown "M↓" mark. The app itself
keeps the Wildcat icon; this one is only used for .md/.markdown files.

Run:  uv run --with pillow python installer/make_doc_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "src" / "wildcat_markdown_viewer" / "assets" / "md-file.ico"
SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
SS = 8  # supersampling factor

INK = (27, 26, 31, 255)        # #1B1A1F, matches the logo outline
PAGE = (255, 255, 255, 255)
FOLD = (226, 228, 233, 255)
ACCENT = (240, 138, 28, 255)   # #F08A1C, the logo's fur orange
WHITE = (255, 255, 255, 255)


def render(size: int) -> Image.Image:
    px = size * SS
    k = px / 256  # design is on a 256 grid
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def p(*pts):
        return [(x * k, y * k) for x, y in pts]

    # Outline width: proportional, but never thinner than ~1 output pixel.
    stroke = max(10 * k, SS * 1.0)

    # Page with folded top-right corner.
    left, top, right, bottom, fold = 40, 12, 216, 244, 56
    page = p((left, top), (right - fold, top), (right, top + fold), (right, bottom), (left, bottom))
    d.polygon(page, fill=PAGE)
    d.line(page + [page[0]], fill=INK, width=round(stroke), joint="curve")
    corner = p((right - fold, top), (right - fold, top + fold), (right, top + fold))
    d.polygon(corner, fill=FOLD)
    d.line(corner + [corner[0]], fill=INK, width=round(stroke), joint="curve")

    # Markdown badge overlapping the lower half of the page.
    d.rounded_rectangle(p((14, 118), (242, 224)), radius=18 * k, fill=INK)
    # "M"
    d.polygon(p((38, 202), (38, 140), (62, 140), (87, 168), (112, 140), (136, 140),
                (136, 202), (114, 202), (114, 172), (87, 202), (60, 172), (60, 202)), fill=WHITE)
    # Down arrow
    d.polygon(p((174, 140), (202, 140), (202, 168), (226, 168), (188, 206),
                (150, 168), (174, 168)), fill=ACCENT)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    images = [render(s) for s in SIZES]
    big = images[-1]
    big.save(OUT, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
