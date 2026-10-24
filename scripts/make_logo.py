"""Draw ReelForge's images from the logo in studio/logo.py: the app icon (the anvil) and the README banner.

  python scripts/make_logo.py        writes assets/icon/reelforge.ico + reelforge.png and docs/banner.png

The icon is a smooth white anvil on black (the same outline the terminal's pixel anvil was traced from); the banner
is the terminal logo itself, pixel for pixel, with the tagline under it. Needs Pillow (in the kit's .venv).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import logo  # noqa: E402

# The anvil's outline: x from the horn's tip (0) to the heel (1), y from the face (0) to the feet (1). A long horn
# tapering to the left, a flat face, a short square heel, a narrow waist, and a wide base with a semicircular arch
# cut out underneath. ICON_W / ICON_H is how wide and tall the icon draws it, so the arch stays round.
ICON_W, ICON_H = 0.80, 0.48


def anvil_outline(arch: float = 0.10) -> list[tuple[float, float]]:
    pts = [(0.00, 0.00), (1.00, 0.00), (1.00, 0.25), (0.88, 0.25), (0.84, 0.32), (0.80, 0.42), (0.79, 0.55),
           (0.82, 0.66), (0.91, 0.73), (0.96, 0.80), (0.96, 1.00), (0.705 + arch, 1.00)]
    ry = arch * ICON_W / ICON_H
    pts += [(0.705 + arch * math.cos(math.pi * k / 12), 1.00 - ry * math.sin(math.pi * k / 12)) for k in range(1, 12)]
    pts += [(0.705 - arch, 1.00), (0.45, 1.00), (0.45, 0.80), (0.50, 0.73), (0.59, 0.66), (0.62, 0.55),
            (0.61, 0.42), (0.56, 0.33), (0.42, 0.27), (0.25, 0.18), (0.10, 0.08)]
    return pts


def icon(size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=(0, 0, 0, 255))
    w, h = size * ICON_W, size * ICON_H
    x0, y0 = (size - w) / 2, (size - h) / 2 + size * 0.02
    d.polygon([(x0 + x * w, y0 + y * h) for x, y in anvil_outline()], fill=(255, 255, 255, 255))
    return img


def pixels(px: list[str], scale: int) -> Image.Image:
    img = Image.new("RGBA", (len(px[0]), len(px)), (0, 0, 0, 0))
    for y, row in enumerate(px):
        for x, ch in enumerate(row):
            col = logo.PALETTE.get(ch)
            if col:
                img.putpixel((x, y), tuple(int(col[i:i + 2], 16) for i in (1, 3, 5)) + (255,))
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)


def banner() -> Image.Image:
    art = pixels(logo.big(), 12)
    W, H = 1440, 400
    img = Image.new("RGB", (W, H), (0, 0, 0))
    img.paste(art, ((W - art.width) // 2, 70), art)
    font = ImageFont.truetype(str(ROOT / "assets" / "fonts" / "JetBrainsMono-Regular.ttf"), 30)
    text = logo.TAGLINE
    tw = ImageDraw.Draw(img).textlength(text, font=font)
    ImageDraw.Draw(img).text(((W - tw) / 2, 70 + art.height + 40), text, font=font, fill=(138, 148, 163))
    return img


def main() -> int:
    big = icon()
    (ROOT / "assets" / "icon").mkdir(parents=True, exist_ok=True)
    big.resize((512, 512), Image.LANCZOS).save(ROOT / "assets" / "icon" / "reelforge.png")
    big.save(ROOT / "assets" / "icon" / "reelforge.ico",
             sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)])
    (ROOT / "docs").mkdir(exist_ok=True)
    banner().save(ROOT / "docs" / "banner.png", optimize=True)
    print("wrote assets/icon/reelforge.ico, assets/icon/reelforge.png, docs/banner.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
