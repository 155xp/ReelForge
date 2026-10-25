"""ReelForge's logo for the terminal: a white anvil, then "reel" in white and "forge" in red.

Standard library only, so setup can draw it before any packages are installed. The art is a grid of sub-pixels,
drawn by hand so every edge is clean: the full logo in studio/logo_art.py, and the anvil on its own below, small
enough for the app's header. In Windows Terminal each cell shows 2 x 2 sub-pixels with the quadrant characters, which
it draws itself on whole pixels; anywhere else each cell shows 1 x 2 with half blocks. (Not sextants, 2 x 3: Windows
Terminal 1.24 takes those from the font, which leaves faint seams and fringes round every edge.)

  big()     the full logo, 8 rows tall: the first-run screens
  anvil()   the anvil alone, 3 rows tall: small spots like the app's header
  ansi(art)       the art as lines of text with colour codes (24-bit, or the nearest of 256 colours where that's
                  all the terminal shows): setup's first box, before the window can run
  cells(art)      each row as (character, colour, background): what the window (ui/) draws
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from . import logo_art

WHITE = "#ffffff"
RED = "#e8213a"
PALETTE = {"W": WHITE, "R": RED}

# The anvil of assets/logo/reelforge-anvil.png, drawn by hand: the face, the horn on the left, the heel curving in on
# the right, the waist and the feet with the arch between them, one sub-row each. The top one of the 3 rows' 6 sub-rows
# is left empty, so the anvil doesn't fill the header from edge to edge.
ANVIL_QUAD = [
    "..................",
    "......WWWWWWWWWWWW",
    "WWWWWWWWWWWWWWWW..",
    "...WWWWWWWWW......",
    "......WWWWWW......",
    "....WWWW..WWWW....",
]
ANVIL_HALF = [      # the same anvil in half blocks, for other terminals
    "...........",
    "...WWWWWWWW",
    "WWWWWWWWW..",
    "..WWWWWW...",
    "....WWWW...",
    "...WW..WW..",
]


@dataclass(frozen=True)
class Art:
    grid: list[str]   # sub-pixels: "W", "R" or "."
    sub_w: int        # sub-pixels per cell, across
    sub_h: int        # and down


def quadrants() -> bool:
    """Windows Terminal draws quadrant characters itself, on whole pixels, so they line up perfectly; other
    terminals take them from the font, which may not have them. REELFORGE_QUADRANTS=1 or 0 overrides."""
    forced = os.environ.get("REELFORGE_QUADRANTS", "").strip()
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
    return Art(logo_art.BIG_QUAD, 2, 2) if quadrants() else Art(logo_art.BIG_HALF, 1, 2)


def anvil() -> Art:
    return Art(ANVIL_QUAD, 2, 2) if quadrants() else Art(ANVIL_HALF, 1, 2)


def width(art: Art) -> int:
    """Terminal columns the art takes."""
    return len(art.grid[0]) // art.sub_w if art.grid else 0


def rows(art: Art) -> int:
    """Terminal rows the art takes."""
    return (len(art.grid) + art.sub_h - 1) // art.sub_h


QUADRANTS = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"   # by the parts filled: bit 0 top-left, 1 top-right, 2 bottom-left, 3 bottom-right


def _quadrant(bits: int) -> str:
    """The character with these of its 4 parts filled."""
    return QUADRANTS[bits]


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
            line.append((_quadrant(bits), PALETTE[ink], None))
        out.append(line)
    return out


def truecolor() -> bool:
    """Whether the terminal shows 24-bit colour: Windows' terminals do, and others say so in COLORTERM (the test
    the window uses too). macOS's own Terminal shows only 256 colours before macOS 26 and turns 24-bit codes
    into the wrong ones. REELFORGE_TRUECOLOR=1 or 0 overrides."""
    forced = os.environ.get("REELFORGE_TRUECOLOR", "").strip()
    if forced in ("0", "1"):
        return forced == "1"
    return sys.platform == "win32" or os.environ.get("COLORTERM", "").strip().lower() in ("truecolor", "24bit")


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def xterm256(hex_color: str) -> int:
    """The nearest of the 256-colour palette's 6 x 6 x 6 cube and 24 greys."""
    r, g, b = _rgb(hex_color)
    levels = (0, 95, 135, 175, 215, 255)
    near = [min(range(6), key=lambda i: abs(levels[i] - c)) for c in (r, g, b)]
    options = [(16 + 36 * near[0] + 6 * near[1] + near[2], tuple(levels[i] for i in near))]
    options += [(232 + i, (8 + 10 * i,) * 3) for i in range(24)]
    return min(options, key=lambda o: sum((a - c) ** 2 for a, c in zip(o[1], (r, g, b))))[0]


def sgr(hex_color: str, background: bool = False) -> str:
    """The code that sets the text (or background) colour."""
    layer = 48 if background else 38
    if truecolor():
        return f"\x1b[{layer};2;{';'.join(map(str, _rgb(hex_color)))}m"
    return f"\x1b[{layer};5;{xterm256(hex_color)}m"


def ansi(art: Art, indent: int = 0) -> list[str]:
    """The art as lines of text with colour codes (each line ends with a reset)."""
    lines = []
    for line in cells(art):
        parts, last = [" " * indent], None
        for ch, fg, bg in line:
            style = (fg, bg)
            if style != last:
                code = "\x1b[0m"
                if fg:
                    code += sgr(fg)
                if bg:
                    code += sgr(bg, background=True)
                parts.append(code)
                last = style
            parts.append(ch)
        lines.append("".join(parts).rstrip() + "\x1b[0m")
    return lines
