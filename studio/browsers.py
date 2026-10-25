"""The browser ReelForge reads your TikTok, Instagram and X stats with (dashboard/platforms/browser.py).

ReelForge drives a browser that's already on your computer, with a profile of its own: Microsoft Edge on Windows
(every Windows PC has it), Google Chrome on macOS and Linux, then Edge, then a Chromium your Linux distribution
installed. A computer with none of them gets the Chromium Playwright downloads (`python -m playwright install
chromium`, about 170 MB, into Playwright's own cache folder); setup offers it. Once ReelForge has used a browser it
keeps using it while it's there, so your logins stay put.

Standard library only: setup and doctor ask about it before the dashboard loads.
"""

from __future__ import annotations

import glob
import json
import os
import plistlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"


@dataclass(frozen=True)
class Browser:
    name: str            # "Edge", "Chrome" or "Chromium", for messages
    exe: Path | None     # its program; None for Playwright's own Chromium (Playwright knows where that is)
    edge: bool = False   # Edge names itself in its user agent too

    def describe(self) -> str:
        return f"{self.name} ({self.exe})" if self.exe else f"{self.name} (Playwright's own)"


def _win_dirs(*parts: str) -> list[Path]:
    bases = [os.environ.get(v) for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    return [Path(b, *parts) for b in bases if b]


def _candidates() -> list[Browser]:
    """The browsers ReelForge can use, in the order it prefers them on this system (installed or not)."""
    if WINDOWS:
        return ([Browser("Edge", p, True) for p in _win_dirs("Microsoft", "Edge", "Application", "msedge.exe")]
                + [Browser("Chrome", p) for p in _win_dirs("Google", "Chrome", "Application", "chrome.exe")])
    if MAC:
        out = []
        for apps in (Path("/Applications"), Path.home() / "Applications"):
            out += [Browser("Chrome", apps / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome"),
                    Browser("Edge", apps / "Microsoft Edge.app" / "Contents" / "MacOS" / "Microsoft Edge", True)]
        return sorted(out, key=lambda b: b.edge)
    # The programs themselves: /usr/bin/google-chrome and the like are scripts round them, and Ubuntu's
    # chromium-browser is a stand-in for the Snap one, which Playwright can't drive.
    return [Browser("Chrome", Path("/opt/google/chrome/chrome")),
            Browser("Edge", Path("/opt/microsoft/msedge/msedge"), True),
            Browser("Chromium", Path("/usr/lib/chromium/chromium")),                  # Debian
            Browser("Chromium", Path("/usr/lib64/chromium-browser/chromium-browser")),  # Fedora
            Browser("Chromium", Path("/usr/lib/chromium/chrome"))]                    # Arch


def playwright_cache() -> Path:
    """Where `playwright install` puts its browsers."""
    custom = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if custom and custom != "0":
        return Path(custom)
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "ms-playwright"
    if MAC:
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path(os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")) / "ms-playwright"


def _playwright_chromium_info() -> dict:
    """Which Chromium this Playwright drives: {"revision": "1248", "browserVersion": "156.0.8078.4"}, or {}."""
    try:
        import importlib.util

        spec = importlib.util.find_spec("playwright")
        if not spec or not spec.origin:
            return {}
        data = json.loads((Path(spec.origin).parent / "driver" / "package" / "browsers.json").read_text("utf-8"))
        return next((b for b in data.get("browsers", []) if b.get("name") == "chromium"), {})
    except (OSError, ValueError, ImportError):
        return {}


def playwright_chromium() -> bool:
    """Whether Playwright's own Chromium, the one this Playwright needs, is downloaded."""
    rev = _playwright_chromium_info().get("revision")
    if not rev:
        return False
    folder = playwright_cache() / f"chromium-{rev}"
    found = (glob.glob(str(folder / "*" / "chrome")) + glob.glob(str(folder / "*" / "chrome.exe"))
             + glob.glob(str(folder / "*" / "*.app" / "Contents" / "MacOS" / "*")))
    return any(Path(p).is_file() for p in found)


def installed() -> list[Browser]:
    """Every browser ReelForge could use here, the one it prefers first."""
    out = [b for b in _candidates() if b.exe and b.exe.is_file()]
    if playwright_chromium():
        out.append(Browser("Chromium", None))
    return out


def find(remembered: str = "") -> Browser | None:
    """The browser to use: the one ReelForge used before (its program's path, or "playwright") while it's still
    there, else the first one installed. None when there's none."""
    here = installed()
    for b in here:
        if remembered and remembered == (str(b.exe) if b.exe else "playwright"):
            return b
    return here[0] if here else None


def key(b: Browser) -> str:
    """What find() is given back to pick the same browser next time."""
    return str(b.exe) if b.exe else "playwright"


def major_version(b: Browser) -> int:
    """The browser's major version (156), read without starting it where possible; 0 when it can't be told."""
    text = ""
    try:
        if b.exe is None:
            text = _playwright_chromium_info().get("browserVersion", "")
        elif WINDOWS:   # Edge and Chrome keep each version's files in a folder named after it, beside the program
            text = max((p.name for p in b.exe.parent.glob("[0-9]*.*") if p.is_dir()),
                       key=lambda v: [int(x) for x in re.findall(r"\d+", v)], default="")
        elif MAC:
            text = plistlib.loads((b.exe.parent.parent / "Info.plist").read_bytes()).get(
                "CFBundleShortVersionString", "")
        else:
            text = subprocess.run([str(b.exe), "--version"], capture_output=True, text=True, timeout=20).stdout
    except (OSError, ValueError, subprocess.SubprocessError, plistlib.InvalidFileException):
        return 0
    m = re.search(r"(\d+)\.\d+", text)
    return int(m.group(1)) if m else 0


def user_agent(b: Browser) -> str:
    """The user agent the browser shows when it has a window. Headless, it calls itself HeadlessChrome (or
    HeadlessEdg), which sites block, so ReelForge's background reads present it as the browser people use."""
    major = major_version(b) or 150
    system = ("Windows NT 10.0; Win64; x64" if WINDOWS else "Macintosh; Intel Mac OS X 10_15_7" if MAC
              else "X11; Linux x86_64")
    agent = f"Mozilla/5.0 ({system}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
    return agent + (f" Edg/{major}.0.0.0" if b.edge else "")


def install_chromium(progress=None) -> str:
    """Download Playwright's own Chromium. progress(text, done, total) hears how far it's got."""
    cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                         errors="replace")
    tail = []
    for line in p.stdout:
        line = line.strip()
        if line:
            tail = (tail + [line])[-5:]
        m = re.search(r"(\d+)% of ([\d.]+) ?MiB", line)
        if progress and m:
            total = float(m.group(2)) * 1048576
            progress("Downloading Chromium", int(total * int(m.group(1)) / 100), int(total))
    if p.wait() != 0 or not playwright_chromium():
        raise RuntimeError("Playwright couldn't download Chromium: " + (tail[-1] if tail else "no message"))
    return "Chromium ready"
