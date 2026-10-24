"""Where everything lives. All paths are relative to the kit folder, so it can sit anywhere."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MY_STUDIO = ROOT / "my-studio"            # your answers and settings (never part of the download)
ANSWERS = MY_STUDIO / "answers.json"
SETTINGS = MY_STUDIO / "studio.toml"
BIBLE = MY_STUDIO / "channel-bible.md"
BACKUPS = MY_STUDIO / "backups"
EPISODES = ROOT / "episodes"
COMPLETED = ROOT / "completed videos"
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
    window says TEST, and it never changes the computer: the reelforge command, the hourly stats job and the desktop
    shortcut stay with your main ReelForge folder."""
    return TEST_COPY.exists()


def dry_system() -> bool:
    """Leave the PATH, the scheduler and the desktop alone: STUDIO_DRY_SYSTEM=1 (tests), or a test copy."""
    return env_flag("STUDIO_DRY_SYSTEM") or test_copy()
