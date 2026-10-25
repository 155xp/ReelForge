"""ReelForge's profile in Windows Terminal: the anvil on ReelForge's tab, and ReelForge in Terminal's + menu.

Windows Terminal, where Windows 11 opens ReelForge.bat, gives each tab its profile's icon; a window it doesn't know
gets a plain console icon. So ReelForge adds a profile of its own as a fragment
(learn.microsoft.com/windows/terminal/json-fragment-extensions), with the anvil beside it:

  %LOCALAPPDATA%\\Microsoft\\Windows Terminal\\Fragments\\ReelForge\\ReelForge.json and reelforge-terminal.png

The profile's command line is the one Windows itself starts for ReelForge.bat (from the desktop shortcut, the Start
menu or a double-click), so Terminal matches those windows to the profile and they show the anvil. A tab you type
reelforge into keeps its own icon: Terminal gives programs no way to change it.

ReelForge checks the fragment each time it opens and rewrites it when something in it is out of date (a moved folder,
a new icon); Terminal reads it the next time it starts. A test copy, or STUDIO_DRY_SYSTEM=1, leaves it alone; the
Windows installer's uninstaller deletes it.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
from pathlib import Path

from . import KIT_NAME
from . import paths as P

ICON = P.ROOT / "assets" / "icon" / "reelforge-terminal.png"
# The id Terminal itself gives a "ReelForge" profile in a "ReelForge" fragment folder (a version 5 UUID from its
# fragment namespace), written down so the profile keeps it whatever it's called later.
GUID = "{4a26ff64-1d6a-5404-b35f-6e622f71b85b}"
# Writes the files in RF_FILES ("name=base64;...") into the folder RF_FRAGMENT, in that order. .NET's own file calls,
# because PowerShell's file commands can't find a folder given by its short name (C:\Users\JOHNSM~1\...).
WRITE = ("$ErrorActionPreference = 'Stop'; $d = $env:RF_FRAGMENT; [IO.Directory]::CreateDirectory($d) | Out-Null; "
         "foreach ($f in $env:RF_FILES -split ';') { $name, $data = $f -split '=', 2; "
         "[IO.File]::WriteAllBytes([IO.Path]::Combine($d, $name), [Convert]::FromBase64String($data)) }")


def folder() -> Path:
    """ReelForge's folder among this user's Terminal fragments."""
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "Microsoft" / "Windows Terminal" / "Fragments" / KIT_NAME


def command_line() -> str:
    """How Windows starts ReelForge.bat when it's opened from Explorer. Terminal gives a window the profile whose
    command line it starts with, so this is copied exactly: the doubled quote and the space before the last one."""
    cmd = os.environ.get("ComSpec") or r"C:\Windows\System32\cmd.exe"
    return f'{cmd} /c ""{P.ROOT / "ReelForge.bat"}" "'


def fragment() -> dict:
    return {"profiles": [{"guid": GUID, "name": KIT_NAME, "commandline": command_line(),
                          "startingDirectory": str(P.ROOT), "icon": str(folder() / ICON.name)}]}


def files() -> dict[str, bytes]:
    """The fragment folder's files by name, the icon first so the profile never points at a missing one."""
    return {ICON.name: ICON.read_bytes(),
            f"{KIT_NAME}.json": (json.dumps(fragment(), indent=2, ensure_ascii=False) + "\n").encode("utf-8")}


def _write(where: Path, files: dict[str, bytes]) -> None:
    """Write the files with PowerShell rather than ReelForge's own Python. Python from the Microsoft Store runs as a
    packaged app, and Windows quietly keeps the folders a packaged app makes in AppData in that app's private copy,
    where Terminal never looks; the programs it starts write to the real folder."""
    env = {**os.environ, "RF_FRAGMENT": str(where),
           "RF_FILES": ";".join(f"{name}={base64.b64encode(data).decode('ascii')}" for name, data in files.items())}
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", WRITE],
                       env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode != 0:
        raise RuntimeError((r.stderr.strip().splitlines() or ["PowerShell couldn't write the profile"])[-1])


def ensure() -> str:
    """Add ReelForge's profile to Windows Terminal, or bring it up to date. Returns a sentence saying what happened."""
    if P.test_copy():
        return "Left alone in a test copy: Windows Terminal's ReelForge profile stays with your main ReelForge."
    if P.dry_system():
        return "(dry run) would add ReelForge's profile to Windows Terminal"
    if not P.WINDOWS:
        return "Windows Terminal is only on Windows."
    where, wanted = folder(), files()
    if all((where / name).is_file() and (where / name).read_bytes() == data for name, data in wanted.items()):
        return "Windows Terminal's ReelForge profile is up to date."
    _write(where, wanted)
    return "ReelForge's profile is in Windows Terminal: its tab shows the anvil from Terminal's next start."
