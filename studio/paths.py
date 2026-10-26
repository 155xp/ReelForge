"""Where everything lives. All paths are relative to the kit folder, so it can sit anywhere.

A channel's own files are the profile's this process works on (studio/profiles.py), looked up each time they're used:
PROFILE, and its MY_STUDIO (your answers and settings, never part of the download), ANSWERS, SETTINGS, BIBLE,
BACKUPS, EPISODES and COMPLETED. For the first profile they're the ReelForge folder's own, as they always were."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import profiles

ROOT = Path(__file__).resolve().parent.parent
_CHANNEL = {"MY_STUDIO": "my_studio", "ANSWERS": "answers", "SETTINGS": "settings", "BIBLE": "bible",
            "BACKUPS": "backups", "EPISODES": "episodes", "COMPLETED": "completed"}


def __getattr__(name: str):
    if name == "PROFILE":
        return profiles.current()
    if name in _CHANNEL:
        return getattr(profiles.current(), _CHANNEL[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


RESEARCH = ROOT / "research"
TOOLS = ROOT / "tools"                    # Blender and ffmpeg downloaded by setup
SFX = ROOT / "assets" / "sfx"
FONTS = ROOT / "assets" / "fonts"
TEMPLATES = Path(__file__).resolve().parent / "templates"
EXAMPLES = ROOT / "examples"
DASHBOARD = ROOT / "dashboard"            # the ReelForge window: stats and publishing
TEST_COPY = ROOT / "TEST-COPY.txt"        # marks a second ReelForge folder for trying things (see test_copy())

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"


RUNNABLE = ("bin/reelforge", "setup.sh", "reelforge.sh", "onboard.sh")   # and the macOS download's .command files


def keep_runnable() -> None:
    """macOS and Linux: keep the launchers runnable. Updates made by ReelForge 1.0.4 and older unpacked the macOS zip
    without its file permissions, so a launcher the update had changed stopped being runnable; ReelForge puts that
    right each time it starts (the launcher starts it again straight after an update)."""
    if WINDOWS:
        return
    for f in [*(ROOT / r for r in RUNNABLE), *ROOT.glob("*.command")]:
        try:
            if f.is_file() and not os.access(f, os.X_OK):
                f.chmod(0o755)
        except OSError:
            pass


def venv_python() -> str:
    """The command that runs the kit's Python, written the way this OS spells it (for docs and messages)."""
    return r".venv\Scripts\python" if WINDOWS else ".venv/bin/python"


def rel(path: Path) -> str:
    """A path relative to the kit folder, with this OS's separators."""
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def free_gb(path: Path = ROOT) -> float:
    import shutil

    return shutil.disk_usage(path).free / 1e9


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def test_copy() -> bool:
    """A test copy (a second ReelForge folder for trying changes or replaying setup) has TEST-COPY.txt in it. Its
    window says TEST, and it never changes the computer: the reelforge command, the hourly stats job, the desktop
    shortcut and Windows Terminal's ReelForge profile stay with your main ReelForge folder."""
    return TEST_COPY.exists()


def dry_system() -> bool:
    """Leave the PATH, the scheduler, the desktop and Windows Terminal alone: STUDIO_DRY_SYSTEM=1 (tests), or a test
    copy."""
    return env_flag("STUDIO_DRY_SYSTEM") or test_copy()
