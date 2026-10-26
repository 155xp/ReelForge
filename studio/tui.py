"""What setup's screens and onboarding share with the launchers: naming the terminal's tab, the tick and cross this
terminal can draw, and the three first-run steps. The screens themselves are the OpenTUI app's (ui/src/setup/)."""

from __future__ import annotations

import os
import sys


def set_title(text: str) -> None:
    """Name the terminal's tab or window: Windows' console call, or the title code every macOS and Linux terminal
    reads (written only to a terminal, never into a log)."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(text)
    elif sys.stdout.isatty():
        sys.stdout.write(f"]0;{text}")
        sys.stdout.flush()


# Windows Terminal (and every macOS/Linux terminal) draws ✓; the old Windows console font doesn't.
FANCY = not sys.platform.startswith("win") or bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"))
CHECK = "✓" if FANCY else "√"
CROSS = "✗" if FANCY else "x"

STEPS = [("tools", "Get the tools"), ("channel", "Your channel"), ("ready", "Ready")]
