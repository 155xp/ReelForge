"""ReelForge's logo for the terminal: a white anvil, then "reel" in white and "forge" in red.

Standard library only, so setup can draw it before any packages are installed. The art is a grid of sub-pixels:
the full logo (studio/logo_art.py) is made by scripts/make_logo.py from the logo itself, and the anvil on its own
is drawn by hand below, so it stays sharp that small. In Windows Terminal each cell shows 2 x 3 sub-pixels with the
sextant characters, which it draws exactly; anywhere else each cell shows 1 x 2 with half blocks.

  big()     the full logo, 8 rows tall: the first-run screens
  anvil()   the anvil alone, 3 rows tall: small spots like the app's header
  ansi(art)       the art as lines of text with 24-bit colour codes
  rich_text(art)  the art as a rich Text (Textual)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from . import logo_art

WHITE = "#ffffff"
RED = "#e8213a"
PALETTE = {"W": WHITE, "R": RED}
TAGLINE = "Your AI makes the videos. You post them."

# The anvil of assets/logo/reelforge-anvil.png, drawn by hand: the horn on the left, the face stepping up from it,
# the heel on the right, the waist, and the feet with the arch between them. 7 sub-pixels tall in the 3 rows' 9, so
# it sits centred on the header's line of text with room above and below.
ANVIL_SEXTANT = [
    "..................",
    "......WWWWWWWWWWWW",
    "WWWWWWWWWWWWWWWW..",
    "..WWWWWWWWWWW.....",
    ".......WWWWW......",
    "......WWWWWWW.....",
    ".....WWWWWWWWW....",
    "....WWWW...WWWW...",
    "..................",
]
ANVIL_HALF = [      # the same anvil in half blocks, for terminals without sextants
    "...WWWWWWWW",
    "WWWWWWWWW..",
    "..WWWWWW...",
    "....WWWW...",
    "...WWWWW...",
    "...WW..WW..",
]


@dataclass(frozen=True)
class Art:
    grid: list[str]   # sub-pixels: "W", "R" or "."
    sub_w: int        # sub-pixels per cell, across
    sub_h: int        # and down


def sextants() -> bool:
    """Windows Terminal draws sextant characters itself, so they line up perfectly; other terminals may not have
    them in their font. REELFORGE_SEXTANTS=1 or 0 overrides."""
    forced = os.environ.get("REELFORGE_SEXTANTS", "").strip()
    if forced in ("0", "1"):
        return forced == "1"
    return sys.platform == "win32" and windows_terminal()


def windows_terminal() -> bool:
    """Whether Windows Terminal is showing this program. It sets WT_SESSION for what it starts itself, but not for a
    program Windows hands it (opened from a shortcut or by double-clicking a .bat). Then the console's window is a
    pseudo console's, which only the newer terminals make, and the others (VS Code, WezTerm...) name themselves in
    TERM_PROGRAM or TERM."""
    if os.environ.get("WT_SESSION"):
        return True
    if any(os.environ.get(k) for k in ("TERM_PROGRAM", "TERM", "TERMINAL_EMULATOR")):
        return False
    return _console_window_class() == "PseudoConsoleWindow"


def _console_window_class() -> str:
    """The class of this console's window ("" without one, or off Windows)."""
    try:
        import ctypes

        kernel32, user32 = ctypes.WinDLL("kernel32"), ctypes.WinDLL("user32")
        kernel32.GetConsoleWindow.restype = ctypes.c_void_p
        user32.GetClassNameW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)
        hwnd = kernel32.GetConsoleWindow()
        name = ctypes.create_unicode_buffer(64)
        return name.value if hwnd and user32.GetClassNameW(hwnd, name, 64) else ""
    except (AttributeError, OSError):
        return ""


def big() -> Art:
    return Art(logo_art.BIG_SEXTANT, 2, 3) if sextants() else Art(logo_art.BIG_HALF, 1, 2)


def anvil() -> Art:
    return Art(ANVIL_SEXTANT, 2, 3) if sextants() else Art(ANVIL_HALF, 1, 2)


def width(art: Art) -> int:
    """Terminal columns the art takes."""
    return len(art.grid[0]) // art.sub_w if art.grid else 0


def rows(art: Art) -> int:
    """Terminal rows the art takes."""
    return (len(art.grid) + art.sub_h - 1) // art.sub_h


def _sextant(bits: int) -> str:
    """The character with these of its 6 parts filled (bit 0 top-left, 1 top-right, 2 middle-left ... 5 bottom-right)."""
    if bits == 0:
        return " "
    if bits == 63:
        return "█"
    if bits == 21:
        return "▌"
    if bits == 42:
        return "▐"
    return chr(0x1FB00 + bits - 1 - (bits > 21) - (bits > 42))


def cells(art: Art) -> list[list[tuple[str, str | None, str | None]]]:
    """Each terminal row as (character, foreground hex, background hex); None means the terminal's own colour."""
    g, sw, sh = art.grid, art.sub_w, art.sub_h
    out = []
    for y in range(0, len(g), sh):
        line = []
        for x in range(0, len(g[0]), sw):
            subs = [g[y + dy][x + dx] if y + dy < len(g) else "." for dy in range(sh) for dx in range(sw)]
            if sw == 1:       # half blocks: top and bottom can each have their own colour
                ft, fb = PALETTE.get(subs[0]), PALETTE.get(subs[1])
                if ft and fb:
                    line.append(("█", ft, None) if ft == fb else ("▀", ft, fb))
                elif ft:
                    line.append(("▀", ft, None))
                elif fb:
                    line.append(("▄", fb, None))
                else:
                    line.append((" ", None, None))
                continue
            inks = [s for s in subs if s != "."]
            if not inks:
                line.append((" ", None, None))
                continue
            ink = max(set(inks), key=inks.count)
            bits = sum(1 << i for i, s in enumerate(subs) if s == ink)
            line.append((_sextant(bits), PALETTE[ink], None))
        out.append(line)
    return out


def _rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return ";".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def ansi(art: Art, indent: int = 0) -> list[str]:
    """The art as lines of text with 24-bit colour codes (each line ends with a reset)."""
    lines = []
    for line in cells(art):
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


def rich_text(art: Art):
    """The art as a rich Text (for Textual); imports rich only when called."""
    from rich.style import Style
    from rich.text import Text

    t = Text(no_wrap=True, overflow="crop")
    for i, line in enumerate(cells(art)):
        if i:
            t.append("\n")
        for ch, fg, bg in line:
            t.append(ch, Style(color=fg, bgcolor=bg) if (fg or bg) else None)
    return t
