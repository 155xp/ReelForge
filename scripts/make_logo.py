"""Make ReelForge's logo files from the logo images: the app icon and the README banner.

  python scripts/make_logo.py

The sources are assets/logo/reelforge-logo.png (the anvil, "reel" in white and "forge" in red, on black) and
assets/logo/reelforge-anvil.png (the anvil alone, white on black); --logo and --anvil use other files. Writes
assets/icon/reelforge.ico + reelforge.png + reelforge-terminal.png and docs/banner.png. The icon's 16-32 pixel sizes
are drawn on the pixel grid rather than shrunk from the big one, which blurs the anvil into a blob;
reelforge-terminal.png is the 32 pixel one, for ReelForge's tab in Windows Terminal (studio/terminal_profile.py).
The terminal's logo isn't made here: shrunk that far, a trace of the logo leaves pixels sticking out, so it's drawn
by hand in studio/logo_art.py and studio/logo.py. Needs Pillow (in the kit's .venv).
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
FIRM = 1.4                           # how hard a small icon's edge pixels are pushed towards solid or empty


def trim(img: Image.Image) -> Image.Image:
    """Crop the black border off a logo image."""
    box = img.convert("L").point(lambda v: 255 if v > 40 else 0).getbbox()
    return img.crop(box) if box else img


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
