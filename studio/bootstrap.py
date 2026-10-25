"""Setup's first minute, before ReelForge's own Python environment exists: it draws the first-run box with the
logo, makes the environment (.venv), installs the Python packages, then hands over to the full first-run screens
(studio/firstrun.py) inside the same box.

setup.ps1 and setup.sh run it with the Python they found:  python -m studio.bootstrap [--yes] [--no-onboard]
Standard library only (nothing else is installed yet). With --yes, or without a terminal, it prints plain lines.
"""

from __future__ import annotations

import atexit
import hashlib
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
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
        self.set(0, text)
        return 0

    def set(self, row: int, text: str, colour: str = "") -> None:
        if not text.lstrip().startswith(tuple(SPIN)):      # spinners and progress only make sense in the box
            print(text, flush=True)

    def close(self, keep: bool = False) -> None:
        pass


def _size() -> tuple[int, int]:
    s = shutil.get_terminal_size((100, 30))
    return s.columns, s.lines


class Box:
    """A double-line box round the whole terminal, the logo at the top, and status lines inside it.

    It lives on the terminal's second screen (the one full-screen apps use, so nothing scrolls or reflows) with line
    wrap off (so drawing the last column never wraps or scrolls). A watcher thread redraws all of it whenever the
    window changes size, and the status lines scroll inside the box once they fill it."""

    STEPS = ("1 Get the tools", "2 Your channel", "3 Ready")

    def __init__(self):
        self.cols, self.rows = _size()
        self.lines: list[list[str]] = []      # [text, colour] for each status line, oldest first
        self.top = 0                          # the first row status lines go on
        self.lock = threading.RLock()
        self.open = False

    def _at(self, row: int, col: int) -> str:
        return f"{ESC}{row + 1};{col + 1}H"

    def _write(self, s: str) -> None:
        sys.stdout.write(s)
        sys.stdout.flush()

    def start(self) -> None:
        self.open = True
        atexit.register(self._restore)
        self._write(f"{ESC}?1049h{ESC}?25l{ESC}?7l")
        with self.lock:
            self._draw()
        threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self) -> None:
        while self.open:
            time.sleep(0.1)
            size = _size()
            with self.lock:
                if self.open and size != (self.cols, self.rows):
                    self.cols, self.rows = size
                    self._draw()

    def _title(self, room: int) -> list[tuple[str, str]]:
        """The steps for the top edge, step 1 lit; fewer of them when the window is narrow."""
        dot = "  ·  "
        for steps in (self.STEPS, self.STEPS[:1]):
            parts = [(" ", "")]
            for n, s in enumerate(steps):
                if n:
                    parts.append((dot, MUTED))
                parts.append((s, BOLD + WHITE if n == 0 else MUTED))
            parts.append((" ", ""))
            if sum(len(t) for t, _ in parts) <= room:
                return parts
        return []

    def _draw(self) -> None:
        c, r = self.cols, self.rows
        out = [f"{ESC}0m{ESC}2J"]
        if c < 4 or r < 3:
            self._write("".join(out))
            return
        title = self._title(c - 6)
        tw = sum(len(t) for t, _ in title)
        left = (c - 2 - tw) // 2
        out.append(self._at(0, 0) + RED + "╔" + "═" * left + RESET)
        out.extend(colour + t + RESET for t, colour in title)
        out.append(RED + "═" * (c - 2 - left - tw) + "╗" + RESET)
        for y in range(1, r - 1):
            out.append(self._at(y, 0) + RED + "║" + self._at(y, c - 1) + "║" + RESET)
        out.append(self._at(r - 1, 0) + RED + "╚" + "═" * (c - 2) + "╝" + RESET)

        big, anvil = logo.big(), logo.anvil()
        y = 2
        if c >= logo.width(big) + 8 and r >= logo.rows(big) + 16:
            art, width = logo.ansi(big), logo.width(big)
        elif c >= logo.width(anvil) + 20 and r >= logo.rows(anvil) + 12:
            art, width = logo.ansi(anvil), logo.width(anvil) + 11
            art[1] += "  " + BOLD + WHITE + "reel" + RED + "forge" + RESET
        else:
            art, width, y = [], 0, 1
        if art:
            x = (c - width) // 2
            for i, line in enumerate(art):
                out.append(self._at(y + i, x) + line)
            y += len(art) + 1
        self.top = y
        out.append(self._body())
        self._write("".join(out))

    def _room(self) -> int:
        return max(0, self.rows - 2 - self.top)

    def _first(self) -> int:
        return max(0, len(self.lines) - self._room())

    def _row(self, i: int) -> str:
        width = max(0, self.cols - 8)
        text, colour = self.lines[i]
        return self._at(self.top + i - self._first(), 4) + colour + text[:width].ljust(width) + RESET

    def _body(self) -> str:
        """Every status line that fits, the newest at the bottom."""
        rows = [self._row(i) for i in range(self._first(), len(self.lines))]
        blank = " " * max(0, self.cols - 8)
        rows += [self._at(self.top + n, 4) + blank for n in range(len(rows), self._room())]
        return "".join(rows)

    def line(self, text: str, colour: str = "") -> int:
        with self.lock:
            scrolls = len(self.lines) >= self._room()
            self.lines.append([text, colour])
            if self.open:
                self._write(self._body() if scrolls else self._row(len(self.lines) - 1))
            return len(self.lines) - 1

    def set(self, i: int, text: str, colour: str = "") -> None:
        with self.lock:
            self.lines[i] = [text, colour]
            if self.open and i >= self._first():
                self._write(self._row(i))

    def _restore(self) -> None:
        if self.open:
            self.open = False
            self._write(f"{ESC}0m{ESC}?7h{ESC}?25h")

    def close(self, keep: bool = False) -> None:
        """Hand the terminal back. keep: leave the box's screen and print its lines (after a failure, so they stay
        readable); otherwise the box stays up until the next full-screen app (setup's next screens) replaces it."""
        with self.lock:
            self._restore()
            if keep:
                self._write(f"{ESC}?1049l")
                for text, colour in self.lines:
                    print(colour + text + RESET)
                sys.stdout.flush()


def _same_file(a: Path, b: Path) -> bool:
    try:
        return hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()
    except OSError:
        return False


def _healthy() -> bool:
    """.venv's Python runs and has pip. A setup that stopped part way (its window closed while Python was making
    .venv) can leave one without pip, which could never install the packages: that one is made again."""
    if not VENV_PY.exists():
        return False
    try:
        return subprocess.run([str(VENV_PY), "-m", "pip", "--version"], capture_output=True,
                              timeout=120).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _mb(n: float) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 1e5 else f"{n / 1e3:.0f} kB"


class Packages:
    """pip's output as one line per package: a spinner and its download while pip fetches it, a tick once it's
    installed (or already was), a cross if pip stopped before it was."""

    NAME = r"([A-Za-z0-9][A-Za-z0-9._-]*)"

    def __init__(self, ui, ok: str, bad: str):
        self.ui, self.ok, self.bad = ui, ok, bad
        self.rows: dict[str, list] = {}        # name, normalised -> [line, name, state, detail, text on screen]
        self.fetching = ""                      # the package being downloaded
        self.error = ""

    def _row(self, name: str) -> list:
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key not in self.rows:
            self.rows[key] = [self.ui.line(f"  {SPIN[0]} {name}", WHITE), name, "busy", "checking", ""]
        return self.rows[key]

    def feed(self, line: str) -> None:
        line = line.strip()
        if m := re.match(r"Collecting " + self.NAME, line):
            self._row(m[1])
        elif m := re.match(r"Requirement already satisfied: " + self.NAME, line):
            r = self._row(m[1])
            r[2], r[3] = "done", "already installed"
        elif (m := re.match(r"(?:Downloading|Using cached) ([A-Za-z0-9._]+?)-\d\S* \(([^)]+)\)", line)) \
                and ".metadata " not in line:
            r = self._row(m[1])
            r[3] = f"downloading {m[2]}" if line.startswith("Downloading") else "from the download cache"
            self.fetching = m[1]
        elif (m := re.match(r"Progress (\d+) of (\d+)", line)) and self.fetching and int(m[2]):
            self._row(self.fetching)[3] = f"downloading {_mb(int(m[1]))} of {_mb(int(m[2]))}"
        elif line.startswith("Installing collected packages:"):
            for name in line.split(":", 1)[1].split(","):
                if name.strip():
                    self._row(name.strip())[3] = "installing"
        elif line.startswith("Successfully installed "):
            for tok in line.split()[2:]:
                name, _, version = tok.rpartition("-")
                r = self._row(name or tok)
                r[2], r[3] = "done", version
        elif line.startswith("ERROR:") and not self.error:
            self.error = line[6:].strip()

    def finish(self, ok: bool) -> None:
        for r in self.rows.values():
            if r[2] == "busy":
                r[2], r[3] = ("done", "installed") if ok else ("failed", "not installed")

    def draw(self, tick: int) -> None:
        for r in self.rows.values():
            line, name, state, detail, shown = r
            mark, colour = {"busy": (SPIN[tick % 4], WHITE), "done": (self.ok, GREEN)}.get(state, (self.bad, YELLOW))
            text = f"  {mark} {name}  {detail}"
            if text != shown:
                r[4] = text
                self.ui.set(line, text, colour)

    def count(self) -> int:
        return sum(r[2] == "done" for r in self.rows.values())


def _run(ui, row: int, label: str, cmd: list[str], watch: Packages | None = None) -> int:
    """Run a command with its output in the log, a spinner and a clock on screen. watch, if given, hears each line
    of the output and redraws its own lines as the spinner turns."""
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8", errors="replace") as log:
        log.write(f"\n$ {' '.join(cmd)}\n")
        log.flush()
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE if watch else log, stderr=subprocess.STDOUT, cwd=ROOT,
                             env=env)
        lines: queue.Queue = queue.Queue()
        if watch:
            def read() -> None:
                for raw in p.stdout:
                    lines.put(raw.decode("utf-8", "replace"))
                lines.put(None)
            threading.Thread(target=read, daemon=True).start()
        t0, i, reading = time.monotonic(), 0, bool(watch)
        while p.poll() is None or reading:
            while True:
                try:
                    text = lines.get_nowait()
                except queue.Empty:
                    break
                if text is None:
                    reading = False
                    break
                log.write(text)
                watch.feed(text)
            secs = int(time.monotonic() - t0)
            ui.set(row, f"{SPIN[i % 4]} {label}  {secs // 60}:{secs % 60:02d}", WHITE)
            if watch:
                watch.draw(i)
            i += 1
            time.sleep(0.15)
        p.wait()
    if watch:
        watch.finish(p.returncode == 0)
        watch.draw(i)
    return p.returncode


def _raw_progress() -> bool:
    """pip 24.1 and newer can report download progress as plain lines (--progress-bar raw)."""
    try:
        out = subprocess.run([str(VENV_PY), "-m", "pip", "--version"], capture_output=True, text=True, timeout=60)
        major, minor = (int(x) for x in out.stdout.split()[1].split(".")[:2])
        return (major, minor) >= (24, 1)
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return False


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
    ui.close(keep=True)
    return 1


def main(argv: list[str]) -> int:
    yes = "--yes" in argv or "-y" in argv
    size = shutil.get_terminal_size((100, 30))
    fancy = not yes and sys.stdout.isatty() and sys.stdin.isatty() and size.columns >= 64 and size.lines >= 18 \
        and enable_colours()
    ui = Box() if fancy else Plain()
    ui.start()
    ok = "✓" if fancy and (not WINDOWS or os.environ.get("WT_SESSION")) else "+"   # the old console font has no ✓
    bad = "✗" if ok == "✓" else "x"
    try:
        v = sys.version_info
        ui.line(f"{ok} Python {v.major}.{v.minor}.{v.micro}", GREEN)
        if not _healthy():
            again = VENV.exists()           # an unfinished one, from a setup that stopped part way
            if again:
                shutil.rmtree(VENV, ignore_errors=True)
            what = "Making ReelForge's own Python environment (.venv)" + (" again" if again else "")
            row = ui.line(what + "...")
            if _run(ui, row, what, [sys.executable, "-m", "venv", str(VENV)]) != 0 or not VENV_PY.exists():
                hint = "" if WINDOWS else " (on Debian/Ubuntu: sudo apt install python3-venv)"
                return _fail(ui, f"Couldn't make the .venv folder{hint}.")
            ui.set(row, f"{ok} ReelForge's Python environment: made" + (" again" if again else ""), GREEN)
        if not STAMP.exists() or not _same_file(REQUIREMENTS, STAMP):
            row = ui.line("Python packages...")
            pkgs = Packages(ui, ok, bad)
            pip = [str(VENV_PY), "-m", "pip", "install", "--disable-pip-version-check"]
            _run(ui, row, "Python packages: updating pip", pip + ["--upgrade", "pip"], pkgs)
            raw = ["--progress-bar", "raw"] if _raw_progress() else []
            if _run(ui, row, "Python packages: downloading and installing", pip + raw + ["-r", str(REQUIREMENTS)],
                    pkgs) != 0:
                ui.set(row, f"{bad} Python packages: {pkgs.error or 'the install stopped'}", YELLOW)
                return _fail(ui, "The package install didn't finish. Check your internet connection and run setup "
                                 "again.")
            shutil.copyfile(REQUIREMENTS, STAMP)
            ui.set(row, f"{ok} Python packages: {pkgs.count()} ready", GREEN)
        else:
            ui.line(f"{ok} Python packages: ready", GREEN)
        ui.line("Starting setup...", MUTED)
        time.sleep(0.4)
    except KeyboardInterrupt:
        ui.close(keep=True)
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
