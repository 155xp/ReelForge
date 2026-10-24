"""ReelForge's logo for the terminal: a white anvil, then "reel" in white and "forge" in red.

Standard library only, so setup can draw it before any packages are installed. It is drawn as pixels, and each
terminal cell shows two of them stacked (the half-block character "▀" with a foreground and a background colour),
so the same art works in any terminal and as an image (scripts/make_logo.py renders the PNGs from it).

  big()     the full logo, 101 x 16 pixels (101 columns x 8 rows): the first-run screens
  anvil()   the anvil alone, 16 x 6 pixels (16 columns x 3 rows): small spots like the dashboard's header
  ansi(px)  the art as text with 24-bit colour codes
  cells(px) rows of (character, foreground, background) for other renderers (Textual uses rich_text)
"""

from __future__ import annotations

WHITE = "#ffffff"
RED = "#e8213a"
PALETTE = {"W": WHITE, "R": RED}

# The anvil, 26 x 16: a long horn tapering to the left, a flat face, a short square heel, a narrow waist and a
# wide base with an arch cut out underneath (traced from the icon's outline in scripts/make_logo.py).
ANVIL = [
    "..........................",
    ".#########################",
    "....######################",
    ".......###################",
    "...........############...",
    "...............#######....",
    "................#####.....",
    "................#####.....",
    "................#####.....",
    "...............######.....",
    ".............###########..",
    "............#############.",
    "............#####...#####.",
    "............####.....####.",
    "..........................",
    "..........................",
]

ANVIL_SMALL = [
    "################",
    "...#############",
    ".........####...",
    ".........####...",
    ".......########.",
    ".......###..###.",
]

# Bold rounded lowercase: x-height rows 4-12, ascenders from row 0, the g's tail to row 15.
FONT = {
    "r": ["......", "......", "......", "......", "##.###", "######", "###...", "##....", "##....", "##....",
          "##....", "##....", "##....", "......", "......", "......"],
    "e": [".......", ".......", ".......", ".......", ".#####.", "#######", "##...##", "##...##", "#######",
          "##.....", "##.....", "#######", ".######", ".......", ".......", "......."],
    "l": ["##", "##", "##", "##", "##", "##", "##", "##", "##", "##", "##", "##", "##", "..", "..", ".."],
    "f": ["...###", "..####", ".##...", ".##...", "#####.", "#####.", ".##...", ".##...", ".##...", ".##...",
          ".##...", ".##...", ".##...", "......", "......", "......"],
    "o": [".......", ".......", ".......", ".......", ".#####.", "#######", "##...##", "##...##", "##...##",
          "##...##", "##...##", "#######", ".#####.", ".......", ".......", "......."],
    "g": [".......", ".......", ".......", ".......", ".######", "#######", "##...##", "##...##", "##...##",
          "##...##", "##...##", "#######", ".######", ".....##", "######.", ".####.."],
}


def _canvas(w: int, h: int) -> list[list[str]]:
    return [["."] * w for _ in range(h)]


def _paste(c: list[list[str]], art: list[str], x: int, y: int, color: str) -> None:
    for dy, row in enumerate(art):
        for dx, ch in enumerate(row):
            if ch == "#" and 0 <= y + dy < len(c) and 0 <= x + dx < len(c[0]):
                c[y + dy][x + dx] = color


def _word(c, text: str, x: int, color: str, gap: int = 2) -> int:
    for ch in text:
        _paste(c, FONT[ch], x, 0, color)
        x += len(FONT[ch][0]) + gap
    return x


def big() -> list[str]:
    reel = sum(len(FONT[ch][0]) + 2 for ch in "reel")
    forge = sum(len(FONT[ch][0]) + 2 for ch in "forge") - 2
    c = _canvas(len(ANVIL[0]) + 4 + reel + forge, 16)
    _paste(c, ANVIL, 0, 0, "W")
    x = _word(c, "reel", len(ANVIL[0]) + 4, "W")
    _word(c, "forge", x, "R")
    return ["".join(r) for r in c]


def anvil() -> list[str]:
    c = _canvas(len(ANVIL_SMALL[0]), len(ANVIL_SMALL))
    _paste(c, ANVIL_SMALL, 0, 0, "W")
    return ["".join(r) for r in c]


def width(px: list[str]) -> int:
    return len(px[0]) if px else 0


def rows(px: list[str]) -> int:
    return (len(px) + 1) // 2


def cells(px: list[str]) -> list[list[tuple[str, str | None, str | None]]]:
    """Each terminal row as (character, foreground hex, background hex); None means the terminal's own colour."""
    out = []
    for y in range(0, len(px), 2):
        top = px[y]
        bottom = px[y + 1] if y + 1 < len(px) else "." * len(top)
        line = []
        for t, b in zip(top, bottom):
            ft, fb = PALETTE.get(t), PALETTE.get(b)
            if ft and fb:
                line.append(("█", ft, None) if ft == fb else ("▀", ft, fb))
            elif ft:
                line.append(("▀", ft, None))
            elif fb:
                line.append(("▄", fb, None))
            else:
                line.append((" ", None, None))
        out.append(line)
    return out


def _rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return ";".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def ansi(px: list[str], indent: int = 0) -> list[str]:
    """The art as lines of text with 24-bit colour codes (each line ends with a reset)."""
    lines = []
    for line in cells(px):
        parts, last = [" " * indent], None
        for ch, fg, bg in line:
            style = (fg, bg)
            if style != last:
                code = "\x1b[0m"
                if fg:
                    code += f"\x1b[38;2;{_rgb(fg)}m"
                if bg:
                    code += f"\x1b[48;2;{_rgb(bg)}m"
                parts.append(code)
                last = style
            parts.append(ch)
        lines.append("".join(parts).rstrip() + "\x1b[0m")
    return lines


def rich_text(px: list[str]):
    """The art as a rich Text (for Textual); imports rich only when called."""
    from rich.style import Style
    from rich.text import Text

    t = Text(no_wrap=True, overflow="crop")
    for i, line in enumerate(cells(px)):
        if i:
            t.append("\n")
        for ch, fg, bg in line:
            t.append(ch, Style(color=fg, bgcolor=bg) if (fg or bg) else None)
    return t


TAGLINE = "Your AI makes the videos. You post them."
