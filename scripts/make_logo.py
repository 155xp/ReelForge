"""Make ReelForge's logo files from the logo images: the terminal art (studio/logo_art.py), the app icon and the
README banner.

  python scripts/make_logo.py

The sources are assets/logo/reelforge-logo.png (the anvil, "reel" in white and "forge" in red, on black) and
assets/logo/reelforge-anvil.png (the anvil alone, white on black); --logo and --anvil use other files. Writes
studio/logo_art.py, assets/icon/reelforge.ico + reelforge.png + reelforge-terminal.png and docs/banner.png. The
terminal art is the full logo resized to the terminal's grid: 2 x 3 sub-pixels per cell (sextants, which Windows
Terminal draws exactly) and 1 x 2 (half blocks, any terminal). The anvil on its own (the app's header) is too small to
resize well, so it's drawn by hand in studio/logo.py instead. The icon's 16-32 pixel sizes are drawn on the pixel
grid rather than shrunk from the big one, which blurs the anvil into a blob; reelforge-terminal.png is the 32 pixel
one, for ReelForge's tab in Windows Terminal (studio/terminal_profile.py). Needs Pillow (in the kit's .venv).
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
LOGO = ROOT / "assets" / "logo" / "reelforge-logo.png"
ANVIL = ROOT / "assets" / "logo" / "reelforge-anvil.png"
RED = (232, 33, 58)
BIG_ROWS = 8                         # terminal rows for the full logo
INK = 0.5                            # how much of a sub-pixel the logo has to cover for it to be drawn
FIRM = 1.4                           # how hard a small icon's edge pixels are pushed towards solid or empty


def trim(img: Image.Image) -> Image.Image:
    """Crop the black border off a logo image."""
    box = img.convert("L").point(lambda v: 255 if v > 40 else 0).getbbox()
    return img.crop(box) if box else img


def shapes(img: Image.Image) -> list[tuple[str, Image.Image]]:
    """The logo's separate shapes (the anvil, each letter), as (colour "W" or "R", a mask the size of the image)."""
    a = np.asarray(img.convert("RGB"), dtype=np.int32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    red = (r > 100) & (r > 1.8 * np.maximum(g, b))
    inks = {"W": (a.sum(axis=2) > 3 * 128) & ~red, "R": red}
    out = []
    for colour, mask in inks.items():
        seen = np.zeros(mask.shape, dtype=bool)
        h, w = mask.shape
        for y0, x0 in zip(*np.nonzero(mask)):
            if seen[y0, x0]:
                continue
            part = np.zeros(mask.shape, dtype=bool)
            stack = [(y0, x0)]
            seen[y0, x0] = True
            while stack:
                y, x = stack.pop()
                part[y, x] = True
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if part.sum() > 50:                              # specks from the image's compression aren't shapes
                out.append((colour, Image.fromarray(part.astype(np.uint8) * 255)))
    return out


def classify(img: Image.Image, w: int, h: int) -> list[str]:
    """Resize to w x h sub-pixels and call each one W (white), R (red) or . (empty). Each shape (the anvil, each
    letter) is sampled on its own: a sub-pixel is drawn when one shape covers at least INK of it, and two shapes
    never touch (where they would, the sub-pixel each covers less is left empty). So letters set close together
    stay apart, as they are in the logo."""
    parts = [(colour, np.asarray(mask.resize((w, h), Image.BOX), dtype=np.float32) / 255) for colour, mask in shapes(img)]
    cover = np.stack([c for _, c in parts])                  # shape, y, x
    best = cover.argmax(axis=0)
    amount = cover.max(axis=0)
    owner = np.where(amount >= INK, best, -1)
    while True:                                              # pull touching shapes apart, corners included
        touch = False
        for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
            for y in range(h - dy):
                for x in range(max(0, -dx), w - max(0, dx)):
                    a, b = owner[y, x], owner[y + dy, x + dx]
                    if a >= 0 and b >= 0 and a != b:
                        touch = True
                        if amount[y, x] <= amount[y + dy, x + dx]:
                            owner[y, x] = -1
                        else:
                            owner[y + dy, x + dx] = -1
        if not touch:
            break
    return ["".join(parts[k][0] if k >= 0 else "." for k in row) for row in owner]


def tidy(grid: list[str], passes: int = 2) -> list[str]:
    """Take off the sub-pixels a trace leaves sticking out, and nothing else: lone sub-pixels, and bumps of one or two
    sub-pixels on a straight edge (the body runs past them on both sides and nothing is on their other side). Each
    pass decides from the grid as it was, so one removal never leads to the next."""
    g = [list(r) for r in grid]
    h, w = len(g), len(g[0])
    for _ in range(passes):
        snap = [r[:] for r in g]

        def at(y: int, x: int) -> str:
            return snap[y][x] if 0 <= y < h and 0 <= x < w else "."

        off: set[tuple[int, int]] = set()
        for y in range(h):
            for x in range(w):
                c = snap[y][x]
                if c != "." and not any(at(y + dy, x + dx) == c for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx):
                    off.add((y, x))
        for along_rows in (True, False):        # bumps up or down, then bumps left or right
            n, m = (h, w) if along_rows else (w, h)

            def get(i: int, j: int) -> str:
                return at(i, j) if along_rows else at(j, i)

            for i in range(n):
                j = 0
                while j < m:
                    c = get(i, j)
                    if c == ".":
                        j += 1
                        continue
                    k = j
                    while k < m and get(i, k) == c:
                        k += 1
                    if k - j <= 2:
                        for side in (-1, 1):
                            if (all(get(i + side, t) == c for t in range(j - 2, k + 2))
                                    and all(get(i - side, t) != c for t in range(j - 1, k + 1))):
                                off.update((i, t) if along_rows else (t, i) for t in range(j, k))
                                break
                    j = k
        if not off:
            break
        for y, x in off:
            g[y][x] = "."
    return ["".join(r) for r in g]


def grids(img: Image.Image, rows: int) -> tuple[list[str], list[str]]:
    """(sextant grid, half-block grid) for `rows` terminal rows; the width keeps the logo's shape (a terminal cell
    is about twice as tall as it is wide)."""
    img = trim(img)
    cols = max(1, round(img.width / img.height * rows * 2))
    return tidy(classify(img, cols * 2, rows * 3)), tidy(classify(img, cols, rows * 2))


def write_art(big: Image.Image) -> Path:
    big_s, big_h = grids(big, BIG_ROWS)

    def block(name: str, rows: list[str]) -> str:
        return f"{name} = [\n" + "".join(f'    "{r}",\n' for r in rows) + "]\n"

    path = ROOT / "studio" / "logo_art.py"
    path.write_text(
        '"""ReelForge\'s full logo as sub-pixel grids for the terminal ("W" white, "R" red, "." empty). Generated by\n'
        'scripts/make_logo.py from assets/logo/reelforge-logo.png; don\'t edit by hand (the anvil on its own is drawn\n'
        'by hand in studio/logo.py). SEXTANT grids have 2 x 3 sub-pixels per terminal cell, HALF grids 1 x 2\n'
        '(studio/logo.py turns them into characters)."""\n\n'
        + block("BIG_SEXTANT", big_s) + "\n" + block("BIG_HALF", big_h),
        encoding="utf-8", newline="\n")
    return path


def icon(anvil: Image.Image, size: int = 1024) -> Image.Image:
    """The white anvil on a rounded black square."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=(0, 0, 0, 255))
    a = trim(anvil)
    scale = min(size * 0.80 / a.width, size * 0.62 / a.height)
    a = a.resize((max(1, int(a.width * scale)), max(1, int(a.height * scale))), Image.LANCZOS)
    img.paste((255, 255, 255, 255), ((size - a.width) // 2, (size - a.height) // 2 + size // 40), a.convert("L"))
    return img


def coverage(anvil: Image.Image, size: int, firm: float = FIRM) -> np.ndarray:
    """How much of each pixel of a small icon (size x size) the anvil covers, 0-1. The anvil fills more of the square
    than in the big icon, it's shrunk straight onto whole pixels so its flat top and bottom stay sharp, and `firm`
    pushes the edge pixels towards solid or empty."""
    a = trim(anvil).convert("L")
    w = size - 2 * math.ceil(size / 16)
    h = round(w * a.height / a.width)
    cover = np.asarray(a.resize((w, h), Image.BOX), dtype=np.float32) / 255
    out = np.zeros((size, size), dtype=np.float32)
    x, y = (size - w) // 2, (size - h + 1) // 2
    out[y:y + h, x:x + w] = np.clip((cover - 0.5) * firm + 0.5, 0, 1)
    return out


def halves_to(big: np.ndarray, small: np.ndarray) -> np.ndarray:
    """`big` (twice `small`'s size) evened out so that each 2 x 2 block averages to `small`'s pixel: shrunk to half,
    as Windows Terminal draws its tab icons on a 100% display, it's exactly the sharp small icon."""
    n = len(small)
    blocks = big.reshape(n, 2, n, 2).transpose(0, 2, 1, 3).reshape(n, n, 4)
    for _ in range(8):
        need = small[..., None] * 4 - blocks.sum(axis=2, keepdims=True)    # how far each block is off its target
        room = np.where(need > 0, 1 - blocks, blocks)            # how far each of its pixels can move that way
        total = room.sum(axis=2, keepdims=True)
        share = np.where(total > 1e-6, room / np.maximum(total, 1e-6), 0.25)
        blocks = np.clip(blocks + need * share, 0, 1)
    return blocks.reshape(n, n, 2, 2).transpose(0, 2, 1, 3).reshape(2 * n, 2 * n)


def small_icon(cover: np.ndarray) -> Image.Image:
    """A small icon from the anvil's coverage: white on the rounded black square, the same shape as the big one."""
    size, ss = len(cover), 16
    square = Image.new("L", (size * ss, size * ss), 0)
    ImageDraw.Draw(square).rounded_rectangle([0, 0, size * ss - 1, size * ss - 1], radius=size * ss // 5, fill=255)
    alpha = np.asarray(square.resize((size, size), Image.BOX), dtype=np.float32) / 255
    rgba = np.dstack([cover, cover, cover, alpha])
    return Image.fromarray((rgba * 255).round().astype(np.uint8), "RGBA")


def small_icons(anvil: Image.Image) -> list[Image.Image]:
    """The icon at 16, 20, 24 and 32 pixels. The 32 is the 16 at twice the detail: it halves to exactly the 16."""
    return [small_icon(coverage(anvil, 16)), small_icon(coverage(anvil, 20)), small_icon(coverage(anvil, 24)),
            small_icon(halves_to(coverage(anvil, 32, firm=1.0), coverage(anvil, 16)))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logo", type=Path, default=LOGO, help="the logo image (anvil + wordmark on black)")
    ap.add_argument("--anvil", type=Path, default=ANVIL, help="the anvil image (white on black)")
    args = ap.parse_args()
    big = Image.open(args.logo).convert("RGB")
    anvil = Image.open(args.anvil).convert("RGB")
    print("wrote", write_art(big).relative_to(ROOT))
    (ROOT / "assets" / "icon").mkdir(parents=True, exist_ok=True)
    ic = icon(anvil)
    small = small_icons(anvil)
    ic.resize((512, 512), Image.LANCZOS).save(ROOT / "assets" / "icon" / "reelforge.png")
    ic.save(ROOT / "assets" / "icon" / "reelforge.ico", append_images=small,
            sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (20, 20), (16, 16)])
    small[-1].save(ROOT / "assets" / "icon" / "reelforge-terminal.png", optimize=True)
    print("wrote assets/icon/reelforge.ico, reelforge.png and reelforge-terminal.png")
    # The README's banner is the logo itself (a few dozen colours are plenty for white and red on black)
    big.quantize(64, Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(ROOT / "docs" / "banner.png",
                                                                              optimize=True)
    print("wrote docs/banner.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
