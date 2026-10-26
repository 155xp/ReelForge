"""ReelForge's icon: open ReelForge without typing a command. Setup makes it if you say yes.

  Windows  a desktop shortcut (ReelForge.lnk) that runs ReelForge.bat
  macOS    ReelForge in your Applications folder (~/Applications/ReelForge.app), so it's in Launchpad and Spotlight
           and can sit in the Dock; it opens ReelForge in Terminal
  Linux    ReelForge in your app menu (~/.local/share/applications/reelforge.desktop), in a terminal window

Each points at this folder, so after moving the folder run setup again to point it at the new place.
"""

from __future__ import annotations

import os
import plistlib
import shlex
import shutil
import subprocess
from pathlib import Path

from . import KIT_NAME, KIT_SLUG, KIT_VERSION
from . import paths as P

ICON_PNG = P.ROOT / "assets" / "icon" / "reelforge.png"
ICON_ICO = P.ROOT / "assets" / "icon" / "reelforge.ico"
COMMENT = "Your channel's stats, and the videos waiting for you to post them"


def path() -> Path:
    """Where the icon goes on this system."""
    if P.WINDOWS:
        return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop" / f"{KIT_NAME}.lnk"
    if P.MAC:
        return Path.home() / "Applications" / f"{KIT_NAME}.app"
    data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data) / "applications" / f"{KIT_SLUG}.desktop"


def label() -> tuple[str, str, str]:
    """(name, what it's for, what making it does) for setup's list."""
    if P.WINDOWS:
        return "Desktop shortcut", "a ReelForge icon on your desktop", "double-click to open ReelForge"
    if P.MAC:
        return ("ReelForge in Applications", "open it from Launchpad, Spotlight or the Dock",
                "opens ReelForge in Terminal")
    return "ReelForge in your app menu", "open it like any other app", "opens ReelForge in a terminal window"


def ready() -> bool:
    """The icon is there and opens this folder's ReelForge."""
    p = path()
    if P.WINDOWS or not p.exists():
        return p.exists()
    launcher = P.ROOT / "bin" / "reelforge"
    try:
        if P.MAC:
            run = p / "Contents" / "Resources" / f"{KIT_NAME}.command"
            return shlex.quote(str(launcher)) in run.read_text(encoding="utf-8")
        return desktop_exec(launcher) in p.read_text(encoding="utf-8")
    except OSError:
        return False


def make() -> str:
    """Make (or remake) the icon. Returns where it is; raises with a readable message."""
    if P.WINDOWS:
        return _windows()
    if P.MAC:
        return _mac()
    return _linux()


def ours() -> bool:
    """The icon is there and opens this folder's ReelForge (on Windows: the shortcut's target is this folder's
    ReelForge.bat, not another copy's)."""
    if not P.WINDOWS:
        return ready()
    link = path()
    if not link.exists():
        return False
    ps = ("(New-Object -ComObject WScript.Shell).CreateShortcut($env:RF_LINK).TargetPath")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30,
                           env={**os.environ, "RF_LINK": str(link)},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    target = r.stdout.strip()
    return bool(target) and os.path.normcase(os.path.normpath(target)) == os.path.normcase(
        os.path.normpath(str(P.ROOT / "ReelForge.bat")))


def remove() -> bool:
    """Remove the icon if it opens this folder's ReelForge. Returns whether it did."""
    if not ready():
        return False
    p = path()
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return True


def _windows() -> str:
    link = path()
    target = P.ROOT / "ReelForge.bat"

    def q(s) -> str:
        return "'" + str(s).replace("'", "''") + "'"

    ps = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({q(link)}); $s.TargetPath = {q(target)}; "
          f"$s.WorkingDirectory = {q(P.ROOT)}; $s.Description = 'ReelForge'; "
          + (f"$s.IconLocation = {q(ICON_ICO)}; " if ICON_ICO.exists() else "") + "$s.Save()")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError((r.stderr.strip().splitlines() or ["PowerShell couldn't make the shortcut"])[-1])
    return str(link)


def command_file() -> str:
    """What the Mac app has Terminal run: make the window big enough for ReelForge, then open it."""
    return ("#!/bin/sh\n"
            f"# Opens {KIT_NAME} ({P.ROOT}). Made by {KIT_NAME}'s setup; run setup again after moving that folder.\n"
            "printf '\\033[8;42;132t'\n"
            f"exec {shlex.quote(str(P.ROOT / 'bin' / 'reelforge'))}\n")


def _mac() -> str:
    """A small app bundle. Its program asks Terminal to open a .command file inside it, which Terminal runs in a new
    window (no permission prompt, unlike scripting Terminal). Made on this Mac, so Gatekeeper has nothing to check."""
    app = path()
    staging = app.with_name(app.name + ".rf-new")
    shutil.rmtree(staging, ignore_errors=True)
    macos, resources = staging / "Contents" / "MacOS", staging / "Contents" / "Resources"
    macos.mkdir(parents=True)
    resources.mkdir()
    info = {
        "CFBundleName": KIT_NAME, "CFBundleDisplayName": KIT_NAME, "CFBundleIdentifier": "com.reelforge.app",
        "CFBundleExecutable": KIT_NAME, "CFBundlePackageType": "APPL", "CFBundleShortVersionString": KIT_VERSION,
        "CFBundleVersion": KIT_VERSION, "CFBundleIconFile": KIT_SLUG, "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    }
    (staging / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
    run = resources / f"{KIT_NAME}.command"
    run.write_text(command_file(), encoding="utf-8")
    run.chmod(0o755)
    exe = macos / KIT_NAME
    exe.write_text('#!/bin/sh\nexec open -a Terminal "$(dirname "$0")/../Resources/' + f'{KIT_NAME}.command"\n',
                   encoding="utf-8")
    exe.chmod(0o755)
    if ICON_PNG.exists():
        from PIL import Image

        Image.open(ICON_PNG).convert("RGBA").save(resources / f"{KIT_SLUG}.icns")
    app.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(app, ignore_errors=True)
    staging.rename(app)
    os.utime(app)          # Finder caches icons: a fresh date makes it read the new one
    return str(app)


def desktop_exec(target: Path) -> str:
    """A path quoted for a .desktop file's Exec line: the quoting rule escapes " ` $ and \\ inside double quotes,
    then the string rule doubles every backslash, and % is written %%."""
    quoted = "".join("\\" + c if c in '"`$\\' else c for c in str(target))
    return ('"' + quoted + '"').replace("\\", "\\\\").replace("%", "%%")


def desktop_entry() -> str:
    return (f"[Desktop Entry]\nType=Application\nName={KIT_NAME}\nComment={COMMENT}\n"
            f"Exec={desktop_exec(P.ROOT / 'bin' / 'reelforge')}\n"
            f"Icon={ICON_PNG}\nTerminal=true\nCategories=AudioVideo;Video;\nStartupNotify=false\n")


def _linux() -> str:
    entry = path()
    entry.parent.mkdir(parents=True, exist_ok=True)
    tmp = entry.with_name(entry.name + ".rf-new")
    tmp.write_text(desktop_entry(), encoding="utf-8")
    tmp.chmod(0o755)                    # some desktops only trust launchers marked executable
    os.replace(tmp, entry)
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(entry.parent)], capture_output=True)
    return str(entry)
