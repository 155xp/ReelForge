"""Setup's first minute, before ReelForge's own Python environment exists: it draws the first-run box with the
logo, makes the environment (.venv), installs the Python packages, then hands over to the full first-run screens
(studio/firstrun.py) inside the same box.

setup.ps1 and setup.sh run it with the Python they found:  python -m studio.bootstrap [--yes] [--no-onboard]
Standard library only (nothing else is installed yet). With --yes, or without a terminal, it prints plain lines.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import KIT_NAME, logo

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
WINDOWS = sys.platform == "win32"
VENV_PY = VENV / ("Scripts/python.exe" if WINDOWS else "bin/python")
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = VENV / "installed.txt"          # a copy of requirements.txt as last installed
LOG = VENV / "setup-log.txt"

ESC = "\x1b["
RED = "\x1b[38;2;232;33;58m"
WHITE = "\x1b[38;2;255;255;255m"
GREEN = "\x1b[38;2;74;222;128m"
MUTED = "\x1b[38;2;138;148;163m"
YELLOW = "\x1b[38;2;255;200;58m"
BOLD, RESET = "\x1b[1m", "\x1b[0m"
SPIN = "-\\|/"


def enable_colours() -> bool:
    """Windows' console understands colour codes once asked to; other terminals always do."""
    if not WINDOWS:
        return True
    try:
        import ctypes

        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return False
        return bool(k.SetConsoleMode(h, mode.value | 0x0004))
    except Exception:
        return False


class Plain:
    """No box: one line per step (for --yes, logs, and terminals that can't draw one)."""

    def start(self) -> None:
        print(f"\n=== {KIT_NAME} setup ===\nFolder: {ROOT}\n", flush=True)

    def line(self, text: str, colour: str = "") -> int:
        print(text, flush=True)
        return 0

    def set(self, row: int, text: str, colour: str = "") -> None:
        if not text.startswith(tuple(SPIN)):
            print(text, flush=True)

    def close(self) -> None:
        pass


class Box:
    """A double-line box round the whole terminal, the logo at the top, and status lines inside it."""

    def __init__(self, cols: int, rows: int):
        self.cols, self.rows = cols, rows
        self.top = 0
        self.used = 0

    def _at(self, row: int, col: int) -> str:
        return f"{ESC}{row + 1};{col + 1}H"

    def start(self) -> None:
        c, r = self.cols, self.rows
        title = " 1 Get the tools  ·  2 Your channel  ·  3 Ready "
        mid = max(1, (c - len(title)) // 2)
        out = [f"{ESC}?25l{ESC}0m{ESC}2J{ESC}H"]
        out.append(self._at(0, 0) + RED + "╔" + "═" * (mid - 1) + RESET + BOLD + WHITE + title + RESET + RED +
                   "═" * (c - mid - len(title) - 1) + "╗" + RESET)
        for y in range(1, r - 1):
            out.append(self._at(y, 0) + RED + "║" + RESET + self._at(y, c - 1) + RED + "║" + RESET)
        out.append(self._at(r - 1, 0) + RED + "╚" + "═" * (c - 2) + "╝" + RESET)
        big = logo.big()
        if c >= logo.width(big) + 8 and r >= 24:
            art, width = logo.ansi(big), logo.width(big)
        else:
            art, width = logo.ansi(logo.anvil()), logo.width(logo.anvil()) + 12
            art[1] += "  " + BOLD + WHITE + "reel" + RED + "forge" + RESET
        x, y = max(2, (c - width) // 2), 2
        for i, line in enumerate(art):
            out.append(self._at(y + i, x) + line)
        y += len(art) + 1
        tag = logo.TAGLINE
        out.append(self._at(y, max(2, (c - len(tag)) // 2)) + MUTED + tag + RESET)
        self.top = y + 2
        sys.stdout.write("".join(out))
        sys.stdout.flush()

    def line(self, text: str, colour: str = "") -> int:
        row = min(self.top + self.used, self.rows - 3)
        self.used += 1
        self.set(row, text, colour)
        return row

    def set(self, row: int, text: str, colour: str = "") -> None:
        width = self.cols - 8
        sys.stdout.write(self._at(row, 4) + colour + text[:width].ljust(width) + RESET)
        sys.stdout.flush()

    def close(self) -> None:
        sys.stdout.write(f"{ESC}0m{ESC}?25h" + self._at(self.rows - 2, 2))
        sys.stdout.flush()


def _same_file(a: Path, b: Path) -> bool:
    try:
        return hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()
    except OSError:
        return False


def _healthy() -> bool:
    if not VENV_PY.exists():
        return False
    try:
        return subprocess.run([str(VENV_PY), "-c", "import sys"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _run(ui, row: int, label: str, cmd: list[str]) -> int:
    """Run a command with its output in the log, a spinner and a clock on screen."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8", errors="replace") as log:
        log.write(f"\n$ {' '.join(cmd)}\n")
        log.flush()
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
        t0, i = time.monotonic(), 0
        while p.poll() is None:
            secs = int(time.monotonic() - t0)
            ui.set(row, f"{SPIN[i % 4]} {label}  {secs // 60}:{secs % 60:02d}", WHITE)
            i += 1
            time.sleep(0.15)
    return p.returncode


def _fail(ui, text: str) -> int:
    ui.line("")
    ui.line(text, YELLOW)
    try:
        tail = LOG.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-6:]
    except OSError:
        tail = []
    for t in tail:
        ui.line("  " + t, MUTED)
    ui.line(f"The full log is in {LOG}", MUTED)
    ui.close()
    return 1


def main(argv: list[str]) -> int:
    yes = "--yes" in argv or "-y" in argv
    size = shutil.get_terminal_size((100, 30))
    fancy = not yes and sys.stdout.isatty() and sys.stdin.isatty() and size.columns >= 64 and size.lines >= 18 \
        and enable_colours()
    ui = Box(size.columns, size.lines) if fancy else Plain()
    ui.start()
    ok = "✓" if fancy and (not WINDOWS or os.environ.get("WT_SESSION")) else "+"   # the old console font has no ✓
    try:
        v = sys.version_info
        ui.line(f"{ok} Python {v.major}.{v.minor}.{v.micro}", GREEN)
        if not _healthy():
            if VENV.exists():
                shutil.rmtree(VENV, ignore_errors=True)
            row = ui.line("Making ReelForge's own Python environment (.venv)...")
            if _run(ui, row, "Making ReelForge's own Python environment (.venv)",
                    [sys.executable, "-m", "venv", str(VENV)]) != 0 or not VENV_PY.exists():
                hint = "" if WINDOWS else " (on Debian/Ubuntu: sudo apt install python3-venv)"
                return _fail(ui, f"Couldn't make the .venv folder{hint}.")
            ui.set(row, f"{ok} ReelForge's Python environment: made", GREEN)
        if not STAMP.exists() or not _same_file(REQUIREMENTS, STAMP):
            row = ui.line("Installing Python packages (a minute or two)...")
            _run(ui, row, "Updating pip", [str(VENV_PY), "-m", "pip", "install", "--disable-pip-version-check",
                                           "--quiet", "--upgrade", "pip"])
            if _run(ui, row, "Installing Python packages (a minute or two)",
                    [str(VENV_PY), "-m", "pip", "install", "--disable-pip-version-check", "--quiet", "-r",
                     str(REQUIREMENTS)]) != 0:
                return _fail(ui, "The package install didn't finish. Check your internet connection and run setup "
                                 "again.")
            shutil.copyfile(REQUIREMENTS, STAMP)
        ui.line(f"{ok} Python packages: ready", GREEN)
        ui.line("Starting setup...", MUTED)
        time.sleep(0.4)
    except KeyboardInterrupt:
        ui.close()
        return 130
    ui.close()
    env = dict(os.environ, PYTHONUTF8="1")
    args = [str(VENV_PY), str(ROOT / "bin" / "reelforge.py"), "setup", *argv]
    while True:
        code = subprocess.call(args, cwd=ROOT, env=env)
        if code != 75:            # 75: ReelForge updated itself from the window it opened; start it again
            return code
        args = [str(VENV_PY), str(ROOT / "bin" / "reelforge.py")]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
